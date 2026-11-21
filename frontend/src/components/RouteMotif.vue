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

<style scoped src="../assets/styles/components/RouteMotif.css"></style>
