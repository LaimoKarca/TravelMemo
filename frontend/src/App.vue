<script setup lang="ts">
import { ref, onMounted } from 'vue'
import BrandHeader from '@/features/auth/BrandHeader.vue'
import RouteMotif from '@/features/auth/RouteMotif.vue'
import LoginForm from '@/features/auth/LoginForm.vue'
import OtpForm from '@/features/auth/OtpForm.vue'
import TripWorkspace from '@/app/workspace/TripWorkspace.vue'
import StatusAlert from '@/components/ui/StatusAlert.vue'
import {
  requestCode,
  verifyCode,
  getMe,
  logout as apiLogout,
  setUnauthorizedHandler,
  ApiError
} from '@/api/auth'
import type { User } from '@/types/auth'

type AuthStep = 'loading_session' | 'email' | 'otp' | 'welcome'

const currentStep = ref<AuthStep>('loading_session')
const user = ref<User | null>(null)
const email = ref('')
const retryAfter = ref(60)
const otpForm = ref<InstanceType<typeof OtpForm> | null>(null)

// Alert status
const alertMessage = ref('')
const alertType = ref<'error' | 'success' | 'info'>('info')

// Action loading states
const requestingCode = ref(false)
const verifyingCode = ref(false)
const resendingCode = ref(false)
const loggingOut = ref(false)

function setAlert(message: string, type: 'error' | 'success' | 'info' = 'info') {
  alertMessage.value = message
  alertType.value = type
}

function clearAlert() {
  alertMessage.value = ''
}

// Check session on page load
onMounted(async () => {
  setUnauthorizedHandler(() => {
    // Only reset session if user was actually signed in (welcome step)
    if (currentStep.value === 'welcome' && user.value) {
      user.value = null
      currentStep.value = 'email'
      setAlert('您的登入狀態已過期，請重新登入。', 'info')
    }
  })

  try {
    const session = await getMe()
    if (session && session.user) {
      user.value = session.user
      currentStep.value = 'welcome'
    } else {
      currentStep.value = 'email'
    }
  } catch (err) {
    currentStep.value = 'email'
  }
})

// Step 1: Submit email to request OTP
async function handleRequestCode(targetEmail: string) {
  clearAlert()
  requestingCode.value = true
  email.value = targetEmail

  try {
    const res = await requestCode(targetEmail)
    retryAfter.value = res.retry_after || 60
    currentStep.value = 'otp'
    setAlert(res.message || '驗證碼已寄出，請查閱您的電子信箱。', 'success')
  } catch (err: any) {
    const msg = err instanceof ApiError ? err.detail : '索取驗證碼失敗，請稍後再試。'
    setAlert(msg, 'error')
  } finally {
    requestingCode.value = false
  }
}

// Resend OTP
async function handleResendCode() {
  clearAlert()
  resendingCode.value = true

  try {
    const res = await requestCode(email.value)
    retryAfter.value = res.retry_after || 60
    otpForm.value?.resetTimer(retryAfter.value)
    setAlert('若此信箱符合登入資格，將會收到新的驗證碼。', 'success')
  } catch (err: any) {
    const msg = err instanceof ApiError ? err.detail : '重新索取驗證碼失敗，請稍後再試。'
    setAlert(msg, 'error')
  } finally {
    resendingCode.value = false
  }
}

// Step 2: Verify OTP
async function handleVerifyCode(code: string) {
  clearAlert()
  verifyingCode.value = true

  try {
    const res = await verifyCode(email.value, code)
    user.value = res.user
    currentStep.value = 'welcome'
    clearAlert()
  } catch (err: any) {
    const msg = err instanceof ApiError ? err.detail : '驗證碼無效或已過期，請重新輸入。'
    setAlert(msg, 'error')
  } finally {
    verifyingCode.value = false
  }
}

// Return to email step
function handleBackToEmail() {
  clearAlert()
  currentStep.value = 'email'
}

// Logout
async function handleLogout() {
  clearAlert()
  loggingOut.value = true

  try {
    await apiLogout()
    user.value = null
    currentStep.value = 'email'
    setAlert('您已安全登出。', 'info')
  } catch (err: any) {
    const msg = err instanceof ApiError ? err.detail : '登出過程中發生問題，已清除本機會話。'
    if (err instanceof ApiError && err.status === 401) {
      user.value = null
      currentStep.value = 'email'
    }
    setAlert(msg, 'error')
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <main class="app-layout" :class="{ 'is-workspace-layout': currentStep === 'welcome' }">
    <!-- Signed-in Workspace: Fills viewport fluidly without card nesting -->
    <template v-if="currentStep === 'welcome' && user">
      <TripWorkspace
        :key="user.id"
        :user="user"
        :logging-out="loggingOut"
        @logout="handleLogout"
      />
    </template>

    <!-- Signed-out Auth: Full-bleed two-column layout with simple divider, no card/shadow -->
    <div v-else class="auth-fullbleed">
      <!-- Left: Route artwork with travel waypoint visual language -->
      <RouteMotif class="auth-motif" />

      <!-- Right: Auth form panel -->
      <section class="auth-main">
        <div class="auth-content">
          <BrandHeader />

          <StatusAlert v-if="alertMessage" :message="alertMessage" :type="alertType" />

          <div v-if="currentStep === 'loading_session'" class="loading-state" role="status" aria-live="polite">
            <div class="page-spinner ui-spinner ui-spinner--page" aria-hidden="true"></div>
            <p class="loading-text">正在確認登入狀態...</p>
          </div>

          <LoginForm
            v-else-if="currentStep === 'email'"
            :initial-email="email"
            :loading="requestingCode"
            @submit="handleRequestCode"
          />

          <OtpForm
            ref="otpForm"
            v-else-if="currentStep === 'otp'"
            :email="email"
            :retry-after="retryAfter"
            :loading="verifyingCode"
            :resending="resendingCode"
            @verify="handleVerifyCode"
            @resend="handleResendCode"
            @back="handleBackToEmail"
          />
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped src="./App.css"></style>
