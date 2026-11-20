<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { PhotoDTO, PhotoCaptionUpdate } from '../types/photo'
import PhotoViewer from './PhotoViewer.vue'
import ConfirmDialog from './ConfirmDialog.vue'

const props = withDefaults(
  defineProps<{
    photos: PhotoDTO[]
    coverPhotoId?: string | null
    loading?: boolean
    canSetCover?: boolean
    canReorder?: boolean
    canDelete?: boolean
    canEditCaption?: boolean
    saveCaption?: (payload: PhotoCaptionUpdate) => Promise<void>
    emptyText?: string
    emptyHint?: string
    compactEmpty?: boolean
  }>(),
  {
    coverPhotoId: null,
    loading: false,
    canSetCover: false,
    canReorder: false,
    canDelete: true,
    canEditCaption: true,
    emptyText: '尚未新增任何照片'
  }
)

const emit = defineEmits<{
  (e: 'set-cover', photoId: string): void
  (e: 'reorder', photoIds: string[]): void
  (e: 'delete', payload: { photoId: string; version: number }): void
  (e: 'retry', payload: { photoId: string; version: number }): void
  (e: 'refresh'): void
}>()

// Lightbox state
const viewerVisible = ref(false)
const selectedPhotoId = ref<string | null>(null)

function openViewer(photo: PhotoDTO) {
  selectedPhotoId.value = photo.id
  viewerVisible.value = true
}

function closeViewer() {
  viewerVisible.value = false
  selectedPhotoId.value = null
}

// Delete confirmation with multi-binding warning
const confirmDialogVisible = ref(false)
const confirmDialogTitle = ref('確認刪除照片')
const confirmDialogMessage = ref('')
const pendingDeletePhoto = ref<{ photoId: string; version: number } | null>(null)

function promptDeletePhoto(photo: PhotoDTO) {
  pendingDeletePhoto.value = { photoId: photo.id, version: photo.version }
  confirmDialogTitle.value = '確認刪除照片'
  const isMultiBound = !!(photo.bindings && photo.bindings.length > 1)
  confirmDialogMessage.value = isMultiBound
    ? '此照片同時關聯於多個旅程或足跡，刪除將會從所有手記中永久移除此照片。確定要刪除嗎？'
    : '確定要刪除這張照片嗎？此操作無法復原。'
  confirmDialogVisible.value = true
}

function handleConfirmDelete() {
  if (pendingDeletePhoto.value) {
    emit('delete', pendingDeletePhoto.value)
    pendingDeletePhoto.value = null
  }
  confirmDialogVisible.value = false
}

function handleCancelDelete() {
  confirmDialogVisible.value = false
  pendingDeletePhoto.value = null
}

function onViewerDelete(payload: { photoId: string; version: number }) {
  const photo = props.photos.find((p) => p.id === payload.photoId)
  if (photo) {
    promptDeletePhoto(photo)
  } else {
    pendingDeletePhoto.value = payload
    confirmDialogTitle.value = '確認刪除照片'
    confirmDialogMessage.value = '確定要刪除這張照片嗎？此操作無法復原。'
    confirmDialogVisible.value = true
  }
}

// Reordering
function canMoveLeft(idx: number): boolean {
  return idx > 0
}

function canMoveRight(idx: number): boolean {
  return idx < props.photos.length - 1
}

function movePhoto(idx: number, direction: 'left' | 'right') {
  if (direction === 'left' && idx <= 0) return
  if (direction === 'right' && idx >= props.photos.length - 1) return

  const targetIdx = direction === 'left' ? idx - 1 : idx + 1
  const reordered = [...props.photos]
  const temp = reordered[idx]
  reordered[idx] = reordered[targetIdx]
  reordered[targetIdx] = temp

  emit(
    'reorder',
    reordered.map((p) => p.id)
  )
}

// Bounded polling for photos in 'pending' | 'processing' state
let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollCount = 0
const MAX_POLLS = 10

const hasPendingPhotos = computed(() => {
  return props.photos.some((p) => p.status === 'pending' || p.status === 'processing')
})

function checkAndSchedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }

  if (!hasPendingPhotos.value || pollCount >= MAX_POLLS) {
    return
  }

  // Backoff: 2s, 3s, 4s, up to 8s
  const delay = Math.min(2000 + pollCount * 1000, 8000)
  pollTimer = setTimeout(() => {
    pollCount++
    emit('refresh')
  }, delay)
}

