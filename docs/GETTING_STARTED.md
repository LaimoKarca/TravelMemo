# 本機開發與啟動

本文件說明如何在自己的電腦啟動 TravelMemo，以及執行開發檢查。
若要對外提供服務，請接續 [Cloudflare Tunnel 部署教學](CLOUDFLARE_TUNNEL.md)。
已取得原始碼者，可略過下方 git clone 與 cd TravelMemo。

## 1. Windows 本機啟動

需求：Python 3.12、Node.js 22.12 以上、已啟動的 Docker Desktop（Linux containers）。

```powershell
git clone https://github.com/LaimoKarca/TravelMemo.git
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

登入後可新增旅程手記、填入日期範圍與時區，再加入每次到訪紀錄。時間不詳可留空；
同日紀錄可往上或往下移動，也能依城市及類別篩選。重複到訪可明確選用既有地點，
仍保留不同事件。修改或刪除遇到其他分頁已更新時，會提示衝突，避免覆蓋新資料。

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
npm.cmd run build
```

本機 Neo4j / SMTP 整合測試：啟動上述容器後，在根目錄設定
`$env:TRAVELMEMO_INTEGRATION='1'` 再執行 pytest；只支援本機開發設定。

更多設定與排錯見 [操作說明](OPERATIONS.md)；回到 [文件索引](README.md)或[專案介紹](../README.md)。
