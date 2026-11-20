import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecallSearch from '../RecallSearch.vue'
import * as searchApi from '../../api/search'
import type { Trip } from '../../types/travel'
import type { SearchResponse } from '../../types/search'

const mockTrips: Trip[] = [
  {
    id: 't-1',
    name: '京都秋楓紀行',
    start_date: '2026-11-20',
    end_date: '2026-11-25',
    timezone: 'Asia/Tokyo',
    description: '',
    version: 1
  }
]

const mockSearchResult: SearchResponse = {
  items: [
    {
      event: {
        id: 'e-1',
        trip_id: 't-1',
        place_id: 'p-1',
        place_name: '清水寺本堂',
        city: '京都市',
        address: '東山區清水1丁目294',
        category: '景點',
        date: '2026-11-20',
        time: '09:00',
        notes: '登舞台遠眺京都市區景色。',
        position: 0,
        version: 1,
        trip_name: '京都秋楓紀行'
      },
      score: 0.88,
      reasons: ['符合關鍵字「清水寺」', '類別「景點」高度相符'],
      relation: {
        anchor_id: 'e-0',
        direction: 'after',
        anchor_date: '2026-11-19',
        target_date: '2026-11-20'
      }
    }
  ],
  clarification: '您可能也在尋找音羽瀑布的泉水體驗？',
  vector_status: 'ready'
}

