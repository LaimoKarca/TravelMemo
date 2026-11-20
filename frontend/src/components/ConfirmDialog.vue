<script setup lang="ts">
import { watch, ref, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    title: string
    message: string
    confirmText?: string
    cancelText?: string
    loading?: boolean
    danger?: boolean
    confirmFirst?: boolean
  }>(),
  {
    confirmText: '確定',
    cancelText: '取消',
    loading: false,
    danger: true
  }
)

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const dialogRef = ref<HTMLElement | null>(null)
const launcherRef = ref<HTMLElement | null>(null)

const FOCUSABLE_SELECTOR = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

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
      nextTick(() => {
        dialogRef.value?.querySelector<HTMLElement>('.cancel-action')?.focus()
      })
    } else if (oldVal) {
      nextTick(() => {
        launcherRef.value?.focus()
      })
    }
  },
  { immediate: true }
)

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
    class="dialog-backdrop confirmation-backdrop"
    role="presentation"
    @click.self="emit('cancel')"
  >
    <div
      ref="dialogRef"
      class="dialog-card"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      tabindex="-1"
    >
      <header class="dialog-header">
        <div class="warning-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </div>
        <h3 class="dialog-title">{{ title }}</h3>
      </header>

      <div class="dialog-body">
        <p class="dialog-message">{{ message }}</p>
      </div>

      <footer class="dialog-actions">
        <button
          v-for="action in (confirmFirst ? ['confirm', 'cancel'] : ['cancel', 'confirm'])"
          :key="action"
          type="button"
          class="btn"
          :class="action === 'cancel' ? 'btn-secondary cancel-action' : danger ? 'btn-danger' : 'btn-primary'"
          :disabled="loading"
          @click="action === 'cancel' ? emit('cancel') : emit('confirm')"
        >
          <span v-if="action === 'confirm' && loading" class="spinner-small" aria-hidden="true"></span>
          <span>{{ action === 'cancel' ? cancelText : loading ? '處理中...' : confirmText }}</span>
        </button>
      </footer>
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
  padding: 1rem;
  z-index: 2000;
}

.dialog-card {
  width: 100%;
  max-width: 440px;
  background-color: var(--color-paper);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.dialog-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.warning-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-error-bg);
  color: var(--color-error-text);
  flex-shrink: 0;
}

.dialog-title {
  font-size: 1.125rem;
  font-weight: 700;
  color: var(--color-ink);
  line-height: 1.3;
}

.dialog-body {
  font-size: 0.875rem;
  color: var(--color-subtle);
  line-height: 1.5;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.btn-danger {
  background-color: var(--color-error-text);
  color: #FFFFFF;
}

.btn-danger:hover:not(:disabled) {
  background-color: #A01C00;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #FFFFFF;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
