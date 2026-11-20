<script setup lang="ts">
import { watch, onBeforeUnmount } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps<{
  type?: 'error' | 'success' | 'info'
  message: string
  floating?: boolean
  noticeKey?: number
}>()
const emit = defineEmits<{ (e: 'dismiss'): void }>()
let timer: ReturnType<typeof setTimeout> | undefined
watch(() => [props.message, props.type, props.noticeKey, props.floating], () => {
  if (timer !== undefined) clearTimeout(timer)
  if (props.floating && props.message && props.type !== 'error') {
    timer = setTimeout(() => emit('dismiss'), 2000)
  }
}, { immediate: true })
onBeforeUnmount(() => { if (timer !== undefined) clearTimeout(timer) })
</script>

<template>
  <Teleport to="body" :disabled="!floating">
  <div
    v-if="message"
    class="status-alert"
    :class="[`status-alert--${type || 'info'}`, { 'workspace-notice': floating }]"
    :role="type === 'error' ? 'alert' : 'status'"
    :aria-live="type === 'error' ? 'assertive' : 'polite'"
  >
    <div class="alert-icon" aria-hidden="true">
      <svg v-if="type === 'error'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <svg v-else-if="type === 'success'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
        <polyline points="22 4 12 14.01 9 11.01" />
      </svg>
      <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    </div>
    <div class="alert-text">{{ message }}</div>
    <button v-if="floating" type="button" class="notice-close" aria-label="關閉通知" @click="emit('dismiss')"><AppIcon name="close" /></button>
  </div>
  </Teleport>
</template>

<style scoped>
.status-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border-radius: var(--radius-md);
  margin-bottom: 1.25rem;
  font-size: 0.9375rem;
  line-height: 1.5;
  border: 1px solid transparent;
}

.alert-icon {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.alert-text {
  flex-grow: 1;
  min-width: 0;
}

.workspace-notice {
  position: fixed;
  top: max(.75rem, env(safe-area-inset-top));
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  width: max-content;
  max-width: min(36rem, calc(100vw - 1.5rem));
  box-sizing: border-box;
  margin: 0;
  align-items: center;
  padding: .45rem .55rem .45rem .85rem;
  box-shadow: var(--shadow-md);
}
.notice-close { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 40px; width: 40px; height: 40px; border: 0; background: transparent; color: inherit; border-radius: var(--radius-sm); cursor: pointer; }
.notice-close:hover { background: rgba(69, 58, 50, .08); }

.status-alert--error {
  color: var(--color-error-text);
  background-color: var(--color-error-bg);
  border-color: var(--color-error-border);
}

.status-alert--success {
  color: var(--color-success-text);
  background-color: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.status-alert--info {
  color: var(--color-info-text);
  background-color: var(--color-info-bg);
  border-color: var(--color-info-border);
}
</style>
