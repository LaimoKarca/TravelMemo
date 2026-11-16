# 第二階段交付與驗收

日期：2026-11-16。範圍：私人旅程、到訪事件、地點重用、時間軸與 NEXT。

## 已完成

- 使用既有信箱登入，所有旅行資料由工作階段決定擁有者；寫入要求 CSRF。
- 旅程建立、查閱、修改、刪除；日期範圍、IANA 時區、內容長度及額外欄位驗證。
- 每次到訪獨立 ID，時間可留空；明確選取 Place 重用，同名新地點不自動合併。
- 按日期與同日明確順序呈現時間軸；新增、改日、刪除及完整重排交易更新 NEXT。
- Trip/Event/Place/Category 為實際 Neo4j 節點與關係，不存入 AuthRecord JSON。
- 編輯及刪除採版本檢查；衝突不覆蓋新資料，表單保留未儲存內容並可重新載入。
- 前端手記列表、足跡表單、刪除確認、城市/類別篩選、同日上下移動及鍵盤焦點控制。
- Python 新增 tzdata，支援 Windows IANA 時區；依賴鎖定檔同步。

## 實際證據

| 檢查 | 結果 |
| --- | --- |
| 完整 pytest（容器測試預設 opt-in） | 18 passed、2 skipped |
| tests/test_phase2_database.py，真實 Neo4j | 1 passed |
| Ruff check backend tests main.py | 通過 |
| 前端 Vitest | 34 passed，4 test files |
| vue-tsc + Vite production build | 通過 |
| Chrome + 真實 API/Neo4j | 建立旅程、兩筆事件、重排、重整持久性、編輯心得、刪除事件與旅程通過 |
| 視覺檢查 | 已檢視 1440px 桌面及390px手機截圖，無水平溢出 |

真實資料庫測試核對 NEXT 及 AT 邊，Place 重用，應用重啟後資料仍存在，最後刪除測試旅程。
單元/API 測試涵蓋跨帳號 404、CSRF、日期界限、空時間、重訪、重排集合與日期順序、版本衝突。
瀏覽器腳本為 tests/browser-travel.js 與 tests/browser-travel-edit.js；需已啟動 CaptureMail API、
前端、Mailpit，並保留允許的 friend@example.com 測試帳號。後者會清除腳本建立的 Browser travel 旅程。
開發測試仍有 Starlette/httpx2 棄用提示，無測試失敗。

## 審查修正

獨立審查發現刪除旅程缺少與其他 mutation 相同的 Trip 寫入鎖；已在讀取版本之前取得鎖，
避免舊版本刪除覆蓋並行更新。Category 改由 owner+normalized_name 推導穩定 ID，
在唯一性約束下 MERGE，避免不同旅程同時建立相同類別造成多列事件寫入。
Lead 另修正回傳內部 owner 欄位造成的回應驗證問題（由 Worker 落實）、手機長信箱排版，
並核對篩選時重排仍提交完整事件集合。

## 環境與限制

Gmail 與 Tunnel 的私人設定於本機管理，不隨開源程式發佈。本機 .env 保存真實 SMTP 設定；
目前 API 以 deploy/start-dev.ps1 -CaptureMail 啟動，程序範圍設定導向 Mailpit，未更改 .env。
第二階段交付時 Gmail 登入尚未成功；後續已設定應用程式密碼並通過認證。OpenAI model access HTTP200，未呼叫生成。
後續已將目前版本部署至 Tan-Ji；實際部署及驗收狀態見 docs/DEPLOYMENT.md。

第三階段檢索與第四階段對話尚未實作。本次沒有新增假搜尋按鈕或圖片辨識。
尚未啟動正式備份還原流程；開發卷持久保存，勿執行 compose down -v。

技能沿用：herdr-orchestration、frontend-design、test-driven-development、requesting-code-review、
playwright-cli、verification-before-completion；設定模型另核對 OpenAI Docs。
兩個 Antigravity Flash Worker 負責互不重疊的前後端檔案，Lead 審查與整合並執行實際驗收。
