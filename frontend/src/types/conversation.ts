import type { PhotoDTO } from './photo'

export type MessageRole = 'user' | 'assistant'

export type MessageStatus =
  | 'answered'
  | 'insufficient_evidence'
  | 'needs_clarification'
  | 'unavailable'

export type CitationState = 'current' | 'changed' | 'deleted'

export type AnswerScope = 'memory' | 'image' | 'mixed'

export interface PhotoCitation {
  photo_id: string
  version: number
  state: CitationState
  caption?: string
  thumbnail_url: string
  url: string
}

export interface Citation {
  event_id: string
  trip_id: string
  date: string
  place_name: string
  version: number
  state: CitationState
  relation?: {
    anchor_id: string
    direction: string
    anchor_date?: string | null
    target_date?: string | null
  } | null
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  status: MessageStatus
  citations: Citation[]
  created_at: string
  photos?: PhotoDTO[]
  photo_citations?: PhotoCitation[]
  answer_scope?: AnswerScope
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
}

export interface ConversationListResponse {
  items: ConversationSummary[]
}

export interface CreateConversationPayload {
  title?: string
}

export interface MessageListResponse {
  items: Message[]
}

export interface SendMessagePayload {
  content?: string
  photo_ids?: string[]
}

export interface UsageMeResponse {
  date: string
  requests: number
  input_tokens: number
  output_tokens: number
  daily_limit: number
  model: string
}
