<script setup lang="ts">
// RouteMotif provides the notebook side-illustration with route waypoints
</script>

<template>
  <aside class="route-motif" aria-label="旅行筆記插圖">
    <div class="notebook-decor">
      <div class="stamp">
        <span class="stamp-code">TravelMemo</span>
        <span class="stamp-date">旅程手記</span>
      </div>

      <div class="route-map">
        <svg class="route-svg" viewBox="0 0 280 400" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Background faint grid / notebook lines -->
          <line x1="20" y1="80" x2="260" y2="80" stroke="#cfe0e5" stroke-dasharray="4 4" stroke-width="1" />
          <line x1="20" y1="160" x2="260" y2="160" stroke="#cfe0e5" stroke-dasharray="4 4" stroke-width="1" />
          <line x1="20" y1="240" x2="260" y2="240" stroke="#cfe0e5" stroke-dasharray="4 4" stroke-width="1" />
          <line x1="20" y1="320" x2="260" y2="320" stroke="#cfe0e5" stroke-dasharray="4 4" stroke-width="1" />

          <!-- Route curve line -->
          <path
            d="M 60 70 C 130 90, 80 170, 200 160 C 250 155, 170 260, 90 260 C 40 260, 120 340, 210 330"
            stroke="#176b68"
            stroke-width="3"
            stroke-linecap="round"
            stroke-dasharray="6 6"
          />

          <!-- Route Waypoints -->
          <!-- Point 1 -->
          <circle cx="60" cy="70" r="8" fill="#ffffff" stroke="#176b68" stroke-width="3" />
          <circle cx="60" cy="70" r="4" fill="#e8c768" />
          <text x="75" y="74" fill="#153e48" font-size="12" font-weight="600" font-family="sans-serif">那次出發</text>

          <!-- Point 2 -->
          <circle cx="200" cy="160" r="7" fill="#ffffff" stroke="#176b68" stroke-width="3" />
          <circle cx="200" cy="160" r="3" fill="#176b68" />
          <text x="135" y="190" fill="#153e48" font-size="12" font-family="sans-serif">沿途的風景</text>

          <!-- Point 3 -->
          <circle cx="90" cy="260" r="7" fill="#ffffff" stroke="#176b68" stroke-width="3" />
          <circle cx="90" cy="260" r="3" fill="#176b68" />
          <text x="35" y="290" fill="#153e48" font-size="12" font-family="sans-serif">記得的片刻</text>

          <!-- Point 4 (Destination) -->
          <circle cx="210" cy="330" r="9" fill="#e8c768" stroke="#153e48" stroke-width="2" />
          <circle cx="210" cy="330" r="3" fill="#153e48" />
          <text x="155" y="360" fill="#153e48" font-size="12" font-weight="600" font-family="sans-serif">留在這裡</text>
        </svg>
      </div>

      <div class="notebook-quote">
        <p class="quote-text">把走過的地方，慢慢記下來。</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.route-motif {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 2rem;
  background-color: #f7fbfc;
  border-right: 1px dashed var(--color-border);
  position: relative;
}

.notebook-decor {
  display: flex;
  flex-direction: column;
  height: 100%;
  justify-content: space-between;
}

.stamp {
  display: inline-flex;
  flex-direction: column;
  align-self: flex-start;
  padding: 0.35rem 0.65rem;
  border: 1.5px solid var(--color-teal);
  border-radius: var(--radius-sm);
  color: var(--color-teal);
  transform: rotate(-3deg);
  opacity: 0.85;
}

.stamp-code {
  font-family: var(--font-serif);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.stamp-date {
  font-size: 0.65rem;
  letter-spacing: 0.05em;
  color: var(--color-subtle);
}

.route-map {
  margin: 1.5rem 0;
  display: flex;
  justify-content: center;
}

.route-svg {
  width: 100%;
  max-width: 280px;
  height: auto;
}

.notebook-quote {
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}

.quote-text {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 0.9375rem;
  color: var(--color-subtle);
  line-height: 1.6;
}
</style>
