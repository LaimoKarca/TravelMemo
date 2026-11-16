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

## 規格與工程紀錄

| 文件 | 內容 |
| --- | --- |
| [SPEC](SPEC.md) | 系統範圍、技術決策、開發階段與驗收條件 |
| [領域詞彙](GLOSSARY.md) | 旅程、事件、地點與圖關係的定義 |
| [階段一契約](implementation/phase-1-contract.md) | 登入與基礎 API 契約 |
| [階段一驗收](implementation/phase-1.md) | 基礎與登入的交付及驗證紀錄 |
| [階段二契約](implementation/phase-2-contract.md) | 旅程、事件與順序管理契約 |
| [階段二驗收](implementation/phase-2.md) | 旅程管理的交付及驗證紀錄 |

`reference/` 為專案擁有者本機保留的參考資料，未包含於公開儲存庫。
