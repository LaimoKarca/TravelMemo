import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, enableAutoUnmount } from '@vue/test-utils'
import TripWorkspace from '../TripWorkspace.vue'
import StatusAlert from '../StatusAlert.vue'
import ConfirmDialog from '../ConfirmDialog.vue'
import * as travel from '../../api/travel'
import * as photos from '../../api/photos'

const trip = { id: 't1', name: '京都慢旅', start_date: '2026-11-01', end_date: '2026-11-03', timezone: 'Asia/Tokyo', description: '河邊散步', version: 1 }
const detail = { trip, events: [], next_edges: [] }
const user = { id: 'u1', email: 'tester@example.com' }
enableAutoUnmount(afterEach)

beforeEach(() => {
  vi.spyOn(travel, 'listTrips').mockResolvedValue({ items: [trip] })
  vi.spyOn(travel, 'getTrip').mockResolvedValue(detail)
  vi.spyOn(photos, 'listPhotos').mockResolvedValue({ items: [] })
  vi.spyOn(photos, 'getTripCover').mockResolvedValue({ photo_id: null })
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); document.body.innerHTML = '' })

describe('compact journal interactions', () => {
  it('keeps loading below search and hides existing cards during a refresh', async () => {
    const w = mount(TripWorkspace, { props: { user } })
    await flushPromises()
    await w.get('.trip-card').trigger('click')
    await flushPromises()
    let finish!: (value: { items: typeof trip[] }) => void
    vi.mocked(travel.listTrips).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await w.get('#workspace-tab-trips').trigger('click')
    expect(w.find('.trip-list-section').exists()).toBe(true)
    expect(w.find('.library-search-bar').exists()).toBe(true)
    expect(w.find('.trip-card').exists()).toBe(false)
    const html = w.get('.trip-list-section').html()
    expect(html.indexOf('library-search-bar')).toBeLessThan(html.indexOf('loading-state'))
    finish({ items: [trip] })
    await flushPromises()
    expect(w.find('.trip-card').exists()).toBe(true)
    expect(w.find('.loading-state').exists()).toBe(false)
  })

  it.each(['.sidebar-brand', '.mobile-brand'])('returns home through %s and ignores an old detail request', async (selector) => {
    const w = mount(TripWorkspace, { props: { user } })
    await flushPromises()
    let finish!: (value: typeof detail) => void
    vi.mocked(travel.getTrip).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    await w.get('.trip-card').trigger('click')
    expect(w.get('.trip-detail-loading').text()).toContain('載入手記中')
    await w.get(selector).trigger('click')
    finish(detail)
    await flushPromises()
    expect(w.find('.trip-list-section').exists()).toBe(true)
    expect(w.find('.trip-detail-section').exists()).toBe(false)
    expect(w.find('.banner-trip-name').exists()).toBe(false)
  })

  it('floats notices over dialogs, resets the timeout and leaves errors dismissible', async () => {
    vi.useFakeTimers()
    const w = mount(StatusAlert, { props: { floating: true, message: '已更新照片說明。', type: 'success', noticeKey: 1 }, attachTo: document.body })
    expect(document.body.querySelector('.workspace-notice')).not.toBeNull()
    await vi.advanceTimersByTimeAsync(1500)
    await w.setProps({ noticeKey: 2 })
    await vi.advanceTimersByTimeAsync(1500)
    expect(w.emitted('dismiss')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(500)
    expect(w.emitted('dismiss')).toHaveLength(1)
    await w.setProps({ message: '儲存失敗', type: 'error', noticeKey: 3 })
    await vi.advanceTimersByTimeAsync(4000)
    expect(w.emitted('dismiss')).toHaveLength(1)
    ;(document.body.querySelector('button[aria-label="關閉通知"]') as HTMLButtonElement).click()
    expect(w.emitted('dismiss')).toHaveLength(2)
  })

  it('places destructive confirmation before cancel while initially focusing cancel', async () => {
    const w = mount(ConfirmDialog, { props: { visible: true, title: '刪除照片', message: '刪除無法復原', confirmFirst: true }, attachTo: document.body })
    await flushPromises()
    const buttons = w.findAll('button')
    expect(buttons.map(b => b.text())).toEqual(['確定', '取消'])
    expect(document.activeElement).toBe(buttons[1].element)
  })
})
