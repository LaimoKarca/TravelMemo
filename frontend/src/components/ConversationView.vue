<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import type {
  ConversationSummary,
  Message,
  Citation,
  UsageMeResponse,
  MessageStatus
} from '../types/conversation'
import {
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  sendMessage,
  getUsage
} from '../api/conversation'
import { ApiError } from '../api/auth'
import ConfirmDialog from './ConfirmDialog.vue'

const emit = defineEmits<{
  (e: 'view-citation', citation: Citation): void
  (e: 'jump-trip', payload: { tripId: string; eventId: string }): void
}>()

// State
const conversations = ref<ConversationSummary[]>([])
const activeConversationId = ref<string | null>(null)
const messages = ref<Message[]>([])
const usage = ref<UsageMeResponse | null>(null)

const loadingConversations = ref(false)
const loadingMessages = ref(false)
const sendingMessage = ref(false)
const loadingUsage = ref(false)

const newConversationTitle = ref('')
const inputContent = ref('')
const errorMessage = ref('')

// Drafts cache per conversation to preserve user draft across switches
const drafts = ref<Record<string, string>>({})

// Generation counter to invalidate stale loads when switching or on create/delete
let messageLoadGen = 0

// Delete conversation confirm modal
const showDeleteConfirm = ref(false)
const conversationToDelete = ref<ConversationSummary | null>(null)
const deletingConversation = ref(false)

const messagesContainerRef = ref<HTMLElement | null>(null)

onMounted(async () => {
  await Promise.all([
    fetchConversations(),
    fetchUsage()
  ])
})

async function fetchConversations() {
  loadingConversations.value = true
  errorMessage.value = ''
  try {
    const res = await listConversations()
    conversations.value = res.items || []
    loadingConversations.value = false
    if (!activeConversationId.value && conversations.value.length > 0) {
      selectConversation(conversations.value[0].id)
    }
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '載入對話列表失敗，請稍後再試。'
    loadingConversations.value = false
  }
}

async function fetchUsage() {
  loadingUsage.value = true
  try {
    const res = await getUsage()
    usage.value = res
  } catch {
    // Non-blocking usage fetch
  } finally {
    loadingUsage.value = false
  }
}

async function selectConversation(id: string) {
  if (activeConversationId.value === id && messages.value.length > 0) return

  // Preserve draft of current active conversation before switching
  if (activeConversationId.value && activeConversationId.value !== id) {
    drafts.value[activeConversationId.value] = inputContent.value
  }

  activeConversationId.value = id
  // Restore draft for this conversation
  inputContent.value = drafts.value[id] || ''
  messages.value = []

  const currentGen = ++messageLoadGen
  loadingMessages.value = true
  errorMessage.value = ''

  try {
    const res = await listMessages(id)
    // Guard against race conditions: only apply if this is still the active conversation & latest load
    if (currentGen !== messageLoadGen || activeConversationId.value !== id) {
      return
    }
    messages.value = res.items || []
    await scrollToBottom()
  } catch (err: any) {
    if (currentGen !== messageLoadGen || activeConversationId.value !== id) {
      return
    }
    errorMessage.value = err instanceof ApiError ? err.detail : '載入訊息紀錄失敗，請稍後再試。'
  } finally {
    if (currentGen === messageLoadGen && activeConversationId.value === id) {
      loadingMessages.value = false
    }
  }
}

async function handleCreateConversation() {
  errorMessage.value = ''
  const title = newConversationTitle.value.trim() || undefined
  loadingConversations.value = true

  try {
    const created = await createConversation({ title })
    newConversationTitle.value = ''
    conversations.value.unshift(created)

    // Save previous draft if applicable
    if (activeConversationId.value) {
      drafts.value[activeConversationId.value] = inputContent.value
    }

    // Invalidate in-flight message loads only upon successful creation
    messageLoadGen++
    activeConversationId.value = created.id
    messages.value = []
    inputContent.value = ''
    loadingMessages.value = false
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '建立新對話失敗，請稍後再試。'
  } finally {
    loadingConversations.value = false
  }
}

