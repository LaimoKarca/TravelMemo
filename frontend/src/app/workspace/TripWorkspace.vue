<script setup lang="ts">
import { ref, reactive, computed, nextTick } from 'vue'
import type { User } from '@/types/auth'
import type { EventDestination, TripListItem } from '@/types/travel'
import { createRecallState, type SearchItem, type SearchEvent } from '@/types/search'
import type { ChatWorkspaceState, Citation } from '@/types/conversation'
import StatusAlert from '@/components/ui/StatusAlert.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import BrandMark from '@/components/ui/BrandMark.vue'
import TravelDivider from '@/components/ui/TravelDivider.vue'
import TripJournal from '@/features/trips/TripJournal.vue'
import RecallSearch from '@/features/recall/RecallSearch.vue'
import SourceDetailModal from '@/features/recall/SourceDetailModal.vue'
import StandaloneFootprints from '@/features/footprints/StandaloneFootprints.vue'
import ConversationView from '@/features/chat/ConversationView.vue'
import { useTravelMotion } from './useTravelMotion'

const props = defineProps<{
  user: User
  loggingOut?: boolean
}>()

const emit = defineEmits<{
  (e: 'logout'): void
}>()

const { isTabWashing, triggerTabWash, handleActionClick } = useTravelMotion()
const recallState = reactive(createRecallState())
const chatWorkspace = reactive<ChatWorkspaceState>({ drafts: new Map(), conversations: [] })

// Workspace active tab navigation
type WorkspaceTab = 'trips' | 'footprints' | 'search' | 'chat'
const activeTab = ref<WorkspaceTab>('trips')

interface WorkspaceTabItem {
  id: WorkspaceTab
  label: string
  shortLabel: string
  tabId: string
  panelId: string
}

const TABS: WorkspaceTabItem[] = [
  { id: 'trips', label: '旅行手記', shortLabel: '手記', tabId: 'workspace-tab-trips', panelId: 'workspace-panel-trips' },
  { id: 'footprints', label: '日常足跡', shortLabel: '足跡', tabId: 'workspace-tab-footprints', panelId: 'workspace-panel-footprints' },
  { id: 'search', label: '回憶搜尋', shortLabel: '搜尋', tabId: 'workspace-tab-search', panelId: 'workspace-panel-search' },
  { id: 'chat', label: 'AI 助理', shortLabel: 'AI', tabId: 'workspace-tab-chat', panelId: 'workspace-panel-chat' }
]

const tabButtonRefs = ref<(HTMLButtonElement | null)[]>([])
function setTabRef(el: any, index: number) {
  tabButtonRefs.value[index] = el as HTMLButtonElement | null
}

function switchTab(tab: WorkspaceTab) {
  if (tab !== 'footprints') focusedStandaloneId.value = null
  if (tab === 'trips') {
    activeTab.value = tab
    backToTripList()
    triggerTabWash(450)
    return
  }
  if (activeTab.value !== tab) {
    activeTab.value = tab
    clearAlert()
    triggerTabWash(450)
  }
}

async function handleTabKeydown(e: KeyboardEvent, currentIndex: number) {
  let targetIndex = -1
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    targetIndex = (currentIndex + 1) % TABS.length
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    targetIndex = (currentIndex - 1 + TABS.length) % TABS.length
  } else if (e.key === 'Home') {
    targetIndex = 0
  } else if (e.key === 'End') {
    targetIndex = TABS.length - 1
  }

  if (targetIndex !== -1) {
    e.preventDefault()
    switchTab(TABS[targetIndex].id)
    await nextTick()
    tabButtonRefs.value[targetIndex]?.focus()
  }
}

// Source detail modal & timeline jump highlight
const showSourceModal = ref(false)
const sourceModalEventId = ref<string | null>(null)
const sourceModalInitialEvent = ref<SearchEvent | null>(null)
const focusedStandaloneId = ref<string | null>(null)

