"""戶政司 ODRP018 的欄位註冊表。

來源用過**三種**命名方案（皆為 2026-08-13 實測 103 個期別所得，非推論）：

| 方案 | 期別 | 欄數 | 樣貌 |
| ---- | ---- | ---: | ---- |
| `aborigine_` | 10701–11410（不含 11308） | 115 | `aborigine_amis_m` |
| **中文** | **11308 單一期** | 115 | `原住民_阿美族_男_人數` |
| `indigenous_` | 11411–11507 | 162 | `indigenous_amis_m`，新增平埔 |

11308 是夾在羅馬字期間裡的孤立中文欄名期。資料模型與 `aborigine_` 版逐項相同，
故支援而非跳過——它是月報序列裡的一期，缺一個月比欄名不一致嚴重。

改版同時把三個族名的羅馬字改為族語自稱（`tsou`→`cou`、`puyuma`→`pinuyumayan`、
`hlaaluaavu`→`hlaalua`），所以正規值一律取**中文族名**，各方案的來源拼法列為別名。
與 C 系列把「國中進修部」正規化為「國中補校」是同一手法。

平埔欄位自 **11411** 起出現（值仍為 0）。11410 及之前來源**沒有**這些欄位，那是
「未提供此維度」而非「為零」，故不得產列。
"""

from __future__ import annotations

from dataclasses import dataclass, field

DATASET = "ODRP018"
FIRST_PERIOD = 10701
LAST_KNOWN_PERIOD = 11507   # 11508 實測回「查無資料」，尚未發布

# 平埔欄位最早出現的期別。實測 11410 為 115 欄無平埔、11411 為 162 欄有平埔且為 0。
PINGPU_FROM = 11411

STATUSES = {
    "plain": "平地原住民",
    "mountain": "山地原住民",
    "pingpu": "平埔原住民",
}
PINGPU_KEY = "pingpu"
SEXES = {"m": "男", "f": "女"}

# 族別：中文正規值 → 羅馬字別名（新版在前）。中文方案直接用鍵本身。
PEOPLES: dict[str, tuple[str, ...]] = {
    "阿美族": ("amis",),
    "泰雅族": ("atayal",),
    "排灣族": ("paiwan",),
    "布農族": ("bunun",),
    "魯凱族": ("rukai",),
    "卑南族": ("pinuyumayan", "puyuma"),
    "鄒族": ("cou", "tsou"),
    "賽夏族": ("saisiyat",),
    "雅美族": ("yami",),
    "邵族": ("thao",),
    "噶瑪蘭族": ("kavalan",),
    "太魯閣族": ("truku",),
    "撒奇萊雅族": ("sakizaya",),
    "賽德克族": ("sediq",),
    "拉阿魯哇族": ("hlaalua", "hlaaluaavu"),
    "卡那卡那富族": ("kanakanavu",),
    "尚未申報": ("undeclared",),
}

# 平埔族群：僅在 11411 起出現
PINGPU_PEOPLES: dict[str, tuple[str, ...]] = {
    "西拉雅族": ("siraya",),
    "大武壠族": ("taivoan",),
    "馬卡道族": ("makatau",),
    "凱達格蘭族": ("ketagalan",),
    "巴布薩族": ("babuza",),
    "洪雅族": ("hoanya",),
    "拍瀑拉族": ("papora",),
    "巴宰族": ("pazeh",),
    "噶哈巫族": ("kaxabu",),
    "道卡斯族": ("taokas",),
    "噶瑪蘭族": ("kavalan",),
    "尚未申報": ("undeclared",),
}

# site_id／區域別是「縣市＋鄉鎮市區」連寫。以已知清單比對而非固定切 3 字，
# 才能在出現未預期行政區名時報錯而非默默切錯。桃園縣列入因 103–104 尚未升格。
COUNTIES = (
    "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市",
    "基隆市", "新竹市", "嘉義市",
    "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣",
    "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣", "桃園縣",
)


class RegistryError(RuntimeError):
    """註冊表無法描述來源結構時拋出。不設靜默降級路徑。"""


