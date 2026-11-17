<script setup lang="ts">
withDefaults(
  defineProps<{
    orientation?: 'vertical' | 'horizontal'
  }>(),
  {
    orientation: 'vertical'
  }
)
</script>

<template>
  <div
    class="travel-divider"
    :class="`is-${orientation}`"
    aria-hidden="true"
    role="presentation"
  >
    <!-- Soft ~12-18px feathered wash layer -->
    <div class="feathered-wash" />

    <!-- Organic / wavy low-contrast SVG edge -->
    <svg
      v-if="orientation === 'vertical'"
      class="organic-edge-svg is-vertical"
      viewBox="0 0 16 1000"
      preserveAspectRatio="none"
      aria-hidden="true"
      role="presentation"
    >
      <!-- Subtle wavy organic primary path -->
      <path
        d="M 8 0
           C 9.5 70, 6.5 140, 8 210
           C 9.5 280, 6.5 350, 8 420
           C 9.5 490, 6.5 560, 8 630
           C 9.5 700, 6.5 770, 8 840
           C 9.5 910, 6.5 970, 8 1000"
        fill="none"
        stroke="var(--color-border)"
        stroke-opacity="0.35"
        stroke-width="1.2"
        stroke-linecap="round"
      />
      <!-- Secondary organic contour echo -->
      <path
        d="M 8 0
           C 6.8 80, 9.2 160, 8 240
           C 6.8 320, 9.2 400, 8 480
           C 6.8 560, 9.2 640, 8 720
           C 6.8 800, 9.2 880, 8 960
           L 8 1000"
        fill="none"
        stroke="var(--color-border-light)"
        stroke-opacity="0.25"
        stroke-width="1"
        stroke-linecap="round"
      />
    </svg>

    <svg
      v-else
      class="organic-edge-svg is-horizontal"
      viewBox="0 0 1000 16"
      preserveAspectRatio="none"
      aria-hidden="true"
      role="presentation"
    >
      <!-- Subtle wavy organic horizontal path -->
      <path
        d="M 0 8
           C 70 9.5, 140 6.5, 210 8
           C 280 9.5, 350 6.5, 420 8
           C 490 9.5, 560 6.5, 630 8
           C 700 9.5, 770 6.5, 840 8
           C 910 9.5, 970 6.5, 1000 8"
        fill="none"
        stroke="var(--color-border)"
        stroke-opacity="0.35"
        stroke-width="1.2"
        stroke-linecap="round"
      />
      <!-- Secondary organic contour echo -->
      <path
        d="M 0 8
           C 80 6.8, 160 9.2, 240 8
           C 320 6.8, 400 9.2, 480 8
           C 560 6.8, 640 9.2, 720 8
           C 800 6.8, 880 9.2, 960 8
           L 1000 8"
        fill="none"
        stroke="var(--color-border-light)"
        stroke-opacity="0.25"
        stroke-width="1"
        stroke-linecap="round"
      />
    </svg>

    <!-- Sparse visible tiny maple accents (aria-hidden, pointer-events: none) -->
    <template v-if="orientation === 'vertical'">
      <svg
        class="maple-accent maple-accent-v1"
        viewBox="0 0 24 24"
        width="11"
        height="11"
        aria-hidden="true"
        role="presentation"
      >
        <path
          d="M12 21v-3.5m0-3.5c-1.8-1.8-4.5-.9-5.4.9 0-2.7.9-5.4-.9-7.2 1.8 0 3.6.9 4.5 2.7 0-2.7.9-6.3 1.8-9 1 2.7 1.8 6.3 1.8 9 .9-1.8 2.7-2.7 4.5-2.7-1.8 1.8-.9 4.5-.9 7.2-.9-1.8-3.6-2.7-5.4-.9"
          fill="var(--color-maple)"
          fill-opacity="0.5"
          stroke="var(--color-maple)"
          stroke-opacity="0.8"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <svg
        class="maple-accent maple-accent-v2"
        viewBox="0 0 24 24"
        width="10"
        height="10"
        aria-hidden="true"
        role="presentation"
      >
        <path
          d="M12 21v-3.5m0-3.5c-1.8-1.8-4.5-.9-5.4.9 0-2.7.9-5.4-.9-7.2 1.8 0 3.6.9 4.5 2.7 0-2.7.9-6.3 1.8-9 1 2.7 1.8 6.3 1.8 9 .9-1.8 2.7-2.7 4.5-2.7-1.8 1.8-.9 4.5-.9 7.2-.9-1.8-3.6-2.7-5.4-.9"
          fill="var(--color-maple)"
          fill-opacity="0.45"
          stroke="var(--color-maple)"
          stroke-opacity="0.75"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </template>

    <template v-else>
      <svg
        class="maple-accent maple-accent-h1"
        viewBox="0 0 24 24"
        width="11"
        height="11"
        aria-hidden="true"
        role="presentation"
      >
        <path
          d="M12 21v-3.5m0-3.5c-1.8-1.8-4.5-.9-5.4.9 0-2.7.9-5.4-.9-7.2 1.8 0 3.6.9 4.5 2.7 0-2.7.9-6.3 1.8-9 1 2.7 1.8 6.3 1.8 9 .9-1.8 2.7-2.7 4.5-2.7-1.8 1.8-.9 4.5-.9 7.2-.9-1.8-3.6-2.7-5.4-.9"
          fill="var(--color-maple)"
          fill-opacity="0.5"
          stroke="var(--color-maple)"
          stroke-opacity="0.8"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <svg
        class="maple-accent maple-accent-h2"
        viewBox="0 0 24 24"
        width="10"
        height="10"
        aria-hidden="true"
        role="presentation"
      >
        <path
          d="M12 21v-3.5m0-3.5c-1.8-1.8-4.5-.9-5.4.9 0-2.7.9-5.4-.9-7.2 1.8 0 3.6.9 4.5 2.7 0-2.7.9-6.3 1.8-9 1 2.7 1.8 6.3 1.8 9 .9-1.8 2.7-2.7 4.5-2.7-1.8 1.8-.9 4.5-.9 7.2-.9-1.8-3.6-2.7-5.4-.9"
          fill="var(--color-maple)"
          fill-opacity="0.45"
          stroke="var(--color-maple)"
          stroke-opacity="0.75"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </template>
  </div>
