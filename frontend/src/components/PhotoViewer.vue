<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { PhotoDTO, PhotoCaptionUpdate } from '../types/photo'
import AppIcon from './AppIcon.vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    photos: PhotoDTO[]
    initialPhotoId?: string | null
    canEditCaption?: boolean
    saveCaption?: (payload: PhotoCaptionUpdate) => Promise<void>
    coverPhotoId?: string | null
    showCoverAction?: boolean
    showDeleteAction?: boolean
    showSaveToJournalAction?: boolean
  }>(),
  {
    initialPhotoId: null,
    canEditCaption: false,
    coverPhotoId: null,
    showCoverAction: false,
    showDeleteAction: false,
    showSaveToJournalAction: false
  }
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'set-cover', photoId: string): void
  (e: 'delete', payload: { photoId: string; version: number }): void
  (e: 'retry', payload: { photoId: string; version: number }): void
  (e: 'save-to-journal', photo: PhotoDTO): void
}>()

const currentIndex = ref(0)
const editingCaption = ref(false)
const captionInput = ref('')
const savingCaption = ref(false)
const captionError = ref('')
const captionVersion = ref(0)
let captionGeneration = 0
const dialogRef = ref<HTMLElement | null>(null)
const launcherRef = ref<HTMLElement | null>(null)

const currentPhoto = computed<PhotoDTO | null>(() => {
  if (!props.photos || props.photos.length === 0) return null
  if (currentIndex.value < 0 || currentIndex.value >= props.photos.length) {
    return props.photos[0]
  }
  return props.photos[currentIndex.value]
})

const isCover = computed(() => {
  if (!currentPhoto.value || !props.coverPhotoId) return false
  return currentPhoto.value.id === props.coverPhotoId
})

watch(
  () => props.visible,
  (val) => {
    captionGeneration++
    savingCaption.value = false
    captionError.value = ''
    if (val) {
      launcherRef.value = document.activeElement as HTMLElement | null
      const idx = props.photos.findIndex((p) => p.id === props.initialPhotoId)
      currentIndex.value = idx >= 0 ? idx : 0
      editingCaption.value = false
      captionInput.value = currentPhoto.value?.caption || ''
      nextTick(() => {
        dialogRef.value?.focus()
      })
    } else {
      nextTick(() => {
        launcherRef.value?.focus()
      })
    }
  },
  { immediate: true }
)

watch(currentPhoto, (photo, previous) => {
  if (photo?.id !== previous?.id) {
    captionGeneration++
    savingCaption.value = false
    editingCaption.value = false
    captionError.value = ''
  }
  if (photo && !editingCaption.value) {
    captionInput.value = photo.caption || ''
  }
})

function prevPhoto() {
  if (props.photos.length <= 1 || savingCaption.value) return
  editingCaption.value = false
  currentIndex.value = (currentIndex.value - 1 + props.photos.length) % props.photos.length
}

function nextPhoto() {
  if (props.photos.length <= 1 || savingCaption.value) return
  editingCaption.value = false
  currentIndex.value = (currentIndex.value + 1) % props.photos.length
}

async function handleSaveCaption() {
  if (!currentPhoto.value || !props.saveCaption || savingCaption.value) return
  const generation = ++captionGeneration
  savingCaption.value = true
  captionError.value = ''
  try {
    await props.saveCaption({ photoId: currentPhoto.value.id, caption: captionInput.value.trim(), version: captionVersion.value })
    if (generation === captionGeneration) editingCaption.value = false
  } catch {
    if (generation === captionGeneration) captionError.value = '儲存失敗，請稍後再試。'
  } finally {
    if (generation === captionGeneration) savingCaption.value = false
  }
}

function startCaptionEdit() { captionInput.value = currentPhoto.value?.caption || ''; captionVersion.value = currentPhoto.value?.version || 0; captionError.value = ''; editingCaption.value = true }
function cancelCaptionEdit() { if (!savingCaption.value) { editingCaption.value = false; captionError.value = '' } }

function handleRetry() {
  if (!currentPhoto.value) return
  emit('retry', {
    photoId: currentPhoto.value.id,
    version: currentPhoto.value.version
  })
}

function handleDelete() {
  if (!currentPhoto.value) return
  emit('delete', {
    photoId: currentPhoto.value.id,
    version: currentPhoto.value.version
  })
}

