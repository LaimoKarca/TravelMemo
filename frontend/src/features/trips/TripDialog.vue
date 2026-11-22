<script setup lang="ts">
import AppDialogFrame from '@/components/ui/AppDialogFrame.vue'
import { ref, watch, computed } from 'vue'
import JournalNote from '@/features/trips/JournalNote.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PhotoPicker from '@/features/media/PhotoPicker.vue'
import { bindPhoto, listPhotos, setTripCover } from '@/api/photos'
import type { PhotoDTO } from '@/types/photo'
import type { Trip, CreateTripPayload, UpdateTripPayload } from '@/types/travel'
import { getTimezoneOptions, normalizeTimezoneInput } from '@/utils/timezones'

const props = withDefaults(
  defineProps<{
    visible: boolean
    trip?: Trip | null
    loading?: boolean
    errorMessage?: string
    hasConflict?: boolean
    coverPhotoId?: string | null
  }>(),
  {
    trip: null,
    loading: false,
    errorMessage: '',
    hasConflict: false
  }
)

const emit = defineEmits<{
  (e: 'submit', payload: CreateTripPayload | UpdateTripPayload): void
  (e: 'refresh'): void
  (e: 'cancel'): void
  (e: 'cover-updated', payload: { tripId: string; photoId: string | null }): void
}>()


const name = ref('')
const startDate = ref('')
const endDate = ref('')
const timezone = ref('Asia/Taipei')
const description = ref('')
const clientValidationError = ref('')
const coverPicker = ref<any>(null)
const coverBusy = ref(false)
const coverError = ref('')
const albumPhotos = ref<PhotoDTO[]>([])
const currentCover = ref<string | null>(props.coverPhotoId || null)
watch(() => props.coverPhotoId, id => { currentCover.value = id || null })
watch(() => props.visible, visible => { if (visible) { currentCover.value = props.coverPhotoId || null; albumPhotos.value = []; coverError.value = '' } })
async function loadAlbum(event: Event) {
  if (!(event.target as HTMLDetailsElement).open || !props.trip) return
  try { albumPhotos.value = (await listPhotos({ trip_id: props.trip.id })).items }
  catch { coverError.value = '暫時無法讀取相簿。' }
}
async function chooseCover(id: string | null) {
  if (!props.trip || coverBusy.value) return
  const tripId = props.trip.id
  coverBusy.value = true; coverError.value = ''
  try {
    await setTripCover(tripId, id)
    currentCover.value = id
    emit('cover-updated', { tripId, photoId: id })
  } catch { coverError.value = '封面更新失敗，請稍後再試。' }
  finally { coverBusy.value = false }
}
async function uploadCover(photo: PhotoDTO) {
  if (!props.trip) return
  const tripId = props.trip.id
  try {
    await bindPhoto(photo.id, 'trip', tripId)
    if (props.trip?.id !== tripId) return
    await chooseCover(photo.id)
    coverPicker.value?.clear()
  }
  catch { coverError.value = '封面照片加入失敗，請稍後再試。' }
}

const isEdit = computed(() => !!props.trip)
const dialogTitle = computed(() => (isEdit.value ? '編輯旅行手記' : '建立旅行手記'))

const timezoneOptions = computed(() => {
  return getTimezoneOptions(startDate.value || undefined)
})


function resetFormFromProps() {
  clientValidationError.value = ''
  if (props.trip) {
    name.value = props.trip.name
    startDate.value = props.trip.start_date
    endDate.value = props.trip.end_date
    timezone.value = props.trip.timezone || 'Asia/Taipei'
    description.value = props.trip.description || ''
  } else {
    name.value = ''
    const today = new Date().toLocaleDateString('en-CA')
    startDate.value = today
    endDate.value = new Date(new Date(today).getTime() + 86400000).toISOString().slice(0, 10)
    timezone.value = 'Asia/Taipei'
    description.value = ''
  }
}

watch(() => props.visible, (visible) => {
  if (visible && !props.hasConflict) resetFormFromProps()
}, { immediate: true })

watch(
  () => props.trip,
  () => {
    resetFormFromProps()
  }
)

watch(startDate, (start) => {
  if (start && endDate.value < start) endDate.value = start
})

function handleSubmit() {
  clientValidationError.value = ''

  const trimmedName = name.value.trim()
  if (!trimmedName) {
    clientValidationError.value = '請填寫旅程名稱（1 至 200 字元）。'
    return
  }
  if (trimmedName.length > 200) {
    clientValidationError.value = '旅程名稱不可超過 200 字元。'
    return
  }
  if (!startDate.value) {
    clientValidationError.value = '請選擇開始日期。'
    return
  }
  if (!endDate.value) {
    clientValidationError.value = '請選擇結束日期。'
    return
  }
  if (startDate.value > endDate.value) {
    clientValidationError.value = '結束日期不得早於開始日期。'
    return
  }
  if (description.value.length > 10000) {
    clientValidationError.value = '旅程隨筆不可超過 10,000 字元。'
    return
  }

  const rawTimezone = timezone.value.trim()
  const normalized = normalizeTimezoneInput(rawTimezone)
  const finalTimezone = (normalized && normalized.trim()) || rawTimezone || 'Asia/Taipei'

  if (isEdit.value && props.trip) {
    const payload: UpdateTripPayload = {
      name: trimmedName,
      start_date: startDate.value,
      end_date: endDate.value,
      timezone: finalTimezone,
      description: description.value,
      version: props.trip.version
    }
    emit('submit', payload)
  } else {
    const payload: CreateTripPayload = {
      name: trimmedName,
      start_date: startDate.value,
      end_date: endDate.value,
      timezone: finalTimezone,
      description: description.value
    }
    emit('submit', payload)
  }
}

