<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import type {
  Trip,
  TripListItem,
  Event,
  CreateTripPayload,
  UpdateTripPayload,
  CreateEventPayload,
  UpdateEventPayload
} from '@/types/travel'
import {
  listTrips,
  createTrip,
  getTrip,
  updateTrip,
  deleteTrip,
  createEvent,
  updateEvent,
  deleteEvent
} from '@/api/travel'
import {
  listPhotos,
  bindPhoto,
  deletePhoto,
  retryPhoto,
  updatePhoto,
  reorderTripPhotos,
  getTripCover,
  setTripCover
} from '@/api/photos'
import type { PhotoDTO } from '@/types/photo'
import { ApiError } from '@/api/auth'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppSearchBar from '@/components/ui/AppSearchBar.vue'
import { getTripStatus } from '@/utils/timezones'
import FootprintAssistant from '@/features/footprints/FootprintAssistant.vue'
import TripDialog from './TripDialog.vue'
import EventDialog from '@/features/footprints/EventDialog.vue'
import LocationLink from '@/features/footprints/LocationLink.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import PhotoGallery from '@/features/media/PhotoGallery.vue'
import PhotoPicker from '@/features/media/PhotoPicker.vue'
import PhotoViewer from '@/features/media/PhotoViewer.vue'

const props = defineProps<{ active: boolean }>()
const trips = defineModel<TripListItem[]>('trips', { required: true })
const emit = defineEmits<{
  notice: [message: string, type: 'error' | 'success' | 'info']
  'clear-notice': []
}>()

function showAlert(message: string, type: 'error' | 'success' | 'info' = 'info') {
  emit('notice', message, type)
}

function clearAlert() {
  emit('clear-notice')
}

const highlightedEventId = ref<string | null>(null)

// Loading states
const loadingTrips = ref(false)
const loadingDetail = ref(false)
const actionInProgress = ref(false)

// Data state
const clockNow = ref(new Date())
let clockTimer: ReturnType<typeof setInterval> | undefined
function refreshClock() { clockNow.value = new Date() }
function tripStatus(trip: Trip) {
  try { return getTripStatus(trip.start_date, trip.end_date, trip.timezone, clockNow.value) }
  catch (error) {
    if (error instanceof RangeError) return 'unknown'
    throw error
  }
}
const tripQuery = ref('')
const tripPeriod = ref('all')
const tripYear = ref('')
const libraryFiltersOpen = ref(false)
const libraryFiltersActive = computed(() => tripPeriod.value !== 'all' || !!tripYear.value)
const tripYears = computed(() => [...new Set(trips.value.map(t => t.start_date.slice(0, 4)))].sort().reverse())
const visibleTrips = computed(() => {
  const q = tripQuery.value.trim().toLocaleLowerCase()
  return trips.value.filter(t => (!q || `${t.name} ${t.description || ''} ${t.timezone}`.toLocaleLowerCase().includes(q))
    && (!tripYear.value || t.start_date.startsWith(tripYear.value))
    && (tripPeriod.value === 'all' || tripStatus(t) === tripPeriod.value))
    .sort((a, b) => b.start_date.localeCompare(a.start_date) || b.id.localeCompare(a.id))
})
const activeTripId = ref<string | null>(null)
const currentTrip = ref<Trip | null>(null)
const showFootprintAssistant = ref(false)
watch(() => [props.active, activeTripId.value], () => { showFootprintAssistant.value = false })
async function handleFootprintsSaved() {
  if (activeTripId.value) await selectTrip(activeTripId.value)
}

const currentEvents = ref<Event[]>([])

// Photo state
const currentTripPhotos = ref<PhotoDTO[]>([])
const currentTripCoverId = ref<string | null>(null)
const albumOpen = ref(false)
const loadingTripPhotos = ref(false)
const brokenCoverIds = reactive(new Map<string, string>())
const editingCoverId = computed(() => {
  if (!editingTrip.value) return null
  const id = editingTrip.value.id
  const item = trips.value.find(trip => trip.id === id)
  return item ? item.cover_photo_id : currentTrip.value?.id === id ? currentTripCoverId.value : null
})
const tripPhotoPickerRef = ref<any>(null)

// Lightbox for timeline event photos
const timelineViewerVisible = ref(false)
const timelineSelectedPhotoId = ref<string | null>(null)

function openTimelinePhotoViewer(photoId: string) {
  timelineSelectedPhotoId.value = photoId
  timelineViewerVisible.value = true
}

function getEventPhotos(eventId: string): PhotoDTO[] {
  return currentTripPhotos.value.filter((p) =>
    p.bindings?.some((b) => b.kind === 'event' && b.target_id === eventId)
  )
}

// Filters for current trip
const selectedCityFilter = ref<string>('all')
const selectedCategoryFilter = ref<string>('all')
const eventQuery = ref('')
const eventFiltersOpen = ref(false)
const eventFiltersActive = computed(() => selectedCityFilter.value !== 'all' || selectedCategoryFilter.value !== 'all')

// Modals state
const showTripModal = ref(false)
const editingTrip = ref<Trip | null>(null)
const tripModalError = ref('')
const tripModalConflict = ref(false)

const showEventModal = ref(false)
const editingEvent = ref<Event | null>(null)
const eventModalError = ref('')
const eventModalConflict = ref(false)

// Confirm dialog state
const confirmDialogVisible = ref(false)
const confirmationResource = ref<{ id: string; name: string; kind: 'trip' | 'event' } | null>(null)
const confirmDialogTitle = ref('')
const confirmDialogMessage = ref('')
const confirmAction = ref<(() => Promise<void>) | null>(null)

