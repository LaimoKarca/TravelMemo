<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { Trip, Event, CreateEventPayload, UpdateEventPayload } from '../types/travel'
import type { PhotoDTO } from '../types/photo'
import { listPhotos, bindPhoto, deletePhoto, retryPhoto, updatePhoto } from '../api/photos'
import JournalNote from './JournalNote.vue'
import AppIcon from './AppIcon.vue'
import PhotoGallery from './PhotoGallery.vue'
import PhotoPicker from './PhotoPicker.vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    trip: Trip
    event?: Event | null
    categories?: string[]
    loading?: boolean
    errorMessage?: string
    hasConflict?: boolean
  }>(),
  {
    event: null,
    loading: false,
    errorMessage: '',
    hasConflict: false
  }
)

const emit = defineEmits<{
  (e: 'submit', payload: CreateEventPayload | UpdateEventPayload, stagedPhotoIds?: string[]): void
  (e: 'refresh'): void
  (e: 'cancel'): void
  (e: 'notice', message: string, type: 'success' | 'error'): void
}>()

const dialogRef = ref<HTMLElement | null>(null)
const launcherRef = ref<HTMLElement | null>(null)

const moreDetails = ref(false)

const placeName = ref('')
const city = ref('')
const address = ref('')
const category = ref('景點')
const eventDate = ref('')
const eventTime = ref('')
const notes = ref('')

const clientValidationError = ref('')

const isEdit = computed(() => !!props.event)
const dialogTitle = computed(() => (isEdit.value ? '編輯旅行足跡' : '記錄旅行足跡'))

const addedCategories = ref<string[]>([])
const addingCategory = ref(false)
const newCategory = ref('')
const categoryOptions = computed(() => [...new Set([...commonCategories, ...(props.categories || []), ...addedCategories.value, category.value].filter(Boolean))])
function addCategory() {
  const value = newCategory.value.trim()
  if (!value || value.length > 200) return
  addedCategories.value.push(value)
  category.value = value
  newCategory.value = ''
  addingCategory.value = false
}
const commonCategories = ['景點', '美食', '住宿', '交通', '購物', '文化', '咖啡', '休閒']

const eventPhotos = ref<PhotoDTO[]>([])
const loadingPhotos = ref(false)
const stagedPhotos = ref<PhotoDTO[]>([])
const eventPhotoPickerRef = ref<any>(null)

async function fetchEventPhotos(eventId: string) {
  loadingPhotos.value = true
  try {
    const res = await listPhotos({ event_id: eventId })
    eventPhotos.value = res.items || []
  } catch {
    // Non-blocking error for photos
  } finally {
    loadingPhotos.value = false
  }
}

async function handleEventPhotoUploaded(photo: PhotoDTO) {
  if (props.event) {
    try {
      await bindPhoto(photo.id, 'event', props.event.id)
      eventPhotos.value.push(photo)
      eventPhotoPickerRef.value?.removePhoto(photo.id)
      if (eventPhotoPickerRef.value?.stagedPhotos?.length === 0) {
        eventPhotoPickerRef.value?.clear()
      }
    } catch {
      // Non-blocking
    }
  }
}

async function handleDeleteEventPhoto(payload: { photoId: string; version: number }) {
  try {
    await deletePhoto(payload.photoId, payload.version)
    eventPhotos.value = eventPhotos.value.filter((p) => p.id !== payload.photoId)
  } catch {
    // Non-blocking
  }
}

async function handleRetryEventPhoto(payload: { photoId: string; version: number }) {
  try {
    const updated = await retryPhoto(payload.photoId, payload.version)
    const idx = eventPhotos.value.findIndex((p) => p.id === payload.photoId)
    if (idx !== -1) eventPhotos.value[idx] = updated
  } catch {
    // Non-blocking
  }
}

