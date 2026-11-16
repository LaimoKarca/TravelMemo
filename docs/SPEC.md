# TravelMemo SPEC v0.1

2026-11-16 核准，依本次對話確認的規格分階段實作。

## 產品與環境

多人私人旅遊回憶 Web App。Python 3.12/FastAPI、Vue 3/TypeScript/Vite、Neo4j Community
（圖與內建 Vector Index）。LaiMO 本機開發，先建立 .venv；未來 Tan-Ji 以獨立 Docker Compose
專案與 Cloudflare Tunnel 部署。設定從 .env 載入，秘密與個人資料不提交。

以允許名單內信箱與 SMTP 六位數驗證碼登入，無密碼、無公開註冊與管理員頁面。
名單放 .env；工作階段七天，正式環境 Secure/HttpOnly/SameSite 與 CSRF 防護。
驗證碼十分鐘、重寄六十秒、最多五次猜測，具信箱與 IP 頻率限制。
所有 CRUD、搜尋、對話與引用由後端依目前使用者限制；跨帳號資源返回不存在。

## 核心資料與介面

User OWNS Trip HAS_EVENT Event；Event AT Place、HAS_CATEGORY Category，
同一使用者同一旅程的相鄰 Event 以有向 NEXT 相連。
同地重訪保留不同 Event ID，Place 以獨立 ID 選取，不按同名自動合併。
Trip 含名稱、日期範圍、時區與描述。Event 含日期、選填時間、地點、城市、類別、地址、心得。
依日期排列，同日以使用者確認順序為準；不造時間。NEXT 可跨日並保留日期脈絡，
只表示下一筆已記錄活動。插入刪除重排在交易內重接 NEXT，防循環與跨使用者/旅程連結。
八小時 trail 清洗僅屬 benchmark。編輯採版本檢查，衝突返回 409。

API `/api/v1`：auth/request-code、verify-code、logout、me；trips 與 events CRUD、
trips/{id}/event-order；search；conversations 與 messages；usage/me；health/live、ready。
前後端使用同網域。搜尋回傳事件、名次、理由及關係證據；對話回傳回答、引用與
answered/no_evidence/clarification 狀態。

## 檢索與生成

BM25 與固定 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` 的 multilingual-e5-small，
384 維正規化向量，query:/passage: 前綴。Neo4j 向量搜尋內先篩 owner，不能全站 Top-K 後過濾。
各取前 50，以 k=60 等權 RRF 融合，同分以 Event ID 排序。
事件編碼只用自身欄位；完整心得保留，截斷有紀錄。
實際文字規則解析前置地點、方向及類別，錨點前五筆沿 NEXT 一跳，按期中提案以
標準化混合 H 與關係 R 各 0.5 重排；無解析/無關係候選時用 H。
「之後」無法確認是否相鄰時澄清。索引工作狀態持久化，重啟恢復，修改排除舊向量，寫回核對版本。

OpenAI 官方 Python SDK Responses API，預設 gpt-6-luna（依使用者後續指定），僅 GPT-5 或更新世代，
不降級到舊模型。全域 Key 放 .env。store=false，本地存對話，必要歷史及證據才外送。
結構化輸出驗證引用屬本人且來自本次證據後顯示。含糊追問先澄清，無證據不編造。
歷史引用修改/刪除可辨識，追問重取資料；紀錄不是指令。API 失敗不影響紀錄管理與搜尋。
預設每人每日 50 則、每人同時一筆、全站兩筆，記錄 token 與模型用量。

## 階段與驗收

1. 基礎與登入：虛擬環境、鎖定依賴、設定、Neo4j、SMTP、Vue 登入、錯誤邊界。
2. 旅程管理：CRUD、時間軸、排序與 NEXT、資料隔離。
3. 檢索：E5、Neo4j Vector Index、BM25、RRF、方向遍歷與來源。
4. 對話：GPT-5+、追問、引用、限額與用量。
5. 評估部署：四方法 MRR、Success@1/5 與延遲；精確向量與 ANN 分報；同資料文字表示受控比較。
   benchmark 與私人資料分離，固定 commit/模型/hash/設定。至少一個失敗修正與複驗紀錄。
   Docker/Tunnel、持久卷、備份還原、版本回退及主機重啟演練。

每階段集中交付驗收結果與操作文件，依使用者指示進入下一階段。
測試覆蓋允許名單、到期重用猜測、CSRF、不同帳號、重訪/未知時間/跨日、交易失敗、
索引競態與重啟、引用與限額、桌面手機與鍵盤操作。

照片辨識、地圖、分享共編、個人 Key、公開註冊及完整研究管理介面延後。
參考資料位於 docs/reference；既有研究 https://github.com/LaimoKarca/fuzzy-travel-recall-benchmark
固定參考 commit cadb2eca2a1e09475a1851545e12de99779b8a53。
