import type { Event } from './travel'
export interface FootprintItem {
  id: string
  selected: boolean
  place_name: string | null
  date: string | null
  time: string | null
  city: string
  address: string
  category: string
  notes: string
}
export interface FootprintDraft {
  id: string
  trip_id: string
  version: number
  trip_version: number
  status: 'editing' | 'queued' | 'running' | 'ready' | 'failed' | 'committed'
  record_date: string
  text: string
  items: FootprintItem[]
  issues: Record<string, string[]>
  error: string | null
  request_id: string | null
}
export interface DraftChanges { version: number; record_date?: string; text?: string; items?: FootprintItem[] }
export interface FootprintCommit { events: Event[]; trip_version: number; draft: FootprintDraft }
