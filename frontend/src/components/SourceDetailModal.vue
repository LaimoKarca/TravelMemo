<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { SearchEvent } from '../types/search'
import { getEvent } from '../api/search'
import { ApiError } from '../api/auth'

const props = defineProps<{
  visible: boolean
  eventId?: string | null
  initialEvent?: SearchEvent | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'jump', payload: { tripId: string; eventId: string }): void
}>()

const loading = ref(false)
const errorMessage = ref('')
const currentEvent = ref<SearchEvent | null>(null)
const isDeleted = ref(false)

let loadEventGen = 0
const modalRef = ref<HTMLElement | null>(null)
let previousActiveElement: HTMLElement | null = null

watch(
  () => [props.visible, props.eventId, props.initialEvent] as const,
  async ([visible, id, initEvt]) => {
    if (visible) {
      previousActiveElement = document.activeElement as HTMLElement | null
      errorMessage.value = ''
      isDeleted.value = false

      // Use initialEvent search snapshot as preview only while fetching fresh data
      if (initEvt) {
        currentEvent.value = initEvt
      } else {
        currentEvent.value = null
      }

      const targetId = id || initEvt?.id
      if (targetId) {
        await loadEvent(targetId)
      }

      await nextTick()
      focusFirstElement()
    } else {
      loadEventGen++
      loading.value = false
      currentEvent.value = null
      isDeleted.value = false
      errorMessage.value = ''
      if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
        previousActiveElement.focus()
      }
    }
  },
  { immediate: true }
)

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
})

async function loadEvent(id: string) {
  const currentGen = ++loadEventGen
  loading.value = true
  errorMessage.value = ''
  isDeleted.value = false

  try {
    const fetched = await getEvent(id)
    const activeTargetId = props.eventId || props.initialEvent?.id
    if (!props.visible || currentGen !== loadEventGen || activeTargetId !== id) {
      return
    }
    currentEvent.value = fetched
  } catch (err: any) {
    const activeTargetId = props.eventId || props.initialEvent?.id
    if (!props.visible || currentGen !== loadEventGen || activeTargetId !== id) {
      return
    }
    if (err instanceof ApiError && err.status === 404) {
      isDeleted.value = true
      currentEvent.value = null
      errorMessage.value = '此足跡紀錄已自旅程中移除（找不到此事件或已刪除）。'
    } else {
      errorMessage.value = err instanceof ApiError ? err.detail : '載入足跡詳情失敗，請稍後再試。'
    }
  } finally {
    if (props.visible && currentGen === loadEventGen) {
      loading.value = false
    }
  }
}

function focusFirstElement() {
  if (!modalRef.value) return
  const focusables = modalRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  )
  if (focusables.length > 0) {
    focusables[0].focus()
  }
}

function handleKeyDown(e: KeyboardEvent) {
  if (!props.visible || !modalRef.value) return

  if (e.key === 'Escape') {
    e.preventDefault()
    handleClose()
    return
  }

  if (e.key === 'Tab') {
    const focusables = modalRef.value.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    if (focusables.length === 0) return

    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }
}

function handleClose() {
  emit('close')
}

function handleJump() {
  if (!currentEvent.value) return
  emit('jump', {
    tripId: currentEvent.value.trip_id,
    eventId: currentEvent.value.id
  })
  handleClose()
}
</script>

