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
  trip_id: string
  place_id: string
  place_name: string
  city: string
  address: string
  category: string
  date: string
  time: string | null
  notes: string
  position: number
  version: number
}

export interface Place {
  id: string
  name: string
  city: string
  address: string
}

export interface NextEdge {
  from_id: string
  to_id: string
}

export interface TripListResponse {
  items: Trip[]
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
  place_id?: string | null
  place_name: string
  city: string
  address: string
  category: string
  date: string
  time?: string | null
  notes: string
}

export interface UpdateEventPayload {
  place_id?: string | null
  place_name: string
  city: string
  address: string
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
