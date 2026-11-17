import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  uploadPhoto,
  listPhotos,
  getPhoto,
  updatePhoto,
  deletePhoto,
  retryPhoto,
  bindPhoto,
  unbindPhoto,
  reorderTripPhotos,
  getTripCover,
  setTripCover
} from '../photos'
import { setCsrfToken } from '../auth'

const mockPhotoDTO = {
  id: 'photo-1',
  caption: '嵐山竹林漫步',
  version: 1,
  analysis_version: 1,
  status: 'ready' as const,
  analysis: {
    summary: '一片茂密的綠色竹林小徑',
    visible_text: [],
    tags: ['竹林', '京都', '自然'],
    place_candidates: ['嵐山竹林之道'],
    date_candidate: '2026-11-20',
    uncertainties: []
  },
  width: 1920,
  height: 1080,
  size_bytes: 450000,
  thumbnail_size_bytes: 32000,
  created_at: '2026-11-20T10:00:00Z',
  updated_at: '2026-11-20T10:01:00Z',
  bindings: [{ kind: 'trip' as const, target_id: 'trip-1' }],
  url: '/api/v1/photos/photo-1/content',
  thumbnail_url: '/api/v1/photos/photo-1/thumbnail'
}

describe('Photos API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    setCsrfToken('csrf-token-abc')
  })

  it('uploadPhoto sends raw Blob with Content-Type and X-CSRF-Token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockPhotoDTO
    })
    globalThis.fetch = fetchMock

    const blob = new Blob(['fake image bytes'], { type: 'image/jpeg' })
    const result = await uploadPhoto(blob)

    expect(result.id).toBe('photo-1')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/photos', expect.objectContaining({
      method: 'POST',
      body: blob
    }))
    const headers = fetchMock.mock.calls[0][1].headers as Headers
    expect(headers.get('Content-Type')).toBe('image/jpeg')
    expect(headers.get('X-CSRF-Token')).toBe('csrf-token-abc')
  })

  it('listPhotos formats query parameters correctly', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ items: [mockPhotoDTO] })
    })
    globalThis.fetch = fetchMock

    const res = await listPhotos({ trip_id: 'trip-1', event_id: 'evt-1' })
    expect(res.items.length).toBe(1)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/photos?trip_id=trip-1&event_id=evt-1'),
      expect.objectContaining({ method: 'GET' })
    )
  })

  it('getPhoto fetches photo DTO by id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockPhotoDTO
    })
    globalThis.fetch = fetchMock

    const res = await getPhoto('photo-1')
    expect(res.caption).toBe('嵐山竹林漫步')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/photos/photo-1', expect.anything())
  })

  it('updatePhoto sends PATCH with caption and version', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ ...mockPhotoDTO, caption: '更新後的說明', version: 2 })
    })
    globalThis.fetch = fetchMock

    const res = await updatePhoto('photo-1', { version: 1, caption: '更新後的說明' })
    expect(res.caption).toBe('更新後的說明')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/photos/photo-1', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ version: 1, caption: '更新後的說明' })
    }))
  })

  it('deletePhoto sends DELETE with version in query param', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers()
    })
    globalThis.fetch = fetchMock

    await deletePhoto('photo-1', 2)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/photos/photo-1?version=2',
      expect.objectContaining({ method: 'DELETE' })
    )
  })

  it('retryPhoto sends POST with version', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ ...mockPhotoDTO, status: 'processing' })
    })
    globalThis.fetch = fetchMock

    const res = await retryPhoto('photo-1', 1)
    expect(res.status).toBe('processing')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/photos/photo-1/retry', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ version: 1 })
    }))
  })

  it('bindPhoto sends POST to bindings with kind and target_id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockPhotoDTO
    })
    globalThis.fetch = fetchMock

    await bindPhoto('photo-1', 'event', 'evt-100')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/photos/photo-1/bindings', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ kind: 'event', target_id: 'evt-100' })
    }))
  })

  it('unbindPhoto sends DELETE with kind and target_id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers()
    })
    globalThis.fetch = fetchMock

    await unbindPhoto('photo-1', 'event', 'evt-100')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/photos/photo-1/bindings?kind=event&target_id=evt-100',
      expect.objectContaining({ method: 'DELETE' })
    )
  })

  it('reorderTripPhotos sends PUT with photo_ids', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ items: [mockPhotoDTO] })
    })
    globalThis.fetch = fetchMock

    await reorderTripPhotos('trip-1', ['photo-2', 'photo-1'])
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/trips/trip-1/photos/order', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ photo_ids: ['photo-2', 'photo-1'] })
    }))
  })

  it('getTripCover and setTripCover manage cover photo id', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ photo_id: 'photo-1' })
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ photo_id: null })
      })
    globalThis.fetch = fetchMock

    const res1 = await getTripCover('trip-1')
    expect(res1.photo_id).toBe('photo-1')

    const res2 = await setTripCover('trip-1', null)
    expect(res2.photo_id).toBeNull()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/trips/trip-1/photos/cover', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ photo_id: null })
    }))
  })
})
