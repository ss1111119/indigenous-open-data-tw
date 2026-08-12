# 搬進來的記憶

2026-08-12 從 `~/.claude/projects/C--Users-rsjhu-Documents/memory/` 複製過來，
讓這個資料夾切成獨立工作目錄後仍有完整脈絡。

**這些是快照，不是正本。** 正本仍在原記憶目錄；若原記憶更新，這裡不會自動同步。
以下每則的「為什麼在這」說明它對本專案的作用。

## 資料來源與取數技術

| 檔案 | 為什麼在這 |
|---|---|
| `segis-language-census.md` | ⚠️ **最重要**。SEGIS 的 oCode 只給最新一期、加密請求碼繞不過去、一個入口即全國、教育程度那筆縣市歸屬是壞的、109 語言普查 FLD 欄位對照與百分比陷阱。本專案第四節的硬限制全來自這裡。 |
| `moe-stats-detail-files.md` | 教育部 opendata 與 detail 兩條路徑、檔名沒有規律、`base3` 的 Big5＋Tab 等跨年格式陷阱。 |

## 既有的姊妹專案

| 檔案 | 為什麼在這 |
|---|---|
| `moe-indigenous-stats.md` | 大專原住民學生統計。已上 GitHub Pages、已導入 spectra、有 17 項不變量測試。本專案的作法應與它一致。 |
| `indigenous-constitution-tw.md` | 原住民族憲政代表性。已上線；有 `data/processed/population-by-township.json` 可與語言普查對接算傳承落差。 |
| `amis-translation-toolchain.md` | 阿美語翻譯工具鏈（ILRDF 官方翻譯＋g0v 萌典查證）。語言那塊若要做會用到。 |
| `amis-moedict-project.md` | 阿美語萌典 fork、已知資料錯誤與中文反查現況。 |

## 工作方式

| 檔案 | 為什麼在這 |
|---|---|
| `feedback-verify-before-spec.md` | **寫規格前先實測**。提案裡的數字都要是跑出來的；假設被推翻先修 artifact 再寫程式。 |
| `feedback-pin-invariants-not-restatements.md` | 安全網要釘不變量，釘跨檔案約束不釘單一數字；斷言別建立在「敘述會提到某個東西」上；注入故障驗證。 |
| `feedback-no-unbacked-service-promises.md` | 不承諾做不到的事——只寫確定做得到的，不寫「定期更新／主動通知」。README 的範圍宣告照這條寫。 |
| `documents-git-repo-hazard.md` | ⚠️ `Documents` 本身是 git 工作目錄，根目錄 `git add -A` 會掃進個資檔。動 git 前先確認 toplevel。 |
