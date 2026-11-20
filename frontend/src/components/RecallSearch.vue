<script setup lang="ts">
import { ref } from 'vue'
import type { Trip } from '../types/travel'
import type { SearchItem, SearchPayload, SearchResponse, SearchPhotoItem } from '../types/search'
import type { PhotoDTO } from '../types/photo'
import { searchRecall } from '../api/search'
import { ApiError } from '../api/auth'
import PhotoPicker from './PhotoPicker.vue'
import PhotoViewer from './PhotoViewer.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps<{
  trips: Trip[]
}>()

const emit = defineEmits<{
  (e: 'view-source', item: SearchItem): void
  (e: 'jump-trip', payload: { tripId: string; eventId?: string }): void
}>()

const query = ref('')
const selectedTripId = ref('')
const selectedCity = ref('')
const selectedCategory = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const searchLimit = ref<number>(10)

// Extra filters collapsed initially per brief
const showFilters = ref(false)

const loading = ref(false)
const errorMessage = ref('')
const hasSearched = ref(false)
const searchResult = ref<SearchResponse | null>(null)
const photoResultsOpen = ref(false)
const footprintResultsOpen = ref(true)

// Image search state
const searchPhotos = ref<PhotoDTO[]>([])
const searchPhotoPickerRef = ref<any>(null)

// Lightbox for photo search results
const viewerVisible = ref(false)
const viewerPhotos = ref<PhotoDTO[]>([])
const viewerInitialPhotoId = ref<string | null>(null)

function openPhotoResult(item: SearchPhotoItem) {
  viewerInitialPhotoId.value = item.photo.id
  viewerPhotos.value = (searchResult.value?.photo_items || []).map((pi) => pi.photo)
  viewerVisible.value = true
}

function photoDestination(item: SearchPhotoItem): { tripId: string; eventId?: string } | null {
  if (item.event) return { tripId: item.event.trip_id, eventId: item.event.id }
  const binding = item.photo.bindings.find(b => b.kind === 'trip' || (b.kind === 'event' && b.trip_id))
  if (!binding) return null
  return { tripId: binding.kind === 'trip' ? binding.target_id : binding.trip_id! }
}
function jumpToPhotoTrip(item: SearchPhotoItem) {
  const destination = photoDestination(item)
  if (destination) emit('jump-trip', destination)
}

// Generation counter to guard against stale search results or races with reset
let searchGeneration = 0

async function handleSearch() {
  const trimmed = query.value.trim()
  if (!trimmed && searchPhotos.value.length === 0) {
    errorMessage.value = '請輸入欲搜尋的關鍵字或選取照片。'
    return
  }

  const currentGen = ++searchGeneration
  errorMessage.value = ''
  loading.value = true
  hasSearched.value = true

  const payload: SearchPayload = {
    query: trimmed,
    limit: searchLimit.value
  }

  if (searchPhotos.value.length > 0) {
    payload.photo_ids = searchPhotos.value.map((p) => p.id)
  }

  if (selectedTripId.value) payload.trip_id = selectedTripId.value
  if (selectedCity.value.trim()) payload.city = selectedCity.value.trim()
  if (selectedCategory.value.trim()) payload.category = selectedCategory.value.trim()
  if (dateFrom.value) payload.date_from = dateFrom.value
  if (dateTo.value) payload.date_to = dateTo.value

  try {
    const res = await searchRecall(payload)
    if (currentGen !== searchGeneration) {
      return
    }
    searchResult.value = res
    photoResultsOpen.value = false
    footprintResultsOpen.value = true
  } catch (err: any) {
    if (currentGen !== searchGeneration) {
      return
    }
    searchResult.value = null
    errorMessage.value = err instanceof ApiError ? err.detail : '檢索旅行回憶時發生錯誤，請稍後再試。'
  } finally {
    if (currentGen === searchGeneration) {
      loading.value = false
    }
  }
}

function handleResetFilters() {
  searchGeneration++
  query.value = ''
  searchPhotos.value = []
  searchPhotoPickerRef.value?.clear()
  selectedTripId.value = ''
  selectedCity.value = ''
  selectedCategory.value = ''
  dateFrom.value = ''
  dateTo.value = ''
  searchLimit.value = 10
  errorMessage.value = ''
  hasSearched.value = false
  photoResultsOpen.value = false
  footprintResultsOpen.value = true
  searchResult.value = null
  loading.value = false
}