watch(
  hasPendingPhotos,
  (pending) => {
    if (pending) {
      checkAndSchedulePoll()
    } else {
      pollCount = 0
      if (pollTimer) {
        clearTimeout(pollTimer)
        pollTimer = null
      }
    }
  },
  { immediate: true }
)

watch(
  () => props.photos,
  () => {
    if (hasPendingPhotos.value) {
      checkAndSchedulePoll()
    }
  }
)

onBeforeUnmount(() => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <div class="photo-gallery-root">
    <!-- Loading skeleton -->
    <div v-if="loading" class="gallery-loading" role="status" aria-live="polite">
      <div class="page-spinner" aria-hidden="true"></div>
      <p>載入相簿中...</p>
    </div>

    <!-- Empty state -->
    <p v-else-if="photos.length === 0 && compactEmpty" class="compact-empty">尚無照片</p>
    <div v-else-if="photos.length === 0" class="gallery-empty">
      <div class="empty-icon-sm" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
      </div>
      <p class="empty-text">{{ emptyText }}</p>
      <p v-if="emptyHint" class="empty-hint">{{ emptyHint }}</p>
    </div>

    <!-- Photos Grid -->
    <div v-else class="gallery-grid">
      <div
        v-for="(photo, idx) in photos"
        :key="photo.id"
        class="photo-card"
        :class="{ 'is-cover': photo.id === coverPhotoId }"
      >
        <!-- Thumbnail with click-to-lightbox -->
        <div
          class="thumb-box"
          tabindex="0"
          role="button"
          :aria-label="`檢視照片：${photo.caption || photo.analysis?.summary || '旅途照片'}`"
          @click="openViewer(photo)"
          @keydown.enter="openViewer(photo)"
          @keydown.space.prevent="openViewer(photo)"
        >
          <img
            :src="photo.thumbnail_url || photo.url"
            :alt="photo.caption || photo.analysis?.summary || '相簿照片'"
            class="thumb-img"
            loading="lazy"
          />

          <!-- Cover Badge -->
          <span v-if="photo.id === coverPhotoId" class="badge-cover">
            ★ 封面
          </span>

          <!-- Processing Overlay -->
          <div
            v-if="photo.status === 'processing' || photo.status === 'pending'"
            class="thumb-status-overlay status-overlay-processing"
            title="AI 分析處理中"
          >
            <span class="spinner-small" aria-hidden="true"></span>
            <span class="status-overlay-text">分析中</span>
          </div>

          <!-- Failed Overlay -->
          <div
            v-else-if="photo.status === 'failed'"
            class="thumb-status-overlay status-overlay-failed"
            title="分析失敗"
          >
            <span class="status-overlay-text">分析失敗</span>
          </div>

          <!-- Blocked Overlay -->
          <div
            v-else-if="photo.status === 'blocked'"
            class="thumb-status-overlay status-overlay-blocked"
            title="安全封鎖"
          >
            <span class="status-overlay-text">已封鎖</span>
          </div>
        </div>

        <!-- Card Footer / Compact Icon Actions -->
        <div class="photo-card-actions">
          <!-- Reorder buttons -->
          <div v-if="canReorder" class="reorder-group">
            <button
              type="button"
              class="btn-icon-action"
              :disabled="!canMoveLeft(idx)"
              title="往前移"
              aria-label="往前移"
              @click.stop="movePhoto(idx, 'left')"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <button
              type="button"
              class="btn-icon-action"
              :disabled="!canMoveRight(idx)"
              title="往後移"
              aria-label="往後移"
              @click.stop="movePhoto(idx, 'right')"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </div>

          <!-- Set Cover Button -->
          <button
            v-if="canSetCover && photo.id !== coverPhotoId"
            type="button"
            class="btn-icon-action action-cover"
            title="設為封面照片"
            aria-label="設為封面照片"
            @click.stop="emit('set-cover', photo.id)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </button>

          <!-- Retry button if failed -->
          <button
            v-if="photo.status === 'failed'"
            type="button"
            class="btn-icon-action action-retry"
            title="重試 AI 分析"
            aria-label="重試 AI 分析"
            @click.stop="emit('retry', { photoId: photo.id, version: photo.version })"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
          </button>

          <!-- Delete Button (prompts ConfirmDialog) -->
          <button
            v-if="canDelete"
            type="button"
            class="btn-icon-action action-delete"
            title="刪除照片"
            aria-label="刪除照片"
            @click.stop="promptDeletePhoto(photo)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Reusable Lightbox Viewer -->
    <PhotoViewer
      :visible="viewerVisible"
      :photos="photos"
      :initial-photo-id="selectedPhotoId"
      :cover-photo-id="coverPhotoId"
      :can-edit-caption="canEditCaption"
      :show-cover-action="canSetCover"
      :show-delete-action="canDelete"
      @close="closeViewer"
      @set-cover="emit('set-cover', $event)"
      @delete="onViewerDelete"
      @retry="emit('retry', $event)"
      :save-caption="saveCaption"
    />

    <!-- Confirm Delete Dialog (reusable component with multi-binding warning) -->
    <ConfirmDialog
      :visible="confirmDialogVisible"
      :title="confirmDialogTitle"
      :message="confirmDialogMessage"
      confirm-text="刪除照片"
      confirmation-mode="keyword"
      :target-key="pendingDeletePhoto?.photoId"
      @confirm="handleConfirmDelete"
      @cancel="handleCancelDelete"
    />
  </div>
</template>

<style scoped>
.compact-empty { margin: .25rem 0; font-size: .8rem; color: var(--color-subtle); }
.photo-gallery-root {
  width: 100%;
}

.gallery-loading,
.gallery-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1.5rem 1rem;
  background-color: var(--color-paper);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-subtle);
  font-size: 0.875rem;
}

