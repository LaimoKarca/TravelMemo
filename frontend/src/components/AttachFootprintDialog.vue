<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError } from '../api/auth'
import { attachEventToTrip, getTrip, listTrips } from '../api/travel'
import type { Event, Trip, TripDetailResponse } from '../types/travel'
import { normalizeTimezoneInput } from '../utils/timezones'
import AppIcon from './AppIcon.vue'
import TrailLoader from './TrailLoader.vue'

const props = defineProps<{ event: Event }>()
const emit = defineEmits<{ close: [stale: boolean]; attached: [Event] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const trips = ref<Trip[]>([])
const query = ref('')
const tripId = ref('')
const before = ref('')
const detail = ref<TripDetailResponse | null>(null)
const loadingTrips = ref(true)
const loadingDetail = ref(false)
const saving = ref(false)
const listError = ref(false)
const detailError = ref('')
const saveError = ref('')
const conflict = ref(false)
let generation = 0
let active = true

const eventZone = computed(() => normalizeTimezoneInput(props.event.timezone || 'Asia/Taipei'))
function matchesDate(trip: Trip) {
  return trip.start_date <= props.event.date && props.event.date <= trip.end_date
}
function matchesZone(trip: Trip) {
  return normalizeTimezoneInput(trip.timezone) === eventZone.value
}
function distance(trip: Trip) {
  if (matchesDate(trip)) return 0
  const date = props.event.date < trip.start_date ? trip.start_date : trip.end_date
  return Math.abs(Date.parse(date) - Date.parse(props.event.date))
}
function searchText(value: string) { return value.normalize('NFKC').toLocaleLowerCase() }
const sortedTrips = computed(() => trips.value.map(trip => ({
  trip, distance: distance(trip), zoneMatches: matchesZone(trip),
})).sort((a, b) => a.distance - b.distance || Number(b.zoneMatches) - Number(a.zoneMatches)
  || b.trip.start_date.localeCompare(a.trip.start_date) || a.trip.id.localeCompare(b.trip.id)))
const visibleTrips = computed(() => {
  const tokens = searchText(query.value).trim().split(/\s+/)
  return sortedTrips.value.filter(({ trip }) => {
    const text = searchText(`${trip.name} ${trip.start_date} ${trip.end_date}`)
    return tokens.every(token => text.includes(token))
  })
})
const selectedOutsideResults = computed(() => visibleTrips.value.some(({ trip }) => trip.id === tripId.value)
  ? null : trips.value.find(trip => trip.id === tripId.value))
const sameDay = computed(() => detail.value?.events.filter(event => event.date === props.event.date) || [])
const incompatibility = computed(() => {
  const trip = detail.value?.trip
  if (!trip) return ''
  if (!matchesDate(trip)) return '這本手記不涵蓋足跡日期。請選另一本，或先調整日期。'
  if (!matchesZone(trip)) return '手記與足跡的時區不同，請先調整其中一方。'
  return ''
})

onMounted(() => {
  dialog.value?.showModal()
  void loadTrips()
})
onBeforeUnmount(() => { active = false; generation++; dialog.value?.close() })

async function loadTrips() {
  loadingTrips.value = true
  listError.value = false
  try {
    const result = await listTrips()
    if (active) trips.value = result.items
  } catch {
    if (active) listError.value = true
  } finally {
    if (active) loadingTrips.value = false
  }
}

async function loadTrip(id: string) {
  const request = ++generation
  tripId.value = id
  detail.value = null
  before.value = ''
  detailError.value = ''
  saveError.value = ''
  loadingDetail.value = true
  try {
    const result = await getTrip(id)
    if (request === generation) detail.value = result
  } catch (err) {
    if (request === generation) detailError.value = err instanceof ApiError ? err.detail : '無法載入手記。'
  } finally {
    if (request === generation) loadingDetail.value = false
  }
}

async function submit() {
  if (!detail.value || loadingDetail.value || saving.value || incompatibility.value || conflict.value) return
  saving.value = true
  saveError.value = ''
  try {
    const event = await attachEventToTrip(props.event.id, {
      trip_id: detail.value.trip.id, trip_version: detail.value.trip.version,
      version: props.event.version, before_event_id: before.value || null,
    })
    if (active) emit('attached', event)
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      conflict.value = true
      saveError.value = '足跡或手記已變更。返回列表後可重新選擇。'
    } else {
      saveError.value = err instanceof ApiError ? err.detail : '無法收進手記，請稍後再試。'
    }
  } finally {
    saving.value = false
  }
}
function close() { if (!saving.value) emit('close', conflict.value) }
</script>

