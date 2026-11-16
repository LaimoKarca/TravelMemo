# Gmail SMTP 設定教學

本教學設定 TravelMemo 的登入驗證碼寄送。伺服器共用一個寄件 Gmail，
使用者以自己的收件信箱與驗證碼登入，不需要每位朋友都提供 Gmail 帳密。
以下帳號及密碼是佔位值，請換成自己的設定。

## 1. 啟用兩步驟驗證

1. 登入準備拿來寄信的 Gmail。
2. 開啟 [Google 帳戶安全性](https://myaccount.google.com/security)。
3. 確認右上角是正確的寄件帳號。
4. 找到「兩步驟驗證」，依畫面完成啟用。

應用程式密碼需要先啟用兩步驟驗證；僅有通行金鑰，不代表這個條件已完成。
參見 [Google 官方說明](https://support.google.com/accounts/answer/185833?hl=zh-Hant)。

## 2. 建立應用程式密碼

1. 開啟 [應用程式密碼](https://myaccount.google.com/apppasswords)。
2. 依畫面輸入名稱，例如 `TravelMemo`，建立密碼。
3. 複製產生的16字元密碼；若以四組顯示，填設定前移除分組空格。
4. 下一節的 `SMTP_PASSWORD` 填這個新產生的密碼。

若出現「您的帳戶無法使用這項設定」，先核對帳號與兩步驟驗證狀態。
若已啟用仍不可用，可能是只使用安全金鑰、機構政策或進階保護限制，需依帳戶政策選用其他寄信方式。
Google 帳戶密碼變更後，應用程式密碼也可能需重新建立。
參見 [應用程式密碼的條件與撤銷規則](https://support.google.com/accounts/answer/185833?hl=zh-Hant)。

## 3. 填寫私人 `.env`

首次可從 `.env.example` 複製為 `.env`；已有設定時直接編輯，勿覆蓋原有資料庫密碼。

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=starttls
SMTP_AUTH=true
SMTP_USER=your-gmail-account@gmail.com
SMTP_PASSWORD=replace-with-your-app-password
SMTP_FROM="TravelMemo <your-gmail-account@gmail.com>"
SMTP_TIMEOUT=10
ALLOWED_EMAILS=owner@example.com,friend@example.com
```

- 將兩處寄件地址換成自己的完整 Gmail，`SMTP_FROM` 先與 `SMTP_USER` 使用同一帳號。
- `ALLOWED_EMAILS` 是可以登入的收件者，與寄件者可以不同。自己要登入時，也要加入自己的收件地址。
- 清單以逗號分隔、保持同一行；使用引號時，左右引號須成對。

Gmail SMTP 伺服器是 `smtp.gmail.com`，587使用STARTTLS，465使用SSL。
本應用支援將設定改為 `SMTP_PORT=465`、`SMTP_TLS=ssl`。
參見 [Google SMTP 連線設定](https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app)。
隨附的 `check-smtp.py` 檢查腳本目前使用587/STARTTLS；465設定請以實際登入寄碼流程驗證。

`.env`、`.env.*` 已由 Git 排除，只有 `.env.example` 是公開範例。
不要將實際密碼寫入公開文件或截圖。

## 4. 套用設定

### 本機 Python API

從專案根目錄執行；已有 API 運行時，先在原終端按 Ctrl+C 停止再啟動：

```powershell
.\.venv\Scripts\python.exe main.py check-config
.\.venv\Scripts\python.exe main.py serve
```

`check-config` 只驗證格式，不測帳密。
`deploy/start-dev.ps1 -CaptureMail` 會在程序內覆寫 SMTP，讓信件進入 Mailpit；
要實際寄到信箱，改用上面的普通啟動方式。

### 正式 Docker API

在部署原始碼目錄執行，換成自己的正式設定檔位置。
RELEASE_ID 要與目前部署版本相同；主機已有 current.json 時可查其 image_tag。

```powershell
$configFile = 'D:\Services\TravelMemo\.env'
$env:RELEASE_ID = '<目前部署的映像版本>'
docker compose --env-file $configFile -f deploy/compose.prod.yml up -d --no-deps --force-recreate api
```

變更 env file 後需重建 API 容器；只執行 `docker restart` 會保留建立容器時的環境變數。
請確認編輯的是部署主機使用的檔案，開發機設定不會自動同步。

## 5. 驗證：先認證、再收件

本機587設定可從根目錄執行以下指令，只做SMTP AUTH，不寄信：

```powershell
Get-Content -Raw -Encoding utf8 deploy/check-smtp.py | .\.venv\Scripts\python.exe -
```

正式容器使用：

```powershell
Get-Content -Raw -Encoding utf8 deploy/check-smtp.py | docker exec -i travelmemo-api-1 python -
```

`SMTP_AUTH_OK` 代表認證成功。接著開啟自己的網站，用允許名單內的信箱按「取得驗證碼」，
確認實際收件並輸入最新碼登入。這一步才會寄送真實郵件。

## 6. 常見問題

| 現象 | 檢查方式 |
| --- | --- |
| 應用程式密碼頁不可用 | 核對帳號、兩步驟驗證、機構政策、安全金鑰與進階保護限制 |
| 認證失敗或登入階段斷線 | 核對完整寄件地址及應用程式密碼，移除分組空格，確認密碼未撤銷 |
| 連線逾時 | 主機對 smtp.gmail.com 的 DNS、對外587連線與防火牆 |
| 寄碼503 | 核對實際 API 的 SMTP 設定與認證；可查看 docker logs --tail 50 travelmemo-api-1 |
| 畫面顯示已處理但收不到 | 查垃圾郵件、ALLOWED_EMAILS、寄送限額，並確認不是CaptureMail模式 |
| Mailpit有信，真實信箱沒有 | 改用普通API啟動方式 |
| 改設定後沒變 | 本機重啟API；Docker重建API，並核對設定檔位置 |
| 429 | 等待重寄／每小時限制結束，避免連續點選 |

為避免透露允許名單，未列入清單的信箱也會得到相同要求寄碼回應，但不會寄信。
因此HTTP202、ready200、SMTP AUTH成功，都不能單獨當成「郵件已送達」的證據。