function toggleFilters() {
  showFilters.value = !showFilters.value
}


</script>

<template>
  <section class="recall-search-section" aria-label="回憶搜尋">
    <!-- Confident short page heading per brief, no decorative filler subtitle -->
    <div class="search-header">
      <h2 class="search-title">回憶搜尋</h2>


    </div>

    <!-- Search Bar & Controls -->
    <form class="search-form-card" @submit.prevent="handleSearch">
      <!-- Main Search Input and Readily Available Trip Selector per brief -->
      <div class="main-query-row">
        <div class="query-input-wrap">
          <label for="search-query-input" class="sr-only">搜尋關鍵字</label>
          <div class="input-with-icon">
            <svg class="search-lens-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              id="search-query-input"
              v-model="query"
              type="text"
              class="form-input query-input"
              placeholder="搜尋地點或行程紀錄..."
              :disabled="loading"
              :required="searchPhotos.length === 0"
            />
          </div>
        </div>

        <PhotoPicker ref="searchPhotoPickerRef" v-model:photos="searchPhotos" :icon-only="true" :compact="true" :multiple="true" :max-photos="4" />

        <!-- Clear filter toggle button -->
        <button
          type="button"
          class="btn btn-secondary filter-toggle-btn"
          :aria-expanded="showFilters"
          @click="toggleFilters"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
          <span class="sr-only">{{ showFilters ? '收起篩選' : '進階篩選' }}</span>
        </button>

        <button
          type="submit"
          class="btn btn-primary search-submit-btn"
          :disabled="loading || searchPhotos.some(p => p.status !== 'ready') || (!query.trim() && searchPhotos.length === 0)"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span class="sr-only">{{ loading ? '搜尋中...' : '搜尋' }}</span>
        </button>
      </div>

      <!-- Collapsible Additional Filters Grid (v-show preserves DOM access for tests/a11y) -->
      <div v-show="showFilters" class="filters-grid">
        <!-- Trip scope stays with the other collapsible filters. -->
        <div class="trip-selector-wrap">
          <label for="filter-trip" class="filter-label">指定旅程</label>
          <select id="filter-trip" v-model="selectedTripId" class="form-input filter-input trip-select" :disabled="loading">
            <option value="">全部旅程手記</option>
            <option v-for="t in trips" :key="t.id" :value="t.id">
              {{ t.name }}
            </option>
          </select>
        </div>


        <div class="filter-col">
          <label for="filter-city" class="filter-label">城市</label>
          <input
            id="filter-city"
            v-model="selectedCity"
            type="text"
            class="form-input filter-input"
            placeholder="例如：京都市"
            :disabled="loading"
          />
        </div>

        <div class="filter-col">
          <label for="filter-category" class="filter-label">類別</label>
          <input
            id="filter-category"
            v-model="selectedCategory"
            type="text"
            class="form-input filter-input"
            placeholder="例如：景點"
            :disabled="loading"
          />
        </div>

        <div class="dates-grouped-col">
          <div class="filter-col date-subcol">
            <label for="filter-date-from" class="filter-label">起始日期：</label>
            <input
              id="filter-date-from"
              v-model="dateFrom"
              type="date"
              class="form-input filter-input"
              :disabled="loading"
            />
          </div>

          <div class="filter-col date-subcol">
            <label for="filter-date-to" class="filter-label">結束日期：</label>
            <input
              id="filter-date-to"
              v-model="dateTo"
              type="date"
              class="form-input filter-input"
              :disabled="loading"
            />
          </div>
        </div>

        <div class="reset-wrap">
          <button
            type="button"
            class="btn-link reset-btn"
            @click="handleResetFilters"
          >
            重設篩選條件
          </button>
        </div>
      </div>
    </form>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Clarification Prompt from Search Service -->
    <div v-if="searchResult && searchResult.clarification" class="clarification-card" role="region" aria-label="搜尋澄清說明">
      <div class="clarification-content">
        <h4 class="clarification-title">搜尋建議與釐清</h4>
        <p class="clarification-text">{{ searchResult.clarification }}</p>
      </div>
    </div>

    <!-- Results Context Toolbar: Limit moved to results context per brief -->
    <div class="results-toolbar">
      <span class="results-count">
        搜尋結果
      </span>

      <div class="toolbar-limit-group">
        <label for="filter-limit" class="filter-label limit-label">顯示上限</label>
        <select id="filter-limit" v-model.number="searchLimit" class="form-input filter-limit-select" :disabled="loading">
          <option :value="10">10 筆</option>
          <option :value="20">20 筆</option>
          <option :value="50">50 筆</option>
        </select>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state" role="status" aria-live="polite">
      <div class="page-spinner" aria-hidden="true"></div>
      <p class="loading-text">正在回憶旅程中...</p>
    </div>

    <!-- Results Container -->
    <div v-else-if="searchResult" class="results-container">
      <!-- Empty Results -->
      <div v-if="searchResult.items.length === 0 && (!searchResult.photo_items || searchResult.photo_items.length === 0)" class="empty-results">
        <div class="empty-icon" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        </div>
        <h3 class="empty-title">還沒找到回憶</h3>
        <p class="empty-desc">
          換個關鍵字或調整篩選試試。
        </p>
      </div>

      <!-- Matched Photos Section -->
      <div v-if="searchResult.photo_items && searchResult.photo_items.length > 0" class="photo-results-section">
        <h3 class="result-section-title"><button type="button" class="result-section-toggle" :aria-expanded="photoResultsOpen" aria-controls="photo-results" @click="photoResultsOpen = !photoResultsOpen"><span>相符照片記憶 ({{ searchResult.photo_items.length }})</span><AppIcon name="chevron" :class="{ 'is-open': photoResultsOpen }" /></button></h3>
        <div v-show="photoResultsOpen" id="photo-results" class="photo-results-grid">
          <article
            v-for="(pItem, pIdx) in searchResult.photo_items"
            :key="pItem.photo.id + '-' + pIdx"
            class="photo-result-card"
          >
            <div
              class="photo-result-thumb-box"
              tabindex="0"
              role="button"
              :aria-label="`檢視相符照片：${pItem.photo.caption || pItem.photo.analysis?.summary || '相簿照片'}`"
              @click="openPhotoResult(pItem)"
              @keydown.enter="openPhotoResult(pItem)"
              @keydown.space.prevent="openPhotoResult(pItem)"
            >
              <img
                :src="pItem.photo.thumbnail_url || pItem.photo.url"
                :alt="pItem.photo.caption || '搜尋照片結果'"
                class="photo-result-img"
              />
            </div>

            <div class="photo-result-info">
              <p v-if="pItem.photo.caption" class="photo-result-caption">
                {{ pItem.photo.caption }}
              </p>
              <p v-else-if="pItem.photo.analysis?.summary" class="photo-result-summary">
                {{ pItem.photo.analysis.summary }}
              </p>

              <button v-if="photoDestination(pItem)" type="button" class="icon-button jump-btn" aria-label="前往手記" title="前往手記" @click.stop="jumpToPhotoTrip(pItem)"><AppIcon name="jump" /></button>
            </div>
          </article>
        </div>
      </div>

      <!-- Results with original sources and recorded context -->
      <section v-if="searchResult.items.length > 0" class="footprint-results-section">
        <h3 class="result-section-title"><button type="button" class="result-section-toggle" :aria-expanded="footprintResultsOpen" aria-controls="footprint-results" @click="footprintResultsOpen = !footprintResultsOpen"><span>相符足跡 ({{ searchResult.items.length }})</span><AppIcon name="chevron" :class="{ 'is-open': footprintResultsOpen }" /></button></h3>
      <div v-show="footprintResultsOpen" id="footprint-results" class="source-cards-grid">
        <article
          v-for="(item, idx) in searchResult.items"
          :key="item.event.id + '-' + idx"
          class="source-card source-row"
        >
          <button type="button" class="source-card-open" :aria-label="`檢視足跡：${item.event.place_name}`" @click="emit('view-source', item)"></button>
          <div class="source-row-main">
            <div class="source-card-header">
              <div class="source-badge-group">
                <span class="source-date-pill">{{ item.event.date }}</span>
                <span v-if="item.event.time" class="source-time-pill">{{ item.event.time }}</span>
                <span v-if="item.event.category" class="source-cat-pill">{{ item.event.category }}</span>
                <span v-if="item.event.trip_name" class="trip-tag">{{ item.event.trip_name }}</span>
              </div>
            </div>

            <div class="source-card-body">
              <h3 class="source-place-name">{{ item.event.place_name }}</h3>

              <div v-if="item.event.city || item.event.address" class="source-location-row">
                <span class="loc-text">
                  {{ [item.event.city, item.event.address].filter(Boolean).join(' · ') }}
                </span>
              </div>

              <!-- Reasons list: Quiet collapsed metadata -->

              <!-- Relation Context -->
              <div v-if="item.relation" class="relation-block">
                <span class="relation-label">時間關係脈絡：</span>
                <span class="relation-text">
                  基準日期 {{ item.relation.anchor_date }} ➔ {{ item.relation.direction === 'next' ? '下一站' : '上一站' }} ➔ 目標日期 {{ item.relation.target_date }}
                </span>
              </div>
            </div>
          </div>

          <div class="source-description-row">
            <p class="source-notes-excerpt">{{ item.event.notes || '尚無隨筆' }}</p>
            <button type="button" class="icon-button jump-btn" aria-label="前往手記" title="前往手記" @click.stop="emit('jump-trip', { tripId: item.event.trip_id, eventId: item.event.id })"><AppIcon name="jump" /></button>
          </div>
        </article>
      </div>
      </section>
    </div>

    <!-- Reusable Lightbox Viewer -->
    <PhotoViewer
      :visible="viewerVisible"
      :photos="viewerPhotos"
      :initial-photo-id="viewerInitialPhotoId"
      :can-edit-caption="false"
      @close="viewerVisible = false"
    />
  </section>
