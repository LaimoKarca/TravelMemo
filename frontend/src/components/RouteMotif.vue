<script setup lang="ts">
// RouteMotif provides the auth side-illustration with route waypoints
</script>

<template>
  <aside class="route-motif" aria-label="旅行手記路線圖">
    <div class="motif-content">
      <div class="motif-badge">
        <span class="badge-brand">TravelMemo</span>
        <span class="badge-desc">旅程手記</span>
      </div>

      <div class="route-map" aria-hidden="true">
        <svg class="route-svg" viewBox="0 0 280 380" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Subtle journey grid lines -->
          <line x1="20" y1="70" x2="260" y2="70" stroke="var(--color-border)" stroke-dasharray="3 3" stroke-width="1" />
          <line x1="20" y1="150" x2="260" y2="150" stroke="var(--color-border)" stroke-dasharray="3 3" stroke-width="1" />
          <line x1="20" y1="230" x2="260" y2="230" stroke="var(--color-border)" stroke-dasharray="3 3" stroke-width="1" />
          <line x1="20" y1="310" x2="260" y2="310" stroke="var(--color-border)" stroke-dasharray="3 3" stroke-width="1" />

          <!-- Dynamic route curve line -->
          <path
            d="M 50 65 C 130 80, 80 160, 210 150 C 255 145, 175 240, 85 240 C 35 240, 110 320, 215 315"
            stroke="var(--color-maple)"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-dasharray="6 6"
          />

          <!-- Route Waypoints -->
          <!-- Waypoint 1 -->
          <circle cx="50" cy="65" r="8" fill="var(--color-paper)" stroke="var(--color-maple)" stroke-width="2.5" />
          <circle cx="50" cy="65" r="3.5" fill="var(--color-amber)" />
          <text x="66" y="70" fill="var(--color-ink)" font-size="12" font-weight="600" font-family="system-ui, sans-serif">出發</text>

          <!-- Waypoint 2 -->
          <circle cx="210" cy="150" r="7" fill="var(--color-paper)" stroke="var(--color-maple)" stroke-width="2" />
          <circle cx="210" cy="150" r="3" fill="var(--color-maple)" />

          <!-- Waypoint 3 -->
          <circle cx="85" cy="240" r="7" fill="var(--color-paper)" stroke="var(--color-maple)" stroke-width="2" />
          <circle cx="85" cy="240" r="3" fill="var(--color-maple)" />

          <!-- Waypoint 4 (Destination) -->
          <circle cx="215" cy="315" r="9" fill="var(--color-amber)" stroke="var(--color-ink)" stroke-width="2" />
          <circle cx="215" cy="315" r="3" fill="var(--color-ink)" />
          <text x="156" y="344" fill="var(--color-ink)" font-size="12" font-weight="600" font-family="system-ui, sans-serif">下一站</text>
        </svg>
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
  border-left: 3px solid var(--color-maple);
  background-color: var(--color-paper);
  border-radius: var(--radius-xs);
  box-shadow: var(--shadow-sm);
}

.badge-brand {
  font-family: var(--font-sans);
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-ink);
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
