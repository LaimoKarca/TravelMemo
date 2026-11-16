import { getCsrfToken, ApiError } from './auth'
import type {
  Trip,
  Event,
  TripListResponse,
  TripDetailResponse,
  PlaceListResponse,
  CreateTripPayload,
  UpdateTripPayload,
  CreateEventPayload,
  UpdateEventPayload,
  ReorderEventsPayload
} from '../types/travel'

const BASE_URL = '/api/v1'

async function travelRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')

  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const token = getCsrfToken()
  if (token && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', token)
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
    let detail = '發生未預期的伺服器錯誤，請稍後再試。'
    if (data && typeof data.detail === 'string') {
      detail = data.detail
    } else if (response.status === 409) {
      detail = '資料已被其他操作更新（版本衝突），請重新整理以取得最新版本。'
    } else if (response.status === 404) {
      detail = '找不到指定的旅程或行程資料。'
    } else if (response.status === 422) {
      detail = '資料驗證失敗，請檢查欄位格式與時間範圍。'
    } else if (response.status === 401) {
      detail = '您的登入狀態已過期，請重新登入。'
    }
    throw new ApiError(response.status, detail)
  }

  return data as T
}

export async function listTrips(): Promise<TripListResponse> {
  return travelRequest<TripListResponse>('/trips', {
    method: 'GET'
  })
}

export async function createTrip(payload: CreateTripPayload): Promise<Trip> {
  return travelRequest<Trip>('/trips', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function getTrip(id: string): Promise<TripDetailResponse> {
  return travelRequest<TripDetailResponse>(`/trips/${encodeURIComponent(id)}`, {
    method: 'GET'
  })
}

export async function updateTrip(id: string, payload: UpdateTripPayload): Promise<Trip> {
  return travelRequest<Trip>(`/trips/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export async function deleteTrip(id: string, version: number): Promise<void> {
  return travelRequest<void>(`/trips/${encodeURIComponent(id)}?version=${encodeURIComponent(version)}`, {
    method: 'DELETE'
  })
}

export async function listPlaces(): Promise<PlaceListResponse> {
  return travelRequest<PlaceListResponse>('/places', {
    method: 'GET'
  })
}

export async function createEvent(tripId: string, payload: CreateEventPayload): Promise<Event> {
  return travelRequest<Event>(`/trips/${encodeURIComponent(tripId)}/events`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function updateEvent(eventId: string, payload: UpdateEventPayload): Promise<Event> {
  return travelRequest<Event>(`/events/${encodeURIComponent(eventId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export async function deleteEvent(eventId: string, version: number): Promise<void> {
  return travelRequest<void>(`/events/${encodeURIComponent(eventId)}?version=${encodeURIComponent(version)}`, {
    method: 'DELETE'
  })
}

export async function reorderEvents(
  tripId: string,
  payload: ReorderEventsPayload
): Promise<TripDetailResponse> {
  return travelRequest<TripDetailResponse>(`/trips/${encodeURIComponent(tripId)}/event-order`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}