function handleKeyDown(e: KeyboardEvent) {
  if (!props.visible) return
  if (document.querySelector('.confirmation-backdrop')) return

  if (e.key === 'Tab' && dialogRef.value) {
    const focusables = Array.from(dialogRef.value.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), [tabindex="0"]'))
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (!first || !last) { e.preventDefault(); return }
    const active = document.activeElement
    if (!dialogRef.value.contains(active) || active === dialogRef.value || (e.shiftKey ? active === first : active === last)) {
      e.preventDefault()
      ;(e.shiftKey ? last : first).focus()
    }
    return
  }

  if (e.key === 'Escape') {
    e.preventDefault()
    if (editingCaption.value) cancelCaptionEdit()
    else emit('close')
  } else if (e.key === 'ArrowLeft') {
    if (!editingCaption.value) {
      e.preventDefault()
      prevPhoto()
    }
  } else if (e.key === 'ArrowRight') {
    if (!editingCaption.value) {
      e.preventDefault()
      nextPhoto()
    }
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  captionGeneration++
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<template>
  <div
    v-if="visible && currentPhoto"
    ref="dialogRef"
    class="lightbox-backdrop"
    role="dialog"
    aria-modal="true"
    aria-label="照片檢視器"
    tabindex="-1"
    @click.self="emit('close')"
  >
    <div class="lightbox-container">
      <!-- Top Bar: Counter & Close button -->
      <header class="lightbox-header">
        <div class="lightbox-counter">
          <span v-if="photos.length > 1">{{ currentIndex + 1 }} / {{ photos.length }}</span>
          <span v-if="isCover" class="lightbox-cover-badge">★ 封面照片</span>
        </div>

        <div class="lightbox-header-actions">
          <button
            v-if="showCoverAction && !isCover"
            type="button"
            class="btn btn-secondary btn-sm"
            @click="emit('set-cover', currentPhoto.id)"
          >
            設為封面
          </button>
          <button
            v-if="showSaveToJournalAction"
            type="button"
            class="btn btn-secondary btn-sm"
            @click="emit('save-to-journal', currentPhoto)"
          >
            存入手記
          </button>
          <button
            v-if="showDeleteAction"
            type="button"
            class="viewer-icon btn-delete-text"
            aria-label="刪除照片" title="刪除照片"
            :disabled="savingCaption"
            @click="handleDelete"
          >
            <AppIcon name="trash" />
          </button>
          <button
            type="button"
            class="lightbox-close-btn"
            aria-label="關閉預覽"
            @click="emit('close')"
          >
            <AppIcon name="close" />
          </button>
        </div>
      </header>

      <!-- Main Viewer Area -->
      <div class="lightbox-body">
        <button
          v-if="photos.length > 1"
          type="button"
          class="nav-arrow nav-prev"
          aria-label="上一張照片"
          @click="prevPhoto"
        >
          ‹
        </button>

        <div class="lightbox-media-wrapper">
          <img
            :src="currentPhoto.url || currentPhoto.thumbnail_url"
            :alt="currentPhoto.caption || currentPhoto.analysis?.summary || '旅途照片'"
            class="lightbox-image"
          />
        </div>

        <button
          v-if="photos.length > 1"
          type="button"
          class="nav-arrow nav-next"
          aria-label="下一張照片"
          @click="nextPhoto"
        >
          ›
        </button>
      </div>

      <!-- Info & Analysis Footer -->
      <footer class="lightbox-footer">
        <!-- Caption Row -->
        <div class="caption-row">
          <template v-if="editingCaption">
            <input
              v-model="captionInput"
              type="text"
              class="form-input caption-input"
              placeholder="新增照片說明..."
              maxlength="500"
              aria-label="照片說明"
              :disabled="savingCaption"
              @keydown.enter.prevent="!$event.isComposing && handleSaveCaption()"
            />
            <button
              type="button"
              class="viewer-icon"
              aria-label="返回照片說明" title="返回"
              :disabled="savingCaption"
              @click="cancelCaptionEdit"
            >
              <AppIcon name="back" />
            </button>
            <button
              type="button"
              class="viewer-icon caption-save"
              :aria-label="savingCaption ? '正在儲存說明' : '儲存說明'" title="儲存說明"
              :disabled="savingCaption"
              @click="handleSaveCaption"
            >
              <span v-if="savingCaption" class="spinner-small" aria-hidden="true"></span><AppIcon v-else name="save" />
            </button>
          </template>
          <template v-else>
            <p class="photo-caption-text">
              {{ currentPhoto.caption || '尚未填寫照片說明' }}
            </p>
            <button
              v-if="canEditCaption && saveCaption"
              type="button"
              class="viewer-icon edit-caption-btn"
              aria-label="編輯照片說明" title="編輯說明"
              @click="startCaptionEdit"
            >
              <AppIcon name="edit" />
            </button>
          </template>
        </div>
        <p v-if="captionError" class="caption-error" role="alert">{{ captionError }}</p>

        <!-- Status & Analysis Details -->
        <div class="analysis-panel">
          <div v-if="currentPhoto.status === 'processing' || currentPhoto.status === 'pending'" class="status-chip status-processing">
            <span class="spinner-small" aria-hidden="true"></span>
            <span>AI 分析中...</span>
          </div>
          <div v-else-if="currentPhoto.status === 'failed'" class="status-chip status-failed">
            <span>分析失敗</span>
            <button type="button" class="btn-link retry-btn" @click="handleRetry">
              重試分析
            </button>
          </div>
          <div v-else-if="currentPhoto.status === 'blocked'" class="status-chip status-blocked">
            <span>安全檢查不通過</span>
          </div>

          <!-- Ready Analysis Info -->
          <div v-if="currentPhoto.status === 'ready' && currentPhoto.analysis" class="analysis-content">
            <p v-if="currentPhoto.analysis.summary" class="analysis-summary">
              <span class="analysis-label">AI 場景摘要：</span>{{ currentPhoto.analysis.summary }}
            </p>

            <div v-if="currentPhoto.analysis.tags && currentPhoto.analysis.tags.length > 0" class="analysis-tags">
              <span v-for="tag in currentPhoto.analysis.tags" :key="tag" class="tag-pill">
                #{{ tag }}
              </span>
            </div>

            <p v-if="currentPhoto.analysis.visible_text && (Array.isArray(currentPhoto.analysis.visible_text) ? currentPhoto.analysis.visible_text.length > 0 : !!currentPhoto.analysis.visible_text)" class="analysis-ocr">
              <span class="analysis-label">偵測文字：</span>
              <span>{{ Array.isArray(currentPhoto.analysis.visible_text) ? currentPhoto.analysis.visible_text.join(' · ') : currentPhoto.analysis.visible_text }}</span>
            </p>

            <div v-if="currentPhoto.analysis.place_candidates && currentPhoto.analysis.place_candidates.length > 0" class="analysis-places">
              <span class="analysis-label">推測地點：</span>
              <span>{{ currentPhoto.analysis.place_candidates.join(', ') }}</span>
            </div>

            <p v-if="currentPhoto.analysis.date_candidate" class="analysis-date">
              <span class="analysis-label">推測時間：</span>{{ currentPhoto.analysis.date_candidate }}
            </p>
          </div>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.lightbox-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(30, 24, 20, 0.88);
  backdrop-filter: blur(4px);
  z-index: 1500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.lightbox-container {
  display: flex;
  flex-direction: column;
  max-width: 960px;
  width: 100%;
  max-height: 94vh;
  background-color: var(--color-paper);
  border-radius: var(--radius-md);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
  overflow: hidden;
}

.lightbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: .25rem .75rem;
  min-height: 52px;
  box-sizing: border-box;
  background-color: var(--color-paper);
  border-bottom: 1px solid var(--color-border-light);
}

.lightbox-counter {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-ink-secondary);
}