function promptDeleteConversation(conv: ConversationSummary) {
  conversationToDelete.value = conv
  showDeleteConfirm.value = true
}

async function handleConfirmDelete() {
  if (!conversationToDelete.value) return
  const targetId = conversationToDelete.value.id
  deletingConversation.value = true
  errorMessage.value = ''

  try {
    await deleteConversation(targetId)
    conversations.value = conversations.value.filter((c) => c.id !== targetId)
    delete drafts.value[targetId]

    // Only invalidate and switch if deleting the currently active conversation
    if (activeConversationId.value === targetId) {
      messageLoadGen++
      if (conversations.value.length > 0) {
        await selectConversation(conversations.value[0].id)
      } else {
        activeConversationId.value = null
        messages.value = []
        inputContent.value = ''
        loadingMessages.value = false
      }
    }
    showDeleteConfirm.value = false
    conversationToDelete.value = null
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '刪除對話失敗，請稍後再試。'
  } finally {
    deletingConversation.value = false
  }
}

async function handleSendMessage() {
  const targetId = activeConversationId.value
  const content = inputContent.value.trim()
  if (!content || !targetId || sendingMessage.value) return

  // Optimistically append user message
  const tempUserMessage: Message = {
    id: 'temp-' + Date.now(),
    role: 'user',
    content,
    status: 'answered',
    citations: [],
    created_at: new Date().toISOString()
  }

  // Clear input and current draft
  inputContent.value = ''
  delete drafts.value[targetId]

  messages.value.push(tempUserMessage)
  sendingMessage.value = true
  errorMessage.value = ''

  scrollToBottom()

  try {
    const reply = await sendMessage(targetId, { content })
    // Only append reply if still same active conversation
    if (activeConversationId.value === targetId) {
      messages.value.push(reply)
      await scrollToBottom()
    }
    await fetchUsage()
  } catch (err: any) {
    // Failed send: remove optimistic message and restore draft
    const tempIdx = messages.value.findIndex((m) => m.id === tempUserMessage.id)
    if (tempIdx !== -1) {
      messages.value.splice(tempIdx, 1)
    }

    if (activeConversationId.value === targetId) {
      inputContent.value = content
      errorMessage.value = err instanceof ApiError ? err.detail : '發送訊息失敗，請稍後再試。'
    } else {
      drafts.value[targetId] = content
    }
    await fetchUsage()
  } finally {
    sendingMessage.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainerRef.value) {
    messagesContainerRef.value.scrollTop = messagesContainerRef.value.scrollHeight
  }
}

function getStatusBadge(status: MessageStatus): { text: string; className: string } {
  switch (status) {
    case 'answered':
      return { text: '已依手記回答', className: 'status-answered' }
    case 'insufficient_evidence':
      return { text: '手記證據不足', className: 'status-insufficient' }
    case 'needs_clarification':
      return { text: '需進一步釐清', className: 'status-clarify' }
    case 'unavailable':
      return { text: '暫無法回覆', className: 'status-unavailable' }
    default:
      return { text: status, className: 'status-default' }
  }
}

function getCitationStateBadge(state: Citation['state']): { text: string; className: string } {
  switch (state) {
    case 'current':
      return { text: '最新版本', className: 'cite-current' }
    case 'changed':
      return { text: '手記已修訂', className: 'cite-changed' }
    case 'deleted':
      return { text: '足跡已刪除', className: 'cite-deleted' }
    default:
      return { text: state, className: 'cite-default' }
  }
}

function handleCitationClick(citation: Citation) {
  if (citation.state === 'deleted') return
  emit('view-citation', citation)
}
</script>

