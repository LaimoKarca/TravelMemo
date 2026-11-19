import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PhotoViewer from '../PhotoViewer.vue'
import PhotoPicker from '../PhotoPicker.vue'
import PhotoGallery from '../PhotoGallery.vue'
import * as photosApi from '../../api/photos'
import type { PhotoDTO } from '../../types/photo'

const mockPhotos: PhotoDTO[] = [
  {
    id: 'photo-1',
    caption: '清水寺晨光',
    version: 1,
    analysis_version: 1,
    status: 'ready',
    analysis: {
      summary: '陽光穿透清水舞台懸造木樑',
      visible_text: ['清水寺'],
      tags: ['寺院', '世界遺產', '日出'],
      place_candidates: ['清水寺'],
      date_candidate: '2026-11-20',
      uncertainties: []
    },
    width: 2048,
    height: 1536,
    size_bytes: 400000,
    thumbnail_size_bytes: 30000,
    created_at: '2026-11-20T08:00:00Z',
    updated_at: '2026-11-20T08:02:00Z',
    bindings: [{ kind: 'trip', target_id: 'trip-1' }],
    url: '/api/v1/photos/photo-1/content',
    thumbnail_url: '/api/v1/photos/photo-1/thumbnail'
  },
  {
    id: 'photo-2',
    caption: '嵐山竹林',
    version: 1,
    analysis_version: 1,
    status: 'processing',
    analysis: {
      summary: '',
      visible_text: [],
      tags: [],
      place_candidates: [],
      date_candidate: null,
      uncertainties: []
    },
    width: 1920,
    height: 1080,
    size_bytes: 350000,
    thumbnail_size_bytes: 25000,
    created_at: '2026-11-20T11:00:00Z',
    updated_at: '2026-11-20T11:00:00Z',
    bindings: [{ kind: 'trip', target_id: 'trip-1' }],
    url: '/api/v1/photos/photo-2/content',
    thumbnail_url: '/api/v1/photos/photo-2/thumbnail'
  },
  {
    id: 'photo-3',
    caption: '金閣寺倒影',
    version: 2,
    analysis_version: 1,
    status: 'failed',
    analysis: {
      summary: '',
      visible_text: [],
      tags: [],
      place_candidates: [],
      date_candidate: null,
      uncertainties: []
    },
    width: 1920,
    height: 1080,
    size_bytes: 320000,
    thumbnail_size_bytes: 22000,
    created_at: '2026-11-20T14:00:00Z',
    updated_at: '2026-11-20T14:01:00Z',
    bindings: [{ kind: 'trip', target_id: 'trip-1' }],
    url: '/api/v1/photos/photo-3/content',
    thumbnail_url: '/api/v1/photos/photo-3/thumbnail'
  }
]