</script>

<template>
  <AppDialogFrame
    :visible="visible"
    :busy="loading"
    class="trip-editor"
    labelled-by="trip-dialog-title"
    panel-class="editor-dialog"
    :initial-focus="isEdit ? undefined : '#trip-name-input'"
    @close="emit('cancel')"
  >
      <header class="dialog-header">
        <h3 id="trip-dialog-title" class="dialog-title">{{ dialogTitle }}</h3>
        <button
          type="button"
          class="close-button"
          aria-label="關閉視窗"
          :disabled="loading"
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
            此旅程資料已在其他地方更新。您剛才輸入的內容已完整保留，您可以點擊「重新載入」取得最新紀錄，或檢查後再次儲存。
          </p>
          <button
            type="button"
            class="btn btn-secondary conflict-refresh-btn"
            @click="emit('refresh')"
          >
            重新載入最新手記
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
          <label for="trip-name-input" class="form-label">
            旅程名稱 <span class="required-star">*</span>
          </label>
          <input
            id="trip-name-input"
            v-model="name"
            type="text"
            class="form-input"
            placeholder="例如：2026 冬季京都漫步"
            maxlength="200"
            required
            :disabled="loading"
          />
        </div>

        <div class="form-row">
          <div class="form-group flex-1">
            <label for="trip-start-date" class="form-label">
              開始日期 <span class="required-star">*</span>
            </label>
            <input
              id="trip-start-date"
              v-model="startDate"
              type="date"
              class="form-input"
              required
              :disabled="loading"
            />
          </div>

          <div class="form-group flex-1">
            <label for="trip-end-date" class="form-label">
              結束日期 <span class="required-star">*</span>
            </label>
            <input
              id="trip-end-date"
              v-model="endDate"
              type="date"
              class="form-input"
              :min="startDate"
              required
              :disabled="loading"
            />
          </div>
        </div>

        <div class="form-group">
          <label for="trip-timezone" class="form-label">
            時區
          </label>
          <input
            id="trip-timezone"
            v-model="timezone"
            type="text"
            list="trip-timezone-list"
            class="form-input"
            placeholder="例如：Asia/Taipei 或 UTC+08:00"
            autocomplete="off"
            :disabled="loading"
          />
          <datalist id="trip-timezone-list">
            <option
              v-for="opt in timezoneOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            >
              {{ opt.label }}
            </option>
          </datalist>
        </div>

        <JournalNote id="trip-description" v-model="description" kind="trip" label="旅行隨筆／備忘回憶" placeholder="記下旅程的初衷、夥伴或沿途感受…" :disabled="loading" />

        <section v-if="isEdit" class="cover-editor" aria-label="手記封面">
          <div class="cover-editor-heading"><h4>手記封面</h4><button v-if="currentCover" type="button" class="btn-link" :disabled="loading || coverBusy" @click="chooseCover(null)">移除</button></div>
          <img v-if="currentCover" :src="`/api/v1/photos/${currentCover}/thumbnail`" class="cover-preview" alt="目前手記封面" />
          <PhotoPicker ref="coverPicker" :compact="true" :multiple="false" :max-photos="1" :disabled="loading || coverBusy" button-text="上傳封面" @upload-complete="uploadCover" />
          <details @toggle="loadAlbum"><summary>從旅程相簿選擇</summary><div class="cover-options"><button v-for="photo in albumPhotos" :key="photo.id" type="button" :disabled="loading || coverBusy" :aria-label="`選為封面：${photo.caption || '相簿照片'}`" :aria-pressed="currentCover === photo.id" @click="chooseCover(photo.id)"><img :src="photo.thumbnail_url" :alt="photo.caption || '相簿照片'" loading="lazy" /></button></div></details>
          <small>封面變更會即時儲存。</small><p v-if="coverError" role="alert" class="cover-error">{{ coverError }}</p>
        </section>
        </div>
        <footer class="dialog-footer dialog-icon-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="loading"
            aria-label="返回" title="返回"
            @click="emit('cancel')"
          >
            <AppIcon name="back" />
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="loading"
            :aria-label="loading ? '儲存中' : isEdit ? '儲存修改' : '建立旅程'"
            :title="isEdit ? '儲存修改' : '建立旅程'"
            :aria-busy="loading"
          >
            <span v-if="loading" class="spinner-small ui-spinner ui-spinner--on-primary" aria-hidden="true"></span>
            <AppIcon v-else name="save" />
          </button>
        </footer>
      </form>
  </AppDialogFrame>
</template>

<style scoped src="./TripDialog.css"></style>