function handleViewEvent(event: SearchEvent) {
  sourceModalInitialEvent.value = event
  sourceModalEventId.value = event.id
  showSourceModal.value = true
}

function handleViewSearchSource(item: SearchItem) {
  handleViewEvent(item.event)
}

function handleViewCitation(cite: Citation) {
  sourceModalInitialEvent.value = null
  sourceModalEventId.value = cite.event_id
  showSourceModal.value = true
}

const trips = ref<TripListItem[]>([])
const journal = ref<InstanceType<typeof TripJournal> | null>(null)
const accountName = computed(() => props.user.email.split('@')[0])

function backToTripList() {
  activeTab.value = 'trips'
  showSourceModal.value = false
  journal.value?.backToTripList()
}

async function handleJumpToTrip(payload: EventDestination) {
  if (!payload.tripId) {
    if (!payload.eventId) return
    switchTab('footprints')
    focusedStandaloneId.value = payload.eventId
    return
  }
  focusedStandaloneId.value = null
  activeTab.value = 'trips'
  await nextTick()
  if (activeTab.value === 'trips') await journal.value?.openTrip(payload.tripId, payload.eventId)
}

// Alert notification state
const alertMessage = ref('')
const alertType = ref<'error' | 'success' | 'info'>('info')
const alertSequence = ref(0)

function showAlert(message: string, type: 'error' | 'success' | 'info' = 'info') {
  alertMessage.value = message
  alertType.value = type
  alertSequence.value++
}

function clearAlert() {
  alertMessage.value = ''
}

</script>

