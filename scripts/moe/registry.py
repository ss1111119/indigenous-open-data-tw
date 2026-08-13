"""C 系列 6 張表的結構註冊表。

擷取程式讀這份資料運作，本身不含任何以表號分支的邏輯。新增表格＝增加一個
`Table` 條目，不改程式。

指標欄一律以**表頭文字**描述而非欄索引——實測 `A1-3` 在 109 起整體左移一欄，
若寫死索引會靜默取到錯欄（見 docs/來源盤點.md）。列維度則必須用欄索引，因為
左側標籤欄沒有表頭文字可比對。

三個只能寫在註冊表、無法從工作表讀出的事實：

1. **合法的 `等級別 × 年級` 組合**。國中系列只有一～三年級；原始檔把不存在的
   組合印成 `-`，與「人數為 0」無法區分，故合法性必須宣告而非推斷。
2. **年級的絕對化換算**。`C2-3`／`C2-4` 的國中列用「一年級」指七年級，`C2-1`
   同一批人卻標「七年級」。故指標欄一律登記**相對年級序號**，絕對名稱由序號
   加上等級別推導，兩種來源因此收斂到同一組標籤。
3. **`C2-1`／`C2-2` 的等級別含進修部**。這兩張表的校別清單包含進修部學校，
   其總數等於 `C1-1` 的本科＋補校（實測 114 學年國中 24,536 ＝ 24,513 ＋ 23）。
   故等級別標為「國中（含進修部）」而非「國中」——用同一個「國中」會與 `C1-1`
   的國中（不含補校）構成假相等，正是專案最該避免的口徑混用。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 兩列表頭固定在 r3（統計別）與 r4（指標名）；資料起始列會位移，須偵測不可寫死
HEADER_ROWS = (3, 4)

ENROLLED = "在學學生"
GRADUATE = "上學年度畢業生"

# r3／r4 有時把「上學年度」與「畢業生人數」拆成兩列，故比對前先把兩列接起來
STATISTIC_BY_HEADER = {
    "在學學生人數": ENROLLED,
    "上學年度畢業生人數": GRADUATE,
}

# 絕對學制年級。國中系列的相對第 n 年級 ＝ 絕對第 n+6 年級。
GRADE_NAMES = ("一年級", "二年級", "三年級", "四年級", "五年級", "六年級",
               "七年級", "八年級", "九年級")
JUNIOR_HIGH_OFFSET = 6

# 各等級別合法的相對年級數。國中沒有四～六年級。
LEGAL_GRADE_COUNT = {
    "國中": 3,
    "國中補校": 3,
    "國中（含進修部）": 3,
    "國小": 6,
    "國小補校": 6,
    "國小（含進修部）": 6,
}
JUNIOR_HIGH_LEVELS = frozenset(
    lv for lv, n in LEGAL_GRADE_COUNT.items() if n == 3
)

# `C2-3`／`C2-4` 的等級別取自列標籤，原始檔用「國中進修部」；正規化為補校用語，
# 與 `C1-1` 的指標欄標題一致，使兩張表的等級別對得起來
LEVEL_ALIASES = {
    "國中進修部": "國中補校",
    "國小進修部": "國小補校",
}


@dataclass(frozen=True)
class Measure:
    """一個指標欄：以表頭文字定位，並宣告它貢獻哪些維度值。

    `grade_index` 為該欄在其等級別內的**相對**年級序號（0 起算）。絕對年級名稱
    由 `absolute_grade` 依等級別推導，故「一年級」與「七年級」兩種來源標籤會
    收斂到同一個值。無年級細分的欄（如畢業生總數）留 None。
    """

    header: str
    dims: dict[str, str] = field(default_factory=dict)
    grade_index: int | None = None
    aggregate: bool = False          # 總計欄：驗證用，不入長表


@dataclass(frozen=True)
class RowDim:
    """一個列維度：只能以欄索引定位，因為左側標籤欄無表頭文字。

    style:
      group_label — 標籤跨列合併且垂直置中，只出現在群組的某一列（不必是第一列）
      per_row     — 每列都有自己的標籤
      indent      — 以全形空格縮排表示階層，僅最深層為明細
    """

    cols: tuple[int, ...]
    name: str
    style: str
    aggregates: frozenset[str] = frozenset()
    detail_indent: int | None = None
    # 標籤為中英並列（`臺北市 Taipei City`），需切除英文尾綴。只有宣告了才切——
    # 無條件切會毀掉本身帶英文字母的值，例如進修部校碼 `173E16` 會變成 `173`
    bilingual: bool = False


@dataclass(frozen=True)
class Table:
    code: str
    row_dims: tuple[RowDim, ...]
    # 指標欄按統計別分組——同一組 r4 標題在在學欄與畢業欄各出現一次
    measures: dict[str, tuple[Measure, ...]]
    fixed_dims: dict[str, str] = field(default_factory=dict)
    # 群組邊界靠這一欄的值循環判定（style=group_label 用）
    group_marker_col: int | None = None
    group_marker_start: str | None = None
    # 表級總計列的標籤欄。`C2-1`／`C2-2` 在校別清單之上有一列全表總計，
    # 它不屬於任何列維度，但必須等於所有明細列之和，故單獨宣告以供驗證。
    total_row_col: int | None = None


def _level_measures() -> tuple[Measure, ...]:
    """`C1-1`／`C1-2` 的指標欄：總計 ＋ 四個等級別。"""
    return (
        Measure("總計", aggregate=True),
        Measure("國中", {"等級別": "國中"}),
        Measure("國小", {"等級別": "國小"}),
        Measure("國中補校", {"等級別": "國中補校"}),
        Measure("國小補校", {"等級別": "國小補校"}),
    )


def _relative_grade_measures(headers: tuple[str, ...]) -> tuple[Measure, ...]:
    """在學欄按年級細分。`headers` 是原始檔的欄標題，序號即其位置。"""
    return (Measure("總計", aggregate=True),) + tuple(
        Measure(h, grade_index=i) for i, h in enumerate(headers)
    )


_GRADUATE_TOTAL = (Measure("畢業生人數"),)
_ELEMENTARY_HEADERS = GRADE_NAMES[:6]
_JUNIOR_HEADERS_ABSOLUTE = GRADE_NAMES[6:]

TABLES: dict[str, Table] = {
    # 族籍別 × 性別 × 等級別
    "C1-1": Table(
        code="C1-1",
        row_dims=(
            RowDim(cols=(0, 1), name="族籍別", style="group_label",
                   aggregates=frozenset({"總計"})),
            RowDim(cols=(2,), name="性別", style="per_row",
                   aggregates=frozenset({"計"})),
        ),
        measures={ENROLLED: _level_measures(), GRADUATE: _level_measures()},
        group_marker_col=2,
        group_marker_start="計",
    ),
    # 學校所在地（縣市）× 等級別
    "C1-2": Table(
        code="C1-2",
        row_dims=(
            RowDim(cols=(0,), name="學校所在地", style="indent", detail_indent=2,
                   bilingual=True),
        ),
        measures={ENROLLED: _level_measures(), GRADUATE: _level_measures()},
    ),
    # 校別 × 年級（國中，含進修部學校）
    "C2-1": Table(
        code="C2-1",
        row_dims=(
            RowDim(cols=(1,), name="校碼", style="per_row"),
            RowDim(cols=(2,), name="學校名稱", style="per_row"),
        ),
        measures={
            ENROLLED: _relative_grade_measures(_JUNIOR_HEADERS_ABSOLUTE),
            GRADUATE: _GRADUATE_TOTAL,
        },
        fixed_dims={"等級別": "國中（含進修部）"},
        total_row_col=0,
    ),
    # 校別 × 年級（國小，含進修部學校）
    "C2-2": Table(
        code="C2-2",
        row_dims=(
            RowDim(cols=(1,), name="校碼", style="per_row"),
            RowDim(cols=(2,), name="學校名稱", style="per_row"),
        ),
        measures={
            ENROLLED: _relative_grade_measures(_ELEMENTARY_HEADERS),
            GRADUATE: _GRADUATE_TOTAL,
        },
        fixed_dims={"等級別": "國小（含進修部）"},
        total_row_col=0,
    ),
    # 等級別 × 設立別 × 年級
    "C2-3": Table(
        code="C2-3",
        row_dims=(
            RowDim(cols=(0, 1), name="等級別", style="group_label",
                   aggregates=frozenset({"總計"})),
            RowDim(cols=(2,), name="設立別", style="per_row",
                   aggregates=frozenset({"計"})),
        ),
        measures={
            ENROLLED: _relative_grade_measures(_ELEMENTARY_HEADERS),
            GRADUATE: _GRADUATE_TOTAL,
        },
        group_marker_col=2,
        group_marker_start="計",
    ),
    # 等級別 × 性別 × 年級
    "C2-4": Table(
        code="C2-4",
        row_dims=(
            RowDim(cols=(0, 1), name="等級別", style="group_label",
                   aggregates=frozenset({"總計"})),
            RowDim(cols=(2,), name="性別", style="per_row",
                   aggregates=frozenset({"計"})),
        ),
        measures={
            ENROLLED: _relative_grade_measures(_ELEMENTARY_HEADERS),
            GRADUATE: _GRADUATE_TOTAL,
        },
        group_marker_col=2,
        group_marker_start="計",
    ),
}

CODES = tuple(TABLES)


def normalize_level(label: str) -> str:
    """把列標籤的等級別正規化（「國中進修部」→「國中補校」）。"""
    return LEVEL_ALIASES.get(label, label)


def absolute_grade(level: str | None, grade_index: int) -> str:
    """相對年級序號 ＋ 等級別 → 絕對學制年級名稱。"""
    offset = JUNIOR_HIGH_OFFSET if level in JUNIOR_HIGH_LEVELS else 0
    return GRADE_NAMES[grade_index + offset]


def is_legal_grade(level: str | None, grade_index: int) -> bool:
    """該等級別是否真有這個相對年級。國中 × 四年級不存在，不得產列。

    等級別為空者一律不合法——那只會發生在跨等級別的彙總列，本來就不入長表。
    """
    if level is None:
        return False
    limit = LEGAL_GRADE_COUNT.get(level)
    if limit is None:
        raise KeyError(f"註冊表未宣告等級別「{level}」的合法年級數")
    return grade_index < limit
