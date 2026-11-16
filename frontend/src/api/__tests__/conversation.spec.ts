import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  sendMessage,
  getUsage
} from '../conversation'
import { setCsrfToken } from '../auth'

describe('Conversation API Client', () => {
  beforeEach(() => {
    setCsrfToken(null)
    vi.restoreAllMocks()
  })

  it('listConversations sends GET /api/v1/conversations', async () => {
    const mockList = {
      items: [
        { id: 'c-1', title: '京都行程規劃', created_at: '2026-11-20T10:00:00Z' }
      ]
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockList
    })
    globalThis.fetch = fetchMock

    const res = await listConversations()
    expect(res.items).toHaveLength(1)
    expect(res.items[0].id).toBe('c-1')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations', expect.objectContaining({
      method: 'GET'
    }))
  })

  it('createConversation sends POST /api/v1/conversations with title', async () => {
    setCsrfToken('csrf-conv')
    const mockCreated = { id: 'c-2', title: '台東美食建議', created_at: '2026-11-20T11:00:00Z' }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockCreated
    })
    globalThis.fetch = fetchMock

    const res = await createConversation({ title: '台東美食建議' })
    expect(res.id).toBe('c-2')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ title: '台東美食建議' })
    }))
  })

  it('deleteConversation sends DELETE /api/v1/conversations/:id', async () => {
    setCsrfToken('csrf-conv-del')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers()
    })
    globalThis.fetch = fetchMock

    await deleteConversation('c-1')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations/c-1', expect.objectContaining({
      method: 'DELETE'
    }))
  })

  it('listMessages sends GET /api/v1/conversations/:id/messages', async () => {
    const mockMessages = {
      items: [
        {
          id: 'm-1',
          role: 'user',
          content: '我上次去京都吃了什麼？',
          status: 'answered',
          citations: [],
          created_at: '2026-11-20T12:00:00Z'
        },
        {
          id: 'm-2',
          role: 'assistant',
          content: '您在 2026-11-20 造訪了錦市場午餐。',
          status: 'answered',
          citations: [
            {
              event_id: 'e-2',
              trip_id: 't-1',
              date: '2026-11-20',
              place_name: '錦市場午餐',
              version: 1,
              state: 'current'
            }
          ],
          created_at: '2026-11-20T12:00:02Z'
        }
      ]
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockMessages
    })
    globalThis.fetch = fetchMock

    const res = await listMessages('c-1')
    expect(res.items).toHaveLength(2)
    expect(res.items[1].citations[0].place_name).toBe('錦市場午餐')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations/c-1/messages', expect.objectContaining({
      method: 'GET'
    }))
  })

  it('sendMessage sends POST /api/v1/conversations/:id/messages', async () => {
    setCsrfToken('csrf-msg')
    const mockReply = {
      id: 'm-3',
      role: 'assistant',
      content: '查無足跡紀錄。',
      status: 'insufficient_evidence',
      citations: [],
      created_at: '2026-11-20T13:00:00Z'
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockReply
    })
    globalThis.fetch = fetchMock

    const res = await sendMessage('c-1', { content: '下週天氣如何？' })
    expect(res.status).toBe('insufficient_evidence')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/conversations/c-1/messages', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ content: '下週天氣如何？' })
    }))
  })

  it('getUsage sends GET /api/v1/usage/me', async () => {
    const mockUsage = {
      date: '2026-11-20',
      requests: 3,
      input_tokens: 450,
      output_tokens: 180,
      daily_limit: 50,
      model: 'gpt-6-luna'
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockUsage
    })
    globalThis.fetch = fetchMock

    const res = await getUsage()
    expect(res.requests).toBe(3)
    expect(res.daily_limit).toBe(50)
    expect(res.model).toBe('gpt-6-luna')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/usage/me', expect.objectContaining({
      method: 'GET'
    }))
  })
})
