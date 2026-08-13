"""取得教育部原住民學生概況統計原始工作簿（103–114 學年）。

網址規律：
    https://stats.moe.gov.tw/files/ebook/indigenous/{學年}/{學年}indigenous.{ext}

副檔名分界在 108/109：103–108 為 `.xls`、109 起為 `.xlsx`（2026-08-12 實測，
108 的 `.xlsx` 回 404）。故按年度先試對應副檔名，再退回另一種，而非假設單一副檔名。

`data/raw/` 不入版控，所以取檔必須可重跑：已存在且可開啟的檔案不重新下載，
下游建置在檔案齊備時完全不連網。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
import urllib.error
import urllib.request

RAW = pathlib.Path("data/raw/moe")
URL = "https://stats.moe.gov.tw/files/ebook/indigenous/{year}/{year}indigenous{ext}"
UA = "indigenous-open-data-tw/0.1 (public statistics flattening; contact via GitHub)"

FIRST_YEAR = 103
LAST_YEAR = 114
# 副檔名分界：<= 108 為 .xls，>= 109 為 .xlsx
XLSX_FROM = 109


def extensions_for(year: int) -> list[str]:
    """回傳該學年應嘗試的副檔名，慣用者在前。

    兩種都列出是刻意的——分界是實測得知的慣例而非保證，若上游改版，
    退回另一種副檔名比整批失敗好。實際取到哪一種由回應決定。
    """
    return [".xls", ".xlsx"] if year < XLSX_FROM else [".xlsx", ".xls"]


def existing(year: int) -> pathlib.Path | None:
    """回傳該學年已存在且非空的本機檔案，沒有則 None。"""
    for ext in extensions_for(year):
        path = RAW / f"{year}indigenous{ext}"
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def download(url: str, dest: pathlib.Path, timeout: int = 120) -> None:
    """下載至暫存檔後改名，避免中斷留下半截檔案被誤認為已取得。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body:
        raise ValueError(f"回應為空：{url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(body)
    tmp.replace(dest)


def fetch_year(year: int) -> tuple[pathlib.Path, bool]:
    """取得單一學年的工作簿，回傳（本機路徑, 是否實際下載過）。

    已存在且非空者直接回傳，不重新下載。所有副檔名皆失敗時 raise
    RuntimeError 並列出每一個嘗試過的網址——不靜默略過該學年。
    """
    have = existing(year)
    if have is not None:
        print(f"{year} 學年  已存在，略過下載：{have.name}", flush=True)
        return have, False

    attempted: list[str] = []
    for ext in extensions_for(year):
        url = URL.format(year=year, ext=ext)
        attempted.append(url)
        dest = RAW / f"{year}indigenous{ext}"
        try:
            download(url, dest)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            print(f"{year} 學年  {ext} 失敗（{type(exc).__name__}: {exc}）", flush=True)
            continue
        print(f"{year} 學年  取得 {dest.name}（{dest.stat().st_size:,} bytes）", flush=True)
        return dest, True

    raise RuntimeError(
        f"{year} 學年所有副檔名皆取檔失敗。嘗試過的網址：\n  "
        + "\n  ".join(attempted)
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", type=int, default=FIRST_YEAR, help="起始學年（民國）")
    ap.add_argument("--to", dest="end", type=int, default=LAST_YEAR, help="結束學年（民國）")
    args = ap.parse_args(argv)

    if args.start > args.end:
        ap.error(f"起始學年 {args.start} 大於結束學年 {args.end}")

    RAW.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    got: list[pathlib.Path] = []
    downloaded = 0

    for year in range(args.start, args.end + 1):
        try:
            path, did_download = fetch_year(year)
        except RuntimeError as exc:
            failed.append(str(exc))
            continue
        got.append(path)
        if did_download:
            downloaded += 1
            time.sleep(0.5)

    print(
        f"\n{args.start}–{args.end} 學年：齊備 {len(got)} 份"
        f"（本次下載 {downloaded} 份），失敗 {len(failed)} 份"
    )
    for msg in failed:
        print(f"\n{msg}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