</template>

<style scoped>
.result-section-title { margin: 0; font-size: 1rem; font-weight: 600; }
.result-section-toggle { display: flex; align-items: center; justify-content: space-between; gap: .5rem; width: 100%; min-height: 44px; padding: .25rem 0; border: 0; background: transparent; color: var(--color-ink); font: inherit; cursor: pointer; text-align: left; }
.result-section-toggle svg { color: var(--color-subtle); transition: transform .15s ease; }
.result-section-toggle svg.is-open { transform: rotate(180deg); }
.result-section-toggle:focus-visible { outline: 2px solid var(--color-maple); outline-offset: 2px; border-radius: var(--radius-sm); }
.footprint-results-section { display: flex; flex-direction: column; gap: .5rem; }
@media(prefers-reduced-motion: reduce) { .result-section-toggle svg { transition: none; } }
.main-query-row { position: relative; }
.main-query-row :deep(.photo-source-options) { top: calc(100% + .4rem); bottom: auto; }
.main-query-row :deep(.is-icon-only) { width: 44px; flex: 0 0 44px; }
.main-query-row :deep(.staged-previews-grid) { position: absolute; left: 0; top: 100%; display: flex; margin-top: .5rem; }
.main-query-row:has(.staged-preview-item) { margin-bottom: 100px; }

