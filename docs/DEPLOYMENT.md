# Docker 與 Cloudflare 部署

第一次自行部署請先看 [Cloudflare Tunnel 逐步教學](CLOUDFLARE_TUNNEL.md)，
包含網域替換、建立 connector 與公開路由；寄件設定見 [Gmail SMTP 教學](GMAIL_SMTP.md)。
下文說明正式網路、版本更新與回退。歷史驗收保留於 implementation 文件。

正式部署與本機開發使用不同資料卷及私人設定。評估另用隔離資料庫，
不把 benchmark 或開發旅程搬到正式資料庫。

## 入口與網路

公開網址 `https://travel.tan-ji.org`，Cloudflare Published Application 指向
`http://travelmemo-web:80`。既有專用 `travelmemo-tunnel` connector 保持獨立運作。

`deploy/compose.prod.yml` 建立 `travelmemo` 專案與 `travelmemo-net` 網路：

| 服務 | 私人 IP | 功能 |
| --- | --- | --- |
| 既有 connector | 172.30.80.2 | Cloudflare Tunnel |
| web | 172.30.80.10 | Nginx、Vue 靜態檔、API 反向代理 |
| api | 172.30.80.20 | FastAPI，僅信任 web 的代理標頭 |
| neo4j | 172.30.80.30 | 獨立持久資料卷 |

子網段需先核對不與既有 Docker/VPN 網段重疊。服務均不發佈主機 Port；web 僅允許 connector
及自身健康檢查來源。Nginx 以 Cloudflare 的來源 IP 覆寫 X-Forwarded-For，API 只信任 web IP。
API 停用正式環境的 OpenAPI 與 Swagger，Cookie 強制 Secure。

## 正式設定

在專案外的私人 `.env` 保存 ALLOWED_EMAILS、SESSION_SECRET、NEO4J_PASSWORD、SMTP 設定。
正式 SESSION_SECRET 與資料庫密碼獨立產生，不沿用開發資料庫。
SMTP 使用 Gmail 應用程式密碼；不將正式設定或 token 放進 Git/Docker image。
OPENAI_API_KEY 由正式 `.env` 傳給 API，未設定則 AI 顯示不可用，旅程管理與搜尋仍可使用。
Tunnel token 只給獨立 connector，不傳給 API。PUBLIC_URL 從 `.env` 讀取，Nginx 不綁死既有網域。

API 記憶體上限2048MiB、Neo4j1536MiB、Web128MiB，加上 connector128MiB，總上限約3.75GiB。
E5 僅載入一份、CPU最多兩個編碼執行緒、批次最多8筆。模型保存於 model-data 持久卷。

## 安裝與更新

建議目錄：`D:\Services\TravelMemo`。私人 `.env` 放在根目錄，固定版本的 GitHub source
archive 解壓縮到 `releases\<commit>`，其下保留 repo 目錄。
從 release 的 repo 根目錄執行（填實際私人設定絕對路徑）。
既有站台升級前先依 [備份與還原](BACKUP_RESTORE.md)建立並驗證備份，記下原 RELEASE_ID。

```powershell
$env:RELEASE_ID = '<commit-short-id>'
docker compose --env-file 'D:\Services\TravelMemo\.env' -f deploy/compose.prod.yml config --quiet
docker compose --env-file 'D:\Services\TravelMemo\.env' -f deploy/compose.prod.yml build
docker compose --env-file 'D:\Services\TravelMemo\.env' -f deploy/compose.prod.yml up -d --wait --wait-timeout 240
docker exec travelmemo-api-1 python main.py download-model
docker exec travelmemo-api-1 python main.py rebuild-index
```

首次建立網路後，把既有專用 connector 接上：

```powershell
docker network connect --ip 172.30.80.2 travelmemo-net travelmemo-tunnel
```

若 connector 已連到該網路，不要重複執行；先 inspect 其網路位址。
API 及資料庫使用健康檢查控制啟動順序。容器設定 restart=unless-stopped。
Windows Docker Desktop 需在主機重新開機後啟動；完整主機重啟演練尚待專案部署驗收階段。

## 驗證與回退

核對 `docker compose ps`、API ready、外部 HTTPS、Secure Cookie、允許名單寄碼、資料隔離。
自動化測試應避免寄送未經要求的郵件；SMTP AUTH 可先單獨驗證，登入寄碼由使用者觸發。
公開檢查使用 `python deploy/check-public.py`，其 User-Agent 明確標示專案；Cloudflare 可能攔截
預設 Python urllib User-Agent 並回1010，這與來源網站故障不同。
如需回退程式，使用前一個 release 目錄及原 RELEASE_ID 執行 compose up，沿用原資料卷。
資料庫格式升級不得只換 image 回退，須先完成備份及對應還原程序。

**不要執行 `docker compose down -v`，也不要清理其他專案的容器、網路或資料卷。**
完整操作見 [備份與還原](BACKUP_RESTORE.md)，檢索與 AI 維護見 [回憶搜尋與 AI 對話](RECALL.md)。

## 首次公開部署驗收（2026-11-16）

- Tan-Ji 原生 Docker 建置成功，web/API/Neo4j 健康檢查通過。
- Connector 實際位於172.30.80.2；外部 HTTPS 首頁與 ready/live 都回200。
- 未登入的 me/trips 回401、開發文件回404、錯誤 Origin 寄碼要求回403。
- 實際訪客 IP 傳至 API，偽造 X-Forwarded-For 未改變 API 看到的訪客來源。
- Tan-Ji API 容器通過 Gmail SMTP AUTH，未寄出測試信；實際收碼由使用者首次登入確認。
- Chrome 可正常顯示登入頁；Cloudflare 的邊緣腳本與網站標頭相容。
- 後端22項測試通過、2項容器測試預設略過；私人旅程及資料庫整合沿用第二階段有效證據。
- 尚未進行主機重新開機或資料庫還原演練；不宣稱完成整個 SPEC 階段五。
