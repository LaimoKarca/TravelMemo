<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Trip } from '../types/travel'
import type { FootprintDraft, FootprintItem } from '../types/footprint'
import * as api from '../api/footprint'
import { getTrip } from '../api/travel'
import { ApiError } from '../api/auth'
import AppIcon from './AppIcon.vue'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps<{ visible: boolean; trip: Trip; categories?: string[] }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()
const panel = ref<HTMLElement | null>(null)
const draft = ref<FootprintDraft | null>(null)
const tripInfo = ref<Trip>(props.trip)
const recordDate = ref('')
const description = ref('')
const items = ref<FootprintItem[]>([])
const expanded = ref<string | null>(null)
const loading = ref(false)
const saving = ref(false)
const committing = ref(false)
const error = ref('')
const dirty = ref(false)
const conflict = ref(false)
const success = ref(false)
const confirmAction = ref<'regenerate' | 'discard' | 'reload' | 'leave' | null>(null)
const busy = computed(() => draft.value?.status === 'queued' || draft.value?.status === 'running')
const selected = computed(() => items.value.filter(i => i.selected))
const categories = computed(() => [...new Set(['景點', '美食', '住宿', '交通', '購物', '文化', '咖啡', '休閒', '其他', ...(props.categories || []), ...items.value.map(i => i.category)])])
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const confirmMessage = computed(() => confirmAction.value === 'regenerate' ? '重新整理會取代目前的足跡草稿，尚未加入手記。' : confirmAction.value === 'discard' ? '放棄目前描述與足跡草稿？已儲存的手記不受影響。' : confirmAction.value === 'leave' ? '目前無法儲存。暫時關閉會保留此頁的輸入，但重整或離開手記可能遺失尚未儲存的內容。' : '重新載入會取代目前尚未儲存的修改。')
let alive = true
let generation = 0
let editNumber = 0
let polling: ReturnType<typeof setTimeout> | null = null
let debounce: ReturnType<typeof setTimeout> | null = null
let saveTask: Promise<void> | null = null
let previousFocus: HTMLElement | null = null
let commitRequest: string | null = null
let generateRequest: string | null = null

