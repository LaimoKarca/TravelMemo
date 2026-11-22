<script setup lang="ts">
import AppDialogFrame from '@/components/ui/AppDialogFrame.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import LocationLink from '@/features/footprints/LocationLink.vue'
import { ref, reactive, toRef, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type {
  ChatDraft,
  ChatWorkspaceState,
  ConversationSummary,
  Message,
  Citation,
  MessageStatus,
  PhotoCitation
} from '@/types/conversation'
import type { PhotoDTO } from '@/types/photo'
import type { Trip, Event as TravelEvent } from '@/types/travel'
import {
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  enqueueMessage, getChatRequest, listChatRequests
} from '@/api/conversation'
import { listTrips, getTrip } from '@/api/travel'
import { bindPhoto } from '@/api/photos'
import { ApiError, getCsrfToken } from '@/api/auth'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import PhotoPicker from '@/features/media/PhotoPicker.vue'
import PhotoViewer from '@/features/media/PhotoViewer.vue'

const props = withDefaults(defineProps<{ accountId?: string; workspace?: ChatWorkspaceState }>(), { accountId: 'current' })
const storageKey = () => `travelmemo.chat.${props.accountId}`
function rememberConversation(id: string | null) {
  try { if (id) localStorage.setItem(storageKey(), id); else localStorage.removeItem(storageKey()) } catch { /* Storage can be unavailable in private browsing. */ }
}
const emit = defineEmits<{
  (e: 'open-trip', tripId: string): void
  (e: 'view-citation', citation: Citation): void
  (e: 'jump-trip', payload: { tripId: string; eventId: string }): void
}>()

// State
const chatWorkspace = props.workspace ?? reactive<ChatWorkspaceState>({ drafts: new Map(), conversations: [] })
const conversations = toRef(chatWorkspace, 'conversations')
const activeConversationId = ref<string | null>(null)
const messages = ref<Message[]>([])

const loadingConversations = ref(false)
const loadingMessages = ref(false)
const sendingMessage = ref(false)

const isHistoryOpen = ref(false)
const activeConversation = computed(() => {
  return conversations.value.find((c) => c.id === activeConversationId.value) || null
})

function onHistoryToggle(e: Event) {
  isHistoryOpen.value = (e.target as HTMLDetailsElement).open
}

const errorMessage = ref('')
const composerInputRef = ref<HTMLTextAreaElement | null>(null)
const { drafts } = chatWorkspace
function emptyDraft(): ChatDraft {
  return { text: '', photos: [], uploading: false, uploadError: '', submitting: false, acceptedRequestId: null }
}
function draftFor(id: string | null) {
  if (!drafts.has(id)) drafts.set(id, emptyDraft())
  return drafts.get(id)!
}
draftFor(null)
const activeDraft = computed(() => drafts.get(activeConversationId.value) ?? drafts.get(null)!)
const inputContent = computed({
  get: () => activeDraft.value.text,
  set: text => { activeDraft.value.text = text }
})
const stagedChatPhotos = computed({
  get: () => activeDraft.value.photos,
  set: photos => { activeDraft.value.photos = photos }
})

function beginComposerUpload() {
  const draft = activeDraft.value
  draft.uploading = true
  draft.uploadError = ''
  return {
    add: (photo: PhotoDTO) => { draft.photos.push(photo) },
    finish: (error: string) => { draft.uploading = false; draft.uploadError = error }
  }
}

let composing = false
watch(activeDraft, () => { composing = false })
function onComposerKeydown(event: KeyboardEvent) {
  if (composing || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void handleSendMessage()
}

// Save to Journal modal state
const showSaveModal = ref(false)
const photoToSave = ref<PhotoDTO | null>(null)
const availableTrips = ref<Trip[]>([])
const tripEventsForSave = ref<TravelEvent[]>([])
const saveSelectedTripId = ref('')
const saveSelectedEventId = ref('')
const savingToJournal = ref(false)
const saveSuccessMessage = ref('')
const saveErrorMessage = ref('')

// Lightbox viewer state
const viewerVisible = ref(false)
const viewerPhotos = ref<PhotoDTO[]>([])
const viewerInitialPhotoId = ref<string | null>(null)

function openLightbox(photo: PhotoDTO, photosList: PhotoDTO[] = []) {
  viewerInitialPhotoId.value = photo.id
  viewerPhotos.value = photosList.length > 0 ? photosList : [photo]
  viewerVisible.value = true
}

function openCitationPhoto(pCite: PhotoCitation) {
  const syntheticPhoto: PhotoDTO = {
    id: pCite.photo_id,
    caption: pCite.caption || '',
    version: pCite.version || 1,
    analysis_version: 1,
    status: 'ready',
    analysis: {
      summary: pCite.caption || '',
      visible_text: [],
      tags: [],
      place_candidates: [],
      date_candidate: null,
      uncertainties: []
    },
    width: 0,
    height: 0,
    size_bytes: 0,
    thumbnail_size_bytes: 0,
    created_at: '',
    updated_at: '',
    bindings: [],
    url: pCite.url,
    thumbnail_url: pCite.thumbnail_url
  }
  openLightbox(syntheticPhoto, [syntheticPhoto])
}

async function openSaveToJournalModal(photo: PhotoDTO) {
  photoToSave.value = photo
  saveSelectedTripId.value = ''
  saveSelectedEventId.value = ''
  tripEventsForSave.value = []
  saveSuccessMessage.value = ''
  saveErrorMessage.value = ''
  showSaveModal.value = true

  try {
    const res = await listTrips()
    availableTrips.value = res.items || []
  } catch {
    // Non-blocking
  }
}

async function onSaveTripChange() {
  saveSelectedEventId.value = ''
  tripEventsForSave.value = []
  if (!saveSelectedTripId.value) return

  try {
    const detail = await getTrip(saveSelectedTripId.value)
    tripEventsForSave.value = detail.events || []
  } catch {
    // Non-blocking
  }
}

async function confirmSaveToJournal() {
  if (!photoToSave.value || !saveSelectedTripId.value) return
  savingToJournal.value = true
  saveSuccessMessage.value = ''
  saveErrorMessage.value = ''

  const kind = saveSelectedEventId.value ? 'event' : 'trip'
  const targetId = saveSelectedEventId.value || saveSelectedTripId.value

  try {
    await bindPhoto(photoToSave.value.id, kind, targetId)
    saveSuccessMessage.value = '已成功將照片存入旅行手記！'
    setTimeout(() => {
      showSaveModal.value = false
      photoToSave.value = null
    }, 1200)
  } catch (err: any) {
    saveErrorMessage.value = err instanceof ApiError ? err.detail : '加入手記失敗，請稍後再試。'
  } finally {
    savingToJournal.value = false
  }
}

function closeSaveModal() {
  showSaveModal.value = false
  photoToSave.value = null
}

function getAnswerScopeLabel(scope?: string): string {
  if (scope === 'image') return '照片依據'
  if (scope === 'mixed') return '回憶與照片依據'
  return '手記回憶依據'
}

let chatPollTimer: ReturnType<typeof setTimeout> | null = null
let chatPollCount = 0
let active = true
const hasPendingChatPhotos = computed(() => messages.value.some(message =>
  message.photos?.some(photo => photo.status === 'pending' || photo.status === 'processing')
))

function stopChatPhotoPoll() {
  if (chatPollTimer) clearTimeout(chatPollTimer)
  chatPollTimer = null
  chatPollCount = 0
}

function checkAndScheduleChatPoll() {
  const id = activeConversationId.value
  if (!active || !id || sendingMessage.value || !hasPendingChatPhotos.value || chatPollTimer || chatPollCount >= 10) return
  const generation = requestGeneration
  const delay = Math.min(2000 + chatPollCount * 1000, 8000)
  chatPollTimer = setTimeout(async () => {
    chatPollTimer = null
    const isCurrent = () => active && activeConversationId.value === id && requestGeneration === generation
    if (!isCurrent() || sendingMessage.value) return
    chatPollCount++
    try {
      const res = await listMessages(id)
      if (isCurrent() && !sendingMessage.value) messages.value = res.items || []
    } catch {
      // A transient read failure can be retried while these photos are pending.
    }
    if (isCurrent()) checkAndScheduleChatPoll()
  }, delay)
}

watch([hasPendingChatPhotos, sendingMessage], ([pending, sending]) => {
  if (pending && !sending) checkAndScheduleChatPoll()
  else stopChatPhotoPoll()
})

const hasPendingStagedPhotos = computed(() =>
  stagedChatPhotos.value.some(p => p.status === 'pending' || p.status === 'processing')
)
const hasUnreadyStagedPhotos = computed(() => stagedChatPhotos.value.some(p => p.status !== 'ready'))
const hasFailedOrBlockedStagedPhotos = computed(() =>
  stagedChatPhotos.value.some(p => p.status === 'failed' || p.status === 'blocked')
)

onBeforeUnmount(() => {
  active = false
  messageLoadGen++
  stopRequestPolling()
  stopChatPhotoPoll()
  window.removeEventListener('online', reconnectRequest)
})

// Generation counter to invalidate stale loads when switching or on create/delete
let messageLoadGen = 0

// Delete conversation confirm modal
const showDeleteConfirm = ref(false)
const conversationToDelete = ref<ConversationSummary | null>(null)
const deletingConversation = ref(false)

const messagesContainerRef = ref<HTMLElement | null>(null)

onMounted(async () => {
  await fetchConversations()
  if (!active) return
  let saved: string | null = null
  try { saved = localStorage.getItem(storageKey()) } catch { /* Storage is optional. */ }
  if (saved && conversations.value.some(c => c.id === saved)) await selectConversation(saved)
  else rememberConversation(null)
  if (active) window.addEventListener('online', reconnectRequest)
})

async function fetchConversations() {
  loadingConversations.value = true
  errorMessage.value = ''
  try {
    await reloadConversationsPreservingSelection(false)
    loadingConversations.value = false
    // Initial AI view remains a new blank chat rather than auto-selecting history
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '載入對話列表失敗，請稍後再試。'
    loadingConversations.value = false
  }
}

async function reloadConversationsPreservingSelection(ignoreFailure = true) {
  const knownIds = new Set(conversations.value.map(conversation => conversation.id))
  try {
    const res = await listConversations()
    if (!active) return
    const items = res.items || []
    const loadedIds = new Set(items.map(conversation => conversation.id))
    const createdWhileLoading = conversations.value.filter(conversation => !knownIds.has(conversation.id) && !loadedIds.has(conversation.id))
    conversations.value = [...createdWhileLoading, ...items]
  } catch (err) {
    if (!ignoreFailure) throw err
  }
}

async function selectConversation(id: string) {
  if (activeConversationId.value === id && messages.value.length > 0) return
  stopRequestPolling()
  stopChatPhotoPoll()
  sendingMessage.value = false
  draftFor(id)
  activeConversationId.value = id
  rememberConversation(id)
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
    await recoverRequests(id)
    if (currentGen === messageLoadGen) await scrollToBottom()
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

function handleStartNewConversation() {
  stopRequestPolling()
  stopChatPhotoPoll()
  sendingMessage.value = false
  rememberConversation(null)
  if (!activeConversationId.value && activeDraft.value.submitting) drafts.set(null, emptyDraft())
  messageLoadGen++
  activeConversationId.value = null
  messages.value = []
  loadingMessages.value = false
  errorMessage.value = ''
  nextTick(() => {
    composerInputRef.value?.focus()
  })
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
    drafts.delete(targetId)

    // If deleting the active conversation, reset to blank chat
    if (activeConversationId.value === targetId) {
      stopRequestPolling()
      stopChatPhotoPoll()
      rememberConversation(null)
      sendingMessage.value = false
      messageLoadGen++
      activeConversationId.value = null
      messages.value = []
      loadingMessages.value = false
    }
    showDeleteConfirm.value = false
    conversationToDelete.value = null
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '刪除對話失敗，請稍後再試。'
  } finally {
    deletingConversation.value = false
  }
}

let requestTimer: ReturnType<typeof setTimeout> | null = null
let requestGeneration = 0
type PendingRequest = { conversationId: string; requestId: string }
let pendingRequest: PendingRequest | null = null
let pollingRequest: PendingRequest | null = null
function stopRequestPolling() {
  requestGeneration++
  if (requestTimer) clearTimeout(requestTimer)
  requestTimer = null
  pendingRequest = null
}
function reconnectRequest() {
  if (pendingRequest) void pollRequest(pendingRequest.conversationId, pendingRequest.requestId, requestGeneration)
  else if (activeConversationId.value) void recoverRequests(activeConversationId.value)
}
async function recoverRequests(id: string) {
  const generation = requestGeneration
  try {
    const jobs = await listChatRequests(id)
    if (generation !== requestGeneration || activeConversationId.value !== id || pendingRequest) return
    const pending = jobs.items.find(j => j.status === 'queued' || j.status === 'running')
    if (pending) trackRequest(id, pending.id)
  } catch { /* History is still available; reconnect will retry request discovery. */ }
}
function trackRequest(id: string, rid: string) {
  if (pendingRequest) return
  sendingMessage.value = true
  pendingRequest = { conversationId: id, requestId: rid }
  void pollRequest(id, rid, requestGeneration)
}

watch([activeConversationId, () => activeDraft.value.acceptedRequestId, loadingMessages], ([id, rid, loading]) => {
  if (id && rid && !loading) trackRequest(id, rid)
})

async function pollRequest(id: string, rid: string, generation: number) {
  const request = pendingRequest
  const isCurrent = () => request === pendingRequest && generation === requestGeneration && activeConversationId.value === id
  if (!request || request.requestId !== rid || pollingRequest === request || !isCurrent()) return
  if (requestTimer) clearTimeout(requestTimer)
  pollingRequest = request
  try {
    const job = await getChatRequest(id, rid)
    if (!isCurrent()) return
    const history = await listMessages(id)
    if (!isCurrent()) return
    const optimistic = messages.value.find(m => m.id === 'pending-' + rid)
    messages.value = history.items || []
    if (optimistic && !messages.value.some(m => m.role === 'user' && m.content === optimistic.content && m.created_at >= optimistic.created_at) && (job.status === 'queued' || job.status === 'running')) messages.value.push(optimistic)
    if (job.message && !messages.value.some(m => m.id === job.message!.id)) messages.value.push(job.message)
    if (job.status === 'completed' || job.status === 'failed') {
      sendingMessage.value = false
      pendingRequest = null
      if (activeDraft.value.acceptedRequestId === rid) activeDraft.value.acceptedRequestId = null
      if (job.status === 'failed') errorMessage.value = job.error || '這次回覆未完成，請重新發問。'
      await reloadConversationsPreservingSelection()
      if (generation === requestGeneration) await scrollToBottom()
      return
    }
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 404)) {
      if (isCurrent()) {
        if (activeDraft.value.acceptedRequestId === rid) activeDraft.value.acceptedRequestId = null
        stopRequestPolling()
        sendingMessage.value = false
        errorMessage.value = err.detail
      }
      return
    }
    // An interrupted connection does not cancel work or create another request.
  } finally {
    if (pollingRequest === request) pollingRequest = null
  }
  if (isCurrent()) requestTimer = setTimeout(() => void pollRequest(id, rid, generation), navigator.onLine ? 1500 : 5000)
}
async function handleSendMessage() {
  const draft = activeDraft.value
  const text = draft.text
  const content = text.trim()
  const photos = [...draft.photos]
  if ((!content && !photos.length) || loadingMessages.value || sendingMessage.value || draft.submitting || draft.uploading || hasUnreadyStagedPhotos.value) return
  stopRequestPolling()
  const generation = requestGeneration
  const session = getCsrfToken()
  const isCurrentSession = () => session === getCsrfToken()
  const isCurrentView = () => generation === requestGeneration && draft === activeDraft.value
  let targetId = activeConversationId.value
  draft.submitting = true
  sendingMessage.value = true
  errorMessage.value = ''
  try {
    if (!targetId) {
      const created = await createConversation({})
      if (!isCurrentSession()) return
      conversations.value.unshift(created)
      targetId = created.id
      drafts.set(targetId, draft)
      if (isCurrentView()) {
        activeConversationId.value = targetId
        rememberConversation(targetId)
      }
      if (drafts.get(null) === draft) drafts.set(null, emptyDraft())
    }
    const rid = crypto.randomUUID()
    const payload = { content, ...(photos.length ? { photo_ids: photos.map(p => p.id) } : {}) }
    // Repeat only this exact idempotent request if its acknowledgement is lost.
    let accepted = false
    for (let attempt = 0; attempt < 2 && !accepted; attempt++) {
      if (!isCurrentSession()) return
      try { await enqueueMessage(targetId, rid, payload); accepted = true }
      catch (err) { if (err instanceof ApiError || attempt === 1) throw err }
    }
    if (!isCurrentSession()) return
    if (draft.text === text) draft.text = ''
    const sentPhotoIds = new Set(photos.map(photo => photo.id))
    draft.photos = draft.photos.filter(photo => !sentPhotoIds.has(photo.id))
    draft.acceptedRequestId = rid
    if (isCurrentView()) {
      messages.value.push({ id: 'pending-' + rid, role: 'user', content, status: 'answered', citations: [], photos, created_at: new Date().toISOString() })
      void scrollToBottom()
    }
  } catch (err) {
    if (isCurrentSession() && isCurrentView()) {
      sendingMessage.value = false
      errorMessage.value = err instanceof ApiError ? err.detail : '連線中斷；已送出的問題會繼續處理，重新連線後可接回回覆。'
      if (targetId) await recoverRequests(targetId)
    }
  } finally {
    draft.submitting = false
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
      return { text: '已更新', className: 'cite-changed' }
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
    <!-- Top Header: Title & Collapsed History -->
    <header class="conversation-header">
      <div class="header-main-row">
        <h2 class="view-title">AI 旅程助理</h2>
        <button
          type="button"
          class="btn btn-secondary btn-new-conv"
          :disabled="loadingConversations"
          @click="handleStartNewConversation"
        >
          + 新對話
        </button>
      </div>

      <!-- Compact History Toolbar with Collapsible Details/Summary -->
      <details
        class="history-details"
        :open="isHistoryOpen"
        role="region"
        aria-label="歷史對話紀錄"
        @toggle="onHistoryToggle"
      >
        <summary class="history-summary" :aria-expanded="isHistoryOpen">
          <span class="history-summary-left">
            <span class="history-summary-title">歷史對話 ({{ conversations.length }})</span>
            <span v-if="activeConversation" class="history-active-title">
              · {{ activeConversation.title || '無標題對話' }}
            </span>
          </span>
          <svg
            class="history-chevron"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </summary>

        <div class="conversation-toolbar" aria-label="歷史對話導覽">
          <div class="toolbar-top">
            <span class="toolbar-label">歷史對話紀錄</span>
          </div>

          <div v-if="loadingConversations" class="toolbar-loading" role="status" aria-live="polite">
            <div class="page-spinner-sm ui-spinner" aria-hidden="true"></div>
            <span>載入中...</span>
          </div>

          <div v-else-if="conversations.length === 0" class="toolbar-empty">
            <span>尚未建立對話。在下方輸入訊息即可直接交談。</span>
          </div>

          <ul v-else class="conversations-list" aria-label="對話列表">
            <li
              v-for="conv in conversations"
              :key="conv.id"
              class="conversation-item"
              :class="{ 'is-active': conv.id === activeConversationId }"
              @click="selectConversation(conv.id)"
            >
              <button
                type="button"
                class="conv-item-content conversation-select"
                :aria-pressed="conv.id === activeConversationId"
              >
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
      </details>
    </header>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Flattened Open Message Stream & Single Composer (No enclosing chat card) -->
    <main class="chat-main" aria-label="對話內容">
      <div class="chat-thread-container">
        <!-- Open Messages Stream -->
        <div
          ref="messagesContainerRef"
          class="messages-stream"
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
        >
          <div v-if="loadingMessages" class="chat-loading" role="status">
            <div class="page-spinner ui-spinner" aria-hidden="true"></div>
            <p class="loading-text">載入對話紀錄中...</p>
          </div>

          <div v-else-if="messages.length === 0" class="empty-chat-state">
            <p class="empty-chat-title">想找回哪段旅程？</p>
            <div class="empty-chat-examples"><span>我去過哪些咖啡店？</span><span>清水寺是哪天去的？</span></div>
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
            </header>

            <!-- Natural text in open stream -->
            <div class="message-content">
              {{ msg.content }}
            </div>

            <!-- Attached Photos (User or Assistant) -->
            <div
              v-if="msg.photos && msg.photos.length > 0"
              class="message-photos-grid"
            >
              <div
                v-for="photo in msg.photos"
                :key="photo.id"
                class="message-photo-item"
              >
                <div
                  class="photo-thumb-wrap"
                  tabindex="0"
                  role="button"
                  :aria-label="`檢視照片：${photo.caption || '照片'}`"
                  @click="openLightbox(photo, msg.photos || [])"
                  @keydown.enter="openLightbox(photo, msg.photos || [])"
                >
                  <img
                    :src="photo.thumbnail_url || photo.url"
                    :alt="photo.caption || '對話照片'"
                    class="message-photo-img"
                  />
                </div>
                <button
                  type="button"
                  class="btn-save-to-journal"
                  title="存入旅行手記"
                  @click="openSaveToJournalModal(photo)"
                >
                  存入手記
                </button>
              </div>
            </div>

            <!-- Citations: Flat text rows right below answer (No nested source cards) -->
            <div
              v-if="msg.role === 'assistant' && msg.citations && msg.citations.length > 0"
              class="citations-container"
            >
              <span class="citations-heading">足跡來源</span>
              <div class="citations-flat-list">
                <div
                  v-for="cite in msg.citations"
                  :key="cite.event_id"
                  class="citation-card citation-row"
                  :class="{ 'is-deleted': cite.state === 'deleted' }"
                >
                  <button v-if="cite.state !== 'deleted'" type="button" class="source-link" @click="handleCitationClick(cite)">{{ cite.place_name }} <span class="cite-date">{{ cite.date }}</span></button>
                  <span v-else class="deleted-source">{{ cite.place_name }} <span class="cite-date">{{ cite.date }}</span></span>
                  <small v-if="cite.state !== 'current'" class="source-note">{{ cite.state === 'changed' ? '已更新' : '已刪除' }}</small>
                  <LocationLink v-if="cite.state === 'current' && cite.map_url" :location="cite" show-label />
                </div>
              </div>
            </div>

            <div v-if="msg.trip_citations?.length" class="trip-citations">
              <button v-for="trip in msg.trip_citations" :key="trip.trip_id" type="button" class="trip-source-link" :disabled="trip.state === 'deleted'" @click="emit('open-trip', trip.trip_id)">{{ trip.name }} <small>{{ trip.start_date }} — {{ trip.end_date }}{{ trip.state === 'changed' ? '・已更新' : trip.state === 'deleted' ? '・已刪除' : '' }}</small></button>
            </div>
            <!-- Photo Citations -->
            <div
              v-if="msg.role === 'assistant' && msg.photo_citations && msg.photo_citations.length > 0"
              class="photo-citations-container"
            >
              <span class="citations-heading">照片來源</span>
              <div class="photo-citations-list">
                <div
                  v-for="pCite in msg.photo_citations"
                  :key="pCite.photo_id"
                  class="photo-citation-card"
                  :class="{ 'is-deleted': pCite.state === 'deleted' }"
                  tabindex="0"
                  role="button"
                  :aria-label="`檢視引用照片：${pCite.caption || '手記照片'}`"
                  @click="openCitationPhoto(pCite)"
                  @keydown.enter="openCitationPhoto(pCite)"
                >
                  <img
                    :src="pCite.thumbnail_url || pCite.url"
                    :alt="pCite.caption || '引用照片'"
                    class="cite-photo-thumb"
                  />
                  <div class="cite-photo-info">
                    <span class="cite-photo-caption">{{ pCite.caption || '手記照片' }}</span>
                    <span
                      v-if="pCite.state !== 'current'" class="source-note"
                      :class="getCitationStateBadge(pCite.state).className"
                    >
                      {{ getCitationStateBadge(pCite.state).text }}
                    </span>
                  </div>
                  <button
                    v-if="pCite.state !== 'deleted'"
                    type="button"
                    class="btn-save-cite-to-journal"
                    title="存入旅行手記"
                    @click.stop="openSaveToJournalModal({
                      id: pCite.photo_id,
                      caption: pCite.caption || '',
                      version: pCite.version || 1,
                      analysis_version: 1,
                      status: 'ready',
                      analysis: { summary: pCite.caption || '', visible_text: [], tags: [], place_candidates: [], date_candidate: null, uncertainties: [] },
                      width: 0,
                      height: 0,
                      size_bytes: 0,
                      thumbnail_size_bytes: 0,
                      created_at: '',
                      updated_at: '',
                      bindings: [],
                      url: pCite.url,
                      thumbnail_url: pCite.thumbnail_url
                    })"
                  >
                    存入手記
                  </button>
                </div>
              </div>
            </div>
          </article>

          <!-- Sending assistant indicator -->
          <div v-if="sendingMessage" class="message-card message-assistant sending-placeholder" role="status">
            <span class="message-role-label">手記助理</span>
            <div class="assistant-thinking-row">
              <div class="page-spinner-sm ui-spinner" aria-hidden="true"></div>
              <span class="thinking-text">正在翻閱旅程手記並檢索證據...</span>
            </div>
          </div>
        </div>

        <!-- Single Composer on page -->
        <footer class="chat-input-bar">
          <form class="chat-form" @submit.prevent="handleSendMessage">
            <div class="composer-picker-row">
              <PhotoPicker
                :key="activeConversationId ?? 'new'"
                v-model:photos="stagedChatPhotos"
                :begin-upload="beginComposerUpload"
                :disabled="activeDraft.uploading || activeDraft.submitting"
                :icon-only="true"
                :compact="true"
                :multiple="true"
                :max-photos="4"
                button-text="選取照片"
                camera-button-text="拍照"
              />

              <div v-if="activeDraft.uploadError" class="staged-alert-hint" role="alert">{{ activeDraft.uploadError }}</div>
              <div v-else-if="hasPendingStagedPhotos" class="reading-indicator" role="status" aria-live="polite">
                <div class="page-spinner-sm ui-spinner" aria-hidden="true"></div>
                <span class="reading-text">正在識別照片內容...</span>
              </div>

              <div v-else-if="hasFailedOrBlockedStagedPhotos" class="staged-alert-hint" role="alert">
                <span class="alert-icon" aria-hidden="true">⚠️</span>
                <span>照片未就緒，請重試或移除無法識別的照片</span>
              </div>
            </div>

            <label for="chat-message-input" class="sr-only">輸入對話訊息</label>
            <textarea
              id="chat-message-input"
              ref="composerInputRef"
              v-model="inputContent"
              class="form-input chat-textarea"
              placeholder="問問你的旅行回憶…"
              rows="2"
              :disabled="sendingMessage || loadingMessages || activeDraft.submitting"
              @compositionstart="composing = true"
              @compositionend="composing = false"
              @keydown.enter.exact="onComposerKeydown"
            ></textarea>

            <button
              type="submit"
              class="btn btn-primary send-btn"
              :disabled="sendingMessage || loadingMessages || activeDraft.submitting || activeDraft.uploading || hasUnreadyStagedPhotos || (!inputContent.trim() && stagedChatPhotos.length === 0)"
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

    <!-- Save Photo to Journal Modal -->
    <AppDialogFrame
      :visible="showSaveModal"
      :busy="savingToJournal"
      :dismiss-outside="false"
      class="chat-save-dialog"
      label="存入旅行手記"
      panel-class="save-modal-card editor-dialog"
      @close="closeSaveModal"
    >
        <div class="dialog-form-body">
        <h3 class="save-modal-title">存入旅行手記</h3>
        <p class="save-modal-desc">選擇要將這張照片加入的旅程手記或足跡：</p>

        <div class="form-group">
          <label for="save-trip-select" class="form-label">選擇旅程手記</label>
          <select
            id="save-trip-select"
            v-model="saveSelectedTripId"
            class="form-input form-select"
            @change="onSaveTripChange"
          >
            <option value="">-- 請選擇旅程 --</option>
            <option v-for="t in availableTrips" :key="t.id" :value="t.id">
              {{ t.name }}
            </option>
          </select>
        </div>

        <div v-if="saveSelectedTripId && tripEventsForSave.length > 0" class="form-group">
          <label for="save-event-select" class="form-label">選擇特定足跡（選填）</label>
          <select
            id="save-event-select"
            v-model="saveSelectedEventId"
            class="form-input form-select"
          >
            <option value="">綁定於整個旅程（相簿）</option>
            <option v-for="e in tripEventsForSave" :key="e.id" :value="e.id">
              {{ e.place_name }} ({{ e.date }})
            </option>
          </select>
        </div>

        <div v-if="saveSuccessMessage" class="save-success-banner" role="status">
          {{ saveSuccessMessage }}
        </div>
        <div v-if="saveErrorMessage" class="error-banner" role="alert">
          {{ saveErrorMessage }}
        </div>

        </div>
        <footer class="dialog-footer dialog-icon-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="savingToJournal"
            aria-label="返回" title="返回"
            @click="closeSaveModal"
          >
            <AppIcon name="back" />
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="savingToJournal || !saveSelectedTripId"
            :aria-label="savingToJournal ? '儲存中' : '確認加入手記'" title="加入手記"
            :aria-busy="savingToJournal"
            @click="confirmSaveToJournal"
          >
            <span v-if="savingToJournal" class="spinner-small" aria-hidden="true"></span><AppIcon v-else name="save" />
          </button>
        </footer>
    </AppDialogFrame>

    <!-- Reusable Lightbox Viewer -->
    <PhotoViewer
      :visible="viewerVisible"
      :photos="viewerPhotos"
      :initial-photo-id="viewerInitialPhotoId"
      :show-save-to-journal-action="true"
      @close="viewerVisible = false"
      @save-to-journal="openSaveToJournalModal"
    />

    <!-- Confirm Dialog for Deleting Conversation -->
    <ConfirmDialog
      :visible="showDeleteConfirm"
      title="確認刪除對話"
      confirm-text="刪除對話"
      confirmation-mode="keyword"
      :target-key="conversationToDelete?.id"
      :message="`確定要刪除「${conversationToDelete?.title || '此對話'}」嗎？此動作將清除對話內的問答紀錄。`"
      :loading="deletingConversation"
      @confirm="handleConfirmDelete"
      @cancel="showDeleteConfirm = false"
    />
  </section>
</template>

<style scoped src="./ConversationView.css"></style>