<template>
  <section class="conversation-view-section" aria-label="AI 旅程對話">
    <!-- Top Header: Title & Disclosure for detailed token/model usage -->
    <header class="conversation-header">
      <div class="header-main-row">
        <h2 class="view-title">AI 旅程助理</h2>

        <!-- Detailed token/model info via disclosure per brief -->
        <details v-if="usage" class="usage-disclosure" role="region" aria-label="今日對話用量">
          <summary class="usage-summary">
            <svg class="usage-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span>今日用量：{{ usage.requests }} / {{ usage.daily_limit }} 次</span>
          </summary>
          <div class="usage-details-popover">
            <div class="usage-row">
              <span class="usage-label">今日請求：</span>
              <span class="usage-value">{{ usage.requests }} / {{ usage.daily_limit }} 次</span>
            </div>
            <div class="usage-row">
              <span class="usage-label">消耗 Tokens：</span>
              <span class="usage-value">{{ usage.input_tokens + usage.output_tokens }}</span>
            </div>
            <div class="usage-meta-tag">
              <span>模型：{{ usage.model }}</span>
              <span>({{ usage.date }} UTC)</span>
            </div>
          </div>
        </details>
      </div>

      <!-- Compact History Toolbar across top (No secondary framed sidebar) -->
      <div class="conversation-toolbar" aria-label="歷史對話導覽">
        <div class="toolbar-top">
          <span class="toolbar-label">歷史對話</span>
          <form class="create-conv-form" @submit.prevent="handleCreateConversation">
            <input
              v-model="newConversationTitle"
              type="text"
              class="form-input conv-title-input"
              placeholder="新對話主題..."
              maxlength="40"
              :disabled="loadingConversations"
            />
            <button
              type="submit"
              class="btn btn-secondary btn-new-conv"
              :disabled="loadingConversations"
            >
              + 新對話
            </button>
          </form>
        </div>

        <div v-if="loadingConversations" class="toolbar-loading" role="status" aria-live="polite">
          <div class="page-spinner-sm" aria-hidden="true"></div>
          <span>載入中...</span>
        </div>

        <div v-else-if="conversations.length === 0" class="toolbar-empty">
          <span>尚未建立對話。輸入主題後點擊「+ 新對話」開始。</span>
        </div>

        <ul v-else class="conversations-list" aria-label="對話列表">
          <li
            v-for="conv in conversations"
            :key="conv.id"
            class="conversation-item"
            :class="{ 'is-active': conv.id === activeConversationId }"
            @click="selectConversation(conv.id)"
          >
            <button type="button" class="conv-item-content conversation-select" :aria-pressed="conv.id === activeConversationId">
              <span class="conv-title">{{ conv.title || '無標題對話' }}</span>
              <span class="conv-date">{{ conv.created_at ? conv.created_at.slice(0, 10) : '' }}</span>
            </button>
            <button
              type="button"
              class="btn-delete-conv"
              title="刪除此對話"
              :aria-label="`刪除對話 ${conv.title || '無標題對話'}`"
              @click.stop="promptDeleteConversation(conv)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </li>
        </ul>
      </div>
    </header>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Flattened Open Message Stream & Single Composer (No enclosing chat card) -->
    <main class="chat-main" aria-label="對話內容">
      <div v-if="!activeConversationId" class="no-active-chat">
        <p>請建立或選擇一個歷史對話以開始旅程交談。</p>
      </div>

      <div v-else class="chat-thread-container">
        <!-- Open Messages Stream -->
        <div
          ref="messagesContainerRef"
          class="messages-stream"
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
        >
          <div v-if="loadingMessages" class="chat-loading" role="status">
            <div class="page-spinner" aria-hidden="true"></div>
            <p class="loading-text">載入對話紀錄中...</p>
          </div>

          <div v-else-if="messages.length === 0" class="empty-chat-state">
            <p class="empty-chat-title">您好！我是您的旅行手記助理。</p>
            <p class="empty-chat-sub">
              您可以詢問：「我上次去京都吃了哪幾家店？」或「我有記錄過清水寺的隨筆嗎？」
            </p>
          </div>

          <!-- Message turns separated with natural space -->
          <article
            v-for="msg in messages"
            :key="msg.id"
            class="message-card"
            :class="msg.role === 'user' ? 'message-user' : 'message-assistant'"
          >
            <header class="message-header">
              <span class="message-role-label">
                {{ msg.role === 'user' ? '旅人' : '手記助理' }}
              </span>
              <span
                v-if="msg.role === 'assistant'"
                class="message-status-pill"
                :class="getStatusBadge(msg.status).className"
              >
                {{ getStatusBadge(msg.status).text }}
              </span>
            </header>

            <!-- Natural text in open stream -->
            <div class="message-content">
              {{ msg.content }}
            </div>

            <!-- Citations: Flat text rows right below answer (No nested source cards) -->
            <div
              v-if="msg.role === 'assistant' && msg.citations && msg.citations.length > 0"
              class="citations-container"
            >
              <span class="citations-heading">引用手記足跡：</span>
              <div class="citations-flat-list">
                <div
                  v-for="cite in msg.citations"
                  :key="cite.event_id"
                  class="citation-card citation-row"
                  :class="{ 'is-deleted': cite.state === 'deleted' }"
                >
                  <span class="cite-bullet" aria-hidden="true">—</span>
                  <span class="cite-place-name">{{ cite.place_name }}</span>
                  <span class="cite-date">({{ cite.date }})</span>
                  <span
                    class="cite-state-pill"
                    :class="getCitationStateBadge(cite.state).className"
                  >
                    {{ getCitationStateBadge(cite.state).text }}
                  </span>

                  <button
                    v-if="cite.state !== 'deleted'"
                    type="button"
                    class="btn-cite-inspect"
                    @click="handleCitationClick(cite)"
                  >
                    檢視足跡
                  </button>
                  <span v-else class="cite-deleted-tip">已刪除不可檢視</span>
                </div>
              </div>
            </div>
          </article>

          <!-- Sending assistant indicator -->
          <div v-if="sendingMessage" class="message-card message-assistant sending-placeholder" role="status">
            <span class="message-role-label">手記助理</span>
            <div class="assistant-thinking-row">
              <div class="page-spinner-sm" aria-hidden="true"></div>
              <span class="thinking-text">正在翻閱旅程手記並檢索證據...</span>
            </div>
          </div>
        </div>

        <!-- Single Composer on page -->
        <footer class="chat-input-bar">
          <form class="chat-form" @submit.prevent="handleSendMessage">
            <label for="chat-message-input" class="sr-only">輸入對話訊息</label>
            <textarea
              id="chat-message-input"
              v-model="inputContent"
              class="form-input chat-textarea"
              placeholder="詢問任何關於您旅程手記的問題...（Enter 發送，Shift+Enter 換行）"
              rows="2"
              :disabled="sendingMessage || loadingMessages"
              @keydown.enter.exact.prevent="handleSendMessage"
            ></textarea>
            <button
              type="submit"
              class="btn btn-primary send-btn"
              :disabled="sendingMessage || loadingMessages || !inputContent.trim()"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
              <span>{{ sendingMessage ? '回覆中...' : '發送' }}</span>
            </button>
          </form>
        </footer>
      </div>
    </main>

    <!-- Confirm Dialog for Deleting Conversation -->
    <ConfirmDialog
      :visible="showDeleteConfirm"
      title="確認刪除對話"
      :message="`確定要刪除「${conversationToDelete?.title || '此對話'}」嗎？此動作將清除對話內的問答紀錄。`"
      :loading="deletingConversation"
      @confirm="handleConfirmDelete"
      @cancel="showDeleteConfirm = false"
    />
  </section>