@dataclass(frozen=True)
class NamingScheme:
    """一種欄名命名方案。

    三種方案的差異不只是前綴：中文方案的「總計」在頂層與身分別用不同的詞
    （`總計` 對 `合計`）、族別欄多一個 `_人數` 尾綴、性別用中文。把這些差異
    寫成資料而非分支，新增第四種方案時只要多一個條目。
    """

    label: str
    signature: str                      # 辨識用：該方案必然存在的欄名
    dims: dict[str, str]                # 正規維度名 → 來源欄名
    top: str                            # 頂層片段
    status_segment: dict[str, str]       # 身分別鍵 → 來源片段
    total_top: str                       # 頂層「總計」用詞
    total_status: str                    # 身分別小計「總計」用詞
    sex_label: dict[str, str]            # m/f → 來源寫法
    suffix: str = ""                     # 族別欄尾綴
    chinese_people: bool = False         # 族別欄用中文族名

    def aliases(self, chinese: str, status: str | None = None) -> tuple[str, ...]:
        if self.chinese_people:
            return (chinese,)
        table = PINGPU_PEOPLES if status == PINGPU_KEY else PEOPLES
        try:
            return table[chinese]
        except KeyError:
            raise RegistryError(f"註冊表沒有族別「{chinese}」的別名") from None

    def top_total(self, sex: str | None = None) -> str:
        base = f"{self.top}_{self.total_top}"
        return base if sex is None else f"{base}_{self.sex_label[sex]}"

    def status_total(self, status: str, sex: str | None = None) -> str:
        base = f"{self.status_segment[status]}_{self.total_status}"
        return base if sex is None else f"{base}_{self.sex_label[sex]}"

    def people(self, alias: str, sex: str, status: str | None = None) -> str:
        head = self.top if status is None else self.status_segment[status]
        return f"{head}_{alias}_{self.sex_label[sex]}{self.suffix}"


def _roman(prefix: str) -> NamingScheme:
    """羅馬字方案：aborigine_ 與 indigenous_ 只差前綴，其餘規則相同。"""
    return NamingScheme(
        label=prefix,
        signature=prefix + "total",
        dims={
            "期別": "statistic_yyymm",
            "區域代碼": "district_code",
            "行政區": "site_id",
            "村里": "village",
        },
        top=prefix.rstrip("_"),
        status_segment={k: f"{prefix}{k}" for k in STATUSES},
        total_top="total",
        total_status="total",
        sex_label={"m": "m", "f": "f"},
    )


SCHEME_LEGACY = _roman("aborigine_")
SCHEME_CURRENT = _roman("indigenous_")
SCHEME_CHINESE = NamingScheme(
    label="中文欄名",
    signature="原住民_總計",
    dims={
        "期別": "統計年月",
        "區域代碼": "區域別代碼",
        "行政區": "區域別",
        "村里": "村里",
    },
    top="原住民",
    status_segment={k: v for k, v in STATUSES.items()},
    total_top="總計",
    total_status="合計",
    sex_label={"m": "男", "f": "女"},
    suffix="_人數",
    chinese_people=True,
)

# 偵測順序：以 signature 欄名是否存在判定，彼此互斥
SCHEMES = (SCHEME_CURRENT, SCHEME_LEGACY, SCHEME_CHINESE)


def detect_scheme(columns: object) -> NamingScheme:
    """從實際欄名判定命名方案。判不出來就報錯，不猜。"""
    names = set(columns)
    for scheme in SCHEMES:
        if scheme.signature in names:
            return scheme
    sample = sorted(names)[:6]
    raise RegistryError(
        f"無法判定命名方案。已知方案的辨識欄位："
        f"{[s.signature for s in SCHEMES]}，實際欄名樣本：{sample}"
    )


def peoples_for(status: str) -> dict[str, tuple[str, ...]]:
    """該身分別對應的族別對照表。平埔有自己的族群清單。"""
    return PINGPU_PEOPLES if status == PINGPU_KEY else PEOPLES


def statuses_for(period: int) -> tuple[str, ...]:
    """該期別合法的身分別。平埔在 11411 之前不存在，不得產列。"""
    if period >= PINGPU_FROM:
        return ("plain", "mountain", PINGPU_KEY)
    return ("plain", "mountain")


def expected_column_count(period: int) -> int:
    """該期別預期的欄數。實測：平埔出現前 115 欄、出現後 162 欄。"""
    return 162 if period >= PINGPU_FROM else 115


def split_site(site_id: str) -> tuple[str, str]:
    """把 `新北市板橋區` 拆成（縣市, 鄉鎮市區）。對不上已知縣市即報錯。"""
    text = str(site_id).strip()
    for county in COUNTIES:
        if text.startswith(county):
            district = text[len(county):].strip()
            if not district:
                raise RegistryError(f"行政區欄只有縣市沒有鄉鎮市區：{site_id!r}")
            return county, district
    raise RegistryError(f"行政區欄的縣市不在註冊表清單中：{site_id!r}")
