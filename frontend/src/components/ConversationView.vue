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
  // Capture target conversation ID and content before ANY await or scroll
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

  // Scroll after capturing targetId and content
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
    // Failed send (including 429): remove optimistic message and restore draft
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
    <!-- Top Header: Title & Usage Banner -->
    <div class="conversation-top-row">
      <div>
        <h2 class="view-title">AI 旅程助理</h2>
        <p class="view-subtitle">
          依旅行手記回答問題並提供來源，資料不足時會提示您補充線索。
        </p>
      </div>

      <!-- Usage Indicator Banner -->
      <div v-if="usage" class="usage-banner" role="region" aria-label="今日對話用量">
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
    </div>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Main 2-column Conversation Workspace -->
    <div class="chat-layout">
      <!-- Left Column: Conversations Sidebar -->
      <aside class="conversations-sidebar" aria-label="對話列表清單">
        <div class="sidebar-header">
          <h3 class="sidebar-title">歷史對話</h3>
          <form class="create-conv-form" @submit.prevent="handleCreateConversation">
            <input
              v-model="newConversationTitle"
              type="text"
              class="form-input conv-title-input"
              placeholder="對話主題（選填）..."
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

        <div v-if="loadingConversations" class="sidebar-loading" role="status" aria-live="polite">
          <div class="page-spinner-sm" aria-hidden="true"></div>
          <span>載入對話...</span>
        </div>

        <div v-else-if="conversations.length === 0" class="sidebar-empty">
          <span>尚未建立對話。輸入主題並點擊「+ 新對話」開始。</span>
        </div>

        <ul v-else class="conversations-list" role="listbox" aria-label="對話列表">
          <li
            v-for="conv in conversations"
            :key="conv.id"
            class="conversation-item"
            :class="{ 'is-active': conv.id === activeConversationId }"
            role="option"
            :aria-selected="conv.id === activeConversationId"
            tabindex="0"
            @click="selectConversation(conv.id)"
            @keydown.enter="selectConversation(conv.id)"
            @keydown.space.prevent="selectConversation(conv.id)"
          >
            <div class="conv-item-content">
              <span class="conv-title">{{ conv.title || '無標題對話' }}</span>
              <span class="conv-date">{{ conv.created_at ? conv.created_at.slice(0, 10) : '' }}</span>
            </div>
            <button
              type="button"
              class="btn-delete-conv"
              title="刪除此對話"
              :aria-label="`刪除對話 ${conv.title || '無標題對話'}`"
              @click.stop="promptDeleteConversation(conv)"
            >
              ✕
            </button>
          </li>
        </ul>
      </aside>

      <!-- Right Column: Active Chat Area -->
      <main class="chat-main" aria-label="對話內容">
        <!-- If no active conversation -->
        <div v-if="!activeConversationId" class="no-active-chat">
          <p>請從左側選擇或建立一個對話，開始向旅程助理提問。</p>
        </div>

        <!-- Active Chat Container -->
        <div v-else class="chat-thread-container">
          <!-- Messages Stream -->
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

            <!-- Messages List -->
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

              <!-- Clean Vue text interpolation with preserved whitespace -->
              <div class="message-content">
                {{ msg.content }}
              </div>

              <!-- Citations List for Assistant -->
              <div
                v-if="msg.role === 'assistant' && msg.citations && msg.citations.length > 0"
                class="citations-container"
              >
                <span class="citations-heading">引用手記足跡：</span>
                <div class="citations-grid">
                  <div
                    v-for="cite in msg.citations"
                    :key="cite.event_id"
                    class="citation-card"
                    :class="{ 'is-deleted': cite.state === 'deleted' }"
                  >
                    <div class="citation-main">
                      <span class="cite-place-name">{{ cite.place_name }}</span>
                      <span class="cite-date">{{ cite.date }}</span>
                    </div>

                    <div class="citation-actions">
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
              </div>
            </article>

            <!-- Sending assistant spinner -->
            <div v-if="sendingMessage" class="message-card message-assistant sending-placeholder" role="status">
              <span class="message-role-label">手記助理</span>
              <div class="assistant-thinking-row">
                <div class="page-spinner-sm" aria-hidden="true"></div>
                <span class="thinking-text">正在翻閱旅程手記並檢索證據...</span>
              </div>
            </div>
          </div>

          <!-- Message Input Bar -->
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
    </div>

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
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
}

