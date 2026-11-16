# 回憶搜尋與 AI 對話

## 回憶搜尋

登入後開啟「回憶搜尋」，輸入記得的地點、食物、心得或行程線索。
可選擇旅程、日期範圍、城市與類別縮小範圍。結果卡片會列出事件日期、命中原因與關係證據，
點「檢視詳情」可查看目前紀錄，或跳至原旅程修訂。

例子：

- 「吃到很濃郁抹茶甜點的店」：以詞彙與語意搜尋紀錄。
- 「清水寺的下一站」：找出錨點，再沿紀錄中的 NEXT 關係尋找直接相鄰事件。
- 「咖啡店的上一站」：沿反向 NEXT 尋找前一筆紀錄。
- 「去過清水寺之後」：若無法確認是否指緊接下一站，先澄清。

時間未知時不會補造時間；跨日相鄰會保留兩端日期。
NEXT 只能證明「紀錄中的下一站」，不能保證途中沒有未記錄的活動。

## 索引生命週期

事件保存後即可從時間軸與 BM25 使用。向量由同一 API process 的背景工作編碼，
因此新事件可能先以詞彙命中，稍後才有語意命中。
更新會使舊向量失效；寫回向量前核對事件版本，刪除或連續編輯不應被舊工作覆蓋。

初次安裝時，先從專案根目錄執行：

```powershell
.\.venv\Scripts\python.exe main.py download-model
.\.venv\Scripts\python.exe main.py rebuild-index
```

正式容器使用：

```powershell
docker exec travelmemo-api-1 python main.py download-model
docker exec travelmemo-api-1 python main.py rebuild-index
```

正式模型目錄位於持久化的 model-data 資料卷。一般版本更新不需要重新下載。
模型固定 revision、384 維，使用 query:/passage: 前綴及正規化；長筆記完整保留，
只有 E5 編碼受輸入長度限制，BM25 仍搜尋完整內容。

若無法使用向量，先確認模型下載、API 日誌及 Neo4j 索引狀態。
日誌不應包含完整私人筆記；失敗修復後可執行 rebuild-index。
修改模型 revision 後也必須重建，不能混用不同模型的向量。

## AI 對話

開啟「AI 對話」，建立對話並輸入問題。系統先檢索本人資料，再將必要證據與有限歷史送往 OpenAI。
回覆狀態包含「已回答」、「證據不足」、「需要澄清」與「服務暫時不可用」。

- 回答的來源卡片可查看日期與事件，並跳回原旅程。
- 「那家店／那天」等追問會參照前次引用；有多個可能對象時先澄清。
- 來源修改或刪除後，歷史引用會標示已變更或已刪除；後續問題重新取得資料。
- OpenAI 未設定或失敗時，旅程管理與一般搜尋仍可使用。

由站台擁有者在私人 `.env` 設定 `OPENAI_API_KEY`，使用伺服器共用 Key。
預設 `OPENAI_MODEL=gpt-6-luna`，不自動改用其他模型。
每日用量以 UTC 換日，預設每人50則、每人同時1筆、全站同時2筆；設定、限制與用量顯示於對話頁。
進入處理的請求即計入次數，即使 API 失敗仍保留該次記錄；被429拒絕的要求不新增對話訊息。

請求使用 Responses API 結構化輸出及 `store=false`，引用 ID 由後端重新驗證。
這個設定控制 API 回應儲存，並不代表服務商不保留任何資料。
參見 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
及 [資料控制說明](https://developers.openai.com/api/docs/guides/your-data)。

照片辨識、分享共編、地圖規劃與個人 API Key 不在本版範圍。
