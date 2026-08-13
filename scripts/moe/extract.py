"""依註冊表從原始工作簿擷取 C 系列表格，輸出明細列。

本模組不含任何以表號分支的邏輯——所有表格差異都在 registry.py。

處理的五個實測陷阱（見 docs/來源盤點.md）：

1. 表名帶尾隨空白（113 的 `A1-1 `）→ 定位一律 strip 後比對表號，不比對標題字串
2. 幻影欄：109 起最後一欄是「○○學年」浮水印，且可能夾帶雜散值（111 `C2-2`
   該欄含一個孤立的 0）→ 有效欄須「表頭有標題文字」且「資料區有值」雙條件
3. 資料起始列位移（108 自 r5、109 起自 r6）→ 偵測不寫死
4. 維度標籤跨列合併且垂直置中 → 先判群組邊界再套組內唯一標籤，不用 ffill／bfill
5. 各表版面偏移不同 → 指標欄以表頭文字定位
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

import pandas as pd

from . import registry as reg


class ExtractionError(RuntimeError):
    """擷取階段的阻斷性錯誤。本模組不設靜默降級路徑。"""


@dataclass(frozen=True)
class Discrepancy:
    """一處彙總不符。以值與位置一併作為身分，故上游修好或改版都會顯形。

    定義在此而非建置模組，是為了讓 known_issues 不必匯入入口模組——`python -m`
    會把入口模組同時以 `__main__` 與其套件路徑載入兩次，跨模組的資料類別比對
    會因此永遠不相等。
    """

    year: int
    code: str
    check: str
    row: int
    column: int
    expected: int
    actual: int

    @property
    def difference(self) -> int:
        return self.expected - self.actual

    def describe(self) -> str:
        return (
            f"{self.year} 學年 {self.code} r{self.row} c{self.column}"
            f"（{self.check}）彙總 {self.expected} ≠ 明細加總 {self.actual}，"
            f"差 {self.difference}"
        )


@dataclass(frozen=True)
class Cell:
    """一個明細儲存格：維度組合 ＋ 原始值。人數的解析留給建置階段。"""

    code: str
    statistic: str
    dims: dict[str, str]
    raw: object
    row: int          # 原始列號，報錯時指位置用
    column: int


def _text(value: object) -> str:
    """把儲存格轉為正規化文字：去除換行與前後空白（含全形空格）。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", "", str(value).replace("　", " ")).strip()


def _indent_level(value: object) -> int:
    """數出列標籤前的全形空格數，用於 `C1-2` 的階層判定。"""
    s = "" if value is None else str(value)
    return len(s) - len(s.lstrip("　 "))


def workbook_path(year: int, raw_dir: pathlib.Path) -> pathlib.Path:
    """回傳該學年的本機工作簿；兩種副檔名都找不到即報錯。"""
    for ext in (".xls", ".xlsx"):
        path = raw_dir / f"{year}indigenous{ext}"
        if path.exists():
            return path
    raise ExtractionError(
        f"{year} 學年找不到原始檔。已查看：{raw_dir}/{year}indigenous.xls(x)。"
        f"請先執行 python -m scripts.moe.fetch --from {year} --to {year}"
    )


def load_sheet(path: pathlib.Path, year: int, code: str) -> pd.DataFrame:
    """以正規化表號定位工作表。不使用標題字串比對——標題破折號跨年不一致。"""
    # with 是必要的：不關閉會在 Windows 上留著檔案句柄，暫存目錄因此刪不掉
    with pd.ExcelFile(path) as book:
        by_normalized = {name.strip(): name for name in book.sheet_names}
        actual = by_normalized.get(code)
        if actual is None:
            raise ExtractionError(
                f"{year} 學年的 {path.name} 找不到表號 {code}。"
                f"該檔實際的工作表：{book.sheet_names}"
            )
        # 校碼必須讀為字串：011301 會被轉成 11301.0、173E16 會被當科學記號
        return book.parse(actual, header=None, dtype=str)


def _statistic_by_column(header: pd.DataFrame) -> dict[int, str]:
    """把 r3 的統計別標題橫向填滿到它所跨的欄，回傳 欄索引 → 統計別。

    r3 是合併儲存格，只在群組第一欄有值，故橫向填滿是正確的（與列方向的
    ffill 陷阱無關）。r3 與 r4 有時把「上學年度」「畢業生人數」拆兩列，
    故先接起來再查表。
    """
    top, sub = header.iloc[0], header.iloc[1]
    result: dict[int, str] = {}
    current = ""
    for col in range(header.shape[1]):
        label = _text(top.iloc[col])
        if label:
            current = label
        if not current:
            continue
        for candidate in (current, current + _text(sub.iloc[col])):
            if candidate in reg.STATISTIC_BY_HEADER:
                result[col] = reg.STATISTIC_BY_HEADER[candidate]
                break
    return result


