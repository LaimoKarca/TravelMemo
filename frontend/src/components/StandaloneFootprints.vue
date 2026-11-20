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

const props = defineProps<{ focusId?: string | null }>()
const emit = defineEmits<{
  view: [Event]
  jump: [EventDestination]
  notice: [string, 'success' | 'error']
  unfocus: []
}>()
const queryInput = ref('')
const query = ref('')
const filtersOpen = ref(false)
const city = ref('')
const category = ref('')
const dateFrom = ref('')
const dateTo = ref('')
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
const filtersActive = computed(() => Boolean(city.value || category.value || dateFrom.value || dateTo.value))

async function loadPage(append = false) {
  if (append && (loading.value || offset.value === null)) return
  const generation = ++pageGeneration
  error.value = ''
  if (!append) { offset.value = null; events.value = [] }
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    error.value = '結束日期須等於或晚於開始日期。'
    loading.value = false
    return
  }
  loading.value = true
  try {
    const page = await listStandaloneEvents({ q: query.value, city: city.value.trim(), category: category.value.trim(), date_from: dateFrom.value, date_to: dateTo.value, limit: 20, offset: append ? offset.value! : 0 })
    if (generation !== pageGeneration) return
    const known = new Set(events.value.map(event => event.id))
    events.value = [...events.value, ...page.items.filter(event => !known.has(event.id))]
    offset.value = page.next_offset
  } catch (err) {
    if (generation === pageGeneration) error.value = message(err, '無法載入日常足跡。')
  } finally {
    if (generation === pageGeneration) loading.value = false
  }
}

