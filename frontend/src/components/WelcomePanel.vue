<script setup lang="ts">
import type { User } from '../types/auth'

defineProps<{
  user: User
  loggingOut?: boolean
}>()

const emit = defineEmits<{
  (e: 'logout'): void
}>()
</script>

<template>
  <div class="welcome-panel">
    <div class="welcome-header">
      <div class="user-badge" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </div>
      <div>
        <h2 class="welcome-title">歡迎回來，旅人</h2>
        <p class="user-email">{{ user.email }}</p>
      </div>
    </div>

    <!-- Phase 1 status message: journey management comes next -->
    <div class="status-card">
      <div class="status-card-header">
        <span class="status-pill">已登入</span>
        <h3 class="status-card-title">歡迎來到你的旅程手記</h3>
      </div>
      <p class="status-card-desc">
        你的信箱已完成驗證，下次回來時會自動恢復有效的登入狀態。
      </p>

      <div class="roadmap-notice">
        <div class="notice-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        </div>
        <div class="notice-content">
          <strong>接下來：</strong>
          <span>旅程管理將於下一階段開放，目前可使用信箱登入與登出。</span>
        </div>
      </div>
    </div>

    <div class="session-info">
      <dl class="info-list">
        <div class="info-row">
          <dt>帳號識別碼</dt>
          <dd class="font-mono">{{ user.id }}</dd>
        </div>
        <div class="info-row">
          <dt>驗證狀態</dt>
          <dd>已完成信箱驗證</dd>
        </div>
      </dl>
    </div>

    <div class="actions">
      <button
        type="button"
        class="btn btn-secondary logout-btn"
        :disabled="loggingOut"
        @click="emit('logout')"
      >
        <span v-if="loggingOut" class="spinner-small ui-spinner ui-spinner--maple" aria-hidden="true"></span>
        <span>{{ loggingOut ? '登出中...' : '登出手記' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped src="../assets/styles/components/WelcomePanel.css"></style>