.conversation-top-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
}

.view-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-ink);
}

.view-subtitle {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  margin-top: 0.25rem;
}

/* Usage banner */
.usage-banner {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  background-color: #f7fbfc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0.625rem 1rem;
  font-size: 0.8125rem;
  flex-wrap: wrap;
}

.usage-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.usage-label {
  color: var(--color-subtle);
}

.usage-value {
  font-weight: 700;
  color: var(--color-teal);
}

.usage-meta-tag {
  color: var(--color-subtle);
  font-size: 0.75rem;
  display: flex;
  gap: 0.35rem;
}

.error-banner {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-text);
  padding: 0.875rem 1rem;
  border-radius: var(--radius-md);
  font-size: 0.9375rem;
}

/* Chat Layout */
.chat-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  min-height: 580px;
  max-height: 75vh;
  overflow: hidden;
  box-shadow: 0 4px 14px rgba(21, 62, 72, 0.05);
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

/* Sidebar */
.conversations-sidebar {
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  background-color: #fbfdfe;
  min-width: 0;
}

.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.sidebar-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--color-ink);
}

.create-conv-form {
  display: flex;
  gap: 0.5rem;
  width: 100%;
  min-width: 0;
}

.conv-title-input {
  min-height: 36px;
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
  flex: 1 1 0;
  min-width: 0;
}

.btn-new-conv {
  min-height: 36px;
  padding: 0.25rem 0.65rem;
  font-size: 0.8125rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.sidebar-loading,
.sidebar-empty {
  padding: 2rem 1rem;
  text-align: center;
  font-size: 0.8125rem;
  color: var(--color-subtle);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.conversations-list {
  list-style: none;
  overflow-y: auto;
  flex: 1;
  padding: 0.5rem 0;
}

.conversation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  cursor: pointer;
  border-bottom: 1px solid #f0f6f8;
  transition: background-color 0.15s ease;
}

.conversation-item:hover {
  background-color: #f0f7f8;
}

.conversation-item.is-active {
  background-color: #e5f1f4;
  border-left: 3px solid var(--color-teal);
}

.conversation-item:focus-visible {
  outline: 2px solid var(--color-teal);
  outline-offset: -2px;
}

.conv-item-content {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  flex: 1;
}

.conv-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-date {
  font-size: 0.75rem;
  color: var(--color-subtle);
}

.btn-delete-conv {
  background: transparent;
  border: none;
  color: var(--color-subtle);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.btn-delete-conv:hover {
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
}

/* Chat Main */
.chat-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.no-active-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-subtle);
  font-size: 0.9375rem;
  padding: 2rem;
  text-align: center;
}

.chat-thread-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 580px;
  width: 100%;
  min-width: 0;
}

.messages-stream {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  background-color: #fdfefe;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
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
  height: 100%;
  padding: 3rem 1.5rem;
  text-align: center;
  color: var(--color-subtle);
}

.empty-chat-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-ink);
}

.empty-chat-sub {
  font-size: 0.875rem;
  margin-top: 0.5rem;
  max-width: 420px;
  line-height: 1.5;
}

/* Message Cards */
.message-card {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
  max-width: 85%;
  line-height: 1.6;
  min-width: 0;
  box-sizing: border-box;
}

.message-user {
  align-self: flex-end;
  background-color: #e5f1f4;
  border: 1px solid #cfe0e5;
  color: var(--color-ink);
}

.message-assistant {
  align-self: flex-start;
  background-color: #ffffff;
  border: 1px solid var(--color-border);
  box-shadow: 0 2px 8px rgba(21, 62, 72, 0.04);
}

.message-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.message-role-label {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--color-teal);
  letter-spacing: 0.05em;
}

.message-status-pill {
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-sm);
  font-weight: 600;
}

.status-answered {
  background-color: #eaf6f0;
  color: #115e45;
}

