# 檢索評估與重現

[文件索引](README.md)

本專案比較 BM25、E5、BM25＋E5 RRF 與查詢導向 NEXT。評估與 Web App 共用檢索服務，使用相同事件表示及候選範圍。若要在介面試問功能，可使用另外提供的[示範資料與功能試問](DEMO_GUIDE.md)。

## 繁體中文模糊回憶題庫

[合成題庫](../examples/demo/fuzzy-recall.json)包含 40 位虛構旅人、320 本手記、3,840 筆足跡和 4,000 題。按旅人切成試跑、開發和測試三組，各有 5、5、30 位旅人。測試組包含以下 3,000 題。

| 類型 | 題數 | 線索 |
| --- | ---: | --- |
| 語意、時空、前後站 | 各 800 | 每類 200 個不同目標，各有四種問法 |
| 多個答案、需澄清、無證據 | 各 200 | 分別檢查找全紀錄、辨別方向歧義和處理無資料問題 |

四種問法為較精確、口語、無地名和弱線索。較精確版也遮住答案的店名，關係題可以提到錨點。無地名版保留情境細節，弱線索版進一步保留較少或較間接的資訊。每個單一答案案例還有一筆干擾足跡，例如同城市同類別，或位於錨點相反方向。事件內容、題目與標記是虛構的，可在獨立環境重跑。

題庫先建立事件與答案，再撰寫或以模型改寫問題。驗證包括帳號隔離、答案範圍、相鄰方向、題目重複和地名洩漏。另以模型不看標記及排序結果抽核 300 題，296 題的判斷與標記一致。四題分歧都涉及「之後」是否足以確定目的地。這是合成情境的品質抽查，結果仍受問題模板及答案判定方式限制。

### 繁中題庫摘要

| 方法 | MRR@50 | 首筆命中 | 前五筆命中 | 勝過干擾足跡 |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 0.586 | 50.0% | 68.9% | 78.8% |
| E5 | 0.624 | 53.8% | 73.2% | 80.8% |
| RRF | 0.651 | 57.5% | 74.8% | 82.3% |
| 查詢導向 NEXT | 0.761 | 69.7% | 82.8% | 83.6% |

上表只計 2,400 題單一答案題。前後站 800 題中，RRF、保留錨點融合但停用邊、完整 NEXT 的 MRR@50 依序為 0.160、0.287、0.578。完整 NEXT 相較停用邊提升 0.291，95% 信賴區間為 0.260 至 0.323，以旅人為單位進行配對 bootstrap。無地名前後站題的 MRR@50 為 0.273，弱線索題為 0.298，清楚提到錨點的版本為 0.993。完整 NEXT 在語意類的 MRR@50 為 0.806，RRF 為 0.890。

多答案題的前五筆召回率由完整 NEXT 達到 97.3%。完整 NEXT 對標記需澄清的 200 題觸發 139 次澄清。無證據題仍可能有相似候選，搜尋分數只能提供線索，回答是否有證據需由對話流程核對。

另從同一測試組抽出 600 題評估助理，其中 120 題各重跑兩次。440 題可答問題中，377 題送齊正解證據，364 題通過地點名稱與引用 ID 的自動初核。80 題無證據問題均表示證據不足，80 題應澄清的問題有 56 題先要求澄清，有 10 題直接作答。120 題重複實驗中，112 題三次的回覆狀態及引用集合相同。初核只量測預期地點與來源，無法驗證每句回覆的內容。

以獨立 Neo4j 對照 60 題，近似索引與精確向量的前五筆重疊率在 E5、RRF、NEXT 依序是 100%、100%、99.7%。此結果的候選範圍是合成旅人各自的少量足跡。

### 重跑方式

先完成[本機開發環境](GETTING_STARTED.md)及模型下載，再從專案根目錄執行。評估輸出位於被 Git 忽略的 `data/`。

```powershell
.\.venv\Scripts\python.exe main.py download-model
.\.venv\Scripts\python.exe -m experiments.fuzzy_evaluate --input examples/demo/fuzzy-recall.json --output data/fuzzy-evaluation --cache data/fuzzy-evaluation-embeddings.npz --latency-per-stratum 5
```

固定題庫可直接重跑，無須模型 API Key。精確向量比較使用記憶體資料庫，`test-summary.json` 彙整各方法、各類型、配對差值和方向解析漏斗。測試分組為預設，可用 `--split pilot` 或 `--split dev` 檢查流程。

若要比較 Neo4j 的近似向量結果，另外啟動空的本機評估資料庫，設定 `EVAL_NEO4J_URI` 和 `EVAL_NEO4J_PASSWORD`，執行：

```powershell
.\.venv\Scripts\python.exe -m experiments.fuzzy_ann --input examples/demo/fuzzy-recall.json --ranking data/fuzzy-evaluation/test-ranking.jsonl --cache data/fuzzy-evaluation-embeddings.npz --output data/fuzzy-ann.json
```

若要測試完整 AI 助理，可從同一題庫執行。先設定 `.env` 內的模型和 API Key，只有加上 `--run-llm` 才會呼叫模型並產生費用。逐題輸出會保存在本機供檢查。

```powershell
.\.venv\Scripts\python.exe -m experiments.fuzzy_assistant --corpus examples/demo/fuzzy-recall.json --output data/fuzzy-assistant --run-llm
```

### 方法參考

題庫採用固定情境、多種線索，以及區分可答、需澄清與無證據的設計。[LoCoMo](https://aclanthology.org/2024.acl-long.747/) · [LongMemEval](https://arxiv.org/abs/2410.10813) · [Promptagator](https://arxiv.org/abs/2209.11755)

## 東京公開資料對照

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
