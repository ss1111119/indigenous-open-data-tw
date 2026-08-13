"""取得戶政司 ODRP018 各期別，驗證後聚合到鄉鎮市區，捨棄村里明細。

    python -m scripts.moi.fetch --from 10701 --to 11507

⚠️ **村里明細只過記憶體，不落地。** 專案的倫理界線是輸出止於鄉鎮市區；實測村里
層級 7,524 個非零列中有 1,897 列少於 10 人，且「村里 × 單一族別 × 性別」有 32,936
格的值是 1 或 2。保留村里的唯一功能是輸出更細的粒度，那是專案承諾永不做的事。

此捨棄**不可逆**：聚合無法還原明細，要恢復只能重抓。所以驗證必須在捨棄前做完，
且結果寫進 manifest，使日後仍能查核當時驗過什麼。
"""

from __future__ import annotations

import argparse
import collections
import csv
import http.client
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import registry as reg

RAW = pathlib.Path("data/raw/moi")
MANIFEST = RAW / "manifest.jsonl"
URL = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/{code}/{period}"
UA = "indigenous-open-data-tw/0.1 (public statistics flattening; contact via GitHub)"

# 來源回應碼：成功與「查無資料」（尚未發布）
CODE_OK = "OD-0101-S"
CODE_NO_DATA = "OD-0102-S"

LONG_COLUMNS = ("期別", "縣市", "鄉鎮市區", "身分別", "族別", "性別", "人數")
DELAY_SECONDS = 1.0


class FetchError(RuntimeError):
    """取檔階段的阻斷性錯誤。不設靜默降級路徑。"""


class NotPublished(Exception):
    """該期別尚未發布——是正常邊界，不是錯誤。"""


def _num(value: object) -> int:
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return 0
    if not text.lstrip("-").isdigit():
        raise FetchError(f"指標儲存格無法讀為整數：{value!r}")
    return int(text)


# 單頁約 7 MB，連線中途斷掉（IncompleteRead）是實測會發生的暫時性故障。
# 專案既有作法是重試以區分暫時性故障與真失效（見 docs/來源盤點.md 的分級管線）。
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5.0

# IncompleteRead 是 http.client.HTTPException，不是 OSError 子類，必須單獨列出，
# 否則會以未捕捉的例外炸掉整批而不是只失敗該期
TRANSIENT = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    http.client.HTTPException,
    OSError,
    json.JSONDecodeError,
)