// Unique cities in current trip events
const uniqueCities = computed(() => {
  const cities = new Set<string>()
  for (const evt of currentEvents.value) {
    if (evt.city && evt.city.trim()) {
      cities.add(evt.city.trim())
    }
  }
  return Array.from(cities).sort()
})

// Unique categories in current trip events
const uniqueCategories = computed(() => {
  const categories = new Set<string>()
  for (const evt of currentEvents.value) {
    if (evt.category && evt.category.trim()) {
      categories.add(evt.category.trim())
    }
  }
  return Array.from(categories).sort()
})

// Filtered events for display
const filteredEvents = computed(() => {
  const query = eventQuery.value.trim().toLocaleLowerCase()
  return currentEvents.value.filter((evt) => {
    if (query && ![evt.place_name, evt.city, evt.address, evt.category, evt.notes, evt.date].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)) return false
    if (selectedCityFilter.value !== 'all') {
      if ((evt.city || '').trim() !== selectedCityFilter.value) {
        return false
      }
    }
    if (selectedCategoryFilter.value !== 'all') {
      if ((evt.category || '').trim() !== selectedCategoryFilter.value) {
        return false
      }
    }
    return true
  })
})

const collapsedDates = reactive(new Set<string>())
watch([activeTripId, eventQuery, selectedCityFilter, selectedCategoryFilter], () => collapsedDates.clear())

function toggleDay(date: string) {
  if (!collapsedDates.delete(date)) collapsedDates.add(date)
}

// Timeline: grouped by date
interface DayGroup {
  date: string
  dayNumber: number
  events: Event[]
}

const timelineGroups = computed<DayGroup[]>(() => {
  if (!currentTrip.value) return []

  const groupsMap = new Map<string, Event[]>()

  const trip = currentTrip.value
  const direction = tripStatus(trip) === 'current' ? -1 : 1
  // Reverse only the presentation; recorded positions and NEXT remain unchanged.
  const sorted = [...filteredEvents.value].sort((a, b) => {
    if (a.date !== b.date) {
      return direction * a.date.localeCompare(b.date)
    }
    return direction * ((a.position ?? 0) - (b.position ?? 0) || a.id.localeCompare(b.id))
  })

  for (const evt of sorted) {
    const list = groupsMap.get(evt.date) || []
    list.push(evt)
    groupsMap.set(evt.date, list)
  }

  const startDate = new Date(currentTrip.value.start_date)
  const result: DayGroup[] = []

  const sortedDates = Array.from(groupsMap.keys()).sort((a, b) => direction * a.localeCompare(b))
  for (const dateStr of sortedDates) {
    const curDate = new Date(dateStr)
    const diffDays = Math.round((curDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)) + 1
    result.push({
      date: dateStr,
      dayNumber: diffDays > 0 ? diffDays : 1,
      events: groupsMap.get(dateStr) || []
    })
  }

  return result
})

// Fetch all trips on mount
onMounted(async () => {
  refreshClock()
  clockTimer = setInterval(refreshClock, 60000)
  document.addEventListener('visibilitychange', refreshClock)
  window.addEventListener('focus', refreshClock)
  await fetchTrips()
})
onBeforeUnmount(() => {
  tripsGeneration++
  detailGeneration++
  photosGeneration++
  if (clockTimer !== undefined) clearInterval(clockTimer)
  document.removeEventListener('visibilitychange', refreshClock)
  window.removeEventListener('focus', refreshClock)
})

let tripsGeneration = 0
let detailGeneration = 0
let photosGeneration = 0
async function fetchTrips() {
  const generation = ++tripsGeneration
  clearAlert()
  loadingTrips.value = true
  try {
    const res = await listTrips()
    if (generation !== tripsGeneration) return
    brokenCoverIds.clear()
    trips.value = res.items || []
  } catch (err: any) {
    if (generation === tripsGeneration) showAlert(err instanceof ApiError ? err.detail : '載入旅程清單失敗，請稍後再試。', 'error')
  } finally {
    if (generation === tripsGeneration) loadingTrips.value = false
  }
}

async function selectTrip(tripId: string) {
  const generation = ++detailGeneration
  photosGeneration++
  currentTrip.value = null
  currentEvents.value = []
  currentTripPhotos.value = []
  currentTripCoverId.value = null
  highlightedEventId.value = null
  albumOpen.value = false
  clearAlert()
  loadingDetail.value = true
  activeTripId.value = tripId
  eventQuery.value = ''
  eventFiltersOpen.value = false
  selectedCityFilter.value = 'all'
  selectedCategoryFilter.value = 'all'

  try {
    const res = await getTrip(tripId)
    if (generation !== detailGeneration || activeTripId.value !== tripId) return
    currentTrip.value = res.trip
    currentEvents.value = (res.events || []).sort((a, b) => {
      if (a.date !== b.date) return a.date.localeCompare(b.date)
      return (a.position ?? 0) - (b.position ?? 0)
    })
  } catch (err: any) {
    if (generation !== detailGeneration) return
    showAlert(err instanceof ApiError ? err.detail : '載入旅程手記詳情失敗。', 'error')
    activeTripId.value = null
    currentTrip.value = null
  } finally {
    if (generation === detailGeneration) loadingDetail.value = false
  }
  if (generation === detailGeneration && activeTripId.value === tripId) void fetchTripPhotos(tripId)
}

