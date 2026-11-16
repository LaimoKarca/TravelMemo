<script setup lang="ts">
defineProps<{
  type?: 'error' | 'success' | 'info'
  message: string
}>()
</script>

<template>
  <div
    v-if="message"
    class="status-alert"
    :class="`status-alert--${type || 'info'}`"
    role="status"
    aria-live="polite"
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
  </div>
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
}

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
