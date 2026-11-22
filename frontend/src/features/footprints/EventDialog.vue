<script setup lang="ts">
import AppDialogFrame from '@/components/ui/AppDialogFrame.vue'
import { ref, watch, computed, onBeforeUnmount } from 'vue'
import type { Trip, Event, CreateEventPayload, UpdateEventPayload } from '@/types/travel'
import type { PhotoDTO } from '@/types/photo'
import { listPhotos, bindPhoto, deletePhoto, retryPhoto, updatePhoto } from '@/api/photos'
import JournalNote from '@/features/trips/JournalNote.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PhotoGallery from '@/features/media/PhotoGallery.vue'
import PhotoPicker from '@/features/media/PhotoPicker.vue'
import { getTripLocalDate } from '@/utils/timezones'
import { locationInputError, maxMapUrlLength, validMapUrl } from '@/utils/maps'

const props = withDefaults(
  defineProps<{
    visible: boolean
    trip?: Trip | null
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
  (e: 'photo-deleted', photoId: string): void
}>()



const placeName = ref('')
const city = ref('')
const location = ref('')
const locationError = computed(() => locationInputError(location.value))
const category = ref('景點')
const eventDate = ref('')
const eventTime = ref('')
const defaultDailyTimezone = 'Asia/Taipei'
const notes = ref('')

const clientValidationError = ref('')

const isEdit = computed(() => !!props.event)
const dialogTitle = computed(() => `${isEdit.value ? '編輯' : '記錄'}${props.trip ? '旅行' : '日常'}足跡`)

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
const photoLoadError = ref(false)
const photoSession = ref(0)
let photoLoadGeneration = 0
const stagedPhotos = ref<PhotoDTO[]>([])
const newPhotoPicker = ref<InstanceType<typeof PhotoPicker> | null>(null)
const photosPending = computed(() => !isEdit.value && (
  newPhotoPicker.value?.isUploading || stagedPhotos.value.some(photo => photo.status === 'pending' || photo.status === 'processing')
))
const savingEvent = computed(() => props.loading || photosPending.value)
const eventPhotoPickerRef = ref<InstanceType<typeof PhotoPicker> | null>(null)

function isPhotoSessionCurrent(session: number) {
  return props.visible && session === photoSession.value
}

async function fetchEventPhotos() {
  const eventId = props.event?.id
  if (!props.visible || !eventId) return
  const session = photoSession.value
  const generation = ++photoLoadGeneration
  const isCurrent = () => isPhotoSessionCurrent(session) && generation === photoLoadGeneration
  loadingPhotos.value = true
  photoLoadError.value = false
  try {
    const res = await listPhotos({ event_id: eventId })
    if (isCurrent()) eventPhotos.value = res.items || []
  } catch {
    if (isCurrent()) photoLoadError.value = true
  } finally {
    if (isCurrent()) loadingPhotos.value = false
  }
}

function applyPhotoChange(session: number, update: () => void) {
  if (!isPhotoSessionCurrent(session)) return
  update()
  // Reload after the write if an older read is still in flight.
  if (loadingPhotos.value) void fetchEventPhotos()
}

async function handleEventPhotoUploaded(photo: PhotoDTO) {
  const eventId = props.event?.id
  if (!props.visible || !eventId) return
  const session = photoSession.value
  try {
    const bound = await bindPhoto(photo.id, 'event', eventId)
    applyPhotoChange(session, () => {
      if (!eventPhotos.value.some(item => item.id === bound.id)) eventPhotos.value.push(bound)
      eventPhotoPickerRef.value?.removePhoto(photo.id)
    })
  } catch {
    if (isPhotoSessionCurrent(session)) emit('notice', '無法將照片加入足跡。', 'error')
  }
}

function hasCurrentPhoto(photoId: string) {
  return props.visible && !loadingPhotos.value && eventPhotos.value.some(photo => photo.id === photoId)
}

async function handleDeleteEventPhoto(payload: { photoId: string; version: number }) {
  if (!hasCurrentPhoto(payload.photoId)) return
  const session = photoSession.value
  try {
    await deletePhoto(payload.photoId, payload.version)
    emit('photo-deleted', payload.photoId)
    applyPhotoChange(session, () => {
      eventPhotos.value = eventPhotos.value.filter(p => p.id !== payload.photoId)
    })
  } catch {
    if (isPhotoSessionCurrent(session)) emit('notice', '無法刪除照片，請稍後重試。', 'error')
  }
}

async function handleRetryEventPhoto(payload: { photoId: string; version: number }) {
  if (!hasCurrentPhoto(payload.photoId)) return
  const session = photoSession.value
  try {
    const updated = await retryPhoto(payload.photoId, payload.version)
    applyPhotoChange(session, () => {
      eventPhotos.value = eventPhotos.value.map(p => p.id === updated.id ? updated : p)
    })
  } catch {
    if (isPhotoSessionCurrent(session)) emit('notice', '無法重試照片識別。', 'error')
  }
}

async function handleUpdateEventPhotoCaption(payload: { photoId: string; caption: string; version: number }) {
  if (!hasCurrentPhoto(payload.photoId)) throw new Error('找不到目前足跡的照片。')
  const session = photoSession.value
  try {
    const updated = await updatePhoto(payload.photoId, { caption: payload.caption, version: payload.version })
    applyPhotoChange(session, () => {
      eventPhotos.value = eventPhotos.value.map(p => p.id === updated.id ? updated : p)
      emit('notice', '已更新照片說明。', 'success')
    })
  } catch (err) {
    if (isPhotoSessionCurrent(session)) emit('notice', '更新照片說明失敗，請稍後再試。', 'error')
    throw err
  }
}

function handleCancel() {
  if (props.loading) return
  stagedPhotos.value = []
  emit('cancel')
}


function resetFormFromProps() {
  clientValidationError.value = ''
  addingCategory.value = false
  if (props.event) {
    placeName.value = props.event.place_name
    city.value = props.event.city || ''
    location.value = props.event.map_url || props.event.address || ''
    category.value = props.event.category || (props.trip ? '景點' : '未分類')
    eventDate.value = props.event.date
    eventTime.value = props.event.time || ''
    notes.value = props.event.notes || ''
  } else {
    placeName.value = ''
    city.value = ''
    location.value = ''
    category.value = props.trip ? '景點' : '未分類'
    eventDate.value = props.trip?.start_date || getTripLocalDate(new Date(), defaultDailyTimezone)
    eventTime.value = ''
    notes.value = ''
  }
}

watch(() => props.visible, (visible) => {
  stagedPhotos.value = []
  if (visible && !props.hasConflict) resetFormFromProps()
}, { immediate: true })

watch([() => props.visible, () => props.event?.id], ([visible, eventId]) => {
  photoSession.value++
  loadingPhotos.value = false
  photoLoadError.value = false
  eventPhotos.value = []
  if (visible && eventId) void fetchEventPhotos()
}, { immediate: true })

watch(
  () => props.event,
  () => {
    resetFormFromProps()
  }
)

function handleSubmit() {
  if (savingEvent.value) return
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

  if (locationError.value) return
  const mapUrl = validMapUrl(location.value)
  const address = mapUrl ? '' : location.value.trim()

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

  if (props.trip && (eventDate.value < props.trip.start_date || eventDate.value > props.trip.end_date)) {
    clientValidationError.value = `造訪日期必須在旅程區間內（${props.trip.start_date} 至 ${props.trip.end_date}）。`
    return
  }

  if (notes.value.length > 20000) {
    clientValidationError.value = '隨筆筆記不可超過 20,000 字元。'
    return
  }

  const normalizedTime = eventTime.value ? eventTime.value : null
  const old = props.event
  const oldMapUrl = validMapUrl(old?.map_url) || validMapUrl(old?.address)
  const unchangedPlace = old && trimmedPlaceName === old.place_name && trimmedCity === (old.city || '')
    && mapUrl === oldMapUrl && address === (oldMapUrl ? '' : (old.address || '').trim())
  const placeIdToSubmit = unchangedPlace ? old.place_id : null

  if (isEdit.value && props.event) {
    const payload: UpdateEventPayload = {
      place_id: placeIdToSubmit,
      place_name: trimmedPlaceName,
      city: trimmedCity,
      address,
      map_url: mapUrl,
      category: trimmedCategory,
      date: eventDate.value,
      time: normalizedTime,
      notes: notes.value,
      version: props.event.version
    }
    emit('submit', payload)
  } else {
    const payload: CreateEventPayload = {
      ...(props.trip ? {} : { timezone: defaultDailyTimezone }),
      place_id: placeIdToSubmit,
      place_name: trimmedPlaceName,
      city: trimmedCity,
      address,
      map_url: mapUrl,
      category: trimmedCategory,
      date: eventDate.value,
      time: normalizedTime,
      notes: notes.value
    }
    emit('submit', payload, stagedPhotos.value.map((p) => p.id))
  }
}

onBeforeUnmount(() => { photoSession.value++ })
</script>

<template>
  <AppDialogFrame
    :visible="visible"
    :busy="loading"
    class="event-editor"
    labelled-by="event-dialog-title"
    panel-class="editor-dialog"
    :initial-focus="isEdit || !trip ? undefined : '#event-place-name'"
    @close="handleCancel"
  >
      <header class="dialog-header">
        <h3 id="event-dialog-title" class="dialog-title">{{ dialogTitle }}</h3>
        <button
          type="button"
          class="close-button"
          aria-label="關閉視窗"
          :disabled="loading"
          @click="handleCancel"
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
        <div class="essential-row date-time-row">
          <div class="form-group">
            <label for="event-date" class="form-label">日期 <span v-if="trip" class="required-star">*</span></label>
            <input id="event-date" v-model="eventDate" type="date" class="form-input" :min="trip?.start_date" :max="trip?.end_date" :required="Boolean(trip)" :disabled="loading" />
          </div>
          <div class="form-group">
            <label for="event-time" class="form-label">抵達時間</label>
            <input id="event-time" v-model="eventTime" type="time" class="form-input" :disabled="loading" />
          </div>
        </div>
        <div class="essential-row">
          <div class="form-group">
            <div class="category-label"><label for="event-city" class="form-label">地區</label></div>
            <input id="event-city" v-model="city" class="form-input" placeholder="例如臺中市東區" maxlength="200" :disabled="loading" />
          </div>
          <div class="form-group">
            <div class="category-label">
              <label for="event-category" class="form-label">分類 <span v-if="trip" class="required-star">*</span></label>
              <button type="button" class="add-tag-button" :aria-expanded="addingCategory" :disabled="loading" @click="addingCategory = !addingCategory">＋ 標籤</button>
            </div>
            <select id="event-category" v-model="category" class="form-input" :disabled="loading" :required="Boolean(trip)" aria-label="回憶分類">
              <option v-for="cat in categoryOptions" :key="cat" :value="cat">{{ cat }}</option>
            </select>
          </div>
        </div>
        <div v-if="addingCategory" class="category-select-row">
          <input v-model="newCategory" class="form-input" aria-label="新標籤名稱" placeholder="標籤名稱" maxlength="200" :disabled="loading" @keydown.enter.prevent="addCategory" />
          <button type="button" class="add-tag-button" :disabled="loading || !newCategory.trim()" @click="addCategory">加入</button>
        </div>
        <div class="form-group">
          <label for="event-address" class="form-label">地址或 Google Maps 連結</label>
          <input id="event-address" v-model="location" class="form-input" :maxlength="maxMapUrlLength"
            :disabled="loading" :aria-invalid="Boolean(locationError)" :aria-describedby="locationError ? 'event-location-error' : undefined" />
          <p v-if="locationError" id="event-location-error" class="error-banner" role="alert">{{ locationError }}</p>
        </div>
        <JournalNote id="event-notes" v-model="notes" kind="event" :label="trip ? '旅途隨筆' : '隨筆'" :placeholder="trip ? '留下餐點、沿途風景或旅途感受…' : '此刻想記下什麼？'" :disabled="loading" :maxlength="20000" />

        <section class="event-photo-section" aria-label="足跡相片">
          <div class="event-photo-heading photo-control-heading"><h4>足跡相片</h4>
            <PhotoPicker v-if="isEdit && event" :key="photoSession" ref="eventPhotoPickerRef" :compact="true" :multiple="true" button-text="新增照片" camera-button-text="拍照" @upload-complete="handleEventPhotoUploaded" />
            <PhotoPicker v-else :key="photoSession" ref="newPhotoPicker" v-model:photos="stagedPhotos" :disabled="loading" :compact="true" :multiple="true" button-text="選擇照片" camera-button-text="拍照" />
          </div>
          <p v-if="photoLoadError" role="alert">無法載入足跡照片。 <button type="button" class="btn-link" @click="fetchEventPhotos">重試</button></p>
          <PhotoGallery v-else-if="isEdit && event" :key="photoSession" :photos="eventPhotos" :compact-empty="true" :loading="loadingPhotos" :can-set-cover="false" :can-reorder="false" :can-delete="true" :can-edit-caption="true" empty-text="此處足跡尚未附帶照片" @delete="handleDeleteEventPhoto" @retry="handleRetryEventPhoto" :save-caption="handleUpdateEventPhotoCaption" @refresh="fetchEventPhotos" />
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
            class="btn btn-primary event-save"
            :class="{ 'is-photo-pending': photosPending }"
            :disabled="savingEvent"
            :aria-label="photosPending ? '等待照片處理' : loading ? '儲存中' : isEdit ? '儲存修改' : '記錄足跡'"
            :title="isEdit ? '儲存修改' : '記錄足跡'"
            :aria-busy="savingEvent"
          >
            <span v-if="savingEvent" class="spinner-small ui-spinner ui-spinner--on-primary" aria-hidden="true"></span>
            <AppIcon v-else name="save" />
          </button>
        </footer>
      </form>
  </AppDialogFrame>
</template>

<style scoped src="./EventDialog.css"></style>
