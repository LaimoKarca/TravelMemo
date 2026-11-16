import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  listTrips,
  createTrip,
  getTrip,
  updateTrip,
  deleteTrip,
  listPlaces,
  createEvent,
  updateEvent,
  deleteEvent,
  reorderEvents
} from '../travel'
import { setCsrfToken, ApiError } from '../auth'

describe('Travel API Client', () => {
  beforeEach(() => {
    setCsrfToken(null)
    vi.restoreAllMocks()
  })

  it('listTrips sends GET /api/v1/trips and returns TripListResponse', async () => {
    const mockTrips = {
      items: [
        {
          id: 't-1',
          name: '京都秋楓紀行',
          start_date: '2026-11-20',
          end_date: '2026-11-25',
          timezone: 'Asia/Tokyo',
          description: '京都古寺與紅葉漫步',
          version: 1
        }
      ]
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockTrips
    })
    globalThis.fetch = fetchMock

    const res = await listTrips()
    expect(res.items).toHaveLength(1)
    expect(res.items[0].name).toBe('京都秋楓紀行')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips', expect.objectContaining({
      method: 'GET',
      credentials: 'include'
    }))
  })

  it('createTrip sends POST /api/v1/trips with in-memory CSRF token', async () => {
    setCsrfToken('mock-csrf-token')
    const createdTrip = {
      id: 't-2',
      name: '花東縱谷散策',
      start_date: '2026-12-01',
      end_date: '2026-12-03',
      timezone: 'Asia/Taipei',
      description: '慢活溫泉與田園',
      version: 1
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createdTrip
    })
    globalThis.fetch = fetchMock

    const payload = {
      name: '花東縱谷散策',
      start_date: '2026-12-01',
      end_date: '2026-12-03',
      timezone: 'Asia/Taipei',
      description: '慢活溫泉與田園'
    }

    const res = await createTrip(payload)
    expect(res.id).toBe('t-2')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(payload)
    }))
    const callHeaders = fetchMock.mock.calls[0][1].headers as Headers
    expect(callHeaders.get('X-CSRF-Token')).toBe('mock-csrf-token')
  })

  it('getTrip sends GET /api/v1/trips/:id', async () => {
    const detail = {
      trip: {
        id: 't-1',
        name: '京都秋楓紀行',
        start_date: '2026-11-20',
        end_date: '2026-11-25',
        timezone: 'Asia/Tokyo',
        description: '京都古寺與紅葉漫步',
        version: 2
      },
      events: [],
      next_edges: []
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => detail
    })
    globalThis.fetch = fetchMock

    const res = await getTrip('t-1')
    expect(res.trip.name).toBe('京都秋楓紀行')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips/t-1', expect.objectContaining({
      method: 'GET'
    }))
  })

  it('updateTrip sends PUT /api/v1/trips/:id with version and CSRF', async () => {
    setCsrfToken('csrf-update')
    const updated = {
      id: 't-1',
      name: '京都秋楓紀行修訂版',
      start_date: '2026-11-20',
      end_date: '2026-11-26',
      timezone: 'Asia/Tokyo',
      description: '新增宇治行程',
      version: 2
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => updated
    })
    globalThis.fetch = fetchMock

    const payload = {
      name: '京都秋楓紀行修訂版',
      start_date: '2026-11-20',
      end_date: '2026-11-26',
      timezone: 'Asia/Tokyo',
      description: '新增宇治行程',
      version: 1
    }

    const res = await updateTrip('t-1', payload)
    expect(res.version).toBe(2)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips/t-1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify(payload)
    }))
  })

  it('deleteTrip sends DELETE /api/v1/trips/:id?version=N and handles 204', async () => {
    setCsrfToken('csrf-del')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers()
    })
    globalThis.fetch = fetchMock

    await deleteTrip('t-1', 2)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips/t-1?version=2', expect.objectContaining({
      method: 'DELETE'
    }))
  })

  it('listPlaces sends GET /api/v1/places', async () => {
    const places = {
      items: [
        { id: 'p-1', name: '清水寺', city: '京都市', address: '東山區清水1丁目294' }
      ]
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => places
    })
    globalThis.fetch = fetchMock

    const res = await listPlaces()
    expect(res.items[0].name).toBe('清水寺')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/places', expect.objectContaining({
      method: 'GET'
    }))
  })

  it('createEvent sends POST /api/v1/trips/:id/events', async () => {
    setCsrfToken('csrf-evt')
    const createdEvent = {
      id: 'e-1',
      trip_id: 't-1',
      place_id: 'p-1',
      place_name: '清水寺',
      city: '京都市',
      address: '東山區清水1丁目294',
      category: '景點',
      date: '2026-11-21',
      time: '09:00',
      notes: '晨光穿透舞台',
      position: 0,
      version: 1
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => createdEvent
    })
    globalThis.fetch = fetchMock

    const payload = {
      place_id: 'p-1',
      place_name: '清水寺',
      city: '京都市',
      address: '東山區清水1丁目294',
      category: '景點',
      date: '2026-11-21',
      time: '09:00',
      notes: '晨光穿透舞台'
    }

    const res = await createEvent('t-1', payload)
    expect(res.id).toBe('e-1')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips/t-1/events', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(payload)
    }))
  })

  it('updateEvent sends PUT /api/v1/events/:id with version', async () => {
    setCsrfToken('csrf-evt-up')
    const updated = {
      id: 'e-1',
      trip_id: 't-1',
      place_id: 'p-1',
      place_name: '清水寺本堂',
      city: '京都市',
      address: '東山區清水1丁目294',
      category: '名勝',
      date: '2026-11-21',
      time: '09:30',
      notes: '預約門票已完成',
      position: 0,
      version: 2
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => updated
    })
    globalThis.fetch = fetchMock

    const payload = {
      place_name: '清水寺本堂',
      city: '京都市',
      address: '東山區清水1丁目294',
      category: '名勝',
      date: '2026-11-21',
      time: '09:30',
      notes: '預約門票已完成',
      version: 1
    }

    const res = await updateEvent('e-1', payload)
    expect(res.version).toBe(2)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/events/e-1', expect.objectContaining({
      method: 'PUT'
    }))
  })

  it('deleteEvent sends DELETE /api/v1/events/:id?version=N', async () => {
    setCsrfToken('csrf-evt-del')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers()
    })
    globalThis.fetch = fetchMock

    await deleteEvent('e-1', 1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/events/e-1?version=1', expect.objectContaining({
      method: 'DELETE'
    }))
  })

  it('reorderEvents sends PUT /api/v1/trips/:id/event-order with version and event_ids', async () => {
    setCsrfToken('csrf-reorder')
    const reordered = {
      trip: { id: 't-1', name: '京都秋楓紀行', version: 3 },
      events: [
        { id: 'e-2', position: 0 },
        { id: 'e-1', position: 1 }
      ],
      next_edges: [{ from_id: 'e-2', to_id: 'e-1' }]
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => reordered
    })
    globalThis.fetch = fetchMock

    const payload = {
      version: 2,
      event_ids: ['e-2', 'e-1']
    }

    const res = await reorderEvents('t-1', payload)
    expect(res.next_edges).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips/t-1/event-order', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify(payload)
    }))
  })

  it('throws ApiError with status 409 on version conflict', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: '版本衝突，資料已在別處變更' })
    })
    globalThis.fetch = fetchMock

    await expect(deleteTrip('t-1', 1)).rejects.toThrow(ApiError)
    try {
      await deleteTrip('t-1', 1)
    } catch (err: any) {
      expect(err.status).toBe(409)
      expect(err.detail).toBe('版本衝突，資料已在別處變更')
    }
  })
})
