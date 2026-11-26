import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import TripWorkspace from '@/app/workspace/TripWorkspace.vue'
import TripDialog from '@/features/trips/TripDialog.vue'
import EventDialog from '@/features/footprints/EventDialog.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import * as travelApi from '@/api/travel'
import * as convApi from '@/api/conversation'
import * as searchApi from '@/api/search'
import * as timezones from '@/utils/timezones'
import * as photosApi from '@/api/photos'
import type { TripListItem, Event, Place } from '@/types/travel'

const mockUser = {
  id: 'u-lead-1',
  email: 'traveler@travelmemo.local'
}

const mockTrips: TripListItem[] = [
  {
    id: 'trip-1',
    name: '京都秋楓巡禮',
    start_date: '2026-11-20',
    end_date: '2026-11-24',
    timezone: 'Asia/Tokyo',
    description: '漫步哲學之道與嵐山竹林',
    cover_photo_id: null,
    version: 1
  },
  {
    id: 'trip-2',
    name: '台東縱谷慢旅',
    start_date: '2026-12-10',
    end_date: '2026-12-12',
    timezone: 'Asia/Taipei',
    description: '鹿野高台與溫泉體驗',
    cover_photo_id: null,
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

enableAutoUnmount(afterEach)

describe('TripWorkspace and Travel Components', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: [...mockTrips] })
    vi.spyOn(travelApi, 'listStandaloneEvents').mockResolvedValue({ items: [], next_offset: null })
    vi.spyOn(travelApi, 'listPlaces').mockResolvedValue({ items: [...mockPlaces] })
    vi.spyOn(photosApi, 'listPhotos').mockResolvedValue({ items: [] })
    vi.spyOn(photosApi, 'getTripCover').mockResolvedValue({ photo_id: null })
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: [] })
    vi.spyOn(convApi, 'getUsage').mockResolvedValue({
      date: '2026-11-20',
      requests: 0,
      input_tokens: 0,
      output_tokens: 0,
      daily_limit: 50,
      model: 'gpt-6-luna'
    })
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({ items: [] })
    vi.spyOn(searchApi, 'searchRecall').mockResolvedValue({
      items: [],
      clarification: null,
      vector_status: 'ready'
    })
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
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('renders the account name without the email domain, logout, and trip list', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('traveler')
    expect(wrapper.html()).not.toContain('traveler@travelmemo.local')
    expect(wrapper.text()).toContain('我的旅行手記')
    expect(wrapper.text()).toContain('京都秋楓巡禮')
    expect(wrapper.text()).toContain('台東縱谷慢旅')

    // Click logout button emits logout
    const logoutBtn = wrapper.find('button.logout-button')
    expect(logoutBtn.exists()).toBe(true)
    await logoutBtn.trigger('click')
    expect(wrapper.emitted('logout')).toBeTruthy()
  })

  it('keeps library filters collapsed and applies or clears them without clearing the query', async () => {
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    const toggle = wrapper.get('button[aria-controls="library-filters"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    await wrapper.get('input[aria-label="搜尋旅行手記"]').setValue('京都')
    await wrapper.get('select[aria-label="篩選旅程年份"]').setValue('2026')
    expect(toggle.attributes('aria-label')).toContain('已套用')
    await toggle.trigger('click')
    expect(wrapper.get('.trip-cards-grid').text()).toContain('京都')
    await toggle.trigger('click')
    await wrapper.get('.library-reset').trigger('click')
    expect(toggle.attributes('aria-label')).toBe('篩選手記')
    expect((wrapper.get('input[type=search]').element as HTMLInputElement).value).toBe('京都')
    wrapper.unmount()
  })

  it('opens trip detail timeline when clicking a trip card', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    const tripCards = wrapper.findAll('.trip-card')
    expect(tripCards.length).toBe(2)

    await wrapper.find('[aria-label="檢視手記：京都秋楓巡禮"]').trigger('click')
    await flushPromises()

    // Now in detail timeline view
    expect(travelApi.getTrip).toHaveBeenCalledWith('trip-1')
    expect(wrapper.text()).toContain('京都秋楓巡禮')
    expect(wrapper.text()).toContain('Day 1')
    expect(wrapper.text()).toContain('清水寺')
    expect(wrapper.text()).toContain('金閣寺')
    expect(wrapper.text()).toContain('嵐山天龍寺')
    expect(wrapper.find('.next-destination-indicator').exists()).toBe(false)
  })

  it('collapses only the chosen day and restores it with the same button', async () => {
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    await wrapper.get('.trip-card').trigger('click')
    await flushPromises()

    const dayOne = wrapper.get('button[aria-controls="trip-day-2026-11-20"]')
    const firstStream = wrapper.get<HTMLElement>('#trip-day-2026-11-20').element
    const secondStream = wrapper.get<HTMLElement>('#trip-day-2026-11-21').element
    expect(dayOne.attributes('aria-expanded')).toBe('true')
    expect(firstStream.style.display).not.toBe('none')

    await dayOne.trigger('click')
    expect(dayOne.attributes('aria-expanded')).toBe('false')
    expect(firstStream.style.display).toBe('none')
    expect(secondStream.style.display).not.toBe('none')

    await dayOne.trigger('click')
    expect(dayOne.attributes('aria-expanded')).toBe('true')
    expect(firstStream.style.display).not.toBe('none')
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

  it('searches within the current trip together with city and category filters', async () => {
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    await wrapper.findAll('.trip-card')[0].trigger('click')
    await flushPromises()
    const query = wrapper.get('input[aria-label="搜尋足跡"]')
    expect(wrapper.get('button[aria-controls="event-filter-options"]').attributes('aria-expanded')).toBe('false')
    await query.setValue('午後')
    expect(wrapper.findAll('.event-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('金閣寺')
    await wrapper.get('#city-filter').setValue('京都市')
    await wrapper.get('#category-filter').setValue('文化')
    expect(wrapper.findAll('.event-card')).toHaveLength(0)
    await wrapper.get('.clear-filters-btn').trigger('click')
    expect((query.element as HTMLInputElement).value).toBe('')
    expect(wrapper.findAll('.event-card')).toHaveLength(3)
    await query.setValue('2026-11-21')
    expect(wrapper.findAll('.event-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('嵐山天龍寺')
    await wrapper.get('.back-button').trigger('click')
    await wrapper.findAll('.trip-card')[1].trigger('click')
    await flushPromises()
    expect((wrapper.get('input[aria-label="搜尋足跡"]').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it.each([
    ['2026-11-19T03:00:00Z', ['event-event-1', 'event-event-2', 'event-event-3']],
    ['2026-11-20T03:00:00Z', ['event-event-3', 'event-event-2', 'event-event-1']],
    ['2026-11-25T03:00:00Z', ['event-event-1', 'event-event-2', 'event-event-3']]
  ])('displays the trip in state-based order at %s without rewriting its route', async (now, expected) => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date(now))
    const reorder = vi.spyOn(travelApi, 'reorderEvents')
    const original = mockEvents.map(e => ({ ...e }))
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    await wrapper.findAll('.trip-card')[0].trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.event-card').map(e => e.attributes('id'))).toEqual(expected)
    expect(wrapper.find('.btn-reorder').exists()).toBe(false)
    expect(wrapper.find('.next-destination-indicator').exists()).toBe(false)
    await wrapper.get('#category-filter').setValue('景點')
    expect(wrapper.findAll('.event-card').map(e => e.attributes('id'))).toEqual(expected.filter(id => id !== 'event-event-3'))
    expect(reorder).not.toHaveBeenCalled()
    expect(mockEvents).toEqual(original)
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('switches to forward order after the trip-local final day ends', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date('2026-11-24T14:59:30Z'))
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    await wrapper.findAll('.trip-card')[0].trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.event-card')[0].attributes('id')).toBe('event-event-3')
    await vi.advanceTimersByTimeAsync(60000)
    expect(wrapper.findAll('.event-card')[0].attributes('id')).toBe('event-event-1')
    expect(wrapper.findAll('.day-number')[0].text()).toBe('Day 1')
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('offers delete before edit in the footprint header and keeps the city next to the place', async () => {
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    await wrapper.findAll('.trip-card')[0].trigger('click')
    await flushPromises()
    const card = wrapper.findAll('.event-card')[0]
    expect(card.get('.event-place-name').text()).toContain('京都市')
    expect(card.find('.event-footer-actions').exists()).toBe(false)
    const actions = card.findAll('.event-header-actions button')
    expect(actions[0].attributes('aria-label')).toContain('刪除')
    expect(actions[1].attributes('aria-label')).toContain('編輯')
    await actions[0].trigger('click')
    const confirmation = wrapper.findAllComponents(ConfirmDialog).find(dialog => dialog.props('visible'))
    expect(confirmation).toBeDefined()
    confirmation!.vm.$emit('cancel')
    await actions[1].trigger('click')
    expect(wrapper.findComponent(EventDialog).props('visible')).toBe(true)
    wrapper.unmount()
  })

  it('keeps a valid but unsupported timezone readable without guessing its status', async () => {
    const originalStatus = timezones.getTripStatus
    vi.spyOn(timezones, 'getTripStatus').mockImplementation((start, end, zone, now) => {
      if (zone === 'America/Coyhaique') throw new RangeError('Unsupported timezone')
      return originalStatus(start, end, zone, now)
    })
    const trip = { ...mockTrips[0], timezone: 'America/Coyhaique' }
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: [trip] })
    vi.spyOn(travelApi, 'getTrip').mockResolvedValue({ trip, events: mockEvents, next_edges: [] })
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    expect(wrapper.findAll('.trip-card')).toHaveLength(1)
    await wrapper.get('select[aria-label="篩選旅程狀態"]').setValue('current')
    expect(wrapper.findAll('.trip-card')).toHaveLength(0)
    await wrapper.get('select[aria-label="篩選旅程狀態"]').setValue('all')
    await wrapper.get('.trip-card').trigger('click')
    await flushPromises()
    expect(wrapper.get('.timezone-notice').text()).toContain('暫依行程順序顯示')
    expect(wrapper.findAll('.event-card').map(card => card.attributes('id'))).toEqual(['event-event-1', 'event-event-2', 'event-event-3'])
    wrapper.unmount()
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

  it('opens journal editing without input autofocus and keeps footer actions icon-only', async () => {
    const wrapper = mount(TripDialog, { props: { visible: true, trip: mockTrips[0] }, attachTo: document.body })
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[role="dialog"]').element)
    const buttons = wrapper.findAll('.dialog-icon-actions button')
    expect(buttons.map(b => b.attributes('aria-label'))).toEqual(['返回', '儲存修改'])
    expect(buttons.every(b => !b.text() && b.find('svg').exists())).toBe(true)
  })

  it('keeps journal deletion confirmation before cancel', async () => {
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    await wrapper.findAll('.trip-card')[0].get('button[aria-label="刪除手記"]').trigger('click')
    const dialog = wrapper.findAllComponents(ConfirmDialog).find(c => c.props('visible'))!
    expect(dialog.findAll('.dialog-actions button').map(b => b.text())).toEqual(['取消', '刪除手記'])
    expect(dialog.get('input').attributes('aria-label')).toBe('輸入完整手記名稱')
    expect(dialog.findAll('.dialog-actions button')[1].attributes('disabled')).toBeDefined()
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

  it('TripDialog keeps the current timezone and offers a bounded, keyboard-selectable search', async () => {
    const wrapper = mount(TripDialog, {
      props: { visible: true, trip: mockTrips[0] } // mockTrips[0] has timezone: 'Asia/Tokyo'
    })
    await flushPromises()

    const tzInput = wrapper.find('input#trip-timezone')
    expect(tzInput.exists()).toBe(true)
    expect(tzInput.attributes('list')).toBeUndefined()
    expect((tzInput.element as HTMLInputElement).value).toBe('Asia/Tokyo')

    await tzInput.trigger('focus')
    expect(wrapper.findAll('[role="option"]')).toHaveLength(10)
    await tzInput.setValue('臺北')
    expect(wrapper.findAll('[role="option"]').map(option => option.text())).toEqual([expect.stringContaining('Asia/Taipei')])
    await tzInput.setValue('臺')
    expect(wrapper.findAll('[role="option"]').length).toBeLessThanOrEqual(10)
    await tzInput.setValue('臺北')
    await tzInput.trigger('keydown', { key: 'ArrowDown' })
    await tzInput.trigger('keydown', { key: 'Enter' })
    expect((tzInput.element as HTMLInputElement).value).toBe('Asia/Taipei')
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('TripDialog allows typing custom UTC offset and emits normalized value on submit', async () => {
    const wrapper = mount(TripDialog, {
      props: { visible: true, trip: null }
    })
    await flushPromises()

    await wrapper.find('#trip-name-input').setValue('台南古蹟文化行')
    await wrapper.find('#trip-start-date').setValue('2026-11-20')
    await wrapper.find('#trip-end-date').setValue('2026-11-22')
    await wrapper.find('input#trip-timezone').setValue('UTC+8')

    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    const payload = wrapper.emitted('submit')![0][0] as any
    expect(payload.timezone).toBeTruthy()
  })

  it('opens footprint editing without focusing an input and preserves create autofocus', async () => {
    const wrapper = mount(EventDialog, { props: { visible: true, trip: mockTrips[0], event: mockEvents[0] }, attachTo: document.body })
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[role="dialog"]').element)
    await wrapper.setProps({ visible: false, event: null })
    await wrapper.setProps({ visible: true })
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('#event-place-name').element)
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
    expect(wrapper.find('.place-mode-switch').exists()).toBe(false)
    expect(wrapper.find('#existing-place-select').exists()).toBe(false)
    expect(wrapper.find('#event-place-name').attributes('disabled')).toBeUndefined()
    await wrapper.find('.add-tag-button').trigger('click')
    await wrapper.find('[aria-label="新標籤名稱"]').setValue('攝影')
    await wrapper.findAll('.add-tag-button')[1].trigger('click')

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

  it('shows all four destinations in the same order and keeps the journal home', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()

    const navTabs = wrapper.findAll('.nav-tab-btn')
    expect(navTabs.map(tab => tab.text())).toEqual(['旅行手記', '日常足跡', '回憶搜尋', 'AI 助理'])
    expect(wrapper.findAll('.mobile-nav-btn').map(tab => tab.text())).toEqual(['手記', '足跡', '搜尋', 'AI'])

    // Initially in trips tab
    expect(wrapper.find('.trip-list-section').exists()).toBe(true)

    await navTabs[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('#workspace-panel-footprints').exists()).toBe(true)

    await navTabs[2].trigger('click')
    await flushPromises()
    expect(wrapper.find('.recall-search-section').exists()).toBe(true)
    expect(wrapper.find('.trip-list-section').exists()).toBe(false)

    // Switch to AI Conversation tab
    await navTabs[3].trigger('click')
    await flushPromises()
    expect(wrapper.find('.conversation-view-section').exists()).toBe(true)
    expect(wrapper.find('.recall-search-section').exists()).toBe(false)

    // Switch back to Trips tab
    await navTabs[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('.trip-list-section').exists()).toBe(true)
  })

  it('jumps from search or conversation to a specific trip and highlights event', async () => {
    vi.mocked(searchApi.searchRecall).mockResolvedValueOnce({
      items: [{ event: mockEvents[1], score: 1, reasons: [], relation: null }],
      clarification: null,
      vector_status: 'ready'
    })
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser }
    })
    await flushPromises()
    await wrapper.get('.trip-card').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-controls="trip-day-2026-11-20"]').trigger('click')
    expect(wrapper.get<HTMLElement>('#trip-day-2026-11-20').element.style.display).toBe('none')

    // Switch to Recall Search tab
    const navTabs = wrapper.findAll('.nav-tab-btn')
    await navTabs[2].trigger('click')
    await flushPromises()

    // Trigger jump-trip event from RecallSearch component
    const searchComp = wrapper.findComponent({ name: 'RecallSearch' })
    expect(searchComp.exists()).toBe(true)
    await searchComp.get('#search-query-input').setValue('金閣寺')
    await searchComp.get('form').trigger('submit')
    await flushPromises()
    await searchComp.get('[aria-controls="footprint-results"]').trigger('click')
    searchComp.vm.$emit('jump-trip', { tripId: 'trip-1', eventId: 'event-2' })
    await flushPromises()

    // View should switch back to trips detail timeline
    expect(travelApi.getTrip).toHaveBeenCalledWith('trip-1')
    expect(wrapper.find('.trip-detail-section').exists()).toBe(true)

    // Highlighted class should be applied on event-2 card
    const eventCard2 = wrapper.find('#event-event-2')
    expect(eventCard2.exists()).toBe(true)
    expect(wrapper.get<HTMLElement>('#trip-day-2026-11-20').element.style.display).not.toBe('none')
    expect(wrapper.get('button[aria-controls="trip-day-2026-11-20"]').attributes('aria-expanded')).toBe('true')
    expect(eventCard2.classes()).toContain('is-highlighted')

    await navTabs[2].trigger('click')
    const restored = wrapper.getComponent({ name: 'RecallSearch' })
    expect(restored.get<HTMLInputElement>('#search-query-input').element.value).toBe('金閣寺')
    expect(restored.get('[aria-controls="footprint-results"]').attributes('aria-expanded')).toBe('false')
    expect(searchApi.searchRecall).toHaveBeenCalledTimes(1)
  })

  it('renders a listed cover on first load and falls back on a thumbnail error', async () => {
    vi.mocked(travelApi.listTrips).mockResolvedValueOnce({
      items: [{ ...mockTrips[0], cover_photo_id: 'cover' }, mockTrips[1]]
    })
    const wrapper = mount(TripWorkspace, { props: { user: mockUser } })
    await flushPromises()
    const first = wrapper.get('.trip-card[aria-label$="京都秋楓巡禮"]')
    const image = first.get('.trip-cover-img')
    expect(image.attributes('src')).toBe('/api/v1/photos/cover/thumbnail')
    expect(photosApi.getTripCover).not.toHaveBeenCalled()
    await image.trigger('error')
    expect(first.find('.trip-cover-img').exists()).toBe(false)
    expect(first.find('.trip-cover svg').exists()).toBe(true)
  })

  it('supports full keyboard accessibility with role=tab, roving tabindex, and Arrow/Home/End navigation', async () => {
    const wrapper = mount(TripWorkspace, {
      props: { user: mockUser },
      attachTo: document.body
    })
    await flushPromises()

    const tablist = wrapper.find('[role="tablist"]')
    expect(tablist.exists()).toBe(true)
    expect(tablist.attributes('aria-label')).toBe('工作區功能切換')

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.length).toBe(4)

    // Initial state: trips tab active, roving tabindex
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(tabs[0].attributes('tabindex')).toBe('0')
    expect(tabs[0].attributes('aria-controls')).toBe('workspace-panel-trips')

    expect(tabs[1].attributes('aria-selected')).toBe('false')
    expect(tabs[1].attributes('tabindex')).toBe('-1')
    expect(tabs[1].attributes('aria-controls')).toBe('workspace-panel-footprints')

    expect(tabs[2].attributes('aria-selected')).toBe('false')
    expect(tabs[2].attributes('tabindex')).toBe('-1')
    expect(tabs[2].attributes('aria-controls')).toBe('workspace-panel-search')

    const initialPanel = wrapper.find('#workspace-panel-trips')
    expect(initialPanel.exists()).toBe(true)
    expect(initialPanel.attributes('role')).toBe('tabpanel')
    expect(initialPanel.attributes('aria-labelledby')).toBe('workspace-tab-trips')

    // Navigate with ArrowRight from trips to footprints.
    await tabs[0].trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()

    expect(tabs[1].attributes('aria-selected')).toBe('true')
    expect(tabs[1].attributes('tabindex')).toBe('0')
    expect(tabs[0].attributes('aria-selected')).toBe('false')
    expect(tabs[0].attributes('tabindex')).toBe('-1')
    expect(wrapper.find('#workspace-panel-footprints').exists()).toBe(true)
    expect(document.activeElement).toBe(tabs[1].element)

    // Continue through search to chat.
    await tabs[1].trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()

    expect(tabs[2].attributes('aria-selected')).toBe('true')
    expect(tabs[2].attributes('tabindex')).toBe('0')
    expect(wrapper.find('#workspace-panel-search').exists()).toBe(true)
    expect(document.activeElement).toBe(tabs[2].element)
    await tabs[2].trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(wrapper.find('#workspace-panel-chat').exists()).toBe(true)
    expect(document.activeElement).toBe(tabs[3].element)

    // ArrowRight on last tab wraps around to first tab (0)
    await tabs[3].trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()

    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(tabs[0].attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(tabs[0].element)

    // ArrowLeft on first tab wraps around to chat.
    await tabs[0].trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()

    expect(tabs[3].attributes('aria-selected')).toBe('true')
    expect(tabs[3].attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(tabs[3].element)

    // ArrowLeft from chat to search.
    await tabs[3].trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()

    expect(tabs[2].attributes('aria-selected')).toBe('true')
    expect(tabs[2].attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(tabs[2].element)

    // Home key jumps to first tab (0)
    await tabs[2].trigger('keydown', { key: 'Home' })
    await flushPromises()

    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(tabs[0].attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(tabs[0].element)

    // End key jumps to last tab (2)
    await tabs[0].trigger('keydown', { key: 'End' })
    await flushPromises()

    expect(tabs[3].attributes('aria-selected')).toBe('true')
    expect(tabs[3].attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(tabs[3].element)

    wrapper.unmount()
  })
})
