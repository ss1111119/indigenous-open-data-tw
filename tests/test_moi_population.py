"""戶政司原住民人口長表的不變量測試。

釘跨期與跨維度的結構約束，不釘單一數字快照——人口每月都變，約束不變。

七組逐列恆等式已在取檔階段驗過（村里明細捨棄前），故這裡不重複；本檔驗的是
長表層級、以及取檔階段無法檢查的跨期關係。

測試讀既成長表與 manifest，不重新取檔，故免連網、秒級完成。
"""

from __future__ import annotations

import collections
import inspect
import pathlib

import pandas as pd
import pytest

from scripts.moi import build_long_table as bl, fetch, registry as reg

LONG_TABLE = pathlib.Path("data/processed/moi-indigenous-population-long.csv.gz")
PINGPU = reg.STATUSES[reg.PINGPU_KEY]
MAINSTREAM = tuple(v for k, v in reg.STATUSES.items() if k != reg.PINGPU_KEY)


@pytest.fixture(scope="module")
def long_table() -> pd.DataFrame:
    if not LONG_TABLE.exists():
        pytest.skip(
            f"找不到 {LONG_TABLE}，請先執行 "
            f"python -m scripts.moi.fetch 與 python -m scripts.moi.build_long_table"
        )
    return pd.read_csv(LONG_TABLE)


@pytest.fixture(scope="module")
def manifest() -> dict[int, dict]:
    if not fetch.MANIFEST.exists():
        pytest.skip(f"找不到 {fetch.MANIFEST}")
    return fetch.load_manifest()


# --- 不變量一：維度交叉必須完整 ---
#
# ⚠️ 原本寫的是「依族別加總等於依身分別加總」。那條**恆真**：兩者都是把同一批列
# 相加，與資料對不對無關，注入故障也不會失敗。改為檢查交叉完整性——那才抓得到
# 漏列、重列、族別對映錯誤。

def test_every_group_carries_the_full_dimension_cross_product(
    long_table: pd.DataFrame,
) -> None:
    """每個（期別 × 鄉鎮市區 × 身分別）必須恰有「該身分別族別數 × 2 性別」列。

    漏一列、多一列、或某族因欄名改版而對映失敗，都會在這裡顯形。
    """
    expected = {
        reg.STATUSES[key]: len(reg.peoples_for(key)) * len(reg.SEXES)
        for key in reg.STATUSES
    }
    sizes = long_table.groupby(["期別", "縣市", "鄉鎮市區", "身分別"]).size()
    wrong = {
        key: int(size) for key, size in sizes.items()
        if size != expected[key[3]]
    }
    assert not wrong, (
        f"{len(wrong)} 個群的列數不符，預期 {expected}，"
        f"前幾個異常：{list(wrong.items())[:3]}"
    )


def test_row_count_follows_from_the_dimension_sizes(long_table: pd.DataFrame) -> None:
    """總列數必須等於各期的（鄉鎮市區數 × 該期各身分別族別數之和 × 2）。"""
    total = 0
    for period, group in long_table.groupby("期別"):
        districts = group.groupby(["縣市", "鄉鎮市區"]).ngroups
        peoples = sum(len(reg.peoples_for(k)) for k in reg.statuses_for(int(period)))
        total += districts * peoples * len(reg.SEXES)
    assert total == len(long_table)


def test_sex_split_covers_every_row(long_table: pd.DataFrame) -> None:
    assert set(long_table["性別"].unique()) == set(reg.SEXES.values())


# --- 不變量二：族別標籤不得因來源改版而分裂 ---

def test_people_labels_are_consistent_across_the_revision(
    long_table: pd.DataFrame,
) -> None:
    """`tsou` 與 `cou` 必須收斂到同一個「鄒族」，否則跨期序列會斷成兩段。

    比較的是平地與山地的族別集合——平埔的族別清單本來就不同，不該混進來比。
    """
    mainstream = long_table[long_table["身分別"].isin(MAINSTREAM)]
    per_period = mainstream.groupby("期別")["族別"].apply(frozenset)
    distinct = set(per_period)
    assert len(distinct) == 1, (
        f"平地與山地的族別集合跨期不一致，出現 {len(distinct)} 種組合："
        f"{[sorted(s)[:4] for s in distinct]}"
    )
    assert len(next(iter(distinct))) == len(reg.PEOPLES)


