<script setup lang="ts">
// BrandHeader displays the TravelMemo wordmark with route waypoint icon
</script>

<template>
  <header class="brand-header">
    <div class="brand-title-wrap">
      <div class="brand-icon" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="5" r="3" />
          <path d="M12 8v10" stroke-dasharray="2 2" />
          <circle cx="12" cy="19" r="2" fill="currentColor" />
        </svg>
      </div>
      <h1 class="brand-name travelmemo-wordmark">TravelMemo</h1>
      <span class="brand-subtitle">旅程手記</span>
    </div>
  </header>
</template>

<style scoped>
.brand-header {
  margin-bottom: 2rem;
}

.brand-title-wrap {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.brand-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background-color: var(--color-maple);
  color: #FFFFFF;
}

.brand-name {
  font-family: var(--font-sans);
  font-size: 1.875rem;
  font-weight: 700;
  color: var(--color-ink);
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.brand-subtitle {
  font-family: var(--font-sans);
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-maple);
  letter-spacing: 0.05em;
  padding: 0.15rem 0.5rem;
  background-color: var(--color-maple-subtle);
  border-radius: var(--radius-xs);
}
</style>