</template>

<style scoped>
.travel-divider {
  position: absolute;
  pointer-events: none;
  user-select: none;
  z-index: 3;
}

/* Vertical: desktop sidebar right boundary (~16px feathered wash) */
.travel-divider.is-vertical {
  top: 0;
  bottom: 0;
  right: -8px;
  width: 16px;
}

.travel-divider.is-vertical .feathered-wash {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to right,
    transparent 0%,
    rgba(220, 209, 191, 0.15) 30%,
    rgba(220, 209, 191, 0.28) 50%,
    rgba(220, 209, 191, 0.15) 70%,
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to bottom,
    transparent 0%,
    black 6%,
    black 94%,
    transparent 100%
  );
  mask-image: linear-gradient(
    to bottom,
    transparent 0%,
    black 6%,
    black 94%,
    transparent 100%
  );
}

.travel-divider.is-vertical .organic-edge-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.travel-divider.is-vertical .maple-accent {
  position: absolute;
  left: 50%;
  pointer-events: none;
}

.travel-divider.is-vertical .maple-accent-v1 {
  top: 26%;
  transform: translate(-50%, -50%) rotate(-14deg);
}

.travel-divider.is-vertical .maple-accent-v2 {
  top: 74%;
  transform: translate(-50%, -50%) rotate(16deg);
}

/* Horizontal: mobile bottom nav top boundary (~16px feathered wash) */
.travel-divider.is-horizontal {
  top: -8px;
  left: 0;
  right: 0;
  height: 16px;
}

.travel-divider.is-horizontal .feathered-wash {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    rgba(220, 209, 191, 0.15) 30%,
    rgba(220, 209, 191, 0.28) 50%,
    rgba(220, 209, 191, 0.15) 70%,
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0%,
    black 5%,
    black 95%,
    transparent 100%
  );
  mask-image: linear-gradient(
    to right,
    transparent 0%,
    black 5%,
    black 95%,
    transparent 100%
  );
}

.travel-divider.is-horizontal .organic-edge-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.travel-divider.is-horizontal .maple-accent {
  position: absolute;
  top: 50%;
  pointer-events: none;
}

.travel-divider.is-horizontal .maple-accent-h1 {
  left: 33%;
  transform: translate(-50%, -50%) rotate(-10deg);
}

.travel-divider.is-horizontal .maple-accent-h2 {
  left: 67%;
  transform: translate(-50%, -50%) rotate(12deg);
}

@media (prefers-reduced-motion: reduce) {
  .travel-divider,
  .maple-accent,
  .feathered-wash,
  .organic-edge-svg {
    animation: none !important;
    transition: none !important;
  }
}
</style>
