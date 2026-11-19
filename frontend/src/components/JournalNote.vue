<script setup lang="ts">
import { ref } from 'vue'
import { request } from '../api/auth'
import AppIcon from './AppIcon.vue'
const props = defineProps<{ modelValue: string; kind: 'trip' | 'event'; label: string; id: string; placeholder?: string; disabled?: boolean; maxlength?: number }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()
const busy = ref(false)
const proposal = ref('')
const original = ref('')
const undo = ref<string | null>(null)
const error = ref('')
async function polish() {
  if (!props.modelValue.trim() || busy.value) return
  original.value = props.modelValue
  error.value = ''
  proposal.value = ''
  busy.value = true
  try {
    const result = await request<{ text: string }>('/writing/polish', { method: 'POST', body: JSON.stringify({ text: original.value, kind: props.kind }) })
    proposal.value = result.text
  } catch { error.value = '暫時無法潤飾，原文已保留。' }
  finally { busy.value = false }
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
    <div v-if="proposal" class="polish-preview" aria-live="polite"><p>{{ proposal }}</p><div class="note-actions"><button type="button" class="btn btn-secondary" :disabled="disabled" @click="proposal = ''">保留原文</button><button type="button" class="btn btn-primary" :disabled="disabled" @click="apply">套用潤飾</button></div></div>
    <button v-else-if="undo !== null" type="button" class="btn-link undo-note" :disabled="disabled" @click="emit('update:modelValue', undo!); undo = null">復原原文</button>
  </fieldset>
</template>
<style scoped>
.journal-note { position: relative; min-width: 0; border: 0; border-top: 1px solid var(--color-border); padding: 1rem 0 0; margin: 0; }
legend { padding: 0 2.6rem 0 0; font-size: .875rem; font-weight: 600; color: var(--color-maple); }
textarea { width: 100%; resize: vertical; min-height: 100px; }
.polish-button { position: absolute; right: 0; top: -1.75rem; background: var(--color-paper); color: var(--color-maple); }
.polish-preview { padding: .75rem 0 0; color: var(--color-ink); white-space: pre-wrap; line-height: 1.8; }
.note-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: .75rem; }
.note-error { color: var(--color-error-text); font-size: .875rem; }
.undo-note { align-self: start; font-size: .8rem; margin-top: .4rem; }
.spinning { animation: breathe 1s ease-in-out infinite alternate; }
@keyframes breathe { to { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .spinning { animation: none; } }
</style>
