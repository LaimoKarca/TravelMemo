<script setup lang="ts">
import AppDialogFrame from '@/components/ui/AppDialogFrame.vue'
import { ref, watch } from 'vue'
import type { SearchEvent } from '@/types/search'
import type { EventDestination } from '@/types/travel'
import { getEvent } from '@/api/search'
import { listPhotos } from '@/api/photos'
import type { PhotoDTO } from '@/types/photo'
import { ApiError } from '@/api/auth'
import AppIcon from '@/components/ui/AppIcon.vue'
import PhotoGallery from '@/features/media/PhotoGallery.vue'

const props = defineProps<{
  visible: boolean
  eventId?: string | null
  initialEvent?: SearchEvent | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'jump', payload: EventDestination): void
}>()

const loading = ref(false)
const errorMessage = ref('')
const currentEvent = ref<SearchEvent | null>(null)
const isDeleted = ref(false)
const photos = ref<PhotoDTO[]>([])
const loadingPhotos = ref(false)
const photoError = ref(false)

let loadEventGen = 0

watch(
  () => [props.visible, props.eventId, props.initialEvent] as const,
  async ([visible, id, initEvt]) => {
    if (visible) {
      errorMessage.value = ''
      isDeleted.value = false
      photos.value = []
      loadingPhotos.value = false
      photoError.value = false

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

    } else {
      loadEventGen++
      loading.value = false
      currentEvent.value = null
      isDeleted.value = false
      errorMessage.value = ''
    }
  },
  { immediate: true }
)

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
    if (!fetched.trip_id) void loadPhotos(id, currentGen)
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

async function loadPhotos(id: string, generation: number) {
  loadingPhotos.value = true
  try {
    const result = await listPhotos({ event_id: id })
    if (generation === loadEventGen) photos.value = result.items
  } catch {
    if (generation === loadEventGen) photoError.value = true
  } finally {
    if (generation === loadEventGen) loadingPhotos.value = false
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
  <AppDialogFrame
    :visible="visible"
    class="modal-backdrop"
    labelled-by="source-modal-title"
    initial-focus=".btn-close"
    @close="handleClose"
  >
      <header class="dialog-header">
        <h3 id="source-modal-title" class="dialog-title">足跡詳情</h3>
        <button
          type="button"
          class="btn-close"
          aria-label="關閉對話框"
          @click="handleClose"
        >
          <AppIcon name="close" />
        </button>
      </header>

      <div v-if="loading && !currentEvent" class="loading-state" role="status" aria-live="polite">
        <div class="page-spinner ui-spinner ui-spinner--page" aria-hidden="true"></div>
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
        <p v-if="photoError" role="status">暫時無法載入照片。</p>
        <PhotoGallery v-if="!currentEvent.trip_id && (loadingPhotos || photos.length)" :key="currentEvent.id" :photos="photos" :loading="loadingPhotos" :can-delete="false" :can-edit-caption="false" @refresh="loadPhotos(currentEvent.id, loadEventGen)" />

      </div>

      <footer v-if="currentEvent && !isDeleted" class="dialog-footer">
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
          <span>{{ currentEvent.trip_id ? '前往手記' : '前往足跡' }}</span>
        </button>
      </footer>
  </AppDialogFrame>
</template>

<style scoped src="./SourceDetailModal.css"></style>
