<script setup lang="ts">
import { ref } from 'vue'
import type { Trip } from '../types/travel'
import type { SearchItem, SearchPayload, SearchResponse } from '../types/search'
import { searchRecall } from '../api/search'
import { ApiError } from '../api/auth'

const props = defineProps<{
  trips: Trip[]
}>()

const emit = defineEmits<{
  (e: 'view-source', item: SearchItem): void
  (e: 'jump-trip', payload: { tripId: string; eventId: string }): void
}>()

const query = ref('')
const selectedTripId = ref('')
const selectedCity = ref('')
const selectedCategory = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const searchLimit = ref<number>(10)

const loading = ref(false)
const errorMessage = ref('')
const hasSearched = ref(false)
const searchResult = ref<SearchResponse | null>(null)

// Generation counter to guard against stale search results or races with reset
let searchGeneration = 0

async function handleSearch() {
  const trimmed = query.value.trim()
  if (!trimmed) {
    errorMessage.value = '請輸入欲搜尋的關鍵字。'
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
  selectedTripId.value = ''
  selectedCity.value = ''
  selectedCategory.value = ''
  dateFrom.value = ''
  dateTo.value = ''
  searchLimit.value = 10
  errorMessage.value = ''
  hasSearched.value = false
  searchResult.value = null
  loading.value = false
}

function getVectorStatusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case 'ready':
      return '向量索引就緒'
    case 'building':
    case 'indexing':
      return '向量建立中'
    case 'degraded':
      return '向量降級模式 (BM25)'
    default:
      return `向量狀態：${status}`
  }
}
</script>

