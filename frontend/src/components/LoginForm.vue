<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  initialEmail?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'submit', email: string): void
}>()

const email = ref(props.initialEmail || '')

function handleSubmit() {
  const trimmed = email.value.trim()
  if (!trimmed || props.loading) return
  emit('submit', trimmed)
}
</script>

<template>
  <form class="login-form" @submit.prevent="handleSubmit" novalidate>
    <div class="form-intro">
      <h2 class="form-title">旅人登入</h2>
      <p class="form-desc">
        輸入信箱，取得登入驗證碼。
      </p>
    </div>

    <div class="field-group">
      <label for="email-input" class="field-label">
        電子信箱 <span class="required-indicator" aria-hidden="true">*</span>
      </label>
      <input
        id="email-input"
        v-model="email"
        type="email"
        required
        autocomplete="email"
        placeholder="your-name@example.com"
        class="form-input"
        :disabled="loading"
        aria-required="true"
        aria-describedby="email-hint"
      />
      <p id="email-hint" class="field-hint">
        請使用允許登入的信箱
      </p>
    </div>

    <button
      type="submit"
      class="btn btn-primary submit-btn"
      :disabled="loading || !email.trim()"
    >
      <span v-if="loading" class="spinner ui-spinner ui-spinner--auth" aria-hidden="true"></span>
      <span>{{ loading ? '寄送驗證碼中...' : '取得驗證碼' }}</span>
    </button>
  </form>
</template>

<style scoped src="../assets/styles/components/LoginForm.css"></style>
