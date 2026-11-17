# 檢索與對話 API

本文補充 [SPEC](SPEC.md) 的實際介面。開發環境可從 /api/docs 查閱 FastAPI OpenAPI；
正式部署停用 Swagger。所有介面位於 `/api/v1`，使用同網域 Cookie 工作階段。

## 認證與錯誤

擁有者從工作階段決定，不接受前端指定。POST、PUT、DELETE 使用 X-CSRF-Token；
登入寄碼及驗碼按既有登入契約處理。跨帳號資源404，登入失效401，CSRF失敗403，
編輯版本衝突409，輸入無效422，並行或頻率限制429，資料庫不可用503。

Python 入口固定單一 API process，模型共用並限制編碼並行；不要另以多 worker 啟動。

## 搜尋

`POST /search`：

```json
{
  "query": "清水寺的下一站",
  "trip_id": "optional-trip-id",
  "date_from": "2026-11-01",
  "date_to": "2026-11-03",
  "city": "京都",
  "category": "咖啡",
  "limit": 10
}
```

除 query 外皆可省略；limit 為1至50。日期必須有效且起點不晚於終點，空白查詢不接受。

回應為 `{items, clarification, vector_status}`：

- items 每筆包含既有 Event 欄位、score、reasons，以及選填 relation。
- relation 為 `{anchor_id,direction,anchor_date,target_date}`，direction 是 next 或 prev。
- clarification 非空時，需先確認使用者的相鄰語意。
- vector_status 顯示向量可用性；無法使用模型時仍回傳 BM25 結果。

`GET /events/{id}` 取得目前本人事件，額外提供 trip_name。前端來源視窗必須重新讀取，
不可將先前搜尋快照當成目前紀錄。來源跳轉使用 trip_id 與 event_id。

## 對話

| 方法與路徑 | 輸入 | 回應 |
| --- | --- | --- |
| POST /conversations | 選填 {title} | {id,title,created_at}，201 |
| GET /conversations | 無 | {items:[對話摘要]} |
| DELETE /conversations/{id} | 無 | 204 |
| GET /conversations/{id}/messages | 無 | {items:[訊息]} |
| POST /conversations/{id}/messages | {content,photo_ids?}，文字或圖片至少一項 | 助理訊息 |

訊息結構為 `{id,role,content,status,citations,created_at}`。
另提供 `photos`、`photo_citations` 與 `answer_scope`，舊訊息預設為空圖片清單及 memory。
`answer_scope` 是 image、memory 或 mixed；圖片描述可引用照片，私人經歷仍須事件引用。
role 是 user 或 assistant；status 是 answered、insufficient_evidence、needs_clarification 或 unavailable。
citations 每筆為 `{event_id,trip_id,date,place_name,version,state}`，
state 是 current、changed 或 deleted。關係引用可額外保存 relation 證據；
讀歷史會重新核對事件版本及原本的相鄰關係，行程重排也可標示已變更。

回答完成前必須重新驗證引用在本次證據內、仍屬本人且版本未變；
關係問題也重新驗證實際 NEXT／反向鄰接。任一引用無效時不保留原本有把握的回答。
指代追問以先前引用的獨立 Event ID 鎖定錨點，不能只依同名地點混合多次到訪。

不設每日次數上限。安全分類拒絕或並行名額不足的要求不新增訊息，處理結束時釋放名額。
首則問題自動產生標題，較舊內容採滾動摘要；詳見 [後端處理流程](BACKEND.md)。
OpenAI 使用 Responses 結構化輸出、store=false；
回覆完成驗證後才顯示，不串流未驗證內容。

## 索引及內部評估介面

SearchService 提供 initialize、run_worker、process_pending、index_status、rebuild。
search 的 internal method 參數可指定 bm25/e5/rrf/next 供評估，預設 next；
internal anchor_id 只供已驗證的對話指代，不對 HTTP 呼叫者開放。

向量寫回及失敗標記都核對 owner_id 與事件版本；模型版本不相容的向量排除並重新排入。
失敗工作持久化，依冷卻時間重試，優先處理新待辦，避免單一失敗批次阻擋後續事件。
ANN 內先套用擁有者與有效索引狀態，以及支援的旅程／日期／城市／類別篩選，再取 Top-K。

## 前端狀態

非同步載入須綁定請求識別碼與目前資源；切換、刪除或重設後不得讓過期回應覆寫畫面。
拒絕的訊息必須移除樂觀顯示並保留草稿。401 會清除過期工作階段，
但驗證碼錯誤的401仍留在驗碼表單。頁面支援窄螢幕、可見焦點與鍵盤分頁切換。
