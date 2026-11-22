<script setup lang="ts">
import { computed, ref } from 'vue'
import { getTimezoneOptions } from '@/utils/timezones'

const props = defineProps<{ id: string; referenceDate?: string; disabled?: boolean }>()
const value = defineModel<string>({ required: true })
const open = ref(false)
const query = ref('')
const highlighted = ref(-1)
const listId = computed(() => `${props.id}-options`)
const options = computed(() => open.value ? getTimezoneOptions(props.referenceDate, 'zh-TW', query.value, 10) : [])
const expanded = computed(() => open.value && options.value.length > 0)

function optionId(index: number) { return `${listId.value}-${index}` }
function show() {
  query.value = ''
  highlighted.value = -1
  open.value = true
}
function input(event: Event) {
  if ((event as InputEvent).isComposing) return
  const typed = (event.target as HTMLInputElement).value
  value.value = typed
  query.value = typed
  highlighted.value = -1
  open.value = true
}
function close() {
  open.value = false
  highlighted.value = -1
}
function choose(index: number) {
  value.value = options.value[index].value
  close()
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) show()
    const size = options.value.length
    if (!size) return
    const direction = event.key === 'ArrowDown' ? 1 : -1
    highlighted.value = highlighted.value < 0 ? (direction > 0 ? 0 : size - 1) : (highlighted.value + direction + size) % size
    document.getElementById(optionId(highlighted.value))?.scrollIntoView?.({ block: 'nearest' })
  } else if (event.key === 'Enter' && expanded.value && highlighted.value >= 0) {
    event.preventDefault()
    choose(highlighted.value)
  } else if (event.key === 'Escape' && expanded.value) {
    event.preventDefault()
    event.stopPropagation()
    close()
  }
}
</script>

<template>
  <div class="timezone-picker">
    <input :id="id" :value="value" class="form-input" type="text" role="combobox"
      :disabled="disabled" :aria-expanded="expanded" :aria-controls="expanded ? listId : undefined"
      aria-autocomplete="list" :aria-activedescendant="expanded && highlighted >= 0 ? optionId(highlighted) : undefined"
      placeholder="搜尋地區或輸入 UTC 時差" autocomplete="off" autocorrect="off" autocapitalize="off" :spellcheck="false"
      @focus="show" @click="!open && show()" @input="input" @compositionend="input" @blur="close" @keydown="keydown" />
    <ul v-if="expanded" :id="listId" class="timezone-options" role="listbox" aria-label="時區建議">
      <li v-for="(option, index) in options" :id="optionId(index)" :key="option.value"
        role="option" :aria-selected="index === highlighted" @mousedown.prevent @click="choose(index)">{{ option.label }}</li>
    </ul>
  </div>
</template>

<style scoped src="./TimezoneInput.css"></style>
