<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import type { User } from '../types/auth'
import type {
  Trip,
  Event,
  Place,
  CreateTripPayload,
  UpdateTripPayload,
  CreateEventPayload,
  UpdateEventPayload
} from '../types/travel'
import type { SearchItem, SearchEvent } from '../types/search'
import type { Citation } from '../types/conversation'
import {
  listTrips,
  createTrip,
  getTrip,
  updateTrip,
  deleteTrip,
  listPlaces,
  createEvent,
  updateEvent,
  deleteEvent,
  reorderEvents
} from '../api/travel'
import { ApiError } from '../api/auth'
import StatusAlert from './StatusAlert.vue'
import TripDialog from './TripDialog.vue'
import EventDialog from './EventDialog.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import RecallSearch from './RecallSearch.vue'
import ConversationView from './ConversationView.vue'
import SourceDetailModal from './SourceDetailModal.vue'

const props = defineProps<{
  user: User
  loggingOut?: boolean
}>()

const emit = defineEmits<{
  (e: 'logout'): void
}>()

// Workspace active tab navigation
type WorkspaceTab = 'trips' | 'search' | 'chat'
const activeTab = ref<WorkspaceTab>('trips')

interface WorkspaceTabItem {
  id: WorkspaceTab
  label: string
  tabId: string
  panelId: string
}

const TABS: WorkspaceTabItem[] = [
  { id: 'trips', label: '旅行手記', tabId: 'workspace-tab-trips', panelId: 'workspace-panel-trips' },
  { id: 'search', label: '回憶搜尋', tabId: 'workspace-tab-search', panelId: 'workspace-panel-search' },
  { id: 'chat', label: 'AI 對話', tabId: 'workspace-tab-chat', panelId: 'workspace-panel-chat' }
]

const tabButtonRefs = ref<(HTMLButtonElement | null)[]>([])
function setTabRef(el: any, index: number) {
  tabButtonRefs.value[index] = el as HTMLButtonElement | null
}

function switchTab(tab: WorkspaceTab) {
  activeTab.value = tab
}

async function handleTabKeydown(e: KeyboardEvent, currentIndex: number) {
  let targetIndex = -1
  if (e.key === 'ArrowRight') {
    targetIndex = (currentIndex + 1) % TABS.length
  } else if (e.key === 'ArrowLeft') {
    targetIndex = (currentIndex - 1 + TABS.length) % TABS.length
  } else if (e.key === 'Home') {
    targetIndex = 0
  } else if (e.key === 'End') {
    targetIndex = TABS.length - 1
  }

  if (targetIndex !== -1) {
    e.preventDefault()
    switchTab(TABS[targetIndex].id)
    await nextTick()
    tabButtonRefs.value[targetIndex]?.focus()
  }
}

// Source detail modal & timeline jump highlight
const showSourceModal = ref(false)
const sourceModalEventId = ref<string | null>(null)
const sourceModalInitialEvent = ref<SearchEvent | null>(null)
const highlightedEventId = ref<string | null>(null)

function handleViewSearchSource(item: SearchItem) {
  sourceModalInitialEvent.value = item.event
  sourceModalEventId.value = item.event.id
  showSourceModal.value = true
}

function handleViewCitation(cite: Citation) {
  sourceModalInitialEvent.value = null
  sourceModalEventId.value = cite.event_id
  showSourceModal.value = true
}

