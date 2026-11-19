<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import type { PhotoDTO } from '../types/photo'
import { uploadPhoto, retryPhoto, getPhoto } from '../api/photos'
import { ApiError } from '../api/auth'
import AppIcon from './AppIcon.vue'

const props = withDefaults(
  defineProps<{
    multiple?: boolean
    maxPhotos?: number
    disabled?: boolean
    initialPhotos?: PhotoDTO[]
    photos?: PhotoDTO[]
    autoUpload?: boolean
    buttonText?: string
    cameraButtonText?: string
    compact?: boolean
    iconOnly?: boolean
  }>(),
  {
    multiple: true,
    maxPhotos: Number.MAX_SAFE_INTEGER,
    disabled: false,
    initialPhotos: () => [],
    autoUpload: true,
    buttonText: '選取照片',
    cameraButtonText: '拍照',
    compact: false
  }
)

const emit = defineEmits<{
  (e: 'update:photos', photos: PhotoDTO[]): void
  (e: 'upload-complete', photo: PhotoDTO): void
  (e: 'remove', photoId: string): void
  (e: 'retry', photoId: string): void
  (e: 'error', message: string): void
}>()

const cameraInputRef = ref<HTMLInputElement | null>(null)
const galleryInputRef = ref<HTMLInputElement | null>(null)
const menuRef = ref<HTMLDetailsElement | null>(null)
function choosePhoto(camera: boolean) {
  if (menuRef.value) menuRef.value.open = false
  if (camera) triggerCamera()
  else triggerGallery()
}

const stagedPhotos = ref<PhotoDTO[]>([...(props.photos ?? props.initialPhotos)])
const isUploading = ref(false)
const uploadProgressText = ref('')
const errorMessage = ref('')

watch(
  () => props.photos ?? props.initialPhotos,
  (newPhotos) => {
    stagedPhotos.value = [...(newPhotos || [])]
  },
  { deep: true }
)

let statusTimer: ReturnType<typeof setTimeout> | null = null
let statusAttempts = 0
let disposed = false
let polling = false
const pending = () => stagedPhotos.value.some(p => p.status === 'pending' || p.status === 'processing')

function scheduleStatus() {
  if (disposed || statusTimer || polling || !pending() || statusAttempts >= 60) return
  statusTimer = setTimeout(refreshStatus, Math.min(1000 + statusAttempts * 250, 5000))
}

async function refreshStatus() {
  statusTimer = null
  if (disposed || !pending()) return
  polling = true
  statusAttempts++
  try {
    const updates = await Promise.all(stagedPhotos.value
      .filter(p => p.status === 'pending' || p.status === 'processing')
      .map(p => getPhoto(p.id).catch(() => null)))
    if (disposed) return
    stagedPhotos.value = stagedPhotos.value.map(p => updates.find(next => next?.id === p.id) ?? p)
    emit('update:photos', [...stagedPhotos.value])
  } finally {
    polling = false
    if (statusAttempts >= 60 && pending()) errorMessage.value = '圖片仍在處理，請稍後重新整理。'
    scheduleStatus()
  }
}

watch(pending, value => {
  if (!value) {
    statusAttempts = 0
    if (statusTimer) clearTimeout(statusTimer)
    statusTimer = null
  } else scheduleStatus()
}, { immediate: true })

onBeforeUnmount(() => {
  disposed = true
  if (statusTimer) clearTimeout(statusTimer)
})

function triggerCamera() {
  if (props.disabled || isUploading.value) return
  errorMessage.value = ''
  if (cameraInputRef.value) {
    cameraInputRef.value.value = ''
    cameraInputRef.value.click()
  }
}

function triggerGallery() {
  if (props.disabled || isUploading.value) return
  errorMessage.value = ''
  if (galleryInputRef.value) {
    galleryInputRef.value.value = ''
    galleryInputRef.value.click()
  }
}

