# 檢索評估與重現

本專案比較 BM25、E5、BM25+E5 RRF 與查詢導向 NEXT 四種方法，
使用正式檢索服務的 method 參數進行消融，HTTP 搜尋介面仍使用完整流程。

## 固定輸入

- 來源：[fuzzy-travel-recall-benchmark](https://github.com/LaimoKarca/fuzzy-travel-recall-benchmark)。
- commit：`cadb2eca2a1e09475a1851545e12de99779b8a53`。
- 事件：`data/prepared/stage_04_retrieval/common/tokyo_event_documents.csv`。
- 查詢：`data/prepared/stage_03_queries/tokyo_recall_queries_main.csv`。
- E5 revision：`614241f622f53c4eeff9890bdc4f31cfecc418b3`，384維正規化。

評估程序下載固定 commit 的公開 CSV 並記錄 SHA-256。
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
- 應用 commit、工作目錄是否有未提交變更、資料雜湊、模型與套件版本、參數。

需澄清或找不到目標都計為未命中，保留在分母。MRR 限於前50筆，不能與完整排名的 MRR 混稱。
產品將含糊的「之後」先澄清，與舊 benchmark 的 relational_after 標記不一定語意相同，
因此必須連同澄清次數與查詢原文解讀，不保證圖遍歷在所有資料上優於基線。
延遲是此主機的單次查詢量測，未代表多使用者壓力測試或其他主機效能。

可用 `--limit-queries 20 --output data/evaluation-smoke` 先檢查流程；正式報告不可把此子集當成全資料結果。

## Neo4j ANN 對照

另開**空的、獨立的** Neo4j 2026.10.2 資料庫，不能使用朋友或自己的應用資料庫。
透過程序環境設定 `EVAL_NEO4J_URI` 與 `EVAL_NEO4J_PASSWORD`，再執行：

```powershell
.\.venv\Scripts\python.exe main.py evaluate --ann --output data/evaluation-ann
```

ANN 程序會拒絕非空資料庫，在空資料庫中載入相同事件與圖關係，使用同一批 passage 編碼，
分開報告 Neo4j ANN 的排名與延遲，以及與精確向量前五筆的重疊率。
完成後保留該評估資料庫供檢查；重新執行須建立另一個空的評估資料卷。
評估資料庫可只綁定主機 loopback port，不需 Cloudflare 路由。