async function handleJumpToTrip(payload: { tripId: string; eventId: string }) {
  activeTab.value = 'trips'
  await selectTrip(payload.tripId)
  highlightedEventId.value = payload.eventId
  await nextTick()
  const el = document.getElementById(`event-${payload.eventId}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

// Loading states
const loadingTrips = ref(false)
const loadingDetail = ref(false)
const actionInProgress = ref(false)

// Alert notification state
const alertMessage = ref('')
const alertType = ref<'error' | 'success' | 'info'>('info')

function showAlert(message: string, type: 'error' | 'success' | 'info' = 'info') {
  alertMessage.value = message
  alertType.value = type
}

function clearAlert() {
  alertMessage.value = ''
}

// Data state
const trips = ref<Trip[]>([])
const activeTripId = ref<string | null>(null)
const currentTrip = ref<Trip | null>(null)
const currentEvents = ref<Event[]>([])
const nextEdges = ref<Array<{ from_id: string; to_id: string }>>([])
const reusablePlaces = ref<Place[]>([])

// Filters for current trip
const selectedCityFilter = ref<string>('all')
const selectedCategoryFilter = ref<string>('all')

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
  return currentEvents.value.filter((evt) => {
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

// Timeline: grouped by date
interface DayGroup {
  date: string
  dayNumber: number
  events: Event[]
}

const timelineGroups = computed<DayGroup[]>(() => {
  if (!currentTrip.value) return []

  const groupsMap = new Map<string, Event[]>()

  // Sort events by date ascending, then position ascending
  const sorted = [...filteredEvents.value].sort((a, b) => {
    if (a.date !== b.date) {
      return a.date.localeCompare(b.date)
    }
    return a.position - b.position
  })

  for (const evt of sorted) {
    const list = groupsMap.get(evt.date) || []
    list.push(evt)
    groupsMap.set(evt.date, list)
  }

  const startDate = new Date(currentTrip.value.start_date)
  const result: DayGroup[] = []

  const sortedDates = Array.from(groupsMap.keys()).sort()
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

// Check if an event has a route pointing to another event
function getNextEventName(eventId: string): string | null {
  const edge = nextEdges.value.find((e) => e.from_id === eventId)
  if (!edge) return null
  const target = currentEvents.value.find((e) => e.id === edge.to_id)
  return target ? `${target.place_name}` : null
}

// Check reordering bounds on the FULL same-day list (unaffected by active filters)
function canMoveUpInDay(event: Event): boolean {
  const sameDayEvents = currentEvents.value
    .filter((e) => e.date === event.date)
    .sort((a, b) => a.position - b.position)
  const index = sameDayEvents.findIndex((e) => e.id === event.id)
  return index > 0
}

function canMoveDownInDay(event: Event): boolean {
  const sameDayEvents = currentEvents.value
    .filter((e) => e.date === event.date)
    .sort((a, b) => a.position - b.position)
  const index = sameDayEvents.findIndex((e) => e.id === event.id)
  return index >= 0 && index < sameDayEvents.length - 1
}

// Fetch all trips on mount
onMounted(async () => {
  await fetchTrips()
  await fetchPlaces()
})

async function fetchTrips() {
  clearAlert()
  loadingTrips.value = true
  try {
    const res = await listTrips()
    trips.value = res.items || []
  } catch (err: any) {
    showAlert(err instanceof ApiError ? err.detail : '載入旅程清單失敗，請稍後再試。', 'error')
  } finally {
    loadingTrips.value = false
  }
}

async function fetchPlaces() {
  try {
    const res = await listPlaces()
    reusablePlaces.value = res.items || []
  } catch {
    // Non-blocking for places list
  }
}

async function selectTrip(tripId: string) {
  clearAlert()
  loadingDetail.value = true
  activeTripId.value = tripId
  selectedCityFilter.value = 'all'
  selectedCategoryFilter.value = 'all'

  try {
    const res = await getTrip(tripId)
    currentTrip.value = res.trip
    currentEvents.value = (res.events || []).sort((a, b) => {
      if (a.date !== b.date) return a.date.localeCompare(b.date)
      return a.position - b.position
    })
    nextEdges.value = res.next_edges || []
  } catch (err: any) {
    showAlert(err instanceof ApiError ? err.detail : '載入旅程手記詳情失敗。', 'error')
    activeTripId.value = null
    currentTrip.value = null
  } finally {
    loadingDetail.value = false
  }
}

function backToTripList() {
  clearAlert()
  activeTripId.value = null
  currentTrip.value = null
  currentEvents.value = []
  nextEdges.value = []
  fetchTrips()
}

// --- Trip Create / Edit ---
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

async function handleTripSubmit(payload: CreateTripPayload | UpdateTripPayload) {
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
      showAlert(`已建立新旅程手記「${created.name}」`, 'success')
      showTripModal.value = false
      await fetchTrips()
      await selectTrip(created.id)
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
      nextEdges.value = detail.next_edges || []
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

async function handleEventSubmit(payload: CreateEventPayload | UpdateEventPayload) {
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
      await fetchPlaces()
    } else {
      const created = await createEvent(currentTrip.value.id, payload as CreateEventPayload)
      showAlert(`已記錄旅行足跡「${created.place_name}」`, 'success')
      showEventModal.value = false
      await selectTrip(currentTrip.value.id)
      await fetchPlaces()
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

// --- Same-Day Move Up / Down Reorder per contract ---
// Operates on the full-day list even when filters are active, preserving all hidden IDs in the trip
async function moveEventInDay(event: Event, direction: 'up' | 'down') {
  if (!currentTrip.value || actionInProgress.value) return

  // 1. All events in current trip (sorted by date asc, position asc)
  const allEvents = [...currentEvents.value].sort((a, b) => {
    if (a.date !== b.date) return a.date.localeCompare(b.date)
    return a.position - b.position
  })

  // 2. Full list of events on this same date (unaffected by filters)
  const sameDayEvents = allEvents.filter((e) => e.date === event.date)
  const indexInDay = sameDayEvents.findIndex((e) => e.id === event.id)

  if (direction === 'up' && indexInDay <= 0) return
  if (direction === 'down' && indexInDay >= sameDayEvents.length - 1) return

  const targetIndexInDay = direction === 'up' ? indexInDay - 1 : indexInDay + 1
  const swapEvent = sameDayEvents[targetIndexInDay]

  // 3. Swap in global array so that EVERY event in the trip is preserved (no hidden events discarded)
  const globalIndexA = allEvents.findIndex((e) => e.id === event.id)
  const globalIndexB = allEvents.findIndex((e) => e.id === swapEvent.id)

  const reordered = [...allEvents]
  reordered[globalIndexA] = swapEvent
  reordered[globalIndexB] = event

  const eventIds = reordered.map((e) => e.id)

  actionInProgress.value = true
  clearAlert()

  try {
    const res = await reorderEvents(currentTrip.value.id, {
      version: currentTrip.value.version,
      event_ids: eventIds
    })
    currentTrip.value = res.trip
    currentEvents.value = (res.events || []).sort((a, b) => {
      if (a.date !== b.date) return a.date.localeCompare(b.date)
      return a.position - b.position
    })
    nextEdges.value = res.next_edges || []
    showAlert('已更新足跡順序。', 'success')
  } catch (err: any) {
    if (err instanceof ApiError && err.status === 409) {
      showAlert('順序調整提示：旅程紀錄已在其他地方更新，已為您重新整理最新狀態。', 'error')
      await selectTrip(currentTrip.value.id)
    } else {
      showAlert(err instanceof ApiError ? err.detail : '調整足跡順序失敗。', 'error')
    }
  } finally {
    actionInProgress.value = false
  }
}

// Reset filters
function resetFilters() {
  selectedCityFilter.value = 'all'
  selectedCategoryFilter.value = 'all'
}
</script>

<template>
  <div class="workspace-root">
    <!-- Top Bar: User Identity & Global Actions -->
    <header class="workspace-topbar">
      <div class="user-greeting">
        <div class="user-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <div class="user-details">
          <span class="user-label">旅人手記工作區</span>
          <span class="user-email">{{ user.email }}</span>
        </div>
      </div>

      <div class="topbar-actions">
        <button
          type="button"
          class="btn btn-secondary logout-button"
          :disabled="loggingOut || actionInProgress"
          @click="emit('logout')"
        >
          <span v-if="loggingOut" class="spinner-small" aria-hidden="true"></span>
          <span>{{ loggingOut ? '登出中...' : '登出手記' }}</span>
        </button>
      </div>
    </header>

    <!-- Workspace Navigation Tabs -->
    <nav class="workspace-nav" role="tablist" aria-label="工作區功能切換">
      <button
        v-for="(t, index) in TABS"
        :id="t.tabId"
        :key="t.id"
        :ref="(el) => setTabRef(el, index)"
        type="button"
        class="nav-tab-btn"
        :class="{ 'is-active': activeTab === t.id }"
        :aria-selected="activeTab === t.id"
        :aria-controls="t.panelId"
        role="tab"
        :tabindex="activeTab === t.id ? 0 : -1"
        @click="switchTab(t.id)"
        @keydown="handleTabKeydown($event, index)"
      >
        <svg v-if="t.id === 'trips'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
        <svg v-else-if="t.id === 'search'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <svg v-else-if="t.id === 'chat'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span>{{ t.label }}</span>
      </button>
    </nav>

    <!-- Global Alert Area -->
    <StatusAlert :message="alertMessage" :type="alertType" />

    <!-- TAB 1: Trips Workspace View -->
    <div
      v-if="activeTab === 'trips'"
      id="workspace-panel-trips"
      role="tabpanel"
      aria-labelledby="workspace-tab-trips"
      class="trips-tab-container"
      tabindex="0"
    >
      <!-- VIEW 1: Trip List View -->
      <section v-if="!activeTripId" class="trip-list-section" aria-label="旅程列表">
      <div class="section-header">
        <div>
          <h2 class="section-title">我的旅行手記</h2>
          <p class="section-subtitle">點選旅程回顧足跡隨筆，或記錄一段新的旅行回憶。</p>
        </div>
        <button
          type="button"
          class="btn btn-primary create-trip-btn"
          :disabled="loadingTrips || actionInProgress"
          @click="openCreateTripModal"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>新增旅程手記</span>
        </button>
      </div>

      <!-- Loading Trips Skeleton -->
      <div v-if="loadingTrips" class="loading-state" role="status" aria-live="polite">
        <div class="page-spinner" aria-hidden="true"></div>
        <p class="loading-text">正在載入您的旅行手記...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="trips.length === 0" class="empty-state">
        <div class="empty-icon" aria-hidden="true">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="15" y2="15" />
          </svg>
        </div>
        <h3 class="empty-title">尚未記錄任何旅行手記</h3>
        <p class="empty-desc">每一次出發與停駐都值得被記錄。點擊上方「新增旅程手記」，開啟你的第一本回憶筆記。</p>
        <button
          type="button"
          class="btn btn-primary"
          @click="openCreateTripModal"
        >
          記錄第一趟旅程
        </button>
      </div>

      <!-- Trips Grid -->
      <div v-else class="trip-cards-grid">
        <article
          v-for="trip in trips"
          :key="trip.id"
          class="trip-card"
          tabindex="0"
          role="button"
          :aria-label="`檢視手記：${trip.name}`"
          @click="selectTrip(trip.id)"
          @keydown.enter="selectTrip(trip.id)"
          @keydown.space.prevent="selectTrip(trip.id)"
        >
          <div class="trip-card-content">
            <div class="trip-badge-row">
              <span class="trip-date-pill">
                {{ trip.start_date }} ~ {{ trip.end_date }}
              </span>
            </div>

            <h3 class="trip-name">{{ trip.name }}</h3>

            <p v-if="trip.description" class="trip-desc">
              {{ trip.description }}
            </p>
            <p v-else class="trip-desc is-empty">
              未填寫隨筆備忘
            </p>

            <div class="trip-meta-row">
              <span class="trip-timezone">時區：{{ trip.timezone }}</span>
            </div>
          </div>

          <div class="trip-card-actions" @click.stop>
            <button
              type="button"
              class="btn-icon"
              title="編輯手記"
              aria-label="編輯手記"
              @click="openEditTripModal(trip)"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </div>
        </article>
      </div>
    </section>

    <!-- VIEW 2: Trip Detail & Timeline View -->
    <section v-else-if="currentTrip" class="trip-detail-section" aria-label="旅行手記詳情與時間軸">
      <!-- Detail Navigation Header -->
      <nav class="detail-nav" aria-label="麵包屑導航">
        <button
          type="button"
          class="btn-link back-button"
          @click="backToTripList"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          <span>返回手記列表</span>
        </button>

        <div class="detail-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="actionInProgress"
            @click="selectTrip(currentTrip.id)"
          >
            重新整理
          </button>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="actionInProgress"
            @click="openEditTripModal(currentTrip)"
          >
            編輯手記
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="actionInProgress"
            @click="openCreateEventModal"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>記錄足跡</span>
          </button>
        </div>
      </nav>

      <!-- Trip Overview Card -->
      <div class="trip-banner-card">
        <div class="banner-top">
          <div class="banner-title-wrap">
            <h2 class="banner-trip-name">{{ currentTrip.name }}</h2>
          </div>
          <div class="banner-dates">
            <span class="banner-date-icon" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </span>
            <span>{{ currentTrip.start_date }} 至 {{ currentTrip.end_date }}</span>
            <span class="banner-tz-pill">{{ currentTrip.timezone }}</span>
          </div>
        </div>

        <p v-if="currentTrip.description" class="banner-description">
          {{ currentTrip.description }}
        </p>
      </div>

      <!-- Filter Bar: City & Category Filtering in Current Trip -->
      <div class="filter-bar" role="region" aria-label="旅途回憶篩選">
        <div class="filter-controls">
          <div class="filter-field">
            <label for="city-filter" class="filter-label">城市篩選：</label>
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
            <label for="category-filter" class="filter-label">類別篩選：</label>
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
            v-if="selectedCityFilter !== 'all' || selectedCategoryFilter !== 'all'"
            type="button"
            class="btn-link clear-filters-btn"
            @click="resetFilters"
          >
            清除篩選
          </button>
        </div>

        <div class="filter-summary">
          <span>顯示 {{ filteredEvents.length }} / {{ currentEvents.length }} 處旅途足跡</span>
        </div>
      </div>

      <!-- Timeline Content -->
      <div v-if="loadingDetail" class="loading-state" role="status" aria-live="polite">
        <div class="page-spinner" aria-hidden="true"></div>
        <p class="loading-text">載入時間軸中...</p>
      </div>

      <!-- Empty Events in Trip -->
      <div v-else-if="currentEvents.length === 0" class="empty-state">
        <div class="empty-icon" aria-hidden="true">
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 14 14" />
          </svg>
        </div>
        <h3 class="empty-title">這趟旅程尚未記錄任何足跡</h3>
        <p class="empty-desc">寫下第一個值得留存的旅行回憶吧！點擊下方按鈕開始記錄。</p>
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
        <h3 class="empty-title">沒有符合篩選條件的旅途紀錄</h3>
        <p class="empty-desc">請調整上方的城市或類別條件，或點擊清除篩選。</p>
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
        <div
          v-for="day in timelineGroups"
          :key="day.date"
          class="timeline-day-group"
        >
          <!-- Day Header -->
          <div class="day-header">
            <div class="day-marker" aria-hidden="true">
              <span class="day-number">Day {{ day.dayNumber }}</span>
            </div>
            <h3 class="day-date-heading">{{ day.date }}</h3>
            <span class="day-event-count">{{ day.events.length }} 處足跡</span>
          </div>

          <!-- Day Events Stream -->
          <div class="day-events-stream">
            <article
              v-for="evt in day.events"
              :id="'event-' + evt.id"
              :key="evt.id"
              class="event-card"
              :class="{ 'is-highlighted': highlightedEventId === evt.id }"
            >
              <!-- Timeline node connector -->
              <div class="node-connector" aria-hidden="true">
                <div class="node-dot"></div>
                <div class="node-line"></div>
              </div>

              <!-- Main Event Card Body -->
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

                  <!-- Same-Day Move Up / Down Buttons (Checking full-day list, preserving all IDs) -->
                  <div class="event-reorder-actions" aria-label="同日足跡順序調整">
                    <button
                      type="button"
                      class="btn-reorder"
                      :disabled="!canMoveUpInDay(evt) || actionInProgress"
                      :title="!canMoveUpInDay(evt) ? '已是當日最前足跡' : '在同日足跡中往上移一位'"
                      :aria-label="`將 ${evt.place_name} 往上移`"
                      @click="moveEventInDay(evt, 'up')"
                    >
                      ▲ 往上移
                    </button>
                    <button
                      type="button"
                      class="btn-reorder"
                      :disabled="!canMoveDownInDay(evt) || actionInProgress"
                      :title="!canMoveDownInDay(evt) ? '已是當日最後足跡' : '在同日足跡中往下移一位'"
                      :aria-label="`將 ${evt.place_name} 往下移`"
                      @click="moveEventInDay(evt, 'down')"
                    >
                      ▼ 往下移
                    </button>
                  </div>
                </div>

                <div class="event-place-info">
                  <h4 class="event-place-name">{{ evt.place_name }}</h4>
                  <div v-if="evt.city || evt.address" class="event-location-text">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                    <span>{{ [evt.city, evt.address].filter(Boolean).join(' · ') }}</span>
                  </div>
                </div>

                <p v-if="evt.notes" class="event-notes-content">
                  {{ evt.notes }}
                </p>

                <!-- Route connection indication -->
                <div v-if="getNextEventName(evt.id)" class="next-destination-indicator">
                  <span class="next-arrow" aria-hidden="true">➔</span>
                  <span class="next-label">接續足跡：</span>
                  <span class="next-target-name">{{ getNextEventName(evt.id) }}</span>
                </div>

                <!-- Event Bottom Actions -->
                <div class="event-footer-actions">
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    :disabled="actionInProgress"
                    @click="openEditEventModal(evt)"
                  >
                    編輯
                  </button>
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm btn-delete-text"
                    :disabled="actionInProgress"
                    @click="promptDeleteEvent(evt)"
                  >
                    刪除
                  </button>
                </div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>
    </div>

    <!-- TAB 2: Recall Search View -->
    <div
      v-else-if="activeTab === 'search'"
      id="workspace-panel-search"
      role="tabpanel"
      aria-labelledby="workspace-tab-search"
      class="tabpanel-container"
      tabindex="0"
    >
      <RecallSearch
        :trips="trips"
        @view-source="handleViewSearchSource"
        @jump-trip="handleJumpToTrip"
      />
    </div>

    <!-- TAB 3: AI Conversation View -->
    <div
      v-else-if="activeTab === 'chat'"
      id="workspace-panel-chat"
      role="tabpanel"
      aria-labelledby="workspace-tab-chat"
      class="tabpanel-container"
      tabindex="0"
    >
      <ConversationView
        @view-citation="handleViewCitation"
        @jump-trip="handleJumpToTrip"
      />
    </div>

    <!-- Modals -->
    <TripDialog
      :visible="showTripModal"
      :trip="editingTrip"
      :loading="actionInProgress"
      :error-message="tripModalError"
      :has-conflict="tripModalConflict"
      @submit="handleTripSubmit"
      @refresh="refreshTripFromModal"
      @cancel="showTripModal = false"
    />

    <EventDialog
      v-if="currentTrip"
      :visible="showEventModal"
      :trip="currentTrip"
      :event="editingEvent"
      :places="reusablePlaces"
      :loading="actionInProgress"
      :error-message="eventModalError"
      :has-conflict="eventModalConflict"
      @submit="handleEventSubmit"
      @refresh="refreshEventFromModal"
      @cancel="showEventModal = false"
    />

    <ConfirmDialog
      :visible="confirmDialogVisible"
      :title="confirmDialogTitle"
      :message="confirmDialogMessage"
      :loading="actionInProgress"
      @confirm="confirmAction && confirmAction()"
      @cancel="confirmDialogVisible = false"
    />

    <SourceDetailModal
      :visible="showSourceModal"
      :event-id="sourceModalEventId"
      :initial-event="sourceModalInitialEvent"
      @close="showSourceModal = false"
      @jump="handleJumpToTrip"
    />
  </div>
</template>

<style scoped>
.workspace-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

/* Workspace navigation */
.workspace-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 2px solid var(--color-border);
  padding-bottom: 0.5rem;
  min-width: 0;
  width: 100%;
}

.nav-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 44px;
  padding: 0.5rem 1.125rem;
  font-family: var(--font-sans);
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-subtle);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.nav-tab-btn:hover {
  color: var(--color-ink);
  background-color: rgba(23, 107, 104, 0.06);
}

.nav-tab-btn.is-active {
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.1);
  border-color: rgba(23, 107, 104, 0.25);
}

.nav-tab-btn:focus-visible {
  outline: 2px solid var(--color-teal);
  outline-offset: 2px;
}

.tabpanel-container {
  width: 100%;
  min-width: 0;
}

.tabpanel-container:focus,
.trips-tab-container:focus {
  outline: none;
}

.trips-tab-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Top bar */
.workspace-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 1.25rem;
  border-bottom: 1px dashed var(--color-border);
}

.user-greeting {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.user-icon {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background-color: rgba(23, 107, 104, 0.1);
  color: var(--color-teal);
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-details {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.user-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-teal);
  letter-spacing: 0.05em;
}

.user-email {
  overflow-wrap: anywhere;
  font-size: 0.9375rem;
  color: var(--color-ink);
  font-weight: 500;
}

.logout-button {
  min-height: 44px;
  white-space: nowrap;
  padding: 0.4rem 1rem;
  font-size: 0.875rem;
}

/* Section Header */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.section-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-ink);
}

.section-subtitle {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  margin-top: 0.25rem;
}

.create-trip-btn {
  display: inline-flex;
  gap: 0.5rem;
}

/* Trip Cards Grid */
.trip-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.25rem;
}

.trip-card {
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1.25rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 1rem;
  transition: all 0.2s ease;
  position: relative;
  text-align: left;
}

.trip-card:hover {
  border-color: var(--color-teal);
  box-shadow: 0 4px 14px rgba(21, 62, 72, 0.08);
  transform: translateY(-2px);
}

.trip-card:focus-visible {
  outline: 2px solid var(--color-teal);
  outline-offset: 2px;
}

.trip-card-content {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.trip-badge-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.trip-date-pill {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.08);
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
}

.trip-name {
  font-size: 1.1875rem;
  font-weight: 600;
  color: var(--color-ink);
  line-height: 1.3;
}

.trip-desc {
  font-size: 0.875rem;
  color: var(--color-subtle);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.trip-desc.is-empty {
  font-style: italic;
  opacity: 0.7;
}

.trip-meta-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--color-subtle);
}

.trip-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  border-top: 1px dashed var(--color-border);
  padding-top: 0.75rem;
}

.btn-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  background-color: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-subtle);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-icon:hover {
  background-color: #edf5f7;
  color: var(--color-ink);
}

.btn-icon.is-danger:hover {
  background-color: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error-text);
}

/* Detail Navigation */
.detail-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.back-button {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0;
  font-weight: 500;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Trip Banner Card */
.trip-banner-card {
  background-color: #f7fbfc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.banner-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.banner-title-wrap {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.banner-trip-name {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-ink);
}

.banner-dates {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--color-subtle);
}

.banner-date-icon {
  display: flex;
  align-items: center;
}

.banner-tz-pill {
  font-size: 0.75rem;
  background-color: #e5f1f4;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-sm);
  color: var(--color-teal);
}

.banner-description {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  line-height: 1.5;
  white-space: pre-line;
}

/* Filter Bar */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  background-color: #ffffff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0.75rem 1rem;
  margin-bottom: 1.5rem;
}

.filter-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.filter-field {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.filter-label {
  font-size: 0.8125rem;
  color: var(--color-subtle);
  font-weight: 500;
}

.filter-select {
  min-height: 36px;
  padding: 0.25rem 0.625rem;
  font-size: 0.875rem;
  width: auto;
}

.clear-filters-btn {
  padding: 0;
  min-height: auto;
  font-size: 0.8125rem;
}

.filter-summary {
  font-size: 0.8125rem;
  color: var(--color-subtle);
}

/* Timeline Layout */
.timeline-container {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.timeline-day-group {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.day-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--color-border);
}

.day-marker {
  background-color: var(--color-yellow);
  color: #4a3805;
  font-weight: 700;
  font-size: 0.8125rem;
  padding: 0.25rem 0.625rem;
  border-radius: var(--radius-sm);
  letter-spacing: 0.05em;
}

.day-date-heading {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-ink);
}

.day-event-count {
  font-size: 0.8125rem;
  color: var(--color-subtle);
  margin-left: auto;
}

.day-events-stream {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  position: relative;
  padding-left: 1rem;
}

.event-card {
  display: flex;
  gap: 1rem;
  position: relative;
}

.node-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
  padding-top: 1rem;
}

.node-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background-color: var(--color-teal);
  border: 3px solid #ffffff;
  box-shadow: 0 0 0 1px var(--color-teal);
  z-index: 2;
}

.node-line {
  width: 2px;
  flex-grow: 1;
  background-color: var(--color-border);
  margin-top: 0.25rem;
  min-height: 40px;
}

.event-card-body {
  flex-grow: 1;
  background-color: #ffffff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  box-shadow: 0 2px 6px rgba(21, 62, 72, 0.04);
  transition: all 0.3s ease;
}

.event-card.is-highlighted .event-card-body {
  border-color: var(--color-teal);
  box-shadow: 0 0 0 3px rgba(23, 107, 104, 0.3), 0 6px 16px rgba(21, 62, 72, 0.12);
  background-color: #f7fdfd;
}

.event-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.event-tags {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.event-time-badge {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.1);
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
}

.event-category-pill {
  font-size: 0.75rem;
  font-weight: 500;
  color: #4a3805;
  background-color: #fff2c4;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-sm);
}

.event-reorder-actions {
  display: flex;
  gap: 0.375rem;
}

.btn-reorder {
  min-height: 32px;
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
  font-weight: 500;
  background-color: #f7fbfc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-ink);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-reorder:hover:not(:disabled) {
  background-color: rgba(23, 107, 104, 0.08);
  border-color: var(--color-teal);
  color: var(--color-teal);
}

.btn-reorder:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.event-place-name {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-ink);
  line-height: 1.3;
}

.event-location-text {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-subtle);
  margin-top: 0.25rem;
}

.event-notes-content {
  font-size: 0.875rem;
  color: var(--color-subtle);
  line-height: 1.5;
  white-space: pre-line;
  background-color: #fafdfd;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-teal);
}

.next-destination-indicator {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.06);
  padding: 0.35rem 0.625rem;
  border-radius: var(--radius-sm);
}

.next-arrow {
  font-weight: bold;
}

.next-label {
  font-weight: 500;
}

.next-target-name {
  font-weight: 600;
}

.event-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  border-top: 1px dashed var(--color-border);
  padding-top: 0.625rem;
}

.btn-sm {
  min-height: 32px;
  padding: 0.25rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-delete-text {
  color: var(--color-error-text);
}

.btn-delete-text:hover:not(:disabled) {
  background-color: var(--color-error-bg);
  border-color: var(--color-error-border);
}

/* Loading & Empty states */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  gap: 1rem;
}

.page-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(23, 107, 104, 0.2);
  border-top-color: var(--color-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 0.9375rem;
  color: var(--color-subtle);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
  background-color: #fafdfd;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  gap: 1rem;
}

.empty-icon {
  color: var(--color-teal);
  opacity: 0.7;
}

.empty-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-ink);
}

.empty-desc {
  font-size: 0.875rem;
  color: var(--color-subtle);
  max-width: 420px;
  line-height: 1.5;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(23, 107, 104, 0.3);
  border-top-color: var(--color-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .workspace-nav {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.25rem;
    padding-bottom: 0.5rem;
    width: 100%;
    min-width: 0;
    overflow-x: visible;
  }

  .nav-tab-btn {
    width: 100%;
    min-width: 0;
    min-height: 44px;
    padding: 0.35rem 0.25rem;
    gap: 0.35rem;
    justify-content: center;
    font-size: 0.8125rem;
  }

  .nav-tab-btn svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .nav-tab-btn span {
    white-space: nowrap;
    font-weight: 600;
  }

  .workspace-topbar {
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .trip-cards-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .event-card {
    min-width: 0;
  }

  .event-card-body {
    min-width: 0;
  }

  .day-events-stream {
    padding-left: 0;
  }

  .node-connector {
    display: none;
  }

  .banner-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-controls {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-field {
    width: 100%;
    justify-content: space-between;
  }

  .filter-select {
    flex-grow: 1;
  }
}
</style>
