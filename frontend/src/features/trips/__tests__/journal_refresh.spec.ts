import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TripDialog from '@/features/trips/TripDialog.vue'
import JournalNote from '@/features/trips/JournalNote.vue'
import PhotoPicker from '@/features/media/PhotoPicker.vue'
import EventDialog from '@/features/footprints/EventDialog.vue'
import ConversationView from '@/features/chat/ConversationView.vue'
import * as auth from '@/api/auth'
import * as api from '@/api/conversation'
import * as photos from '@/api/photos'
import type { PhotoDTO } from '@/types/photo'

describe('Journal editing and resumable chat', () => {
  beforeEach(() => { vi.restoreAllMocks(); localStorage.clear() })
  afterEach(() => { vi.useRealTimers() })
  it('updates the cover for the trip being edited', async () => {
    const trip = { id: 'edited-trip', name: 'Trip', start_date: '2026-01-01', end_date: '2026-01-02', timezone: 'Asia/Taipei', description: '', version: 1 }
    const photo = { id: 'uploaded-cover' } as PhotoDTO
    const bind = vi.spyOn(photos, 'bindPhoto').mockResolvedValue(photo)
    const set = vi.spyOn(photos, 'setTripCover').mockResolvedValue({ photo_id: photo.id })
    const wrapper = mount(TripDialog, { props: { visible: true, trip } })
    wrapper.findComponent(PhotoPicker).vm.$emit('upload-complete', photo)
    await flushPromises()
    expect(bind).toHaveBeenCalledWith(photo.id, 'trip', trip.id)
    expect(set).toHaveBeenCalledWith(trip.id, photo.id)
    expect(wrapper.emitted('cover-updated')?.[0]).toEqual([{ tripId: trip.id, photoId: photo.id }])
    expect(wrapper.get('.cover-preview').attributes('src')).toContain(photo.id)
    wrapper.unmount()
  })
  it('edits location independently and preserves place identity for note-only changes', async () => {
    const event = { id: 'event', trip_id: 'trip', place_id: 'original', place_name: '河邊', city: '', address: '', category: '景點', date: '2026-01-01', time: null, notes: '', position: 0, version: 1 }
    const wrapper = mount(EventDialog, { props: { visible: true, trip: { id: 'trip', name: '旅程', start_date: '2026-01-01', end_date: '2026-01-02', timezone: 'Asia/Taipei', description: '', version: 1 }, event } })
    expect(wrapper.get('.more-details').attributes('open')).toBeUndefined()
    expect(wrapper.find('#existing-place-select').exists()).toBe(false)
    await wrapper.get('#event-notes').setValue('舒服')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ place_id: 'original', notes: '舒服' })
    await wrapper.get('#event-place-name').setValue('山邊')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({ place_id: null, place_name: '山邊', version: 1 })
    await wrapper.setProps({ event: { ...event, city: '京都' } })
    expect(wrapper.get('.more-details').attributes('open')).toBeDefined()
    wrapper.unmount()
  })
  it('closes the image menu outside or on Escape, but keeps internal clicks usable', async () => {
    const wrapper = mount(PhotoPicker, { attachTo: document.body, props: { iconOnly: true } })
    const menu = wrapper.get('details').element as HTMLDetailsElement
    menu.open = true
    wrapper.get('summary').element.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(menu.open).toBe(true)
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(menu.open).toBe(false)
    menu.open = true
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(menu.open).toBe(false)
    wrapper.unmount()
  })
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
  it('covers the screen while polishing and removes the mask after failure', async () => {
    let reject!: (reason: unknown) => void
    vi.spyOn(auth, 'request').mockReturnValue(new Promise((_, fail) => { reject = fail }))
    const wrapper = mount(JournalNote, { props: { modelValue: '散步', kind: 'event', label: '隨筆', id: 'busy-note' } })
    await wrapper.get('[aria-label="AI 潤飾文字"]').trigger('click')
    expect(wrapper.get('.polish-mask').attributes('aria-busy')).toBe('true')
    expect(wrapper.find('.polish-spinner').exists()).toBe(true)
    reject(new Error('offline'))
    await flushPromises()
    expect(wrapper.find('.polish-mask').exists()).toBe(false)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
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
