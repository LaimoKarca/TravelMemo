# 階段一交付紀錄

日期：2026-11-16。範圍：基礎與登入。第二至五階段尚未實作。

## 已交付

- 根目錄 main.py、Python .venv、pyproject 與完整版本 requirements.lock.txt。
- 本機 .env 已生成隨機 session secret 與 Neo4j 密碼，未輸出秘密；提供 .env.example。
- FastAPI：request-code、verify-code、me、logout、live、ready 與 OpenAPI。
- Neo4j 唯一性約束、驗證碼 HMAC、單次使用、持久工作階段、清理與交易鎖。
- SMTP TLS/SSL 支援；本機 Docker Neo4j 2026.10.2 與 Mailpit 1.27.10。
- Vue 3/TypeScript 登入、數字驗證碼、自動恢復工作階段、重寄倒數、CSRF 登出。
- SPEC、API 契約、README 與操作排錯文件。原有 PDF 保留。

## 已執行證據

| 檢查 | 結果 |
| --- | --- |
| Python pytest | 8 passed，1 skipped（預設略過真實容器測試） |
| 額外 opt-in tests/test_integration.py | 1 passed，真實 Neo4j / SMTP |
| Ruff check | 通過 |
| pip check | No broken requirements found |
| main.py init-db / check-config / --help | 通過 |
| 前端 Vitest | 13 passed |
| 前端 vue-tsc + Vite build | 通過 |
| Chrome 實際操作 | Mailpit 寄碼、登入、重新整理保留登入、登出通過 |
| 畫面 | 1280×800、390×844，已檢視截圖，手機無水平溢出 |
| 最後瀏覽器 console | 0 errors、0 warnings |

真實整合測試還包含兩個平行要求兌換同一驗證碼，僅一個成功；關閉原 driver、建立新 driver/app
後仍可讀取工作階段並登出。未以測試替身代替這項驗證。
畫面與瀏覽器輸出存於忽略的 .playwright-cli，操作腳本為 tests/browser-login.js。
瀏覽器腳本需本機 Mailpit 及允許的 friend@example.com 測試帳號。

## 發現與修正

獨立審查指出允許名單可能由重寄狀態差異被探知。先新增測試觀察到不允許信箱第二次仍回202，
再改為所有信箱使用相同獨立重寄限制；回歸通過。瀏覽器整合前另修正重寄成功後倒數不重設，
以及網路登出失敗卻先清除 CSRF token 的問題，保留重試能力。
Mailpit 首次容器啟動出現8025埠未綁定，重建本專案 mailpit 容器後恢復並完成整合。

## 限制與後續

- 真實外部 SMTP、正式信箱、OpenAI Key、Cloudflare 與 Tan-Ji 部署尚未設定或驗證。
- 開發環境使用 localhost 的測試信箱與 Mailpit，不寄外部郵件。
- 代理下的 IP 來源目前以連線端為準；正式部署前須設定明確受信任代理範圍，不能直接信任任意 XFF。
- 測試套件有 Starlette 提示 httpx TestClient 將改用 httpx2 的棄用警告；目前全部測試通過。
- 第一階段沒有旅程管理、向量檢索、AI 對話或正式備份還原命令，請依 SPEC 階段繼續。
- Spec Kit 初始化因目錄非空停止，未強制覆寫；本專案採現有 docs 下的 SPEC 與階段紀錄。

技能：speckit-router、herdr-orchestration（Antigravity 前端 Worker）、test-driven-development、
frontend-design、playwright-cli、requesting-code-review、verification-before-completion。
Lead 已檢視 Worker 檔案並自行驗證前端建置/測試與真實端到端流程。
