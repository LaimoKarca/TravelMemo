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
      <span v-if="loading" class="spinner" aria-hidden="true"></span>
      <span>{{ loading ? '寄送驗證碼中...' : '取得驗證碼' }}</span>
    </button>
  </form>
</template>

<style scoped>
.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
}

.form-intro {
  margin-bottom: 0.25rem;
}

.form-title {
  font-size: 1.375rem;
  color: var(--color-ink);
  font-weight: 700;
  margin-bottom: 0.35rem;
}

.form-desc {
  font-size: 0.875rem;
  color: var(--color-subtle);
  line-height: 1.5;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.field-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-ink);
}

.required-indicator {
  color: var(--color-error-text);
}

.field-hint {
  font-size: 0.75rem;
  color: var(--color-subtle);
}

.submit-btn {
  width: 100%;
  margin-top: 0.25rem;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #FFFFFF;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
