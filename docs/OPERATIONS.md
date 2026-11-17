# 操作與排錯

## 設定與帳號

應用從根目錄 `.env` 載入設定，執行時的環境變數優先。請從專案根目錄啟動。
`ALLOWED_EMAILS=a@example.com,b@example.com` 以逗號分隔，不分大小寫。
調整後重啟 API。已移除信箱的既有工作階段會於後續請求失效；資料不會自動刪除。
登入錯誤不顯示信箱是否在名單內。新碼使舊碼失效；驗證失敗次數會保存，不因回傳錯誤而回滾。

`SESSION_SECRET` 至少 32 字元；可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"`
產生。變更秘密會使工作階段與未使用驗證碼失效。
驗證碼預設 600 秒、重寄 60 秒、最多五次猜測。寄碼每信箱每小時五次、每 IP 二十次；
驗證每 IP 每小時一百次。遭拒的寄碼要求也可能計入限制，等待視窗結束後重試。

工作階段預設七天。Cookie 為 HttpOnly、SameSite=Lax；登出需要 `/auth/me`
回傳的 CSRF token，前端僅在記憶體中保存。API 不信任任意 Forwarded header。
正式代理只信任專案內的 Web IP，來源 IP 由 Cloudflare 經 Nginx 傳遞；設定見部署文件。

## SMTP

使用 Gmail 時，請依 [Gmail SMTP 逐步教學](GMAIL_SMTP.md)設定 Google 兩步驟驗證、
應用程式密碼與 `.env`，並驗證實際收件。公開網站設定見 [Cloudflare Tunnel 教學](CLOUDFLARE_TUNNEL.md)。

本機使用 Mailpit，`SMTP_HOST=localhost`、`SMTP_PORT=1025`、`SMTP_TLS=none`，
帳密留空，信件只留在本機開發收件箱。寄件者可用預設 example.com 測試地址。

真實服務通常設定 `SMTP_TLS=starttls` / port 587 或 `SMTP_TLS=ssl` / port 465，
依供應商設定 `SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM`。部分服務需要應用程式密碼或寄件網域驗證。
帳密僅填本機 `.env`。正式設定前不宣稱外部郵件投遞已驗證。

若要在本機開發時攔截信件進行除錯，可執行 `powershell -File deploy/start-dev.ps1 -CaptureMail`；此指令僅在啟動程序中覆寫 SMTP 環境變數導向 Mailpit，停止該程序後不影響 `.env` 設定。

OpenAI 預設模型設定為 `gpt-6-luna`，API Key 保留在 `.env`。
對話與引用操作見 [回憶搜尋與 AI 對話](RECALL.md)。本版保存文字紀錄，不提供圖片辨識。

`APP_ENV=production` 要求 HTTPS `PUBLIC_URL`、`COOKIE_SECURE=true`、非空允許名單、
已設定 SMTP 及加密 SMTP。不要將開發 Mailpit 或 Neo4j Browser 暴露到網路。
更完整 Docker / Cloudflare 部署與備份還原見 [部署說明](DEPLOYMENT.md) 與 [備份與還原](BACKUP_RESTORE.md)。

## 啟停與資料

API：`python main.py serve`，Ctrl+C 停止。前端：`npm.cmd run dev`。
開發容器：`docker compose --env-file .env -f deploy/compose.dev.yml stop` 暫停，
`up -d` 恢復。`down` 移除容器但保留 Neo4j 卷；勿加 `-v`，那會刪除資料。
不要刪除其他專案的容器或資料卷。

Neo4j 密碼透過 `.env` 初始化；既有資料卷不會因改 `.env` 而重設資料庫密碼。
第一次啟動需要下載映像及等待 Neo4j 就緒。初始化命令可重複執行，建立唯一性約束。
所有 AuthRecord 以唯一 key 保存 JSON 狀態；OTP 與工作階段僅保存不可直接還原的驗證資料。
使用資料庫鎖將狀態轉換序列化，避免同碼平行兌換。到期記錄每小時清理。

## 排錯

- `check-config` 失敗：核對必要秘密長度、TLS 選項與正式環境要求。
- API 啟動失敗：確認 Docker Desktop 已啟動、Neo4j 已就緒與帳密正確；無資料庫時不切換記憶體保存。
- 寄碼 503：核對 SMTP 主機、TLS、帳密與寄件者資格；秘密不寫入回應。
- 登入 401：確認最新驗證碼、期限與錯誤次數；要求新碼後舊碼無效。
- 429：等待限制視窗結束，不需清除資料庫。
- 登出 403：重新整理取得目前工作階段的 CSRF token。
- Ready 503：回應只列出資料庫可用性與 SMTP 是否有設定，不保證真實信箱投遞。

正式部署請填入自己的信箱、SMTP、網域與 Tunnel token；AI 對話另需 OpenAI Key。
備份、隔離演練及版本回退見 [備份與還原](BACKUP_RESTORE.md)。
