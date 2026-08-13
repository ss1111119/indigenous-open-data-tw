"""去重清單的不變量測試。

釘的是跨檔案約束與結構不變量。「筆數關係」那幾項只讀兩份清單，不需要 `data/raw/`
即可執行；「不掉資源」需要資源 json，缺檔時單獨 skip 而不拖垮整批。
"""

from __future__ import annotations

import inspect
import pathlib

import pandas as pd
import pytest

from scripts.catalog import dedupe as dd

DEDUPED = pathlib.Path("catalog/odportal-deduped.csv")

EXPECTED_ROWS = 683
EXPECTED_MERGED = 80
EXPECTED_ORIGINAL = 763
EXPECTED_GRADE_GAPS = 23


@pytest.fixture(scope="module")
def deduped() -> pd.DataFrame:
    if not DEDUPED.exists():
        pytest.skip(f"找不到 {DEDUPED}，請先執行 python -m scripts.catalog.dedupe")
    return pd.read_csv(DEDUPED)


@pytest.fixture(scope="module")
def graded() -> pd.DataFrame:
    if not dd.GRADED.exists():
        pytest.skip(f"找不到 {dd.GRADED}")
    return pd.read_csv(dd.GRADED)


@pytest.fixture(scope="module")
def resources() -> dict[str, set[str]]:
    if not dd.RESOURCES.exists():
        pytest.skip(f"找不到 {dd.RESOURCES}（data/raw/ 不入版控）")
    return dd.load_resources(dd.RESOURCES)


def _union_of(frame: pd.DataFrame, resources: dict[str, set[str]]) -> set[str]:
    """一份清單涵蓋的全部資源網址。去重清單以 `合併來源` 展開回成員 id。"""
    if dd.MERGED_FROM in frame.columns:
        nanos = {n for row in frame[dd.MERGED_FROM] for n in str(row).split(dd.JOIN)}
    else:
        nanos = {dd.nano_of(v) for v in frame[dd.ID_COL]}
    return set().union(*(resources.get(n, set()) for n in nanos))


# --- 不變量一：去重不得掉資源 ---

def test_deduplication_preserves_every_resource_url(
    deduped: pd.DataFrame, graded: pd.DataFrame, resources: dict[str, set[str]]
) -> None:
    """實測 46 筆兩邊互有獨有資源，選單一贏家會掉資料。聯集必須完全相等。"""
    before, after = _union_of(graded, resources), _union_of(deduped, resources)
    assert not before - after, f"去重後遺失 {len(before - after)} 個資源網址"
    assert not after - before, f"去重後多出 {len(after - before)} 個資源網址"


def test_resource_count_matches_the_union(
    deduped: pd.DataFrame, resources: dict[str, set[str]]
) -> None:
    """`資源數` 必須等於該列成員資源的聯集大小，而非任一成員的原始數量。"""
    for _, row in deduped[deduped[dd.MERGED_COUNT] > 1].iterrows():
        members = str(row[dd.MERGED_FROM]).split(dd.JOIN)
        union = set().union(*(resources.get(n, set()) for n in members))
        assert int(row["資源數"]) == len(union), row["名稱"]


def test_choosing_one_side_would_have_lost_resources(
    deduped: pd.DataFrame, resources: dict[str, set[str]]
) -> None:
    """反向釘住聯集的必要性：若留單一贏家即無損，這條約束就寫鬆了。"""
    lossy = 0
    for _, row in deduped[deduped[dd.MERGED_COUNT] > 1].iterrows():
        members = [resources.get(n, set()) for n in str(row[dd.MERGED_FROM]).split(dd.JOIN)]
        union = set().union(*members)
        if all(m != union for m in members):
            lossy += 1
    assert lossy > 0, (
        "沒有任何一群是兩邊互有獨有資源——聯集規則已無必要，請重新查證"
    )


# --- 不變量二：筆數關係（不需要 data/raw/）---

def test_row_counts_reconcile_to_the_input(deduped: pd.DataFrame) -> None:
    assert len(deduped) == EXPECTED_ROWS
    assert int((deduped[dd.MERGED_COUNT] == 2).sum()) == EXPECTED_MERGED
    assert int(deduped[dd.MERGED_COUNT].sum()) == EXPECTED_ORIGINAL


def test_no_group_exceeds_two_members(deduped: pd.DataFrame) -> None:
    """合併規則的實測依據只涵蓋雙筆群；出現更大的群代表依據已失效。"""
    assert int(deduped[dd.MERGED_COUNT].max()) == 2


