import type {
  RequestCodeResponse,
  VerifyCodeResponse,
  HealthLiveResponse,
  HealthReadyResponse,
  ApiErrorDetail
} from '../types/auth'

const BASE_URL = '/api/v1'

// Keep CSRF token in memory only. Never persist to localStorage or sessionStorage.
let memoryCsrfToken: string | null = null
let onUnauthorizedHandler: (() => void) | null = null

export function getCsrfToken(): string | null {
  return memoryCsrfToken
}

export function setCsrfToken(token: string | null): void {
  memoryCsrfToken = token
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorizedHandler = handler
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')

  if (options.body && !(options.body instanceof FormData)) {
    if (options.body instanceof Blob) {
      if (!headers.has('Content-Type')) {
        headers.set('Content-Type', (options.body as Blob).type || 'application/octet-stream')
      }
    } else if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
  }

  // Include in-memory CSRF token if present and not already provided
  if (memoryCsrfToken && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', memoryCsrfToken)
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: 'include'
  })

  if (response.status === 204) {
    return undefined as unknown as T
  }

  let data: any = null
  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    try {
      data = await response.json()
    } catch {
      data = null
    }
  }

  if (!response.ok) {
    const isAuthEndpoint =
      path.startsWith('/auth/verify-code') ||
      path.startsWith('/auth/request-code') ||
      path === '/auth/me'

    if (response.status === 401 && !isAuthEndpoint) {
      setCsrfToken(null)
      if (onUnauthorizedHandler) {
        onUnauthorizedHandler()
      }
    }

    let errorMsg = '發生未預期的伺服器錯誤，請稍後再試。'
    if (data && typeof data.detail === 'string') {
      errorMsg = data.detail
    } else if (response.status === 401) {
      errorMsg = '驗證碼錯誤或已過期，請重新輸入或索取驗證碼。'
    } else if (response.status === 404) {
      errorMsg = '找不到指定的旅程或行程資料。'
    } else if (response.status === 409) {
      errorMsg = '資料已被其他操作更新（版本衝突），請重新整理以取得最新版本。'
    } else if (response.status === 422) {
      errorMsg = '資料驗證失敗，請檢查欄位格式與時間範圍。'
    } else if (response.status === 429) {
      errorMsg = '請求過於頻繁或已達用量上限，請稍候再試。'
    } else if (response.status === 503) {
      errorMsg = '郵件或伺服器服務暫時不可用，請稍候再試。'
    }

    throw new ApiError(response.status, errorMsg)
  }

  return data as T
}

export async function requestCode(email: string): Promise<RequestCodeResponse> {
  return request<RequestCodeResponse>('/auth/request-code', {
    method: 'POST',
    body: JSON.stringify({ email })
  })
}

export async function verifyCode(email: string, code: string): Promise<VerifyCodeResponse> {
  const result = await request<VerifyCodeResponse>('/auth/verify-code', {
    method: 'POST',
    body: JSON.stringify({ email, code })
  })
  if (result && result.csrf_token) {
    setCsrfToken(result.csrf_token)
  }
  return result
}

export async function getMe(): Promise<VerifyCodeResponse | null> {
  try {
    const result = await request<VerifyCodeResponse>('/auth/me', {
      method: 'GET'
    })
    if (result && result.csrf_token) {
      setCsrfToken(result.csrf_token)
    }
    return result
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      setCsrfToken(null)
      return null
    }
    throw err
  }
}

export async function logout(): Promise<void> {
  await request<void>('/auth/logout', { method: 'POST' })
  setCsrfToken(null)
}

export async function checkLiveHealth(): Promise<HealthLiveResponse> {
  return request<HealthLiveResponse>('/health/live', {
    method: 'GET'
  })
}

export async function checkReadyHealth(): Promise<HealthReadyResponse> {
  return request<HealthReadyResponse>('/health/ready', {
    method: 'GET'
  })
}