async function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0) return

  const remainingSlots = props.maxPhotos - stagedPhotos.value.length
  if (remainingSlots <= 0) {
    errorMessage.value = `最多僅能選擇 ${props.maxPhotos} 張照片。`
    emit('error', errorMessage.value)
    return
  }

  const selectedFiles = Array.from(files).slice(0, remainingSlots)
  if (files.length > remainingSlots) {
    errorMessage.value = `已達上限，僅選取前 ${remainingSlots} 張照片。`
  }

  if (props.autoUpload) {
    isUploading.value = true
    try {
      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i]
        uploadProgressText.value = `上傳中 (${i + 1}/${selectedFiles.length})...`
        const photoDto = await uploadPhoto(file, file.type)
        stagedPhotos.value.push(photoDto)
        emit('upload-complete', photoDto)
        emit('update:photos', [...stagedPhotos.value])
      }
    } catch (err: any) {
      errorMessage.value = err instanceof ApiError ? err.detail : '上傳照片失敗，請檢查格式或網路連線。'
      emit('error', errorMessage.value)
    } finally {
      isUploading.value = false
      uploadProgressText.value = ''
      if (target) target.value = ''
    }
  }
}

function removePhoto(photoId: string) {
  stagedPhotos.value = stagedPhotos.value.filter((p) => p.id !== photoId)
  emit('remove', photoId)
  emit('update:photos', [...stagedPhotos.value])
}

async function handleRetry(photo: PhotoDTO) {
  statusAttempts = 0
  try {
    const updated = await retryPhoto(photo.id, photo.version)
    const idx = stagedPhotos.value.findIndex((p) => p.id === photo.id)
    if (idx !== -1) {
      stagedPhotos.value[idx] = updated
    }
    emit('update:photos', [...stagedPhotos.value])
    emit('retry', photo.id)
    scheduleStatus()
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '重試照片識別失敗，請稍後再試。'
  }
}

function clear() {
  stagedPhotos.value = []
  errorMessage.value = ''
  if (cameraInputRef.value) cameraInputRef.value.value = ''
  if (galleryInputRef.value) galleryInputRef.value.value = ''
  emit('update:photos', [])
}

defineExpose({
  clear,
  removePhoto,
  stagedPhotos
})
</script>

