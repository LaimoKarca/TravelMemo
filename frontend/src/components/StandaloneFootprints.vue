<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError } from '../api/auth'
import { bindPhoto } from '../api/photos'
import { createStandaloneEvent, deleteEvent, getEvent, listStandaloneEvents, updateEvent } from '../api/travel'
import type { CreateEventPayload, Event, EventDestination, UpdateEventPayload } from '../types/travel'
import AppIcon from './AppIcon.vue'
import AttachFootprintDialog from './AttachFootprintDialog.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import EventDialog from './EventDialog.vue'
import TrailLoader from './TrailLoader.vue'

const props = defineProps<{ focusId?: string | null }>()
const emit = defineEmits<{
  view: [Event]
  jump: [EventDestination]
  notice: [string, 'success' | 'error']
  unfocus: []
  'photo-deleted': [string]
}>()
const queryInput = ref('')
const filtersOpen = ref(false)
const city = ref('')
const category = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const applied = ref({ q: '', city: '', category: '', date_from: '', date_to: '' })
const filterError = ref('')
const failedAppend = ref(false)
const events = ref<Event[]>([])
const offset = ref<number | null>(null)
const focused = ref<Event | null>(null)
const error = ref('')
const loading = ref(false)
const loadingFocus = ref(false)
const editorOpen = ref(false)
const editing = ref<Event | null>(null)
const busy = ref(false)
const editorError = ref('')
const editorConflict = ref(false)
const deleting = ref<Event | null>(null)
const attaching = ref<Event | null>(null)
const listRef = ref<HTMLElement | null>(null)
const filterButton = ref<HTMLButtonElement | null>(null)
const openMenuId = ref<string | null>(null)
const menuAbove = ref(false)
let menuTrigger: HTMLButtonElement | null = null
let pageGeneration = 0
let focusGeneration = 0
let active = true

const results = computed(() => focused.value && !events.value.some(e => e.id === focused.value?.id)
  ? [focused.value, ...events.value] : events.value)
const groups = computed(() => {
  const days = new Map<string, Event[]>()
  for (const event of results.value) {
    const entries = days.get(event.date) || []
    entries.push(event)
    days.set(event.date, entries)
  }
  return [...days.entries()]
})
const categories = computed(() => [...new Set(events.value.map(event => event.category).filter(Boolean))])
const appliedFiltersActive = computed(() => Boolean(applied.value.city || applied.value.category || applied.value.date_from || applied.value.date_to))
const filtersActive = computed(() => Boolean(city.value || category.value || dateFrom.value || dateTo.value))
const isFiltered = computed(() => appliedFiltersActive.value || Boolean(applied.value.q))
const showReset = computed(() => Boolean(queryInput.value || filtersActive.value || isFiltered.value))
const loadingMore = computed(() => loading.value && offset.value !== null)

function closeMenu(restoreFocus = false) {
  const trigger = menuTrigger
  menuTrigger = null
  openMenuId.value = null
  if (restoreFocus) trigger?.focus({ preventScroll: true })
}

function toggleMenu(event: MouseEvent, id: string) {
  if (openMenuId.value === id) { closeMenu(); return }
  menuTrigger = event.currentTarget as HTMLButtonElement
  const bottomNavHeight = document.querySelector('.mobile-bottom-nav')?.getBoundingClientRect().height ?? 0
  menuAbove.value = window.innerHeight - bottomNavHeight - menuTrigger.getBoundingClientRect().bottom < 150
  openMenuId.value = id
}

function closeOutside(event: globalThis.Event) {
  if (event.target instanceof Node && menuTrigger && !menuTrigger.parentElement?.contains(event.target)) closeMenu()
}

function closeOnEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !menuTrigger) return
  event.preventDefault()
  event.stopPropagation()
  closeMenu(true)
}