async function handleUpdateEventPhotoCaption(payload: { photoId: string; caption: string; version: number }) {
  try {
    const updated = await updatePhoto(payload.photoId, { caption: payload.caption, version: payload.version })
    const idx = eventPhotos.value.findIndex((p) => p.id === payload.photoId)
    if (idx !== -1) eventPhotos.value[idx] = updated
    emit('notice', '已更新照片說明。', 'success')
  } catch (err) {
    emit('notice', '更新照片說明失敗，請稍後再試。', 'error')
    throw err
  }
}

function handleCancel() {
  stagedPhotos.value = []
  emit('cancel')
}

const FOCUSABLE_SELECTOR = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function resetFormFromProps() {
  clientValidationError.value = ''
  addingCategory.value = false
  moreDetails.value = !!(props.event && (props.event.city || props.event.address || props.event.time))
  if (props.event) {
    placeName.value = props.event.place_name
    city.value = props.event.city || ''
    address.value = props.event.address || ''
    category.value = props.event.category || '景點'
    eventDate.value = props.event.date
    eventTime.value = props.event.time || ''
    notes.value = props.event.notes || ''
  } else {
    placeName.value = ''
    city.value = ''
    address.value = ''
    category.value = '景點'
    eventDate.value = props.trip.start_date
    eventTime.value = ''
    notes.value = ''
  }
}

function handleKeyDown(event: KeyboardEvent) {
  if (document.querySelector('.lightbox-backdrop, .confirmation-backdrop')) return
  if (!props.visible || !dialogRef.value) return

  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
    return
  }

  if (event.key === 'Tab') {
    const focusables = Array.from(
      dialogRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    )
    if (focusables.length === 0) {
      event.preventDefault()
      return
    }

    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const current = document.activeElement

    if (event.shiftKey) {
      if (current === first || !dialogRef.value.contains(current)) {
        event.preventDefault()
        last.focus()
      }
    } else {
      if (current === last || !dialogRef.value.contains(current)) {
        event.preventDefault()
        first.focus()
      }
    }
  }
}

watch(
  () => props.visible,
  (val, oldVal) => {
    if (val) {
      launcherRef.value = document.activeElement as HTMLElement | null
      stagedPhotos.value = []
      if (!props.hasConflict) {
        resetFormFromProps()
      }
      if (props.event) {
        fetchEventPhotos(props.event.id)
      } else {
        eventPhotos.value = []
      }
      nextTick(() => {
        if (isEdit.value) { dialogRef.value?.focus({ preventScroll: true }); return }
        const firstInput = dialogRef.value?.querySelector<HTMLElement>('#event-place-name')
        const firstFocusable = dialogRef.value?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
        ;(firstInput || firstFocusable)?.focus()
      })
    } else if (oldVal) {
      stagedPhotos.value = []
      nextTick(() => {
        launcherRef.value?.focus()
      })
    }
  },
  { immediate: true }
)

watch(
  () => props.event,
  () => {
    resetFormFromProps()
  }
)

