<script setup lang="ts">
import { ref } from 'vue'
import { useDialogFocus } from './useDialogFocus'

const props = withDefaults(defineProps<{
  visible: boolean
  label?: string
  labelledBy?: string
  initialFocus?: string
  panelClass?: string
  busy?: boolean
  dismissOutside?: boolean
}>(), { dismissOutside: true })
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)

function close() {
  if (!props.busy) emit('close')
}

const { level, focusInitial } = useDialogFocus(() => props.visible, panel, { close, initial: () => props.initialFocus })
defineExpose({ focusInitial })
</script>

<template>
  <div
    v-if="visible"
    class="dialog-backdrop"
    :style="{ zIndex: level }"
    role="presentation"
    @click.self="dismissOutside && close()"
  >
    <div ref="panel" class="dialog-card" :class="panelClass" role="dialog" aria-modal="true" :aria-labelledby="labelledBy" :aria-label="label" tabindex="-1">
      <slot />
    </div>
  </div>
</template>

<style scoped src="./AppDialogFrame.css"></style>