async function loadPage(append = false) {
  if (append && (loading.value || offset.value === null)) return
  const generation = ++pageGeneration
  error.value = ''
  failedAppend.value = false
  if (!append) { closeMenu(); offset.value = null; events.value = [] }
  loading.value = true
  try {
    const page = await listStandaloneEvents({ ...applied.value, limit: 20, offset: append ? offset.value! : 0 })
    if (generation !== pageGeneration) return
    const known = new Set(events.value.map(event => event.id))
    events.value = [...events.value, ...page.items.filter(event => !known.has(event.id))]
    offset.value = page.next_offset
  } catch (err) {
    if (generation === pageGeneration) {
      failedAppend.value = append
      error.value = message(err, '無法載入日常足跡。')
    }
  } finally {
    if (generation === pageGeneration) loading.value = false
  }
}

function message(err: unknown, fallback: string) { return err instanceof ApiError ? err.detail : fallback }
function clearFocus() { focused.value = null; emit('unfocus') }
function applyFilters() {
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    filtersOpen.value = true
    filterError.value = '結束日期須等於或晚於開始日期。'
    return
  }
  filterError.value = ''
  applied.value = {
    q: queryInput.value.trim(), city: city.value.trim(), category: category.value.trim(),
    date_from: dateFrom.value, date_to: dateTo.value
  }
  clearFocus()
  void loadPage()
}
watch([dateFrom, dateTo], () => { filterError.value = '' })
function resetFilters() {
  city.value = ''; category.value = ''; dateFrom.value = ''; dateTo.value = ''; queryInput.value = ''
  applyFilters()
}
function clearSearchAndFilters() {
  resetFilters()
  filterButton.value?.focus({ preventScroll: true })
}
async function scrollToFocus() {
  await nextTick()
  const row = listRef.value?.querySelector<HTMLElement>('[data-focused=true]')
  row?.focus({ preventScroll: true })
  row?.scrollIntoView?.({ block: 'nearest' })
}

watch(() => props.focusId, async (id) => {
  const generation = ++focusGeneration
  focused.value = null
  loadingFocus.value = !!id
  if (!id) return
  try {
    const event = await getEvent(id)
    if (generation !== focusGeneration) return
    if (event.trip_id) { emit('jump', { tripId: event.trip_id, eventId: event.id }); return }
    focused.value = event
    await scrollToFocus()
  } catch (err) {
    if (generation === focusGeneration) emit('notice', message(err, '找不到這筆足跡。'), 'error')
  } finally {
    if (generation === focusGeneration) loadingFocus.value = false
  }
}, { immediate: true })
onMounted(() => {
  document.addEventListener('pointerdown', closeOutside)
  document.addEventListener('focusin', closeOutside)
  document.addEventListener('keydown', closeOnEscape, true)
  void loadPage()
})
onBeforeUnmount(() => {
  active = false
  pageGeneration++
  focusGeneration++
  document.removeEventListener('pointerdown', closeOutside)
  document.removeEventListener('focusin', closeOutside)
  document.removeEventListener('keydown', closeOnEscape, true)
})

