# 旅程與事件 API

[文件索引](README.md)

所有路徑以 `/api/v1` 為前綴，錯誤格式為 `{detail:string}`。介面使用既有 Cookie 工作階段，寫入另須 `X-CSRF-Token`。
擁有者由後端決定，不接受前端指定；其他帳號的資源 ID 回傳 404。格式驗證失敗回傳 422，版本衝突回傳 409。

## 資料格式

| 資源 | 欄位與規則 |
| --- | --- |
| Trip | `{id,name,start_date,end_date,timezone,description,version}`；日期使用 `YYYY-MM-DD`，時區為 IANA 或固定 UTC 偏移，預設 `Asia/Taipei`。名稱 1–200 字，描述最多 10,000 字，開始日期不得晚於結束日期。 |
| Event | `{id,trip_id,place_id,place_name,city,address,category,date,time,notes,position,version,timezone,record_scope}`。日常足跡的 `trip_id` 與 `position` 為 `null`、`record_scope` 為 `standalone`。手記內的足跡採手記時區、日期須在旅程範圍內、`record_scope` 為 `trip`。時間為 `HH:mm` 或 `null`，心得最多 20,000 字。地點名稱 1–200 字，城市與類別最多 200 字，地址最多 1,000 字。 |
| Place | `{id,name,city,address}`；地點屬於單一使用者，只在明確提供 `place_id` 時重用，不依同名自動合併。 |

Trip 與 Event 的 `version` 從 1 開始。旅程本身或所含足跡變更時，Trip 版本會增加；Event 編輯時增加自己的版本。
每次到訪都有獨立 Event ID，未知時間保持 `null`，不補造時間。

建立手記表單預設將結束日期設為開始日隔日；開始日變動時會修正過早的結束日。當日來回仍可使用同一天，API 也會獨立驗證日期範圍。

提供 `place_id` 時，以本人既有 Place 欄位為準；未提供時建立新 Place。
編輯時未提供 `place_id` 也會建立新地點，不連動改寫其他事件共用的地點。Category 依擁有者及正規化名稱管理。

## 旅程與足跡端點

| 方法與路徑 | 請求與回應 |
| --- | --- |
| `GET /trips` | 回傳 `{items:Trip[]}`，依開始日期由新到舊，同分依 ID 排列。 |
| `POST /trips` | 提供 `name,start_date,end_date,timezone,description`，回傳 201 Trip。 |
| `GET /trips/{id}` | 回傳 `{trip:Trip,events:Event[],next_edges:[{from_id,to_id}]}`。 |
| `PUT /trips/{id}` | 提供建立欄位及 `version`，回傳 Trip；不得縮小日期範圍而排除既有足跡。 |
| `DELETE /trips/{id}?version=N` | 回傳 204，刪除本人的旅程、事件及 NEXT，保留可重用的 Place。 |
| `GET /places` | 回傳 `{items:Place[]}`。 |
| `POST /trips/{id}/events` | 提供 `place_id?:str\|null,place_name,city,address,category,date,time,notes`，回傳 201 Event。 |
| `GET /events` | 只列出本人的日常足跡。可傳入 `q,city,category,date_from,date_to,limit,offset`，回傳 `{items:Event[],next_offset:int\|null}`，預設每頁二十筆。 |
| `POST /events` | 建立日常足跡，回傳 201 Event。地點名稱必填，日期預設為所用時區的當日，時區預設 `Asia/Taipei`，分類預設「未分類」。其他事件欄位選填。 |
| `PUT /events/{id}` | 提供事件欄位及 `version`，回傳 Event。可為日常足跡指定 `timezone`。 |
| `POST /events/{id}/attach-trip` | 提供 `{trip_id,version,trip_version,before_event_id?}`，將日常足跡收進手記並回傳原 Event。選填的前置位置須為同日足跡 ID，省略時接在同日末尾。 |
| `DELETE /events/{id}?version=N` | 回傳 204。 |
| `PUT /trips/{id}/event-order` | 提供 `{version,event_ids:[...]}`，回傳與旅程詳情相同格式。須將所有事件 ID 各列一次，日期保持非遞減，同日內可調整順序。 |

