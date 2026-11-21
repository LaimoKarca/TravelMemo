<script setup lang="ts">
import { watch, ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    title: string
    message: string
    confirmText?: string
    cancelText?: string
    loading?: boolean
    danger?: boolean
    confirmationMode?: 'none' | 'keyword' | 'name'
    confirmationName?: string
    targetKey?: string
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
const confirmationInput = ref('')
const submitted = ref(false)
const canConfirm = computed(() => {
  const input = confirmationInput.value.trim()
  if (props.confirmationMode === 'keyword') return input === '刪除' || input.toUpperCase() === 'DELETE'
  if (props.confirmationMode === 'name') return !!props.confirmationName?.trim() && input === props.confirmationName.trim()
  return true
})
function handleConfirm() {
  if (!props.visible || props.loading || submitted.value || !canConfirm.value) return
  submitted.value = true
  emit('confirm')
}
function handleCancel() {
  if (props.loading || submitted.value) return
  emit('cancel')
}
watch(() => [props.visible, props.targetKey, props.title, props.message, props.confirmationMode, props.confirmationName], () => {
  confirmationInput.value = ''
  submitted.value = false
  if (props.visible) nextTick(() => dialogRef.value?.querySelector<HTMLElement>('.cancel-action')?.focus())
})
watch(() => props.loading, (value, previous) => { if (previous && !value) submitted.value = false })

const FOCUSABLE_SELECTOR = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function handleKeyDown(event: KeyboardEvent) {
  if (!props.visible || !dialogRef.value) return

  if (event.key === 'Escape') {
    event.preventDefault()
    handleCancel()
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
    @click.self="handleCancel"
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
        <label v-if="confirmationMode && confirmationMode !== 'none'" class="confirmation-input-label">
          <span>{{ confirmationMode === 'name' ? '輸入完整手記名稱' : '輸入 DELETE 或「刪除」' }}</span>
          <input v-model="confirmationInput" class="form-input" type="text" :aria-label="confirmationMode === 'name' ? '輸入完整手記名稱' : '輸入 DELETE 或刪除'" :maxlength="confirmationMode === 'name' ? 200 : 20" autocomplete="off" autocapitalize="off" :spellcheck="false" :disabled="loading || submitted" @keydown.enter.prevent="!$event.isComposing && handleConfirm()" />
        </label>
      </div>

      <footer class="dialog-actions">
        <button
          v-for="action in ['cancel', 'confirm']"
          :key="action"
          type="button"
          class="btn"
          :class="action === 'cancel' ? 'btn-secondary cancel-action' : danger ? 'btn-danger' : 'btn-primary'"
          :disabled="loading || (action === 'confirm' && (submitted || !canConfirm))"
          @click="action === 'cancel' ? handleCancel() : handleConfirm()"
        >
          <span v-if="action === 'confirm' && loading" class="spinner-small ui-spinner ui-spinner--on-primary" aria-hidden="true"></span>
          <span>{{ action === 'cancel' ? cancelText : loading ? '處理中...' : confirmText }}</span>
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped src="../assets/styles/components/ConfirmDialog.css"></style>
