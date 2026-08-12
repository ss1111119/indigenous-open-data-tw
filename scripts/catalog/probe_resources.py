"""階段二：實際打資源端點，判定每筆資料集是真資料、PDF 殼、還是已失效。

盤點第一條陷阱：格式標示不可信（原民會就業標 JSON/XML/CSV，實際是 24 筆 PDF
連結清單）。因此分級一律以「實際回傳內容」判定，不看 metadata 的格式欄。

每個資料集只探測代表性資源（預設頭尾各一，去重後最多 N 個），不打全部 5,409 個。

可中斷續跑：結果逐筆 append 到 JSONL，重跑時自動跳過已完成的資源網址。
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import pathlib
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

RESOURCES = pathlib.Path("data/raw/catalog/odportal-resources.json")
CATALOG = pathlib.Path("catalog/odportal-763.csv")
OUTDIR = pathlib.Path("data/raw/catalog")
JSONL = OUTDIR / "probe-results.jsonl"

UA = "indigenous-open-data-tw/0.1 (dataset quality survey; contact via GitHub)"
READ_LIMIT = 256 * 1024  # 只抓前 256KB，足以判定型態
PER_HOST_CONCURRENCY = 2
PER_HOST_DELAY = 0.4

_host_locks: dict[str, threading.Semaphore] = {}
_host_last: dict[str, float] = {}
_registry_lock = threading.Lock()
_write_lock = threading.Lock()

PDF_IN_VALUE = re.compile(r"\.pdf(\?|$|#)", re.I)
# 實測：原民會就業那筆的連結是 DownloadFile.aspx?filno=<guid>，網址裡沒有 .pdf，
# 靠副檔名比對抓不到。真正的訊號是欄位名（檔案pdf）與「值幾乎全是連結、沒有數字」。
FILE_KEY = re.compile(
    r"pdf|檔案|附件|下載|連結|網址|url|link|download|file", re.I
)
URL_VALUE = re.compile(r"^\s*https?://", re.I)
NUMERIC_VALUE = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*$")


def shell_signals(rows: list) -> dict:
    """判定「連結殼」：記錄存在但內容只是檔案連結，不是可用資料。

    回傳欄位名中的檔案類關鍵字、值為連結的比例、值為數字的比例。
    """
    out: dict = {"file_keys": [], "url_ratio": None, "numeric_ratio": None}
    scalars: list[str] = []
    keys: set[str] = set()
    for r in rows[:200]:
        if isinstance(r, dict):
            for k, v in r.items():
                keys.add(str(k))
                if isinstance(v, (str, int, float)) and v is not None:
                    scalars.append(str(v))
    if not scalars:
        return out
    out["file_keys"] = sorted(k for k in keys if FILE_KEY.search(k))[:6]
    out["url_ratio"] = round(
        sum(1 for v in scalars if URL_VALUE.match(v)) / len(scalars), 3
    )
    out["numeric_ratio"] = round(
        sum(1 for v in scalars if NUMERIC_VALUE.match(v)) / len(scalars), 3
    )
    return out


def host_gate(host: str) -> threading.Semaphore:
    with _registry_lock:
        if host not in _host_locks:
            _host_locks[host] = threading.Semaphore(PER_HOST_CONCURRENCY)
        return _host_locks[host]


def polite_wait(host: str) -> None:
    with _registry_lock:
        last = _host_last.get(host, 0.0)
        wait = PER_HOST_DELAY - (time.time() - last)
        _host_last[host] = time.time() + max(wait, 0.0)
    if wait > 0:
        time.sleep(wait)


def sniff(body: bytes, ctype: str) -> str:
    head = body[:512].lstrip()
    if body[:4] == b"%PDF":
        return "pdf"
    if body[:2] == b"PK":
        return "zip"
    if body[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    low = head[:400].lower()
    if low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low:
        return "html"
    if head[:1] in (b"{", b"["):
        return "json"
    if head[:5] == b"<?xml" or head[:1] == b"<":
        return "xml"
    if "json" in ctype:
        return "json"
    if "xml" in ctype:
        return "xml"
    if "html" in ctype:
        return "html"
    if "pdf" in ctype:
        return "pdf"
    return "text"


def iter_values(obj, depth: int = 0):
    """走訪 JSON 結構取出純量值，用於偵測 PDF 連結殼。"""
    if depth > 6:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from iter_values(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:200]:
            yield from iter_values(v, depth + 1)
    elif isinstance(obj, str):
        yield obj


def deep_records(obj, depth: int = 0) -> list:
    """遞迴找出最大的「物件陣列」，避開 CKAN 之類的外層包裝。

    實測遇到的包裝：`[{"success":true,"result":{"fields":[...],"records":[...]}}]`
    直接取頂層長度會得到 1，必須往下找真正的資料列。
    """
    best: list = []
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:20]):
            best = obj
        if depth < 6:
            for v in obj[:50]:
                cand = deep_records(v, depth + 1)
                if len(cand) > len(best):
                    best = cand
    elif isinstance(obj, dict) and depth < 6:
        # fields 是欄位定義不是資料列，排除以免蓋過真正的 records
        for k, v in obj.items():
            if k == "fields":
                continue
            cand = deep_records(v, depth + 1)
            if len(cand) > len(best):
                best = cand
    return best


RECORD_SEP = re.compile(rb"\}\s*,\s*\{")


def analyse(body: bytes, kind: str, truncated: bool = False) -> dict:
    """回傳 records 筆數與 pdf 連結佔比。無法解析時 records 為 None。"""
    out: dict = {"records": None, "pdf_ratio": None, "note": ""}
    try:
        if kind == "json":
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                if truncated:
                    # 截斷導致無法解析屬預期情形，以物件邊界估算下限
                    out["records"] = len(RECORD_SEP.findall(body))
                    out["records_approx"] = True
                    txt = body.decode("utf-8", errors="replace")
                    hits = len(PDF_IN_VALUE.findall(txt))
                    out["pdf_ratio"] = round(hits / max(out["records"], 1), 3)
                    out["note"] = "截斷，筆數為下限估計"
                    return out
                raise
            rows = deep_records(data)
            out["records"] = len(rows)
            vals = list(iter_values(rows if rows else data))
            if vals:
                hits = sum(1 for v in vals if PDF_IN_VALUE.search(v))
                out["pdf_ratio"] = round(hits / len(vals), 3)
            out.update(shell_signals(rows))
        elif kind in ("text",):
            text = body.decode("utf-8-sig", errors="replace")
            rows = list(csv.reader(io.StringIO(text)))
            rows = [r for r in rows if any(c.strip() for c in r)]
            out["records"] = max(len(rows) - 1, 0)
            flat = [c for r in rows for c in r]
            if flat:
                hits = sum(1 for c in flat if PDF_IN_VALUE.search(c))
                out["pdf_ratio"] = round(hits / len(flat), 3)
            if rows:
                header = [h.strip() for h in rows[0]]
                dicts = [dict(zip(header, r)) for r in rows[1:201]]
                out.update(shell_signals(dicts))
        elif kind == "xml":
            text = body.decode("utf-8", errors="replace")
            tags = re.findall(r"<(\w+)[\s/>]", text)
            counts = collections.Counter(tags)
            out["records"] = counts.most_common(1)[0][1] if counts else 0
            hits = len(PDF_IN_VALUE.findall(text))
            out["pdf_ratio"] = round(hits / max(len(tags), 1), 3)
    except Exception as exc:  # noqa: BLE001 - 解析失敗是分級訊號，不是崩潰理由
        out["note"] = f"{type(exc).__name__}: {exc}"[:160]
    return out


def encode_url(url: str) -> str:
    """對網址中的非 ASCII 字元做百分比編碼。

    實測：`https://www.vac.gov.tw/files/i2原住民退除役官兵人數按縣市及性別分.csv`
    直接送進 urllib 會拋 UnicodeEncodeError，被誤記成端點失效。
    """
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc.encode("idna").decode("ascii")
            if any(ord(c) > 127 for c in parts.netloc)
            else parts.netloc,
            urllib.parse.quote(parts.path, safe="/%:@&=+$,~()!*'"),
            urllib.parse.quote(parts.query, safe="/%:@&=+$,~()!*'?"),
            parts.fragment,
        )
    )


def probe(res: dict, nano: str) -> dict:
    url = res.get("url") or ""
    rec = {
        "nanoId": nano,
        "url": url,
        "declared_format": res.get("format"),
        "resource_name": res.get("name"),
    }
    if not url.lower().startswith(("http://", "https://")):
        rec.update(status="bad_url", kind=None, records=None)
        return rec

    host = urllib.parse.urlsplit(url).netloc
    gate = host_gate(host)
    with gate:
        polite_wait(host)
        t0 = time.time()
        try:
            req = urllib.request.Request(
                encode_url(url), headers={"User-Agent": UA, "Accept": "*/*"}
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read(READ_LIMIT)
                ctype = (resp.headers.get("Content-Type") or "").lower()
                code = resp.status
                final = resp.geturl()
        except urllib.error.HTTPError as exc:
            rec.update(
                status=f"http_{exc.code}", kind=None, records=None,
                elapsed=round(time.time() - t0, 1),
            )
            return rec
        except Exception as exc:  # noqa: BLE001 - 網路錯誤是分級訊號
            rec.update(
                status="error", error=f"{type(exc).__name__}: {exc}"[:160],
                kind=None, records=None, elapsed=round(time.time() - t0, 1),
            )
            return rec

    kind = sniff(body, ctype)
    truncated = len(body) >= READ_LIMIT
    info = analyse(body, kind, truncated)
    rec.update(
        status=f"http_{code}",
        kind=kind,
        content_type=ctype[:80],
        bytes=len(body),
        truncated=truncated,
        final_url=final if final != url else None,
        elapsed=round(time.time() - t0, 1),
        **info,
    )
    return rec


def pick(resources: list[dict], per_dataset: int) -> list[dict]:
    """取代表性資源：頭尾各一（抓得到「舊的能用、新的壞掉」），並盡量涵蓋不同格式。"""
    live = [r for r in resources if r.get("url")]
    if not live:
        return []
    if len(live) <= per_dataset:
        return live
    chosen = [live[0], live[-1]]
    seen_fmt = {(r.get("format") or "").upper() for r in chosen}
    for r in live[1:-1]:
        if len(chosen) >= per_dataset:
            break
        f = (r.get("format") or "").upper()
        if f not in seen_fmt:
            chosen.append(r)
            seen_fmt.add(f)
    return chosen[:per_dataset]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-dataset", type=int, default=2)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 個資料集（試跑用）")
    ap.add_argument(
        "--retry-failed",
        action="store_true",
        help="只重跑先前失敗的資源，用於區分暫時性故障與真正失效",
    )
    args = ap.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)
    with CATALOG.open(encoding="utf-8-sig", newline="") as fh:
        catalog = {
            row["ODPortal"].rsplit("/", 1)[-1]
            for row in csv.DictReader(fh)
            if row.get("ODPortal")
        }
    allres = {d["nanoId"]: d for d in json.loads(RESOURCES.read_text(encoding="utf-8"))}

    done: set[str] = set()
    if JSONL.exists():
        # 以網址為鍵取最後一筆，重試會產生同網址多列，後寫的為準
        latest: dict[str, dict] = {}
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001,S112
                continue
            if r.get("url"):
                latest[r["url"]] = r
        if args.retry_failed:
            done = {u for u, r in latest.items() if r.get("status") == "http_200"}
            print(
                f"重試模式：已成功 {len(done)} 個，"
                f"待重試 {len(latest) - len(done)} 個",
                flush=True,
            )
        else:
            done = set(latest)
            print(f"續跑：已完成 {len(done)} 個資源網址", flush=True)

    jobs: list[tuple[dict, str]] = []
    targets = sorted(catalog)
    if args.limit:
        targets = targets[: args.limit]
    for nano in targets:
        d = allres.get(nano)
        if not d:
            continue
        for r in pick(d.get("resources") or [], args.per_dataset):
            if r.get("url") not in done:
                jobs.append((r, nano))

    print(
        f"資料集 {len(targets)} 個，待探測資源 {len(jobs)} 個"
        f"（每集最多 {args.per_dataset}，併發 {args.workers}，每主機 {PER_HOST_CONCURRENCY}）",
        flush=True,
    )
    if not jobs:
        print("沒有待辦工作，全部已完成。", flush=True)
        return 0

    t0 = time.time()
    tally: collections.Counter = collections.Counter()
    with JSONL.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(
        max_workers=args.workers
    ) as pool:
        futs = {pool.submit(probe, r, n): (r, n) for r, n in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            r, n = futs[fut]
            try:
                rec = fut.result()
            except Exception as exc:  # noqa: BLE001 - 單筆失敗不可拖垮整批
                rec = {
                    "nanoId": n,
                    "url": r.get("url"),
                    "status": "crash",
                    "error": f"{type(exc).__name__}: {exc}"[:160],
                }
            with _write_lock:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
            tally[rec.get("status", "?")] += 1
            if i % 25 == 0 or i == len(jobs):
                el = time.time() - t0
                rate = i / el if el else 0
                eta = (len(jobs) - i) / rate if rate else 0
                print(
                    f"  {i}/{len(jobs)}  {el/60:.1f} 分經過  ETA {eta/60:.1f} 分  "
                    f"{dict(tally.most_common(5))}",
                    flush=True,
                )

    print(f"\n完成，耗時 {(time.time()-t0)/60:.1f} 分。結果寫入 {JSONL}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
