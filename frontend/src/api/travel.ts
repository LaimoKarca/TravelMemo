import { request } from './auth'
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
  ReorderEventsPayload,
  StandaloneEventFilters,
  StandaloneEventPage,
  AttachEventPayload
} from '../types/travel'
import type { SearchEvent } from '../types/search'

export async function listTrips(): Promise<TripListResponse> {
  return request<TripListResponse>('/trips', {
    method: 'GET'
  })
}

export async function createTrip(payload: CreateTripPayload): Promise<Trip> {
  return request<Trip>('/trips', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function getTrip(id: string): Promise<TripDetailResponse> {
  return request<TripDetailResponse>(`/trips/${encodeURIComponent(id)}`, {
    method: 'GET'
  })
}

export async function updateTrip(id: string, payload: UpdateTripPayload): Promise<Trip> {
  return request<Trip>(`/trips/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export async function deleteTrip(id: string, version: number): Promise<void> {
  return request<void>(`/trips/${encodeURIComponent(id)}?version=${encodeURIComponent(version)}`, {
    method: 'DELETE'
  })
}

export async function listPlaces(): Promise<PlaceListResponse> {
  return request<PlaceListResponse>('/places', {
    method: 'GET'
  })
}

export async function getEvent(eventId: string): Promise<SearchEvent> {
  return request<SearchEvent>(`/events/${encodeURIComponent(eventId)}`, {
    method: 'GET'
  })
}

export async function createEvent(tripId: string, payload: CreateEventPayload): Promise<Event> {
  return request<Event>(`/trips/${encodeURIComponent(tripId)}/events`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function listStandaloneEvents(filters: StandaloneEventFilters = {}): Promise<StandaloneEventPage> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  return request<StandaloneEventPage>(`/events?${query}`)
}

export function createStandaloneEvent(payload: CreateEventPayload): Promise<Event> {
  return request<Event>('/events', { method: 'POST', body: JSON.stringify(payload) })
}

export function attachEventToTrip(eventId: string, payload: AttachEventPayload): Promise<Event> {
  return request<Event>(`/events/${encodeURIComponent(eventId)}/attach-trip`, {
    method: 'POST', body: JSON.stringify(payload)
  })
}

export async function updateEvent(eventId: string, payload: UpdateEventPayload): Promise<Event> {
  return request<Event>(`/events/${encodeURIComponent(eventId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export async function deleteEvent(eventId: string, version: number): Promise<void> {
  return request<void>(`/events/${encodeURIComponent(eventId)}?version=${encodeURIComponent(version)}`, {
    method: 'DELETE'
  })
}

export async function reorderEvents(
  tripId: string,
  payload: ReorderEventsPayload
): Promise<TripDetailResponse> {
  return request<TripDetailResponse>(`/trips/${encodeURIComponent(tripId)}/event-order`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}
