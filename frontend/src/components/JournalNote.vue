<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { request } from '../api/auth'
import AppIcon from './AppIcon.vue'
const props = defineProps<{ modelValue: string; kind: 'trip' | 'event'; label: string; id: string; placeholder?: string; disabled?: boolean; maxlength?: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()
const busy = ref(false)
const proposal = ref('')
const original = ref('')
const undo = ref<string | null>(null)
const error = ref('')
const overlay = ref<HTMLElement | null>(null)
async function polish() {
  if (!props.modelValue.trim() || busy.value) return
  original.value = props.modelValue
  error.value = ''
  proposal.value = ''
  busy.value = true
  const previousFocus = document.activeElement as HTMLElement | null
  await nextTick()
  overlay.value?.focus()
  try {
    const result = await request<{ text: string }>('/writing/polish', { method: 'POST', body: JSON.stringify({ text: original.value, kind: props.kind }) })
    proposal.value = result.text
  } catch { error.value = '暫時無法潤飾，原文已保留。' }
  finally { busy.value = false; await nextTick(); previousFocus?.focus() }
}
function apply() {
  if (props.modelValue !== original.value) { error.value = '原文已修改，請重新潤飾。'; proposal.value = ''; return }
  undo.value = props.modelValue
  emit('update:modelValue', proposal.value)
  proposal.value = ''
}
</script>
<template>
  <fieldset class="journal-note">
    <legend><label :for="id">{{ label }}</label></legend>
    <button type="button" class="icon-button polish-button" :disabled="disabled || busy || !modelValue.trim() || modelValue.length > 10000" :aria-label="busy ? '潤飾中' : 'AI 潤飾文字'" :title="modelValue.length > 10000 ? '請縮短至 10,000 字以內再潤飾' : 'AI 潤飾文字'" @click="polish"><AppIcon name="wand" :class="{ spinning: busy }" /></button>
    <textarea :id="id" :value="modelValue" :placeholder="placeholder" :maxlength="maxlength || 10000" :disabled="disabled" class="form-input" rows="4" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" />
    <p v-if="error" class="note-error" role="alert">{{ error }}</p>
    <div v-if="proposal" class="polish-preview" aria-live="polite"><div class="preview-toolbar"><span>潤飾建議</span><div class="note-actions"><button type="button" class="discard-polish" :disabled="disabled" @click="proposal = ''">保留原文</button><button type="button" class="btn btn-primary apply-polish" :disabled="disabled" @click="apply"><span aria-hidden="true">✓</span> 套用潤飾</button></div></div><p>{{ proposal }}</p></div>
    <button v-else-if="undo !== null" type="button" class="btn-link undo-note" :disabled="disabled" @click="emit('update:modelValue', undo!); undo = null">復原原文</button>
  </fieldset>
  <Teleport to="body"><div v-if="busy" ref="overlay" class="polish-mask" role="status" aria-live="polite" aria-busy="true" tabindex="-1" @keydown.stop.prevent><div class="polish-progress"><span class="polish-spinner ui-spinner" aria-hidden="true"></span><span>正在潤飾…</span></div></div></Teleport>
</template>
<style scoped src="../assets/styles/components/JournalNote.css"></style>
