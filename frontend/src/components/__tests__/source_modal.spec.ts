import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SourceDetailModal from '../SourceDetailModal.vue'
import * as searchApi from '../../api/search'
import { ApiError } from '../../api/auth'
import type { SearchEvent } from '../../types/search'

const mockEvent: SearchEvent = {
  id: 'evt-101',
  trip_id: 'trip-101',
  place_id: 'place-101',
  place_name: '嵐山竹林小徑',
  city: '京都市',
  address: '右京區嵯峨小倉山田淵山町',
  category: '景點',
  date: '2026-11-22',
  time: '08:30',
  notes: '清晨微光灑落竹葉間，非常幽靜。',
  position: 0,
  version: 2,
  trip_name: '京都楓紅之旅'
}

describe('SourceDetailModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(searchApi, 'getEvent').mockResolvedValue(mockEvent)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders initial event preview and always refetches fresh event data', async () => {
    const previewEvent: SearchEvent = {
      ...mockEvent,
      notes: '搜尋快照預覽備忘',
      version: 1
    }

    const freshEvent: SearchEvent = {
      ...mockEvent,
      notes: '伺服器端最新修訂備忘',
      version: 2
    }

    const getEventSpy = vi.spyOn(searchApi, 'getEvent').mockResolvedValue(freshEvent)

    const wrapper = mount(SourceDetailModal, {
      props: {
        visible: true,
        initialEvent: previewEvent
      }
    })

    // Immediately shows initial preview
    expect(wrapper.text()).toContain('嵐山竹林小徑')
    expect(wrapper.text()).toContain('搜尋快照預覽備忘')

    await flushPromises()

    // Always refetched from server to get authoritative latest version
    expect(getEventSpy).toHaveBeenCalledWith('evt-101')
    expect(wrapper.text()).toContain('伺服器端最新修訂備忘')
    expect(wrapper.text()).toContain('第 2 版')
  })

  it('fetches event by eventId when initialEvent is not provided', async () => {
    const getEventSpy = vi.spyOn(searchApi, 'getEvent').mockResolvedValue(mockEvent)

    const wrapper = mount(SourceDetailModal, {
      props: {
        visible: true,
        eventId: 'evt-101'
      }
    })
    await flushPromises()

    expect(getEventSpy).toHaveBeenCalledWith('evt-101')
    expect(wrapper.text()).toContain('嵐山竹林小徑')
  })

  it('handles deleted 404 event clearly and hides jump button', async () => {
    vi.spyOn(searchApi, 'getEvent').mockRejectedValue(new ApiError(404, '找不到指定的旅程或行程資料。'))

    const wrapper = mount(SourceDetailModal, {
      props: {
        visible: true,
        eventId: 'evt-deleted'
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('此足跡紀錄已自旅程中移除（找不到此事件或已刪除）。')
    expect(wrapper.find('button.jump-btn').exists()).toBe(false)
  })

  it('guards loadEvent by request generation and does not let late A result overwrite B after modal reopen', async () => {
    let resolveA!: (val: SearchEvent) => void
    const promiseA = new Promise<SearchEvent>((resolve) => {
      resolveA = resolve
    })

    const eventB: SearchEvent = {
      ...mockEvent,
      id: 'evt-B',
      place_name: '清水寺本堂',
      trip_name: '京都秋天'
    }

    const getEventSpy = vi.spyOn(searchApi, 'getEvent')
      .mockReturnValueOnce(promiseA)
      .mockResolvedValueOnce(eventB)

    const wrapper = mount(SourceDetailModal, {
      props: {
        visible: true,
        eventId: 'evt-A'
      }
    })

    // Close modal while request A is in-flight
    await wrapper.setProps({ visible: false })

    // Reopen modal for event B
    await wrapper.setProps({ visible: true, eventId: 'evt-B' })
    await flushPromises()

    expect(wrapper.text()).toContain('清水寺本堂')

    // Request A finishes late
    resolveA({
      ...mockEvent,
      id: 'evt-A',
      place_name: '已過期的舊足跡 A'
    })
    await flushPromises()

    // Must NOT be overwritten by late A response
    expect(wrapper.text()).toContain('清水寺本堂')
    expect(wrapper.text()).not.toContain('已過期的舊足跡 A')
  })

  it('emits jump with tripId and eventId when clicking jump button', async () => {
    const wrapper = mount(SourceDetailModal, {
      props: {
        visible: true,
        initialEvent: mockEvent
      }
    })
    await flushPromises()

    const jumpBtn = wrapper.find('button.jump-btn')
    expect(jumpBtn.exists()).toBe(true)
    await jumpBtn.trigger('click')

    expect(wrapper.emitted('jump')).toBeTruthy()
    expect(wrapper.emitted('jump')![0][0]).toEqual({
      tripId: 'trip-101',
      eventId: 'evt-101'
    })
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('manages focus trap and Escape key', async () => {
    const launcher = document.createElement('button')
    launcher.id = 'source-launcher'
    document.body.appendChild(launcher)
    launcher.focus()

    const wrapper = mount(SourceDetailModal, {
      props: {
        visible: true,
        initialEvent: mockEvent
      },
      attachTo: document.body
    })
    await flushPromises()

    // Escape emits close
    const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    window.dispatchEvent(escapeEvent)
    await flushPromises()

    expect(wrapper.emitted('close')).toBeTruthy()

    await wrapper.setProps({ visible: false })
    await flushPromises()
    expect(document.activeElement).toBe(launcher)

    wrapper.unmount()
  })
})
