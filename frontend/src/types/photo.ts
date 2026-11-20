export type PhotoStatus = 'pending' | 'processing' | 'ready' | 'failed' | 'blocked'

export interface PhotoAnalysis {
  summary: string
  visible_text: string[]
  tags: string[]
  place_candidates: string[]
  date_candidate: string | null
  uncertainties: string[]
}

export type PhotoBindingKind = 'trip' | 'event' | 'conversation' | 'message'

export interface PhotoBinding {
  kind: PhotoBindingKind
  target_id: string
  trip_id?: string
}

export interface PhotoDTO {
  id: string
  caption: string
  version: number
  analysis_version: number
  status: PhotoStatus
  analysis: PhotoAnalysis
  width: number
  height: number
  size_bytes: number
  thumbnail_size_bytes: number
  created_at: string
  updated_at: string
  bindings: PhotoBinding[]
  url: string
  thumbnail_url: string
}

export interface PhotoListResponse {
  items: PhotoDTO[]
}

export interface UpdatePhotoPayload {
  version: number
  caption: string
}

export interface PhotoCaptionUpdate {
  photoId: string
  caption: string
  version: number
}

export interface RetryPhotoPayload {
  version: number
}

export interface CreateBindingPayload {
  kind: PhotoBindingKind
  target_id: string
}

export interface ReorderTripPhotosPayload {
  photo_ids: string[]
}

export interface TripCoverResponse {
  photo_id: string | null
}
