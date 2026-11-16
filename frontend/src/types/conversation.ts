export type MessageRole = 'user' | 'assistant'

export type MessageStatus =
  | 'answered'
  | 'insufficient_evidence'
  | 'needs_clarification'
  | 'unavailable'

export type CitationState = 'current' | 'changed' | 'deleted'

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
  content: string
}

export interface UsageMeResponse {
  date: string
  requests: number
  input_tokens: number
  output_tokens: number
  daily_limit: number
  model: string
}