async function fetchTripPhotos(tripId: string) {
  const generation = ++photosGeneration
  loadingTripPhotos.value = true
  try {
    const [photosRes, coverRes] = await Promise.all([
      listPhotos({ trip_id: tripId }),
      getTripCover(tripId)
    ])
    if (generation !== photosGeneration || activeTripId.value !== tripId) return
    currentTripPhotos.value = photosRes.items || []
    currentTripCoverId.value = coverRes.photo_id
  } catch {
    // Non-blocking
  } finally {
    if (generation === photosGeneration) loadingTripPhotos.value = false
  }
}

async function handleTripPhotoUploaded(photo: PhotoDTO) {
  if (currentTrip.value) {
    try {
      await bindPhoto(photo.id, 'trip', currentTrip.value.id)
      currentTripPhotos.value.push(photo)
      showAlert('已新增照片至旅程相簿。', 'success')
      // Clear staged preview after successful bind (without deleting bound photo)
      // Avoid showing the same image in both the picker and album.
      tripPhotoPickerRef.value?.removePhoto(photo.id)
      if (tripPhotoPickerRef.value?.stagedPhotos?.length === 0) {
        tripPhotoPickerRef.value?.clear()
      }
    } catch (err: any) {
      showAlert(err instanceof ApiError ? err.detail : '新增照片至旅程相簿失敗。', 'error')
    }
  }
}

async function handleCoverUpdated(payload: { tripId: string; photoId: string | null }) {
  const trip = trips.value.find(item => item.id === payload.tripId)
  if (trip) trip.cover_photo_id = payload.photoId
  brokenCoverIds.delete(payload.tripId)
  if (loadingTrips.value) void fetchTrips()
  if (activeTripId.value === payload.tripId) {
    currentTripCoverId.value = payload.photoId
    await fetchTripPhotos(payload.tripId)
  }
}

function handlePhotoDeleted(photoId: string) {
  currentTripPhotos.value = currentTripPhotos.value.filter(p => p.id !== photoId)
  for (const trip of trips.value) {
    if (trip.cover_photo_id === photoId) trip.cover_photo_id = null
  }
  if (currentTripCoverId.value === photoId) currentTripCoverId.value = null
  if (loadingTrips.value) void fetchTrips()
  if (loadingTripPhotos.value && activeTripId.value) void fetchTripPhotos(activeTripId.value)
}

async function handleReorderPhotos(photoIds: string[]) {
  if (!currentTrip.value) return
  try {
    const res = await reorderTripPhotos(currentTrip.value.id, photoIds)
    currentTripPhotos.value = res.items || []
    showAlert('已更新相簿照片順序。', 'success')
  } catch (err: any) {
    showAlert(err instanceof ApiError ? err.detail : '調整照片順序失敗。', 'error')
  }
}

async function handleDeletePhoto(payload: { photoId: string; version: number }) {
  actionInProgress.value = true
  try {
    await deletePhoto(payload.photoId, payload.version)
    handlePhotoDeleted(payload.photoId)
    showAlert('已刪除照片。', 'info')
  } catch (err: any) {
    showAlert(err instanceof ApiError ? err.detail : '刪除照片失敗。', 'error')
  } finally {
    actionInProgress.value = false
  }
}

async function handleRetryPhoto(payload: { photoId: string; version: number }) {
  try {
    const updated = await retryPhoto(payload.photoId, payload.version)
    const idx = currentTripPhotos.value.findIndex((p) => p.id === payload.photoId)
    if (idx !== -1) currentTripPhotos.value[idx] = updated
    showAlert('已重新提交 AI 照片分析。', 'info')
  } catch (err: any) {
    showAlert(err instanceof ApiError ? err.detail : '重試照片分析失敗。', 'error')
  }
}

async function handleUpdateCaption(payload: { photoId: string; caption: string; version: number }) {
  try {
    const updated = await updatePhoto(payload.photoId, { caption: payload.caption, version: payload.version })
    const idx = currentTripPhotos.value.findIndex((p) => p.id === payload.photoId)
    if (idx !== -1) currentTripPhotos.value[idx] = updated
    showAlert('已更新照片說明。', 'success')
  } catch (err: any) {
    showAlert(err instanceof ApiError ? err.detail : '更新照片說明失敗。', 'error')
    throw err
  }
}

function backToTripList() {
  detailGeneration++
  photosGeneration++
  loadingDetail.value = false
  loadingTripPhotos.value = false
  showTripModal.value = false
  showEventModal.value = false
  showFootprintAssistant.value = false
  timelineViewerVisible.value = false
  highlightedEventId.value = null
  clearAlert()
  activeTripId.value = null
  currentTrip.value = null
  currentEvents.value = []
  currentTripPhotos.value = []
  currentTripCoverId.value = null
  fetchTrips()
}

// --- Trip Create / Edit ---
const coverRetry = ref<{ trip: Trip; photoId: string } | null>(null)

function openCreateTripModal() {
  clearAlert()
  editingTrip.value = null
  tripModalError.value = ''
  tripModalConflict.value = false
  showTripModal.value = true
}

function openEditTripModal(trip: Trip) {
  clearAlert()
  editingTrip.value = trip
  tripModalError.value = ''
  tripModalConflict.value = false
  showTripModal.value = true
}

async function finishCreatedTrip(trip: Trip, coverSkipped = false) {
  coverRetry.value = null
  showTripModal.value = false
  await fetchTrips()
  await selectTrip(trip.id)
  if (currentTrip.value?.id === trip.id) {
    showAlert(coverSkipped ? '手記已建立，封面尚未設定。' : `已建立新旅程手記「${trip.name}」`, coverSkipped ? 'info' : 'success')
  }
}