function handleSubmit() {
  clientValidationError.value = ''

  const trimmedPlaceName = placeName.value.trim()
  if (!trimmedPlaceName) {
    clientValidationError.value = '請填寫地點名稱（1 至 200 字元）。'
    return
  }
  if (trimmedPlaceName.length > 200) {
    clientValidationError.value = '地點名稱不可超過 200 字元。'
    return
  }

  const trimmedCity = city.value.trim()
  if (trimmedCity.length > 200) {
    clientValidationError.value = '城市名稱不可超過 200 字元。'
    return
  }

  const trimmedAddress = address.value.trim()
  if (trimmedAddress.length > 1000) {
    clientValidationError.value = '地址不可超過 1,000 字元。'
    return
  }

  const trimmedCategory = category.value.trim()
  if (!trimmedCategory) {
    clientValidationError.value = '請填寫或選擇回憶分類（1 至 200 字元）。'
    return
  }
  if (trimmedCategory.length > 200) {
    clientValidationError.value = '類別名稱不可超過 200 字元。'
    return
  }

  if (!eventDate.value) {
    clientValidationError.value = '請選擇造訪日期。'
    return
  }

  if (eventDate.value < props.trip.start_date || eventDate.value > props.trip.end_date) {
    clientValidationError.value = `造訪日期必須在旅程區間內（${props.trip.start_date} 至 ${props.trip.end_date}）。`
    return
  }

  if (notes.value.length > 20000) {
    clientValidationError.value = '隨筆筆記不可超過 20,000 字元。'
    return
  }

  const normalizedTime = eventTime.value ? eventTime.value : null
  const old = props.event
  const unchangedPlace = old && trimmedPlaceName === old.place_name && trimmedCity === (old.city || '') && trimmedAddress === (old.address || '')
  const placeIdToSubmit = unchangedPlace ? old.place_id : null

  if (isEdit.value && props.event) {
    const payload: UpdateEventPayload = {
      place_id: placeIdToSubmit,
      place_name: trimmedPlaceName,
      city: trimmedCity,
      address: trimmedAddress,
      category: trimmedCategory,
      date: eventDate.value,
      time: normalizedTime,
      notes: notes.value,
      version: props.event.version
    }
    emit('submit', payload)
  } else {
    const payload: CreateEventPayload = {
      place_id: placeIdToSubmit,
      place_name: trimmedPlaceName,
      city: trimmedCity,
      address: trimmedAddress,
      category: trimmedCategory,
      date: eventDate.value,
      time: normalizedTime,
      notes: notes.value
    }
    emit('submit', payload, stagedPhotos.value.map((p) => p.id))
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  if (props.visible) {
    launcherRef.value?.focus()
  }
})
</script>