def _request(url: str) -> dict:
    """發一個請求並解析 JSON，暫時性故障重試。全部嘗試失敗才 raise FetchError。"""
    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read())
        except TRANSIENT as exc:
            last = exc
            if attempt < MAX_ATTEMPTS:
                print(
                    f"    重試 {attempt}/{MAX_ATTEMPTS - 1}："
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise FetchError(
        f"重試 {MAX_ATTEMPTS} 次後仍失敗：{url}"
        f"（{type(last).__name__}: {last}）"
    )


def fetch_period(period: int, code: str = reg.DATASET) -> list[dict]:
    """取得單一期別的全部村里列。

    依來源回報的頁數請求全部頁面；只讀第一頁會靜默丟掉約四分之三的資料。
    收集列數與來源回報的總列數不符即中止。
    """
    base = URL.format(code=code, period=period)
    # _request 已內含重試，全部失敗才 raise FetchError——那是「請求失敗」而非
    # 「尚未發布」，兩者由 responseCode 區分，見下
    first = _request(base)

    response_code = str(first.get("responseCode", ""))
    if response_code == CODE_NO_DATA:
        raise NotPublished(period)
    if response_code != CODE_OK:
        raise FetchError(
            f"{code}/{period} 回傳非預期的 responseCode={response_code!r}"
            f"（訊息：{first.get('responseMessage')!r}）"
        )

    reported = int(first["totalDataSize"])
    pages = int(first["totalPage"])
    rows = list(first.get("responseData") or [])
    for page in range(2, pages + 1):
        time.sleep(DELAY_SECONDS)
        data = _request(f"{base}?page={page}")
        rows.extend(data.get("responseData") or [])

    if len(rows) != reported:
        raise FetchError(
            f"{code}/{period} 取得 {len(rows)} 列，來源回報 {reported} 列，"
            f"共 {pages} 頁——分頁不完整，不得繼續"
        )
    return rows


def _resolve_columns(
    period: int, columns: set[str], scheme: reg.NamingScheme, statuses: tuple[str, ...]
) -> tuple[dict[tuple[str, str], str], dict[str, str], list[str]]:
    """把註冊表的族別對到實際欄名，解析一次供逐列重用。

    回傳（身分別族別欄名, 頂層族別欄名, 族別聯集）。任一缺欄即報錯——那可能是
    新的改版，靜默略過會產出漏族的長表。
    """
    union: list[str] = []
    for status in statuses:
        for chinese in reg.peoples_for(status):
            if chinese not in union:
                union.append(chinese)

    per_status: dict[tuple[str, str], str] = {}
    for status in statuses:
        for chinese in reg.peoples_for(status):
            found = None
            for alias in scheme.aliases(chinese, status):
                if scheme.people(alias, "m", status) in columns:
                    found = alias
                    break
            if found is None:
                raise FetchError(
                    f"{period} 期缺少註冊表描述的欄位：{scheme.label} 方案下"
                    f"身分別 {status}、族別 {chinese}"
                )
            for sex in reg.SEXES:
                per_status[(status, chinese, sex)] = scheme.people(found, sex, status)

    top: dict[str, str] = {}
    for chinese in union:
        found = None
        for status in statuses:
            # 只查真的帶這一族的身分別——平埔獨有的族群不在平地／山地的清單裡，
            # 逐一硬查會在第一個身分別就報「沒有別名」
            if chinese not in reg.peoples_for(status):
                continue
            for alias in scheme.aliases(chinese, status):
                if scheme.people(alias, "m") in columns:
                    found = alias
                    break
            if found:
                break
        if found is None:
            raise FetchError(f"{period} 期缺少頂層族別欄位：{chinese}")
        for sex in reg.SEXES:
            top[(chinese, sex)] = scheme.people(found, sex)

    return per_status, top, union


def verify(
    period: int, rows: list[dict], scheme: reg.NamingScheme
) -> dict[str, int]:
    """逐列檢查七組恆等式。任一不符即中止，且不得寫出任何檔案。

    族別清單按身分別取自註冊表，不共用同一份——平地與山地各 17 族、平埔 12 族、
    頂層是聯集 27 族。用共用清單會在平埔轉非零後開始失敗。
    """
    statuses = reg.statuses_for(period)
    columns = set(rows[0])
    per_status, top, union = _resolve_columns(period, columns, scheme, statuses)
    location = scheme.dims["區域代碼"]

    checks = collections.Counter()
    for row in rows:
        where = f"{period} 期 村里代碼 {row.get(location)}"
        total = _num(row[scheme.top_total()])

        if total != sum(_num(row[scheme.top_total(s)]) for s in reg.SEXES):
            raise FetchError(f"{where} 恆等式 A 不符：總計 ≠ 男 + 女")
        checks["A"] += 1

        subtotals = sum(_num(row[scheme.status_total(s)]) for s in statuses)
        if total != subtotals:
            raise FetchError(
                f"{where} 恆等式 B 不符：總計 {total} ≠ 身分別小計之和 {subtotals}，"
                f"差 {total - subtotals}"
            )
        checks["B"] += 1

        by_people = sum(
            _num(row[top[(c, sex)]]) for c in union for sex in reg.SEXES
        )
        if total != by_people:
            raise FetchError(
                f"{where} 恆等式 C 不符：總計 {total} ≠ 族別聯集之和 {by_people}，"
                f"差 {total - by_people}"
            )
        checks["C"] += 1

        for status in statuses:
            expected = _num(row[scheme.status_total(status)])
            actual = sum(
                _num(row[per_status[(status, c, sex)]])
                for c in reg.peoples_for(status)
                for sex in reg.SEXES
            )
            if expected != actual:
                raise FetchError(
                    f"{where} 恆等式 D–F 不符：{reg.STATUSES[status]} 小計 "
                    f"{expected} ≠ 其族別之和 {actual}，差 {expected - actual}"
                )
            checks["D-F"] += 1

        for chinese in union:
            for sex in reg.SEXES:
                value = _num(row[top[(chinese, sex)]])
                parts = sum(
                    _num(row[per_status[(status, chinese, sex)]])
                    for status in statuses
                    if (status, chinese, sex) in per_status
                )
                if value != parts:
                    raise FetchError(
                        f"{where} 恆等式 G 不符：{chinese} {reg.SEXES[sex]} 頂層 "
                        f"{value} ≠ 各身分別之和 {parts}"
                    )
        checks["G"] += 1

    return dict(checks)


def aggregate(
    period: int, rows: list[dict], scheme: reg.NamingScheme
) -> list[dict[str, object]]:
    """聚合到鄉鎮市區，回傳長表形狀的明細列。

    只輸出「身分別 × 族別 × 性別」的最細組合；總計欄與身分別小計不入輸出，
    因為未過濾的彙總會使 groupby().sum() 得到數倍數字。
    """
    statuses = reg.statuses_for(period)
    per_status, _, _ = _resolve_columns(period, set(rows[0]), scheme, statuses)
    site_column = scheme.dims["行政區"]
    totals: dict[tuple[str, str, str, str, str], int] = collections.defaultdict(int)

    for row in rows:
        county, district = reg.split_site(row[site_column])
        for status in statuses:
            for chinese in reg.peoples_for(status):
                for sex_key, sex in reg.SEXES.items():
                    key = (county, district, reg.STATUSES[status], chinese, sex)
                    totals[key] += _num(row[per_status[(status, chinese, sex_key)]])

    return [
        {
            "期別": period,
            "縣市": county,
            "鄉鎮市區": district,
            "身分別": status,
            "族別": people,
            "性別": sex,
            "人數": count,
        }
        for (county, district, status, people, sex), count in sorted(totals.items())
    ]


def period_path(period: int) -> pathlib.Path:
    return RAW / f"{reg.DATASET}-{period}.csv"


def load_manifest() -> dict[int, dict]:
    if not MANIFEST.exists():
        return {}
    records = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[int(record["期別"])] = record
    return records


def _append_manifest(record: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_period(period: int, now: str) -> str:
    """取得、驗證、聚合、寫出單一期別。回傳處理結果的簡述。"""
    try:
        rows = fetch_period(period)
    except NotPublished:
        _append_manifest({
            "期別": period, "狀態": "尚未發布", "取檔時間": now,
        })
        return "尚未發布"

    scheme = reg.detect_scheme(rows[0])
    expected_columns = reg.expected_column_count(period)
    if len(rows[0]) != expected_columns:
        raise FetchError(
            f"{period} 期欄數為 {len(rows[0])}，註冊表宣告 {expected_columns}"
            f"（方案 {scheme.label}）。這可能是新的改版，"
            f"請查明後更新 scripts/moi/registry.py"
        )
    has_pingpu = scheme.status_total(reg.PINGPU_KEY) in set(rows[0])
    if has_pingpu != (period >= reg.PINGPU_FROM):
        raise FetchError(
            f"{period} 期的平埔欄位存在與否（{has_pingpu}）與註冊表宣告的下界 "
            f"{reg.PINGPU_FROM} 矛盾，請查明後更新註冊表"
        )

    checks = verify(period, rows, scheme)
    aggregated = aggregate(period, rows, scheme)
    districts = len({(r["縣市"], r["鄉鎮市區"]) for r in aggregated})

    path = period_path(period)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LONG_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(aggregated)

    _append_manifest({
        "期別": period,
        "狀態": "已取得",
        "來源回報列數": len(rows),
        "取得列數": len(rows),
        "頁數": (len(rows) + 1999) // 2000,
        "鄉鎮市區數": districts,
        "恆等式檢查": checks,
        "欄名版本": scheme.label,
        "欄數": len(rows[0]),
        "聚合後列數": len(aggregated),
        "取檔時間": now,
    })
    # 村里明細在此離開作用域，不落地
    return f"{districts} 個鄉鎮市區、{len(aggregated):,} 列（村里 {len(rows):,} 列已捨棄）"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", type=int, default=reg.FIRST_PERIOD)
    ap.add_argument("--to", dest="end", type=int, default=reg.LAST_KNOWN_PERIOD)
    args = ap.parse_args(argv)

    manifest = load_manifest()
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    periods = [
        p for p in range(args.start, args.end + 1)
        # 民國年月：月份只有 01–12，其餘數字不是合法期別
        if 1 <= p % 100 <= 12
    ]

    done = failed = skipped = unpublished = 0
    for period in periods:
        record = manifest.get(period)
        if record and record.get("狀態") == "已取得" and period_path(period).exists():
            skipped += 1
            continue
        try:
            outcome = process_period(period, now)
        except (FetchError, reg.RegistryError) as exc:
            print(f"{period}  ✗ {exc}", file=sys.stderr, flush=True)
            failed += 1
            continue
        if outcome == "尚未發布":
            unpublished += 1
        else:
            done += 1
        print(f"{period}  {outcome}", flush=True)
        time.sleep(DELAY_SECONDS)

    print(
        f"\n{args.start}–{args.end}：新取得 {done} 期、已存在略過 {skipped} 期、"
        f"尚未發布 {unpublished} 期、失敗 {failed} 期"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
