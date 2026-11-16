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
        輸入您的電子信箱，系統將寄送一次性六位數驗證碼至信箱。無需記憶密碼。
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
        請輸入有效的電子信箱以接收登入驗證碼
      </p>
    </div>

    <button
      type="submit"
      class="btn btn-primary submit-btn"
      :disabled="loading || !email.trim()"
    >
      <span v-if="loading" class="spinner" aria-hidden="true"></span>
      <span>{{ loading ? '寄送驗證碼中...' : '取得驗證碼' }}</span>
    </button>
  </form>
</template>

<style scoped>
.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.form-intro {
  margin-bottom: 0.5rem;
}

.form-title {
  font-size: 1.5rem;
  color: var(--color-ink);
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.form-desc {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  line-height: 1.6;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field-label {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-ink);
}

.required-indicator {
  color: var(--color-error-text);
}

.field-hint {
  font-size: 0.8125rem;
  color: var(--color-subtle);
}

.submit-btn {
  width: 100%;
  margin-top: 0.5rem;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