<template>
  <div
    v-if="visible"
    class="modal-backdrop"
    role="presentation"
    @click.self="handleClose"
  >
    <div
      ref="modalRef"
      class="dialog-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-modal-title"
    >
      <header class="dialog-header">
        <h3 id="source-modal-title" class="dialog-title">足跡來源詳情</h3>
        <button
          type="button"
          class="btn-close"
          aria-label="關閉對話框"
          @click="handleClose"
        >
          ✕
        </button>
      </header>

      <div v-if="loading && !currentEvent" class="loading-state" role="status" aria-live="polite">
        <div class="page-spinner" aria-hidden="true"></div>
        <p class="loading-text">載入足跡最新資料中...</p>
      </div>

      <div v-if="errorMessage" class="error-banner" role="alert">
        {{ errorMessage }}
      </div>

      <div v-if="currentEvent" class="dialog-body">
        <div class="event-headline">
          <h4 class="place-name">{{ currentEvent.place_name }}</h4>
          <span v-if="currentEvent.category" class="category-pill">
            {{ currentEvent.category }}
          </span>
        </div>

        <div class="meta-grid">
          <div v-if="currentEvent.trip_name" class="meta-item">
            <span class="meta-label">所屬手記：</span>
            <span class="meta-value">{{ currentEvent.trip_name }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">造訪日期：</span>
            <span class="meta-value">{{ currentEvent.date }}</span>
          </div>
          <div v-if="currentEvent.time" class="meta-item">
            <span class="meta-label">造訪時間：</span>
            <span class="meta-value">{{ currentEvent.time }}</span>
          </div>
          <div v-if="currentEvent.city" class="meta-item">
            <span class="meta-label">所屬城市：</span>
            <span class="meta-value">{{ currentEvent.city }}</span>
          </div>
          <div v-if="currentEvent.address" class="meta-item full-width">
            <span class="meta-label">詳細地址：</span>
            <span class="meta-value">{{ currentEvent.address }}</span>
          </div>
        </div>

        <div v-if="currentEvent.notes" class="notes-section">
          <span class="notes-label">隨筆備忘：</span>
          <p class="notes-text">{{ currentEvent.notes }}</p>
        </div>

        <div class="version-info">
          <span>資料版本：第 {{ currentEvent.version }} 版</span>
        </div>
      </div>

      <footer class="dialog-footer">
        <button
          type="button"
          class="btn btn-secondary"
          @click="handleClose"
        >
          關閉
        </button>
        <button
          v-if="currentEvent && !isDeleted"
          type="button"
          class="btn btn-primary jump-btn"
          @click="handleJump"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
          <span>跳至原旅程修訂</span>
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(69, 58, 50, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.dialog-card {
  background-color: var(--color-paper);
  border-radius: var(--radius-lg);
  box-shadow: 0 10px 30px rgba(69, 58, 50, 0.15);
  border: 1px solid var(--color-border);
  width: 100%;
  max-width: 540px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--color-border);
}

.dialog-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-ink);
}

.btn-close {
  background: transparent;
  border: none;
  font-size: 1.25rem;
  color: var(--color-subtle);
  cursor: pointer;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.btn-close:hover {
  color: var(--color-ink);
  background-color: var(--color-maple-subtle);
}

.dialog-body {
  padding: 1.5rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.event-headline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.place-name {
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--color-ink);
}

.category-pill {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-amber-text);
  background-color: var(--color-amber-subtle);
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-sm);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem 1rem;
  background-color: var(--color-canvas);
  padding: 1rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.meta-item.full-width {
  grid-column: 1 / -1;
}

.meta-label {
  font-size: 0.75rem;
  color: var(--color-subtle);
  font-weight: 500;
}

.meta-value {
  font-size: 0.9375rem;
  color: var(--color-ink);
  font-weight: 600;
}

.notes-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.notes-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-maple);
}

.notes-text {
  font-size: 0.9375rem;
  color: var(--color-ink);
  line-height: 1.6;
  white-space: pre-line;
  background-color: var(--color-canvas);
  padding: 0.75rem;
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-maple);
}

.version-info {
  font-size: 0.75rem;
  color: var(--color-subtle);
  text-align: right;
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--color-border);
  background-color: var(--color-paper);
}

.jump-btn {
  display: inline-flex;
  gap: 0.5rem;
}

.error-banner {
  padding: 1rem 1.5rem;
  color: var(--color-error-text);
  background-color: var(--color-error-bg);
  border-bottom: 1px solid var(--color-error-border);
  font-size: 0.9375rem;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  gap: 1rem;
}

.page-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(169, 85, 53, 0.2);
  border-top-color: var(--color-maple);
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

@media (max-width: 600px) {
  .dialog-card {
    max-height: 95vh;
  }

  .dialog-header {
    padding: 1rem;
  }

  .dialog-body {
    padding: 1rem;
    gap: 1rem;
  }

  .meta-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.5rem;
    padding: 0.75rem;
  }

  .dialog-footer {
    padding: 0.75rem 1rem;
    flex-direction: column-reverse;
  }

  .dialog-footer .btn {
    width: 100%;
    justify-content: center;
    min-height: 44px;
  }
}
</style>
