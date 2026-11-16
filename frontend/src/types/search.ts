import type { Event } from './travel'

export interface SearchEvent extends Event {
  trip_name?: string
}

export interface SearchRelation {
  anchor_id: string
  direction: string
  anchor_date: string
  target_date: string
}

export interface SearchItem {
  event: SearchEvent
  score: number
  reasons: string[]
  relation: SearchRelation | null
}

export interface SearchPayload {
  query: string
  trip_id?: string
  date_from?: string
  date_to?: string
  city?: string
  category?: string
  limit?: number
}

export interface SearchResponse {
  items: SearchItem[]
  clarification: string | null
  vector_status: string
}
