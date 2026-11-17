# 登入與健康檢查 API

所有介面位於 `/api/v1`，使用同網域 Cookie 工作階段。錯誤格式為 `{ "detail": "錯誤說明" }`。

| 方法與路徑 | 請求與回應 |
| --- | --- |
| POST `/auth/request-code` | `{email}`，回傳 202 `{message,retry_after}`；無論資格皆使用相同訊息，寄件失敗 503、過於頻繁 429 |
| POST `/auth/verify-code` | `{email,code}`，成功回傳 `{user:{id,email},csrf_token}` 並設定 HttpOnly Cookie；驗證碼無效或過期 401 |
| GET `/auth/me` | 回傳目前使用者與 CSRF token；未登入 401 |
| POST `/auth/logout` | 需 `X-CSRF-Token`，回傳 204 並撤銷工作階段 |
| GET `/health/live` | 存活狀態 `{status:"ok"}` |
| GET `/health/ready` | 依賴服務狀態，回傳 200 或 503；不會為了檢查而寄信 |

正式環境啟用 Secure、HttpOnly、SameSite Cookie；CSRF token 保存在前端記憶體。
允許名單、驗證碼期限及 SMTP 設定見 [操作文件](OPERATIONS.md)。