<template>
  <div class="workspace-viewport">
    <!-- Desktop Left Navigation Sidebar (~208px) -->
    <aside class="workspace-sidebar" aria-label="工作區選單">
      <!-- App Brand Title -->
      <button type="button" class="sidebar-brand brand-home" aria-label="返回旅行手記" @click="backToTripList">
        <BrandMark />
        <div class="brand-text-group">
          <span class="brand-title">TravelMemo</span>
          <span class="brand-subtitle">旅程手記</span>
        </div>
      </button>

      <!-- Navigation Tabs (Desktop) -->
      <nav class="sidebar-nav" role="tablist" aria-label="工作區功能切換">
        <button
          v-for="(t, index) in TABS"
          :id="t.tabId"
          :key="t.id"
          :ref="(el) => setTabRef(el, index)"
          type="button"
          class="nav-tab-btn"
          :class="{ 'is-active': activeTab === t.id }"
          :aria-selected="activeTab === t.id"
          :aria-controls="t.panelId"
          role="tab"
          :tabindex="activeTab === t.id ? 0 : -1"
          @click="(e) => { handleActionClick(e); switchTab(t.id); }"
          @keydown="handleTabKeydown($event, index)"
        >
          <svg v-if="t.id === 'trips'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <AppIcon v-else-if="t.id === 'footprints'" name="pin" />
          <svg v-else-if="t.id === 'search'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <svg v-else-if="t.id === 'chat'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <span>{{ t.label }}</span>
        </button>
      </nav>

      <!-- Sidebar User Profile & Logout -->
      <div class="sidebar-user-section">
        <div class="user-info-card">
          <div class="user-avatar" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <span class="user-email">{{ accountName }}</span>
        </div>

        <button
          type="button"
          class="btn btn-secondary logout-button"
          :disabled="loggingOut || journal?.actionInProgress"
          @click="(e) => { handleActionClick(e); emit('logout'); }"
        >
          <span v-if="loggingOut" class="spinner-small ui-spinner ui-spinner--maple" aria-hidden="true"></span>
          <span>{{ loggingOut ? '登出中...' : '登出手記' }}</span>
        </button>
      </div>

      <!-- Softened feathered organic boundary with sparse tiny maple leaf accents -->
      <TravelDivider orientation="vertical" />
    </aside>

    <!-- Mobile Top Identity Bar -->
    <header class="mobile-topbar">
      <button type="button" class="mobile-brand brand-home" aria-label="返回旅行手記" @click="backToTripList"><BrandMark /><span class="brand-title">TravelMemo</span></button>
      <div class="mobile-user-row">
        <span class="mobile-user-email">{{ accountName }}</span>
        <button
          type="button"
          class="icon-button logout-button mobile-logout"
          :aria-label="loggingOut ? '登出中' : '登出'" title="登出"
          :disabled="loggingOut || journal?.actionInProgress"
          @click="emit('logout')"
        >
          <span v-if="loggingOut" class="spinner-small ui-spinner ui-spinner--maple" aria-hidden="true"></span><AppIcon v-else name="logout" />
        </button>
      </div>
    </header>

    <!-- Main Content Area: Fluid and Spacious -->
    <main class="workspace-main" :class="{ 'is-chat-tab': activeTab === 'chat' }">
      <div
        class="workspace-content-pane"
        :class="{ 'tab-wash-active': isTabWashing, 'is-chat-pane': activeTab === 'chat' }"
      >
        <!-- Global Alert Notification Area -->
        <StatusAlert :message="alertMessage" :type="alertType" :notice-key="alertSequence" floating @dismiss="clearAlert" />

        <TripJournal
          ref="journal"
          v-model:trips="trips"
          :active="activeTab === 'trips'"
          @notice="showAlert"
          @clear-notice="clearAlert"
          @action-click="handleActionClick"
        />

        <div v-if="activeTab === 'footprints'" id="workspace-panel-footprints" role="tabpanel" aria-labelledby="workspace-tab-footprints" class="tabpanel-container" tabindex="0">
          <StandaloneFootprints :focus-id="focusedStandaloneId" @view="handleViewEvent" @jump="handleJumpToTrip" @notice="showAlert" @unfocus="focusedStandaloneId = null" @photo-deleted="journal?.handlePhotoDeleted($event)" />
        </div>

        <!-- Recall Search View -->
        <div
          v-else-if="activeTab === 'search'"
          id="workspace-panel-search"
          role="tabpanel"
          aria-labelledby="workspace-tab-search"
          class="tabpanel-container"
          tabindex="0"
        >
          <RecallSearch
            :trips="trips"
            :state="recallState"
            @view-source="handleViewSearchSource"
            @jump-trip="handleJumpToTrip"
          />
        </div>

        <!-- TAB 3: AI Conversation View -->
        <div
          v-else-if="activeTab === 'chat'"
          id="workspace-panel-chat"
          role="tabpanel"
          aria-labelledby="workspace-tab-chat"
          class="tabpanel-container chat-tabpanel"
          tabindex="0"
        >
          <ConversationView
            :account-id="String(user.id)"
            :workspace="chatWorkspace"
            @open-trip="id => handleJumpToTrip({ tripId: id })"
            @view-citation="handleViewCitation"
            @jump-trip="handleJumpToTrip"
          />
        </div>
      </div>
    </main>

    <!-- Mobile bottom navigation -->
    <nav class="mobile-bottom-nav" aria-label="行動快捷功能">
      <TravelDivider orientation="horizontal" />
      <button
        v-for="t in TABS"
        :key="t.id"
        type="button"
        class="mobile-nav-btn"
        :aria-label="t.label"
        :class="{ 'is-active': activeTab === t.id }"
        :aria-pressed="activeTab === t.id"
        @click="(e) => { handleActionClick(e); switchTab(t.id); }"
      >
        <svg v-if="t.id === 'trips'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
        <AppIcon v-else-if="t.id === 'footprints'" name="pin" />
        <svg v-else-if="t.id === 'search'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <svg v-else-if="t.id === 'chat'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span>{{ t.shortLabel }}</span>
      </button>
    </nav>

    <SourceDetailModal
      :visible="showSourceModal"
      :event-id="sourceModalEventId"
      :initial-event="sourceModalInitialEvent"
      @close="showSourceModal = false"
      @jump="handleJumpToTrip"
    />

  </div>
</template>

<style scoped src="./TripWorkspace.css"></style>
