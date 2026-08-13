"""C 系列長表的不變量測試。

釘的是跨檔案約束與結構不變量，不是單一數字快照——數字每年都會變，約束不會。

測試讀 `data/processed/` 的既成長表，不跑 pipeline，故免連網、秒級完成。長表不存在
時整批 skip 並提示建置指令。
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from scripts.moe import known_issues, registry as reg

LONG_TABLE = pathlib.Path("data/processed/moe-c-series-long.csv")
YEARS = tuple(range(103, 115))
ENROLLED = reg.ENROLLED

# `C1-1`／`C2-3` 的等級別是本科與補校分列；`C2-1`／`C2-2` 的校別清單含進修部，
# 故兩邊對帳時必須把本科與補校加起來（實測差額恰為補校人數）
MAINSTREAM_WITH_CONTINUING = {
    "國中（含進修部）": ("國中", "國中補校"),
    "國小（含進修部）": ("國小", "國小補校"),
}


@pytest.fixture(scope="module")
def long_table() -> pd.DataFrame:
    if not LONG_TABLE.exists():
        pytest.skip(
            f"找不到 {LONG_TABLE}，請先執行 python -m scripts.moe.build_long_table"
        )
    return pd.read_csv(LONG_TABLE, dtype={"校碼": "string"})


def _enrolled(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    return frame[(frame["表號"] == code) & (frame["統計別"] == ENROLLED)]


# --- 不變量一：同一批學生的三種切法，在學總人數必須相等 ---

def test_c11_c12_c23_agree_on_enrolled_totals(long_table: pd.DataFrame) -> None:
    """`C1-1`（族籍別×性別）、`C1-2`（縣市）、`C2-3`（設立別）是同一批學生。"""
    totals = {
        code: _enrolled(long_table, code).groupby("學年")["人數"].sum()
        for code in ("C1-1", "C1-2", "C2-3")
    }
    mismatched = {
        year: {code: int(t[year]) for code, t in totals.items()}
        for year in YEARS
        if len({int(t[year]) for t in totals.values()}) != 1
    }
    assert not mismatched, f"三張表的在學總人數不一致：{mismatched}"


def test_c11_and_c23_agree_per_level(long_table: pd.DataFrame) -> None:
    """再往下一層：同學年同等級別也必須相等，不只總數相等。"""
    per_level = {
        code: _enrolled(long_table, code).groupby(["學年", "等級別"])["人數"].sum()
        for code in ("C1-1", "C2-3")
    }
    assert per_level["C1-1"].to_dict() == per_level["C2-3"].to_dict()


# --- 不變量二：校別加總 ＝ 對應的本科 ＋ 補校 ---

def test_school_level_totals_reconcile_to_c11(long_table: pd.DataFrame) -> None:
    """`C2-1`／`C2-2` 的校別清單含進修部，故對帳要加上補校那一欄。"""
    c11 = _enrolled(long_table, "C1-1").groupby(["學年", "等級別"])["人數"].sum()
    for code, level in (("C2-1", "國中（含進修部）"), ("C2-2", "國小（含進修部）")):
        schools = _enrolled(long_table, code).groupby("學年")["人數"].sum()
        for year in YEARS:
            expected = sum(
                int(c11.get((year, part), 0))
                for part in MAINSTREAM_WITH_CONTINUING[level]
            )
            assert int(schools[year]) == expected, (
                f"{year} 學年 {code} 校別加總 {int(schools[year])} "
                f"≠ C1-1 的{MAINSTREAM_WITH_CONTINUING[level]}之和 {expected}"
            )


def test_reconciliation_needs_the_continuing_education_column(
    long_table: pd.DataFrame,
) -> None:
    """反向釘住上一項的理由：只用本科欄對帳必須失敗，否則該約束寫鬆了。"""
    c11 = _enrolled(long_table, "C1-1").groupby(["學年", "等級別"])["人數"].sum()
    schools = _enrolled(long_table, "C2-1").groupby("學年")["人數"].sum()
    mainstream_only = [
        year for year in YEARS if int(schools[year]) == int(c11.get((year, "國中"), 0))
    ]
    assert not mainstream_only, (
        f"{mainstream_only} 學年在只算本科時也相等——補校人數為 0 或約束已失效，"
        "請重新查證 C2-1 是否仍含進修部學校"
    )


# --- 不變量三：每個表號在 12 學年都必須有資料 ---

def test_every_table_code_present_in_every_year(long_table: pd.DataFrame) -> None:
    present = set(map(tuple, long_table[["學年", "表號"]].drop_duplicates().values))
    missing = [(y, c) for y in YEARS for c in reg.CODES if (y, c) not in present]
    assert not missing, f"缺資料的（學年, 表號）組合：{missing}"


def test_year_and_code_sets_are_exactly_the_declared_scope(
    long_table: pd.DataFrame,
) -> None:
    assert sorted(long_table["學年"].unique()) == list(YEARS)
    assert sorted(long_table["表號"].unique()) == sorted(reg.CODES)


# --- 不變量四：長表不得含彙總列 ---

def test_no_aggregate_rows_survive(long_table: pd.DataFrame) -> None:
    """彙總值若混進長表，未過濾的 groupby 會得到二至三倍的數字。"""
    aggregate_labels = {"總計", "總　計", "計", "臺灣地區", "金馬地區"}
    for column in ("等級別", "年級", "族籍別", "性別", "設立別", "學校所在地"):
        offending = set(long_table[column].dropna().unique()) & aggregate_labels
        assert not offending, f"`{column}` 含彙總標籤：{offending}"


def test_summing_one_table_code_does_not_double_count(
    long_table: pd.DataFrame,
) -> None:
    """`C1-1` 在學總數應等於其族籍別明細之和——若含「計」列就會是兩倍。"""
    c11 = _enrolled(long_table, "C1-1")
    for year in YEARS:
        year_rows = c11[c11["學年"] == year]
        by_ethnicity = year_rows.groupby("族籍別")["人數"].sum().sum()
        assert int(year_rows["人數"].sum()) == int(by_ethnicity)


# --- schema 契約 ---

def test_schema_columns_and_mandatory_fields(long_table: pd.DataFrame) -> None:
    from scripts.moe.build_long_table import COLUMNS

    assert tuple(long_table.columns) == COLUMNS
    for column in ("學年", "表號", "統計別", "人數"):
        assert long_table[column].notna().all(), f"`{column}` 不得為空"
    assert (long_table["人數"] >= 0).all()
    assert long_table["人數"].dtype.kind in "iu", "人數 必須是整數型別"


def test_school_codes_survive_as_strings(long_table: pd.DataFrame) -> None:
    """`011301` 不得變成 `11301.0`、`173E16` 不得變成 `1.73e+18`。"""
    schools = long_table[long_table["表號"].isin(("C2-1", "C2-2"))]
    assert schools["校碼"].notna().all(), "C2-1／C2-2 的校碼不得為空"
    codes = set(schools[schools["學年"] == 114]["校碼"])
    assert "011301" in codes
    assert "173E16" in codes
    assert not any("." in code or "e+" in code.lower() for code in codes)

    others = long_table[~long_table["表號"].isin(("C2-1", "C2-2"))]
    assert others["校碼"].isna().all(), "其餘表號的校碼必須為空"


def test_duplicate_school_names_are_distinguishable(
    long_table: pd.DataFrame,
) -> None:
    rows = long_table[(long_table["表號"] == "C2-2") & (long_table["學年"] == 114)]
    schools = rows[["校碼", "學校名稱"]].drop_duplicates()
    repeated = schools["學校名稱"].value_counts()
    assert repeated.max() > 1, "校名本應有重複；若無，此約束已失效"
    assert schools["校碼"].is_unique


def test_grades_are_absolute_school_system_grades(long_table: pd.DataFrame) -> None:
    """國中系列不得出現一～六年級——那是「該等級別內的第 n 年級」的舊語意。"""
    junior = long_table[long_table["等級別"].isin(reg.JUNIOR_HIGH_LEVELS)]
    grades = set(junior["年級"].dropna().unique())
    assert grades <= {"七年級", "八年級", "九年級"}, f"國中系列出現異常年級：{grades}"

    c23 = long_table[
        (long_table["表號"] == "C2-3")
        & (long_table["學年"] == 114)
        & (long_table["等級別"] == "國中")
        & (long_table["年級"] == "七年級")
        & (long_table["統計別"] == ENROLLED)
    ]
    assert int(c23["人數"].sum()) == 8469


def test_impossible_level_and_grade_combinations_are_absent(
    long_table: pd.DataFrame,
) -> None:
    """國中沒有四年級。原始檔把這種格印成 `-`，不得被當成 0 產列。"""
    graded = long_table[long_table["年級"].notna()]
    for level, limit in reg.LEGAL_GRADE_COUNT.items():
        rows = graded[graded["等級別"] == level]
        if rows.empty:
            continue
        allowed = {reg.absolute_grade(level, i) for i in range(limit)}
        assert set(rows["年級"].unique()) <= allowed, (
            f"等級別「{level}」出現不合法年級：{set(rows['年級'].unique()) - allowed}"
        )


def test_graduate_rows_of_school_tables_carry_no_grade(
    long_table: pd.DataFrame,
) -> None:
    """`C2-1`／`C2-2` 的畢業生欄是單一總數，沒有年級細分。"""
    graduates = long_table[
        long_table["表號"].isin(("C2-1", "C2-2"))
        & (long_table["統計別"] == reg.GRADUATE)
    ]
    assert graduates["年級"].isna().all()
    assert not graduates.empty


def test_administrative_names_use_the_orthodox_form(
    long_table: pd.DataFrame,
) -> None:
    places = set(long_table["學校所在地"].dropna().unique())
    assert places, "`學校所在地` 不該全為空"
    assert not [p for p in places if "台" in p], "行政區名一律用「臺」"
    assert not [p for p in places if any(c.isascii() and c.isalpha() for c in p)], (
        "行政區名不得殘留英文尾綴"
    )
    assert "臺北市" in places


# --- 注入故障：確認上面四項不變量不是恆真的 ---

def _bump(frame: pd.DataFrame, code: str, amount: int = 1) -> pd.DataFrame:
    """把某表號第一列的人數加一，模擬攤平錯誤。"""
    seeded = frame.copy()
    target = seeded.index[
        (seeded["表號"] == code) & (seeded["統計別"] == ENROLLED)
    ][0]
    seeded.loc[target, "人數"] += amount
    return seeded


def _relabel_as_aggregate(frame: pd.DataFrame) -> pd.DataFrame:
    """把一個性別值改成「計」，模擬彙總列漏過濾。"""
    seeded = frame.copy()
    target = seeded.index[seeded["性別"].notna()][0]
    seeded.loc[target, "性別"] = "計"
    return seeded


def _drop_one_table_year(frame: pd.DataFrame) -> pd.DataFrame:
    """整批刪掉 103 學年的 C2-4，模擬某表某年漏擷取。"""
    return frame[~((frame["學年"] == 103) & (frame["表號"] == "C2-4"))].copy()


SEEDED_FAULTS = (
    ("三表在學總數相等", _bump, ("C1-2",), test_c11_c12_c23_agree_on_enrolled_totals),
    ("校別加總對帳", _bump, ("C2-1",), test_school_level_totals_reconcile_to_c11),
    ("表號年度齊備", lambda f: _drop_one_table_year(f), (),
     test_every_table_code_present_in_every_year),
    ("不含彙總列", lambda f: _relabel_as_aggregate(f), (), test_no_aggregate_rows_survive),
)


@pytest.mark.parametrize(
    "name,mutate,args,invariant",
    SEEDED_FAULTS,
    ids=[case[0] for case in SEEDED_FAULTS],
)
def test_seeded_fault_is_detected(
    name: str, mutate, args: tuple, invariant, long_table: pd.DataFrame
) -> None:
    """每項不變量都必須抓到對應的注入故障，否則該測試恆真、毫無保護力。"""
    seeded = mutate(long_table, *args)
    with pytest.raises(AssertionError):
        invariant(seeded)


def test_seeded_faults_do_not_trip_unrelated_invariants(
    long_table: pd.DataFrame,
) -> None:
    """每個故障只該打破自己那一項——否則不變量之間互相遮蔽，定位不到問題。"""
    invariants = [case[3] for case in SEEDED_FAULTS]
    for name, mutate, args, own in SEEDED_FAULTS:
        seeded = mutate(long_table, *args)
        for other in invariants:
            if other is own:
                continue
            other(seeded)  # 不該拋出


# --- 已知上游不符的反向約束 ---

def test_known_upstream_issues_are_all_still_hit() -> None:
    """清單上每一筆都必須恰好命中一次。

    上游修好了、或改版使列號位移，該筆就不再命中——測試因此失敗，逼人回頭重新
    查證，而不是讓過期的放行條目無聲累積。
    """
    from scripts.moe.build_long_table import verify_aggregates

    raw = pathlib.Path("data/raw/moe")
    if not raw.exists() or not any(raw.iterdir()):
        pytest.skip("找不到原始檔，請先執行 python -m scripts.moe.fetch")

    hit: list = []
    for year in sorted(known_issues.AFFECTED_YEARS):
        for code in reg.CODES:
            _, found = verify_aggregates(year, code, raw)
            hit.extend(found)

    listed = set(known_issues.KNOWN)
    assert len(hit) == len(set(hit)), "同一處不符被回報多次"
    stale = listed - set(hit)
    assert not stale, (
        "清單上這幾筆已不再出現（上游可能已修正或改版），請重新查證後移除：\n  "
        + "\n  ".join(d.describe() for d in sorted(stale, key=lambda d: (d.year, d.code)))
    )
    unlisted = set(hit) - listed
    assert not unlisted, (
        "出現未查證的彙總不符：\n  " + "\n  ".join(d.describe() for d in unlisted)
    )


def test_every_known_issue_carries_a_verified_cause() -> None:
    for discrepancy, cause_key in known_issues.KNOWN.items():
        assert cause_key in known_issues.CAUSES, (
            f"{discrepancy.describe()} 的根因鍵 {cause_key!r} 未定義"
        )
        assert len(known_issues.CAUSES[cause_key]) > 40, "根因說明過短，不足以構成查證結論"


def test_build_path_performs_no_network_access() -> None:
    """建置在檔案齊備時不得連網——取檔與建置是可分開執行的兩步。"""
    import inspect

    from scripts.moe import build_long_table, extract

    for module in (build_long_table, extract, reg, known_issues):
        source = inspect.getsource(module)
        for forbidden in ("urllib", "requests", "httpx", "socket"):
            assert forbidden not in source, (
                f"{module.__name__} 出現網路相關匯入 `{forbidden}`"
            )