async function applyNewTripCover(trip: Trip, photoId: string) {
  try {
    await bindPhoto(photoId, 'trip', trip.id)
    await setTripCover(trip.id, photoId)
  } catch {
    coverRetry.value = { trip, photoId }
    tripModalError.value = '手記已建立，但封面尚未設定。'
    return
  }
  await finishCreatedTrip(trip)
}

async function retryNewTripCover() {
  if (!coverRetry.value || actionInProgress.value) return
  const { trip, photoId } = coverRetry.value
  actionInProgress.value = true
  try { await applyNewTripCover(trip, photoId) }
  finally { actionInProgress.value = false }
}

async function closeTripModal() {
  if (actionInProgress.value) return
  if (coverRetry.value) await finishCreatedTrip(coverRetry.value.trip, true)
  else showTripModal.value = false
}

async function handleTripSubmit(payload: CreateTripPayload | UpdateTripPayload, photoId?: string) {
  if (actionInProgress.value || coverRetry.value) return
  actionInProgress.value = true
  tripModalError.value = ''
  tripModalConflict.value = false

  try {
    if (editingTrip.value) {
      const updated = await updateTrip(editingTrip.value.id, payload as UpdateTripPayload)
      showAlert(`已成功更新旅程手記「${updated.name}」`, 'success')
      showTripModal.value = false
      if (currentTrip.value && currentTrip.value.id === updated.id) {
        currentTrip.value = updated
      }
      await fetchTrips()
    } else {
      const created = await createTrip(payload as CreateTripPayload)
      if (photoId) await applyNewTripCover(created, photoId)
      else await finishCreatedTrip(created)
    }
  } catch (err: any) {
    if (err instanceof ApiError && err.status === 409) {
      tripModalConflict.value = true
      tripModalError.value = err.detail || '旅程資料已被其他操作更新。'
    } else {
      tripModalError.value = err instanceof ApiError ? err.detail : '儲存旅行手記失敗，請檢查輸入內容。'
    }
  } finally {
    actionInProgress.value = false
  }
}

async function refreshTripFromModal() {
  if (!editingTrip.value) return
  actionInProgress.value = true
  try {
    const detail = await getTrip(editingTrip.value.id)
    editingTrip.value = detail.trip
    if (currentTrip.value && currentTrip.value.id === detail.trip.id) {
      currentTrip.value = detail.trip
      currentEvents.value = detail.events || []
    }
    tripModalConflict.value = false
    tripModalError.value = ''
    showAlert('已重新載入最新旅程手記資料。', 'info')
  } catch (err: any) {
    tripModalError.value = '重新載入失敗：' + (err instanceof ApiError ? err.detail : err.message)
  } finally {
    actionInProgress.value = false
  }
}

// --- Trip Delete ---
function promptDeleteTrip(trip: Trip) {
  confirmationResource.value = { id: trip.id, name: trip.name, kind: 'trip' }
  confirmDialogTitle.value = '確認刪除旅行手記'
  confirmDialogMessage.value = `確定要刪除「${trip.name}」嗎？這將一併移除此旅程記錄的所有足跡。已記錄的地點將被保留以供未來其他旅程使用。`
  confirmAction.value = async () => {
    actionInProgress.value = true
    try {
      await deleteTrip(trip.id, trip.version)
      showAlert(`已刪除旅行手記「${trip.name}」`, 'info')
      confirmDialogVisible.value = false
      if (activeTripId.value === trip.id) {
        activeTripId.value = null
        currentTrip.value = null
      }
      await fetchTrips()
    } catch (err: any) {
      showAlert(err instanceof ApiError ? err.detail : '刪除旅行手記失敗。', 'error')
    } finally {
      actionInProgress.value = false
    }
  }
  confirmDialogVisible.value = true
}

// --- Event Create / Edit ---
function openCreateEventModal() {
  clearAlert()
  editingEvent.value = null
  eventModalError.value = ''
  eventModalConflict.value = false
  showEventModal.value = true
}

function openEditEventModal(event: Event) {
  clearAlert()
  editingEvent.value = event
  eventModalError.value = ''
  eventModalConflict.value = false
  showEventModal.value = true
}

async function handleEventSubmit(
  payload: CreateEventPayload | UpdateEventPayload,
  stagedPhotoIds: string[] = []
) {
  if (!currentTrip.value) return
  actionInProgress.value = true
  eventModalError.value = ''
  eventModalConflict.value = false

  try {
    if (editingEvent.value) {
      const updated = await updateEvent(editingEvent.value.id, payload as UpdateEventPayload)
      showAlert(`已更新旅行足跡「${updated.place_name}」`, 'success')
      showEventModal.value = false
      await selectTrip(currentTrip.value.id)
        } else {
      const created = await createEvent(currentTrip.value.id, payload as CreateEventPayload)
      if (stagedPhotoIds && stagedPhotoIds.length > 0) {
        for (const pId of stagedPhotoIds) {
          try {
            await bindPhoto(pId, 'event', created.id)
          } catch {
            // Non-blocking bind error
          }
        }
      }
      showAlert(`已記錄旅行足跡「${created.place_name}」`, 'success')
      showEventModal.value = false
      await selectTrip(currentTrip.value.id)
        }
  } catch (err: any) {
    if (err instanceof ApiError && err.status === 409) {
      eventModalConflict.value = true
      eventModalError.value = err.detail || '此處旅途足跡已在其他地方更新。'
    } else {
      eventModalError.value = err instanceof ApiError ? err.detail : '儲存旅行足跡失敗，請檢查輸入內容。'
    }
  } finally {
    actionInProgress.value = false
  }
}