.lightbox-cover-badge {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-amber-text);
  background-color: var(--color-amber-subtle);
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-xs);
}

.lightbox-header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.lightbox-close-btn {
  background: transparent;
  border: none;
  font-size: 1.25rem;
  color: var(--color-ink);
  cursor: pointer;
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;
}

.lightbox-close-btn:hover {
  background-color: var(--color-canvas);
}

.lightbox-body {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #1A1512;
  min-height: 280px;
  max-height: 58vh;
  overflow: hidden;
}

.lightbox-media-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  max-height: 58vh;
}

.lightbox-image {
  max-width: 100%;
  max-height: 58vh;
  object-fit: contain;
  user-select: none;
}

.nav-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background-color: rgba(69, 58, 50, 0.65);
  color: #FFFFFF;
  border: none;
  width: 44px;
  height: 44px;
  font-size: 2rem;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  cursor: pointer;
  transition: background-color 0.15s ease;
  z-index: 2;
}

.nav-arrow:hover {
  background-color: rgba(169, 85, 53, 0.9);
}

.nav-prev {
  left: 0.75rem;
}

.nav-next {
  right: 0.75rem;
}

.lightbox-footer {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background-color: var(--color-paper);
  border-top: 1px solid var(--color-border-light);
  overflow-y: auto;
  max-height: 30vh;
}

.caption-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: nowrap;
  min-width: 0;
}

.photo-caption-text {
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--color-ink);
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.caption-input {
  flex: 1 1 0;
  width: 0;
  min-width: 0;
  font-size: 16px;
}

.viewer-icon { width: 40px; height: 40px; flex: 0 0 40px; display: inline-flex; align-items: center; justify-content: center; padding: 0; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--color-maple); cursor: pointer; }
.viewer-icon:hover:not(:disabled) { background: var(--color-maple-subtle); }
.viewer-icon:disabled { opacity: .5; cursor: wait; }
.caption-error { font-size: .8rem; color: var(--color-error-text); }

.analysis-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.25rem 0.6rem;
  border-radius: var(--radius-xs);
  align-self: flex-start;
}

.status-processing {
  background-color: var(--color-amber-subtle);
  color: var(--color-amber-text);
}

.status-failed {
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
}

.status-blocked {
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
}

.retry-btn {
  font-size: 0.75rem;
  min-height: auto;
  padding: 0;
  margin-left: 0.25rem;
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.8125rem;
  color: var(--color-ink-secondary);
  background-color: var(--color-canvas);
  padding: 0.625rem 0.875rem;
  border-radius: var(--radius-sm);
}

.analysis-label {
  font-weight: 600;
  color: var(--color-subtle);
}

.analysis-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.tag-pill {
  font-size: 0.75rem;
  color: var(--color-maple);
  background-color: var(--color-maple-subtle);
  padding: 0.1rem 0.45rem;
  border-radius: var(--radius-xs);
}

.btn-delete-text {
  color: var(--color-error-text);
}

.spinner-small {
  width: 12px;
  height: 12px;
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