def _data_start_row(df: pd.DataFrame) -> int:
    """表頭之後第一個有內容的列。108 自 r5、109 起插空白列改自 r6。"""
    for row in range(max(reg.HEADER_ROWS) + 1, len(df)):
        if df.iloc[row].map(_text).any():
            return row
    raise ExtractionError("表頭之後找不到任何有內容的列")


def _valid_data_columns(df: pd.DataFrame, start: int) -> set[int]:
    """雙條件判定有效資料欄：表頭列有標題文字，且資料區有值。

    單看「資料區有值」會把 109 起的浮水印欄誤判為資料欄——111 學年 `C2-2`
    的浮水印欄就夾帶一個孤立的 0。
    """
    header = df.iloc[list(reg.HEADER_ROWS)]
    body = df.iloc[start:]
    valid = set()
    for col in range(df.shape[1]):
        has_header = any(_text(v) for v in header.iloc[:, col])
        has_data = any(_text(v) for v in body.iloc[:, col])
        if has_header and has_data:
            valid.add(col)
    return valid


def _resolve_measures(
    table: reg.Table, df: pd.DataFrame, start: int, year: int
) -> dict[int, tuple[str, reg.Measure]]:
    """以（統計別, 表頭文字）把註冊表的指標欄對到實際欄索引。

    註冊表未描述的有效資料欄視為阻斷性錯誤——那可能是真正的改版。
    """
    header = df.iloc[list(reg.HEADER_ROWS)]
    statistic_of = _statistic_by_column(header)
    valid = _valid_data_columns(df, start)
    sub = header.iloc[1]

    resolved: dict[int, tuple[str, reg.Measure]] = {}
    for col in sorted(valid):
        statistic = statistic_of.get(col)
        if statistic is None:
            continue
        label = _text(sub.iloc[col])
        for measure in table.measures.get(statistic, ()):
            if _text(measure.header) == label:
                resolved[col] = (statistic, measure)
                break

    unregistered = [
        (col, _text(sub.iloc[col]))
        for col in sorted(valid)
        if col not in resolved and statistic_of.get(col) is not None
    ]
    if unregistered:
        raise ExtractionError(
            f"{year} 學年 {table.code} 出現註冊表未描述的有效資料欄："
            f"{unregistered}。這可能是上游改版，請查明後更新 registry.py"
        )

    expected = sum(len(m) for m in table.measures.values())
    if len(resolved) != expected:
        found = sorted((c, s, m.header) for c, (s, m) in resolved.items())
        raise ExtractionError(
            f"{year} 學年 {table.code} 指標欄數不符：註冊表宣告 {expected} 欄，"
            f"實際對上 {len(resolved)} 欄。對上的欄：{found}"
        )
    return resolved


def _group_bounds(df: pd.DataFrame, table: reg.Table, start: int) -> list[range]:
    """依群組標記欄切出群組範圍。標籤置中於組內，故必須先有邊界才能套標籤。"""
    marker_col = table.group_marker_col
    starts: list[int] = []
    end = start
    for row in range(start, len(df)):
        label = _text(df.iat[row, marker_col])
        if not label:
            continue
        if label == table.group_marker_start:
            starts.append(row)
        end = row + 1
    if not starts:
        raise ExtractionError(
            f"{table.code} 找不到任何以「{table.group_marker_start}」起始的群組"
        )
    bounds = []
    for i, first in enumerate(starts):
        last = starts[i + 1] if i + 1 < len(starts) else end
        bounds.append(range(first, last))
    return bounds


def _group_label(df: pd.DataFrame, rows: range, dim: reg.RowDim) -> str:
    """取群組內唯一的非空標籤，套用至整組。不用 ffill／bfill——標籤在組中間。"""
    found = {
        _text(df.iat[row, col])
        for row in rows
        for col in dim.cols
        if _text(df.iat[row, col])
    }
    if len(found) != 1:
        raise ExtractionError(
            f"群組 r{rows.start}–r{rows.stop - 1} 的「{dim.name}」標籤不唯一：{found}"
        )
    return found.pop()