def test_no_people_label_contains_latin_letters(long_table: pd.DataFrame) -> None:
    latin = [v for v in long_table["族別"].unique()
             if any(c.isascii() and c.isalpha() for c in v)]
    assert not latin, f"族別殘留羅馬字：{latin}"


def test_pingpu_peoples_appear_only_under_pingpu(long_table: pd.DataFrame) -> None:
    """平埔獨有的族群不得出現在平地或山地之下。"""
    pingpu_only = set(reg.PINGPU_PEOPLES) - set(reg.PEOPLES)
    assert pingpu_only, "平埔獨有族群為空，此約束已無意義"
    mainstream = long_table[long_table["身分別"].isin(MAINSTREAM)]
    leaked = pingpu_only & set(mainstream["族別"].unique())
    assert not leaked, f"平埔獨有族群出現在非平埔身分別：{sorted(leaked)}"


# --- 不變量三：平埔列的期別下界 ---

def test_pingpu_rows_start_at_the_declared_period(long_table: pd.DataFrame) -> None:
    """11411 及之前來源沒有平埔欄位，那是「未提供」不是「為零」，不得產列。"""
    pingpu = long_table[long_table["身分別"] == PINGPU]
    if pingpu.empty:
        pytest.skip("長表尚未涵蓋 11412 之後的期別")
    # 下界永不得早於宣告值；長表確實涵蓋 11412 時才要求恰好等於它，
    # 否則部分涵蓋的長表會誤報
    assert int(pingpu["期別"].min()) >= reg.PINGPU_FROM
    if reg.PINGPU_FROM in set(long_table["期別"].unique()):
        assert int(pingpu["期別"].min()) == reg.PINGPU_FROM


def test_periods_before_the_boundary_have_no_pingpu(long_table: pd.DataFrame) -> None:
    early = long_table[long_table["期別"] < reg.PINGPU_FROM]
    if early.empty:
        pytest.skip("長表尚未涵蓋 11412 之前的期別")
    assert PINGPU not in set(early["身分別"].unique())


# --- 不變量四：長表與 manifest 必須對得上 ---

def test_period_set_matches_the_manifest(
    long_table: pd.DataFrame, manifest: dict[int, dict]
) -> None:
    retrieved = {p for p, r in manifest.items() if r.get("狀態") == "已取得"}
    assert set(long_table["期別"].unique()) == retrieved


def test_district_counts_match_the_manifest(
    long_table: pd.DataFrame, manifest: dict[int, dict]
) -> None:
    """每期的鄉鎮市區數必須與取檔當時記錄的一致——村里明細已捨棄，這是唯一的對帳依據。"""
    for period, group in long_table.groupby("期別"):
        record = manifest[int(period)]
        actual = group.groupby(["縣市", "鄉鎮市區"]).ngroups
        assert actual == record["鄉鎮市區數"], f"{period} 期：{actual} vs {record['鄉鎮市區數']}"


def test_manifest_records_the_identity_checks(manifest: dict[int, dict]) -> None:
    """每期都必須留下七組恆等式的檢查紀錄，否則聚合值就是無法追溯的斷言。"""
    retrieved = [r for r in manifest.values() if r.get("狀態") == "已取得"]
    assert retrieved
    for record in retrieved:
        checks = record["恆等式檢查"]
        assert set(checks) == {"A", "B", "C", "D-F", "G"}
        assert all(v > 0 for v in checks.values()), record["期別"]
        assert record["欄名版本"] in {s.label for s in reg.SCHEMES}


def test_all_three_naming_schemes_are_exercised(manifest: dict[int, dict]) -> None:
    """三種命名方案都必須在實際資料上用過，否則註冊表有條目是空談。

    實測分佈：`aborigine_` 93 期、`indigenous_` 9 期、中文欄名 1 期（11308）。
    """
    used = collections.Counter(
        r["欄名版本"] for r in manifest.values() if r.get("狀態") == "已取得"
    )
    assert set(used) == {s.label for s in reg.SCHEMES}, (
        f"有方案未被任何期別使用：{ {s.label for s in reg.SCHEMES} - set(used) }"
    )
    assert used[reg.SCHEME_CHINESE.label] == 1, "中文欄名應恰為 11308 一期"