function openEditor(event: Event | null) {
  editing.value = event
  editorError.value = ''
  editorConflict.value = false
  editorOpen.value = true
}
async function refreshEdit() {
  if (!editing.value || busy.value) return
  try {
    const latest = await getEvent(editing.value.id)
    if (latest.trip_id) { editorOpen.value = false; emit('jump', { tripId: latest.trip_id, eventId: latest.id }); return }
    editing.value = latest
    editorConflict.value = false
    editorError.value = ''
  } catch (err) { editorError.value = message(err, '無法載入最新足跡。') }
}
async function save(payload: CreateEventPayload | UpdateEventPayload, photos: string[] = []) {
  if (busy.value) return
  busy.value = true
  editorError.value = ''
  const previous = editing.value
  try {
    const event = previous
      ? await updateEvent(previous.id, payload as UpdateEventPayload)
      : await createStandaloneEvent(payload)
    const bindings = await Promise.allSettled(photos.map(id => bindPhoto(id, 'event', event.id)))
    if (!active) return
    editorOpen.value = false
    if (!previous) { resetFilters(); emit('jump', { tripId: null, eventId: event.id }) }
    else {
      if (focused.value?.id === event.id) focused.value = event
      await loadPage()
    }
    const failed = bindings.filter(result => result.status === 'rejected').length
    emit('notice', failed ? `足跡已儲存，${failed} 張照片未能加入。可在編輯時重新加入。` : '足跡已儲存。', failed ? 'error' : 'success')
  } catch (err) {
    editorConflict.value = err instanceof ApiError && err.status === 409
    editorError.value = message(err, '無法儲存足跡。')
  } finally { busy.value = false }
}
async function remove() {
  const event = deleting.value
  if (!event || busy.value) return
  busy.value = true
  try {
    await deleteEvent(event.id, event.version)
    deleting.value = null
    if (focused.value?.id === event.id) clearFocus()
    emit('notice', '足跡已刪除。', 'success')
    await loadPage()
  } catch (err) {
    deleting.value = null
    emit('notice', message(err, '無法刪除足跡。'), 'error')
    await loadPage()
  } finally { busy.value = false }
}
function attached(event: Event) {
  attaching.value = null
  if (focused.value?.id === event.id) clearFocus()
  emit('jump', { tripId: event.trip_id, eventId: event.id })
  emit('notice', '足跡已收進手記。', 'success')
}
function closeAttach(stale: boolean) {
  attaching.value = null
  if (stale) {
    clearFocus()
    void loadPage()
  }
}
</script>

