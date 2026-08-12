"""階段三：依探測結果為 763 筆資料集分級，並驗證分級本身的一致性。

分級規則只讀 probe-results.jsonl 的原始訊號，不重打端點——規則要調整時
重跑本程式即可，不必再對政府主機發一次請求。

分級（每個資料集取其資源中最好的一級）：
  真資料    端點回可解析內容且有記錄，非連結殼
  連結殼    有記錄，但欄位是檔案連結（如原民會就業的「檔案pdf」），真正的數字在 PDF 裡
  二進位    回傳 PDF / ZIP / XLS 本體，需另行解析才知有無資料
  空資料    可解析但 0 筆記錄
  HTML殼    宣稱資料格式卻回 HTML（SPA、錯誤頁或登入頁）
  失效      連線失敗或 HTTP 錯誤
  無資源    清單上沒有任何資源網址
"""

from __future__ import annotations

import collections
import csv
import json
import pathlib
import sys

JSONL = pathlib.Path("data/raw/catalog/probe-results.jsonl")
CATALOG = pathlib.Path("catalog/odportal-763.csv")
RESOURCES = pathlib.Path("data/raw/catalog/odportal-resources.json")
OUT = pathlib.Path("catalog/odportal-763-graded.csv")
REPORT = pathlib.Path("catalog/品質分級報告.md")

# 由好到壞；資料集取其資源中最好的一級
ORDER = ["真資料", "二進位", "連結殼", "空資料", "HTML殼", "失效", "無資源"]


def grade_resource(rec: dict) -> str:
    status = rec.get("status") or ""
    if status.startswith("http_") and status != "http_200":
        return "失效"
    if status in ("error", "crash", "bad_url"):
        return "失效"

    kind = rec.get("kind")
    if kind == "html":
        return "HTML殼"
    if kind in ("pdf", "zip", "xls"):
        return "二進位"

    records = rec.get("records")
    if records is None:
        return "失效"
    if records == 0:
        return "空資料"

    # 連結殼：欄位名點名檔案／連結，且確實有值是網址
    file_keys = rec.get("file_keys") or []
    url_ratio = rec.get("url_ratio") or 0
    if file_keys and url_ratio > 0:
        return "連結殼"
    return "真資料"


def best(grades: list[str]) -> str:
    for g in ORDER:
        if g in grades:
            return g
    return "無資源"


def main() -> int:
    if not JSONL.exists():
        print(f"找不到 {JSONL}，請先執行 probe_resources.py", file=sys.stderr)
        return 1

    # 重試會讓同一網址出現多列，以網址為鍵取最後一筆，後寫的為準
    latest: dict[str, dict] = {}
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("url"):
            latest[rec["url"]] = rec

    by_ds: dict[str, list[dict]] = collections.defaultdict(list)
    for rec in latest.values():
        by_ds[rec.get("nanoId")].append(rec)

    allres = {
        d["nanoId"]: d for d in json.loads(RESOURCES.read_text(encoding="utf-8"))
    }

    with CATALOG.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    out_rows = []
    for row in rows:
        nano = (row.get("ODPortal") or "").rsplit("/", 1)[-1]
        probes = by_ds.get(nano, [])
        n_res = len(allres.get(nano, {}).get("resources") or [])
        if not probes:
            grade = "無資源" if n_res == 0 else "未探測"
        else:
            grade = best([grade_resource(p) for p in probes])
        best_rec = max(
            (p for p in probes if p.get("records") is not None),
            key=lambda p: p.get("records") or 0,
            default={},
        )
        out_rows.append(
            {
                **row,
                "分級": grade,
                "資源總數": n_res,
                "已探測資源": len(probes),
                "最大記錄數": best_rec.get("records", ""),
                "檔案類欄位": ";".join(best_rec.get("file_keys") or []),
                "實際型態": ";".join(
                    sorted({str(p.get("kind")) for p in probes if p.get("kind")})
                ),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---- 驗證：分級結果本身要通過的檢查 ----
    tally = collections.Counter(r["分級"] for r in out_rows)
    problems: list[str] = []
    if len(out_rows) != 763:
        problems.append(f"資料集筆數為 {len(out_rows)}，應為 763")
    if tally.get("未探測", 0):
        problems.append(f"仍有 {tally['未探測']} 筆未探測，探測尚未跑完")
    graded = sum(v for k, v in tally.items() if k != "未探測")
    if graded and tally.get("真資料", 0) == 0:
        problems.append("真資料為 0 筆，分級規則可能有誤")
    for r in out_rows:
        if r["分級"] == "真資料" and not str(r["最大記錄數"]).strip():
            problems.append(f"分級為真資料卻無記錄數：{r['名稱'][:30]}")
            break

    # 已知答案回歸檢查：盤點文件記載的標準答案
    known = {"OsTvtc-a": "連結殼"}
    idx = {(r.get("ODPortal") or "").rsplit("/", 1)[-1]: r for r in out_rows}
    for nano, expect in known.items():
        got = idx.get(nano, {}).get("分級")
        if got and got != expect:
            problems.append(f"已知答案不符：{nano} 應為 {expect}，實得 {got}")

    lines = [
        "# 763 筆開放資料集品質分級",
        "",
        "以實際打端點取回的內容判定，不採信 metadata 的格式欄。",
        f"探測樣本：每個資料集最多 2 個代表性資源（頭尾各一）。",
        "",
        "| 分級 | 筆數 | 佔比 |",
        "|---|---:|---:|",
    ]
    total = len(out_rows)
    for g in ORDER + ["未探測"]:
        if tally.get(g):
            lines.append(f"| {g} | {tally[g]} | {tally[g]/total:.1%} |")
    lines += ["", f"合計 {total} 筆。", ""]

    if problems:
        lines += ["## ⚠️ 驗證未通過", ""] + [f"- {p}" for p in problems] + [""]
    else:
        lines += ["## ✅ 驗證通過", "", "- 筆數為 763", "- 無未探測項目",
                  "- 已知答案回歸檢查相符（原民會就業＝連結殼）", ""]

    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"寫出 {OUT}")
    print(f"寫出 {REPORT}")
    print()
    for g in ORDER + ["未探測"]:
        if tally.get(g):
            print(f"  {g:>6}  {tally[g]:>4}  {tally[g]/total:>6.1%}")
    print()
    if problems:
        print("⚠️ 驗證未通過：")
        for p in problems:
            print("  -", p)
        return 2
    print("✅ 驗證通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
