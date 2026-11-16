import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  requestCode,
  verifyCode,
  getMe,
  logout,
  getCsrfToken,
  setCsrfToken,
  ApiError
} from '../auth'

describe('Auth API Client', () => {
  beforeEach(() => {
    setCsrfToken(null)
    vi.restoreAllMocks()
  })

  it('manages in-memory CSRF token without touching localStorage', () => {
    expect(getCsrfToken()).toBeNull()
    setCsrfToken('test-csrf-token')
    expect(getCsrfToken()).toBe('test-csrf-token')
    setCsrfToken(null)
    expect(getCsrfToken()).toBeNull()
  })

  it('requestCode sends POST to /api/v1/auth/request-code with credentials include', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ message: '驗證碼已寄出', retry_after: 60 })
    })
    globalThis.fetch = fetchMock

    const res = await requestCode('traveler@example.com')
    expect(res.retry_after).toBe(60)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/request-code', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ email: 'traveler@example.com' })
    }))
  })

  it('verifyCode sets in-memory CSRF token on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        user: { id: 'u123', email: 'traveler@example.com' },
        csrf_token: 'csrf-secret-123'
      })
    })
    globalThis.fetch = fetchMock

    const res = await verifyCode('traveler@example.com', '123456')
    expect(res.user.email).toBe('traveler@example.com')
    expect(getCsrfToken()).toBe('csrf-secret-123')
  })

  it('verifyCode throws ApiError on 401 with Traditional Chinese detail', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: '驗證碼錯誤或已過期' })
    })
    globalThis.fetch = fetchMock

    await expect(verifyCode('traveler@example.com', '999999')).rejects.toThrow(ApiError)
  })

  it('getMe returns user and saves csrf token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        user: { id: 'u456', email: 'memories@example.com' },
        csrf_token: 'csrf-session-token'
      })
    })
    globalThis.fetch = fetchMock

    const res = await getMe()
    expect(res?.user.id).toBe('u456')
    expect(getCsrfToken()).toBe('csrf-session-token')
  })

  it('getMe returns null on 401 without throwing error', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: '未登入' })
    })
    globalThis.fetch = fetchMock

    const res = await getMe()
    expect(res).toBeNull()
    expect(getCsrfToken()).toBeNull()
  })

  it('preserves csrf token when logout fails so the user can retry', async () => {
    setCsrfToken('retry-token')
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network unavailable'))
    await expect(logout()).rejects.toThrow('network unavailable')
    expect(getCsrfToken()).toBe('retry-token')
  })

  it('logout includes X-CSRF-Token and clears memory token', async () => {
    setCsrfToken('active-token-777')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers()
    })
    globalThis.fetch = fetchMock

    await logout()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', expect.objectContaining({
      method: 'POST',
      credentials: 'include'
    }))
    const lastCallHeaders = fetchMock.mock.calls[0][1].headers as Headers
    expect(lastCallHeaders.get('X-CSRF-Token')).toBe('active-token-777')
    expect(getCsrfToken()).toBeNull()
  })
})
