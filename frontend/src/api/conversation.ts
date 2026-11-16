import { request } from './auth'
import type {
  ConversationListResponse,
  ConversationSummary,
  CreateConversationPayload,
  Message,
  MessageListResponse,
  SendMessagePayload,
  UsageMeResponse
} from '../types/conversation'

export async function listConversations(): Promise<ConversationListResponse> {
  return request<ConversationListResponse>('/conversations', {
    method: 'GET'
  })
}

export async function createConversation(payload: CreateConversationPayload = {}): Promise<ConversationSummary> {
  const body: Record<string, any> = {}
  if (payload.title && payload.title.trim()) {
    body.title = payload.title.trim()
  }
  return request<ConversationSummary>('/conversations', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

export async function deleteConversation(id: string): Promise<void> {
  return request<void>(`/conversations/${encodeURIComponent(id)}`, {
    method: 'DELETE'
  })
}

export async function listMessages(conversationId: string): Promise<MessageListResponse> {
  return request<MessageListResponse>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'GET'
  })
}

export async function sendMessage(conversationId: string, payload: SendMessagePayload): Promise<Message> {
  return request<Message>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content: payload.content })
  })
}

export async function getUsage(): Promise<UsageMeResponse> {
  return request<UsageMeResponse>('/usage/me', {
    method: 'GET'
  })
}