.recall-search-section {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
}

.search-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
}

.search-title {
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--color-ink);
  letter-spacing: -0.01em;
}

.vector-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-subtle);
  background-color: var(--color-paper);
  padding: 0.25rem 0.625rem;
  border-radius: var(--radius-xs);
  border: 1px solid var(--color-border);
}

.status-indicator-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--color-olive);
}

.status-indicator-dot.building {
  background-color: var(--color-amber);
}

.status-indicator-dot.degraded {
  background-color: #C06020;
}

/* Search Form Card */
.search-form-card {
  background-color: transparent;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.search-photos-picker-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  padding: 0.25rem 0;
}

.search-picker-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-subtle);
}

/* Photo Search Results */
.photo-results-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.photo-results-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--color-ink);
}

.photo-results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 1rem;
}

.photo-result-card {
  display: flex;
  flex-direction: column;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.photo-result-card:hover {
  border-color: var(--color-maple);
  box-shadow: var(--shadow-sm);
}

.photo-result-thumb-box {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  cursor: pointer;
  background-color: var(--color-canvas);
}

.photo-result-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}

.photo-result-thumb-box:hover .photo-result-img {
  transform: scale(1.04);
}

.photo-result-thumb-box:focus-visible {
  outline: 2px solid var(--color-maple);
  outline-offset: -2px;
}

.photo-score-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 0.6875rem;
}

.photo-result-info {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.625rem 0.75rem;
}

.photo-result-caption,
.photo-result-summary {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-ink);
  line-height: 1.35;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}

.photo-result-actions {
  margin-top: 0.25rem;
}

.main-query-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  width: 100%;
  min-width: 0;
  flex-wrap: wrap;
}

