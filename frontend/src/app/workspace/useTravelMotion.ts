import { ref, onBeforeUnmount } from 'vue'

export function useTravelMotion() {
  const isTabWashing = ref(false)
  let washTimer: number | null = null
  let washRafId: number | null = null
  const activeRipples = new Map<() => void, number>()

  function triggerTabWash(durationMs = 450) {
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      isTabWashing.value = false
      return
    }

    // Cancel pending animation frame and timer from rapid tab switches
    if (washRafId !== null) {
      cancelAnimationFrame(washRafId)
      washRafId = null
    }
    if (washTimer !== null) {
      clearTimeout(washTimer)
      washTimer = null
    }

    isTabWashing.value = false

    washRafId = requestAnimationFrame(() => {
      washRafId = null

      // Check reduced motion inside RAF as well
      if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
        isTabWashing.value = false
        return
      }

      isTabWashing.value = true
      washTimer = window.setTimeout(() => {
        isTabWashing.value = false
        washTimer = null
      }, durationMs)
    })
  }

  function handleActionClick(event: MouseEvent | KeyboardEvent, explicitTarget?: HTMLElement | null) {
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      return
    }

    const target = (explicitTarget || (event.currentTarget as HTMLElement) || (event.target as HTMLElement))
    if (!target || typeof target.getBoundingClientRect !== 'function') return

    // Ignore disabled controls
    if (
      (target as HTMLButtonElement).disabled ||
      target.getAttribute('aria-disabled') === 'true' ||
      target.classList.contains('disabled') ||
      target.classList.contains('is-disabled')
    ) {
      return
    }

    const rect = target.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return

    let x = rect.width / 2
    let y = rect.height / 2

    // Check if pointer click with coordinates inside element
    if ('clientX' in event && event.clientX > 0 && event.clientY > 0) {
      x = event.clientX - rect.left
      y = event.clientY - rect.top
    }
    // Keyboard activation (Enter/Space) will fall back to center (rect.width / 2, rect.height / 2)

    // Ensure target has a relative positioning context so the host bounds locally
    if (typeof window !== 'undefined' && window.getComputedStyle(target).position === 'static') {
      target.style.position = 'relative'
    }

    // Bounded ripple host ensures ripple cannot escape button bounds,
    // while leaving the target's outer focus-visible ring unclipped.
    const host = document.createElement('span')
    host.className = 'travel-cream-ripple-host'
    host.setAttribute('aria-hidden', 'true')

    const ripple = document.createElement('span')
    ripple.className = 'travel-cream-ripple'
    ripple.setAttribute('aria-hidden', 'true')

    // Radius needed to reach all corners from point (x, y)
    const maxDistX = Math.max(x, rect.width - x)
    const maxDistY = Math.max(y, rect.height - y)
    const radius = Math.ceil(Math.hypot(maxDistX, maxDistY))
    const diameter = radius * 2

    ripple.style.width = `${diameter}px`
    ripple.style.height = `${diameter}px`
    ripple.style.left = `${x - radius}px`
    ripple.style.top = `${y - radius}px`

    host.appendChild(ripple)

    const cleanUp = () => {
      if (host.parentNode === target) {
        target.removeChild(host)
      }
      const timerId = activeRipples.get(cleanUp)
      if (timerId) {
        clearTimeout(timerId)
      }
      activeRipples.delete(cleanUp)
    }

    ripple.addEventListener('animationend', cleanUp, { once: true })
    const timerId = window.setTimeout(cleanUp, 480)
    activeRipples.set(cleanUp, timerId)

    // Insert behind button text and icons so content is never obscured
    target.insertBefore(host, target.firstChild)
  }

  onBeforeUnmount(() => {
    if (washRafId !== null) {
      cancelAnimationFrame(washRafId)
      washRafId = null
    }
    if (washTimer !== null) {
      clearTimeout(washTimer)
      washTimer = null
    }
    activeRipples.forEach((timerId, cleanUp) => {
      clearTimeout(timerId)
      cleanUp()
    })
    activeRipples.clear()
  })

  return {
    isTabWashing,
    triggerTabWash,
    handleActionClick
  }
}