def test_merged_provenance_is_recorded(deduped: pd.DataFrame) -> None:
    for _, row in deduped.iterrows():
        members = str(row[dd.MERGED_FROM]).split(dd.JOIN)
        assert len(members) == int(row[dd.MERGED_COUNT])
        assert members == sorted(members), row["名稱"]
    singles = deduped[deduped[dd.MERGED_COUNT] == 1]
    assert all(
        dd.nano_of(url) == merged
        for url, merged in zip(singles[dd.ID_COL], singles[dd.MERGED_FROM])
    )


# --- 不變量三：分級覆蓋範圍與合併規則 ---

def test_grade_coverage_flag_count(deduped: pd.DataFrame) -> None:
    assert int(deduped[dd.GRADE_GAP].sum()) == EXPECTED_GRADE_GAPS


def test_merged_rows_carry_a_providing_agency(deduped: pd.DataFrame) -> None:
    """實測 80/80 是一側有值一側空，故合併後必定取得到機關名。"""
    merged = deduped[deduped[dd.MERGED_COUNT] > 1]
    assert merged["提供機關"].notna().all()


def test_merged_rows_keep_both_source_platforms(deduped: pd.DataFrame) -> None:
    """「上架在兩個平台」正是被合併的事實本身，不該丟掉任一個。"""
    merged = deduped[deduped[dd.MERGED_COUNT] > 1]
    assert merged["來源平台"].str.contains(dd.JOIN).all()


def test_licence_prefers_the_specific_value(deduped: pd.DataFrame) -> None:
    """6 筆衝突皆為 OGDL-1.0 vs UNKNOWN，合併後不該留下 UNKNOWN。"""
    merged = deduped[deduped[dd.MERGED_COUNT] > 1]
    assert "UNKNOWN" not in set(merged["授權"].dropna())


def test_grade_values_are_known(deduped: pd.DataFrame) -> None:
    assert set(deduped["分級"].dropna()) <= set(dd.GRADE_RANK)


def test_original_catalog_is_untouched(graded: pd.DataFrame) -> None:
    """去重另出新檔，原清單不動——「763」在多份文件裡必須維持有效。"""
    assert len(graded) == EXPECTED_ORIGINAL
    assert dd.SHARED_COL in graded.columns


def test_dedupe_performs_no_network_access() -> None:
    source = inspect.getsource(dd)
    for forbidden in ("urllib", "requests", "httpx", "socket"):
        assert forbidden not in source, f"dedupe 出現網路相關匯入 `{forbidden}`"


# --- 注入故障：確認上面的不變量不是恆真的 ---

def _lose_resources_keeping_counts(frame: pd.DataFrame) -> pd.DataFrame:
    """模擬「選單一贏家」造成的掉資源，且刻意不動筆數。

    做法是把某個合併列的兩個成員換成同一個成員兩次：資源聯集因此少掉另一側
    獨有的網址，但 `合併筆數` 仍為 2、總和仍為 763。這樣資源不變量與筆數不變量
    才真的能分開驗——若改成把成員砍掉一個，兩個不變量會同時失敗，就證明不了獨立性。
    """
    seeded = frame.copy()
    for target in seeded.index[seeded[dd.MERGED_COUNT] > 1]:
        members = str(seeded.loc[target, dd.MERGED_FROM]).split(dd.JOIN)
        seeded.loc[target, dd.MERGED_FROM] = dd.JOIN.join([members[0], members[0]])
        return seeded
    raise AssertionError("找不到任何合併列可注入故障")


def _drop_a_row(frame: pd.DataFrame) -> pd.DataFrame:
    """刪掉一列，模擬分群漏掉一個群。"""
    return frame.iloc[1:].copy()


def test_seeded_resource_loss_is_detected(
    deduped: pd.DataFrame, graded: pd.DataFrame, resources: dict[str, set[str]]
) -> None:
    seeded = _lose_resources_keeping_counts(deduped)
    with pytest.raises(AssertionError):
        test_deduplication_preserves_every_resource_url(seeded, graded, resources)


def test_seeded_row_loss_is_detected(deduped: pd.DataFrame) -> None:
    seeded = _drop_a_row(deduped)
    with pytest.raises(AssertionError):
        test_row_counts_reconcile_to_the_input(seeded)


def test_resource_fault_does_not_trip_the_row_count_invariant(
    deduped: pd.DataFrame,
) -> None:
    """資源損失不得被筆數不變量搶先報出，否則兩項擠在一起、定位不到病灶。

    ⚠️ 反方向不成立且不假裝成立：刪掉一列必然同時掉走該列的資源，所以掉列的
    故障會同時打破兩項不變量。獨立性只在「資源損失 → 筆數仍正確」這個方向存在。
    """
    seeded = _lose_resources_keeping_counts(deduped)
    test_row_counts_reconcile_to_the_input(seeded)
    test_no_group_exceeds_two_members(seeded)
    test_merged_provenance_is_recorded(seeded)
