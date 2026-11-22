<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'

defineProps<{ disabled?: boolean; below?: boolean }>()
const emit = defineEmits<{ camera: []; gallery: [] }>()
const menu = ref<HTMLDetailsElement | null>(null)

function close() {
  if (menu.value) menu.value.open = false
}

function closeOutside(event: Event) {
  if (event.type === 'focusin' && event.target instanceof HTMLInputElement && event.target.type === 'file' && event.target.getAttribute('aria-hidden') === 'true') return
  if (menu.value?.open && event.target instanceof Node && !menu.value.contains(event.target)) close()
}

function closeOnEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !menu.value?.open) return
  event.preventDefault()
  event.stopPropagation()
  close()
  menu.value.querySelector('summary')?.focus()
}

onMounted(() => {
  document.addEventListener('pointerdown', closeOutside)
  document.addEventListener('focusin', closeOutside)
  document.addEventListener('keydown', closeOnEscape, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOutside)
  document.removeEventListener('focusin', closeOutside)
  document.removeEventListener('keydown', closeOnEscape, true)
})
defineExpose({ close })
</script>

<template>
  <details ref="menu" class="photo-source-menu" :class="{ 'opens-below': below }">
    <summary class="icon-button" aria-label="加入圖片" title="加入圖片" :aria-disabled="disabled || undefined" @click="disabled && $event.preventDefault()">
      <AppIcon name="image" />
    </summary>
    <div class="photo-source-options">
      <button type="button" :disabled="disabled" @click="emit('camera')">拍照</button>
      <button type="button" :disabled="disabled" @click="emit('gallery')">從圖庫選取</button>
    </div>
  </details>
</template>

<style scoped src="./PhotoSourceMenu.css"></style>
