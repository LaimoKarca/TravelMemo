import { request } from './auth'
import type { DraftChanges, FootprintCommit, FootprintDraft } from '../types/footprint'
const base = (trip: string) => `/trips/${encodeURIComponent(trip)}/footprint-drafts`
const item = (trip: string, id: string) => `${base(trip)}/${encodeURIComponent(id)}`
export const latestFootprintDrafts = (trip: string) => request<{ items: FootprintDraft[] }>(base(trip))
export const createFootprintDraft = (trip: string, record_date: string, text: string) => request<FootprintDraft>(base(trip), { method: 'POST', body: JSON.stringify({ record_date, text }) })
export const getFootprintDraft = (trip: string, id: string) => request<FootprintDraft>(item(trip, id))
export const updateFootprintDraft = (trip: string, id: string, changes: DraftChanges) => request<FootprintDraft>(item(trip, id), { method: 'PATCH', body: JSON.stringify(changes) })
export const generateFootprints = (trip: string, id: string, version: number, request_id: string) => request<FootprintDraft>(`${item(trip, id)}/generate`, { method: 'POST', body: JSON.stringify({ version, request_id }) })
export const commitFootprints = (trip: string, id: string, version: number, trip_version: number, request_id: string) => request<FootprintCommit>(`${item(trip, id)}/commit`, { method: 'POST', body: JSON.stringify({ version, trip_version, request_id }) })
export const discardFootprintDraft = (trip: string, id: string, version: number) => request<void>(`${item(trip, id)}?version=${version}`, { method: 'DELETE' })