.query-input-wrap {
  flex: 2 1 240px;
  min-width: 0;
}

.trip-selector-wrap {
  flex: 1 1 180px;
  min-width: 0;
}

.input-with-icon {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.search-lens-icon {
  position: absolute;
  left: 0.75rem;
  color: var(--color-subtle);
  pointer-events: none;
}

.query-input {
  font-size: 0.875rem;
  padding-left: 2.25rem;
  min-height: 40px;
}

.trip-select {
  min-height: 40px;
  font-size: 0.8125rem;
}

.filter-toggle-btn {
  white-space: nowrap;
  min-height: 40px;
  font-size: 0.8125rem;
  padding: 0.35rem 0.75rem;
}

.search-submit-btn {
  white-space: nowrap;
  min-height: 40px;
  font-size: 0.8125rem;
  padding: 0.35rem 1rem;
}

/* Collapsible Filters Grid: minmax(0, 1fr) for mobile responsiveness down to 390px */
.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border-light);
  align-items: end;
}

.dates-grouped-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  grid-column: span 2;
}

.filter-col {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-subtle);
}

.filter-input {
  min-height: 36px;
  padding: 0.25rem 0.5rem;
  font-size: 0.8125rem;
}

.reset-wrap {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.reset-btn {
  font-size: 0.75rem;
  padding: 0;
  min-height: auto;
}

/* Results Toolbar: Limit placed in results context per brief */
.results-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.25rem 0.25rem;
  gap: 1rem;
}

.results-count {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-ink);
}

.toolbar-limit-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.limit-label {
  font-size: 0.75rem;
  color: var(--color-subtle);
  white-space: nowrap;
}

.filter-limit-select {
  width: auto;
  min-height: 32px;
  padding: 0.2rem 0.5rem;
  font-size: 0.75rem;
}

/* Clarification Card */
.clarification-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  background-color: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-sm);
  padding: 0.75rem 1rem;
}

.clarification-icon {
  font-size: 1.125rem;
}

.clarification-title {
  font-size: 0.875rem;
  font-weight: 700;
  color: var(--color-warning-text);
}

.clarification-text {
  font-size: 0.8125rem;
  color: var(--color-warning-text);
  margin-top: 0.2rem;
  line-height: 1.4;
}

/* Error Banner */
.error-banner {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-text);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
}

/* Flat Rows per brief */
.source-cards-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
}

.source-card {
  position: relative;
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: .35rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  width: 100%;
  box-sizing: border-box;
}

.source-card:hover {
  border-color: var(--color-maple);
  box-shadow: var(--shadow-sm);
}

.source-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.source-card-open { position: absolute; inset: 0; z-index: 1; width: 100%; border: 0; background: transparent; border-radius: inherit; cursor: pointer; }
.source-card-open:focus-visible { outline: 2px solid var(--color-maple); outline-offset: 2px; }
.source-description-row { display: flex; align-items: center; gap: .5rem; width: 100%; min-width: 0; }
.jump-btn { flex: 0 0 40px; min-width: 40px; min-height: 40px; border: 0; background: transparent; position: relative; z-index: 2; }

.source-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.source-badge-group {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.source-date-pill {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-olive-text);
  background-color: var(--color-olive-pale);
  padding: 0.12rem 0.4rem;
  border-radius: var(--radius-xs);
}

.source-time-pill {
  font-size: 0.6875rem;
  font-family: var(--font-mono);
  color: var(--color-subtle);
  background-color: var(--color-canvas);
  padding: 0.12rem 0.4rem;
  border-radius: var(--radius-xs);
}

.source-cat-pill {
  font-size: 0.6875rem;
  font-weight: 500;
  color: var(--color-amber-text);
  background-color: var(--color-amber-subtle);
  border: 1px solid rgba(224, 182, 91, 0.4);
  padding: 0.12rem 0.4rem;
  border-radius: var(--radius-xs);
}

.trip-tag {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-maple);
}

.score-badge {
  font-size: 0.6875rem;
  color: var(--color-subtle);
  background-color: var(--color-canvas);
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-xs);
}

.source-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.source-place-name {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--color-ink);
  line-height: 1.3;
}

.source-location-row {
  display: flex;
  align-items: center;
  font-size: 0.75rem;
  color: var(--color-subtle);
}

.source-notes-excerpt {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8125rem;
  color: var(--color-subtle);
  line-height: 1.5;
  padding: 0.25rem 0;
}

