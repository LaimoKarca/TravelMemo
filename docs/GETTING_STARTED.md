# 本機開發與啟動

[文件索引](README.md)

本文件說明如何在自己的電腦啟動 TravelMemo，以及執行開發檢查。
若要對外提供服務，請接續 [Cloudflare Tunnel 部署教學](CLOUDFLARE_TUNNEL.md)。
已取得原始碼者，可略過下方 git clone 與 cd TravelMemo。

## 1. Windows 本機啟動

需求：Python 3.12、Node.js 22.12 以上、已啟動的 Docker Desktop（Linux containers）。

```powershell
git clone https://github.com/your-username/TravelMemo.git
cd TravelMemo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env  # 僅首次，勿覆蓋既有 .env
```

編輯 `.env`：將 `SESSION_SECRET` 與 `NEO4J_PASSWORD` 換成不同的隨機值，
`ALLOWED_EMAILS` 設為允許登入的信箱，以逗號分隔。新 clone 的範例秘密不會自動替換，請自行產生；
可分別執行 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 取得兩個不同的隨機值。
請勿提交 `.env` 或把其中秘密貼到對話與日誌。

```powershell
.\.venv\Scripts\python.exe main.py check-config
docker compose --env-file .env -f deploy/compose.dev.yml up -d
.\.venv\Scripts\python.exe main.py init-db
.\.venv\Scripts\python.exe main.py download-model
powershell -File deploy/start-dev.ps1 -CaptureMail
```

另開終端啟動前端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

開啟 http://localhost:5173 。上述 `-CaptureMail` 啟動方式使用 Mailpit 攔收信件，**不會寄到真實信箱**；
在 http://localhost:8025 查看驗證碼，再回登入頁輸入。僅允許 `.env` 名單內的信箱登入。
API 文件：http://localhost:8000/api/docs 。

登入後點「＋建立」建立旅行手記、填入日期範圍與時區，再加入每次到訪紀錄。時間不詳可留空；
足跡在旅行中由新到舊，未出發及結束後由舊到新；狀態依旅程時區判定。可搜尋及依城市、類別篩選，重複造訪仍保留不同事件。
手記操作列的「AI 幫我記」可從文字描述整理待確認足跡；首頁搜尋列內的篩選圖示可展開狀態與年份條件。
修改或刪除遇到其他分頁已更新時，會提示衝突，避免覆蓋新資料。

若要實際寄送驗證碼，依 [Gmail SMTP 教學](GMAIL_SMTP.md)啟用兩步驟驗證、建立應用程式密碼，
填入 `.env`，改以 `.\.venv\Scripts\python.exe main.py serve` 啟動。
若要部署自己的公開網站，依 [Cloudflare Tunnel 教學](CLOUDFLARE_TUNNEL.md)設定網域、connector 與 Docker 路由。
要使用 AI 對話，在私人 `.env` 填入 OPENAI_API_KEY；未設定時仍可管理旅程與搜尋。
完整操作、模型下載與索引排錯見 [回憶搜尋與 AI 對話](RECALL.md)。

## 2. 開發檢查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests main.py
cd frontend
npm.cmd test
npm.cmd run build
```

Neo4j / SMTP 整合測試請使用專用的本機測試資料庫與 Mailpit，避免對自己的旅程資料執行測試編碼。
在根目錄執行下列設定，再啟動整合測試；請勿指向正式環境。

```powershell
$env:TRAVELMEMO_INTEGRATION = '1'
$env:SMTP_HOST = '127.0.0.1'
$env:SMTP_PORT = '1025'
$env:SMTP_TLS = 'none'
$env:SMTP_AUTH = 'false'
.\.venv\Scripts\python.exe -m pytest tests/test_integration.py tests/test_phase2_database.py tests/test_retrieval_real_neo4j.py tests/test_release_database.py -q
```

`NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 應指向該測試資料庫。一般 `pytest` 預設略過這四項整合測試。

更多設定與排錯見 [操作說明](OPERATIONS.md)；回到 [文件索引](README.md)或[專案介紹](../README.md)。
