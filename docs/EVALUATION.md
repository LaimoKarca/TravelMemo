# 檢索評估與重現

[文件索引](README.md)

本專案比較 BM25、E5、BM25+E5 RRF 與查詢導向 NEXT 四種方法，
使用正式檢索服務的 method 參數進行消融，HTTP 搜尋介面仍使用完整流程。

若要在介面上試問功能，請使用[示範資料與功能試問](DEMO_GUIDE.md)。該指南使用原創繁中情境，預期依據供人工核對，不是本文件的研究資料或成績。

## 固定輸入

- 來源：[fuzzy-travel-recall-benchmark](https://github.com/LaimoKarca/fuzzy-travel-recall-benchmark)。
- 事件：`data/prepared/stage_04_retrieval/common/tokyo_event_documents.csv`。
- 查詢：`data/prepared/stage_03_queries/tokyo_recall_queries_main.csv`。
- 向量模型：`multilingual-e5-small`，384 維正規化。

評估程序下載公開資料集並核對資料完整性。
事件只使用本身的日期、時間、地點、城市、類別與地址，不嵌入相鄰事件或目標答案。
原始查詢文字與擁有者會進入檢索；target ID、cue 欄位只用於標記，不送入排序或方向解析。
不同方法使用相同事件與表示，不直接沿用舊實驗的排名或分數。

## 執行精確向量比較

從專案根目錄、已安裝依賴的虛擬環境執行：

```powershell
.\.venv\Scripts\python.exe main.py download-model
.\.venv\Scripts\python.exe main.py evaluate
```

首次下載與編碼需要網路及時間。資料、公開事件向量快取與結果都放在被 Git 排除的 `data/`。
程式使用忽略私人 `.env` 的評估設定與記憶體資料庫，不會匯入朋友的正式旅程。
快取只重用 passage 編碼；查詢仍重新編碼，延遲包含查詢編碼及排序。

輸出預設為 `data/evaluation/results.json` 與 `report.md`，包含：

- 四方法 MRR@50、Success@1、Success@5、p50/p95 延遲。
- 各查詢類型與關係查詢結果，以及要求澄清的次數。
- 測試環境設定、資料集名稱、模型與套件版本、參數。

需澄清或找不到目標都計為未命中，保留在分母。MRR 限於前50筆，不能與完整排名的 MRR 混稱。
產品將含糊的「之後」先澄清，與舊 benchmark 的 relational_after 標記不一定語意相同，
因此必須連同澄清次數與查詢原文解讀，不保證圖遍歷在所有資料上優於基線。
延遲為單次查詢量測基準，未代表多使用者壓力測試或其他硬體效能。

可用 `--limit-queries 20 --output data/evaluation-smoke` 先檢查流程；正式報告不可把此子集當成全資料結果。

## 明確相鄰線索的獨立診斷

原始 relational_after 查詢沒有明說「緊接著」，會觸發產品的澄清規則。
為了另測方向性排序，可以建立獨立的107筆診斷：只把原查詢的 after 改為 immediately after，
先驗證原標記確實對應既有 NEXT，事件、目標標記與其他欄位維持不變。
這些查詢**不是原始 benchmark**，結果不得混入上面的320筆原始查詢成績。

```powershell
.\.venv\Scripts\python.exe main.py evaluate --explicit-adjacency --output data/evaluation-adjacency
```

四種方法都接收相同的新查詢文字；標記仍不送進排序或方向解析。
輸出 manifest 會記錄 query_variant 與相鄰標記驗證數。

## Neo4j ANN 對照

另開**空的、獨立的** Neo4j 2026.10.2 資料庫，不能使用既有的應用資料庫。
透過程序環境設定 `EVAL_NEO4J_URI` 與 `EVAL_NEO4J_PASSWORD`，再執行：

```powershell
.\.venv\Scripts\python.exe main.py evaluate --ann --output data/evaluation-ann
```

ANN 程序會拒絕非空資料庫，在空資料庫中載入相同事件與圖關係，使用同一批 passage 編碼，
分開報告 Neo4j ANN 的排名與延遲，以及與精確向量前五筆的重疊率。
完成後保留該評估資料庫供檢查；重新執行須建立另一個空的評估資料卷。
評估資料庫可只綁定主機 loopback port，不需 Cloudflare 路由。