<template>
  <section class="daily" aria-labelledby="daily-title">
    <header class="daily-header">
      <h2 id="daily-title">日常足跡</h2>
      <button type="button" class="btn btn-primary quick-record" aria-label="記錄日常足跡" title="記錄日常足跡" @click="openEditor(null)"><AppIcon name="plus" /></button>
    </header>
    <form role="search" aria-label="搜尋日常足跡" novalidate @submit.prevent="applyFilters">
      <div class="search-bar">
        <button type="submit" class="icon-button search-bar__lead" aria-label="搜尋" title="搜尋"><AppIcon name="search" /></button>
        <input v-model="queryInput" type="search" class="form-input search-bar__input search-bar__input--custom-clear" placeholder="搜尋足跡…" aria-label="搜尋足跡" maxlength="200" />
        <button v-if="showReset" type="button" class="icon-button search-bar__control search-bar__clear"
          title="清除搜尋與篩選" aria-label="清除搜尋與篩選" @click="clearSearchAndFilters"><AppIcon name="close" /></button>
        <button ref="filterButton" type="button" class="icon-button search-bar__control" :class="{ 'is-active': appliedFiltersActive || filtersOpen }" aria-label="篩選足跡" aria-controls="daily-filters" :aria-expanded="filtersOpen" @click="filtersOpen = !filtersOpen"><AppIcon name="filter" /></button>
      </div>
      <div v-show="filtersOpen" id="daily-filters" class="daily-filters">
        <label>城市<input v-model="city" class="form-input" maxlength="200" /></label>
        <label>類別<input v-model="category" class="form-input" list="daily-categories" maxlength="200" /><datalist id="daily-categories"><option v-for="value in categories" :key="value" :value="value" /></datalist></label>
        <label>開始日期<input v-model="dateFrom" type="date" class="form-input" :max="dateTo || undefined" /></label>
        <label>結束日期<input v-model="dateTo" type="date" class="form-input" :min="dateFrom || undefined" :aria-invalid="Boolean(filterError)" :aria-describedby="filterError ? 'daily-date-error' : undefined" /></label>
      </div>
      <p v-if="filterError" id="daily-date-error" class="daily-error" role="alert">{{ filterError }}</p>
    </form>
    <p v-if="error" class="daily-error" role="alert">{{ error }} <button type="button" class="btn-link" @click="loadPage(failedAppend)">重試</button></p>
    <div v-if="(loading && !loadingMore) || loadingFocus" class="daily-loading" role="status">
      <TrailLoader />
      <span class="sr-only">載入足跡中…</span>
    </div>
    <div v-else-if="!loading && !results.length && !error" class="daily-empty">
      <AppIcon name="pin" />
      <p>{{ isFiltered ? '找不到相符的足跡' : '還沒有日常足跡' }}</p>
      <button v-if="!isFiltered" class="btn-link" type="button" @click="openEditor(null)">記下第一次到訪</button>
    </div>
    <div ref="listRef" :aria-busy="loading || loadingFocus">
      <section v-for="[date, entries] in groups" :key="date" class="daily-group">
        <h3>{{ date }}</h3>
        <article v-for="event in entries" :key="event.id" :data-focused="focusId === event.id" class="daily-entry" tabindex="-1">
          <div class="daily-entry-heading">
            <div class="daily-identity">
              <button type="button" class="daily-name" @click="emit('view', event)">{{ event.place_name }}</button>
              <div v-if="event.time || event.city || event.category !== '未分類'" class="daily-meta">
                <time v-if="event.time" class="daily-time" :datetime="event.time">{{ event.time }}</time>
                <span v-if="event.city" class="daily-city"><AppIcon name="pin" /><span>{{ event.city }}</span></span>
                <span v-if="event.category !== '未分類'" class="daily-category">{{ event.category }}</span>
              </div>
            </div>
            <div class="daily-actions">
              <button type="button" class="icon-button daily-menu-trigger" title="足跡選項"
                :aria-label="`足跡選項：${event.place_name}`" :aria-expanded="openMenuId === event.id"
                :aria-controls="openMenuId === event.id ? `daily-menu-${event.id}` : undefined"
                @click="toggleMenu($event, event.id)"><AppIcon name="more" /></button>
              <div v-if="openMenuId === event.id" :id="`daily-menu-${event.id}`" class="daily-menu" :class="{ 'opens-up': menuAbove }">
                <button type="button" @click="closeMenu(true); openEditor(event)"><AppIcon name="edit" />編輯</button>
                <button type="button" @click="closeMenu(true); attaching = event"><AppIcon name="book-in" />收進手記</button>
                <button type="button" class="daily-delete" @click="closeMenu(true); deleting = event"><AppIcon name="trash" />刪除</button>
              </div>
            </div>
          </div>
          <p v-if="event.notes" class="daily-notes">{{ event.notes }}</p>
        </article>
      </section>
    </div>
    <button v-if="offset !== null" type="button" class="btn btn-secondary load-more" :disabled="loading" aria-label="載入更多" @click="loadPage(true)">
      <TrailLoader v-if="loadingMore" />
      <span v-else>載入更多</span>
    </button>
    <span v-if="loadingMore" class="sr-only" role="status">載入更多足跡中…</span>
    <EventDialog :visible="editorOpen" :event="editing" :categories="categories" :loading="busy" :error-message="editorError" :has-conflict="editorConflict" @submit="save" @refresh="refreshEdit" @cancel="editorOpen = false" @notice="(message, type) => emit('notice', message, type)" @photo-deleted="emit('photo-deleted', $event)" />
    <ConfirmDialog :visible="!!deleting" :target-key="deleting?.id" title="刪除日常足跡" :message="`刪除「${deleting?.place_name || ''}」？`" :loading="busy" confirmation-mode="keyword" confirm-text="刪除足跡" @confirm="remove" @cancel="deleting = null" />
    <AttachFootprintDialog v-if="attaching" :event="attaching" @close="closeAttach" @attached="attached" />
  </section>
</template>

<style scoped src="../assets/styles/components/StandaloneFootprints.css"></style>
