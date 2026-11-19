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
  <Teleport to="body"><div v-if="busy" ref="overlay" class="polish-mask" role="status" aria-live="polite" aria-busy="true" tabindex="-1" @keydown.stop.prevent><div class="polish-progress"><span class="polish-spinner" aria-hidden="true"></span><span>正在潤飾…</span></div></div></Teleport>
</template>
<style scoped>
.journal-note { position: relative; min-width: 0; border: 0; border-top: 1px solid var(--color-border); padding: 1rem 0 0; margin: 0; }
legend { padding: 0 2.6rem 0 0; font-size: .875rem; font-weight: 600; color: var(--color-maple); }
textarea { width: 100%; resize: vertical; min-height: 100px; }
.polish-button { position: absolute; right: 0; top: -1.75rem; background: var(--color-paper); color: var(--color-maple); }
.polish-preview { margin-top: .75rem; padding: .75rem 0 .25rem; border-top: 1px dashed var(--color-border); color: var(--color-ink); line-height: 1.8; }
.polish-preview p { white-space: pre-wrap; margin: .65rem 0 0; }
.preview-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; color: var(--color-subtle); font-size: .8rem; }
.note-actions { display: flex; align-items: center; gap: .75rem; }
.discard-polish { border: 0; background: none; color: var(--color-subtle); cursor: pointer; padding: .4rem 0; font: inherit; }
.apply-polish { min-height: 34px; padding: .35rem .7rem; font-size: .8rem; gap: .35rem; }
.polish-mask { position: fixed; inset: 0; z-index: 3000; background: #453a324d; backdrop-filter: blur(3px); display: grid; place-items: center; outline: none; }
.polish-progress { display: flex; align-items: center; gap: 1rem; padding: 1.4rem 1.8rem; background: var(--color-paper); border-radius: 18px; box-shadow: 0 12px 40px #453a3220; color: var(--color-ink); }
.polish-spinner { width: 28px; height: 28px; border: 3px solid var(--color-border-light); border-top-color: var(--color-maple); border-radius: 50%; animation: polish-turn .85s linear infinite; }
@keyframes polish-turn { to { transform: rotate(360deg); } }
.note-error { color: var(--color-error-text); font-size: .875rem; }
.undo-note { align-self: start; font-size: .8rem; margin-top: .4rem; }
.spinning { animation: breathe 1s ease-in-out infinite alternate; }
@keyframes breathe { to { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .spinning { animation: none; } }
</style>