describe('RecallSearch', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders search input and filter controls', () => {
    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })

    expect(wrapper.find('#search-query-input').exists()).toBe(true)
    expect(wrapper.find('#filter-trip').exists()).toBe(true)
    expect(wrapper.find('#filter-city').exists()).toBe(true)
    expect(wrapper.find('#filter-category').exists()).toBe(true)
    expect(wrapper.find('#filter-date-from').exists()).toBe(true)
    expect(wrapper.find('#filter-date-to').exists()).toBe(true)
    expect(wrapper.find('#filter-limit').exists()).toBe(true)
  })

  it('renders sources and relation context without technical ranking details', async () => {
    const searchSpy = vi.spyOn(searchApi, 'searchRecall').mockResolvedValue(mockSearchResult)

    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })

    await wrapper.find('#search-query-input').setValue('清水寺')
    await wrapper.find('#filter-trip').setValue('t-1')
    await wrapper.find('#filter-city').setValue('京都市')
    await wrapper.find('#filter-category').setValue('景點')
    await wrapper.find('#filter-date-from').setValue('2026-11-20')
    await wrapper.find('#filter-date-to').setValue('2026-11-25')

    await wrapper.find('form.search-form-card').trigger('submit.prevent')
    await flushPromises()

    expect(searchSpy).toHaveBeenCalledWith({
      query: '清水寺',
      trip_id: 't-1',
      city: '京都市',
      category: '景點',
      date_from: '2026-11-20',
      date_to: '2026-11-25',
      limit: 10
    })

    // Vector status badge

    // Clarification notice
    expect(wrapper.text()).toContain('搜尋建議與釐清')
    expect(wrapper.text()).toContain('您可能也在尋找音羽瀑布的泉水體驗？')

    // Source card content
    expect(wrapper.text()).toContain('清水寺本堂')
    expect(wrapper.text()).toContain('京都秋楓紀行')
    expect(wrapper.text()).toContain('登舞台遠眺京都市區景色。')
    expect(wrapper.find('.score-badge').exists()).toBe(false)
    expect(wrapper.find('.reasons-block').exists()).toBe(false)
    expect(wrapper.find('.vector-status-badge').exists()).toBe(false)
    expect(wrapper.text()).toContain('時間關係脈絡：')
    expect(wrapper.text()).toContain('基準日期 2026-11-19 ➔ 上一站 ➔ 目標日期 2026-11-20')

    // Card buttons
    expect(wrapper.text()).not.toContain('檢視詳情')
    await wrapper.get('.source-card-open').trigger('click')
    expect(wrapper.emitted('view-source')).toBeTruthy()
    expect(wrapper.emitted('view-source')![0][0]).toEqual(mockSearchResult.items[0])

    const jumpBtn = wrapper.get('.source-card button.jump-btn')
    expect(jumpBtn.attributes('aria-label')).toBe('前往手記')
    await jumpBtn.trigger('click')
    expect(wrapper.emitted('jump-trip')).toBeTruthy()
    expect(wrapper.emitted('jump-trip')![0][0]).toEqual({
      tripId: 't-1',
      eventId: 'e-1'
    })
    expect(wrapper.emitted('view-source')).toHaveLength(1)
  })

  it('renders empty result notice when 0 items returned', async () => {
    vi.spyOn(searchApi, 'searchRecall').mockResolvedValue({
      items: [],
      clarification: null,
      vector_status: 'ready'
    })

    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })

    await wrapper.find('#search-query-input').setValue('完全不存在的地點')
    await wrapper.find('form.search-form-card').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('還沒找到回憶')
  })

  it('resets all filters when clicking reset button', async () => {
    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })

    await wrapper.find('#search-query-input').setValue('北海道')
    await wrapper.find('#filter-city').setValue('札幌市')
    await wrapper.find('button.reset-btn').trigger('click')

    expect((wrapper.find('#search-query-input').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('#filter-city').element as HTMLInputElement).value).toBe('')
  })

  it('guards against out-of-order async search responses using request generation', async () => {
    let resolveFirst!: (val: SearchResponse) => void
    const firstPromise = new Promise<SearchResponse>((resolve) => {
      resolveFirst = resolve
    })

    let resolveSecond!: (val: SearchResponse) => void
    const secondPromise = new Promise<SearchResponse>((resolve) => {
      resolveSecond = resolve
    })

    const searchSpy = vi.spyOn(searchApi, 'searchRecall')
      .mockReturnValueOnce(firstPromise)
      .mockReturnValueOnce(secondPromise)

    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })

    // First search request (slow)
    await wrapper.find('#search-query-input').setValue('慢速請求')
    await wrapper.find('form.search-form-card').trigger('submit.prevent')

    // Second search request (fast)
    await wrapper.find('#search-query-input').setValue('快速請求')
    await wrapper.find('form.search-form-card').trigger('submit.prevent')

    expect(searchSpy).toHaveBeenCalledTimes(2)

    // Second request resolves first with "新結果"
    resolveSecond({
      items: [
        {
          event: {
            ...mockSearchResult.items[0].event,
            id: 'e-fast',
            place_name: '快速請求的新景點'
          },
          score: 0.99,
          reasons: ['最新請求命中'],
          relation: null
        }
      ],
      clarification: null,
      vector_status: 'ready'
    })
    await flushPromises()

    expect(wrapper.text()).toContain('快速請求的新景點')

    // First request resolves later with "舊結果"
    resolveFirst({
      items: [
        {
          event: {
            ...mockSearchResult.items[0].event,
            id: 'e-slow',
            place_name: '已過期的舊景點'
          },
          score: 0.5,
          reasons: ['過期命中'],
          relation: null
        }
      ],
      clarification: null,
      vector_status: 'ready'
    })
    await flushPromises()

    // The stale response must NOT overwrite the latest search result
    expect(wrapper.text()).toContain('快速請求的新景點')
    expect(wrapper.text()).not.toContain('已過期的舊景點')
  })

  it('handleResetFilters invalidates in-flight search so late response does not populate', async () => {
    let resolveSearch!: (val: SearchResponse) => void
    const deferredPromise = new Promise<SearchResponse>((resolve) => {
      resolveSearch = resolve
    })

    vi.spyOn(searchApi, 'searchRecall').mockReturnValueOnce(deferredPromise)

    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })

    // Initiate search
    await wrapper.find('#search-query-input').setValue('等待中的搜尋')
    await wrapper.find('form.search-form-card').trigger('submit.prevent')
    expect(wrapper.find('.loading-state').exists()).toBe(true)

    // User clicks reset while request is in-flight
    await wrapper.find('button.reset-btn').trigger('click')
    expect(wrapper.find('.loading-state').exists()).toBe(false)
    expect(wrapper.find('.results-container').exists()).toBe(false)

    // In-flight request resolves late
    resolveSearch(mockSearchResult)
    await flushPromises()

    // Stale result should NOT be rendered
    expect(wrapper.find('.results-container').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('清水寺本堂')
  })
})
