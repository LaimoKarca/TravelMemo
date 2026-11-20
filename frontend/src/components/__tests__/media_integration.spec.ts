import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ConversationView from '../ConversationView.vue'
import RecallSearch from '../RecallSearch.vue'
import EventDialog from '../EventDialog.vue'
import * as convApi from '../../api/conversation'
import * as searchApi from '../../api/search'
import * as photosApi from '../../api/photos'
import * as travelApi from '../../api/travel'
import type { Message } from '../../types/conversation'
import type { PhotoDTO } from '../../types/photo'
import type { Trip, Event } from '../../types/travel'

const mockPhoto: PhotoDTO = {
  id: 'photo-chat-1',
  caption: '嵐山渡月橋',
  version: 1,
  analysis_version: 1,
  status: 'ready',
  analysis: {
    summary: '渡月橋橫跨桂川',
    visible_text: [],
    tags: ['渡月橋', '嵐山'],
    place_candidates: ['渡月橋'],
    date_candidate: '2026-11-20',
    uncertainties: []
  },
  width: 1920,
  height: 1080,
  size_bytes: 300000,
  thumbnail_size_bytes: 20000,
  created_at: '2026-11-20T10:00:00Z',
  updated_at: '2026-11-20T10:00:00Z',
  bindings: [{ kind: 'conversation', target_id: 'conv-1' }],
  url: '/api/v1/photos/photo-chat-1/content',
  thumbnail_url: '/api/v1/photos/photo-chat-1/thumbnail'
}

const mockMessageWithPhotos: Message = {
  id: 'm-photo-reply',
  role: 'assistant',
  content: '根據您上傳的照片，這是京都嵐山的渡月橋。',
  status: 'answered',
  citations: [],
  photos: [mockPhoto],
  photo_citations: [
    {
      photo_id: 'photo-chat-1',
      version: 1,
      state: 'current',
      caption: '嵐山渡月橋',
      thumbnail_url: '/api/v1/photos/photo-chat-1/thumbnail',
      url: '/api/v1/photos/photo-chat-1/content'
    }
  ],
  answer_scope: 'image',
  created_at: '2026-11-20T10:02:00Z'
}

const mockTrips: Trip[] = [
  {
    id: 'trip-1',
    name: '京都秋楓紀行',
    start_date: '2026-11-20',
    end_date: '2026-11-25',
    timezone: 'Asia/Tokyo',
    description: '',
    version: 1
  }
]

