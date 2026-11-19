import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TripDialog from '../TripDialog.vue'
import JournalNote from '../JournalNote.vue'
import PhotoPicker from '../PhotoPicker.vue'
import ConversationView from '../ConversationView.vue'
import * as auth from '../../api/auth'
import * as api from '../../api/conversation'

describe('Journal editing and resumable chat', () => {
  beforeEach(() => { vi.restoreAllMocks(); localStorage.clear() })
  afterEach(() => { vi.useRealTimers() })
  it('aligns the end date when a later start date is chosen and retains same-day trips', async () => {
    const wrapper = mount(TripDialog, { props: { visible: true } })
    const start = wrapper.get('#trip-start-date')
    const end = wrapper.get('#trip-end-date')
    expect((end.element as HTMLInputElement).value > (start.element as HTMLInputElement).value).toBe(true)
    await start.setValue('2030-05-20')
    expect((end.element as HTMLInputElement).value).toBe('2030-05-20')
    expect(end.attributes('min')).toBe('2030-05-20')
    wrapper.unmount()
  })
  it('previews prose without changing the draft, then applies and undoes it', async () => {
    vi.spyOn(auth, 'request').mockResolvedValue({ text: '沿著河畔慢慢散步。' })
    const wrapper = mount(JournalNote, { props: { modelValue: '河邊走走', kind: 'trip', label: '隨筆', id: 'notes' } })
    await wrapper.get('[aria-label="AI 潤飾文字"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await wrapper.get('.btn-primary').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['沿著河畔慢慢散步。'])
    await wrapper.setProps({ modelValue: '沿著河畔慢慢散步。' })
    await wrapper.get('.undo-note').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual(['河邊走走'])
    wrapper.unmount()
  })
  it('exposes one image menu and does not impose a 20-photo album limit', () => {
    const wrapper = mount(PhotoPicker, { props: { iconOnly: true } })
    expect(wrapper.findAll('summary')).toHaveLength(1)
    expect(wrapper.get('.photo-source-options').text()).toContain('拍照')
    expect(wrapper.get('.photo-source-options').text()).toContain('從圖庫選取')
    expect(wrapper.text()).not.toContain('/20')
    wrapper.unmount()
  })
  it('recovers a pending request after remount and never sends it again', async () => {
    localStorage.setItem('travelmemo.chat.owner', 'conversation')
    vi.spyOn(api, 'listConversations').mockResolvedValue({ items: [{ id: 'conversation', title: '舊對話', created_at: '' }] })
    vi.spyOn(api, 'listMessages').mockResolvedValue({ items: [] })
    const job = { id: 'request', conversation_id: 'conversation', status: 'running' as const, message: null, error: null }
    vi.spyOn(api, 'listChatRequests').mockResolvedValue({ items: [job] })
    const get = vi.spyOn(api, 'getChatRequest').mockResolvedValue(job)
    const enqueue = vi.spyOn(api, 'enqueueMessage')
    const first = mount(ConversationView, { props: { accountId: 'owner' } })
    await flushPromises()
    expect(get).toHaveBeenCalledWith('conversation', 'request')
    first.unmount()
    get.mockResolvedValue({ ...job, status: 'completed', message: { id: 'answer', role: 'assistant', content: '旅程仍在這裡。', status: 'answered', citations: [], created_at: '', answer_scope: 'general' } })
    const second = mount(ConversationView, { props: { accountId: 'owner' } })
    await flushPromises()
    expect(second.text()).toContain('旅程仍在這裡。')
    expect(second.find('.answer-scope-pill').exists()).toBe(false)
    expect(enqueue).not.toHaveBeenCalled()
    second.unmount()
  })
})
