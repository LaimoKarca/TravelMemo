<script setup lang="ts">
// RouteMotif provides the auth side-illustration with route waypoints
</script>

<template>
  <aside class="route-motif" aria-label="旅行手記路線圖">
    <div class="motif-content">
      <div class="motif-badge">
        <span class="badge-brand">TravelMemo</span>
        <span class="badge-desc">探索與留存</span>
      </div>

      <div class="route-map" aria-hidden="true">
        <svg class="route-svg" viewBox="0 0 280 380" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Subtle journey grid lines -->
          <line x1="20" y1="70" x2="260" y2="70" stroke="#DFE1E6" stroke-dasharray="3 3" stroke-width="1" />
          <line x1="20" y1="150" x2="260" y2="150" stroke="#DFE1E6" stroke-dasharray="3 3" stroke-width="1" />
          <line x1="20" y1="230" x2="260" y2="230" stroke="#DFE1E6" stroke-dasharray="3 3" stroke-width="1" />
          <line x1="20" y1="310" x2="260" y2="310" stroke="#DFE1E6" stroke-dasharray="3 3" stroke-width="1" />

          <!-- Dynamic route curve line -->
          <path
            d="M 50 65 C 130 80, 80 160, 210 150 C 255 145, 175 240, 85 240 C 35 240, 110 320, 215 315"
            stroke="#245AE8"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-dasharray="6 6"
          />

          <!-- Route Waypoints -->
          <!-- Waypoint 1 -->
          <circle cx="50" cy="65" r="8" fill="#FFFFFF" stroke="#245AE8" stroke-width="2.5" />
          <circle cx="50" cy="65" r="3.5" fill="#F4C84B" />
          <text x="66" y="70" fill="#172B4D" font-size="12" font-weight="600" font-family="system-ui, sans-serif">啟程時刻</text>

          <!-- Waypoint 2 -->
          <circle cx="210" cy="150" r="7" fill="#FFFFFF" stroke="#245AE8" stroke-width="2" />
          <circle cx="210" cy="150" r="3" fill="#245AE8" />
          <text x="145" y="178" fill="#5E6C84" font-size="11" font-family="system-ui, sans-serif">沿途的足跡</text>

          <!-- Waypoint 3 -->
          <circle cx="85" cy="240" r="7" fill="#FFFFFF" stroke="#245AE8" stroke-width="2" />
          <circle cx="85" cy="240" r="3" fill="#245AE8" />
          <text x="32" y="268" fill="#5E6C84" font-size="11" font-family="system-ui, sans-serif">尋訪與對話</text>

          <!-- Waypoint 4 (Destination) -->
          <circle cx="215" cy="315" r="9" fill="#F4C84B" stroke="#172B4D" stroke-width="2" />
          <circle cx="215" cy="315" r="3" fill="#172B4D" />
          <text x="156" y="344" fill="#172B4D" font-size="12" font-weight="600" font-family="system-ui, sans-serif">記憶歸檔</text>
        </svg>
      </div>

      <div class="motif-footer">
        <p class="motif-caption">每一處駐足，都是值得回溯的旅程故事。</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.route-motif {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 3rem 2.5rem;
  background-color: var(--color-canvas);
  border-right: 1px solid var(--color-border);
  position: relative;
  overflow: hidden;
}

.motif-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 320px;
  justify-content: space-between;
  margin: 0 auto;
}

.motif-badge {
  display: inline-flex;
  flex-direction: column;
  align-self: flex-start;
  padding: 0.35rem 0.75rem;
  border-left: 3px solid var(--color-cobalt);
  background-color: var(--color-white);
  border-radius: var(--radius-xs);
  box-shadow: var(--shadow-sm);
}

.badge-brand {
  font-family: var(--font-sans);
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-navy);
  letter-spacing: 0.05em;
}

.badge-desc {
  font-size: 0.6875rem;
  color: var(--color-subtle);
}

.route-map {
  margin: 2rem 0;
  display: flex;
  justify-content: center;
}

.route-svg {
  width: 100%;
  max-width: 280px;
  height: auto;
}

.motif-footer {
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}

.motif-caption {
  font-family: var(--font-sans);
  font-size: 0.875rem;
  color: var(--color-subtle);
  line-height: 1.5;
}
</style>
