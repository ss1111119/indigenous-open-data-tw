---
name: documents-git-repo-hazard
description: 整個 Documents 資料夾是 ss1111119/newschool 的 git 工作目錄，根目錄 git add -A 會掃進個資檔
metadata: 
  node_type: memory
  type: project
  originSessionId: c2c613ac-5d9f-45fd-a5a8-fcb17868f360
  modified: 2026-08-09T05:59:32.660Z
---

`C:\Users\rsjhu\Documents` **整個資料夾本身**是一個 git 工作目錄，remote 是
`https://github.com/ss1111119/newschool.git`（PRIVATE）。只追蹤 50 個檔案、全在 `code/` 底下，
但有 112 個未追蹤檔案，包含 `20250425_個人資料檔案清冊+風險評估清冊_系統設計組.xlsx` 這類個資文件。

**Why:** 目前沒有外洩（remote 私有、那些檔案未追蹤），但在 repo 根目錄執行一次
`git add -A` 就會全部進版控。這個結構從路徑上看不出來——在 `code/0808/` 底下工作時
`git rev-parse --is-inside-work-tree` 會回 true，很容易誤以為是專案自己的 repo。

**How to apply:** 在 Documents 底下任何位置動 git 之前，先確認
`git rev-parse --show-toplevel`。要 commit 專案檔案時用明確路徑，不要 `git add -A`。
新專案一律在自己的資料夾 `git init`，不要靠外層那個 repo（[[moe-indigenous-stats]] 就是這樣處理的）。
使用者尚未修掉根本問題（可加 `/*` + `!/code/` 的 .gitignore，或把 repo 搬進 `code/`）。
