import type { Event } from './travel'
import type { PhotoDTO } from './photo'

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

export interface SearchPhotoItem {
  photo: PhotoDTO
  score: number
  reasons: string[]
  event?: SearchEvent | null
}

export interface SearchPayload {
  query?: string
  photo_ids?: string[]
  trip_id?: string
  date_from?: string
  date_to?: string
  city?: string
  category?: string
  limit?: number
}

export interface SearchResponse {
  items: SearchItem[]
  photo_items?: SearchPhotoItem[]
  clarification: string | null
  vector_status: string
}
