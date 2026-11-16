# Docker 與 Cloudflare 部署（目前第二階段版本）

此部署提供目前的登入與私人旅程管理。檢索、AI 對話、完整評估及正式備份還原演練仍依 SPEC 開發。
不會把開發環境的旅程或測試資料搬到正式資料庫。

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
此階段尚未啟用 OpenAI 對話，API 容器不載入未使用的 OpenAI Key 或 Tunnel token。

## 安裝與更新

建議目錄：`D:\Services\TravelMemo`。私人 `.env` 放在根目錄，固定版本的 GitHub source
archive 解壓縮到 `releases\<commit>`，其下保留 repo 目錄。
從 release 的 repo 根目錄執行（填實際私人設定絕對路徑）：

```powershell
$env:RELEASE_ID = '<commit-short-id>'
docker compose --env-file 'D:\Services\TravelMemo\.env' -f deploy/compose.prod.yml config --quiet
docker compose --env-file 'D:\Services\TravelMemo\.env' -f deploy/compose.prod.yml build
docker compose --env-file 'D:\Services\TravelMemo\.env' -f deploy/compose.prod.yml up -d --wait --wait-timeout 240
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
如需回退程式，使用前一個 release 目錄及原 RELEASE_ID 執行 compose up，沿用原資料卷。
資料庫格式升級不得只換 image 回退，須先完成備份及對應還原程序。

**不要執行 `docker compose down -v`，也不要清理其他專案的容器、網路或資料卷。**
目前只有新建獨立資料庫，完整資料庫備份與還原演練另依 SPEC 階段五完成。
