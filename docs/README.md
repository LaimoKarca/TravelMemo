# TravelMemo 文件索引

專案介紹與功能總覽見 [首頁 README](../README.md)。以下依使用目的整理操作與工程文件。

## 啟動與部署

| 文件 | 內容 |
| --- | --- |
| [本機開發與啟動](GETTING_STARTED.md) | 環境需求、虛擬環境、Mailpit、前後端啟動與開發檢查 |
| [Gmail SMTP](GMAIL_SMTP.md) | Google 兩步驟驗證、應用程式密碼、SMTP 設定及收信驗證 |
| [Cloudflare Tunnel](CLOUDFLARE_TUNNEL.md) | 網域、connector、Docker 網路與公開路由的完整步驟 |
| [操作與排錯](OPERATIONS.md) | 允許名單、設定、啟停、登入與 SMTP 常見錯誤 |
| [部署與更新](DEPLOYMENT.md) | 正式部署架構、Docker Compose 設定與更新回退指引 |
| [回憶搜尋與 AI 對話](RECALL.md) | 搜尋線索、來源、模型與索引維護、自動標題與多輪追問 |
| [後端處理流程](BACKEND.md) | AI 安全分流、上下文壓縮、記憶邊界與時區資料 |
| [備份與還原](BACKUP_RESTORE.md) | 離線備份、完整性驗證、隔離演練、正式還原與版本回退 |
| [檢索評估](EVALUATION.md) | 固定輸入、四方法比較、精確向量與 ANN、結果解讀 |

## 規格與工程契約

| 文件 | 內容 |
| --- | --- |
| [SPEC](SPEC.md) | 系統範圍、技術決策與核心架構 |
| [領域詞彙](GLOSSARY.md) | 旅程、事件、地點與圖關係的定義 |
| [登入 API](API_AUTH.md) | 登入、工作階段與健康檢查 |
| [旅程 API](API_TRAVEL.md) | 旅程、事件與順序管理 |
| [檢索與對話 API](API_RECALL.md) | 檢索、對話、引用與索引的一致介面 |

`reference/` 為專案保留的參考資料，未包含於公開儲存庫。
