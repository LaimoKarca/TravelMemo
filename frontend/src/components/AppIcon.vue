<script setup lang="ts">
defineProps<{ name: 'image' | 'refresh' | 'wand' | 'search' | 'chevron' | 'plus' }>()
const paths = {
  image: 'M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM3 16l6-6 5 5 3-3 4 4M16 7h.01',
  refresh: 'M20 7v5h-5M4 17v-5h5M6.1 7a7 7 0 0 1 11.6-1L20 9M4 15l2.3 3A7 7 0 0 0 18 17',
  wand: 'm4 20 12-12 4 4L8 24M14 10l4 4M5 3v4M3 5h4M17 1v4M15 3h4M22 17v4M20 19h4',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  chevron: 'm6 9 6 6 6-6',
  plus: 'M12 5v14M5 12h14'
}
</script>
<template><svg viewBox="0 0 26 26" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name]" /></svg></template>
<style scoped>svg { width: 1.25rem; height: 1.25rem; flex: 0 0 auto; }</style>
