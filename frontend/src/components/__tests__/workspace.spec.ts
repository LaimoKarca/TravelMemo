import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TripWorkspace from '../TripWorkspace.vue'
import TripDialog from '../TripDialog.vue'
import EventDialog from '../EventDialog.vue'
import ConfirmDialog from '../ConfirmDialog.vue'
import * as travelApi from '../../api/travel'
import type { Trip, Event, Place } from '../../types/travel'

const mockUser = {
  id: 'u-lead-1',
  email: 'traveler@travelmemo.local'
}

const mockTrips: Trip[] = [
  {
    id: 'trip-1',
    name: '京都秋楓巡禮',
    start_date: '2026-11-20',
    end_date: '2026-11-24',
    timezone: 'Asia/Tokyo',
    description: '漫步哲學之道與嵐山竹林',
    version: 1
  },
  {
    id: 'trip-2',
    name: '台東縱谷慢旅',
    start_date: '2026-12-10',
    end_date: '2026-12-12',
    timezone: 'Asia/Taipei',
    description: '鹿野高台與溫泉體驗',
    version: 1
  }
]

const mockPlaces: Place[] = [
  {
    id: 'place-1',
    name: '清水寺',
    city: '京都市',
    address: '東山區清水1丁目294'
  },
  {
    id: 'place-2',
    name: '金閣寺',
    city: '京都市',
    address: '北區金閣寺町1'
  }
]

const mockEvents: Event[] = [
  {
    id: 'event-1',
    trip_id: 'trip-1',
    place_id: 'place-1',
    place_name: '清水寺',
    city: '京都市',
    address: '東山區清水1丁目294',
    category: '景點',
    date: '2026-11-20',
    time: '09:00',
    notes: '早上人潮較少',
    position: 0,
    version: 1
  },
  {
    id: 'event-2',
    trip_id: 'trip-1',
    place_id: 'place-2',
    place_name: '金閣寺',
    city: '京都市',
    address: '北區金閣寺町1',
    category: '景點',
    date: '2026-11-20',
    time: '14:00',
    notes: '午後陽光照射金碧輝煌',
    position: 1,
    version: 1
  },
  {
    id: 'event-3',
    trip_id: 'trip-1',
    place_id: 'place-3',
    place_name: '嵐山天龍寺',
    city: '京都市',
    address: '右京區嵯峨天龍寺芒之馬場町68',
    category: '文化',
    date: '2026-11-21',
    time: null,
    notes: '欣賞庭園造景',
    position: 0,
    version: 1
  }
]