<template>
  <section class="recall-search-section" aria-label="回憶搜尋">
    <div class="search-header">
      <div>
        <h2 class="search-title">旅途回憶檢索</h2>
        <p class="search-subtitle">
          運用語意與時間關係檢索您的旅程足跡、尋訪備忘與感動片刻。
        </p>
      </div>

      <div v-if="searchResult && searchResult.vector_status" class="vector-status-badge">
        <span class="status-indicator-dot" :class="searchResult.vector_status.toLowerCase()"></span>
        <span>{{ getVectorStatusLabel(searchResult.vector_status) }}</span>
      </div>
    </div>

    <!-- Search Form -->
    <form class="search-form-card" @submit.prevent="handleSearch">
      <div class="main-query-row">
        <div class="query-input-wrap">
          <label for="search-query-input" class="sr-only">搜尋關鍵字</label>
          <input
            id="search-query-input"
            v-model="query"
            type="text"
            class="form-input query-input"
            placeholder="例如：清水寺、宇治抹茶、嵐山渡月橋、雨天美術館..."
            :disabled="loading"
            required
          />
        </div>
        <button
          type="submit"
          class="btn btn-primary search-submit-btn"
          :disabled="loading || !query.trim()"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span>{{ loading ? '搜尋中...' : '搜尋回憶' }}</span>
        </button>
      </div>

      <!-- Advanced Filter Options -->
      <div class="filters-grid">
        <div class="filter-col">
          <label for="filter-trip" class="filter-label">指定手記：</label>
          <select id="filter-trip" v-model="selectedTripId" class="form-input filter-input" :disabled="loading">
            <option value="">全部旅程手記</option>
            <option v-for="t in trips" :key="t.id" :value="t.id">
              {{ t.name }}
            </option>
          </select>
        </div>

        <div class="filter-col">
          <label for="filter-city" class="filter-label">城市地點：</label>
          <input
            id="filter-city"
            v-model="selectedCity"
            type="text"
            class="form-input filter-input"
            placeholder="例如：京都市、台東縣"
            :disabled="loading"
          />
        </div>

        <div class="filter-col">
          <label for="filter-category" class="filter-label">足跡類別：</label>
          <input
            id="filter-category"
            v-model="selectedCategory"
            type="text"
            class="form-input filter-input"
            placeholder="例如：景點、美食、文化"
            :disabled="loading"
          />
        </div>

        <div class="filter-col">
          <label for="filter-date-from" class="filter-label">起始日期：</label>
          <input
            id="filter-date-from"
            v-model="dateFrom"
            type="date"
            class="form-input filter-input"
            :disabled="loading"
          />
        </div>

        <div class="filter-col">
          <label for="filter-date-to" class="filter-label">結束日期：</label>
          <input
            id="filter-date-to"
            v-model="dateTo"
            type="date"
            class="form-input filter-input"
            :disabled="loading"
          />
        </div>

        <div class="filter-col limit-col">
          <label for="filter-limit" class="filter-label">筆數上限：</label>
          <select id="filter-limit" v-model.number="searchLimit" class="form-input filter-input" :disabled="loading">
            <option :value="10">10 筆</option>
            <option :value="20">20 筆</option>
            <option :value="50">50 筆</option>
          </select>
        </div>
      </div>

      <div class="form-actions-row">
        <button
          type="button"
          class="btn-link reset-btn"
          @click="handleResetFilters"
        >
          重設篩選條件
        </button>
      </div>
    </form>

    <!-- Error Banner -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Clarification Prompt from Search Service -->
    <div v-if="searchResult && searchResult.clarification" class="clarification-card" role="region" aria-label="搜尋澄清說明">
      <div class="clarification-icon" aria-hidden="true">💡</div>
      <div class="clarification-content">
        <h4 class="clarification-title">搜尋建議與釐清</h4>
        <p class="clarification-text">{{ searchResult.clarification }}</p>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state" role="status" aria-live="polite">
      <div class="page-spinner" aria-hidden="true"></div>
      <p class="loading-text">正在回憶旅程中...</p>
    </div>

    <!-- Results Container -->
    <div v-else-if="searchResult" class="results-container">
      <div class="results-meta-bar">
        <span class="results-count">
          找到 {{ searchResult.items.length }} 處相符足跡
        </span>
      </div>

      <!-- Empty Results -->
      <div v-if="searchResult.items.length === 0" class="empty-results">
        <div class="empty-icon" aria-hidden="true">
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        </div>
        <h3 class="empty-title">查無相符的旅行記憶</h3>
        <p class="empty-desc">
          未找到與「{{ query }}」相關的足跡。建議放寬日期或城市篩選，或換個相近的描述再試一次。
        </p>
      </div>

      <!-- Source Cards Grid -->
      <div v-else class="source-cards-grid">
        <article
          v-for="(item, idx) in searchResult.items"
          :key="item.event.id + '-' + idx"
          class="source-card"
        >
          <div class="source-card-header">
            <div class="source-badge-group">
              <span class="source-date-pill">{{ item.event.date }}</span>
              <span v-if="item.event.time" class="source-time-pill">{{ item.event.time }}</span>
              <span v-if="item.event.category" class="source-cat-pill">{{ item.event.category }}</span>
            </div>
            <div class="score-badge" :title="`關聯度評分: ${item.score}`">
              <span>評分：{{ typeof item.score === 'number' ? item.score.toFixed(2) : item.score }}</span>
            </div>
          </div>

          <div class="source-card-body">
            <h3 class="source-place-name">{{ item.event.place_name }}</h3>

            <div v-if="item.event.trip_name || item.event.city || item.event.address" class="source-location-row">
              <span v-if="item.event.trip_name" class="trip-tag">📖 {{ item.event.trip_name }}</span>
              <span v-if="item.event.city || item.event.address" class="loc-text">
                📍 {{ [item.event.city, item.event.address].filter(Boolean).join(' · ') }}
              </span>
            </div>

            <p v-if="item.event.notes" class="source-notes-excerpt">
              {{ item.event.notes }}
            </p>

            <!-- Reasons list -->
            <div v-if="item.reasons && item.reasons.length > 0" class="reasons-block">
              <span class="reasons-title">命中原因：</span>
              <ul class="reasons-list">
                <li v-for="(reason, rIdx) in item.reasons" :key="rIdx" class="reason-item">
                  {{ reason }}
                </li>
              </ul>
            </div>

            <!-- Relation Context -->
            <div v-if="item.relation" class="relation-block">
              <span class="relation-label">時間關係脈絡：</span>
              <span class="relation-text">
                基準日期 {{ item.relation.anchor_date }} ➔ {{ item.relation.direction === 'next' ? '下一站' : '上一站' }} ➔ 目標日期 {{ item.relation.target_date }}
              </span>
            </div>
          </div>

          <footer class="source-card-footer">
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              @click="emit('view-source', item)"
            >
              檢視詳情
            </button>
            <button
              type="button"
              class="btn btn-primary btn-sm jump-btn"
              @click="emit('jump-trip', { tripId: item.event.trip_id, eventId: item.event.id })"
            >
              跳至原旅程
            </button>
          </footer>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.recall-search-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
}

.search-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
}

.search-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-ink);
}

.search-subtitle {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  margin-top: 0.25rem;
}

.vector-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.08);
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(23, 107, 104, 0.2);
}

.status-indicator-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-teal);
}

.status-indicator-dot.building {
  background-color: var(--color-yellow);
}

.status-indicator-dot.degraded {
  background-color: #d97706;
}

/* Search Form */
.search-form-card {
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  box-shadow: 0 2px 8px rgba(21, 62, 72, 0.04);
}

