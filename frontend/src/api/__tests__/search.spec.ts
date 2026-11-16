import { describe, it, expect, beforeEach, vi } from 'vitest'
import { searchRecall, getEvent } from '../search'
import { setCsrfToken } from '../auth'

describe('Search API Client', () => {
  beforeEach(() => {
    setCsrfToken(null)
    vi.restoreAllMocks()
  })

  it('searchRecall sends POST /api/v1/search with contract payload', async () => {
    setCsrfToken('mock-search-token')
    const mockResponse = {
      items: [
        {
          event: {
            id: 'e-1',
            trip_id: 't-1',
            place_id: 'p-1',
            place_name: '清水寺',
            city: '京都市',
            address: '東山區清水1丁目294',
            category: '景點',
            date: '2026-11-20',
            time: '09:00',
            notes: '晨光古剎',
            position: 0,
            version: 1,
            trip_name: '京都秋楓紀行'
          },
          score: 0.95,
          reasons: ['文字符合「清水寺」', '類別相符'],
          relation: {
            anchor_id: 'e-0',
            direction: 'after',
            anchor_date: '2026-11-19',
            target_date: '2026-11-20'
          }
        }
      ],
      clarification: null,
      vector_status: 'ready'
    }

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockResponse
    })
    globalThis.fetch = fetchMock

    const res = await searchRecall({
      query: '京都 清水寺',
      trip_id: 't-1',
      city: '京都市',
      category: '景點',
      limit: 10
    })

    expect(res.items).toHaveLength(1)
    expect(res.vector_status).toBe('ready')
    expect(res.items[0].event.place_name).toBe('清水寺')
    expect(res.items[0].relation?.direction).toBe('after')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/search', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        query: '京都 清水寺',
        trip_id: 't-1',
        city: '京都市',
        category: '景點',
        limit: 10
      })
    }))
  })

  it('getEvent sends GET /api/v1/events/:id', async () => {
    const mockEvent = {
      id: 'e-1',
      trip_id: 't-1',
      place_id: 'p-1',
      place_name: '清水寺',
      city: '京都市',
      address: '東山區清水1丁目294',
      category: '景點',
      date: '2026-11-20',
      time: '09:00',
      notes: '晨光古剎',
      position: 0,
      version: 1,
      trip_name: '京都秋楓紀行'
    }

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockEvent
    })
    globalThis.fetch = fetchMock

    const res = await getEvent('e-1')
    expect(res.id).toBe('e-1')
    expect(res.trip_name).toBe('京都秋楓紀行')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/events/e-1', expect.objectContaining({
      method: 'GET'
    }))
  })
})