function invalid(item: FootprintItem) {
  if (!item.place_name?.trim()) return '請補上地點名稱'
  if (!item.date || item.date < tripInfo.value.start_date || item.date > tripInfo.value.end_date) return '請選擇旅程範圍內的日期'
  if (!item.category.trim()) return '請選擇分類'
  return ''
}
const canCommit = computed(() => !busy.value && !loading.value && !committing.value && !conflict.value && selected.value.length > 0 && !selected.value.some(invalid))
function adopt(value: FootprintDraft) {
  draft.value = value
  recordDate.value = value.record_date
  description.value = value.text
  items.value = clone(value.items)
  dirty.value = false
  expanded.value = value.items.find(i => i.selected && invalid(i))?.id || null
  if (value.status === 'committed') success.value = true
}
function report(err: unknown) {
  error.value = err instanceof ApiError ? err.detail : '連線暫時中斷，請稍後再試。'
  if (err instanceof ApiError && err.status === 409) conflict.value = true
}
function stopPoll() { if (polling) clearTimeout(polling); polling = null }
async function poll(id: string, version: number) {
  if (!alive || !props.visible || generation !== version) return
  try {
    const value = await api.getFootprintDraft(props.trip.id, id)
    if (!alive || !props.visible || generation !== version) return
    adopt(value)
    if (value.status === 'failed') error.value = value.error || '整理未完成，描述與原草稿已保留。'
    if (value.status !== 'queued' && value.status !== 'running') return
  } catch (err) {
    if (err instanceof ApiError && [401, 404].includes(err.status)) { report(err); return }
  }
  if (alive && props.visible && generation === version) polling = setTimeout(() => void poll(id, version), navigator.onLine ? 1500 : 5000)
}
function change() {
  if (!conflict.value) error.value = ''
  dirty.value = true
  editNumber++
  commitRequest = null
  generateRequest = null
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(() => void flushSave().catch(report), 600)
}
async function saveLoop() {
  while (dirty.value && !busy.value) {
    const edit = editNumber
    const snapshot = { record_date: recordDate.value, text: description.value, items: clone(items.value).map(i => ({ ...i, place_name: i.place_name?.trim() || null, date: i.date || null, time: i.time || null })) }
    let value: FootprintDraft
    if (!draft.value) {
      value = await api.createFootprintDraft(props.trip.id, snapshot.record_date, snapshot.text)
      draft.value = value
      // A newly created resource starts empty; persist edited items if any.
      if (snapshot.items.length) value = await api.updateFootprintDraft(props.trip.id, value.id, { version: value.version, ...snapshot })
    } else {
      value = await api.updateFootprintDraft(props.trip.id, draft.value.id, { version: draft.value.version, ...snapshot })
    }
    draft.value = value
    if (editNumber === edit) dirty.value = false
  }
}
async function flushSave() {
  if (debounce) clearTimeout(debounce)
  debounce = null
  if (saveTask) await saveTask
  if (!dirty.value || busy.value) return
  if (!recordDate.value || recordDate.value < tripInfo.value.start_date || recordDate.value > tripInfo.value.end_date) throw new ApiError(422, '請先選擇旅程範圍內的記錄日期。')
  saving.value = true
  saveTask = saveLoop()
  try { await saveTask } finally { saveTask = null; saving.value = false }
}
async function load() {
  const version = ++generation
  loading.value = true
  error.value = ''
  conflict.value = false
  try {
    const [context, existing] = await Promise.all([getTrip(props.trip.id), api.latestFootprintDrafts(props.trip.id)])
    if (!alive || generation !== version) return
    tripInfo.value = context.trip
    if (existing.items.length) adopt(existing.items[0])
    else {
      draft.value = null; items.value = []; description.value = ''; dirty.value = false; success.value = false
      const offset = /^UTC([+-])(\d{2}):(\d{2})$/.exec(context.trip.timezone)
      const today = offset ? new Date(Date.now() + (offset[1] === '+' ? 1 : -1) * (Number(offset[2]) * 60 + Number(offset[3])) * 60000).toISOString().slice(0, 10) : new Intl.DateTimeFormat('en-CA', { timeZone: context.trip.timezone }).format(new Date())
      recordDate.value = today >= context.trip.start_date && today <= context.trip.end_date ? today : ''
    }
    if (busy.value && draft.value) void poll(draft.value.id, version)
  } catch (err) { if (generation === version) report(err) }
  finally { if (generation === version) loading.value = false }
}
async function generate() {
  if (!recordDate.value || !description.value.trim() || busy.value || committing.value) return
  if (items.value.length) { confirmAction.value = 'regenerate'; return }
  await runGenerate()
}
async function runGenerate() {
  error.value = ''; loading.value = true
  try {
    if (!draft.value) dirty.value = true
    await flushSave()
    if (!draft.value) return
    generateRequest ||= crypto.randomUUID()
    const value = await api.generateFootprints(props.trip.id, draft.value.id, draft.value.version, generateRequest)
    adopt(value)
    void poll(value.id, generation)
  } catch (err) { report(err) }
  finally { loading.value = false }
}
async function commit() {
  if (!canCommit.value || !draft.value) return
  error.value = ''; committing.value = true
  try {
    await flushSave()
    commitRequest ||= crypto.randomUUID()
    const result = await api.commitFootprints(props.trip.id, draft.value.id, draft.value.version, tripInfo.value.version, commitRequest)
    adopt(result.draft)
    tripInfo.value = { ...tripInfo.value, version: result.trip_version }
    success.value = true
    emit('saved')
  } catch (err) { report(err) }
  finally { committing.value = false }
}
async function refreshContext() {
  try {
    const context = await getTrip(props.trip.id)
    tripInfo.value = context.trip
    if (draft.value) {
      const latest = await api.getFootprintDraft(props.trip.id, draft.value.id)
      if (latest.version !== draft.value.version) { confirmAction.value = 'reload'; return }
    }
    conflict.value = false
    error.value = '手記資料已更新，請核對日期與草稿後再加入。'
  } catch (err) { report(err) }
}
async function confirm() {
  const action = confirmAction.value
  confirmAction.value = null
  if (action === 'regenerate') await runGenerate()
  if (action === 'reload') await load()
  if (action === 'leave') emit('close')
  if (action === 'discard') {
    try {
      if (debounce) clearTimeout(debounce)
      if (saveTask) await saveTask
      stopPoll()
      if (draft.value) await api.discardFootprintDraft(props.trip.id, draft.value.id, draft.value.version)
      dirty.value = false; draft.value = null; items.value = []; description.value = ''; success.value = false; error.value = ''; conflict.value = false
    } catch (err) { report(err) }
  }
}
function move(index: number, delta: number) {
  const target = index + delta
  if (!items.value[target] || items.value[target].date !== items.value[index].date) return
  ;[items.value[index], items.value[target]] = [items.value[target], items.value[index]]
  change()
}
async function close() {
  try { if (!success.value) await flushSave(); emit('close') } catch (err) { report(err); confirmAction.value = 'leave' }
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !confirmAction.value) { event.stopPropagation(); event.preventDefault(); void close() }
  if (event.key === 'Tab' && panel.value) {
    const elements = [...panel.value.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]')].filter(el => el.getClientRects().length)
    const first = elements[0], last = elements[elements.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
watch(() => props.visible, async visible => {
  stopPoll()
  if (visible) {
    previousFocus = document.activeElement as HTMLElement | null
    if (!dirty.value) await load()
    await nextTick(); panel.value?.querySelector<HTMLButtonElement>('button')?.focus()
  } else { generation++; await nextTick(); previousFocus?.focus() }
}, { immediate: true })
onBeforeUnmount(() => { alive = false; generation++; stopPoll(); if (debounce) clearTimeout(debounce) })
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="footprint-backdrop" @click.self="close" @keydown="keydown">
      <aside ref="panel" class="footprint-panel" role="dialog" aria-modal="true" aria-labelledby="footprint-title" tabindex="-1">
        <header class="assist-header"><div><h2 id="footprint-title">AI 幫我記</h2><p>{{ tripInfo.name }}</p></div><button type="button" class="icon-button" aria-label="關閉足跡助手" @click="close"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button></header>
        <main class="assist-body">
          <div v-if="error" class="assist-error" role="alert">{{ error }} <button v-if="conflict" type="button" class="btn-link" @click="refreshContext">更新手記資料</button></div>
          <div v-if="success" class="assist-success" role="status"><AppIcon name="wand" /><h3>足跡已加入手記</h3><p>回到時間軸，就能繼續編輯與調整順序。</p><button type="button" class="btn btn-secondary" @click="draft = null; success = false; items = []; description = ''; error = ''">繼續記錄</button></div>
          <template v-else>
            <div class="record-day"><label for="assist-date">記錄日期</label><input id="assist-date" v-model="recordDate" type="date" class="form-input" :min="tripInfo.start_date" :max="tripInfo.end_date" :disabled="busy || loading || committing" @change="change" /></div>
            <label for="assist-description" class="description-label">說說這一天去了哪裡</label>
            <textarea id="assist-description" v-model="description" class="form-input assist-description" rows="5" maxlength="10000" placeholder="早上去清水寺散步，下午在河邊喝抹茶，靠窗的座位能看到河景…" :disabled="busy || loading || committing" @input="change" />
            <div class="generate-row"><small>{{ saving ? '儲存草稿中…' : dirty ? '尚未儲存' : draft ? '草稿已保留' : '先選日期，再描述行程' }}</small><button type="button" class="btn btn-secondary" :disabled="busy || loading || committing || conflict || !recordDate || !description.trim()" @click="generate"><AppIcon name="wand" />{{ items.length ? '重新整理' : '整理成足跡' }}</button></div>
            <div v-if="busy || loading" class="assist-progress" role="status"><span class="assist-spinner"></span><span>{{ busy ? '正在整理，關閉後也能回來接續' : '正在讀取…' }}</span></div>
            <section v-if="items.length" class="draft-list" aria-label="待確認足跡"><h3>待確認足跡 <small>{{ items.length }}</small></h3><p class="draft-help">核對地點、日期與心得，再加入手記。</p>
              <article v-for="(item, index) in items" :key="item.id" class="draft-row">
                <div class="draft-summary"><input v-model="item.selected" type="checkbox" :aria-label="`加入 ${item.place_name || '未命名足跡'}`" :disabled="busy || committing" @change="change" /><button type="button" class="draft-name" :aria-expanded="expanded === item.id" @click="expanded = expanded === item.id ? null : item.id"><strong>{{ item.place_name || '請補地點' }}</strong><small>{{ item.date || '日期未提供' }}</small></button><button type="button" class="mini-action" aria-label="足跡往上移" :disabled="busy || committing || index === 0 || items[index - 1]?.date !== item.date" @click="move(index, -1)">↑</button><button type="button" class="mini-action" aria-label="足跡往下移" :disabled="busy || committing || index === items.length - 1 || items[index + 1]?.date !== item.date" @click="move(index, 1)">↓</button></div>
                <p v-if="item.selected && invalid(item)" class="draft-invalid">{{ invalid(item) }}</p>
                <p v-if="expanded !== item.id && item.notes" class="draft-note">{{ item.notes }}</p>
                <div v-if="expanded === item.id" class="draft-fields" @input="change" @change="change">
                  <label>地點<input v-model="item.place_name" class="form-input" maxlength="200" :disabled="busy || committing" /></label>
                  <div class="draft-pair"><label>日期<input v-model="item.date" type="date" class="form-input" :min="tripInfo.start_date" :max="tripInfo.end_date" :disabled="busy || committing" /></label><label>時間<input v-model="item.time" type="time" class="form-input" :disabled="busy || committing" /></label></div>
                  <div class="draft-pair"><label>城市<input v-model="item.city" class="form-input" maxlength="200" :disabled="busy || committing" /></label><label>分類<input v-model="item.category" class="form-input" list="assist-categories" maxlength="200" :disabled="busy || committing" /></label></div>
                  <label>地址<input v-model="item.address" class="form-input" maxlength="1000" :disabled="busy || committing" /></label><label>心得<textarea v-model="item.notes" class="form-input" rows="3" maxlength="20000" :disabled="busy || committing" /></label>
                  <button type="button" class="remove-draft" :disabled="busy || committing" @click="items.splice(index, 1); change()">移除這筆草稿</button>
                </div>
              </article>
            </section>
          </template>
          <datalist id="assist-categories"><option v-for="category in categories" :key="category" :value="category" /></datalist>
        </main>
        <footer class="assist-footer"><button v-if="!success && (draft || description)" type="button" class="btn-link" :disabled="busy || loading || committing || saving" @click="confirmAction = 'discard'">放棄草稿</button><span v-else></span><button v-if="!success" type="button" class="btn btn-primary" :disabled="!canCommit" @click="commit">{{ committing ? '加入中…' : `加入 ${selected.length} 筆足跡` }}</button><button v-else type="button" class="btn btn-primary" @click="close">回到手記</button></footer>
      </aside>
    </div>
  </Teleport>
  <ConfirmDialog :style="{ zIndex: 1200 }" :visible="!!confirmAction" title="確認草稿操作" :message="confirmMessage" @confirm="confirm" @cancel="confirmAction = null" />
</template>

<style scoped>
.footprint-backdrop { position: fixed; inset: 0; z-index: 1100; background: #453a3240; display: flex; justify-content: flex-end; }
.footprint-panel { width: min(36rem, 100%); height: 100dvh; background: var(--color-paper); display: flex; flex-direction: column; box-shadow: -12px 0 40px #453a3212; outline: none; }
.assist-header { display: flex; justify-content: space-between; align-items: center; padding: 1.5rem 1.6rem 1rem; border-bottom: 1px solid var(--color-border-light); }
.assist-header h2 { font-size: 1.25rem; margin: 0; color: var(--color-ink); }
.assist-header p { color: var(--color-subtle); font-size: .85rem; margin: .3rem 0 0; }
.assist-body { flex: 1; min-height: 0; overflow-y: auto; padding: 1.4rem 1.6rem; }
.record-day { display: flex; justify-content: space-between; align-items: center; gap: .75rem; margin-bottom: 1.2rem; font-size: .85rem; }
.record-day input { width: 11rem; }
.description-label { display: block; font-size: .9rem; margin-bottom: .5rem; }
.assist-description { width: 100%; min-height: 8rem; resize: vertical; }
.generate-row { display: flex; justify-content: space-between; align-items: center; gap: .5rem; margin-top: .6rem; }
.generate-row small { color: var(--color-subtle); font-size: .75rem; }
.generate-row button { display: inline-flex; align-items: center; gap: .4rem; }
.assist-progress { display: flex; align-items: center; gap: .6rem; color: var(--color-subtle); padding: 1.3rem 0; font-size: .85rem; }
.assist-spinner { width: 20px; height: 20px; border: 2px solid var(--color-border); border-top-color: var(--color-maple); border-radius: 50%; animation: turning .8s linear infinite; flex-shrink: 0; }
@keyframes turning { to { transform: rotate(360deg); } }
.draft-list { margin-top: 1.7rem; }
.draft-list h3 { font-size: 1rem; margin-bottom: .3rem; }
.draft-list h3 small { color: var(--color-subtle); font-weight: 400; margin-left: .3rem; }
.draft-help { color: var(--color-subtle); font-size: .8rem; margin: 0 0 .7rem; }
.draft-row { padding: .85rem 0; border-bottom: 1px solid var(--color-border-light); }
.draft-summary { display: flex; align-items: center; gap: .6rem; }
.draft-summary input { accent-color: var(--color-maple); width: 18px; height: 18px; }
.draft-name { flex: 1; min-width: 0; text-align: left; border: 0; background: none; color: var(--color-ink); padding: .2rem 0; cursor: pointer; }
.draft-name strong { display: block; font-size: .95rem; overflow-wrap: anywhere; }
.draft-name small { display: block; color: var(--color-subtle); margin-top: .25rem; }
.mini-action { min-width: 36px; height: 44px; border: 0; background: none; color: var(--color-maple); cursor: pointer; font-size: 1rem; }
.mini-action:disabled { opacity: .25; cursor: default; }
.draft-note { color: var(--color-subtle); font-size: .85rem; margin: .5rem 0 0 1.7rem; line-height: 1.7; white-space: pre-wrap; }
.draft-invalid, .assist-error { color: var(--color-error-text); font-size: .85rem; line-height: 1.7; }
.assist-error { padding: .7rem 0; margin-bottom: .5rem; }
.draft-invalid { margin: .4rem 0 0 1.7rem; }
.draft-fields { display: flex; flex-direction: column; gap: .7rem; padding: .85rem 0 0 1.7rem; }
.draft-fields label { display: flex; flex-direction: column; gap: .3rem; font-size: .8rem; color: var(--color-ink-secondary); min-width: 0; }
.draft-fields .form-input { width: 100%; }
.draft-pair { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; }
.remove-draft { align-self: flex-start; padding: .35rem 0; background: none; border: 0; color: var(--color-subtle); cursor: pointer; font-size: .8rem; }
.assist-footer { display: flex; align-items: center; justify-content: space-between; gap: .75rem; padding: 1rem 1.6rem max(1rem, env(safe-area-inset-bottom)); border-top: 1px solid var(--color-border-light); }
.assist-success { padding: 3rem 0; text-align: center; color: var(--color-ink); }
.assist-success > svg { color: var(--color-maple); width: 36px; height: 36px; margin-bottom: .7rem; }
.assist-success p { font-size: .85rem; color: var(--color-subtle); margin: .6rem 0 1rem; }
@media(max-width: 600px) { .assist-body { padding: 1rem; } .assist-header { padding: 1.1rem 1rem .85rem; } .assist-footer { padding-left: 1rem; padding-right: 1rem; } }
@media(prefers-reduced-motion: reduce) { .assist-spinner { animation: none; } }
</style>
