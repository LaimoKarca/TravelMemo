<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { mapsDestination, textAddress, validMapUrl } from '@/utils/maps'

const props = defineProps<{
  location: { map_url?: string | null; address?: string; city?: string; place_name?: string }
  showAddress?: boolean
  showLabel?: boolean
  mode?: 'saved-map' | 'address'
}>()
const savedMap = computed(() => validMapUrl(props.location.map_url) || validMapUrl(props.location.address))
const link = computed(() => props.mode === 'saved-map' ? savedMap.value : mapsDestination(props.location))
const address = computed(() => props.showAddress || props.mode === 'address' ? textAddress(props.location.address) : '')
const label = computed(() => props.location.place_name
  ? `在 Google Maps 開啟${props.location.place_name}`
  : '在 Google Maps 開啟')
</script>

<template>
  <span v-if="mode === 'address' && address" class="location-address">
    <a v-if="link" class="address-link" :href="link" :aria-label="`${label}：${address}`"
      target="_blank" rel="noopener noreferrer" @click.stop @keydown.enter.stop>{{ address }}</a>
    <template v-else>{{ address }}</template>
  </span>
  <span v-else-if="mode !== 'address' && (link || address)" class="location-link">
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
      <AppIcon :name="mode === 'saved-map' ? 'map' : 'pin'" />
      <span v-if="showLabel">Google Maps</span>
    </a>
  </span>
</template>

<style scoped src="./LocationLink.css"></style>