<template>
  <div
    v-if="visible"
    class="dialog-backdrop"
    role="presentation"
    @click.self="emit('cancel')"
  >
    <div
      ref="dialogRef"
      class="dialog-card editor-dialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="'event-dialog-title'"
      tabindex="-1"
    >
      <header class="dialog-header">
        <h3 id="event-dialog-title" class="dialog-title">{{ dialogTitle }}</h3>
        <button
          type="button"
          class="close-button"
          aria-label="關閉視窗"
          @click="emit('cancel')"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      <!-- Conflict Notice (409) -->
      <div v-if="hasConflict" class="conflict-banner" role="alert">
        <div class="conflict-content">
          <p class="conflict-text">
            <strong>紀錄更新提示：</strong>
            此段旅途紀錄已在其他地方更新。您當前編輯的內容已完整保留，可點擊「重新載入」取得最新紀錄，或核對後再次儲存。
          </p>
          <button
            type="button"
            class="btn btn-secondary conflict-refresh-btn"
            @click="emit('refresh')"
          >
            重新載入最新紀錄
          </button>
        </div>
      </div>

      <!-- General or Client Error Notice -->
      <div v-if="clientValidationError || errorMessage" class="error-banner" role="alert">
        {{ clientValidationError || errorMessage }}
      </div>

      <form class="dialog-form" @submit.prevent="handleSubmit">
        <div class="dialog-form-body">
        <div class="form-group">
          <label for="event-place-name" class="form-label">地點名稱 <span class="required-star">*</span></label>
          <input id="event-place-name" v-model="placeName" class="form-input" placeholder="這一站去了哪裡？" maxlength="200" required :disabled="loading" />
        </div>
        <div class="form-row essential-row">
          <div class="form-group flex-1">
            <label for="event-date" class="form-label">日期 <span class="required-star">*</span></label>
            <input id="event-date" v-model="eventDate" type="date" class="form-input" :min="trip.start_date" :max="trip.end_date" required :disabled="loading" />
          </div>
          <div class="form-group flex-1">
            <div class="category-label"><label for="event-category" class="form-label">分類 <span class="required-star">*</span></label><button type="button" class="add-tag-button" :aria-expanded="addingCategory" :disabled="loading" @click="addingCategory = !addingCategory">＋ 標籤</button></div>
            <select id="event-category" v-model="category" class="form-input" :disabled="loading" required aria-label="回憶分類"><option v-for="cat in categoryOptions" :key="cat" :value="cat">{{ cat }}</option></select>
          </div>
        </div>
        <div v-if="addingCategory" class="category-select-row">
          <input v-model="newCategory" class="form-input" aria-label="新標籤名稱" placeholder="標籤名稱" maxlength="200" :disabled="loading" @keydown.enter.prevent="addCategory" />
          <button type="button" class="add-tag-button" :disabled="loading || !newCategory.trim()" @click="addCategory">加入</button>
        </div>
        <details class="more-details" :open="moreDetails" @toggle="moreDetails = ($event.target as HTMLDetailsElement).open">
          <summary>更多細節</summary>
          <div class="detail-fields">
            <div class="form-row">
              <div class="form-group flex-1"><label for="event-city" class="form-label">城市／地區</label><input id="event-city" v-model="city" class="form-input" maxlength="200" :disabled="loading" /></div>
              <div class="form-group flex-1"><label for="event-time" class="form-label">抵達時間</label><input id="event-time" v-model="eventTime" type="time" class="form-input" :disabled="loading" /></div>
            </div>
            <div class="form-group"><label for="event-address" class="form-label">地址</label><input id="event-address" v-model="address" class="form-input" maxlength="1000" :disabled="loading" /></div>
          </div>
        </details>
        <JournalNote id="event-notes" v-model="notes" kind="event" label="旅途隨筆" placeholder="留下餐點、沿途風景或旅途感受…" :disabled="loading" :maxlength="20000" />

        <section class="event-photo-section" aria-label="足跡相片">
          <div class="event-photo-heading"><h4>足跡相片</h4>
            <PhotoPicker v-if="isEdit && event" ref="eventPhotoPickerRef" :compact="true" :multiple="true" button-text="新增照片" camera-button-text="拍照" @upload-complete="handleEventPhotoUploaded" />
            <PhotoPicker v-else v-model:photos="stagedPhotos" :compact="true" :multiple="true" button-text="選擇照片" camera-button-text="拍照" />
          </div>
          <PhotoGallery v-if="isEdit && event" :photos="eventPhotos" :compact-empty="true" :loading="loadingPhotos" :can-set-cover="false" :can-reorder="false" :can-delete="true" :can-edit-caption="true" empty-text="此處足跡尚未附帶照片" @delete="handleDeleteEventPhoto" @retry="handleRetryEventPhoto" :save-caption="handleUpdateEventPhotoCaption" @refresh="props.event && fetchEventPhotos(props.event.id)" />
        </section>

        </div>
        <footer class="dialog-footer dialog-icon-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="loading"
            aria-label="返回" title="返回"
            @click="handleCancel"
          >
            <AppIcon name="back" />
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="loading"
            :aria-label="loading ? '儲存中' : isEdit ? '儲存修改' : '記錄足跡'"
            :title="isEdit ? '儲存修改' : '記錄足跡'"
            :aria-busy="loading"
          >
            <span v-if="loading" class="spinner-small" aria-hidden="true"></span>
            <AppIcon v-else name="save" />
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.category-label { display: flex; align-items: center; justify-content: space-between; min-height: 24px; }
.category-label .add-tag-button { padding: 0; font-size: .8rem; }
.more-details summary { color: var(--color-subtle); font-size: .85rem; cursor: pointer; padding: .2rem 0; }
.detail-fields { display: flex; flex-direction: column; gap: .8rem; padding-top: .8rem; }
.essential-row > .form-group { min-width: 0; }
@media(min-width: 1024px) { .dialog-card { max-width: 40rem !important; } }

.event-photo-heading { display: flex; align-items: center; gap: .75rem; margin-bottom: .8rem; }
.event-photo-heading { display: grid; grid-template-columns: auto minmax(0, 1fr); }
.event-photo-heading :deep(.photo-picker-container) { display: contents; }
.event-photo-heading :deep(.picker-buttons-row) { justify-self: end; }
.event-photo-heading :deep(.staged-previews-grid), .event-photo-heading :deep(.picker-error-msg) { grid-column: 1 / -1; }
.event-photo-heading h4 { margin: 0 auto 0 0; color: var(--color-maple); font-size: .875rem; font-weight: 600; white-space: nowrap; }
.event-photo-heading :deep(.picker-btn) { min-height: 36px; padding: .4rem .55rem; font-size: .8rem; }
.category-select-row { display: flex; align-items: center; gap: .75rem; }
.category-select-row .form-input { flex: 1; min-width: 0; }
.add-tag-button { flex: 0 0 auto; background: none; border: 0; color: var(--color-maple); font: inherit; font-size: .85rem; padding: .5rem 0; cursor: pointer; }