describe('PhotoViewer (Lightbox)', () => {
  it('renders photo details, caption, and analysis metadata', () => {
    const wrapper = mount(PhotoViewer, {
      props: {
        visible: true,
        photos: mockPhotos,
        initialPhotoId: 'photo-1',
        canEditCaption: true,
        coverPhotoId: 'photo-1',
        showCoverAction: true,
        showDeleteAction: true,
        showSaveToJournalAction: true
      }
    })

    expect(wrapper.text()).toContain('清水寺晨光')
    expect(wrapper.text()).toContain('陽光穿透清水舞台懸造木樑')
    expect(wrapper.text()).toContain('#寺院')
    expect(wrapper.text()).toContain('清水寺')
    expect(wrapper.text()).toContain('★ 封面照片')
    expect(wrapper.text()).toContain('1 / 3')

    const img = wrapper.find('.lightbox-image')
    expect(img.attributes('src')).toBe('/api/v1/photos/photo-1/content')
  })

  it('navigates next and previous photo with buttons and keyboard', async () => {
    const wrapper = mount(PhotoViewer, {
      props: {
        visible: true,
        photos: mockPhotos,
        initialPhotoId: 'photo-1'
      }
    })

    expect(wrapper.text()).toContain('1 / 3')
    await wrapper.find('.nav-next').trigger('click')
    expect(wrapper.text()).toContain('2 / 3')
    expect(wrapper.text()).toContain('嵐山竹林')
    expect(wrapper.text()).toContain('AI 分析中...')

    await wrapper.find('.nav-prev').trigger('click')
    expect(wrapper.text()).toContain('1 / 3')
    expect(wrapper.text()).toContain('清水寺晨光')
  })

  it('emits close on Escape and close button click', async () => {
    const wrapper = mount(PhotoViewer, {
      props: {
        visible: true,
        photos: mockPhotos
      }
    })

    await wrapper.find('.lightbox-close-btn').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')?.length).toBe(2)
  })

  it('emits update-caption when caption is edited and saved', async () => {
    const wrapper = mount(PhotoViewer, {
      props: {
        visible: true,
        photos: mockPhotos,
        initialPhotoId: 'photo-1',
        canEditCaption: true
      }
    })

    await wrapper.find('.edit-caption-btn').trigger('click')
    const input = wrapper.find('.caption-input')
    await input.setValue('清水寺清晨的微風')
    await wrapper.find('.caption-row .btn-primary').trigger('click')

    expect(wrapper.emitted('update-caption')).toBeTruthy()
    expect(wrapper.emitted('update-caption')![0]).toEqual([{
      photoId: 'photo-1',
      caption: '清水寺清晨的微風',
      version: 1
    }])
  })

  it('emits retry and delete actions correctly', async () => {
    const wrapper = mount(PhotoViewer, {
      props: {
        visible: true,
        photos: mockPhotos,
        initialPhotoId: 'photo-3',
        showDeleteAction: true
      }
    })

    await wrapper.find('.retry-btn').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
    expect(wrapper.emitted('retry')![0]).toEqual([{
      photoId: 'photo-3',
      version: 2
    }])

    await wrapper.find('.btn-delete-text').trigger('click')
    expect(wrapper.emitted('delete')).toBeTruthy()
    expect(wrapper.emitted('delete')![0]).toEqual([{
      photoId: 'photo-3',
      version: 2
    }])
  })
})

