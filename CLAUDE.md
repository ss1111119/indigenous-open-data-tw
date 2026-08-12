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

## 動手前必須知道的五件事

1. **格式標示不可信。** 標 CSV/JSON 不代表裡面有資料。原民會就業那筆標 JSON/XML/CSV，實際是 24 筆 PDF 連結清單。
2. **SEGIS 的 oCode 只給最新一期**，拿不到歷年；加密請求碼繞不過去。規劃前先問：要最新一期還是時間序列？
3. **SEGIS `行政區原住民15歲以上…教育程度人口統計` 是壞的**（縣市歸屬錯位，臺南 163%、雲林 194%）。內部一致性檢查抓不到，只能拿外部數字比對。要學歷結構走統計區版。
4. **三個維度常被混用**：「原住民」（身分別）／「原住民族」（族別）／「原住民地區」（55 鄉鎮）。各機關定義未必一致。
5. **倫理界線畫在空間解析度**，不是主題。輸出止於鄉鎮市區，村里／網格不再散布。

## 工作方式

- **寫規格前先實測**。提案裡的數字都要是跑出來的，不是推論的。假設被推翻，先修文件再寫程式。
- **安全網釘不變量**，釘跨檔案約束，不釘單一數字。
- **不承諾做不到的事**。README 與輸出頁只寫確定做得到的，不寫「定期更新／主動通知」。
- ⚠️ `Documents` 本身是 git 工作目錄。動 git 前先 `git rev-parse --show-toplevel`。

## 相關專案

`moe-indigenous-stats`（大專原住民學生，已上線）、`indigenous-constitution-tw`（憲政代表性，已上線）。作法應與這兩個一致。
