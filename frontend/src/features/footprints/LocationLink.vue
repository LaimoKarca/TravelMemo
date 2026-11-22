<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { mapsDestination, validMapUrl } from '@/utils/maps'

const props = defineProps<{
  location: { map_url?: string | null; address?: string; city?: string; place_name?: string }
  showAddress?: boolean
  showLabel?: boolean
}>()
const link = computed(() => mapsDestination(props.location))
const address = computed(() => {
  const value = props.location.address
  return props.showAddress && value && !validMapUrl(value) ? value : ''
})
const label = computed(() => props.location.place_name
  ? `在 Google Maps 開啟${props.location.place_name}`
  : '在 Google Maps 開啟')
</script>

<template>
  <span v-if="link || address" class="location-link">
    <span v-if="address">{{ address }}</span>
    <a
      v-if="link"
      class="icon-button location-link__action"
      :href="link"
      :aria-label="label"
      title="在 Google Maps 開啟"
      target="_blank"
      rel="noopener noreferrer"
      @click.stop
      @keydown.enter.stop
    >
      <AppIcon name="pin" />
      <span v-if="showLabel">Google Maps</span>
    </a>
  </span>
</template>

<style scoped src="./LocationLink.css"></style>