.empty-icon-sm {
  opacity: 0.6;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
}

.photo-card {
  display: flex;
  flex-direction: column;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.photo-card:hover {
  border-color: var(--color-maple);
  box-shadow: var(--shadow-sm);
}

.photo-card.is-cover {
  border-color: var(--color-amber);
  box-shadow: 0 0 0 1px var(--color-amber);
}

.thumb-box {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  cursor: pointer;
  background-color: var(--color-canvas);
}

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}

.thumb-box:hover .thumb-img {
  transform: scale(1.03);
}

.thumb-box:focus-visible {
  outline: 2px solid var(--color-maple);
  outline-offset: -2px;
}

.badge-cover {
  position: absolute;
  top: 4px;
  left: 4px;
  font-size: 0.6875rem;
  font-weight: 700;
  color: var(--color-amber-text);
  background-color: var(--color-amber-subtle);
  border: 1px solid var(--color-amber);
  padding: 0.1rem 0.35rem;
  border-radius: var(--radius-xs);
}

.thumb-status-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.25rem;
  text-align: center;
}

.status-overlay-processing {
  background-color: rgba(224, 182, 91, 0.75);
  color: #3D2D0B;
}

.status-overlay-failed {
  background-color: rgba(166, 47, 25, 0.75);
  color: #FFFFFF;
}

.status-overlay-blocked {
  background-color: rgba(69, 58, 50, 0.85);
  color: #FFFFFF;
}

.photo-card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0.5rem;
  background-color: var(--color-paper);
  border-top: 1px solid var(--color-border-light);
  gap: 0.35rem;
}

.reorder-group {
  display: flex;
  gap: 0.25rem;
}

.btn-icon-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  background-color: var(--color-paper);
  color: var(--color-ink-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-icon-action:hover:not(:disabled) {
  background-color: var(--color-canvas);
  border-color: var(--color-maple);
  color: var(--color-maple);
}

.btn-icon-action:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.btn-icon-action.action-cover:hover:not(:disabled) {
  background-color: var(--color-amber-subtle);
  border-color: var(--color-amber);
  color: var(--color-amber-text);
}

.btn-icon-action.action-retry:hover:not(:disabled) {
  background-color: var(--color-amber-subtle);
  border-color: var(--color-amber);
  color: var(--color-amber-text);
}

.btn-icon-action.action-delete {
  margin-left: auto;
  color: var(--color-error-text);
}

.btn-icon-action.action-delete:hover:not(:disabled) {
  background-color: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error-text);
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
