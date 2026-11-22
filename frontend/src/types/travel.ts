export interface Trip {
  id: string
  name: string
  start_date: string
  end_date: string
  timezone: string
  description: string
  version: number
}

export interface Event {
  id: string
  trip_id: string | null
  place_id: string
  place_name: string
  city: string
  address: string
  map_url?: string | null
  category: string
  date: string
  time: string | null
  notes: string
  position: number | null
  timezone?: string
  record_scope?: 'standalone' | 'trip'
  version: number
}

export interface Place {
  id: string
  name: string
  city: string
  address: string
  map_url?: string | null
}

export interface NextEdge {
  from_id: string
  to_id: string
}

export interface TripListItem extends Trip {
  cover_photo_id: string | null
}

export interface TripListResponse {
  items: TripListItem[]
}

export interface TripDetailResponse {
  trip: Trip
  events: Event[]
  next_edges: NextEdge[]
}

export interface PlaceListResponse {
  items: Place[]
}

export interface CreateTripPayload {
  name: string
  start_date: string
  end_date: string
  timezone: string
  description: string
}

export interface UpdateTripPayload {
  name: string
  start_date: string
  end_date: string
  timezone: string
  description: string
  version: number
}

export interface CreateEventPayload {
  timezone?: string
  place_id?: string | null
  place_name: string
  city: string
  address: string
  map_url?: string | null
  category: string
  date: string
  time?: string | null
  notes: string
}

export interface UpdateEventPayload {
  timezone?: string
  place_id?: string | null
  place_name: string
  city: string
  address: string
  map_url?: string | null
  category: string
  date: string
  time?: string | null
  notes: string
  version: number
}

export interface ReorderEventsPayload {
  version: number
  event_ids: string[]
}

export interface StandaloneEventFilters {
  q?: string
  city?: string
  category?: string
  date_from?: string
  date_to?: string
  offset?: number
  limit?: number
}

export interface StandaloneEventPage {
  items: Event[]
  next_offset: number | null
}

export interface AttachEventPayload {
  trip_id: string
  version: number
  trip_version: number
  before_event_id?: string | null
}

export interface EventDestination {
  tripId: string | null
  eventId?: string
}
