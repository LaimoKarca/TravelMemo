<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError } from '../api/auth'
import { attachEventToTrip, getTrip, listTrips } from '../api/travel'
import type { Event, Trip, TripDetailResponse } from '../types/travel'
import { normalizeTimezoneInput } from '../utils/timezones'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ event: Event }>()
const emit = defineEmits<{ close: [stale: boolean]; attached: [Event] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const trips = ref<Trip[]>([])
const tripId = ref('')
const before = ref('')
const detail = ref<TripDetailResponse | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const conflict = ref(false)
let generation = 0
let active = true

const sameDay = computed(() => detail.value?.events.filter(event => event.date === props.event.date) || [])
const incompatibility = computed(() => {
  const trip = detail.value?.trip
  if (!trip) return ''
  if (props.event.date < trip.start_date || props.event.date > trip.end_date) return '這本手記不涵蓋足跡日期。請選另一本，或先調整日期。'
  if (normalizeTimezoneInput(props.event.timezone || 'Asia/Taipei') !== normalizeTimezoneInput(trip.timezone)) return '手記與足跡的時區不同，請先調整其中一方。'
  return ''
})

onMounted(async () => {
  dialog.value?.showModal()
  await nextTick()
  try {
    trips.value = (await listTrips()).items
  } catch {
    error.value = '無法載入手記，請稍後再試。'
  } finally {
    loading.value = false
  }
})
onBeforeUnmount(() => { active = false; generation++; dialog.value?.close() })

async function loadTrip() {
  const request = ++generation
  const selected = tripId.value
  detail.value = null
  before.value = ''
  error.value = ''
  if (!selected) { loading.value = false; return }
  loading.value = true
  try {
    const result = await getTrip(selected)
    if (request === generation) detail.value = result
  } catch (err) {
    if (request === generation) error.value = err instanceof ApiError ? err.detail : '無法載入手記。'
  } finally {
    if (request === generation) loading.value = false
  }
}
watch(tripId, loadTrip)

async function submit() {
  if (!detail.value || loading.value || saving.value || incompatibility.value || conflict.value) return
  saving.value = true
  error.value = ''
  try {
    const event = await attachEventToTrip(props.event.id, {
      trip_id: detail.value.trip.id, trip_version: detail.value.trip.version,
      version: props.event.version, before_event_id: before.value || null,
    })
    if (active) emit('attached', event)
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      conflict.value = true
      error.value = '足跡或手記已變更。返回列表後可重新選擇。'
    } else {
      error.value = err instanceof ApiError ? err.detail : '無法收進手記，請稍後再試。'
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
        <label v-if="trips.length">旅行手記
          <select v-model="tripId" class="form-input" :disabled="saving || conflict">
            <option value="">選擇手記</option>
            <option v-for="trip in trips" :key="trip.id" :value="trip.id">{{ trip.name }}</option>
          </select>
        </label>
        <p v-else-if="!loading && !error">先建立一本手記，就能把足跡收進去。</p>
        <p v-if="loading" role="status">載入中…</p>
        <p v-if="error || incompatibility" class="attach-error" role="alert">{{ error || incompatibility }}</p>
        <label v-if="detail && !incompatibility">加入位置
          <select v-model="before" class="form-input" :disabled="saving || conflict">
            <option value="">{{ sameDay.length ? '當日最後一筆' : '當日第一筆' }}</option>
            <option v-for="item in sameDay" :key="item.id" :value="item.id">在「{{ item.place_name }}」之前</option>
          </select>
        </label>
      </div>
      <footer class="dialog-icon-actions">
        <button autofocus type="button" class="btn btn-secondary" :disabled="saving" aria-label="返回" title="返回" @click="close"><AppIcon name="back" /></button>
        <button type="submit" class="btn btn-primary" :disabled="!detail || loading || saving || !!incompatibility || conflict" :aria-label="saving ? '移入中' : '確認移入手記'" title="確認移入手記"><span v-if="saving" class="pending" aria-hidden="true"></span><AppIcon v-else name="save" /></button>
      </footer>
    </form>
  </dialog>
</template>

<style scoped>
.attach-dialog { width: min(30rem, calc(100vw - 2rem)); max-height: calc(100dvh - 2rem); margin: auto; padding: 0; color: var(--color-ink); background: var(--color-paper); border: 1px solid var(--color-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-md); overflow: hidden; }
.attach-dialog::backdrop { background: rgb(69 58 50 / .45); }
.attach-dialog form { display: flex; flex-direction: column; max-height: calc(100dvh - 2rem - 2px); }
.attach-body { display: grid; gap: .8rem; padding: 1.25rem; overflow: auto; }
.attach-body h3 { font-size: 1.125rem; }
.attach-event { display: flex; flex-wrap: wrap; gap: .25rem .75rem; align-items: baseline; }
.attach-event span, .attach-body label { color: var(--color-subtle); font-size: .85rem; }
.attach-body label { display: grid; gap: .3rem; min-width: 0; }
.attach-error { color: var(--color-error-text); font-size: .85rem; }
.pending { width: 1rem; height: 1rem; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: attach-spin .8s linear infinite; }
@keyframes attach-spin { to { transform: rotate(360deg); } }
</style>