describe('PhotoPicker', () => {
  it('uses one native source picker without capture and can reopen after cancellation', async () => {
    const wrapper = mount(PhotoPicker, { props: { nativePicker: true, buttonText: '加入相簿照片' } })
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.findAll('.picker-buttons-row button')).toHaveLength(1)
    const gallery = wrapper.findAll('input[type=file]')[1]
    expect(gallery.attributes('capture')).toBeUndefined()
    expect(gallery.attributes('multiple')).toBeDefined()
    const open = vi.spyOn(gallery.element as HTMLInputElement, 'click').mockImplementation(() => {})
    await wrapper.get('button[aria-label="加入相簿照片"]').trigger('click')
    await gallery.trigger('cancel')
    await wrapper.get('button[aria-label="加入相簿照片"]').trigger('click')
    expect(open).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('upload-complete')).toBeUndefined()
    wrapper.unmount()
  })
  it('offers two direct icon actions without a source menu', async () => {
    const wrapper = mount(PhotoPicker, { props: { directIcons: true, buttonText: '新增相簿照片' } })
    const inputs = wrapper.findAll('input[type=file]')
    const camera = vi.spyOn(inputs[0].element as HTMLInputElement, 'click').mockImplementation(() => {})
    const gallery = vi.spyOn(inputs[1].element as HTMLInputElement, 'click').mockImplementation(() => {})
    expect(wrapper.find('details').exists()).toBe(false)
    await wrapper.get('button[aria-label="拍照"]').trigger('click')
    await wrapper.get('button[aria-label="新增相簿照片"]').trigger('click')
    expect(camera).toHaveBeenCalledOnce()
    expect(gallery).toHaveBeenCalledOnce()
    expect(wrapper.findAll('.picker-btn span').every(span => span.classes().includes('sr-only'))).toBe(true)
    wrapper.unmount()
  })
  it('keeps the source active while opening a picker, then closes on native cancel or change', async () => {
    const wrapper = mount(PhotoPicker, { attachTo: document.body, props: { iconOnly: true } })
    try {
      const menu = wrapper.get('details').element as HTMLDetailsElement
      const inputs = wrapper.findAll('input[type=file]')
      for (const [index, input] of inputs.entries()) {
        const open = vi.spyOn(input.element as HTMLInputElement, 'click').mockImplementation(() => {
          expect(menu.open).toBe(true)
          input.element.dispatchEvent(new Event('focusin', { bubbles: true }))
          expect(menu.open).toBe(true)
        })
        menu.open = true
        await wrapper.findAll('.photo-source-options button')[index].trigger('click')
        expect(open).toHaveBeenCalledOnce()
        await input.trigger(index === 0 ? 'cancel' : 'change')
        expect(menu.open).toBe(false)
      }
    } finally { wrapper.unmount() }
  })
  it('updates pending previews and accepts parent model updates without polling after unmount', async () => {
    vi.useFakeTimers()
    const get = vi.spyOn(photosApi, 'getPhoto').mockResolvedValue({ ...mockPhotos[0], version: 2 })
    const wrapper = mount(PhotoPicker, { props: { photos: [{ ...mockPhotos[0], status: 'processing' }] } })
    try {
      await vi.advanceTimersByTimeAsync(1200)
      await flushPromises()
      expect(wrapper.emitted('update:photos')?.at(-1)?.[0]).toEqual([{ ...mockPhotos[0], version: 2 }])
      await wrapper.setProps({ photos: [mockPhotos[1]] })
      expect(wrapper.find('img').attributes('src')).toBe(mockPhotos[1].thumbnail_url)
      wrapper.unmount()
      const calls = get.mock.calls.length
      await vi.advanceTimersByTimeAsync(10000)
      expect(get).toHaveBeenCalledTimes(calls)
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('triggers camera and gallery inputs', async () => {
    const wrapper = mount(PhotoPicker, {
      props: {
        maxPhotos: 4,
        cameraButtonText: '拍攝照片',
        buttonText: '選擇多張照片'
      }
    })

    expect(wrapper.text()).toContain('拍攝照片')
    expect(wrapper.text()).toContain('選擇多張照片')

    const fileInputs = wrapper.findAll('input[type="file"]')
    expect(fileInputs.length).toBe(2)

    // Camera input has capture="environment"
    expect(fileInputs[0].attributes('capture')).toBe('environment')
    expect(fileInputs[0].attributes('accept')).toBe('image/*')

    // Gallery input has multiple
    expect(fileInputs[1].attributes('multiple')).toBeDefined()
  })

  it('uploads selected file as raw Blob and adds thumbnail preview', async () => {
    vi.spyOn(photosApi, 'uploadPhoto').mockResolvedValueOnce({
      ...mockPhotos[0],
      id: 'uploaded-photo-1'
    })

    const wrapper = mount(PhotoPicker, {
      props: {
        autoUpload: true,
        maxPhotos: 4
      }
    })

    const galleryInput = wrapper.findAll('input[type="file"]')[1]
    const fakeFile = new File(['image-bits'], 'japan.jpg', { type: 'image/jpeg' })

    Object.defineProperty(galleryInput.element, 'files', {
      value: [fakeFile],
      writable: true
    })

    await galleryInput.trigger('change')
    await flushPromises()

    expect(photosApi.uploadPhoto).toHaveBeenCalledWith(fakeFile, 'image/jpeg')
    expect(wrapper.emitted('upload-complete')).toBeTruthy()
    expect(wrapper.findAll('.staged-preview-item').length).toBe(1)

    // Remove photo
    await wrapper.find('.btn-remove-photo').trigger('click')
    expect(wrapper.findAll('.staged-preview-item').length).toBe(0)
    expect(wrapper.emitted('remove')).toBeTruthy()
  })

  it('respects maxPhotos limit and clear method', async () => {
    const wrapper = mount(PhotoPicker, {
      props: {
        maxPhotos: 1,
        initialPhotos: [mockPhotos[0]]
      }
    })

    expect(wrapper.text()).toContain('(1/1)')
    expect(wrapper.findAll('.picker-btn')[0].attributes('disabled')).toBeDefined()

    // Call exposed clear method
    wrapper.vm.clear()
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.staged-preview-item').length).toBe(0)
  })

  it('hides native file inputs from tab order and accessibility tree', () => {
    const wrapper = mount(PhotoPicker)
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs.length).toBe(2)
    inputs.forEach((input) => {
      expect(input.attributes('tabindex')).toBe('-1')
      expect(input.attributes('aria-hidden')).toBe('true')
    })
  })

  it('allows removing staged photo via exposed removePhoto method', async () => {
    const wrapper = mount(PhotoPicker, {
      props: {
        initialPhotos: [mockPhotos[0]]
      }
    })
    expect(wrapper.findAll('.staged-preview-item').length).toBe(1)
    wrapper.vm.removePhoto('photo-1')
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.staged-preview-item').length).toBe(0)
  })
})