def _row_dimensions(
    df: pd.DataFrame, table: reg.Table, start: int
) -> dict[int, dict[str, str] | None]:
    """算出每個資料列的列維度值。回傳 None 表示該列是彙總列，應捨棄。"""
    per_row: dict[int, dict[str, str] | None] = {}

    group_of: dict[int, range] = {}
    if any(d.style == "group_label" for d in table.row_dims):
        for rows in _group_bounds(df, table, start):
            for row in rows:
                group_of[row] = rows

    for row in range(start, len(df)):
        dims: dict[str, str] = {}
        aggregate = False
        blank = True

        for dim in table.row_dims:
            if dim.style == "group_label":
                rows = group_of.get(row)
                if rows is None:
                    continue
                value = _group_label(df, rows, dim)
            elif dim.style == "per_row":
                value = next(
                    (_text(df.iat[row, c]) for c in dim.cols if _text(df.iat[row, c])),
                    "",
                )
            elif dim.style == "indent":
                col = dim.cols[0]
                value = _text(df.iat[row, col])
                if value and _indent_level(df.iat[row, col]) != dim.detail_indent:
                    aggregate = True
            else:
                raise ExtractionError(f"註冊表出現未知的列維度樣式：{dim.style}")

            if value:
                blank = False
            if dim.bilingual:
                # 中英並列（`臺北市 Taipei City`）只留中文。僅對宣告過的維度施行——
                # 無條件切會把進修部校碼 `173E16` 毀成 `173`
                value = re.sub(r"[A-Za-z].*$", "", value).strip()
            if value in dim.aggregates:
                aggregate = True
            dims[dim.name] = value

        if blank or aggregate or not any(dims.values()):
            per_row[row] = None
        else:
            per_row[row] = dims

    return per_row


@dataclass(frozen=True)
class SheetContext:
    """一張表解析後的結構，供擷取與彙總驗證共用。"""

    table: reg.Table
    frame: pd.DataFrame
    start: int
    measures: dict[int, tuple[str, reg.Measure]]
    row_dims: dict[int, dict[str, str] | None]

    def groups(self) -> list[range]:
        if self.table.group_marker_col is None:
            return [range(self.start, len(self.frame))]
        return _group_bounds(self.frame, self.table, self.start)

    def group_label(self, rows: range, dim: reg.RowDim) -> str:
        return _group_label(self.frame, rows, dim)

    def indent_level(self, row: int, col: int) -> int:
        return _indent_level(self.frame.iat[row, col])

    def text(self, row: int, col: int) -> str:
        return _text(self.frame.iat[row, col])


def sheet_context(year: int, code: str, raw_dir: pathlib.Path) -> SheetContext:
    """解析一張表的結構：表頭、資料起始列、指標欄、列維度。"""
    table = reg.TABLES[code]
    df = load_sheet(workbook_path(year, raw_dir), year, code)
    start = _data_start_row(df)
    return SheetContext(
        table=table,
        frame=df,
        start=start,
        measures=_resolve_measures(table, df, start, year),
        row_dims=_row_dimensions(df, table, start),
    )


def extract(year: int, code: str, raw_dir: pathlib.Path) -> list[Cell]:
    """擷取一個學年的一張表，回傳明細儲存格（不含彙總列與彙總欄）。"""
    ctx = sheet_context(year, code, raw_dir)
    table, df, measures, row_dims = ctx.table, ctx.frame, ctx.measures, ctx.row_dims

    cells: list[Cell] = []
    for row, dims in row_dims.items():
        if dims is None:
            continue
        for col, (statistic, measure) in measures.items():
            if measure.aggregate:
                continue
            combined = {**table.fixed_dims, **dims, **measure.dims}
            # 等級別一律先正規化（「國中進修部」→「國中補校」）。必須在年級分支之外，
            # 否則無年級的畢業生列會留下未正規化的標籤，同一件事變成兩個值。
            level = combined.get("等級別") or None
            if level:
                level = reg.normalize_level(level)
                combined["等級別"] = level
            if measure.grade_index is not None:
                if not reg.is_legal_grade(level, measure.grade_index):
                    continue
                combined["年級"] = reg.absolute_grade(level, measure.grade_index)
            cells.append(
                Cell(
                    code=code,
                    statistic=statistic,
                    dims=combined,
                    raw=df.iat[row, col],
                    row=row,
                    column=col,
                )
            )
    return cells


