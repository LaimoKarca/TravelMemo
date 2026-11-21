<template>
  <span class="trail-loader" aria-hidden="true"></span>
</template>

<style scoped>
.trail-loader {
  display: block;
  position: relative;
  width: 2.75rem;
  border-top: 1px dashed var(--color-maple);
}
.trail-loader::after {
  content: '';
  position: absolute;
  top: -.25rem;
  left: 0;
  width: .45rem;
  height: .45rem;
  border-radius: 50%;
  background: var(--color-maple);
  animation: travel-trail 1.1s ease-in-out infinite alternate;
}
@keyframes travel-trail {
  from { transform: translateX(0); }
  to { transform: translateX(2.3rem); }
}
@media (prefers-reduced-motion: reduce) {
  .trail-loader::after { animation: none; left: 1.15rem; }
}
</style>
