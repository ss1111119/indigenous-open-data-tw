---
name: indigenous-constitution-tw
description: 原住民族憲政代表性視覺化專案，已上線 GitHub Pages；下一步是 scheduled-data-refresh change 的實作
metadata: 
  node_type: memory
  type: project
  originSessionId: 236be91a-4fc9-41ca-93b4-4d74ea3fcbbd
  modified: 2026-08-11T11:04:51.309Z
---

2026-08-09 起。本機 `C:\Users\rsjhu\Documents\code\indigenous-constitution-tw`，
自己的 git repo（見 [[documents-git-repo-hazard]]），remote `ss1111119/indigenous-constitution-tw`，
已上線 <https://ss1111119.github.io/indigenous-constitution-tw/>（master push 自動部署）。

研究結論、資料來源、格式陷阱、規格與提案全部寫在 repo 的 `docs/`、`data/sources.json`、
`openspec/specs/` 與 `openspec/changes/`，這裡不重複。

**Why:** 以下是重啟時光看 repo 不會知道的事。

1. **時間窗口是這個專案的全部價值。**《平埔原住民族群身分法》第 23 條要求政府於
   **2028-10-23 前**就平埔族群政治參與立法。過了那個期限，本專案從「對進行中辯論
   提供數據」降級為「事後整理」。所有優先序判斷都應該回到這一點。
2. **西拉雅族 2026-08 中開放身分登記。** 第一筆非零的官方平埔人口預計出現在
   ODRP 期別 **11508**（約 2026-10 上架，發布滯後約兩個月）。2026-08-11 實測
   最新可取期別仍是 11506、11507 尚未發布。那個數字出現前，站上「平埔族群的
   戶籍登記人口目前為零」是對的；出現後就是錯的——這是 `scheduled-data-refresh`
   這個 change 的整個理由。
3. **⚠️ `spectra park` 會把 change 的 artifacts 移出工作區，存到 `.git/spectra-app/`，
   那裡不在版本控制中也不會被推。** park 是暫存狀態不是保存機制。
   `/spectra-propose` 結尾會無條件 park，做完要記得 `spectra unpark` 再 commit，
   否則一整份提案只存在單一台機器的 `.git/` 裡。本專案慣例是
   `openspec/changes/` 入庫。
4. **`/spectra-*` 指令只在專案資料夾開 session 才載入得到**（skill 檔在
   `.claude/skills/`）。在 `code/` 開的 session 叫不到；必要時可直接讀
   `.claude/skills/spectra-propose/SKILL.md` 手動走，但 apply 有狀態追蹤，
   不建議手動模擬。
5. 使用者 Downloads 裡曾有同主題 deep research 檔案，2026-08-09 確認與本專案不相關
   且已移走。**不要再去找或引用它們。**

**2026-08-11 收工時的狀態：規劃完成，實作尚未開始。**

- `scheduled-data-refresh` 提案／設計／規格／任務已入庫並推送，但**任務進度 0/12**，
  一行程式都還沒寫。這是唯一有到期日的一項（見上面第 2 點）。
- 已完成並上線：分享卡片 `og:`／`twitter:` 標籤、`favicon.svg`、`icon-180.png`
  （產生器 `scripts/make-brand-assets.py`，需 Pillow，**不屬於組建流程**）。
- 還沒動：**URL 狀態**（分頁／地區／模擬器參數都不可連結，只能截圖分享）、
  席次模擬的**二維等高線圖**、`docs/feasibility-study.md` 待辦第 5 項
  **洪雅族疑點**（🔴，唯一會改變模擬器選項設計的內容待辦）。

**兩件只有使用者能做、已告知但尚未確認完成的事：**

1. Facebook Sharing Debugger 跑一次 Scrape Again——爬蟲快取只有帳號持有者能觸發重抓，
   分享卡片才會生效。
2. 2026-09 月底「118 條／種」追蹤時間點設行事曆或 GitHub issue。
   **不要放在 `feasibility-study.md` 的待辦清單裡**——那份清單已證明會過期
   （待辦 2 早就完成卻掛著 🔴 直到 2026-08-11 才被發現）。

**How to apply:** 下一步是在專案資料夾開 session 跑
`/spectra-apply scheduled-data-refresh`，**先做完第 1 組（回歸測試）就停下來驗證**
再往下——那是後面所有自動化的安全網。

⚠️ **本專案**已評估並**決定不取用 SEGIS**（見 `docs/segis-check.md`：ODRP013 已有
山地／平地分項且期別更新，SEGIS 唯一獨有的只剩村里粒度），不要重新評估。
但這個結論**只限本專案**——SEGIS 本身是好來源，別條線仍在用，見
[[segis-language-census]]。
