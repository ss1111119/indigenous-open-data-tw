"""把各期別的鄉鎮市區聚合結果併成單一長表。

    python -m scripts.moi.build_long_table

只讀 `data/raw/moi/`，**不連網**。輸出為輸入的確定性函式：同樣的輸入產生位元組
相同的 CSV。

取檔階段已完成七組恆等式的逐列驗證並捨棄村里明細（見 scripts/moi/fetch.py），
故本階段驗的是**跨期與跨維度**的約束：期別集合要與 manifest 相符、族別標籤不得
因來源改版而分裂、平埔列不得出現在註冊表宣告的期別下界之前。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

from . import registry as reg
from .fetch import LONG_COLUMNS, MANIFEST, RAW, load_manifest, period_path

OUT = pathlib.Path("data/processed/moi-indigenous-population-long.csv.gz")

# gzip 存放而非純 CSV：未壓縮是 151.6 MB，超過 GitHub 單檔 100 MB 的硬上限
# （50 MB 即警告）。壓縮後 9.2 MB，且 pd.read_csv 能直接讀 .csv.gz，
# 「可直接讀進 pandas」的定位不受影響。
#
# ⚠️ mtime 必須固定為 0：gzip 標頭預設嵌入建置時間，不固定的話每次輸出的位元組
# 都不同，會靜默破壞「重跑產生位元組相同的輸出」這個性質。
GZIP = {"method": "gzip", "mtime": 0}


class BuildError(RuntimeError):
    """建置階段的阻斷性錯誤。不設靜默降級路徑。"""


def build(raw_dir: pathlib.Path = RAW) -> pd.DataFrame:
    """讀各期聚合結果併成長表。期別集合與 manifest 不一致即中止。"""
    if not MANIFEST.exists():
        raise BuildError(
            f"找不到 {MANIFEST}。請先執行 python -m scripts.moi.fetch"
        )

    manifest = load_manifest()
    expected = {p for p, r in manifest.items() if r.get("狀態") == "已取得"}
    on_disk = {
        int(path.stem.rsplit("-", 1)[-1])
        for path in raw_dir.glob(f"{reg.DATASET}-*.csv")
    }
    if expected != on_disk:
        raise BuildError(
            f"manifest 與磁碟上的期別不一致。"
            f"manifest 有而磁碟無：{sorted(expected - on_disk)}；"
            f"磁碟有而 manifest 無：{sorted(on_disk - expected)}"
        )
    if not expected:
        raise BuildError("manifest 中沒有任何已取得的期別，無資料可建置")

    frames = [
        pd.read_csv(period_path(period), dtype={"人數": "int64"})
        for period in sorted(expected)
    ]
    frame = pd.concat(frames, ignore_index=True)

    if list(frame.columns) != list(LONG_COLUMNS):
        raise BuildError(
            f"期別檔案的欄位與長表 schema 不符：{list(frame.columns)}"
        )

    # --- 跨期約束：任一不符即中止 ---
    early_pingpu = frame[
        (frame["身分別"] == reg.STATUSES[reg.PINGPU_KEY])
        & (frame["期別"] < reg.PINGPU_FROM)
    ]
    if not early_pingpu.empty:
        raise BuildError(
            f"平埔列出現在 {reg.PINGPU_FROM} 之前的期別："
            f"{sorted(early_pingpu['期別'].unique())}。"
            f"這與註冊表宣告矛盾，請查明後更新 scripts/moi/registry.py"
        )

    latin = [v for v in frame["族別"].unique() if any(c.isascii() and c.isalpha() for c in v)]
    if latin:
        raise BuildError(f"族別標籤殘留羅馬字，跨期正規化未生效：{latin}")

    unexpected = set(frame["身分別"].unique()) - set(reg.STATUSES.values())
    if unexpected:
        raise BuildError(f"出現註冊表未宣告的身分別：{sorted(unexpected)}")

    if (frame["人數"] < 0).any():
        raise BuildError("出現負的人數")
    if frame[list(LONG_COLUMNS)].isna().any().any():
        empty = [c for c in LONG_COLUMNS if frame[c].isna().any()]
        raise BuildError(f"以下欄位有空值，長表要求每欄皆非空：{empty}")

    # 排序使輸出與讀檔順序脫鉤，重跑才會位元組相同
    frame = frame.sort_values(list(LONG_COLUMNS), kind="stable")
    return frame.reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=pathlib.Path, default=RAW)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args(argv)

    try:
        frame = build(args.raw)
    except (BuildError, reg.RegistryError) as exc:
        print(f"建置中止：{exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        args.out,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n",
        compression=GZIP,
    )

    periods = sorted(frame["期別"].unique())
    size = args.out.stat().st_size / 1048576
    print(f"寫出 {args.out}：{len(frame):,} 列 × {len(frame.columns)} 欄（{size:.1f} MB）")
    print(f"  期別 {len(periods)} 個：{periods[0]}–{periods[-1]}")
    print(f"  鄉鎮市區 {frame.groupby(['縣市', '鄉鎮市區']).ngroups} 個")
    pingpu = frame[frame["身分別"] == reg.STATUSES[reg.PINGPU_KEY]]
    if not pingpu.empty:
        print(
            f"  平埔列自期別 {int(pingpu['期別'].min())} 起，"
            f"目前總人數 {int(pingpu['人數'].sum()):,}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
