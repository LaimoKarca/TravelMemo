import { request } from './auth'
import type {
  PhotoDTO,
  PhotoListResponse,
  UpdatePhotoPayload,
  PhotoBindingKind,
  TripCoverResponse
} from '../types/photo'

export async function uploadPhoto(blob: Blob, contentType?: string): Promise<PhotoDTO> {
  const mimeType = contentType || blob.type || 'image/jpeg'
  return request<PhotoDTO>('/photos', {
    method: 'POST',
    headers: {
      'Content-Type': mimeType
    },
    body: blob
  })
}

export async function listPhotos(params?: {
  trip_id?: string
  event_id?: string
  conversation_id?: string
}): Promise<PhotoListResponse> {
  const query = new URLSearchParams()
  if (params?.trip_id) query.set('trip_id', params.trip_id)
  if (params?.event_id) query.set('event_id', params.event_id)
  if (params?.conversation_id) query.set('conversation_id', params.conversation_id)
  const qs = query.toString() ? `?${query.toString()}` : ''
  return request<PhotoListResponse>(`/photos${qs}`, {
    method: 'GET'
  })
}

export async function getPhoto(id: string): Promise<PhotoDTO> {
  return request<PhotoDTO>(`/photos/${encodeURIComponent(id)}`, {
    method: 'GET'
  })
}

export async function updatePhoto(id: string, payload: UpdatePhotoPayload): Promise<PhotoDTO> {
  return request<PhotoDTO>(`/photos/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export async function deletePhoto(id: string, version: number): Promise<void> {
  return request<void>(`/photos/${encodeURIComponent(id)}?version=${encodeURIComponent(version)}`, {
    method: 'DELETE'
  })
}

export async function retryPhoto(id: string, version: number): Promise<PhotoDTO> {
  return request<PhotoDTO>(`/photos/${encodeURIComponent(id)}/retry`, {
    method: 'POST',
    body: JSON.stringify({ version })
  })
}

export async function bindPhoto(
  id: string,
  kind: PhotoBindingKind,
  targetId: string
): Promise<PhotoDTO> {
  return request<PhotoDTO>(`/photos/${encodeURIComponent(id)}/bindings`, {
    method: 'POST',
    body: JSON.stringify({ kind, target_id: targetId })
  })
}

export async function unbindPhoto(
  id: string,
  kind: PhotoBindingKind,
  targetId: string
): Promise<void> {
  const query = new URLSearchParams({ kind, target_id: targetId })
  return request<void>(`/photos/${encodeURIComponent(id)}/bindings?${query.toString()}`, {
    method: 'DELETE'
  })
}

export async function reorderTripPhotos(tripId: string, photoIds: string[]): Promise<PhotoListResponse> {
  return request<PhotoListResponse>(`/trips/${encodeURIComponent(tripId)}/photos/order`, {
    method: 'PUT',
    body: JSON.stringify({ photo_ids: photoIds })
  })
}

export async function getTripCover(tripId: string): Promise<TripCoverResponse> {
  return request<TripCoverResponse>(`/trips/${encodeURIComponent(tripId)}/photos/cover`, {
    method: 'GET'
  })
}

export async function setTripCover(tripId: string, photoId: string | null): Promise<TripCoverResponse> {
  return request<TripCoverResponse>(`/trips/${encodeURIComponent(tripId)}/photos/cover`, {
    method: 'PUT',
    body: JSON.stringify({ photo_id: photoId })
  })
}