新事件接在同日既有紀錄之後。修改日期時移到新日期群組末尾，日期未變時保留順序；精確時間不取代保存的事件順序。
事件新增、修改、刪除、重排與 NEXT 重建均在單一 Neo4j 交易完成，先鎖定旅程節點，再檢查版本及擁有者。

NEXT 只連接同一使用者、同一旅程內相鄰的紀錄，保留方向、可跨日、不形成循環。
前端時間軸依旅行狀態決定正序或倒序顯示，不改寫保存順序；`event-order` 保留為 API 契約，介面不提供往上／往下移按鈕。
資料使用實際的 User、Trip、Event、Place、Category 節點與關係，不放進登入用的 AuthRecord JSON，亦不需要 APOC。

收進手記時核對事件與手記的擁有者、版本、時區及日期範圍。版本衝突回傳 409，日期、時區或插入位置不合回傳 422。
同一交易更新事件、照片的旅程關聯、時間軸順序與 NEXT，保留事件及照片 ID。刪除手記只影響已收錄的足跡。

## 隨筆潤飾

`POST /writing/polish` 接受 `{text,kind}`，`kind` 為 `trip` 或 `event`，回傳 `{text}`。
原稿不得空白，最多 10,000 字；此操作需要登入與 CSRF，使用已設定的 AI 模型，不會直接建立或更新 Trip、Event。

前端先預覽結果，再由使用者決定是否套用；原文可復原，最後仍透過一般儲存端點保存。
輸入錯誤回傳 422，內容遭拒回傳 400，並行限制回傳 429，AI 無法使用回傳 503。潤飾失敗時保留原稿。

## 足跡草稿

手記內的「AI 幫我記」從文字產生待確認草稿，與 Conversation 分開；使用者確認前不寫入事件。
以下以 `/trips/{trip_id}/footprint-drafts` 為基底路徑，登入、CSRF 及擁有者規則相同；其他帳號的旅程或草稿回傳 404。

| 方法與路徑 | 請求 | 回應 |
| --- | --- | --- |
| `POST /` | `{record_date,text}` | 201 Draft |
| `GET /` | — | `{items:[Draft]}`，包含最近一份有效草稿，或空陣列 |
| `GET /{draft_id}` | — | Draft |
| `PATCH /{draft_id}` | `{version,record_date?,text?,items?}` | 更新後 Draft |
| `POST /{draft_id}/generate` | `{version,request_id}` | 202 Draft，輪詢草稿取得處理進度 |
| `POST /{draft_id}/commit` | `{version,trip_version,request_id}` | `{events,trip_version,draft}` |
| `DELETE /{draft_id}?version=N` | — | 204，捨棄草稿 |

`request_id` 使用 UUID。Draft 包含 `id,trip_id,version,status,record_date,text,items,issues,trip_version,error,request_id` 與建立、更新時間。
狀態為 `editing`、`queued`、`running`、`ready`、`failed` 或 `committed`。`issues` 對應項目 ID 的缺漏或無效欄位訊息，不能取代確認時的伺服器驗證。

每個項目包含 `id,selected,place_name,date,time,city,address,category,notes`，陣列順序即預覽順序。
草稿中的地點、日期與時間可暫為 `null`；勾選項目在確認前須符合一般 Event 建立規則。未勾選的不完整項目不阻擋有效項目加入。

記錄日期須在旅程範圍內，描述最多 10,000 字，生成最多 20 個項目。
編輯時可保存空描述，但生成要求非空文字。未指定日期時使用記錄日期，「今天／昨天」等相對日期以旅程時區的記錄日期為基準。
未知時間保持 `null`，無法分類時使用「其他」。

生成請求與狀態先保存，再於背景處理，不依賴瀏覽器連線。每位使用者最多一個有效助手工作，預設全站同時兩個，可由伺服器調整。
排隊及中斷的工作可在啟動後恢復；生成失敗保留先前內容。手動重試可能再次呼叫外部模型，捨棄後晚到的結果不會恢復草稿。

確認時核對勾選內容、草稿版本與最新 Trip 版本，衝突回傳 409 並保留草稿供檢查。
選定事件、新 Place、Category、NEXT 與確認結果在單一交易保存，Trip 版本增加一次。
同日既有事件保持順序，新事件按預覽順序接在其後；重送已確認草稿會回傳原結果，不會再建立一批事件。助手不修改既有事件。