describe('Media Frontend Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    vi.spyOn(convApi, 'listChatRequests').mockResolvedValue({ items: [] })
    let reply: Message | null = null
    vi.spyOn(convApi, 'enqueueMessage').mockImplementation(async (cid, rid, payload) => {
      reply = await convApi.sendMessage(cid, payload)
      return { id: rid, conversation_id: cid, status: 'completed', message: reply, error: null }
    })
    vi.spyOn(convApi, 'getChatRequest').mockImplementation(async (cid, rid) => ({ id: rid, conversation_id: cid, status: 'completed', message: reply, error: null }))

    vi.spyOn(convApi, 'listConversations').mockResolvedValue({
      items: [{ id: 'conv-1', title: '嵐山照片詢問', created_at: '2026-11-20T10:00:00Z' }]
    })
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({
      items: [mockMessageWithPhotos]
    })
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: mockTrips })
    vi.spyOn(travelApi, 'getTrip').mockResolvedValue({
      trip: mockTrips[0],
      events: [
        {
          id: 'evt-1',
          trip_id: 'trip-1',
          place_id: 'p-1',
          place_name: '渡月橋',
          city: '京都市',
          address: '',
          category: '景點',
          date: '2026-11-20',
          time: null,
          notes: '',
          position: 0,
          version: 1
        }
      ],
      next_edges: []
    })
    vi.spyOn(photosApi, 'bindPhoto').mockResolvedValue(mockPhoto)
    vi.spyOn(photosApi, 'listPhotos').mockResolvedValue({ items: [] })
  })

  it('renders chat message attachments, photo citations, and answer scope in ConversationView', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    // Select conversation
    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('根據您上傳的照片，這是京都嵐山的渡月橋。')
    expect(wrapper.find('.answer-scope-pill').exists()).toBe(false)
    expect(wrapper.text()).toContain('引用手記照片：')
    expect(wrapper.text()).toContain('嵐山渡月橋')

    // Renders photo thumbnails
    const thumbs = wrapper.findAll('.message-photo-img')
    expect(thumbs.length).toBeGreaterThan(0)
    expect(thumbs[0].attributes('src')).toBe('/api/v1/photos/photo-chat-1/thumbnail')
  })

  it('executes save-to-journal action from chat photo without duplicating file', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()

    // Click "存入手記" button
    const saveBtn = wrapper.find('.btn-save-to-journal')
    expect(saveBtn.exists()).toBe(true)
    await saveBtn.trigger('click')
    await flushPromises()

    // Modal opens
    expect(wrapper.find('.save-modal-card').exists()).toBe(true)
    expect(travelApi.listTrips).toHaveBeenCalled()

    // Select trip
    const select = wrapper.find('#save-trip-select')
    await select.setValue('trip-1')
    await flushPromises()

    // Confirm save to journal
    const confirmBtn = wrapper.findAll('.save-modal-card .btn-primary')[0]
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(photosApi.bindPhoto).toHaveBeenCalledWith('photo-chat-1', 'trip', 'trip-1')
    expect(wrapper.text()).toContain('已成功將照片存入旅行手記！')
  })

  it('supports image query and displays photo search results in RecallSearch', async () => {
    vi.spyOn(searchApi, 'searchRecall').mockResolvedValue({
      items: [],
      photo_items: [
        {
          photo: mockPhoto,
          score: 0.94,
          reasons: ['圖片場景高度吻合「渡月橋」'],
          event: {
            id: 'evt-1',
            trip_id: 'trip-1',
            place_id: 'p-1',
            place_name: '渡月橋',
            city: '京都市',
            address: '',
            category: '景點',
            date: '2026-11-20',
            time: null,
            notes: '',
            position: 0,
            version: 1
          }
        }
      ],
      clarification: null,
      vector_status: 'ready'
    })

    const wrapper = mount(RecallSearch, {
      props: { trips: mockTrips }
    })
    await flushPromises()

    // Simulate staging a search photo
    const picker = wrapper.findComponent({ name: 'PhotoPicker' })
    picker.vm.$emit('update:photos', [mockPhoto])
    await flushPromises()

    // Search button is enabled even if text query is empty
    const submitBtn = wrapper.find('.search-submit-btn')
    expect(submitBtn.attributes('disabled')).toBeUndefined()

    await wrapper.find('form.search-form-card').trigger('submit')
    await flushPromises()

    expect(searchApi.searchRecall).toHaveBeenCalledWith(expect.objectContaining({
      photo_ids: ['photo-chat-1']
    }))

    // Renders photo search results section
    expect(wrapper.text()).toContain('相符照片記憶 (1)')
    expect(wrapper.get('button[aria-controls="photo-results"]').attributes('aria-expanded')).toBe('false')
    expect((wrapper.get('#photo-results').element as HTMLElement).style.display).toBe('none')
    await wrapper.get('button[aria-controls="photo-results"]').trigger('click')
    expect((wrapper.get('#photo-results').element as HTMLElement).style.display).not.toBe('none')
    expect(wrapper.text()).toContain('嵐山渡月橋')
    expect(wrapper.text()).not.toContain('圖片場景高度吻合「渡月橋」')
    await wrapper.find('form.search-form-card').trigger('submit')
    await flushPromises()
    expect((wrapper.get('#photo-results').element as HTMLElement).style.display).toBe('none')
  })

  it('EventDialog stages photos on create and passes stagedPhotoIds on submit', async () => {
    const wrapper = mount(EventDialog, {
      props: {
        visible: true,
        trip: mockTrips[0],
        event: null // create mode
      }
    })
    await flushPromises()

    // Fill valid form
    await wrapper.find('#event-place-name').setValue('嵐山公園')
    await wrapper.find('#event-city').setValue('京都市')
    await wrapper.find('#event-category').setValue('景點')

    // Stage a photo
    const picker = wrapper.findComponent({ name: 'PhotoPicker' })
    picker.vm.$emit('update:photos', [mockPhoto])
    await flushPromises()

    // Submit event
    await wrapper.find('form.dialog-form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('submit')).toBeTruthy()
    const submitCall = wrapper.emitted('submit')![0]
    expect(submitCall[0]).toMatchObject({
      place_name: '嵐山公園',
      city: '京都市',
      category: '景點'
    })
    // stagedPhotoIds is passed as second argument
    expect(submitCall[1]).toEqual(['photo-chat-1'])
  })

  it('disables sending when staged photo is pending, displays reading indicator, and polls until ready', async () => {
    vi.useFakeTimers()
    const pendingPhoto: PhotoDTO = { ...mockPhoto, id: 'photo-pending-1', status: 'pending' }
    const readyPhoto: PhotoDTO = { ...mockPhoto, id: 'photo-pending-1', status: 'ready' }

    const getPhotoSpy = vi.spyOn(photosApi, 'getPhoto').mockResolvedValueOnce(readyPhoto)
    const sendMessageSpy = vi.spyOn(convApi, 'sendMessage').mockResolvedValueOnce({
      id: 'm-reply',
      role: 'assistant',
      content: '收到照片',
      status: 'answered',
      citations: [],
      created_at: '2026-11-20T10:05:00Z'
    })

    const wrapper = mount(ConversationView)
    await flushPromises()

    // Select existing conversation
    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()

    // Staging a pending photo via PhotoPicker
    const picker = wrapper.findComponent({ name: 'PhotoPicker' })
    picker.vm.$emit('update:photos', [pendingPhoto])
    await flushPromises()

    // Reading indicator should be visible
    expect(wrapper.find('.reading-indicator').exists()).toBe(true)
    expect(wrapper.text()).toContain('正在識別照片內容...')

    // Send button must be disabled
    const sendBtn = wrapper.find('.send-btn')
    expect(sendBtn.attributes('disabled')).toBeDefined()

    // Attempting to submit should be prevented
    await wrapper.find('form.chat-form').trigger('submit')
    expect(sendMessageSpy).not.toHaveBeenCalled()

    // Advance timer to trigger polling
    await vi.advanceTimersByTimeAsync(1600)
    await flushPromises()

    expect(getPhotoSpy).toHaveBeenCalledWith('photo-pending-1')

    // Now photo status is ready: reading indicator disappears, send button enabled
    expect(wrapper.find('.reading-indicator').exists()).toBe(false)
    expect(sendBtn.attributes('disabled')).toBeUndefined()

    // Submit now succeeds
    await wrapper.find('form.chat-form').trigger('submit')
    await flushPromises()

    expect(sendMessageSpy).toHaveBeenCalledWith('conv-1', {
      content: '',
      photo_ids: ['photo-pending-1']
    })
    vi.useRealTimers()
  })

  it('handles failed or blocked staged photos by disabling send and showing alert hint', async () => {
    const failedPhoto: PhotoDTO = { ...mockPhoto, id: 'photo-failed-1', status: 'failed' }
    const wrapper = mount(ConversationView)
    await flushPromises()

    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()

    // Stage failed photo
    const picker = wrapper.findComponent({ name: 'PhotoPicker' })
    picker.vm.$emit('update:photos', [failedPhoto])
    await flushPromises()

    // Alert hint is shown
    expect(wrapper.find('.staged-alert-hint').exists()).toBe(true)
    expect(wrapper.text()).toContain('照片未就緒，請重試或移除無法識別的照片')

    // Send button disabled
    const sendBtn = wrapper.find('.send-btn')
    expect(sendBtn.attributes('disabled')).toBeDefined()

    // Removing failed photo
    picker.vm.$emit('update:photos', [])
    await flushPromises()

    expect(wrapper.find('.staged-alert-hint').exists()).toBe(false)
  })
})
