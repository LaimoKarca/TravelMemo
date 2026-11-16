<script setup lang="ts">
// BrandHeader displays the TravelMemo Georgia wordmark and Chinese subtitle
</script>

<template>
  <header class="brand-header">
    <div class="brand-title-wrap">
      <h1 class="brand-name travelmemo-wordmark">TravelMemo</h1>
      <span class="brand-subtitle">旅程手記</span>
    </div>
    <p class="brand-desc">記錄旅途點滴，以記憶為線索的旅行隨筆</p>
  </header>
</template>

<style scoped>
.brand-header {
  margin-bottom: 2rem;
}

.brand-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.brand-name {
  font-size: 2.25rem;
  color: var(--color-ink);
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.brand-subtitle {
  font-family: var(--font-sans);
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-teal);
  letter-spacing: 0.05em;
  padding: 0.125rem 0.5rem;
  background-color: rgba(23, 107, 104, 0.08);
  border-radius: var(--radius-sm);
}

.brand-desc {
  margin-top: 0.5rem;
  font-size: 0.9375rem;
  color: var(--color-subtle);
}
</style>