<template>
  <div class="photo-picker-container" :class="{ 'is-compact': compact, 'is-icon-only': iconOnly }">
    <!-- Hidden File Inputs (Hidden from tab order & a11y tree since action buttons provide entry) -->
    <input
      ref="cameraInputRef"
      type="file"
      accept="image/*"
      capture="environment"
      class="sr-only"
      tabindex="-1"
      aria-hidden="true"
      :disabled="disabled || isUploading"
      @change="handleFileChange"
    />
    <input
      ref="galleryInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/heic,image/*"
      :multiple="multiple"
      class="sr-only"
      tabindex="-1"
      aria-hidden="true"
      :disabled="disabled || isUploading"
      @change="handleFileChange"
    />

    <!-- Action Buttons -->
    <div class="picker-buttons-row">
      <details v-if="iconOnly" ref="menuRef" class="photo-source-menu" @keydown.esc.prevent="menuRef && (menuRef.open = false)">
        <summary class="icon-button" aria-label="加入圖片" title="加入圖片" :aria-disabled="disabled || isUploading" @click="(disabled || isUploading) && $event.preventDefault()"><AppIcon name="image" /></summary>
        <div class="photo-source-options"><button type="button" @click="choosePhoto(true)">拍照</button><button type="button" @click="choosePhoto(false)">從圖庫選取</button></div>
      </details>
      <button
        v-if="!iconOnly"
        type="button"
        class="btn btn-secondary picker-btn"
        :disabled="disabled || isUploading || stagedPhotos.length >= maxPhotos"
        @click="triggerCamera"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
        <span>{{ cameraButtonText }}</span>
      </button>

      <button
        v-if="!iconOnly"
        type="button"
        class="btn btn-secondary picker-btn"
        :disabled="disabled || isUploading || stagedPhotos.length >= maxPhotos"
        @click="triggerGallery"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
        <span>{{ buttonText }}</span>
      </button>

      <span v-if="isUploading" class="upload-status-text">
        <span class="spinner-small" aria-hidden="true"></span>
        <span>{{ uploadProgressText }}</span>
      </span>

      <span v-else-if="!iconOnly && maxPhotos <= 100" class="picker-count-hint">
        ({{ stagedPhotos.length }}/{{ maxPhotos }})
      </span>
    </div>

    <!-- Error notice -->
    <div v-if="errorMessage" class="picker-error-msg" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Thumbnail Previews of Staged Photos -->
    <div v-if="stagedPhotos.length > 0" class="staged-previews-grid">
      <div
        v-for="photo in stagedPhotos"
        :key="photo.id"
        class="staged-preview-item"
        :class="'status-' + photo.status"
      >
        <img
          :src="photo.thumbnail_url || photo.url"
          :alt="photo.caption || '已選取的照片預覽'"
          class="staged-thumb-img"
        />

        <!-- Status overlay for pending/processing -->
        <div
          v-if="photo.status === 'pending' || photo.status === 'processing'"
          class="staged-status-overlay is-processing"
          title="識別中..."
        >
          <span class="spinner-tiny" aria-hidden="true"></span>
          <span class="overlay-text">識別中</span>
        </div>

        <!-- Status overlay for failed with retry button -->
        <div
          v-else-if="photo.status === 'failed'"
          class="staged-status-overlay is-failed"
          title="識別失敗"
        >
          <span class="overlay-text">失敗</span>
          <button
            type="button"
            class="btn-staged-retry"
            title="重試照片識別"
            @click.stop="handleRetry(photo)"
          >
            重試
          </button>
        </div>

        <!-- Status overlay for blocked -->
        <div
          v-else-if="photo.status === 'blocked'"
          class="staged-status-overlay is-blocked"
          title="已封鎖"
        >
          <span class="overlay-text">封鎖</span>
        </div>

        <button
          type="button"
          class="btn-remove-photo"
          title="移除照片"
          aria-label="移除照片"
          :disabled="disabled"
          @click="removePhoto(photo.id)"
        >
          ✕
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.photo-source-menu { position: relative; }
.photo-source-menu summary { list-style: none; }
.photo-source-menu summary::-webkit-details-marker { display: none; }
.photo-source-options { position: absolute; bottom: calc(100% + .4rem); left: 0; min-width: 150px; padding: .35rem; z-index: 20; background: var(--color-paper); border: 1px solid var(--color-border); border-radius: var(--radius-md); box-shadow: 0 8px 24px #453a3215; }
.photo-source-options button { display: block; width: 100%; text-align: left; background: none; border: 0; padding: .65rem; color: var(--color-ink); cursor: pointer; border-radius: var(--radius-sm); }
.photo-source-options button:hover { background: var(--color-maple-subtle); }
.is-icon-only .picker-buttons-row { gap: 0; }
.is-icon-only .staged-previews-grid { min-width: 150px; }
.photo-picker-container {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.picker-buttons-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.picker-btn {
  min-height: 40px;
  padding: 0.35rem 0.75rem;
  font-size: 0.875rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.upload-status-text {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8125rem;
  color: var(--color-maple);
  font-weight: 500;
}

.picker-count-hint {
  font-size: 0.75rem;
  color: var(--color-subtle);
}

.picker-error-msg {
  font-size: 0.8125rem;
  color: var(--color-error-text);
  background-color: var(--color-error-bg);
  padding: 0.35rem 0.625rem;
  border-radius: var(--radius-xs);
  border: 1px solid var(--color-error-border);
}

.staged-previews-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.staged-preview-item {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: var(--radius-xs);
  overflow: hidden;
  border: 1px solid var(--color-border);
  background-color: var(--color-paper);
}

.staged-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.btn-remove-photo {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  background-color: rgba(30, 24, 20, 0.75);
  color: #FFFFFF;
  border: none;
  border-radius: 50%;
  font-size: 0.6875rem;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  line-height: 1;
  transition: background-color 0.15s ease;
}

.btn-remove-photo:hover {
  background-color: var(--color-error-text);
}

.staged-status-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.15rem;
  font-size: 0.625rem;
  font-weight: 600;
  z-index: 1;
  text-align: center;
  padding: 0.15rem;
}

.staged-status-overlay.is-processing {
  background-color: rgba(224, 182, 91, 0.85);
  color: #3D2D0B;
}

.staged-status-overlay.is-failed {
  background-color: rgba(166, 47, 25, 0.88);
  color: #FFFFFF;
}

.staged-status-overlay.is-blocked {
  background-color: rgba(69, 58, 50, 0.9);
  color: #FFFFFF;
}

.btn-staged-retry {
  background-color: rgba(255, 255, 255, 0.9);
  color: var(--color-error-text);
  border: none;
  font-size: 0.625rem;
  font-weight: 700;
  padding: 0.1rem 0.35rem;
  border-radius: 2px;
  cursor: pointer;
  margin-top: 0.1rem;
}

.btn-staged-retry:hover {
  background-color: #FFFFFF;
}

.spinner-tiny {
  width: 10px;
  height: 10px;
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  display: inline-block;
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

.is-compact .picker-btn {
  min-height: 34px;
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
}

.is-compact .staged-preview-item {
  width: 48px;
  height: 48px;
}
</style>
