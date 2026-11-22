import { computed, nextTick, onBeforeUnmount, shallowReactive, watch, type Ref } from 'vue'

const focusableSelector = 'button, a[href], input, select, textarea, summary, [tabindex], [contenteditable="true"]'
const openDialogs = shallowReactive<Array<{ panel: Ref<HTMLElement | null> }>>([])
const inertBackground = new Set<HTMLElement>()

watch(() => openDialogs.at(-1)?.panel.value, panel => {
  for (const element of inertBackground) element.removeAttribute('inert')
  inertBackground.clear()
  if (!panel?.isConnected) return
  for (let branch: HTMLElement | null = panel; branch?.parentElement && branch !== document.body; branch = branch.parentElement) {
    for (const element of branch.parentElement.children) {
      if (element === branch || !(element instanceof HTMLElement) || element.hasAttribute('inert')) continue
      element.setAttribute('inert', '')
      inertBackground.add(element)
    }
  }
}, { flush: 'post' })

function focusableElements(panel: HTMLElement) {
  return [...panel.querySelectorAll<HTMLElement>(focusableSelector)].filter(element => {
    if (element.tabIndex < 0 || element.matches(':disabled') || element.closest('[hidden], [inert], [aria-hidden="true"]')) return false
    const closedDetails = element.closest('details:not([open])')
    if (closedDetails && closedDetails.querySelector('summary') !== element) return false
    for (let parent: HTMLElement | null = element; parent && parent !== panel; parent = parent.parentElement) {
      const css = getComputedStyle(parent)
      if (css.display === 'none' || css.visibility === 'hidden') return false
    }
    return true
  })
}

export function useDialogFocus(
  visible: () => boolean,
  panel: Ref<HTMLElement | null>,
  options: { close: () => void; initial?: () => string | undefined; onKeydown?: (event: KeyboardEvent) => void }
) {
  const layer = { panel }
  const level = computed(() => 1000 + openDialogs.indexOf(layer) * 2)
  let launcher: HTMLElement | null = null
  const isTop = () => openDialogs.at(-1) === layer

  function focusInitial() {
    if (!isTop() || !panel.value) return
    const selector = options.initial?.()
    const target = selector && panel.value.querySelector<HTMLElement>(selector)
    const element = target && !target.matches(':disabled') ? target : panel.value
    element.focus({ preventScroll: true })
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented || !isTop() || !panel.value) return
    if (event.key === 'Escape') {
      event.preventDefault()
      options.close()
      return
    }
    if (event.key !== 'Tab') {
      options.onKeydown?.(event)
      return
    }
    const focusables = focusableElements(panel.value)
    const active = document.activeElement
    const boundary = event.shiftKey ? focusables[0] : focusables.at(-1)
    if (!focusables.includes(active as HTMLElement) || active === boundary) {
      event.preventDefault()
      ;(focusables[event.shiftKey ? focusables.length - 1 : 0] || panel.value).focus()
    }
  }

  function containFocus(event: FocusEvent) {
    if (isTop() && event.target instanceof Node && panel.value && !panel.value.contains(event.target)) focusInitial()
  }

  function unregister() {
    const index = openDialogs.indexOf(layer)
    if (index === -1) return
    const wasTop = isTop()
    openDialogs.splice(index, 1)
    window.removeEventListener('keydown', handleKeydown)
    document.removeEventListener('focusin', containFocus)
    const target = launcher
    const nextTop = openDialogs.at(-1)
    launcher = null
    if (wasTop) void nextTick(() => {
      if (openDialogs.at(-1) === nextTop && target?.isConnected) target.focus({ preventScroll: true })
    })
  }

  watch(visible, (open) => {
    if (!open) { unregister(); return }
    launcher = document.activeElement instanceof HTMLElement ? document.activeElement : null
    openDialogs.push(layer)
    window.addEventListener('keydown', handleKeydown)
    document.addEventListener('focusin', containFocus)
    void nextTick(focusInitial)
  }, { immediate: true })
  onBeforeUnmount(unregister)

  return { level, focusInitial }
}