function message(err: unknown, fallback: string) { return err instanceof ApiError ? err.detail : fallback }
function clearFocus() { focused.value = null; emit('unfocus') }
function applyFilters() { clearFocus(); query.value = queryInput.value.trim(); void loadPage() }
function resetFilters() {
  city.value = ''; category.value = ''; dateFrom.value = ''; dateTo.value = ''; queryInput.value = ''
  applyFilters()
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
onMounted(() => void loadPage())
onBeforeUnmount(() => { active = false; pageGeneration++; focusGeneration++ })

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
    <form role="search" aria-label="搜尋日常足跡" @submit.prevent="applyFilters">
      <div class="daily-search">
        <input v-model="queryInput" type="search" class="form-input" placeholder="搜尋足跡…" aria-label="搜尋足跡" maxlength="200" />
        <button type="button" class="icon-button" :class="{ selected: filtersActive }" aria-label="篩選足跡" aria-controls="daily-filters" :aria-expanded="filtersOpen" @click="filtersOpen = !filtersOpen"><AppIcon name="filter" /></button>
        <button type="submit" class="btn btn-primary" aria-label="搜尋" title="搜尋"><AppIcon name="search" /></button>
      </div>
      <div v-show="filtersOpen" id="daily-filters" class="daily-filters">
        <label>城市<input v-model="city" class="form-input" maxlength="200" /></label>
        <label>類別<input v-model="category" class="form-input" list="daily-categories" maxlength="200" /><datalist id="daily-categories"><option v-for="value in categories" :key="value" :value="value" /></datalist></label>
        <label>開始日期<input v-model="dateFrom" type="date" class="form-input" :max="dateTo || undefined" /></label>
        <label>結束日期<input v-model="dateTo" type="date" class="form-input" :min="dateFrom || undefined" /></label>
        <button type="button" class="btn-link" @click="resetFilters">清除</button>
      </div>
    </form>
    <p v-if="error" class="daily-error" role="alert">{{ error }} <button type="button" class="btn-link" @click="loadPage()">重試</button></p>
    <p v-if="loading || loadingFocus" class="daily-status" role="status">載入足跡中…</p>
    <div v-else-if="!results.length && !error" class="daily-empty">
      <AppIcon name="pin" />
      <p>{{ query || filtersActive ? '找不到相符的足跡' : '還沒有日常足跡' }}</p>
      <button v-if="!query && !filtersActive" class="btn-link" type="button" @click="openEditor(null)">記下第一次到訪</button>
    </div>
    <div ref="listRef">
      <section v-for="[date, entries] in groups" :key="date" class="daily-group">
        <h3>{{ date }}</h3>
        <article v-for="event in entries" :key="event.id" :data-focused="focusId === event.id" class="daily-entry" tabindex="-1">
          <div class="daily-entry-main">
            <button type="button" class="daily-name" @click="emit('view', event)">{{ event.place_name }}</button>
            <div v-if="event.time || event.city || event.category !== '未分類'" class="daily-meta">
              <time v-if="event.time">{{ event.time }}</time><span v-if="event.city">{{ event.city }}</span><span v-if="event.category !== '未分類'">{{ event.category }}</span>
            </div>
            <p v-if="event.notes" class="daily-notes">{{ event.notes }}</p>
          </div>
          <details class="daily-actions">
            <summary aria-label="足跡選項" title="足跡選項"><AppIcon name="more" /></summary>
            <div class="daily-menu" @click="($event.currentTarget as HTMLElement).closest('details')?.removeAttribute('open')">
              <button type="button" @click="openEditor(event)"><AppIcon name="edit" /> 編輯</button>
              <button type="button" @click="attaching = event"><AppIcon name="jump" /> 收進手記</button>
              <button type="button" class="daily-error" @click="deleting = event"><AppIcon name="trash" /> 刪除</button>
            </div>
          </details>
        </article>
      </section>
    </div>
    <button v-if="offset !== null" type="button" class="btn btn-secondary load-more" :disabled="loading" @click="loadPage(true)">載入更多</button>
    <EventDialog :visible="editorOpen" :event="editing" :categories="categories" :loading="busy" :error-message="editorError" :has-conflict="editorConflict" @submit="save" @refresh="refreshEdit" @cancel="editorOpen = false" @notice="(message, type) => emit('notice', message, type)" />
    <ConfirmDialog :visible="!!deleting" :target-key="deleting?.id" title="刪除日常足跡" :message="`刪除「${deleting?.place_name || ''}」？`" :loading="busy" confirmation-mode="keyword" confirm-text="刪除足跡" @confirm="remove" @cancel="deleting = null" />
    <AttachFootprintDialog v-if="attaching" :event="attaching" @close="closeAttach" @attached="attached" />
  </section>
</template>

<style scoped>
.daily { width: 100%; min-width: 0; }
.daily-header { display: flex; align-items: center; justify-content: space-between; gap: .75rem; margin-bottom: 1rem; }
.daily-header h2 { font-size: 1.35rem; color: var(--color-ink); }
.quick-record { width: 44px; min-height: 44px; padding: 0; justify-content: center; }
.daily-search { display: flex; align-items: center; padding: 2px; gap: .125rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-paper); }
.daily-search input { border: 0; flex: 1; }
.daily-search button { flex: 0 0 42px; min-height: 42px; padding: 0; justify-content: center; border: 0; }
.daily-search .selected { color: var(--color-maple); background: var(--color-maple-subtle); }
.daily-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem 1rem; padding: .75rem 0; }
.daily-filters label { display: grid; gap: .25rem; font-size: .8rem; min-width: 0; }
.daily-filters .btn-link { justify-self: start; }
.daily-group { margin-top: 1.25rem; }
.daily-group h3 { font-size: .87rem; color: var(--color-subtle); padding: .25rem 0; }
.daily-entry { display: flex; align-items: flex-start; gap: .8rem; padding: .7rem 0; border-top: 1px solid var(--color-border); scroll-margin: .75rem; }
.daily-entry[data-focused=true] { background: var(--color-maple-subtle); border-radius: var(--radius-sm); padding-inline: .65rem; }
.daily-entry-main { min-width: 0; flex: 1; }
.daily-name { border: 0; padding: .2rem 0; background: transparent; color: var(--color-ink); font: inherit; font-weight: 650; text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.daily-name:hover { color: var(--color-maple); }
.daily-meta { display: flex; gap: .6rem; flex-wrap: wrap; font-size: .8rem; color: var(--color-subtle); margin-top: .2rem; }
.daily-notes { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--color-ink-secondary); font-size: .9rem; margin-top: .35rem; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.daily-actions { position: relative; flex: 0 0 auto; }
.daily-actions summary { display: grid; place-items: center; width: 44px; height: 44px; list-style: none; cursor: pointer; border-radius: var(--radius-sm); color: var(--color-subtle); }
.daily-actions summary::-webkit-details-marker { display: none; }
.daily-actions[open] summary { background: var(--color-maple-subtle); color: var(--color-maple); }
.daily-menu { position: absolute; z-index: 3; right: 0; top: 100%; width: max-content; min-width: 9rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-paper); box-shadow: var(--shadow-sm); padding: .25rem; }
.daily-menu button { display: flex; align-items: center; gap: .5rem; width: 100%; min-height: 42px; padding: .4rem .65rem; border: 0; border-radius: var(--radius-xs); background: transparent; color: inherit; font: inherit; cursor: pointer; }
.daily-menu button:hover { background: var(--color-maple-subtle); }
.daily-status, .daily-error { margin: .75rem 0; font-size: .85rem; }
.daily-error, .daily-menu button.daily-error { color: var(--color-error-text); }
.daily-menu button.daily-error { margin: 0; }
.daily-empty { display: grid; justify-items: center; gap: .55rem; padding: 2.75rem .5rem; color: var(--color-subtle); }
.daily-empty > svg { width: 2rem; height: 2rem; color: var(--color-maple); }
.load-more { display: flex; margin: 1rem auto 0; }
</style>
