export interface User {
  id: string | number
  email: string
}

export interface AuthSession {
  user: User
  csrf_token: string
}

export interface RequestCodeResponse {
  message: string
  retry_after?: number
}

export interface VerifyCodeResponse {
  user: User
  csrf_token: string
}

export interface HealthLiveResponse {
  status: string
}

export interface HealthReadyResponse {
  status: 'ready' | 'not_ready' | string
  database: boolean
  smtp_configured: boolean
}

export interface ApiErrorDetail {
  detail?: string
}