</template>

<style scoped>
.conversation-view-section {
  --color-pale-accent: var(--color-maple-subtle);
  --color-amber-pale: var(--color-amber-subtle);

  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
  height: calc(100dvh - 80px);
  min-height: 0;
  background-color: var(--color-canvas);
  color: var(--color-ink);
  box-sizing: border-box;
}

/* Header & Compact Toolbar */
.conversation-header {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--color-border);
}

.header-main-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
}

.view-title {
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--color-ink);
  letter-spacing: -0.01em;
}

/* Usage disclosure */
.usage-disclosure {
  position: relative;
  font-size: 0.8125rem;
}

.usage-summary {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.65rem;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  cursor: pointer;
  color: var(--color-subtle);
  font-weight: 500;
  list-style: none;
  user-select: none;
}

.usage-summary::-webkit-details-marker {
  display: none;
}

.usage-icon {
  color: var(--color-maple);
  flex-shrink: 0;
}

.usage-details-popover {
  position: absolute;
  right: 0;
  top: calc(100% + 0.35rem);
  z-index: 20;
  min-width: 220px;
  padding: 0.625rem 0.875rem;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(69, 58, 50, 0.08);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.75rem;
}

.usage-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.usage-label {
  color: var(--color-subtle);
}

.usage-value {
  font-weight: 700;
  color: var(--color-maple);
}