# --- schema 契約 ---

def test_schema_columns_and_mandatory_fields(long_table: pd.DataFrame) -> None:
    assert tuple(long_table.columns) == fetch.LONG_COLUMNS
    for column in fetch.LONG_COLUMNS:
        assert long_table[column].notna().all(), f"`{column}` 不得為空"
    assert (long_table["人數"] >= 0).all()
    assert long_table["人數"].dtype.kind in "iu"


def test_statuses_are_declared_values(long_table: pd.DataFrame) -> None:
    assert set(long_table["身分別"].unique()) <= set(reg.STATUSES.values())


def test_administrative_names_use_the_orthodox_form(long_table: pd.DataFrame) -> None:
    names = set(long_table["縣市"]) | set(long_table["鄉鎮市區"])
    assert not [n for n in names if "台" in n], "行政區名一律用「臺」"
    assert set(long_table["縣市"].unique()) <= set(reg.COUNTIES)


def test_no_aggregate_rows_survive(long_table: pd.DataFrame) -> None:
    """彙總若混進長表，未過濾的 groupby 會得到數倍數字。"""
    labels = {"總計", "計", "小計", "合計"}
    for column in ("身分別", "族別", "性別", "縣市", "鄉鎮市區"):
        offending = set(long_table[column].unique()) & labels
        assert not offending, f"`{column}` 含彙總標籤：{offending}"


def test_village_granularity_is_absent(long_table: pd.DataFrame) -> None:
    """倫理界線：長表不得帶村里欄位或村里代碼。"""
    forbidden = {"村里", "village", "district_code", "村里代碼"}
    assert not forbidden & set(long_table.columns)


def test_build_performs_no_network_access() -> None:
    for module in (bl, reg):
        source = inspect.getsource(module)
        for forbidden in ("urllib", "requests", "httpx", "socket"):
            assert forbidden not in source, (
                f"{module.__name__} 出現網路相關匯入 `{forbidden}`"
            )


# --- 注入故障：確認不變量不是恆真的 ---

def _drop_one_row(frame: pd.DataFrame) -> pd.DataFrame:
    """刪掉一列，使該群的維度交叉不完整——模擬某族因欄名對映失敗而漏擷取。"""
    return frame.iloc[1:].copy()


def _seed_early_pingpu(frame: pd.DataFrame) -> pd.DataFrame:
    """把一列平埔的期別改到宣告的下界之前。"""
    seeded = frame.copy()
    idx = seeded.index[seeded["身分別"] == PINGPU]
    if len(idx) == 0:
        pytest.skip("長表尚無平埔列可注入故障")
    seeded.loc[idx[0], "期別"] = reg.PINGPU_FROM - 1
    return seeded


def test_seeded_missing_row_is_detected(long_table: pd.DataFrame) -> None:
    seeded = _drop_one_row(long_table)
    with pytest.raises(AssertionError):
        test_every_group_carries_the_full_dimension_cross_product(seeded)


def test_seeded_early_pingpu_is_detected(long_table: pd.DataFrame) -> None:
    seeded = _seed_early_pingpu(long_table)
    with pytest.raises(AssertionError):
        test_periods_before_the_boundary_have_no_pingpu(seeded)


def test_missing_row_fault_does_not_trip_the_pingpu_boundary(
    long_table: pd.DataFrame,
) -> None:
    """漏列不得被平埔邊界那條搶先報出，否則定位不到病灶。

    ⚠️ **反方向不成立，且不假裝成立**：維度交叉完整性對「列的組成」極為敏感，
    任何搬動、新增或刪除列的故障都會打破它——把一列平埔的期別改到 11411，
    會同時使 11411 與 11507 兩個群的列數不符。這是刻意的靈敏度，不是缺陷：
    它讓漏擷取與錯對映一定會被抓到。獨立性只在「漏列 → 平埔邊界仍正確」
    這個方向存在。
    """
    missing_row = _drop_one_row(long_table)
    test_periods_before_the_boundary_have_no_pingpu(missing_row)
    test_people_labels_are_consistent_across_the_revision(missing_row)