.dialog-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(69, 58, 50, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
  z-index: 1000;
  overflow-y: auto;
}

.dialog-card {
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  background-color: var(--color-paper);
  border-radius: var(--radius-lg);
  box-shadow: 0 16px 36px rgba(69, 58, 50, 0.15);
  border: 1px solid var(--color-border);
  padding: 1.75rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  overflow-y: auto;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dialog-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-ink);
}

.close-button {
  background: transparent;
  border: none;
  color: var(--color-subtle);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.375rem;
  border-radius: var(--radius-sm);
}

.close-button:hover {
  background-color: var(--color-maple-subtle);
  color: var(--color-ink);
}

.conflict-banner {
  background-color: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  padding: 0.875rem 1rem;
  color: var(--color-warning-text);
  font-size: 0.875rem;
  line-height: 1.5;
}

.conflict-content {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.conflict-refresh-btn {
  align-self: flex-start;
  min-height: 36px;
  padding: 0.35rem 0.875rem;
  font-size: 0.875rem;
  background-color: var(--color-paper);
  border-color: var(--color-border);
}

.error-banner {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-text);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-fieldset {
  border: 0;
  border-top: 1px solid var(--color-border);
  border-radius: 0;
  padding: 1rem 0 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.fieldset-legend {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-maple);
  padding: 0 0.5rem;
}

.place-mode-switch {
  display: flex;
  gap: 0.5rem;
}

.mode-chip {
  padding: 0.35rem 0.75rem;
  font-size: 0.8125rem;
  border: 1px solid var(--color-border);
  border-radius: 9999px;
  background-color: transparent;
  color: var(--color-subtle);
  cursor: pointer;
  transition: all 0.15s ease;
}

.mode-chip.is-active {
  background-color: var(--color-maple);
  color: #ffffff;
  border-color: var(--color-maple);
  font-weight: 500;
}

.place-bound-hint {
  font-size: 0.8125rem;
  color: var(--color-subtle);
  background-color: var(--color-canvas);
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
}

.inline-link-btn {
  background: transparent;
  border: none;
  color: var(--color-maple);
  text-decoration: underline;
  cursor: pointer;
  font-size: 0.8125rem;
  padding: 0;
}

.category-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 0.375rem;
}

.chip-btn {
  padding: 0.25rem 0.625rem;
  font-size: 0.8125rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background-color: var(--color-canvas);
  color: var(--color-ink);
  cursor: pointer;
  transition: all 0.15s ease;
}

.chip-btn.is-selected {
  background-color: var(--color-amber-subtle);
  border-color: var(--color-amber);
  color: var(--color-amber-text);
  font-weight: 600;
}

.category-custom-input {
  min-height: 38px;
}

.form-group {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-row {
  min-width: 0;
  display: flex;
  gap: 1rem;
}

.flex-1 {
  flex: 1;
}

.flex-2 {
  flex: 2;
}


.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-ink);
}

.label-with-clear {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.clear-time-btn {
  background: transparent;
  border: none;
  color: var(--color-subtle);
  font-size: 0.75rem;
  cursor: pointer;
  text-decoration: underline;
}

.clear-time-btn:hover {
  color: var(--color-ink);
}

.required-star {
  color: var(--color-error-text);
}

.field-hint {
  font-size: 0.75rem;
  color: var(--color-subtle);
}

.form-textarea {
  min-height: 80px;
  resize: vertical;
}

.form-select {
  cursor: pointer;
}


.photos-sub-wrapper {
  margin-top: 0.75rem;
}

.staged-hint {
  margin-bottom: 0.5rem;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 600px) {
  .form-row {
    flex-direction: column;
    gap: 1rem;
  }
}
</style>
