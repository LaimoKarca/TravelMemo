# Cloudflare Tunnel 自行部署教學

本教學以 Windows、PowerShell、Docker Desktop 的 Linux containers 為例，
將 TravelMemo 發佈到 `https://travel.example.com`。請將範例網域換成自己的網域。
目前可部署登入與旅程管理；回憶檢索、AI 對話及完整備份還原演練仍待後續階段。

## 1. 準備主機與網域

1. 在伺服器安裝並啟動 Docker Desktop，確認使用 Linux containers，`docker version` 可連到伺服器端。
2. 將自己的網域加入 Cloudflare，依提示到網域註冊商修改 nameserver，等待網域狀態成為 Active。
   已有網站或郵件時，先核對既有 DNS 紀錄，保留需要的 A、MX、TXT 等紀錄。
3. 取得本專案原始碼，可使用 Git 或下載 GitHub 原始碼 ZIP 後解壓縮。
4. 依 [Gmail SMTP 教學](GMAIL_SMTP.md)準備寄件帳號與應用程式密碼。

以下假設原始碼根目錄為 `D:\Services\TravelMemo\source`，
私人設定為 `D:\Services\TravelMemo\.env` 及 `.env.tunnel`。
這些路徑可自行調整；下文 Docker Compose 指令皆從原始碼根目錄執行。