.usage-meta-tag {
  color: var(--color-subtle);
  display: flex;
  gap: 0.35rem;
  border-top: 1px solid var(--color-border-light);
  padding-top: 0.25rem;
  margin-top: 0.2rem;
}

/* Compact History Toolbar (Flat across top) */
.conversation-toolbar {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.toolbar-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.toolbar-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-subtle);
}

.create-conv-form {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}

.conv-title-input {
  min-height: 32px;
  height: 32px;
  padding: 0.2rem 0.5rem;
  font-size: 0.8125rem;
  width: 180px;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  color: var(--color-ink);
}

.conv-title-input:focus {
  border-color: var(--color-maple);
  box-shadow: 0 0 0 2px var(--color-pale-accent);
  outline: none;
}

.btn-new-conv {
  min-height: 32px;
  height: 32px;
  padding: 0.2rem 0.65rem;
  font-size: 0.75rem;
  white-space: nowrap;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  color: var(--color-ink);
  border-radius: var(--radius-xs);
}

.btn-new-conv:hover:not(:disabled) {
  background-color: var(--color-pale-accent);
  border-color: var(--color-maple);
}

.toolbar-loading,
.toolbar-empty {
  font-size: 0.75rem;
  color: var(--color-subtle);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}

/* Horizontal pill list */
.conversations-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.conversation-item {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.3rem 0.6rem;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
}

.conversation-item:hover {
  background-color: var(--color-pale-accent);
  border-color: var(--color-maple);
}

.conversation-item.is-active {
  background-color: var(--color-pale-accent);
  border-color: var(--color-maple);
}

.conversation-item:focus-visible {
  outline: 2px solid var(--color-maple);
  outline-offset: 1px;
}

.conv-item-content {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
}

.conv-title {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-ink);
  max-width: 140px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conversation-item.is-active .conv-title {
  color: var(--color-maple);
  font-weight: 600;
}

.conv-date {
  font-size: 0.6875rem;
  color: var(--color-subtle);
}

.btn-delete-conv {
  background: transparent;
  border: none;
  color: var(--color-subtle);
  width: 18px;
  height: 18px;
  border-radius: var(--radius-xs);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
}

.btn-delete-conv:hover {
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
}

/* Error Banner */
.error-banner {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-text);
  padding: 0.65rem 0.875rem;
  border-radius: var(--radius-xs);
  font-size: 0.875rem;
}

/* Flattened Chat Main */
.chat-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
}

.no-active-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-subtle);
  font-size: 0.875rem;
  padding: 3rem 1rem;
  text-align: center;
}

.chat-thread-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
  min-height: 0;
}

/* Open message stream: single scrollbox */
.messages-stream {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 0;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  width: 100%;
  min-height: 0;
}

.conversation-select {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  padding: 0;
  cursor: pointer;
}

.chat-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  gap: 0.75rem;
}

.empty-chat-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
  color: var(--color-subtle);
}

.empty-chat-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--color-ink);
}

.empty-chat-sub {
  font-size: 0.8125rem;
  margin-top: 0.35rem;
  max-width: 420px;
  line-height: 1.5;
}

