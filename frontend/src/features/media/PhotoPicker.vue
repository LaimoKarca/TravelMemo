<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import type { PhotoDTO } from '@/types/photo'
import { uploadPhoto, retryPhoto, getPhoto } from '@/api/photos'
import { ApiError, getCsrfToken } from '@/api/auth'
import AppIcon from '@/components/ui/AppIcon.vue'
import PhotoSourceMenu from './PhotoSourceMenu.vue'

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
    directIcons?: boolean
    nativePicker?: boolean
    hideControls?: boolean
    beginUpload?: () => { add: (photo: PhotoDTO) => void; finish: (error: string) => void }
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
  (e: 'error', message: string): void
  (e: 'selection-finished'): void
}>()

const cameraInputRef = ref<HTMLInputElement | null>(null)
const galleryInputRef = ref<HTMLInputElement | null>(null)
const sourceMenu = ref<InstanceType<typeof PhotoSourceMenu> | null>(null)
function finishSelection() {
  sourceMenu.value?.close()
  emit('selection-finished')
}

const stagedPhotos = ref<PhotoDTO[]>([...(props.photos ?? props.initialPhotos)])
const isUploading = ref(false)
const uploadProgressText = ref('')
const errorMessage = ref('')
const statusTimedOut = ref(false)

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
let uploadGeneration = 0
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
    statusTimedOut.value = statusAttempts >= 60 && pending()
    scheduleStatus()
  }
}

watch(pending, value => {
  if (!value) {
    statusAttempts = 0
    statusTimedOut.value = false
    if (statusTimer) clearTimeout(statusTimer)
    statusTimer = null
  } else scheduleStatus()
}, { immediate: true })

function checkStatusAgain() {
  if (polling || !pending()) return
  if (statusTimer) clearTimeout(statusTimer)
  statusAttempts = 0
  statusTimedOut.value = false
  void refreshStatus()
}

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
  finishSelection()
  if (props.disabled || isUploading.value) return
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
    const receiver = props.beginUpload?.()
    const session = getCsrfToken()
    const generation = ++uploadGeneration
    const isCurrent = () => !disposed && generation === uploadGeneration
    let uploadError = ''
    isUploading.value = true
    try {
      for (let i = 0; i < selectedFiles.length; i++) {
        if (session !== getCsrfToken()) break
        if (!receiver && !isCurrent()) break
        const file = selectedFiles[i]
        uploadProgressText.value = `上傳中 (${i + 1}/${selectedFiles.length})...`
        const photoDto = await uploadPhoto(file, file.type)
        if (session !== getCsrfToken()) break
        if (receiver) {
          receiver.add(photoDto)
        } else if (isCurrent()) {
          stagedPhotos.value.push(photoDto)
          emit('upload-complete', photoDto)
          emit('update:photos', [...stagedPhotos.value])
        }
      }
    } catch (err: any) {
      uploadError = err instanceof ApiError ? err.detail : '上傳照片失敗，請檢查格式或網路連線。'
      if (isCurrent() && !receiver) {
        errorMessage.value = uploadError
        emit('error', uploadError)
      }
    } finally {
      receiver?.finish(uploadError)
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
  statusTimedOut.value = false
  try {
    const updated = await retryPhoto(photo.id, photo.version)
    if (disposed) return
    const idx = stagedPhotos.value.findIndex((p) => p.id === photo.id)
    if (idx !== -1) {
      stagedPhotos.value[idx] = updated
    }
    emit('update:photos', [...stagedPhotos.value])
    scheduleStatus()
  } catch (err: any) {
    errorMessage.value = err instanceof ApiError ? err.detail : '重試照片識別失敗，請稍後再試。'
  }
}

function clear() {
  uploadGeneration++
  stagedPhotos.value = []
  errorMessage.value = ''
  if (cameraInputRef.value) cameraInputRef.value.value = ''
  if (galleryInputRef.value) galleryInputRef.value.value = ''
  emit('update:photos', [])
}

defineExpose({
  clear,
  removePhoto,
  stagedPhotos,
  isUploading,
  triggerCamera,
  triggerGallery
})
</script>

<template>
  <div class="photo-picker-container" :class="{
    'is-compact': compact, 'is-icon-only': iconOnly,
    'has-no-visible-content': hideControls && !isUploading && !errorMessage && !stagedPhotos.length
  }">
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
      @cancel="finishSelection"
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
      @cancel="finishSelection"
    />

    <!-- Action Buttons -->
    <div v-if="!hideControls" class="picker-buttons-row">
      <button v-if="nativePicker" type="button" class="icon-button native-picker-btn" :aria-label="buttonText" :title="buttonText" :disabled="disabled || isUploading || stagedPhotos.length >= maxPhotos" @click="triggerGallery"><AppIcon name="camera" /></button>
      <PhotoSourceMenu v-else-if="iconOnly" ref="sourceMenu" :disabled="disabled || isUploading" @camera="triggerCamera" @gallery="triggerGallery" />
      <button
        v-if="!nativePicker && !iconOnly"
        type="button"
        class="btn btn-secondary picker-btn"
        :class="{ 'direct-icon-btn': directIcons }"
        :aria-label="cameraButtonText" :title="cameraButtonText"
        :disabled="disabled || isUploading || stagedPhotos.length >= maxPhotos"
        @click="triggerCamera"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
        <span :class="{ 'sr-only': directIcons }">{{ cameraButtonText }}</span>
      </button>

      <button
        v-if="!nativePicker && !iconOnly"
        type="button"
        class="btn btn-secondary picker-btn"
        :class="{ 'direct-icon-btn': directIcons }"
        :aria-label="buttonText" :title="buttonText"
        :disabled="disabled || isUploading || stagedPhotos.length >= maxPhotos"
        @click="triggerGallery"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
        <AppIcon v-if="directIcons" name="plus" class="add-photo-plus" />
        <span :class="{ 'sr-only': directIcons }">{{ buttonText }}</span>
      </button>

      <span v-if="isUploading" class="upload-status-text">
        <span class="spinner-small ui-spinner ui-spinner--current" aria-hidden="true"></span>
        <span>{{ uploadProgressText }}</span>
      </span>

      <span v-else-if="!iconOnly && maxPhotos <= 100" class="picker-count-hint">
        ({{ stagedPhotos.length }}/{{ maxPhotos }})
      </span>
    </div>

    <span v-if="isUploading && hideControls" class="upload-status-text" role="status">
      <span class="spinner-small ui-spinner ui-spinner--current" aria-hidden="true"></span>
      {{ uploadProgressText }}
    </span>

    <!-- Error notice -->
    <div v-if="errorMessage" class="picker-error-msg" role="alert">
      {{ errorMessage }}
    </div>
    <p v-if="statusTimedOut" class="picker-error-msg" role="status">
      照片仍在處理。<button type="button" class="btn-link" @click="checkStatusAgain">重新查詢</button>
    </p>

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
          <span class="spinner-tiny ui-spinner ui-spinner--current" aria-hidden="true"></span>
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

<style scoped src="./PhotoPicker.css"></style>
