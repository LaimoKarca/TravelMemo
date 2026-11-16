# TravelMemo 文件索引

專案介紹與功能總覽見 [首頁 README](../README.md)。以下依使用目的整理操作與工程文件。

## 啟動與部署

| 文件 | 內容 |
| --- | --- |
| [本機開發與啟動](GETTING_STARTED.md) | 環境需求、虛擬環境、Mailpit、前後端啟動與開發檢查 |
| [Gmail SMTP](GMAIL_SMTP.md) | Google 兩步驟驗證、應用程式密碼、SMTP 設定及收信驗證 |
| [Cloudflare Tunnel](CLOUDFLARE_TUNNEL.md) | 網域、connector、Docker 網路與公開路由的完整步驟 |
| [操作與排錯](OPERATIONS.md) | 允許名單、設定、啟停、登入與 SMTP 常見錯誤 |
| [部署與更新](DEPLOYMENT.md) | 目前部署架構、版本更新、回退與驗收紀錄 |
| [回憶搜尋與 AI 對話](RECALL.md) | 搜尋線索、來源、模型與索引維護、多輪追問及用量 |
| [備份與還原](BACKUP_RESTORE.md) | 離線備份、SHA-256、隔離演練、正式還原與版本回退 |
| [檢索評估](EVALUATION.md) | 固定輸入、四方法比較、精確向量與 ANN、結果解讀 |
| [檢索評估成果報告](EVALUATION_RESULTS.md) | 320 筆基準測試、ANN 比較與 107 筆相鄰診斷綜合評估數據 |

## 規格與工程紀錄

| 文件 | 內容 |
| --- | --- |
| [SPEC](SPEC.md) | 系統範圍、技術決策、開發階段與驗收條件 |
| [領域詞彙](GLOSSARY.md) | 旅程、事件、地點與圖關係的定義 |
| [階段一契約](implementation/phase-1-contract.md) | 登入與基礎 API 契約 |
| [階段一驗收](implementation/phase-1.md) | 基礎與登入的交付及驗證紀錄 |
| [階段二契約](implementation/phase-2-contract.md) | 旅程、事件與順序管理契約 |
| [階段二驗收](implementation/phase-2.md) | 旅程管理的交付及驗證紀錄 |
| [v1 功能契約](implementation/release-contract.md) | 檢索、對話、引用與索引的一致介面 |
| [v1 驗收紀錄](implementation/v1-validation.md) | 測試、評估、正式部署、還原與執行限制 |

`reference/` 為專案擁有者本機保留的參考資料，未包含於公開儲存庫。