<template>
  <dialog ref="dialog" class="attach-dialog" aria-labelledby="attach-title" @cancel.prevent="close">
    <form @submit.prevent="submit">
      <div class="attach-body">
        <h3 id="attach-title">收進手記</h3>
        <p class="attach-event">{{ event.place_name }} <span>{{ event.date }}</span></p>
        <div v-if="loadingTrips" class="attach-loading" role="status">
          <TrailLoader /><span class="sr-only">載入手記清單中…</span>
        </div>
        <div v-else-if="listError" class="attach-error-row">
          <p class="attach-error" role="alert">無法載入手記清單。</p>
          <button type="button" class="btn-link" @click="loadTrips">重試</button>
        </div>
        <p v-else-if="!trips.length">先建立一本手記，就能把足跡收進去。</p>
        <div v-else class="attach-picker">
          <label class="sr-only" for="attach-search">搜尋手記</label>
          <input id="attach-search" v-model="query" type="search" class="form-input"
            placeholder="搜尋手記名稱或日期…" :disabled="saving || conflict" @keydown.enter.prevent />
          <ul v-if="visibleTrips.length" class="attach-choices" aria-label="旅行手記">
            <li v-for="{ trip, distance, zoneMatches } in visibleTrips" :key="trip.id">
              <button type="button" class="attach-choice" :aria-pressed="tripId === trip.id"
                :disabled="saving || conflict || distance !== 0 || !zoneMatches" @click="loadTrip(trip.id)">
                <span class="choice-name">{{ trip.name }}</span>
                <span class="choice-meta">
                  <span>{{ trip.start_date }} ~ {{ trip.end_date }}</span>
                  <span v-if="distance !== 0">日期不符</span>
                  <span v-else-if="!zoneMatches">時區不符</span>
                </span>
              </button>
            </li>
          </ul>
          <p v-else role="status" class="attach-empty">沒有符合的手記。</p>
          <p v-if="selectedOutsideResults" class="attach-empty">已選擇 {{ selectedOutsideResults.name }}</p>
        </div>
        <div v-if="loadingDetail" class="attach-loading" role="status">
          <TrailLoader /><span class="sr-only">載入所選手記中…</span>
        </div>
        <div v-if="detailError" class="attach-error-row">
          <p class="attach-error" role="alert">{{ detailError }}</p>
          <button type="button" class="btn-link" @click="loadTrip(tripId)">重試</button>
        </div>
        <p v-if="saveError || incompatibility" class="attach-error" role="alert">{{ saveError || incompatibility }}</p>
        <label v-if="detail && !incompatibility">加入位置
          <select v-model="before" class="form-input" :disabled="saving || conflict">
            <option value="">{{ sameDay.length ? '當日最後一筆' : '當日第一筆' }}</option>
            <option v-for="item in sameDay" :key="item.id" :value="item.id">在「{{ item.place_name }}」之前</option>
          </select>
        </label>
      </div>
      <footer class="dialog-icon-actions">
        <button autofocus type="button" class="btn btn-secondary" :disabled="saving" aria-label="返回" title="返回" @click="close"><AppIcon name="back" /></button>
        <button type="submit" class="btn btn-primary" :disabled="!detail || loadingDetail || saving || !!incompatibility || conflict" :aria-label="saving ? '移入中' : '確認移入手記'" title="確認移入手記"><span v-if="saving" class="pending ui-spinner ui-spinner--current" aria-hidden="true"></span><AppIcon v-else name="save" /></button>
      </footer>
    </form>
  </dialog>
</template>

<style scoped src="../assets/styles/components/AttachFootprintDialog.css"></style>
