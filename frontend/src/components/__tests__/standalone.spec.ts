import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import EventDialog from '../EventDialog.vue'
import SourceDetailModal from '../SourceDetailModal.vue'
import * as search from '../../api/search'
import * as photos from '../../api/photos'
import * as travel from '../../api/travel'
import StandaloneFootprints from '../StandaloneFootprints.vue'
import type { Event } from '../../types/travel'

const footprint: Event = {
  id: 'sunset', trip_id: null, position: null, place_id: 'coast', place_name: '海邊堤防',
  city: '', address: '', category: '未分類', date: '2026-11-21', time: null,
  timezone: 'Asia/Taipei', record_scope: 'standalone', notes: '臨時去看夕陽', version: 1,
}

enableAutoUnmount(afterEach)
afterEach(() => vi.restoreAllMocks())

describe('日常足跡', () => {
  it('只開啟一個操作選單，點空白處或按 Escape 可收合', async () => {
    vi.spyOn(travel, 'listStandaloneEvents').mockResolvedValue({
      items: [footprint, { ...footprint, id: 'second', place_name: '海邊步道' }], next_offset: null,
    })
    const wrapper = mount(StandaloneFootprints, { attachTo: document.body })
    await flushPromises()
    const [first, second] = wrapper.findAll<HTMLButtonElement>('.daily-menu-trigger')
    await first.trigger('click')
    expect(first.attributes('aria-expanded')).toBe('true')
    await second.trigger('click')
    expect(first.attributes('aria-expanded')).toBe('false')
    expect(second.attributes('aria-expanded')).toBe('true')
    await wrapper.get('.daily-header').trigger('pointerdown')
    expect(second.attributes('aria-expanded')).toBe('false')
    await first.trigger('click')
    await wrapper.get('.daily-menu button').trigger('keydown', { key: 'Escape' })
    expect(first.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(first.element)
  })

  it('只填地點即可記錄，保留未知抵達時間', async () => {
    const wrapper = mount(EventDialog, { props: { visible: true } })
    await wrapper.get('#event-place-name').setValue('海邊堤防')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      place_name: '海邊堤防', category: '未分類', date: expect.stringMatching(/^\d{4}-\d\d-\d\d$/),
      timezone: 'Asia/Taipei', time: null,
    })
  })

  it('來源詳情可跳到未歸入手記的足跡', async () => {
    vi.spyOn(photos, 'listPhotos').mockResolvedValue({ items: [] })
    vi.spyOn(search, 'getEvent').mockResolvedValue(footprint)
    const wrapper = mount(SourceDetailModal, { props: { visible: true, eventId: footprint.id } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('所屬手記')
    const button = wrapper.get('.jump-btn')
    expect(button.text()).toBe('前往足跡')
    await button.trigger('click')
    expect(wrapper.emitted('jump')).toEqual([[{ tripId: null, eventId: footprint.id }]])
  })

  it('能定位不在第一頁的足跡並繼續載入', async () => {
    const list = vi.spyOn(travel, 'listStandaloneEvents')
      .mockResolvedValueOnce({ items: [], next_offset: 20 })
      .mockResolvedValueOnce({ items: [footprint], next_offset: null })
    vi.spyOn(travel, 'getEvent').mockResolvedValue(footprint)
    const wrapper = mount(StandaloneFootprints, { props: { focusId: footprint.id } })
    await flushPromises()
    expect(wrapper.get('[data-focused=true]').text()).toContain('海邊堤防')
    await wrapper.get('.load-more').trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 20, offset: 20 }))
    expect(wrapper.findAll('.daily-entry')).toHaveLength(1)
  })
})
