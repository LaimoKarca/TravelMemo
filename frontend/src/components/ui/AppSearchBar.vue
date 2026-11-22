<script setup lang="ts">
import AppIcon from './AppIcon.vue'

const query = defineModel<string>({ required: true })
withDefaults(defineProps<{
  label: string
  placeholder: string
  inputId?: string
  inputType?: 'search' | 'text'
  lead?: 'icon' | 'submit' | 'none'
  plain?: boolean
  customClear?: boolean
  disabled?: boolean
  required?: boolean
  maxlength?: number
}>(), { lead: 'icon', inputType: 'search' })
</script>

<template>
  <div class="search-bar" :class="{ 'search-bar--plain': plain, 'search-bar--no-lead': lead === 'none' }">
    <button v-if="lead === 'submit'" type="submit" class="icon-button search-bar__lead" aria-label="搜尋" title="搜尋">
      <AppIcon name="search" />
    </button>
    <span v-else-if="lead === 'icon'" class="search-bar__lead" aria-hidden="true"><AppIcon name="search" /></span>
    <input
      :id="inputId"
      v-model="query"
      :type="inputType"
      class="form-input search-bar__input"
      :class="{ 'search-bar__input--custom-clear': customClear }"
      :aria-label="label"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :maxlength="maxlength"
    />
    <slot name="actions" />
  </div>
</template>

<style scoped src="./AppSearchBar.css"></style>
