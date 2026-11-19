<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import JournalNote from './JournalNote.vue'
import type { Trip, CreateTripPayload, UpdateTripPayload } from '../types/travel'
import { getTimezoneOptions, normalizeTimezoneInput } from '../utils/timezones'

const props = withDefaults(
  defineProps<{
    visible: boolean
    trip?: Trip | null
    loading?: boolean
    errorMessage?: string
    hasConflict?: boolean
  }>(),
  {
    trip: null,
    loading: false,
    errorMessage: '',
    hasConflict: false
  }
)

const emit = defineEmits<{
  (e: 'submit', payload: CreateTripPayload | UpdateTripPayload): void
  (e: 'refresh'): void
  (e: 'cancel'): void
}>()

const dialogRef = ref<HTMLElement | null>(null)
const launcherRef = ref<HTMLElement | null>(null)

const name = ref('')
const startDate = ref('')
const endDate = ref('')
const timezone = ref('Asia/Taipei')
const description = ref('')
const clientValidationError = ref('')

const isEdit = computed(() => !!props.trip)
const dialogTitle = computed(() => (isEdit.value ? '編輯旅行手記' : '新增旅行手記'))

const timezoneOptions = computed(() => {
  return getTimezoneOptions(startDate.value || undefined)
})

const FOCUSABLE_SELECTOR = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function resetFormFromProps() {
  clientValidationError.value = ''
  if (props.trip) {
    name.value = props.trip.name
    startDate.value = props.trip.start_date
    endDate.value = props.trip.end_date
    timezone.value = props.trip.timezone || 'Asia/Taipei'
    description.value = props.trip.description || ''
  } else {
    name.value = ''
    const today = new Date().toLocaleDateString('en-CA')
    startDate.value = today
    endDate.value = new Date(new Date(today).getTime() + 86400000).toISOString().slice(0, 10)
    timezone.value = 'Asia/Taipei'
    description.value = ''
  }
}

function handleKeyDown(event: KeyboardEvent) {
  if (!props.visible || !dialogRef.value) return

  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
    return
  }

  if (event.key === 'Tab') {
    const focusables = Array.from(
      dialogRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    )
    if (focusables.length === 0) {
      event.preventDefault()
      return
    }

    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const current = document.activeElement

    if (event.shiftKey) {
      if (current === first || !dialogRef.value.contains(current)) {
        event.preventDefault()
        last.focus()
      }
    } else {
      if (current === last || !dialogRef.value.contains(current)) {
        event.preventDefault()
        first.focus()
      }
    }
  }
}

watch(
  () => props.visible,
  (val, oldVal) => {
    if (val) {
      launcherRef.value = document.activeElement as HTMLElement | null
      if (!props.hasConflict) {
        resetFormFromProps()
      }
      nextTick(() => {
        const firstInput = dialogRef.value?.querySelector<HTMLElement>('#trip-name-input')
        const firstFocusable = dialogRef.value?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
        ;(firstInput || firstFocusable)?.focus()
      })
    } else if (oldVal) {
      nextTick(() => {
        launcherRef.value?.focus()
      })
    }
  },
  { immediate: true }
)

watch(
  () => props.trip,
  () => {
    resetFormFromProps()
  }
)

watch(startDate, (start) => {
  if (start && endDate.value < start) endDate.value = start
})

function handleSubmit() {
  clientValidationError.value = ''

  const trimmedName = name.value.trim()
  if (!trimmedName) {
    clientValidationError.value = '請填寫旅程名稱（1 至 200 字元）。'
    return
  }
  if (trimmedName.length > 200) {
    clientValidationError.value = '旅程名稱不可超過 200 字元。'
    return
  }
  if (!startDate.value) {
    clientValidationError.value = '請選擇開始日期。'
    return
  }
  if (!endDate.value) {
    clientValidationError.value = '請選擇結束日期。'
    return
  }
  if (startDate.value > endDate.value) {
    clientValidationError.value = '結束日期不得早於開始日期。'
    return
  }
  if (description.value.length > 10000) {
    clientValidationError.value = '旅程隨筆不可超過 10,000 字元。'
    return
  }

  const rawTimezone = timezone.value.trim()
  const normalized = normalizeTimezoneInput(rawTimezone)
  const finalTimezone = (normalized && normalized.trim()) || rawTimezone || 'Asia/Taipei'

  if (isEdit.value && props.trip) {
    const payload: UpdateTripPayload = {
      name: trimmedName,
      start_date: startDate.value,
      end_date: endDate.value,
      timezone: finalTimezone,
      description: description.value,
      version: props.trip.version
    }
    emit('submit', payload)
  } else {
    const payload: CreateTripPayload = {
      name: trimmedName,
      start_date: startDate.value,
      end_date: endDate.value,
      timezone: finalTimezone,
      description: description.value
    }
    emit('submit', payload)
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  if (props.visible) {
    launcherRef.value?.focus()
  }
})
</script>