async function refreshEventFromModal() {
  if (!currentTrip.value) return
  actionInProgress.value = true
  try {
    await selectTrip(currentTrip.value.id)
    if (editingEvent.value) {
      const refreshed = currentEvents.value.find((e) => e.id === editingEvent.value?.id)
      if (refreshed) {
        editingEvent.value = refreshed
      }
    }
    eventModalConflict.value = false
    eventModalError.value = ''
    showAlert('已重新載入最新足跡資料。', 'info')
  } catch (err: any) {
    eventModalError.value = '重新載入失敗：' + (err instanceof ApiError ? err.detail : err.message)
  } finally {
    actionInProgress.value = false
  }
}

// --- Event Delete ---
function promptDeleteEvent(event: Event) {
  confirmationResource.value = { id: event.id, name: event.place_name, kind: 'event' }
  confirmDialogTitle.value = '確認刪除旅行足跡'
  confirmDialogMessage.value = `確定要從旅程中移除「${event.place_name}」這處足跡紀錄嗎？`
  confirmAction.value = async () => {
    if (!currentTrip.value) return
    actionInProgress.value = true
    try {
      await deleteEvent(event.id, event.version)
      showAlert(`已刪除旅行足跡「${event.place_name}」`, 'info')
      confirmDialogVisible.value = false
      await selectTrip(currentTrip.value.id)
    } catch (err: any) {
      showAlert(err instanceof ApiError ? err.detail : '刪除旅行足跡失敗。', 'error')
    } finally {
      actionInProgress.value = false
    }
  }
  confirmDialogVisible.value = true
}

// Reset filters
function resetFilters() {
  eventQuery.value = ''
  selectedCityFilter.value = 'all'
  selectedCategoryFilter.value = 'all'
}
async function openTrip(tripId: string, eventId?: string) {
  const generation = detailGeneration + 1
  await selectTrip(tripId)
  if (!props.active || detailGeneration !== generation || activeTripId.value !== tripId) return
  highlightedEventId.value = eventId || null
  if (!eventId) return
  const target = currentEvents.value.find(event => event.id === eventId)
  if (target) collapsedDates.delete(target.date)
  await nextTick()
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  document.getElementById(`event-${eventId}`)?.scrollIntoView?.({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'center' })
}

defineExpose({ openTrip, backToTripList, handlePhotoDeleted, actionInProgress })

</script>

