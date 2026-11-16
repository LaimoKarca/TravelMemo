# TravelMemo

旅遊回憶管理系統，使用 Python 3.12 / FastAPI、Vue 3 / TypeScript 與 Neo4j。

目前包含階段一登入與階段二旅程管理：私人旅程、到訪紀錄、時間軸、地點重用及同日順序調整。
回憶檢索及 AI 對話依序於後續階段實作。

## Windows 本機啟動

需求：Python 3.12、Node.js 22.12 以上、已啟動的 Docker Desktop（Linux containers）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env  # 僅首次，勿覆蓋既有 .env
```

編輯 `.env`：將 `SESSION_SECRET` 與 `NEO4J_PASSWORD` 換成不同的隨機值，
`ALLOWED_EMAILS` 設為允許登入的信箱，以逗號分隔。此工作區首次建立時已自動產生隨機秘密。
請勿提交 `.env` 或把其中秘密貼到對話與日誌。

```powershell
.\.venv\Scripts\python.exe main.py check-config
docker compose --env-file .env -f deploy/compose.dev.yml up -d
.\.venv\Scripts\python.exe main.py init-db
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

若要使用 `.env` 的真實 Gmail 設定，改以 `python main.py serve` 啟動，需先完成 SMTP 認證設定。
模型已更新為 `gpt-6-luna`；OpenAI 對話尚待階段四實作。Tan-Ji 的 Tunnel connector 已上線，
應用與公開網址路由尚待部署階段接上。

## 檢查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests main.py
cd frontend
npm.cmd run build
```

本機 Neo4j / SMTP 整合測試：啟動上述容器後，在根目錄設定
`$env:TRAVELMEMO_INTEGRATION='1'` 再執行 pytest；只支援本機開發設定。

## 文件

- [SPEC 與階段](docs/SPEC.md)
- [設定、SMTP、啟停與排錯](docs/OPERATIONS.md)
- [Docker 與 Cloudflare 部署](docs/DEPLOYMENT.md)
- [階段一驗收紀錄](docs/implementation/phase-1.md)
- [階段二契約](docs/implementation/phase-2-contract.md)
- [階段二驗收紀錄](docs/implementation/phase-2.md)
- [前後端契約](docs/implementation/phase-1-contract.md)

入口為 `main.py`。後端位於 `backend/`，前端位於 `frontend/`，部署設定位於 `deploy/`。
原始參考文獻保留於 `docs/reference/`。模型下載、索引、評估等命令將於所屬階段加入，
目前 `--help` 僅列出實際可執行命令。

## 開源與私人資料

本專案以 [MIT License](LICENSE) 發佈；第三方依賴依各自授權使用。
`.env`、秘密備份、`docs/reference/`、資料集、模型權重、本機收件內容、測試截圖與產物不隨原始碼公開。
參考文獻目錄僅供專案擁有者在本機使用，GitHub clone 不會包含其中檔案。
公開設定範例為 `.env.example`，請填入自己的服務帳密。
