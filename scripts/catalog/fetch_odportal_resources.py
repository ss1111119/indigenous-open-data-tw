"""階段一：從 ODPortal 搜尋端點取回 763 筆資料集的資源網址。

搜尋頁把 Elasticsearch 原始回應塞在 __NEXT_DATA__ 裡，一頁 50 筆、以 offset 分頁
（page/p/from 都無效，會靜默回傳第一頁）。約 19 次請求即可取回全部。

輸出 data/raw/catalog/odportal-resources.json，供階段二探測使用。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

OUT = pathlib.Path("data/raw/catalog")
SEARCH = "https://odportal.tw/datasets/search?s={kw}&path=search&offset={off}"
UA = "indigenous-open-data-tw/0.1 (dataset quality survey; contact via GitHub)"
NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
# 盤點所用的關鍵字；名稱命中在 offset 900 附近歸零
KEYWORD = "原住民族"
MAX_OFFSET = 1000
STEP = 50


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    kw = urllib.parse.quote(KEYWORD)
    seen: dict[str, dict] = {}

    for off in range(0, MAX_OFFSET, STEP):
        url = SEARCH.format(kw=kw, off=off)
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001 - 逐頁失敗要看得到，不中止整批
            print(f"offset {off:>4}  取頁失敗 {type(exc).__name__}: {exc}", flush=True)
            continue

        m = NEXT_DATA.search(html)
        if not m:
            print(f"offset {off:>4}  找不到 __NEXT_DATA__，停止", flush=True)
            break

        try:
            hits = json.loads(m.group(1))["props"]["pageProps"]["datasetsResult"][
                "data"
            ]["hits"]["hits"]
        except (KeyError, json.JSONDecodeError) as exc:
            print(f"offset {off:>4}  解析失敗 {type(exc).__name__}: {exc}", flush=True)
            break

        if not hits:
            print(f"offset {off:>4}  無資料，停止", flush=True)
            break

        new = 0
        for h in hits:
            src = h.get("_source", h)
            nano = src.get("nanoId") or h.get("_id")
            if not nano or nano in seen:
                continue
            seen[nano] = {
                "nanoId": nano,
                "name": src.get("name"),
                "government": src.get("government"),
                "provider": src.get("provider"),
                "url": src.get("url"),
                "lastModified": src.get("lastModified"),
                "resources": [
                    {
                        "name": r.get("name"),
                        "format": r.get("format"),
                        "url": r.get("url") or r.get("downloadUrl"),
                    }
                    for r in (src.get("resources") or [])
                ],
            }
            new += 1

        res_total = sum(len(v["resources"]) for v in seen.values())
        print(
            f"offset {off:>4}  本頁 {len(hits):>3} 筆，新增 {new:>3}，"
            f"累計 {len(seen)} 筆 / {res_total} 個資源",
            flush=True,
        )
        time.sleep(0.5)

    dest = OUT / "odportal-resources.json"
    dest.write_text(
        json.dumps(list(seen.values()), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    have_res = sum(1 for v in seen.values() if v["resources"])
    print(f"\n寫出 {dest}")
    print(f"  資料集 {len(seen)} 筆，其中 {have_res} 筆帶資源網址")
    print(f"  資源總數 {sum(len(v['resources']) for v in seen.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
