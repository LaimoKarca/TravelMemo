<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, toRefs } from 'vue'
import type { EventDestination, Trip } from '@/types/travel'
import { createRecallState, type RecallState, type SearchItem, type SearchPayload, type SearchPhotoItem } from '@/types/search'
import type { PhotoDTO } from '@/types/photo'
import { searchRecall } from '@/api/search'
import { ApiError } from '@/api/auth'
import PhotoPicker from '@/features/media/PhotoPicker.vue'
import PhotoSourceMenu from '@/features/media/PhotoSourceMenu.vue'
import AppSearchBar from '@/components/ui/AppSearchBar.vue'
import PhotoViewer from '@/features/media/PhotoViewer.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import LocationLink from '@/features/footprints/LocationLink.vue'
import { mapsDestination, textAddress } from '@/utils/maps'

const props = defineProps<{
  trips: Trip[]
  state?: RecallState
}>()

const emit = defineEmits<{
  (e: 'view-source', item: SearchItem): void
  (e: 'jump-trip', payload: EventDestination): void
}>()

const state = props.state ?? reactive(createRecallState())
const {
  query, selectedTripId, selectedCity, selectedCategory, dateFrom, dateTo, searchLimit,
  showFilters, searchResult, photoResultsOpen, footprintResultsOpen, searchPhotos
} = toRefs(state)
const loading = ref(false)
const errorMessage = ref('')
const sourceMenu = ref<InstanceType<typeof PhotoSourceMenu> | null>(null)
const searchPhotoPickerRef = ref<InstanceType<typeof PhotoPicker> | null>(null)

// Lightbox for photo search results
const viewerVisible = ref(false)
const viewerPhotos = ref<PhotoDTO[]>([])
const viewerInitialPhotoId = ref<string | null>(null)

function openPhotoResult(item: SearchPhotoItem) {
  viewerInitialPhotoId.value = item.photo.id
  viewerPhotos.value = (searchResult.value?.photo_items || []).map((pi) => pi.photo)
  viewerVisible.value = true
}

function photoDestination(item: SearchPhotoItem): EventDestination | null {
  if (item.event) return { tripId: item.event.trip_id, eventId: item.event.id }
  if (item.trip_id !== undefined) return item.trip_id ? { tripId: item.trip_id } : null
  const binding = item.photo.bindings.find(b => b.kind === 'trip' || (b.kind === 'event' && b.trip_id))
  if (!binding) return null
  return { tripId: binding.kind === 'trip' ? binding.target_id : binding.trip_id! }
}
function photoDestinationLabel(item: SearchPhotoItem) { return item.event && !item.event.trip_id ? '前往足跡' : '前往手記' }
function jumpToPhotoTrip(item: SearchPhotoItem) {
  const destination = photoDestination(item)
  if (destination) emit('jump-trip', destination)
}

// Generation counter to guard against stale search results or races with reset
let searchGeneration = 0
onBeforeUnmount(() => { searchGeneration++ })

async function handleSearch() {
  const trimmed = query.value.trim()
  if (!trimmed && searchPhotos.value.length === 0) {
    errorMessage.value = '請輸入欲搜尋的關鍵字或選取照片。'
    return
  }

  const currentGen = ++searchGeneration
  errorMessage.value = ''
  loading.value = true

  const payload: SearchPayload = {
    query: trimmed,
    limit: searchLimit.value
  }

  if (searchPhotos.value.length > 0) {
    payload.photo_ids = searchPhotos.value.map((p) => p.id)
  }

  if (selectedTripId.value === ':standalone') payload.record_scope = 'standalone'
  else if (selectedTripId.value === ':trip') payload.record_scope = 'trip'
  else if (selectedTripId.value) payload.trip_id = selectedTripId.value
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
  photoResultsOpen.value = false
  footprintResultsOpen.value = true
  searchResult.value = null
  loading.value = false
}


</script>

<template>
  <section class="recall-search-section" aria-label="回憶搜尋">
    <h2 class="search-title">回憶搜尋</h2>
    <form class="search-form-card" role="search" aria-label="搜尋旅行回憶" @submit.prevent="handleSearch">
      <AppSearchBar
        v-model="query"
        input-id="search-query-input"
        input-type="text"
        lead="none"
        label="搜尋關鍵字"
        placeholder="搜尋地點或行程紀錄..."
        :disabled="loading"
        :required="searchPhotos.length === 0"
      >
        <template #actions>
          <PhotoSourceMenu
            ref="sourceMenu"
            below
            :disabled="searchPhotoPickerRef?.isUploading"
            @camera="searchPhotoPickerRef?.triggerCamera()"
            @gallery="searchPhotoPickerRef?.triggerGallery()"
          />
          <button
            type="button"
            class="icon-button search-bar__control"
            :class="{ 'is-active': showFilters }"
            :aria-expanded="showFilters"
            aria-controls="recall-filters"
            @click="showFilters = !showFilters"
          >
            <AppIcon name="filter" />
            <span class="sr-only">{{ showFilters ? '收起篩選' : '進階篩選' }}</span>
          </button>
          <button
            type="submit"
            class="btn btn-primary search-submit-btn"
            :disabled="loading || searchPhotos.some(p => p.status !== 'ready') || (!query.trim() && searchPhotos.length === 0)"
          >
            <AppIcon name="search" />
            <span class="sr-only">{{ loading ? '搜尋中...' : '搜尋' }}</span>
          </button>
        </template>
      </AppSearchBar>
      <PhotoPicker
        ref="searchPhotoPickerRef"
        v-model:photos="searchPhotos"
        hide-controls
        compact
        :max-photos="4"
        @selection-finished="sourceMenu?.close()"
      />
      <!-- Collapsible Additional Filters Grid (v-show preserves DOM access for tests/a11y) -->
      <div v-show="showFilters" id="recall-filters" class="filters-grid">
        <!-- Trip scope stays with the other collapsible filters. -->
        <div class="trip-selector-wrap">
          <label for="filter-trip" class="filter-label">回憶來源</label>
          <select id="filter-trip" v-model="selectedTripId" class="form-input filter-input trip-select" :disabled="loading">
            <option value="">全部回憶</option>
            <option value=":standalone">日常足跡</option>
            <option value=":trip">旅行手記</option>
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
      <div class="page-spinner ui-spinner ui-spinner--page" aria-hidden="true"></div>
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

              <button v-if="photoDestination(pItem)" type="button" class="icon-button jump-btn" :aria-label="photoDestinationLabel(pItem)" :title="photoDestinationLabel(pItem)" @click.stop="jumpToPhotoTrip(pItem)"><AppIcon name="jump" /></button>
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
              <div class="source-title-row">
                <h3 class="source-place-name">{{ item.event.place_name }}</h3>
                <div v-if="item.event.city || textAddress(item.event.address) || mapsDestination(item.event)" class="source-location-row">
                  <LocationLink v-if="mapsDestination(item.event)" :location="item.event" />
                  <AppIcon v-else name="pin" class="source-location-pin" />
                  <span class="loc-text">{{ item.event.city || textAddress(item.event.address) }}</span>
                </div>
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
            <button type="button" class="icon-button jump-btn" :aria-label="item.event.trip_id ? '前往手記' : '前往足跡'" :title="item.event.trip_id ? '前往手記' : '前往足跡'" @click.stop="emit('jump-trip', { tripId: item.event.trip_id, eventId: item.event.id })"><AppIcon name="jump" /></button>
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

<style scoped src="./RecallSearch.css"></style>