<template>
  <!-- TAB 1: Trips Workspace View -->
  <div
    v-if="active"
    id="workspace-panel-trips"
    role="tabpanel"
    aria-labelledby="workspace-tab-trips"
    class="trips-tab-container workspace-panel-enter"
    tabindex="0"
  >
    <!-- VIEW 1: Trip List View -->
    <section v-if="!activeTripId" class="trip-list-section" aria-label="旅程列表">
      <!-- Confident short page heading without filler subtitles per brief -->
      <div class="section-header">
        <h2 class="section-title workspace-page-title">我的旅行手記</h2>
        <button
          type="button"
          class="btn btn-primary create-trip-btn"
          aria-label="建立旅行手記"
          :disabled="loadingTrips || actionInProgress"
          @click="openCreateTripModal"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>建立</span>
        </button>
      </div>

      <form class="trip-library-tools" role="search" :aria-busy="loadingTrips" @submit.prevent>
        <AppSearchBar v-model="tripQuery" class="library-search-bar" label="搜尋旅行手記" placeholder="搜尋手記…">
          <template #actions>
            <button type="button" class="icon-button search-bar__control" :class="{ 'is-active': libraryFiltersActive }" :aria-expanded="libraryFiltersOpen" aria-controls="library-filters" :aria-label="libraryFiltersActive ? '篩選手記（已套用）' : '篩選手記'" @click="libraryFiltersOpen = !libraryFiltersOpen"><AppIcon name="filter" /><span v-if="libraryFiltersActive" class="search-bar__indicator" aria-hidden="true"></span></button>
          </template>
        </AppSearchBar>
        <div v-show="libraryFiltersOpen" id="library-filters" class="library-filters">
          <label><span>旅程狀態</span><select v-model="tripPeriod" class="form-input" aria-label="篩選旅程狀態"><option value="all">全部旅程</option><option value="upcoming">即將出發</option><option value="current">旅行中</option><option value="past">過往旅程</option></select></label>
          <label><span>年份</span><select v-model="tripYear" class="form-input" aria-label="篩選旅程年份"><option value="">所有年份</option><option v-for="year in tripYears" :key="year">{{ year }}</option></select></label>
          <button v-if="libraryFiltersActive" type="button" class="btn-link library-reset" @click="tripPeriod = 'all'; tripYear = ''">清除</button>
        </div>
      </form>
      <div v-if="loadingTrips" class="loading-state" role="status" aria-live="polite">
        <div class="page-spinner ui-spinner ui-spinner--page" aria-hidden="true"></div>
        <p class="loading-text">正在載入您的旅行手記…</p>
      </div>
      <div v-else-if="trips.length === 0" class="empty-state">
        <div class="empty-icon" aria-hidden="true"><AppIcon name="plus" /></div>
        <h3 class="empty-title">尚未記錄任何旅行手記</h3>
        <p class="empty-desc">開啟第一本旅行手記，記錄旅程足跡。</p>
        <button type="button" class="btn btn-primary" @click="openCreateTripModal">建立第一本手記</button>
      </div>
      <p v-else-if="!visibleTrips.length" class="empty-filtered-trips">沒有符合的手記。</p>
      <!-- Trips Grid with Restrained Route Mini-Art per brief -->
      <div v-if="!loadingTrips && visibleTrips.length" class="trip-cards-grid">
        <article
          v-for="trip in visibleTrips"
          :key="trip.id"
          class="trip-card"
          tabindex="0"
          role="button"
          :aria-label="`檢視手記：${trip.name}`"
          @click="selectTrip(trip.id)"
          @keydown.enter="selectTrip(trip.id)"
          @keydown.space.prevent="selectTrip(trip.id)"
        >
          <div class="trip-cover" aria-hidden="true">
            <img
              v-if="trip.cover_photo_id && brokenCoverIds.get(trip.id) !== trip.cover_photo_id"
              :key="trip.cover_photo_id"
              :src="'/api/v1/photos/' + trip.cover_photo_id + '/thumbnail'"
              alt=""
              class="trip-cover-img"
              @error="brokenCoverIds.set(trip.id, trip.cover_photo_id)"
            />
            <svg v-else viewBox="0 0 360 88" fill="none" preserveAspectRatio="xMidYMid slice">
              <path d="M40 59C80 59 68 23 116 25S171 73 216 58 242 22 294 29" stroke="currentColor" stroke-width="2" stroke-dasharray="5 6" stroke-linecap="round" />
              <circle cx="40" cy="59" r="7" fill="var(--color-paper)" stroke="currentColor" stroke-width="2" />
              <circle cx="40" cy="59" r="2.5" fill="currentColor" />
              <circle cx="216" cy="58" r="4" fill="var(--color-paper)" stroke="currentColor" stroke-width="2" />
              <path d="M294 14c-8 0-13 6-13 13 0 10 13 21 13 21s13-11 13-21c0-7-5-13-13-13Z" fill="var(--color-paper)" stroke="currentColor" stroke-width="1.5" />
              <circle cx="294" cy="27" r="4" fill="var(--color-paper)" stroke="currentColor" stroke-width="1.5" />
            </svg>
          </div>
          <div class="trip-card-content">
            <span class="trip-date">{{ trip.start_date }} ~ {{ trip.end_date }}</span>
            <h3 class="trip-name">{{ trip.name }}</h3>

            <p v-if="trip.description" class="trip-desc">
              {{ trip.description }}
            </p>
            <p v-else class="trip-desc is-empty">
              未填寫隨筆備忘
            </p>

            <div class="trip-meta-row">
              <span class="trip-tz-text">{{ trip.timezone }}</span>
              <div class="trip-card-actions" @click.stop @keydown.stop>
                <button
                  type="button"
                  class="btn-icon"
                  title="編輯手記"
                  aria-label="編輯手記"
                  @click="openEditTripModal(trip)"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                  </svg>
                </button>
                <button
                  type="button"
                  class="btn-icon is-danger"
                  title="刪除手記"
                  aria-label="刪除手記"
                  @click="promptDeleteTrip(trip)"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

        </article>
      </div>
    </section>

    <!-- VIEW 2: Trip Detail & Timeline View -->
    <section v-else-if="loadingDetail" class="trip-detail-loading" aria-label="載入旅行手記">
      <button type="button" class="btn-link back-button" @click="backToTripList"><AppIcon name="back" /><span>返回手記列表</span></button>
      <div class="loading-state" role="status" aria-live="polite"><div class="page-spinner ui-spinner ui-spinner--page" aria-hidden="true"></div><p class="loading-text">載入手記中…</p></div>
    </section>
    <section v-else-if="currentTrip" class="trip-detail-section" aria-label="旅行手記詳情與時間軸">
      <!-- Flattened Detail Navigation & Header -->
      <div class="detail-header-block">
        <nav class="detail-nav" aria-label="麵包屑導航">
          <button
            type="button"
            class="btn-link back-button"
            aria-label="返回手記列表"
            @click="backToTripList"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            <span>返回手記列表</span>
          </button>

          <div class="detail-actions">
            <button
              type="button"
              class="icon-button detail-refresh"
              :disabled="actionInProgress"
              @click="selectTrip(currentTrip.id)"
              aria-label="重新整理手記" title="重新整理手記"
            >
              <AppIcon name="refresh" />
            </button>

            <button
              type="button"
              class="btn btn-primary"
              :disabled="actionInProgress"
              @click="openCreateEventModal"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>記錄足跡</span>
            </button>
            <button type="button" class="btn btn-secondary ai-record-btn" :disabled="actionInProgress" @click="showFootprintAssistant = true"><AppIcon name="wand" /><span>AI 幫我記</span></button>
          </div>
        </nav>

        <!-- Flattened Trip Title & Metadata -->
        <div class="trip-summary-line">
          <div class="trip-summary-title-wrap">
            <h2 class="banner-trip-name">{{ currentTrip.name }}</h2>
            <div class="trip-metadata-row">
              <div class="banner-dates">
                <span class="banner-date-icon" aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                    <line x1="16" y1="2" x2="16" y2="6" />
                    <line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                </span>
                <span>{{ currentTrip.start_date }} ～ {{ currentTrip.end_date }}</span>
                <span class="banner-tz-pill">{{ currentTrip.timezone }}</span>
              </div>
              <button v-if="!currentTrip.description" type="button" class="icon-button summary-edit" aria-label="編輯手記" title="編輯手記" :disabled="actionInProgress" @click="openEditTripModal(currentTrip)"><AppIcon name="edit" /></button>
            </div>
          </div>

          <div v-if="currentTrip.description" class="trip-description-row">
            <p class="banner-description">{{ currentTrip.description }}</p>
            <button type="button" class="icon-button summary-edit" aria-label="編輯手記" title="編輯手記" :disabled="actionInProgress" @click="openEditTripModal(currentTrip)"><AppIcon name="edit" /></button>
          </div>
        </div>
      </div>

      <!-- Trip Photo Gallery Section -->
      <section class="trip-gallery-block" aria-label="旅程相簿">
          <div class="album-header photo-control-heading">
          <button type="button" class="album-toggle" :aria-expanded="albumOpen" @click="albumOpen = !albumOpen"><span>旅程相簿 <small>{{ currentTripPhotos.length }}</small></span><AppIcon name="chevron" :class="{ 'is-open': albumOpen }" /></button>
          <PhotoPicker ref="tripPhotoPickerRef" :native-picker="true" :compact="true" :multiple="true" button-text="加入相簿照片" @upload-complete="handleTripPhotoUploaded" />
        </div>
        <div v-show="albumOpen">
        <PhotoGallery
          class="trip-album-photos"
          :photos="currentTripPhotos"
          :cover-photo-id="currentTripCoverId"
          :loading="loadingTripPhotos"
          :can-set-cover="false"
          :can-reorder="true"
          :can-delete="true"
          :can-edit-caption="true"
          empty-text="還沒有照片"
          empty-hint="拍照或加入旅途照片"
          @reorder="handleReorderPhotos"
          @delete="handleDeletePhoto"
          @retry="handleRetryPhoto"
          :save-caption="handleUpdateCaption"
          @refresh="currentTrip && fetchTripPhotos(currentTrip.id)"
        />
        </div>
      </section>

      <form class="filter-bar" role="search" aria-label="搜尋旅途足跡" @submit.prevent>
        <AppSearchBar v-model="eventQuery" plain class="event-search-row" label="搜尋足跡" placeholder="搜尋足跡…">
          <template #actions>
            <button type="button" class="icon-button search-bar__control" :class="{ 'is-active': eventFiltersActive }" :aria-expanded="eventFiltersOpen" aria-controls="event-filter-options" :aria-label="eventFiltersActive ? '篩選足跡（已套用）' : '篩選足跡'" @click="eventFiltersOpen = !eventFiltersOpen"><AppIcon name="filter" /></button>
            <span class="filter-summary" :aria-label="`顯示 ${filteredEvents.length} / ${currentEvents.length} 處旅途足跡`"><span class="count-desktop">顯示 </span>{{ filteredEvents.length }} / {{ currentEvents.length }}<span class="count-desktop"> 處旅途足跡</span></span>
          </template>
        </AppSearchBar>
        <div v-show="eventFiltersOpen" id="event-filter-options" class="filter-controls event-filter-options">
          <div class="filter-field">
            <label for="city-filter" class="sr-only">城市篩選</label>
            <select
              id="city-filter"
              v-model="selectedCityFilter"
              class="form-input filter-select"
            >
              <option value="all">全部城市 ({{ currentEvents.length }})</option>
              <option v-for="c in uniqueCities" :key="c" :value="c">
                {{ c }}
              </option>
            </select>
          </div>

          <div class="filter-field">
            <label for="category-filter" class="sr-only">類別篩選</label>
            <select
              id="category-filter"
              v-model="selectedCategoryFilter"
              class="form-input filter-select"
            >
              <option value="all">全部類別 ({{ currentEvents.length }})</option>
              <option v-for="cat in uniqueCategories" :key="cat" :value="cat">
                {{ cat }}
              </option>
            </select>
          </div>

          <button
            v-if="eventQuery || eventFiltersActive"
            type="button"
            class="btn-link clear-filters-btn"
            @click="resetFilters"
          >
            清除篩選
          </button>
        </div>
      </form>

      <!-- Timeline Content -->
      <div v-if="loadingDetail" class="loading-state" role="status" aria-live="polite">
        <div class="page-spinner ui-spinner ui-spinner--page" aria-hidden="true"></div>
        <p class="loading-text">載入時間軸中...</p>
      </div>

      <!-- Empty Events in Trip -->
      <div v-else-if="currentEvents.length === 0" class="empty-state">
        <div class="empty-icon" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 14 14" />
          </svg>
        </div>
        <h3 class="empty-title">還沒有足跡</h3>
        <p class="empty-desc">記下旅程的第一站。</p>
        <button
          type="button"
          class="btn btn-primary"
          @click="openCreateEventModal"
        >
          記錄第一處足跡
        </button>
      </div>

      <!-- Empty Filtered Results -->
      <div v-else-if="filteredEvents.length === 0" class="empty-state">
        <h3 class="empty-title">還沒找到足跡</h3>
        <p class="empty-desc">換個關鍵字或調整篩選試試。</p>
        <button
          type="button"
          class="btn btn-secondary"
          @click="resetFilters"
        >
          清除篩選條件
        </button>
      </div>

      <!-- Grouped Timeline -->
      <div v-else class="timeline-container">
        <p v-if="tripStatus(currentTrip) === 'unknown'" class="timezone-notice" role="status">此裝置不支援這個旅程時區，暫依行程順序顯示。</p>
        <div
          v-for="day in timelineGroups"
          :key="day.date"
          class="timeline-day-group"
        >
          <h3>
            <button
              type="button"
              class="day-header"
              :aria-expanded="!collapsedDates.has(day.date)"
              :aria-controls="'trip-day-' + day.date"
              @click="toggleDay(day.date)"
            >
              <span class="day-number">Day {{ day.dayNumber }}</span>
              <time class="day-date-heading" :datetime="day.date">{{ day.date }}</time>
              <span class="day-event-count">{{ day.events.length }} 處足跡</span>
              <AppIcon name="chevron" class="day-chevron" />
            </button>
          </h3>

          <!-- Day Events Stream -->
          <div v-show="!collapsedDates.has(day.date)" :id="'trip-day-' + day.date" class="day-events-stream">
            <article
              v-for="evt in day.events"
              :id="'event-' + evt.id"
              :key="evt.id"
              class="event-card"
              :class="{ 'is-highlighted': highlightedEventId === evt.id }"
            >
              <!-- Timeline node connector with route waypoint -->
              <div class="node-connector" aria-hidden="true">
                <div class="node-dot"></div>
                <div class="node-line"></div>
              </div>

              <!-- Event Card Body -->
              <div class="event-card-body">
                <div class="event-card-header">
                  <div class="event-tags">
                    <span class="event-time-badge">
                      {{ evt.time ? evt.time : '未定時間' }}
                    </span>
                    <span class="event-category-pill">
                      {{ evt.category }}
                    </span>
                  </div>

                  <div class="event-header-actions">
                    <LocationLink :location="evt" mode="saved-map" />
                    <button type="button" class="icon-button event-delete" :disabled="actionInProgress" :aria-label="`刪除足跡：${evt.place_name}`" title="刪除足跡" @click="promptDeleteEvent(evt)"><AppIcon name="trash" /></button>
                    <button type="button" class="icon-button" :disabled="actionInProgress" :aria-label="`編輯足跡：${evt.place_name}`" title="編輯足跡" @click="openEditEventModal(evt)"><AppIcon name="edit" /></button>
                  </div>
                </div>

                <div class="event-place-info">
                  <h4 class="event-place-name">{{ evt.place_name }} <span v-if="evt.city" class="event-city-tag"><AppIcon name="pin" /><span>{{ evt.city }}</span></span></h4>
                  <LocationLink class="event-location-text" :location="evt" mode="address" />
                </div>

                <p v-if="evt.notes" class="event-notes-content">
                  {{ evt.notes }}
                </p>

                <!-- Event Photos Thumbnails if present -->
                <div v-if="getEventPhotos(evt.id).length > 0" class="event-photos-strip">
                  <div
                    v-for="ep in getEventPhotos(evt.id)"
                    :key="ep.id"
                    class="event-photo-item"
                    tabindex="0"
                    role="button"
                    :aria-label="`檢視足跡照片：${ep.caption || '照片'}`"
                    @click="openTimelinePhotoViewer(ep.id)"
                    @keydown.enter="openTimelinePhotoViewer(ep.id)"
                  >
                    <img
                      :src="ep.thumbnail_url || ep.url"
                      :alt="ep.caption || '足跡照片'"
                      class="event-photo-thumb"
                    />
                  </div>
                </div>

              </div>
            </article>
          </div>
        </div>
      </div>
    </section>
  </div>

  <FootprintAssistant v-if="currentTrip && activeTripId" :key="currentTrip.id" :visible="showFootprintAssistant" :trip="currentTrip" :categories="uniqueCategories" @close="showFootprintAssistant = false" @saved="handleFootprintsSaved" />

  <!-- Dialogs remain proper modals -->
  <TripDialog
    :visible="showTripModal"
    :trip="editingTrip"
    :cover-photo-id="editingCoverId"
    :cover-retry="Boolean(coverRetry)"
    @cover-updated="handleCoverUpdated"
    :loading="actionInProgress"
    :error-message="tripModalError"
    :has-conflict="tripModalConflict"
    @submit="handleTripSubmit"
    @refresh="refreshTripFromModal"
    @retry-cover="retryNewTripCover"
    @cancel="closeTripModal"
  />

  <EventDialog
    v-if="currentTrip"
    :visible="showEventModal"
    :trip="currentTrip"
    :event="editingEvent"
    :categories="uniqueCategories"
    :loading="actionInProgress"
    :error-message="eventModalError"
    :has-conflict="eventModalConflict"
    @submit="handleEventSubmit"
    @refresh="refreshEventFromModal"
    @cancel="showEventModal = false"
    @notice="(message, type) => showAlert(message, type)"
    @photo-deleted="handlePhotoDeleted"
  />

  <ConfirmDialog
    :visible="confirmDialogVisible"
    :title="confirmDialogTitle"
    :message="confirmDialogMessage"
    :loading="actionInProgress"
    :confirm-text="confirmationResource?.kind === 'trip' ? '刪除手記' : '刪除足跡'"
    :confirmation-mode="confirmationResource?.kind === 'trip' ? 'name' : 'keyword'"
    :confirmation-name="confirmationResource?.name"
    :target-key="confirmationResource?.id"
    @confirm="confirmAction && confirmAction()"
    @cancel="confirmDialogVisible = false"
  />

  <PhotoViewer
    :visible="timelineViewerVisible"
    :photos="currentTripPhotos"
    :initial-photo-id="timelineSelectedPhotoId"
    :can-edit-caption="false"
    @close="timelineViewerVisible = false"
  />
</template>

<style scoped src="./TripJournal.css"></style>