describe('PhotoGallery', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders photos grid with cover badge, status overlays, and actions', () => {
    const wrapper = mount(PhotoGallery, {
      props: {
        photos: mockPhotos,
        coverPhotoId: 'photo-1',
        canSetCover: true,
        canReorder: true,
        canDelete: true
      }
    })

    expect(wrapper.findAll('.photo-card').length).toBe(3)
    expect(wrapper.text()).toContain('★ 封面')
    expect(wrapper.text()).toContain('分析中')
    expect(wrapper.text()).toContain('分析失敗')
  })

  it('handles reordering photos left and right', async () => {
    const wrapper = mount(PhotoGallery, {
      props: {
        photos: mockPhotos,
        canReorder: true
      }
    })

    // Move first photo right using compact icon button
    const rightButton = wrapper.find('button[title="往後移"]')
    await rightButton.trigger('click')

    expect(wrapper.emitted('reorder')).toBeTruthy()
    expect(wrapper.emitted('reorder')![0]).toEqual([['photo-2', 'photo-1', 'photo-3']])
  })

  it('prompts ConfirmDialog on photo delete and warns when multiple bindings exist', async () => {
    const multiBoundPhoto: PhotoDTO = {
      ...mockPhotos[0],
      bindings: [
        { kind: 'trip', target_id: 'trip-1' },
        { kind: 'event', target_id: 'evt-1' }
      ]
    }
    const wrapper = mount(PhotoGallery, {
      props: {
        photos: [multiBoundPhoto],
        canDelete: true
      }
    })

    const deleteBtn = wrapper.find('button[title="刪除照片"]')
    await deleteBtn.trigger('click')

    // Confirm dialog is opened with multi-binding warning
    const dialog = wrapper.findComponent({ name: 'ConfirmDialog' })
    expect(dialog.props('visible')).toBe(true)
    expect(dialog.props('message')).toContain('此照片同時關聯於多個旅程或足跡')

    // Clicking confirm emits delete
    dialog.vm.$emit('confirm')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('delete')).toBeTruthy()
    expect(wrapper.emitted('delete')![0]).toEqual([{ photoId: 'photo-1', version: 1 }])
  })

  it('schedules bounded polling with backoff for pending photos', async () => {
    const wrapper = mount(PhotoGallery, {
      props: {
        photos: mockPhotos // mockPhotos[1] has status 'processing'
      }
    })

    // Advance 2s (first poll interval)
    vi.advanceTimersByTime(2000)
    expect(wrapper.emitted('refresh')).toBeTruthy()

    // Unmounting cleans up timer without leaking
    wrapper.unmount()
  })
})
