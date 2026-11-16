<script setup lang="ts">
import { ref, onMounted } from 'vue'
import BrandHeader from './components/BrandHeader.vue'
import RouteMotif from './components/RouteMotif.vue'
import LoginForm from './components/LoginForm.vue'
import OtpForm from './components/OtpForm.vue'
import TripWorkspace from './components/TripWorkspace.vue'
import StatusAlert from './components/StatusAlert.vue'
import {
  requestCode,
  verifyCode,
  getMe,
  logout as apiLogout,
  setUnauthorizedHandler,
  ApiError
} from './api/auth'
import type { User } from './types/auth'

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
    <div class="notebook-container" :class="{ 'is-workspace-container': currentStep === 'welcome' }">
      <!-- Left Column: Route-line motif & decorative waypoint illustration -->
      <RouteMotif v-if="currentStep !== 'welcome'" class="desktop-motif" />

      <!-- Right Column: Main Notebook Content -->
      <section class="notebook-content" :class="{ 'is-workspace-content': currentStep === 'welcome' }">
        <BrandHeader v-if="currentStep !== 'welcome'" />

        <StatusAlert v-if="currentStep !== 'welcome' && alertMessage" :message="alertMessage" :type="alertType" />

        <div v-if="currentStep === 'loading_session'" class="loading-state" role="status" aria-live="polite">
          <div class="page-spinner" aria-hidden="true"></div>
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
        <TripWorkspace
          v-else-if="currentStep === 'welcome' && user"
          :user="user"
          :logging-out="loggingOut"
          @logout="handleLogout"
        />
      </section>
    </div>
  </main>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
  background-color: var(--color-pale-blue);
}

.app-layout.is-workspace-layout {
  align-items: flex-start;
  padding: 2rem 1.5rem;
}

.notebook-container {
  display: grid;
  grid-template-columns: 320px 1fr;
  width: 100%;
  max-width: 960px;
  background-color: var(--color-paper);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-notebook);
  border: 1px solid var(--color-border);
  overflow: hidden;
  min-height: 540px;
  min-width: 0;
  box-sizing: border-box;
}

.notebook-container.is-workspace-container {
  grid-template-columns: 1fr;
  max-width: 1180px;
  min-height: 650px;
}

.notebook-content {
  padding: 2.5rem 2.5rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}

.notebook-content.is-workspace-content {
  padding: 2rem 2.25rem;
  justify-content: flex-start;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  gap: 1rem;
}

.page-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(23, 107, 104, 0.2);
  border-top-color: var(--color-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 0.9375rem;
  color: var(--color-subtle);
}

/* Responsive: Single column on phone / smaller screens */
@media (max-width: 768px) {
  .app-layout,
  .app-layout.is-workspace-layout {
    padding: 0.75rem 0.5rem;
    align-items: stretch;
  }

  .notebook-container,
  .notebook-container.is-workspace-container {
    grid-template-columns: minmax(0, 1fr);
    border-radius: var(--radius-md);
    min-height: auto;
    width: 100%;
    min-width: 0;
  }

  .desktop-motif {
    display: none;
  }

  .notebook-content,
  .notebook-content.is-workspace-content {
    padding: 1rem 0.75rem;
    width: 100%;
    min-width: 0;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