.reasons-block {
  font-size: 0.75rem;
  color: var(--color-ink);
  padding-top: 0.25rem;
}

.reasons-title {
  font-weight: 600;
  color: var(--color-subtle);
  cursor: pointer;
}

.reasons-list {
  list-style-type: disc;
  padding-left: 1.25rem;
  margin-top: 0.2rem;
}

.reason-item {
  color: var(--color-ink);
  line-height: 1.4;
}

.relation-block {
  font-size: 0.75rem;
  background-color: var(--color-maple-subtle);
  padding: 0.35rem 0.5rem;
  border-radius: var(--radius-xs);
  color: var(--color-maple);
}

.relation-label {
  font-weight: 600;
}

.source-card-footer {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
  flex-shrink: 0;
}

.btn-sm {
  min-height: 32px;
  padding: 0.25rem 0.75rem;
  font-size: 0.75rem;
  white-space: nowrap;
}

/* Loading & Empty states */
.loading-state,
.empty-results {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  text-align: center;
  background-color: var(--color-paper);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-sm);
  gap: 0.75rem;
}

.empty-icon {
  color: var(--color-maple);
  opacity: 0.8;
}

.empty-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--color-ink);
}

.empty-desc {
  font-size: 0.8125rem;
  color: var(--color-subtle);
  max-width: 400px;
  line-height: 1.5;
}

.page-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(169, 85, 53, 0.2);
  border-top-color: var(--color-maple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 0.875rem;
  color: var(--color-subtle);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Responsive */
@media (max-width: 768px) {
  .search-form-card {
    padding: 0;
  }

  .main-query-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: stretch;
  }

  .query-input-wrap,
  .trip-selector-wrap { grid-column: 1 / -1; }

  .query-input-wrap,
  .trip-selector-wrap,
  .filter-toggle-btn,
  .search-submit-btn {
    width: 100%;
    flex: 1 1 100%;
  }

  .dates-grouped-col {
    grid-column: span 1;
    grid-template-columns: minmax(0, 1fr);
  }

  .filters-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .source-card {
    flex-direction: column;
    align-items: stretch;
  }

  .source-card-footer {
    flex-direction: row;
    justify-content: flex-end;
    border-top: 1px solid var(--color-border-light);
    padding-top: 0.5rem;
    width: 100%;
  }

  .source-card-footer .btn {
    flex: 1;
  }
}
@media (max-width: 768px) {
  .main-query-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: center; }
  .main-query-row .query-input-wrap { grid-column: 1 / 4; grid-row: 1; min-width: 0; width: 100%; }
  .main-query-row :deep(.photo-picker-container) { grid-column: 4; grid-row: 1; justify-self: end; }
  .main-query-row :deep(.photo-source-options) { left: auto; right: 0; }
  .main-query-row .trip-selector-wrap { grid-column: 1 / -1; grid-row: 2; }
  .main-query-row .filter-toggle-btn { grid-column: 1 / 3; grid-row: 3; }
  .main-query-row .search-submit-btn { grid-column: 3 / 5; grid-row: 3; }
}

.main-query-row { display: flex; flex-wrap: nowrap; gap: .15rem; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-paper); padding: .15rem; align-items: center; }
.main-query-row .query-input-wrap { flex: 1 1 0; min-width: 0; width: auto; }
.main-query-row .query-input { border: 0; background: transparent; box-shadow: none; padding-left: .65rem; }
.main-query-row .search-lens-icon { display: none; }
.main-query-row .filter-toggle-btn, .main-query-row .search-submit-btn { flex: 0 0 36px; width: 36px; min-height: 38px; padding: 0; display: inline-flex; align-items: center; justify-content: center; }
.main-query-row :deep(.is-icon-only) { flex: 0 0 36px; width: 36px; }
.main-query-row :deep(.icon-button) { min-width: 36px; width: 36px; height: 38px; }
.main-query-row .filter-toggle-btn { border: 0; background: transparent; }
.trip-selector-wrap { display: flex; flex-direction: column; gap: .35rem; }
@media(max-width: 768px) { .main-query-row .query-input-wrap { grid-column: auto; grid-row: auto; } .main-query-row :deep(.photo-picker-container) { grid-column: auto; grid-row: auto; } }
.empty-title, .empty-desc { text-wrap: pretty; }
</style>
