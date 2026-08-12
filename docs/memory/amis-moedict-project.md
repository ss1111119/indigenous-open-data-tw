---
name: amis-moedict-project
description: g0v/amis-moedict 阿美語萌典專案現況、已知問題、技術架構與工作進度
metadata: 
  node_type: memory
  type: project
  originSessionId: b1fd134b-598f-4a0b-88af-efd5aedf7eb0
---

## 專案位置
- 原 repo：https://github.com/g0v/amis-moedict
- Fork：https://github.com/ss1111119/amis-moedict
- 本機（WSL）：`/home/ss1111119/amis-moedict/`
- WSL 從 Windows 存取：`\\wsl$\Ubuntu-24.04\home\ss1111119\amis-moedict\`

**Why:** Windows 無法 clone 這個 repo（`docs/p/ana:.json` 等檔名含冒號，NTFS 不支援），需在 WSL Ubuntu-24.04 操作。

## 已確認的資料錯誤
- `panay.json`：現在定義是「稻子」→ 應該是「小米」
- `hafay.json`：現在定義是「小米」→ 應該是「稻米」（兩者互換）
- `babuy.json`：不存在（404）
- `fafoy.json`：現在只標「野豬」→ 應該包含「豬」

## GitHub Actions 現況（都正常）
- `Safulo dictionary hyperlinks`：每天 UTC 00:00 自動跑
- `Safulo dictionary automated processing`：有詞條更新就觸發（amis-moedict-editor bot）

## 舊系統問題
- `cron:update_safolu_from_old_amis_moedict`：每小時跑的排程，不在 GitHub Actions，在另一台伺服器，目前壞掉。與現在這個 repo 的 GitHub Actions 無關。

## 中文反查（Chinese→Amis）技術現況（2026-06 已改用 LLM 重建）
- `docs/s/ch-mapping.json`：中文→阿美 反查表。**已棄用 jieba**，改用 NIU 伺服器 Ollama `gemma4:26b` 逐詞條重建。
- 母體：31,303 個有定義的詞條（從 42k JSON 篩出有 `t`/`stem` 且有 `d.f` 定義者）。
- 工作腳本：`safulo-daily/amis_chmapping_llm.py`（每 100 筆存 checkpoint，中斷可續跑），速度約 100 筆/分，全量 ~5 小時。
- 輔助腳本：`profile-defs.py`（定義句型分桶統計）、`sample-chmapping.py`（隨機抽樣）、`stratified-sample.py`（分層抽樣，每句型桶各抽測 v3）、`test-prompt-vN.py`（prompt 迭代對比）、`finalize-chmapping.py`（收尾合併）。
- **panay→小米、hafay→稻米、竹林→'aolan**（apostrophe 是 ASCII 0x27），finalize 強制修正。

### 地名/部落專名分流（重要設計）
- 教訓：通用「提取關鍵詞」對專有名詞（部落名 towapon、地名）無能為力——專名沒關鍵詞可抽，羅馬字 stem 又被 `parse_keywords` 的英數過濾砍掉，結果只剩「部落/花蓮市」沒鑑別度。**專名必須分流單獨處理**。
- `list-placenames.py`：挑出地名詞條（定義含「部落名稱/社名/地名」或行政區+今/部落字樣），約 158 個。
- `build-placename-map.py`（純文字、本機跑）：用**分層級正則**（縣市→鄉鎮→村/里/部落，強制順序吃掉上級避免黏字）精煉提取現今中文地名，加去通名版（都蘭村→也加都蘭），後處理剝介詞（之/的/原）+ 丟殘留行政通名 + STOP 黑名單。產出 `placename-map.json`：92 詞 / 176 個「中文地名→阿美羅馬字」key。
- finalize 用 `setdefault` 併入（不覆蓋通用詞義）。讓搜「都蘭/奇美/麒麟/麻荖漏」能命中對應阿美語詞。

### 關鍵技術坑（重要）
- **gemma4:26b 必須走 `/api/chat` 且 `think:False`**。它的 Modelfile 有 `RENDERER gemma4 / PARSER gemma4` + thinking；用 `/api/generate` 配裸 prompt 會把 thinking 連同答案一起吃掉、`response` 回空字串（但 `eval_count` 正常，是解碼後可見文字為空，不是模型壞）。
- Ollama 端點：`http://172.18.0.2:11434`（niu-ollama docker 內網，**只有伺服器連得到**，本機/WSL 連不到）。
- 伺服器路徑 `/home/rsjhuang/amis-moedict/`（sparse checkout 只有 docs/s）；本機開發在 WSL `/home/ss1111119/amis-moedict/`。工作流：WSL 改腳本→git push→伺服器 `curl raw.githubusercontent` 重抓→`nohup python3` 背景跑。

### Prompt 演進（v3 定稿）
- v1：保留主體地名但留「的」短語、同義詞冗餘。
- v2：拆短語但**腦補引申**（無中生有「部落習俗」等），且附帶產地排除退步。棄用。
- **v3（定稿）**：三條規則——①只取定義實際出現的詞、嚴禁推測引申；②不要含「的/地」短語（握手的地方→握手）；③詞條本身是地名/部落保留、附帶產地縣市鄉鎮村排除。殘留泛用詞（地方/時間/原因）由 `parse_keywords` 的 GENERIC 黑名單過濾。

**How to apply:** 正確順序（用全量跑當探針成本太高，已踩過坑）：① `profile-defs.py` 先靜態看句型分布 → ② `stratified-sample.py` 每桶抽測，確認不腦補/不誤殺/拆對短語 → ③ 才全量跑 `amis_chmapping_llm.py`（伺服器 nohup）→ ④ `build-placename-map.py` 建地名表（本機可跑）→ ⑤ `finalize-chmapping.py` 合併 → commit。純文字/讀 JSON 的腳本本機 WSL 直接跑（docs/s 完整有 42292 檔），不必丟伺服器；只有要連 ollama 的才上伺服器。注意檔名帶 apostrophe 前綴（如 `'atomo.json` 不是 `atomo.json`）。
