<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps<{
  email: string
  retryAfter: number
  loading?: boolean
  resending?: boolean
}>()

const emit = defineEmits<{
  (e: 'verify', code: string): void
  (e: 'resend'): void
  (e: 'back'): void
}>()

const code = ref('')
const otpInputRef = ref<HTMLInputElement | null>(null)
const countdown = ref(props.retryAfter || 60)
let timer: ReturnType<typeof setInterval> | null = null

function startCountdown(seconds: number) {
  if (timer) clearInterval(timer)
  countdown.value = seconds
  timer = setInterval(() => {
    if (countdown.value > 0) {
      countdown.value -= 1
    } else {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }, 1000)
}

onMounted(() => {
  startCountdown(props.retryAfter || 60)
  nextTick(() => {
    otpInputRef.value?.focus()
  })
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function handleVerify() {
  const trimmed = code.value.trim()
  if (!/^\d{6}$/.test(trimmed) || props.loading) return
  emit('verify', trimmed)
}

function handleResend() {
  if (countdown.value > 0 || props.resending || props.loading) return
  emit('resend')
}

function resetTimer(newSeconds: number) {
  startCountdown(newSeconds)
}

defineExpose({
  resetTimer,
  focusInput: () => otpInputRef.value?.focus()
})
</script>

<template>
  <form class="otp-form" @submit.prevent="handleVerify" novalidate>
    <div class="form-intro">
      <h2 class="form-title">輸入驗證碼</h2>
      <p class="form-desc">
        我們已寄送 6 位數驗證碼至：<br />
        <strong class="target-email">{{ email }}</strong>
      </p>
    </div>

    <div class="field-group">
      <label for="otp-input" class="field-label">
        6 位數驗證碼 <span class="required-indicator" aria-hidden="true">*</span>
      </label>
      <input
        id="otp-input"
        ref="otpInputRef"
        v-model="code"
        type="text"
        inputmode="numeric"
        pattern="[0-9]{6}"
        maxlength="6"
        autocomplete="one-time-code"
        placeholder="123456"
        class="form-input otp-input"
        :disabled="loading"
        aria-required="true"
        aria-describedby="otp-hint"
      />
      <p id="otp-hint" class="field-hint">
        請輸入郵件中的 6 位阿拉伯數字
      </p>
    </div>

    <button
      type="submit"
      class="btn btn-primary submit-btn"
      :disabled="loading || !/^\d{6}$/.test(code.trim())"
    >
      <span v-if="loading" class="spinner ui-spinner ui-spinner--auth" aria-hidden="true"></span>
      <span>{{ loading ? '驗證中...' : '驗證並進入手記' }}</span>
    </button>

    <div class="action-row">
      <button
        type="button"
        class="btn btn-secondary resend-btn"
        :disabled="countdown > 0 || resending || loading"
        @click="handleResend"
      >
        <span v-if="resending" class="spinner-small ui-spinner ui-spinner--maple" aria-hidden="true"></span>
        <span v-if="countdown > 0">重新寄送 ({{ countdown }}秒)</span>
        <span v-else>重新寄送驗證碼</span>
      </button>

      <button
        type="button"
        class="btn-link back-btn"
        :disabled="loading || resending"
        @click="emit('back')"
      >
        返回更換電子信箱
      </button>
    </div>
  </form>
</template>

<style scoped src="./OtpForm.css"></style>