.main-query-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  width: 100%;
  min-width: 0;
}

.query-input-wrap {
  flex: 1;
  min-width: 240px;
}

.query-input {
  font-size: 1.0625rem;
  padding: 0.75rem 1rem;
}

.search-submit-btn {
  white-space: nowrap;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 1rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--color-border);
}

.filter-col {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.filter-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-subtle);
}

.filter-input {
  min-height: 38px;
  padding: 0.35rem 0.65rem;
  font-size: 0.875rem;
}

.form-actions-row {
  display: flex;
  justify-content: flex-end;
}

.reset-btn {
  font-size: 0.8125rem;
  padding: 0;
  min-height: auto;
}

/* Clarification Card */
.clarification-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  background-color: #fff9e6;
  border: 1px solid #fae19c;
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
}

.clarification-icon {
  font-size: 1.25rem;
}

.clarification-title {
  font-size: 0.9375rem;
  font-weight: 700;
  color: #634a00;
}

.clarification-text {
  font-size: 0.875rem;
  color: #4a3805;
  margin-top: 0.25rem;
  line-height: 1.5;
}

/* Error Banner */
.error-banner {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-text);
  padding: 0.875rem 1rem;
  border-radius: var(--radius-md);
  font-size: 0.9375rem;
}

/* Results */
.results-meta-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.results-count {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-teal);
}

.source-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.25rem;
  width: 100%;
  min-width: 0;
}

.source-card {
  background-color: var(--color-paper);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 1rem;
  box-shadow: 0 2px 6px rgba(21, 62, 72, 0.04);
  transition: all 0.2s ease;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.source-card:hover {
  border-color: var(--color-teal);
  box-shadow: 0 4px 12px rgba(21, 62, 72, 0.08);
}

.source-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
  width: 100%;
  min-width: 0;
}

.source-badge-group {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
  min-width: 0;
}

.source-date-pill {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.08);
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
}

.source-time-pill {
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--color-subtle);
  background-color: #f0f4f5;
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-sm);
}

.source-cat-pill {
  font-size: 0.75rem;
  font-weight: 500;
  color: #4a3805;
  background-color: #fff2c4;
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-sm);
}

.score-badge {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-subtle);
  background-color: #eaf1f3;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
}

.source-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  width: 100%;
  min-width: 0;
}

.source-place-name {
  font-size: 1.1875rem;
  font-weight: 600;
  color: var(--color-ink);
  line-height: 1.3;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.source-location-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-subtle);
  flex-wrap: wrap;
  width: 100%;
  min-width: 0;
  word-break: break-word;
}

.trip-tag {
  font-weight: 500;
  color: var(--color-teal);
}

.source-notes-excerpt {
  font-size: 0.875rem;
  color: var(--color-subtle);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  background-color: #f7fbfc;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--color-teal);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.reasons-block {
  font-size: 0.8125rem;
  color: var(--color-ink);
  background-color: #fdfaf3;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid #fae8c8;
}

.reasons-title {
  font-weight: 600;
  color: #78350f;
}

.reasons-list {
  list-style-type: disc;
  padding-left: 1.25rem;
  margin-top: 0.25rem;
}

.reason-item {
  color: #451a03;
  line-height: 1.4;
}

.relation-block {
  font-size: 0.8125rem;
  background-color: #f0f7f7;
  padding: 0.4rem 0.6rem;
  border-radius: var(--radius-sm);
  border: 1px solid #d0e7e7;
  color: var(--color-teal);
}

.relation-label {
  font-weight: 600;
}

.relation-text {
  word-break: break-word;
  overflow-wrap: anywhere;
}

.source-card-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  border-top: 1px dashed var(--color-border);
  padding-top: 0.75rem;
}

.btn-sm {
  min-height: 36px;
  padding: 0.35rem 0.75rem;
  font-size: 0.8125rem;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.loading-state,
.empty-results {
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
  max-width: 440px;
  line-height: 1.5;
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Responsive */
@media (max-width: 768px) {
  .search-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .search-form-card {
    padding: 1rem 0.875rem;
  }

  .query-input-wrap {
    min-width: 0;
    width: 100%;
    flex: 1 1 100%;
  }

  .search-submit-btn {
    width: 100%;
    min-height: 44px;
    justify-content: center;
  }

  .filters-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.75rem;
  }

  .source-cards-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 1rem;
  }

  .source-card {
    padding: 1rem 0.875rem;
  }

  .source-card-footer {
    flex-wrap: wrap;
    justify-content: stretch;
  }

  .source-card-footer .btn {
    flex: 1 1 120px;
    justify-content: center;
    min-height: 40px;
  }
}
</style>
