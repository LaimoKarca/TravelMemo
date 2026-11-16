# 備份、還原與版本回退

## 備份包含什麼

Neo4j 的 neo4j-data 資料卷保存使用者、登入工作階段、旅程、事件、對話、用量及向量。
`deploy/backup.ps1` 暫停 API 與資料庫，建立包含 Neo4j system/auth 資料的離線 tar.gz，
寫入版本、映像 ID、節點數與 SHA-256 manifest，然後恢復服務。
這段時間網站無法正常讀寫，請安排維護時段。

另行安全備份私人 `.env`、`.env.tunnel` 與服務商復原資訊；資料封存不包含它們。
模型權重可從固定 revision 重下載，不必與私人資料一起備份。
備份有完整私人資料及工作階段，請限制讀取權限，並存到主機以外的安全位置。

## 建立備份

從目前部署原始碼根目錄執行，RELEASE_ID 使用正在運行的版本標籤：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deploy/backup.ps1 `
  -EnvFile 'D:\Services\TravelMemo\.env' `
  -ReleaseId '<目前版本標籤>' `
  -BackupDirectory 'D:\Services\TravelMemo\backups'
```

ExecutionPolicy 只對本次 PowerShell 程序生效，不修改主機的永久原則；若機構政策禁止執行，請遵守該政策。
腳本使用本專案正式 Compose 的容器名稱。不是同一部署結構時，先調整腳本再使用。
備份失敗時確認服務已恢復；不要只因存在 tar.gz 就當作成功，應同時取得 manifest 並做還原演練。

## 在隔離環境驗證還原

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File deploy/restore-drill.ps1 `
  -BackupPath 'D:\Services\TravelMemo\backups\<備份目錄>'
```

腳本驗證雜湊，建立帶隨機識別碼的新資料卷與 Docker internal 網路，還原後啟動同版 Neo4j，
核對節點數，成功輸出 `RESTORE_DRILL_OK`，最後清理本次產生的資源。
不會覆寫正式卷，也不對外發布 port。為了在隔離環境查驗，測試容器會關閉 Neo4j 認證。
不要把這個設定用於正式服務。

不要將測試資料庫設為 network=none：本次環境的 Neo4j 2026.10.2 在此模式無法啟動。
internal 網路提供啟動所需的網路介面，同時不提供外部路由。
跨主機還原前須先取得 manifest 記錄的同版映像，核對映像 ID，並調整備份路徑。
節點數只能作基本完整性檢查；重要資料還應登入核對旅程、事件順序、對話與來源。
驗證指定測試旅程時，可加上 `-ExpectedTripId '<旅程 UUID>' -ExpectedEventCount 2`，
腳本也會核對該旅程的事件數與 NEXT 連線數。

## 正式災難還原

1. 保留目前故障資料卷與容器資訊，停止 API 與 Neo4j，避免還原期間有寫入。
2. 核對備份 SHA-256、版本與私人設定，先執行隔離演練。
3. 使用**新資料卷**還原封存（與 restore-drill.ps1 的 tar 還原及權限步驟相同）。
4. 在正式 Compose 的 neo4j-data 定義加入 `external: true` 與 `name: <新還原資料卷名稱>`，
   保留原卷供回退；移除與 external 衝突的其他卷建立設定。
5. 使用備份對應版本與私人 `.env` 啟動，確認健康檢查、登入與實際旅程操作。
6. 如需失效舊登入工作階段，另行更換 SESSION_SECRET 並重建 API 容器。

正式資料卷切換屬於人工維護操作，請先核對卷名與備份，勿把演練腳本改成覆寫原卷的捷徑。

## 應用版本回退

保留上一版來源目錄、映像標籤與升級前備份。切回上一版原始碼目錄，將 RELEASE_ID 設回原標籤，
用相同私人設定執行 Compose up。若資料結構不相容，僅回退映像不足，需從升級前備份還原到新卷。
不要直接讓舊程式操作尚未確認相容的新 schema。

**不要使用 `docker compose down -v` 或 Docker volume prune 清理正式部署。**
