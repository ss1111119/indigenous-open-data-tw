"""把 C 系列 6 張表 × 103–114 學年攤平成單一長表。

只讀本機 `data/raw/moe/`，完全不連網。輸出為原始檔的確定性函式：同樣的輸入
產生位元組相同的 CSV。

長表只存**最細的明細**。彙總值（總計欄、計列、總計組、臺灣地區列）在建置過程中
用於驗證，通過後即捨棄——把彙總一併存進去，任何未過濾的 `groupby().sum()` 都會
得到二至三倍的數字。任一處彙總驗證不符即中止，不靜默略過。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

from . import extract
from . import known_issues
from . import registry as reg
from .extract import Discrepancy, ExtractionError, SheetContext

RAW = pathlib.Path("data/raw/moe")
OUT = pathlib.Path("data/processed/moe-c-series-long.csv")

FIRST_YEAR = 103
LAST_YEAR = 114

COLUMNS = (
    "學年", "表號", "統計別", "等級別", "年級", "族籍別", "性別",
    "設立別", "學校所在地", "校碼", "學校名稱", "人數",
)

# 「無此數」符號。實測 12 份工作簿的 C 系列只出現這一種非中英數字元，共 269 格，
# 且把它當 0 後總計欄與明細加總零誤差相符（詳見 design.md）。
ABSENT = "-"


class BuildError(RuntimeError):
    """建置階段的阻斷性錯誤。"""


def parse_count(raw: object, where: str) -> int:
    """把指標儲存格讀為非負整數。`-` 讀為 0，其他讀不出來的內容一律中止。"""
    text = "" if raw is None else str(raw).strip()
    if text == ABSENT:
        return 0
    try:
        value = int(float(text))
    except (TypeError, ValueError):
        raise BuildError(
            f"{where} 的指標儲存格無法讀為非負整數，原始內容：{raw!r}"
        ) from None
    if value < 0:
        raise BuildError(f"{where} 的人數為負：{raw!r}")
    return value


def _cell_int(ctx: SheetContext, row: int, col: int, where: str) -> int | None:
    """讀彙總驗證用的儲存格。空白回傳 None（該處無彙總可驗）。"""
    text = ctx.text(row, col)
    if not text:
        return None
    return parse_count(text, where)


def _measure_columns(
    ctx: SheetContext, statistic: str, aggregate: bool
) -> list[int]:
    return [
        col
        for col, (stat, measure) in sorted(ctx.measures.items())
        if stat == statistic and measure.aggregate == aggregate
    ]


def _data_rows(ctx: SheetContext) -> list[int]:
    """資料區內帶任何指標值的列（含彙總列）。"""
    cols = list(ctx.measures)
    return [
        row
        for row in range(ctx.start, len(ctx.frame))
        if any(ctx.text(row, col) for col in cols)
    ]


def _record(
    found: list[Discrepancy], year: int, ctx: SheetContext, check: str,
    row: int, column: int, expected: int, actual: int,
) -> None:
    found.append(
        Discrepancy(year, ctx.table.code, check, row, column, expected, actual)
    )


def _check_total_columns(
    year: int, ctx: SheetContext, found: list[Discrepancy]
) -> int:
    """總計欄 ＝ 同一統計別的明細欄之和。"""
    checks = 0
    for statistic in ctx.table.measures:
        totals = _measure_columns(ctx, statistic, aggregate=True)
        details = _measure_columns(ctx, statistic, aggregate=False)
        if not totals or not details:
            continue
        for row in _data_rows(ctx):
            where = f"{year} 學年 {ctx.table.code} r{row}（{statistic}總計欄）"
            expected = _cell_int(ctx, row, totals[0], where)
            if expected is None:
                continue
            actual = sum(
                parse_count(ctx.text(row, col), where) for col in details
                if ctx.text(row, col)
            )
            if actual != expected:
                _record(found, year, ctx, f"{statistic}總計欄", row, totals[0],
                        expected, actual)
            checks += 1
    return checks


def _check_per_row_aggregates(
    year: int, ctx: SheetContext, found: list[Discrepancy]
) -> int:
    """群組內的彙總列（如「計」）＝ 同組明細列之和。"""
    checks = 0
    for dim in ctx.table.row_dims:
        if dim.style != "per_row" or not dim.aggregates:
            continue
        col = dim.cols[0]
        for rows in ctx.groups():
            agg_rows = [r for r in rows if ctx.text(r, col) in dim.aggregates]
            det_rows = [
                r for r in rows
                if ctx.text(r, col) and ctx.text(r, col) not in dim.aggregates
            ]
            if not agg_rows or not det_rows:
                continue
            for measure_col in ctx.measures:
                where = (
                    f"{year} 學年 {ctx.table.code} r{agg_rows[0]} c{measure_col}"
                    f"（{dim.name}彙總列）"
                )
                expected = _cell_int(ctx, agg_rows[0], measure_col, where)
                if expected is None:
                    continue
                actual = sum(
                    parse_count(ctx.text(r, measure_col), where)
                    for r in det_rows if ctx.text(r, measure_col)
                )
                if actual != expected:
                    _record(found, year, ctx, f"{dim.name}彙總列",
                            agg_rows[0], measure_col, expected, actual)
                checks += 1
    return checks


def _check_group_aggregates(
    year: int, ctx: SheetContext, found: list[Discrepancy]
) -> int:
    """彙總群組（如「總計」組）＝ 各明細群組之和，逐列對位比較。"""
    checks = 0
    for dim in ctx.table.row_dims:
        if dim.style != "group_label" or not dim.aggregates:
            continue
        agg: list[range] = []
        detail: list[range] = []
        for rows in ctx.groups():
            (agg if ctx.group_label(rows, dim) in dim.aggregates else detail).append(rows)
        if not agg or not detail:
            continue
        for offset in range(len(agg[0])):
            for measure_col in ctx.measures:
                where = (
                    f"{year} 學年 {ctx.table.code} r{agg[0].start + offset} "
                    f"c{measure_col}（{dim.name}彙總組）"
                )
                expected = _cell_int(ctx, agg[0].start + offset, measure_col, where)
                if expected is None:
                    continue
                actual = 0
                for rows in detail:
                    if offset >= len(rows):
                        continue
                    text = ctx.text(rows.start + offset, measure_col)
                    if text:
                        actual += parse_count(text, where)
                if actual != expected:
                    _record(found, year, ctx, f"{dim.name}彙總組",
                            agg[0].start + offset, measure_col, expected, actual)
                checks += 1
    return checks


def _check_indent_hierarchy(
    year: int, ctx: SheetContext, found: list[Discrepancy]
) -> int:
    """縮排階層：每個父列 ＝ 其子列之和（`C1-2` 的總計／地區／縣市）。"""
    checks = 0
    for dim in ctx.table.row_dims:
        if dim.style != "indent":
            continue
        col = dim.cols[0]
        labelled = [
            (row, ctx.indent_level(row, col))
            for row in _data_rows(ctx)
            if ctx.text(row, col)
        ]
        for i, (row, level) in enumerate(labelled):
            children = []
            for child_row, child_level in labelled[i + 1:]:
                if child_level <= level:
                    break
                if child_level == level + 1:
                    children.append(child_row)
            if not children:
                continue
            for measure_col in ctx.measures:
                where = (
                    f"{year} 學年 {ctx.table.code} r{row} c{measure_col}"
                    f"（{dim.name}縮排階層）"
                )
                expected = _cell_int(ctx, row, measure_col, where)
                if expected is None:
                    continue
                actual = sum(
                    parse_count(ctx.text(r, measure_col), where)
                    for r in children if ctx.text(r, measure_col)
                )
                if actual != expected:
                    _record(found, year, ctx, f"{dim.name}縮排階層",
                            row, measure_col, expected, actual)
                checks += 1
    return checks


def _check_total_row(
    year: int, ctx: SheetContext, found: list[Discrepancy]
) -> int:
    """表級總計列 ＝ 全部明細列之和（`C2-1`／`C2-2` 校別清單之上那一列）。"""
    col = ctx.table.total_row_col
    if col is None:
        return 0
    total_rows = [r for r in _data_rows(ctx) if ctx.text(r, col)]
    detail_rows = [r for r in _data_rows(ctx) if ctx.row_dims.get(r) is not None]
    if not total_rows or not detail_rows:
        return 0
    checks = 0
    for measure_col in ctx.measures:
        where = f"{year} 學年 {ctx.table.code} r{total_rows[0]} c{measure_col}（表級總計列）"
        expected = _cell_int(ctx, total_rows[0], measure_col, where)
        if expected is None:
            continue
        actual = sum(
            parse_count(ctx.text(r, measure_col), where)
            for r in detail_rows if ctx.text(r, measure_col)
        )
        if actual != expected:
            _record(found, year, ctx, "表級總計列", total_rows[0], measure_col,
                    expected, actual)
        checks += 1
    return checks


def verify_aggregates(
    year: int, code: str, raw_dir: pathlib.Path
) -> tuple[int, list[Discrepancy]]:
    """對一張表執行全部彙總驗證，回傳（檢查數, 不符清單）。

    收集全部不符而非第一處就中止——要判斷一處不符是上游的已知錯誤還是新問題，
    必須看見同一張表裡不符的完整分佈。是否中止由呼叫端依已知清單決定。
    """
    ctx = extract.sheet_context(year, code, raw_dir)
    found: list[Discrepancy] = []
    checks = (
        _check_total_columns(year, ctx, found)
        + _check_per_row_aggregates(year, ctx, found)
        + _check_group_aggregates(year, ctx, found)
        + _check_indent_hierarchy(year, ctx, found)
        + _check_total_row(year, ctx, found)
    )
    return checks, found


def build(
    years: range = range(FIRST_YEAR, LAST_YEAR + 1), raw_dir: pathlib.Path = RAW
) -> tuple[pd.DataFrame, list[Discrepancy]]:
    """建置長表。先驗彙總，通過後才攤平明細。

    回傳（長表, 命中的已知上游不符）。未列於 known_issues 的不符一律中止。
    """
    rows: list[dict[str, object]] = []
    seen: list[Discrepancy] = []
    for year in years:
        for code in reg.CODES:
            checks, found = verify_aggregates(year, code, raw_dir)
            unknown = [d for d in found if not known_issues.is_known(d)]
            if unknown:
                raise BuildError(
                    f"{year} 學年 {code} 出現 {len(unknown)} 處未查證的彙總不符：\n  "
                    + "\n  ".join(d.describe() for d in unknown)
                    + "\n查明原因後再決定處置；若確認是上游錯誤，"
                      "附查證結論登記到 scripts/moe/known_issues.py"
                )
            seen.extend(found)
            for cell in extract.extract(year, code, raw_dir):
                where = f"{year} 學年 {code} r{cell.row} c{cell.column}"
                record: dict[str, object] = {
                    "學年": year,
                    "表號": code,
                    "統計別": cell.statistic,
                    "人數": parse_count(cell.raw, where),
                }
                record.update(cell.dims)
                rows.append(record)
            note = f"，其中 {len(found)} 處為已知上游不符" if found else ""
            print(f"{year} 學年 {code}  彙總檢查 {checks} 項{note}", flush=True)

    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    # 排序使輸出與列舉順序脫鉤，重跑才會位元組相同
    frame = frame.sort_values(list(COLUMNS), kind="stable", na_position="last")
    return frame.reset_index(drop=True), seen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", type=int, default=FIRST_YEAR)
    ap.add_argument("--to", dest="end", type=int, default=LAST_YEAR)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args(argv)

    try:
        frame, known = build(range(args.start, args.end + 1))
    except (BuildError, ExtractionError) as exc:
        print(f"\n建置中止：{exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig 與姊妹專案 moe-indigenous-stats 一致，Excel 直接開不亂碼
    frame.to_csv(args.out, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"\n寫出 {args.out}：{len(frame):,} 列 × {len(frame.columns)} 欄")
    if known:
        years = sorted({d.year for d in known})
        print(
            f"放行 {len(known)} 處已查證的上游彙總不符（{years} 學年）。"
            f"長表只存明細，內容不受影響；詳見 scripts/moe/known_issues.py"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
