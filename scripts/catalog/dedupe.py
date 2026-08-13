"""階段四：把重複上架的資料集併為單列。

那 160 筆「與其他資料集共用資源」不是各轄區的拼圖碎片，而是**同一份資料上架在
中央的政府開放資料平臺與地方入口網**（2026-08-13 實測，見 docs/來源盤點.md 第五節）。
名稱與資源 rid 相同，故該合併。

只讀既有的分級清單與資源 json，**不連網**、不重新探測。

合併規則全部來自 80 個成對群的實測衝突分佈，不是偏好；規則的例外情形一律為阻斷性
錯誤，使規則失效時報錯而非靜默套用。詳見 openspec/changes/dedupe-odportal-catalog/design.md。
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

import pandas as pd

from .grade import ORDER

GRADED = pathlib.Path("catalog/odportal-763-graded.csv")
RESOURCES = pathlib.Path("data/raw/catalog/odportal-resources.json")
OUT = pathlib.Path("catalog/odportal-deduped.csv")

SHARED_COL = "與其他資料集共用資源"
ID_COL = "ODPortal"

# 新增的三個欄位
MERGED_COUNT = "合併筆數"
MERGED_FROM = "合併來源"
GRADE_GAP = "分級未涵蓋新增資源"

# 分級由好到壞的順序沿用 grade.py，不另行定義——「取較可用者」與分級階段
# 「資料集取其資源中最好的一級」是同一個判準
GRADE_RANK = {g: i for i, g in enumerate(ORDER)}

JOIN = ";"
# 授權欄的無資訊值：合併時捨棄，取具體值
UNINFORMATIVE_LICENCE = {"UNKNOWN", ""}


class DedupError(RuntimeError):
    """去重階段的阻斷性錯誤。本模組不設靜默降級路徑。"""


def nano_of(odportal_url: object) -> str:
    """從 ODPortal 網址取出 nanoId。清單存的是完整網址，json 的鍵是 nanoId。"""
    return str(odportal_url).rstrip("/").rsplit("/", 1)[-1]


def load_resources(path: pathlib.Path) -> dict[str, set[str]]:
    """讀資源 json，回傳 nanoId → 資源網址集合。"""
    if not path.exists():
        raise DedupError(
            f"找不到 {path}。data/raw/ 不入版控，請先執行 "
            f"python -m scripts.catalog.fetch_odportal_resources"
        )
    records = json.loads(path.read_text(encoding="utf-8"))
    return {
        rec["nanoId"]: {r["url"] for r in (rec.get("resources") or []) if r.get("url")}
        for rec in records
    }


def group_by_shared_resource(frame: pd.DataFrame) -> list[list[str]]:
    """以共用資源指標做連通分量分群。

    不用兩兩配對：`與其他資料集共用資源` 只存單一夥伴 id，若上游日後出現三筆
    互指，兩兩配對會產出互相矛盾的合併（A 併 B、B 併 C，A 與 C 卻分屬兩列）
    且不會報錯。連通分量在同樣情況下自然併為一群。

    群大小超過 2 視為阻斷性錯誤——合併規則的實測依據只涵蓋雙筆群。
    """
    members = list(frame["nano"])
    parent = {n: n for n in members}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, row in frame[frame[SHARED_COL].notna()].iterrows():
        partner = str(row[SHARED_COL]).strip()
        if partner not in parent:
            raise DedupError(
                f"共用資源指標指向清單外的 id：{partner}，"
                f"來源列「{row['名稱']}」（{row[ID_COL]}）"
            )
        a, b = find(row["nano"]), find(partner)
        if a != b:
            parent[a] = b

    grouped: dict[str, list[str]] = collections.defaultdict(list)
    for n in members:
        grouped[find(n)].append(n)

    groups = [sorted(g) for g in grouped.values()]
    oversized = [g for g in groups if len(g) > 2]
    if oversized:
        raise DedupError(
            f"出現 {len(oversized)} 個超過兩筆的群，合併規則的實測依據只涵蓋雙筆群，"
            f"請重新查證後更新 design.md。群成員：{oversized[:3]}"
        )
    # 依群內第一個 id 排序，使輸出與 DataFrame 列舉順序脫鉤
    return sorted(groups)


def _single(values: list[str], field: str, group: list[str]) -> str:
    """取唯一的非空值。兩側皆有值且不同時報錯——實測顯示不該發生。"""
    present = sorted({v for v in values if v})
    if len(present) > 1:
        raise DedupError(
            f"群 {group} 的「{field}」兩側皆有值且不同：{present}。"
            f"實測 80 個成對群此欄皆為一側有值一側空，請重新查證合併規則"
        )
    return present[0] if present else ""


def _union_field(values: list[str], field: str) -> str:
    """把以 ; 分隔的多值欄取聯集後排序。`field` 僅用於可讀性，不影響行為。"""
    parts = {p.strip() for v in values for p in str(v).split(JOIN) if p.strip()}
    return JOIN.join(sorted(parts))


def _best_grade(values: list[str], group: list[str]) -> str:
    """取較可用的分級。順序沿用 grade.py 的 ORDER。"""
    known = [v for v in values if v in GRADE_RANK]
    if not known:
        raise DedupError(f"群 {group} 沒有任何可辨識的分級：{values}")
    return min(known, key=lambda g: GRADE_RANK[g])


def merge_group(
    rows: pd.DataFrame, resources: dict[str, set[str]], group: list[str]
) -> dict[str, object]:
    """把一個群合併為單列。

    資源取聯集：實測 46 筆兩邊各有對方沒有的資源，選任一邊都會掉資料；且平台
    優先序無效，中央較全與地方較全各佔約一半，落差最大 10 倍。
    """
    def col(name: str) -> list[str]:
        return ["" if pd.isna(v) else str(v).strip() for v in rows[name]]

    per_member = [resources.get(n, set()) for n in group]
    union = set().union(*per_member) if per_member else set()
    largest_member = max((len(s) for s in per_member), default=0)
    if len(union) < largest_member:
        raise DedupError(
            f"群 {group} 的聯集 {len(union)} 個資源少於單一成員的 {largest_member} 個，"
            f"聯集邏輯有誤"
        )

    # 名稱、ODPortal、原始網址都取「提供機關有值」那側——地方入口網是資料的
    # 實際提供者，其命名較貼近來源（6 筆名稱不同者皆為桃園的命名慣例差異）
    agency = _single(col("提供機關"), "提供機關", group)
    if agency:
        anchor = rows[rows["提供機關"].fillna("").astype(str).str.strip() == agency]
    else:
        anchor = rows
    anchor_row = anchor.iloc[0]

    merged: dict[str, object] = {}
    for name in rows.columns:
        if name in ("nano", SHARED_COL):
            continue
        values = col(name)
        if name == "提供機關":
            merged[name] = agency
        elif name in ("名稱", ID_COL, "原始網址"):
            merged[name] = "" if pd.isna(anchor_row[name]) else str(anchor_row[name])
        elif name in ("來源平台", "格式"):
            merged[name] = _union_field(values, name)
        elif name == "授權":
            specific = sorted(
                {v for v in values if v not in UNINFORMATIVE_LICENCE}
            )
            merged[name] = specific[0] if specific else _union_field(values, name)
        elif name == "最後更新":
            merged[name] = max(values) if any(values) else ""
        elif name == "分級":
            merged[name] = _best_grade(values, group)
        elif name in ("資源數", "資源總數"):
            merged[name] = len(union)
        else:
            # 其餘分級欄位（最大記錄數、檔案類欄位、實際型態、已探測資源）沿用
            # anchor 的值。它們是舊樣本的結果，未涵蓋新增資源——由 GRADE_GAP 標示
            merged[name] = "" if pd.isna(anchor_row[name]) else anchor_row[name]

    merged[MERGED_COUNT] = len(group)
    merged[MERGED_FROM] = JOIN.join(sorted(group))
    merged[GRADE_GAP] = len(union) > largest_member
    return merged


def dedupe(
    graded: pathlib.Path = GRADED, resources_path: pathlib.Path = RESOURCES
) -> pd.DataFrame:
    """讀分級清單與資源 json，回傳去重後的清單。"""
    frame = pd.read_csv(graded)
    frame["nano"] = frame[ID_COL].map(nano_of)
    resources = load_resources(resources_path)

    groups = group_by_shared_resource(frame)
    by_nano = frame.set_index("nano", drop=False)

    merged_rows = [
        merge_group(by_nano.loc[group], resources, group) for group in groups
    ]
    out = pd.DataFrame(merged_rows)

    # 欄位順序：原欄位（去掉工作用的 nano 與已失去意義的共用資源指標）＋ 三個新欄
    original = [c for c in frame.columns if c not in ("nano", SHARED_COL)]
    out = out[original + [MERGED_COUNT, MERGED_FROM, GRADE_GAP]]
    # 排序使輸出與列舉順序脫鉤，重跑才會位元組相同
    return out.sort_values(MERGED_FROM, kind="stable").reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graded", type=pathlib.Path, default=GRADED)
    ap.add_argument("--resources", type=pathlib.Path, default=RESOURCES)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args(argv)

    try:
        out = dedupe(args.graded, args.resources)
    except DedupError as exc:
        print(f"去重中止：{exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig", lineterminator="\n")

    merged = int((out[MERGED_COUNT] > 1).sum())
    gaps = int(out[GRADE_GAP].sum())
    print(f"寫出 {args.out}：{len(out)} 列 × {len(out.columns)} 欄")
    print(f"  合併 {merged} 列（原 {int(out[MERGED_COUNT].sum())} 筆）")
    print(f"  {gaps} 列的分級欄位未涵蓋合併後新增的資源（未重新探測）")
    print(f"  {args.graded} 未被修改")
    return 0


if __name__ == "__main__":
    sys.exit(main())
