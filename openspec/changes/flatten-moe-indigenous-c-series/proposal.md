## Why

盤點結論是「資料過剩且碎片化，價值在整合不在蒐集」，但專案至今只有清單，沒有任何一張長表。教育部原住民學生概況統計是四大來源中**唯一已實測證明可跨年度合併**的一組（2026-08-12 驗證：103–114 全 12 份可抓，26 個表號的資料欄語意 12 年一致，初判的 3 個例外經查證全是版面雜訊）。

先做這一組，目的不只是產出資料，更是**用最低風險的來源把長表 schema 與 pipeline 設計定下來**——後續 763 筆碎片的整合都要沿用同一套 schema。若連格式最穩的這組都設計不出可用的長表，其餘來源不必談。

本變更取 C 系列（國民中小學）6 張表。理由：姊妹專案 `moe-indigenous-stats` 已涵蓋大專（A 系列）與高中職分流（B 系列部分），國中小是它文件中明確列為「範圍外」的缺口，不重工；且 C 系列同時包含校別明細（2,304 列）與彙總表（20 列）兩種形態，足以驗證 schema 的通用性。

## What Changes

- 新增可重現的取檔腳本，抓 103–114 共 12 份原始檔至 `data/raw/`（不入版控，可重抓）
- 新增表格結構註冊表，以資料描述 C 系列 6 張表的表頭位置與欄位語意，使日後增表是改資料而非改程式
- 新增攤平程式，將 6 張表 × 12 年輸出為單一長表 `data/processed/`
- 新增不變量測試，釘住跨年度與跨表的硬約束
- 更新 `README.md` 現況表與 `docs/來源盤點.md` 的教育部段落

**已知必須處理的五個陷阱**（皆為 2026-08-12 實測所得，非推論）：

1. **幻影欄**：109 起多數表最後一欄是「○○學年」浮水印，非資料欄；且可能夾帶雜散值（`C2-2` 111 學年該欄含一個 `0`），故「資料區非空」不足以判定有效欄，須併看表頭列有無標題文字
2. **副檔名分界在 108/109**：103–108 為 `.xls`，109 起為 `.xlsx`（108 的 `.xlsx` 回 404）
3. **表名尾隨空白**：113 學年為 `A1-1 `，比對前須正規化
4. **標題破折號不可用於比對**：108 前為 U+2014、109 起多為全形連字號，且同一份檔案內不一致（114 學年 `C2-4` 仍用 U+2014）。表格定位一律用表號，不用標題字串
5. **資料起始列會位移**：108 自 r5 起、109 起插入空白列改自 r6 起；列標籤亦由全形空格版本改為無空格版本

## Non-Goals

（本變更會建立 design.md，Non-Goals 詳見該文件的 Goals/Non-Goals 段落）

## Capabilities

### New Capabilities

- `moe-source-ingest`: 以學年為參數取得教育部原住民學生概況統計原始檔，處理副檔名跨年分界，並確保重跑結果可重現
- `moe-table-extraction`: 從原始檔中依表號定位工作表與資料區，辨識有效資料欄，隔離版面雜訊
- `moe-long-table`: 定義長表 schema、輸出 C 系列長表，並以結構欄位防止使用者跨表誤加總

### Modified Capabilities

(none)

## Impact

- Affected specs: `moe-source-ingest`、`moe-table-extraction`、`moe-long-table`（皆為新增）
- Affected code:
  - New:
    - `scripts/moe/fetch.py`
    - `scripts/moe/registry.py`
    - `scripts/moe/extract.py`
    - `scripts/moe/build_long_table.py`
    - `tests/test_moe_long_table.py`
    - `data/processed/moe-c-series-long.csv`
    - `docs/schema/moe-c-series.md`
  - Modified:
    - `README.md`
    - `docs/來源盤點.md`
  - Removed: （無）
- Dependencies: 既有環境已具備 Python 3.13.9、pandas 3.0.0、openpyxl 3.1.5、xlrd 2.0.2；`.xls` 讀取依賴 `xlrd`，`.xlsx` 依賴 `openpyxl`，本變更不新增第三方套件