/* Open Message Turn (No surrounding border/background/shadow/rounded-card) */
.message-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  width: 100%;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.message-role-label {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.message-user .message-role-label {
  color: var(--color-maple);
}

.message-assistant .message-role-label {
  color: var(--color-olive);
}

.message-status-pill {
  font-size: 0.6875rem;
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-xs);
  font-weight: 600;
}

.status-answered {
  background-color: var(--color-olive-pale);
  color: var(--color-olive);
}

.status-insufficient {
  background-color: var(--color-amber-pale);
  color: #7A5714;
}

.status-clarify {
  background-color: var(--color-pale-accent);
  color: var(--color-maple);
}

.status-unavailable {
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
}

.message-content {
  font-size: 0.9375rem;
  color: var(--color-ink);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

/* Citations as Flat Text Rows / Inline Links (No nested cards) */
.citations-container {
  margin-top: 0.4rem;
  padding-top: 0.4rem;
  border-top: 1px dashed var(--color-border-light);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.citations-heading {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-subtle);
}

.citations-flat-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.citation-card.citation-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.45rem;
  font-size: 0.8125rem;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
}

.citation-card.citation-row.is-deleted {
  opacity: 0.7;
}

.cite-bullet {
  color: var(--color-subtle);
  user-select: none;
}

.cite-place-name {
  font-weight: 600;
  color: var(--color-ink);
}

.cite-date {
  color: var(--color-subtle);
  font-size: 0.75rem;
}

.cite-state-pill {
  font-size: 0.6875rem;
  padding: 0.08rem 0.35rem;
  border-radius: var(--radius-xs);
  font-weight: 600;
}

.cite-current {
  background-color: var(--color-olive-pale);
  color: var(--color-olive);
}

.cite-changed {
  background-color: var(--color-amber-pale);
  color: #7A5714;
}

.cite-deleted {
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
}

/* Citations as Text Link */
.btn-cite-inspect {
  background: transparent;
  border: none;
  color: var(--color-maple);
  padding: 0;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
  line-height: inherit;
}

.btn-cite-inspect:hover {
  color: var(--color-maple-hover);
}

.cite-deleted-tip {
  font-size: 0.75rem;
  color: var(--color-subtle);
}

/* Assistant Thinking Placeholder */
.assistant-thinking-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.2rem 0;
}

.thinking-text {
  font-size: 0.8125rem;
  color: var(--color-subtle);
  font-style: italic;
}

/* Single Composer at bottom */
.chat-input-bar {
  padding-top: 0.875rem;
  border-top: 1px solid var(--color-border);
  background-color: transparent;
}

.chat-form {
  display: flex;
  gap: 0.625rem;
  align-items: flex-end;
}

.chat-textarea {
  resize: none;
  min-height: 44px;
  font-size: 0.875rem;
  line-height: 1.45;
  padding: 0.55rem 0.75rem;
  flex: 1;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  color: var(--color-ink);
}

.chat-textarea:focus {
  border-color: var(--color-maple);
  box-shadow: 0 0 0 2px var(--color-pale-accent);
  outline: none;
}

.send-btn {
  height: 44px;
  white-space: nowrap;
  flex-shrink: 0;
  background-color: var(--color-maple);
  color: #FFFFFF;
  border: 1px solid var(--color-maple);
}

.send-btn:hover:not(:disabled) {
  background-color: var(--color-maple-hover);
  border-color: var(--color-maple-hover);
}

/* Minimal Spinners */
.page-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border-light);
  border-top-color: var(--color-maple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.page-spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border-light);
  border-top-color: var(--color-maple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 0.875rem;
  color: var(--color-subtle);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .conversation-view-section { height: calc(100dvh - 160px); }
  .header-main-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .toolbar-top {
    flex-direction: column;
    align-items: stretch;
  }

  .create-conv-form {
    width: 100%;
  }

  .conv-title-input {
    flex: 1;
    width: auto;
  }

  .messages-stream {
    padding: 0.75rem 0;
    gap: 1.25rem;
  }
}
</style>