.status-insufficient {
  background-color: #fff9e6;
  color: #855d00;
}

.status-clarify {
  background-color: #fff2c4;
  color: #78350f;
}

.status-unavailable {
  background-color: #faeaea;
  color: #8e1f1f;
}

.message-content {
  font-size: 0.9375rem;
  color: var(--color-ink);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* Citations */
.citations-container {
  border-top: 1px dashed var(--color-border);
  padding-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
  min-width: 0;
}

.citations-heading {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-teal);
}

.citations-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
  min-width: 0;
}

.citation-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
  flex-wrap: wrap;
  background-color: #f7fbfc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 0.45rem 0.75rem;
  font-size: 0.8125rem;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.citation-card.is-deleted {
  background-color: #fdf6f6;
  border-color: #f3d4d4;
  opacity: 0.8;
}

.citation-main {
  display: flex;
  align-items: center;
  gap: 0.35rem 0.5rem;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1 1 auto;
}

.cite-place-name {
  font-weight: 600;
  color: var(--color-ink);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.cite-date {
  color: var(--color-subtle);
  font-size: 0.75rem;
  white-space: nowrap;
}

.citation-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem 0.5rem;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.cite-state-pill {
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-sm);
  font-weight: 600;
}

.cite-current {
  background-color: #eaf6f0;
  color: #115e45;
}

.cite-changed {
  background-color: #fff9e6;
  color: #855d00;
}

.cite-deleted {
  background-color: #faeaea;
  color: #8e1f1f;
}

.btn-cite-inspect {
  background: transparent;
  border: 1px solid var(--color-teal);
  color: var(--color-teal);
  padding: 0.2rem 0.55rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.15s ease;
  min-height: 28px;
  white-space: nowrap;
}

.btn-cite-inspect:hover {
  background-color: var(--color-teal);
  color: #ffffff;
}

.cite-deleted-tip {
  font-size: 0.75rem;
  color: var(--color-subtle);
}

/* Sending Placeholder */
.sending-placeholder {
  opacity: 0.85;
}

.assistant-thinking-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
}

.thinking-text {
  font-size: 0.875rem;
  color: var(--color-subtle);
  font-style: italic;
}

/* Chat Input Bar */
.chat-input-bar {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--color-border);
  background-color: #ffffff;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.chat-form {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
  width: 100%;
  min-width: 0;
}

.chat-textarea {
  resize: none;
  min-height: 44px;
  font-size: 0.9375rem;
  line-height: 1.4;
  padding: 0.5rem 0.75rem;
  flex: 1 1 0;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}

.send-btn {
  height: 44px;
  white-space: nowrap;
  flex-shrink: 0;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.page-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(23, 107, 104, 0.2);
  border-top-color: var(--color-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.page-spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(23, 107, 104, 0.3);
  border-top-color: var(--color-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 0.9375rem;
  color: var(--color-subtle);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Responsive */
@media (max-width: 768px) {
  .chat-layout {
    grid-template-columns: minmax(0, 1fr);
    max-height: none;
    width: 100%;
    min-width: 0;
  }

  .conversations-sidebar {
    border-right: none;
    border-bottom: 1px solid var(--color-border);
    max-height: 220px;
    width: 100%;
    min-width: 0;
  }

  .chat-thread-container {
    min-height: 450px;
    width: 100%;
    min-width: 0;
  }

  .messages-stream {
    padding: 1rem 0.75rem;
    gap: 1rem;
    width: 100%;
    min-width: 0;
  }

  .message-card {
    max-width: 100%;
    padding: 0.75rem 0.875rem;
    width: 100%;
  }

  .message-header {
    flex-wrap: wrap;
    gap: 0.35rem 0.5rem;
  }

  .citation-card {
    padding: 0.5rem 0.625rem;
    gap: 0.5rem;
  }

  .citation-main {
    width: 100%;
    justify-content: space-between;
  }

  .citation-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .chat-input-bar {
    padding: 0.75rem 0.625rem;
    width: 100%;
    min-width: 0;
  }

  .chat-form {
    gap: 0.5rem;
  }

  .send-btn {
    padding: 0.5rem 0.75rem;
  }
}
</style>