describe('TripWorkspace and Travel Components', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: [...mockTrips] })
    vi.spyOn(travelApi, 'listPlaces').mockResolvedValue({ items: [...mockPlaces] })
    vi.spyOn(travelApi, 'getTrip').mockResolvedValue({
      trip: { ...mockTrips[0] },
      events: [...mockEvents],
      next_edges: [
        { from_id: 'event-1', to_id: 'event-2' },
        { from_id: 'event-2', to_id: 'event-3' }
      ]
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders user email, logout button, and trip list on mount', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('traveler@travelmemo.local')
    expect(wrapper.text()).toContain('我的旅行手記')
    expect(wrapper.text()).toContain('京都秋楓巡禮')
    expect(wrapper.text()).toContain('台東縱谷慢旅')

    // Click logout button emits logout
    const logoutBtn = wrapper.find('button.logout-button')
    expect(logoutBtn.exists()).toBe(true)
    await logoutBtn.trigger('click')
    expect(wrapper.emitted('logout')).toBeTruthy()
  })

  it('opens trip detail timeline when clicking a trip card', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    const tripCards = wrapper.findAll('.trip-card')
    expect(tripCards.length).toBe(2)

    await tripCards[0].trigger('click')
    await flushPromises()

    // Now in detail timeline view
    expect(travelApi.getTrip).toHaveBeenCalledWith('trip-1')
    expect(wrapper.text()).toContain('京都秋楓巡禮')
    expect(wrapper.text()).toContain('Day 1')
    expect(wrapper.text()).toContain('清水寺')
    expect(wrapper.text()).toContain('金閣寺')
    expect(wrapper.text()).toContain('嵐山天龍寺')
    expect(wrapper.text()).toContain('接續足跡：金閣寺')
  })

  it('supports filtering events by city and category in current trip', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    // Enter trip detail
    await wrapper.findAll('.trip-card')[0].trigger('click')
    await flushPromises()

    const categorySelect = wrapper.find('#category-filter')
    expect(categorySelect.exists()).toBe(true)

    // Filter to '文化'
    await categorySelect.setValue('文化')
    await flushPromises()

    expect(wrapper.text()).toContain('嵐山天龍寺')
    expect(wrapper.text()).not.toContain('清水寺')
    expect(wrapper.text()).toContain('顯示 1 / 3 處旅途足跡')

    // Click clear filters
    const clearBtn = wrapper.find('.clear-filters-btn')
    expect(clearBtn.exists()).toBe(true)
    await clearBtn.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('清水寺')
    expect(wrapper.text()).toContain('顯示 3 / 3 處旅途足跡')
  })

  it('performs same-day move up / move down with active filters without discarding hidden IDs', async () => {
    // 3 events on Day 1: E1 (景點), E2 (美食), E3 (景點)
    const day1Events: Event[] = [
      {
        id: 'e-1',
        trip_id: 'trip-1',
        place_id: 'p-1',
        place_name: '清水寺',
        city: '京都市',
        address: '',
        category: '景點',
        date: '2026-11-20',
        time: '09:00',
        notes: '',
        position: 0,
        version: 1
      },
      {
        id: 'e-2',
        trip_id: 'trip-1',
        place_id: 'p-2',
        place_name: '錦市場午餐',
        city: '京都市',
        address: '',
        category: '美食',
        date: '2026-11-20',
        time: '12:00',
        notes: '',
        position: 1,
        version: 1
      },
      {
        id: 'e-3',
        trip_id: 'trip-1',
        place_id: 'p-3',
        place_name: '金閣寺',
        city: '京都市',
        address: '',
        category: '景點',
        date: '2026-11-20',
        time: '15:00',
        notes: '',
        position: 2,
        version: 1
      }
    ]

    vi.spyOn(travelApi, 'getTrip').mockResolvedValue({
      trip: { ...mockTrips[0] },
      events: day1Events,
      next_edges: []
    })

    const reorderSpy = vi.spyOn(travelApi, 'reorderEvents').mockResolvedValue({
      trip: { ...mockTrips[0], version: 2 },
      events: [day1Events[0], day1Events[2], day1Events[1]],
      next_edges: []
    })

    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    // Select trip-1
    await wrapper.findAll('.trip-card')[0].trigger('click')
    await flushPromises()

    // Filter to '景點' -> hides e-2 (錦市場午餐)
    await wrapper.find('#category-filter').setValue('景點')
    await flushPromises()

    // Only e-1 and e-3 are visible
    expect(wrapper.text()).toContain('清水寺')
    expect(wrapper.text()).not.toContain('錦市場午餐')
    expect(wrapper.text()).toContain('金閣寺')

    // Find reorder buttons for visible cards
    // e-1 is at position 0 in full day -> canMoveUp is false, canMoveDown is true
    // e-3 is at position 2 in full day -> canMoveUp is true, canMoveDown is false
    const reorderButtons = wrapper.findAll('.btn-reorder')
    // e-1: move up disabled, move down enabled
    expect((reorderButtons[0].element as HTMLButtonElement).disabled).toBe(true)
    expect((reorderButtons[1].element as HTMLButtonElement).disabled).toBe(false)

    // e-3: move up enabled, move down disabled
    expect((reorderButtons[2].element as HTMLButtonElement).disabled).toBe(false)
    expect((reorderButtons[3].element as HTMLButtonElement).disabled).toBe(true)

    // Click "Move Up" on e-3 (金閣寺)
    await reorderButtons[2].trigger('click')
    await flushPromises()

    // It swaps with its real adjacent sibling e-2 in full day, keeping e-1 first!
    // And e-2 is NOT discarded! All 3 IDs are preserved!
    expect(reorderSpy).toHaveBeenCalledWith('trip-1', {
      version: 1,
      event_ids: ['e-1', 'e-3', 'e-2']
    })
  })

  it('TripDialog manages focus: traps Tab/Shift+Tab, focuses first input, restores launcher on close', async () => {
    // Create launcher button in DOM
    const launcher = document.createElement('button')
    launcher.id = 'open-trip-dialog-btn'
    document.body.appendChild(launcher)
    launcher.focus()
    expect(document.activeElement).toBe(launcher)

    const wrapper = mount(TripDialog, {
      props: { visible: true, trip: null },
      attachTo: document.body
    })
    await flushPromises()

    // First input should be focused
    const nameInput = wrapper.find('#trip-name-input').element as HTMLInputElement
    expect(document.activeElement).toBe(nameInput)

    const dialogCard = wrapper.find('.dialog-card').element as HTMLElement

    // Test Tab wrap: focus last focusable element
    const focusables = dialogCard.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])'
    )
    const firstFocusable = focusables[0]
    const lastFocusable = focusables[focusables.length - 1]

    lastFocusable.focus()
    expect(document.activeElement).toBe(lastFocusable)

    // Tab on last element -> wraps to first
    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true })
    window.dispatchEvent(tabEvent)
    await flushPromises()
    expect(document.activeElement).toBe(firstFocusable)

    // Shift+Tab on first element -> wraps to last
    const shiftTabEvent = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true })
    window.dispatchEvent(shiftTabEvent)
    await flushPromises()
    expect(document.activeElement).toBe(lastFocusable)

    // Test Escape key -> emits cancel and restores focus
    const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    window.dispatchEvent(escapeEvent)
    await flushPromises()

    expect(wrapper.emitted('cancel')).toBeTruthy()

    // Close modal
    await wrapper.setProps({ visible: false })
    await flushPromises()

    expect(document.activeElement).toBe(launcher)
    wrapper.unmount()
  })

  it('TripDialog validates form fields and successfully emits submit on save', async () => {
    const wrapper = mount(TripDialog, {
      props: { visible: true, trip: null }
    })
    await flushPromises()

    // Fill valid values
    await wrapper.find('#trip-name-input').setValue('北海道小樽冬日漫步')
    await wrapper.find('#trip-start-date').setValue('2026-12-20')
    await wrapper.find('#trip-end-date').setValue('2026-12-25')
    await wrapper.find('#trip-description').setValue('運河雪景與玻璃工藝')

    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')![0][0]).toEqual({
      name: '北海道小樽冬日漫步',
      start_date: '2026-12-20',
      end_date: '2026-12-25',
      timezone: 'Asia/Taipei',
      description: '運河雪景與玻璃工藝'
    })
  })

  it('TripDialog preserves entered values on optimistic 409 conflict and offers refresh', async () => {
    const wrapper = mount(TripDialog, {
      props: { visible: true, trip: mockTrips[0] }
    })
    await flushPromises()

    // User types new modifications
    await wrapper.find('#trip-name-input').setValue('京都楓葉修改草稿')
    await wrapper.find('#trip-description').setValue('新增比叡山延曆寺停留筆記')

    // 409 conflict arrives from API
    await wrapper.setProps({
      hasConflict: true,
      errorMessage: '旅程資料已被其他操作更新。'
    })
    await flushPromises()

    // Verify entered values were NOT wiped out or overwritten
    expect((wrapper.find('#trip-name-input').element as HTMLInputElement).value).toBe('京都楓葉修改草稿')
    expect((wrapper.find('#trip-description').element as HTMLTextAreaElement).value).toBe('新增比叡山延曆寺停留筆記')

    // Verify conflict banner and refresh button
    expect(wrapper.find('.conflict-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('此旅程資料已在其他地方更新')

    const refreshBtn = wrapper.find('.conflict-refresh-btn')
    expect(refreshBtn.exists()).toBe(true)
    await refreshBtn.trigger('click')

    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('EventDialog preserves entered values on optimistic 409 conflict and offers refresh', async () => {
    const wrapper = mount(EventDialog, {
      props: {
        visible: true,
        trip: mockTrips[0],
        event: mockEvents[0],
        places: mockPlaces
      }
    })
    await flushPromises()

    // User edits notes and category
    await wrapper.find('#event-notes').setValue('夕陽西下時分非常壯觀，值得再訪！')
    await wrapper.find('#event-category').setValue('攝影')

    // 409 conflict arrives
    await wrapper.setProps({
      hasConflict: true,
      errorMessage: '此處旅途足跡已在其他地方更新。'
    })
    await flushPromises()

    // Unsaved user inputs are preserved
    expect((wrapper.find('#event-notes').element as HTMLTextAreaElement).value).toBe('夕陽西下時分非常壯觀，值得再訪！')
    expect((wrapper.find('#event-category').element as HTMLInputElement).value).toBe('攝影')

    expect(wrapper.find('.conflict-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('此段旅途紀錄已在其他地方更新')

    await wrapper.find('.conflict-refresh-btn').trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('ConfirmDialog manages focus trap, escape, and emits confirm', async () => {
    const launcher = document.createElement('button')
    launcher.id = 'delete-launcher'
    document.body.appendChild(launcher)
    launcher.focus()

    const wrapper = mount(ConfirmDialog, {
      props: {
        visible: true,
        title: '確認刪除旅行手記',
        message: '此動作無法還原'
      },
      attachTo: document.body
    })
    await flushPromises()

    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBe(2)

    // Escape closes modal and restores launcher
    const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    window.dispatchEvent(escapeEvent)
    await flushPromises()
    expect(wrapper.emitted('cancel')).toBeTruthy()

    await wrapper.setProps({ visible: false })
    await flushPromises()
    expect(document.activeElement).toBe(launcher)

    wrapper.unmount()
  })
})
