---
name: amis-translation-toolchain
description: 阿美語維基百科翻譯校對的工具鏈(ILRDF 官方翻譯 + g0v 萌典本地查證)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 217dab85-0d67-4cfe-bd19-97184718b192
---

校對/翻譯阿美語(ami-wikipedia 專案,翻譯內容存於 Firebase 專案 `ami-wiki-review` 的 Firestore `translations/<id>/sections`)時的工具鏈:

**1. 翻譯引擎 — 原民會 ILRDF 族語基礎翻譯系統(優於通用 AI)**
- 網址:https://ai-labs.ilrdf.org.tw/kari-seejiq-tnpusu-ai-hmjil/
- Gradio API:`POST <該網址>/gradio_api/queue/join` body `{"data":["<中文>","zho_Hant","ami_Xiug"],"fn_index":3,"trigger_id":20,"session_hash":"<隨機>"}`,再 `GET .../gradio_api/queue/data?session_hash=<同>` (SSE) 取 `process_completed` 的 output。
- 方言碼:`ami_Xiug`=秀姑巒、另有海岸/恆春/馬蘭/南勢。本專案目前用**秀姑巒**。
- **重要弱點:數字幾乎都翻錯**(年份/世紀/百分比/大數),還會吐亂碼 `(eXeYe)`。翻完一律照中文原文把數字改成阿拉伯數字、清亂碼。逐句餵效果最好。

**2. 查證字典 — 新版萌典 DB(主力)+ g0v amis-moedict(備援)**
- **主力**:`node dict/lookup-new.mjs <阿美語>`(正查,含各辭典釋義+例句)、`-r <中文>`(反查)。查 `ami-wikipedia/amis-moedict-new-db-backup/amis-moedict-202512.sqlite3`(用 node:sqlite,Node 24+),**11 部辭典/10.5 萬詞/8.3 萬例句**(蔡中涵 42k、吳明義 30k、潘世光阿漢 15k、原民會線上辭典、五方言學習詞表…)。涵蓋率遠勝 g0v,連「聯盟=katatelekan/makaketo」「投降=doʼedo」這類 g0v 查無的都有。容錯喉塞音。
- **備援**:`node dict/lookup.mjs <阿美語>` / `-r <中文>`(g0v amis-moedict,4萬詞,CC0,本機 JSON)。
- 即使新 DB 仍查無的(殖民地/國會/總理/半導體/海峽/貨櫃…)是**真的沒詞**→ 標 `【中文】` 給老師,不硬湊。

**流程:ILRDF 逐句翻 → 數字改阿拉伯 → 萌典正查/反查校對 → 寫回 Firestore `ami_reviewed`,疑問用詞寫進 `comments` → 老師在平台確認。** 不擅自造詞,查無的詞標出來給老師。詳見 [[ami-wiki-review-platform]]。
