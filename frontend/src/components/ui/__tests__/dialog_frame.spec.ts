import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { expect, it } from 'vitest'
import AppDialogFrame from '../AppDialogFrame.vue'
import ConfirmDialog from '../ConfirmDialog.vue'

it('gives the top dialog the keyboard and restores the launcher at each level', async () => {
  const editor = ref(false)
  const confirmation = ref(false)
  const wrapper = mount(defineComponent({
    setup: () => () => h('div', [
      h('button', { id: 'launch-editor', onClick: () => { editor.value = true } }, '編輯'),
      h(AppDialogFrame, {
        visible: editor.value, label: '編輯足跡', onClose: () => { editor.value = false }
      }, () => [
        h('input', { id: 'place-name', 'aria-label': '地點名稱' }),
        h('button', { id: 'launch-confirm', onClick: () => { confirmation.value = true } }, '刪除')
      ]),
      h(ConfirmDialog, {
        visible: confirmation.value, title: '確認刪除', message: '將移除紀錄',
        onCancel: () => { confirmation.value = false }
      })
    ])
  }), { attachTo: document.body })

  try {
    const firstLauncher = wrapper.get<HTMLButtonElement>('#launch-editor')
    firstLauncher.element.focus()
    await firstLauncher.trigger('click')
    await nextTick()
    expect(document.activeElement).toBe(wrapper.get('[aria-label="編輯足跡"]').element)
    expect(firstLauncher.attributes('inert')).toBeDefined()

    const secondLauncher = wrapper.get<HTMLButtonElement>('#launch-confirm')
    secondLauncher.element.focus()
    await secondLauncher.trigger('click')
    await nextTick()
    const cancel = wrapper.get('.cancel-action').element
    expect(document.activeElement).toBe(cancel)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true }))
    expect(document.activeElement?.textContent).toContain('確定')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }))
    await nextTick()
    await nextTick()
    expect(confirmation.value).toBe(false)
    expect(editor.value).toBe(true)
    expect(document.activeElement).toBe(secondLauncher.element)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }))
    await nextTick()
    await nextTick()
    expect(editor.value).toBe(false)
    expect(document.activeElement).toBe(firstLauncher.element)
    expect(firstLauncher.attributes('inert')).toBeUndefined()
  } finally {
    wrapper.unmount()
  }
})