<template>
  <div
    v-if="visible"
    class="dialog-backdrop"
    role="presentation"
    @click.self="emit('cancel')"
  >
    <div
      ref="dialogRef"
      class="dialog-card"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="'trip-dialog-title'"
      tabindex="-1"
    >
      <header class="dialog-header">
        <h3 id="trip-dialog-title" class="dialog-title">{{ dialogTitle }}</h3>
        <button
          type="button"
          class="close-button"
          aria-label="關閉視窗"
          @click="emit('cancel')"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      <!-- Conflict Notice (409) -->
      <div v-if="hasConflict" class="conflict-banner" role="alert">
        <div class="conflict-content">
          <p class="conflict-text">
            <strong>紀錄更新提示：</strong>
            此旅程資料已在其他地方更新。您剛才輸入的內容已完整保留，您可以點擊「重新載入」取得最新紀錄，或檢查後再次儲存。
          </p>
          <button
            type="button"
            class="btn btn-secondary conflict-refresh-btn"
            @click="emit('refresh')"
          >
            重新載入最新手記
          </button>
        </div>
      </div>

      <!-- General or Client Error Notice -->
      <div v-if="clientValidationError || errorMessage" class="error-banner" role="alert">
        {{ clientValidationError || errorMessage }}
      </div>

      <form class="dialog-form" @submit.prevent="handleSubmit">
        <div class="form-group">
          <label for="trip-name-input" class="form-label">
            旅程名稱 <span class="required-star">*</span>
          </label>
          <input
            id="trip-name-input"
            v-model="name"
            type="text"
            class="form-input"
            placeholder="例如：2026 冬季京都漫步"
            maxlength="200"
            required
            :disabled="loading"
          />
        </div>

        <div class="form-row">
          <div class="form-group flex-1">
            <label for="trip-start-date" class="form-label">
              開始日期 <span class="required-star">*</span>
            </label>
            <input
              id="trip-start-date"
              v-model="startDate"
              type="date"
              class="form-input"
              required
              :disabled="loading"
            />
          </div>

          <div class="form-group flex-1">
            <label for="trip-end-date" class="form-label">
              結束日期 <span class="required-star">*</span>
            </label>
            <input
              id="trip-end-date"
              v-model="endDate"
              type="date"
              class="form-input"
              :min="startDate"
              required
              :disabled="loading"
            />
          </div>
        </div>

        <div class="form-group">
          <label for="trip-timezone" class="form-label">
            時區
          </label>
          <input
            id="trip-timezone"
            v-model="timezone"
            type="text"
            list="trip-timezone-list"
            class="form-input"
            placeholder="例如：Asia/Taipei 或 UTC+08:00"
            autocomplete="off"
            :disabled="loading"
          />
          <datalist id="trip-timezone-list">
            <option
              v-for="opt in timezoneOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            >
              {{ opt.label }}
            </option>
          </datalist>
        </div>

        <JournalNote id="trip-description" v-model="description" kind="trip" label="旅行隨筆／備忘回憶" placeholder="記下旅程的初衷、夥伴或沿途感受…" :disabled="loading" />

        <footer class="dialog-footer">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="loading"
            @click="emit('cancel')"
          >
            取消
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="loading"
          >
            <span v-if="loading" class="spinner-small" aria-hidden="true"></span>
            <span>{{ loading ? '儲存中...' : (isEdit ? '儲存修改' : '建立旅程') }}</span>
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(69, 58, 50, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
  z-index: 1000;
  overflow-y: auto;
}

.dialog-card {
  width: 100%;
  max-width: 540px;
  background-color: var(--color-paper);
  border-radius: var(--radius-lg);
  box-shadow: 0 16px 36px rgba(69, 58, 50, 0.15);
  border: 1px solid var(--color-border);
  padding: 1.75rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dialog-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-ink);
}

.close-button {
  background: transparent;
  border: none;
  color: var(--color-subtle);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.375rem;
  border-radius: var(--radius-sm);
}

.close-button:hover {
  background-color: var(--color-maple-subtle);
  color: var(--color-ink);
}

.conflict-banner {
  background-color: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  padding: 0.875rem 1rem;
  color: var(--color-warning-text);
  font-size: 0.875rem;
  line-height: 1.5;
}

.conflict-content {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.conflict-refresh-btn {
  align-self: flex-start;
  min-height: 36px;
  padding: 0.35rem 0.875rem;
  font-size: 0.875rem;
  background-color: var(--color-paper);
  border-color: var(--color-border);
}

.error-banner {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-text);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 1.125rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-row {
  display: flex;
  gap: 1rem;
}

.flex-1 {
  flex: 1;
}

.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-ink);
}

.required-star {
  color: var(--color-error-text);
}

.form-textarea {
  min-height: 90px;
  resize: vertical;
}

.form-select {
  cursor: pointer;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 600px) {
  .form-row {
    flex-direction: column;
    gap: 1.125rem;
  }
}
</style>
