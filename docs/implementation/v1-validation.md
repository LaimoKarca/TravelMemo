# TravelMemo v1.0.0 驗收紀錄

驗收日期：2026-11-17（Asia/Taipei）。正式網站：[travel.tan-ji.org](https://travel.tan-ji.org)。
正式映像來源為 `1fe842a78ec48a3de51226e92a5bea83eae15f39`，映像標籤 `1fe842a`。
後續文件與測試清理不改變這次部署的應用程式內容。

## 交付行為

保留信箱驗證碼登入、私人旅程、到訪事件、地點重用與時間軸，新增：

- BM25、多語 E5、等權 RRF 與查詢導向 NEXT 一跳檢索；搜尋條件在向量 Top-K 前套用。
- 固定模型 revision、384 維向量、背景索引狀態、失敗重試與事件版本核對。
- 附來源的 AI 多輪對話、歧義澄清、引用擁有者與關係驗證、歷史來源變更提示。
- Responses API 結構化輸出、`store=false`、共用 `gpt-6-luna`、每日與並行限額及 token 用量。
- 搜尋、對話與來源視窗，保留手機及鍵盤操作；OpenAI 失敗不影響一般旅程管理與搜尋。
- 可重現的四方法評估、Neo4j ANN 對照、Docker 部署、備份與隔離還原演練。

照片辨識、分享協作、個人 API Key 等未列入 SPEC v0.1 的功能不包含於此版本。

## 自動化與實際操作證據

| 檢查 | 結果與範圍 |
| --- | --- |
| 後端一般測試 | `python -m pytest -q`：89 passed、4 項 opt-in 整合測試預設略過 |
| 真實服務整合 | 四項測試通過：Neo4j／Mailpit 登入與重用限制、旅程交易及隔離、實際 Vector Index／NEXT、對話與用量持久化 |
| 程式檢查 | Ruff 通過，包含 backend、tests、main.py、experiments 與部署驗證工具 |
| 前端 | 9 個測試檔共 71 項通過；TypeScript 型別檢查與 Vite build 通過 |
| 瀏覽器流程 | 以 Mailpit 完成錯碼重試、登入、建立旅程事件、搜尋、來源跳轉、AI 引用與追問 |
| 手機與鍵盤 | 390×844 實際檢查；頁面無水平溢位，三分頁可見，方向鍵及 Home／End 可切換焦點 |
| Linux 模型資源 | 2048MiB 上限內完成 E5 推論；8×512 token 批次測試峰值約 820MiB |
| 本機正式 Compose | 三服務健康；真實 E5／AI、代理入口、12 節點備份與兩事件／NEXT 隔離還原通過 |
| 公開內容排除 | Git 未追蹤 `.env`、私人設定、`docs/reference/`、模型或資料集；提交檔案與已知設定秘密值比對通過 |

前端證據沿用相同程式內容的有效測試結果；最後變更後重新檢查受影響的檢索測試。
整合測試使用本機測試資料，未對朋友的正式資料執行測試編碼，也未寄送真實登入測試信。

## Tan-Ji 正式部署

1. 從 GitHub 取得固定 commit 的原始碼封存，在 Tan-Ji 原生建置 API 與 Web 映像。
2. 升級前停寫備份，保留原映像、原來源及 `previous-v1.json` 作回退依據。
3. 沿用獨立 `travelmemo` Compose、既有資料卷及專用 Cloudflare connector；其他專案未更動。
4. 下載固定 revision 的 E5，逐檔核對 SHA-256，存於持久模型卷。
5. 建立唯一的合成測試帳號資料，驗證兩事件跨日 NEXT、向量搜尋及其他擁有者無法讀取。
6. 實際呼叫 `gpt-6-luna`，確認回答引用正確事件並記錄用量；Gmail SMTP AUTH 成功，未寄信。
7. 對含該合成資料的正式卷做離線備份，在新 internal 網路及新資料卷還原，核對 12 節點、兩事件與一條 NEXT。
8. API／Neo4j 重啟後再驗證搜尋、原對話的兩則訊息、來源引用與用量仍存在。
9. 清除本次合成資料，更新 `current.json`；Web、API、Neo4j 健康，四個專案容器均為 `unless-stopped`，沒有 OOM。

正式備份：`20261116T174639Z-3c626268`，時間名稱使用 UTC。
封存 SHA-256：`49d3e9338e379d991c2d328c93a995f3ac701ec0c8a487f7bee6beb6ca24aa9c`。
實際輸出包含 `RESTORED_TRIP_OK events=2`、`RESTORE_DRILL_OK nodes=12`、
`RESTART_CONVERSATION_CITATIONS_USAGE_OK` 與 `RELEASE_FIXTURE_REMOVED`。

外部 HTTPS 九項 smoke checks 通過：首頁、live／ready、未登入資源 401、正式文件 404、
錯誤 Origin 403 及來源標頭探測。手機 Chrome 登入頁正常；未登入的 `/auth/me` 401 屬預期結果。
公開 JavaScript 與容器檔案 SHA-256 一致：
`35e039b2fb75e656c3737401c20e8cbcd7b9e61b10fb2d15e87f1960449cbcc0`。

## 實際失敗案例與修正

**現象：** 含糊的「after／之後」雖回傳澄清文字，仍先做 NEXT 遍歷並附關係候選，
等同在澄清前假設「之後」就是下一站。

**證據：** 新增 `test_broad_after_does_not_assume_or_traverse_next`，以禁止遍歷的測試替身驗證；
修正前觸發 `AssertionError: Ambiguous after must not traverse NEXT before clarification`。

**原因及修正：** 原流程設定 clarification 後仍繼續關係排序。改為偵測歧義後立即回傳澄清與一般混合候選，
所有候選 relation 為空。原關係測試改用明確「下一站／immediately after」驗證圖排序，另保留中英文歧義斷言。

**複驗：** 新回歸測試、完整後端一般測試，以及實際 Neo4j 的歧義／明確相鄰測試均通過。
另曾修正手機分頁裁切、錯碼導致離開驗證步驟、過期索引寫回、來源重排後關係證據失效等問題。

## 評估與執行限制

完整固定輸入、版本、MRR、Success@1／5、分類結果及延遲見[評估成果](../EVALUATION_RESULTS.md)。
原始 320 筆查詢與另行改寫的 107 筆明確相鄰診斷分開報告，不宣稱 NEXT 在原始資料上勝過其他方法。
量測未包含多使用者高並行壓力測試；舊 commit 的實測延遲不標作最終發布版效能。

容器停止／啟動與還原演練已完成；**整台 Tan-Ji 重開機尚未執行**。
初次驗收時 Docker Desktop `autoStart` 為 false；後續已備份原設定，開啟 Docker 的 Windows 登入後啟動設定，
並保留原有 Windows 登入方式。此設定尚未經整機重開機複驗。

主機擁有者已授權重開機，但 Desktop Commander 的 `blockedCommands` 禁止 `shutdown`，未改用其他方式繞過。
唯讀檢查確認 Windows 遠端桌面已啟用且正在監聽，但未驗證外網可連；擁有者目前只有 Desktop Commander 可用，
且主機未設定 Windows 自動登入。因此保留主機運行，待有現場操作或可用的登入畫面遠端連線後再安排演練。
後續公開 ready 檢查回傳 `database=true`。恢復程序見[部署文件](../DEPLOYMENT.md)；
不將容器驗收、啟動設定或使用者授權當成完整主機重開機證據。

本次使用 Herdr 協作實作與交叉檢查、OpenAI Docs、實用 TDD、瀏覽器／介面檢查與交付驗證流程；
Lead 檢查實際差異與命令結果，未僅依 Worker 的完成訊息宣告通過。
