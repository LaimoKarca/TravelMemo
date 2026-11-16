import { request } from './auth'
import type { SearchPayload, SearchResponse, SearchEvent } from '../types/search'

export async function searchRecall(payload: SearchPayload): Promise<SearchResponse> {
  const body: Record<string, any> = {
    query: payload.query
  }
  if (payload.trip_id) body.trip_id = payload.trip_id
  if (payload.date_from) body.date_from = payload.date_from
  if (payload.date_to) body.date_to = payload.date_to
  if (payload.city) body.city = payload.city
  if (payload.category) body.category = payload.category
  if (typeof payload.limit === 'number') body.limit = payload.limit

  return request<SearchResponse>('/search', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

export async function getEvent(eventId: string): Promise<SearchEvent> {
  return request<SearchEvent>(`/events/${encodeURIComponent(eventId)}`, {
    method: 'GET'
  })
}