Cloudflare 的公開主機名稱路由需要已加入帳戶的網域。
參見 [官方建立 Tunnel 流程](https://developers.cloudflare.com/tunnel/get-started/)。

## 2. 建立 Tunnel，取得 token

1. 登入 Cloudflare，開啟 Cloudflare One／Zero Trust 管理介面。
2. 找到 **Networking → Tunnels**，建立 Tunnel，選擇 `cloudflared`。
   舊版介面可能顯示在 **Networks → Tunnels**。
3. 名稱可填 `travel-memo`。
4. 在 **Setup Environment / Install and run** 選 Docker，取得安裝指令內的 token。
5. 先保持頁面開啟，下一節啟動 connector 後再查看連線狀態。

| 名稱 | 用途 |
| --- | --- |
| Tunnel 名稱 | 管理介面顯示名稱，可自行取名 |
| Tunnel ID | 識別 Tunnel 的 UUID，也會出現在 DNS 目的地 |
| Tunnel token | 讓 connector 連線的秘密；不能以 ID 代替 |
| 公開網址 | 使用者開啟的網站，例如 travel.example.com |

只複製 token 本身，不要把 `cloudflared.exe service install` 等完整指令當成 token。
本教學使用 Docker connector；同一部署不需要再安裝 Windows cloudflared 服務。

## 3. 啟動專用 connector

在 `D:\Services\TravelMemo\.env.tunnel` 寫入一行，換成自己的 token：

```dotenv
TUNNEL_TOKEN=replace-with-your-tunnel-token
```

這是 Docker 原生 env file，值不要加引號，也不要填其他應用程式秘密。
專案 `.env.example` 的 `CLOUDFLARE_TUNNEL_TOKEN` 不會自動傳給此獨立容器；
cloudflared 接受的環境變數名稱是 `TUNNEL_TOKEN`。
參見 [官方 token 參數](https://developers.cloudflare.com/tunnel/reference/run-parameters/)。

```powershell
docker pull cloudflare/cloudflared:latest
$cloudflaredImage = docker image inspect cloudflare/cloudflared:latest --format '{{index .RepoDigests 0}}'
docker run -d --name travelmemo-tunnel --restart unless-stopped --memory 128m --env-file 'D:\Services\TravelMemo\.env.tunnel' $cloudflaredImage tunnel --no-autoupdate run
docker logs --tail 30 travelmemo-tunnel
```

上述流程會以拉取後解析出的 digest 固定實際映像。日後更新前先記錄舊 digest。
若已有同名容器，先確認是否為自己先前建立的 connector，不要重複建立或刪除其他服務。

看到 `Registered tunnel connection`，且 Cloudflare 顯示 Healthy／已連線，表示 connector 已接上 Cloudflare。
這時尚未部署 Web App，網站仍可能無法開啟。
若畫面仍為 **No connection detected yet**，先檢查容器是否運行、token 是否正確及主機對外連線，
再重新整理管理頁；僅建立 Tunnel 或 DNS 紀錄不會啟動 connector。

## 4. 設定正式應用程式

首次複製 `.env.example` 到私人設定位置，再編輯；已有設定時不要覆蓋：

```powershell
Copy-Item .env.example 'D:\Services\TravelMemo\.env'
```

至少設定以下項目，SMTP 完整設定請接續 Gmail 教學：

```dotenv
APP_ENV=production
PUBLIC_URL=https://travel.example.com
COOKIE_SECURE=true
ALLOWED_EMAILS=owner@example.com,friend@example.com
SESSION_SECRET=replace-with-a-random-secret-at-least-32-characters
NEO4J_PASSWORD=replace-with-a-different-random-password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=starttls
SMTP_AUTH=true
SMTP_USER=your-gmail-account@gmail.com
SMTP_PASSWORD=replace-with-your-app-password
SMTP_FROM="TravelMemo <your-gmail-account@gmail.com>"
```

若有 Python，可分別執行 `python -c "import secrets; print(secrets.token_urlsafe(48))"`
產生兩個不同的隨機值。已建立資料庫後，修改 `.env` 不會自動更改既有 Neo4j 密碼。

**目前正式部署檔仍有既有網站網址，僅修改 `.env` 不足以換網域。首次部署自己的網站時，請同步修改：**

| 檔案 | 必須設定的值 |
| --- | --- |
| 私人 `.env` | PUBLIC_URL=https://travel.example.com |
| deploy/compose.prod.yml | api.environment.PUBLIC_URL 改為 https://travel.example.com |
| deploy/nginx.prod.conf | server_name 改為 travel.example.com; |

三處與下一節的公開 hostname 須一致。修改 Nginx 設定後需要重新建置 Web 映像。
正式 Compose 目前只傳入本階段需要的設定，不會把整份 `.env` 都送進 API 容器。

## 5. 建置並連接 Docker 網路

先確認 `172.30.80.0/24` 沒有與其他 Docker／VPN 網路衝突。
本專案固定 connector 為 `.2`、Web 為 `.10`、API 為 `.20`、Neo4j 為 `.30`。
若需更換網段，須同步調整 Compose 的 subnet 與所有固定 IP、API 的 TRUSTED_PROXY_IPS、
Nginx 的 allow 及下方 connector IP，不能只改其中一處。

在原始碼根目錄執行：

```powershell
$configFile = 'D:\Services\TravelMemo\.env'
$env:RELEASE_ID = 'my-first-deploy'
docker compose --env-file $configFile -f deploy/compose.prod.yml config --quiet
docker compose --env-file $configFile -f deploy/compose.prod.yml build
docker compose --env-file $configFile -f deploy/compose.prod.yml up -d --wait --wait-timeout 240
docker compose --env-file $configFile -f deploy/compose.prod.yml ps
docker network connect --ip 172.30.80.2 travelmemo-net travelmemo-tunnel
```

最後一行只在 connector 尚未加入此網路時執行。可檢查實際位址：

```powershell
$networks = docker inspect travelmemo-tunnel --format '{{json .NetworkSettings.Networks}}' | ConvertFrom-Json
$networks.'travelmemo-net'.IPAddress
```

應顯示 `172.30.80.2`。共享網路讓 connector 能以容器名稱連到 Web。
參見 [Docker network connect](https://docs.docker.com/reference/cli/docker/network/connect/)。
此 Compose 不對主機公開 Web、API 或 Neo4j port。

## 6. 新增公開網址路由

回到剛建立的 Tunnel，找到 **Routes → Add route → Published application**。
舊介面可能顯示 **Public Hostnames → Add a public hostname**。

| 欄位 | 範例內容 |
| --- | --- |
| Subdomain | travel |
| Domain | example.com，從自己的網域選擇 |
| Path | 留空 |
| Service URL | http://travelmemo-web:80 |
| Additional application settings | 先保留預設值 |

若畫面分開顯示 Service Type 與 URL，Type 選 **HTTP**，URL 填 `travelmemo-web:80`。
按 **Add route / Save**。Cloudflare 通常會自動建立指向 `<Tunnel-ID>.cfargotunnel.com` 的 CNAME；
若提示已有同名 DNS，先確認該紀錄用途再處理。
參見 [官方路由說明](https://developers.cloudflare.com/tunnel/concepts/routing/)。

對外網址使用 HTTPS，connector 到同一 Docker 網路內的 Nginx 使用 HTTP。
不要填 `localhost:8080`：容器裡的 localhost 指向 connector 自己。
TravelMemo 自帶信箱允許名單及驗證碼登入；額外建立 Cloudflare Access 應用會再增加一層登入，
不屬於本教學的必要設定。

## 7. 驗證與日後重啟

1. 確認 Tunnel 已連線、Compose 的三個服務健康。
2. 瀏覽 `https://travel.example.com`，確認顯示登入頁。
3. 用允許名單內的信箱取得驗證碼，實際收件後登入。
4. 建立旅程及事件，重新整理後確認仍能讀取。

有 Python 的環境還可從原始碼根目錄執行公開介面檢查；務必傳入自己的網址：

```powershell
python deploy/check-public.py https://travel.example.com
```

這個檢查不寄信、不建立旅程，不能取代上面的登入與資料操作驗證。
容器設定了 `unless-stopped`，但 Windows 重開機後仍需確保 Docker Desktop 已啟動；
請實際測試主機重啟後恢復。完整備份還原演練留待階段五，目前仍須自行保護正式資料。
**不要執行 `docker compose down -v`，這會移除包含旅程資料的資料卷。**

更新、回退及目前部署限制參見 [部署說明](DEPLOYMENT.md)。

## 8. 常見問題

| 現象 | 檢查方式 |
| --- | --- |
| No connection detected yet | connector 是否啟動、token 是否有效；查看 connector 日誌及主機對外網路 |
| Tunnel Healthy，但網站502 | Compose 是否健康、Service URL 是否為 http://travelmemo-web:80、兩容器是否同在 travelmemo-net |
| 來源 Nginx 回403 | connector 在專案網路是否固定為172.30.80.2，與 nginx allow 一致 |
| 登入寫入請求403 | 網址、Compose PUBLIC_URL 及瀏覽器 Origin 是否一致；刷新頁面取得目前 CSRF token |
| Python檢查被1010擋住，但瀏覽器正常 | 使用隨附 check-public.py，其 User-Agent 會標明專案；不要直接以預設 urllib 結果判定網站故障 |
| 改SMTP設定仍沒變 | 依 Gmail 教學重建API容器，僅 restart 不會套用新 env file |
| 更換公開網址 | 同步修改三處網址與 Cloudflare route，重建部署，再驗證登入 |

Cloudflare 的1010可與瀏覽器完整性檢查有關，參見 [官方排錯](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)。
不要把含 token、完整環境變數或帳密的日誌貼到公開 issue。
