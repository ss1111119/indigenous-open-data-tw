<!-- SPECTRA:START v1.0.2 -->

# Spectra Instructions

This project uses Spectra for Spec-Driven Development(SDD). Specs live in `openspec/specs/`, change proposals in `openspec/changes/`.

## Use `/spectra-*` skills when:

- A discussion needs structure before coding → `/spectra-discuss`
- User wants to plan, propose, or design a change → `/spectra-propose`
- Tasks are ready to implement → `/spectra-apply`
- There's an in-progress change to continue → `/spectra-ingest`
- User asks about specs or how something works → `/spectra-ask`
- Implementation is done → `/spectra-archive`
- Commit only files related to a specific change → `/spectra-commit`

## Workflow

discuss? → propose → apply ⇄ ingest → archive

- `discuss` is optional — skip if requirements are clear
- Requirements change mid-work? Plan mode → `ingest` → resume `apply`

## Parked Changes

Changes can be parked（暫存）— temporarily moved out of `openspec/changes/`. Parked changes won't appear in `spectra list` but can be found with `spectra list --parked`. To restore: `spectra unpark <name>`. The `/spectra-apply` and `/spectra-ingest` skills handle parked changes automatically.

<!-- SPECTRA:END -->

---

# 專案脈絡

**台灣原住民族公開統計的整理專案。** 建立於 2026-08-12。

## 一句話定位

把散在各機關、各年度、各種格式的原住民族公開統計，整理成可直接讀進 pandas 的長表。
**不蒐集原生資料、不代表任何族群或機構發言、不做入口網站。**

## 起點的關鍵發現

2026-08-12 盤點（`docs/來源盤點.md`）推翻了原本的假設：

> 原以為「政府資料不足，要去挖」。實際上 ODPortal 名稱含原住民關鍵字的有 **763 筆**，
> SEGIS 另有 **120 筆**（且「原住民」是正式統計小類），教育部有 21 學年度。
> **資料過剩且碎片化。價值在篩選、去重、統一口徑、攤平成長表——不在蒐集。**

## 先讀這些

| 檔案 | 內容 |
|---|---|
| `README.md` | 範圍（做什麼／不做什麼）、倫理界線 |
| `docs/來源盤點.md` | 四大來源的完整盤點、取數技術、已知壞掉的資料 |
| `docs/memory/INDEX.md` | 從全域記憶搬進來的脈絡快照，逐則說明為什麼相關 |
| `catalog/odportal-763.csv` | 763 筆清單 |

## 動手前必須知道的八件事

1. **格式標示不可信。** 標 CSV/JSON 不代表裡面有資料。原民會「就業狀況調查報告」那筆標 JSON/XML/CSV，實際是 24 筆 PDF 連結清單。（⚠️ 那只是**那一筆**，不是整個就業主題——見第 8 條。）
2. **SEGIS 的 oCode 只給最新一期**，拿不到歷年；加密請求碼繞不過去。規劃前先問：要最新一期還是時間序列？
3. **SEGIS `行政區原住民15歲以上…教育程度人口統計` 是壞的**（縣市歸屬錯位，臺南 163%、雲林 194%）。內部一致性檢查抓不到，只能拿外部數字比對。要學歷結構走統計區版。
4. **三個維度常被混用**：「原住民」（身分別）／「原住民族」（族別）／「原住民地區」（55 鄉鎮）。各機關定義未必一致。
5. **倫理界線畫在空間解析度**，不是主題。輸出止於鄉鎮市區，村里／網格不再散布。有實測依據：戶政司村里層級 25% 的非零列少於 10 人，「村里 × 單一族別 × 性別」有 32,936 格是 1–2 人。
6. **平埔原住民是另立的法定類別**，不是山地／平地的子類（《平埔原住民族群身分法》114-10-23 施行）。戶政司自期別 11411 開好 12 個平埔族群欄位但**值仍為 0**；11508 起轉非零時，總數上升**不等於**人口成長。故「原住民共 27 族」與「共 17 族」都可能對，取決於問哪個身分別。
7. **清單的價值可能低於它指向的主機。** 683 筆去重清單裡 78% 是單一縣市單一年度的孤立快照，疊得起來的只有 10%；但把資源網址按主機分組，就找到戶政司的規律 REST API。找資料時看主機，不要只看名稱。
8. ⚠️ **就業不是缺口。** 舊文件寫「就業＝PDF 殼，唯一沒有替代來源的缺口」，2026-08-13 實測更正：名稱含就業關鍵字的 51 筆裡 **49 筆是真資料**，只有那份「就業狀況調查報告」是 PDF 殼。原民會把就業切成細表（勞參率、失業率、行業、職業、從業身分、工作收入、求職管道 × 按地區別／人口特性／行業及職業分），9 個年度。**不需要解析 PDF。** ⚠️ 但 **106 年的縣市層是壞的**（臺東縣人口 −82.76、新竹縣 147%、臺東縣 178%）、**107 年整年缺**、且這是**抽樣調查**（有樣本數欄、人數為非整數估計值）。

## 工作方式

- **寫規格前先實測**。提案裡的數字都要是跑出來的，不是推論的。假設被推翻，先修文件再寫程式。
- ⚠️ **主張跨某個維度一致時，該維度必須全掃，不能抽樣。** 抽樣只夠**否證**（一個反例就夠），不夠**斷言一致**。成本使全掃不可行時，就把主張限縮成「已驗的那幾點」，並讓程式在遇到未驗情況時**報錯而非沿用推論**。

  這條是 2026-08-13 用八個實例換來的。當天在 artifacts 層級改了 10 處，其中 8 處同一個病因——抽測 N 點後把結論寫成全域性質：抽測 11301／11306 都是 `aborigine_` 欄名，漏掉中間 11308 是全中文欄名；抽測 11401（115 欄）與 11412（162 欄），把改版邊界寫成 11412，實際是 11411；只驗 `C1-2` 的 `-` 是 0 就寫「一律當 0」，漏掉 `C2-3` 的 `-` 是「組合不存在」。

  **八處全部沒有產出錯資料，因為程式選了報錯而不是沿用推論。** 這條規則要固化的就是這個已經生效的作法。

- **安全網釘不變量**，釘跨檔案約束，不釘單一數字。⚠️ **並確認它不是恆真的**：曾寫過「依族別加總等於依身分別加總」，那兩者都是把同一批列相加，數學上永遠相等，注入故障也不會失敗。每條不變量都要有對應的注入故障測試證明它會失敗。
- **不承諾做不到的事**。README 與輸出頁只寫確定做得到的，不寫「定期更新／主動通知」。
- ⚠️ `Documents` 本身是 git 工作目錄。動 git 前先 `git rev-parse --show-toplevel`。

## 相關專案

`moe-indigenous-stats`（大專原住民學生，已上線）、`indigenous-constitution-tw`（憲政代表性，已上線）。作法應與這兩個一致。
