<script setup lang="ts">
import { watch, onBeforeUnmount } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'

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

<style scoped src="./StatusAlert.css"></style>
