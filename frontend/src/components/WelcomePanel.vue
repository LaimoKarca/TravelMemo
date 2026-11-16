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
        <span v-if="loggingOut" class="spinner-small" aria-hidden="true"></span>
        <span>{{ loggingOut ? '登出中...' : '登出手記' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.welcome-panel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.welcome-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.user-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: rgba(23, 107, 104, 0.12);
  color: var(--color-teal);
  flex-shrink: 0;
}

.welcome-title {
  font-size: 1.375rem;
  font-weight: 600;
  color: var(--color-ink);
  line-height: 1.2;
}

.user-email {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  word-break: break-all;
  margin-top: 0.25rem;
}

.status-card {
  background-color: #f7fbfc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.status-card-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.status-pill {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-teal);
  background-color: rgba(23, 107, 104, 0.1);
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
  letter-spacing: 0.05em;
}

.status-card-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-ink);
}

.status-card-desc {
  font-size: 0.9375rem;
  color: var(--color-subtle);
  line-height: 1.5;
}

.roadmap-notice {
  display: flex;
  gap: 0.75rem;
  background-color: #fff9e6;
  border: 1px solid #fae8a8;
  border-radius: var(--radius-sm);
  padding: 0.875rem 1rem;
  color: #705510;
  font-size: 0.875rem;
  line-height: 1.5;
  margin-top: 0.5rem;
}

.notice-icon {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.session-info {
  border-top: 1px dashed var(--color-border);
  padding-top: 1rem;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.info-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.info-row dt {
  color: var(--color-subtle);
}

.info-row dd {
  font-weight: 500;
  color: var(--color-ink);
  text-align: right;
}

.font-mono {
  font-family: var(--font-mono);
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.5rem;
}

.logout-btn {
  min-width: 120px;
}

.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(23, 107, 104, 0.3);
  border-top-color: var(--color-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
