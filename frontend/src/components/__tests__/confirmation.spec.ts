import { afterEach, describe, expect, it } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import ConfirmDialog from '../ConfirmDialog.vue'
enableAutoUnmount(afterEach)

describe('deletion confirmation', () => {
  it('keeps cancel first and accepts DELETE or 刪除 only after deliberate input', async () => {
    const w = mount(ConfirmDialog, { props: { visible: true, title: '刪除照片', message: '此操作無法復原', confirmText: '刪除照片', confirmationMode: 'keyword', targetKey: 'photo1' } })
    expect(w.findAll('footer button').map(b => b.text())).toEqual(['取消', '刪除照片'])
    const input = w.get('input')
    const button = w.get('footer button:last-child')
    expect(button.attributes('disabled')).toBeDefined()
    await input.setValue('DELETE NOW')
    await input.trigger('keydown.enter')
    expect(w.emitted('confirm')).toBeUndefined()
    for (const word of [' delete ', '刪除']) {
      await input.setValue(word)
      expect(button.attributes('disabled')).toBeUndefined()
    }
    await input.trigger('keydown.enter')
    await button.trigger('click')
    expect(w.emitted('confirm')).toHaveLength(1)
    await w.get('.cancel-action').trigger('click')
    expect(w.emitted('cancel')).toBeUndefined()
  })

  it('requires the journal name, resets on target change and initially focuses cancel', async () => {
    const w = mount(ConfirmDialog, { props: { visible: true, title: '刪除手記', message: '確定刪除？', confirmationMode: 'name', confirmationName: '宜蘭小假期', targetKey: 'trip1' }, attachTo: document.body })
    await flushPromises()
    expect(document.activeElement === w.get('.cancel-action').element).toBe(true)
    const input = w.get('input')
    await input.setValue('DELETE')
    expect(w.get('footer button:last-child').attributes('disabled')).toBeDefined()
    await input.setValue(' 宜蘭小假期 ')
    expect(w.get('footer button:last-child').attributes('disabled')).toBeUndefined()
    await w.setProps({ targetKey: 'trip2' })
    expect((input.element as HTMLInputElement).value).toBe('')
    expect(w.get('footer button:last-child').attributes('disabled')).toBeDefined()
  })
})
