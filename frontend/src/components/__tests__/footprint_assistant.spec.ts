import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import FootprintAssistant from '../FootprintAssistant.vue'
import * as api from '../../api/footprint'
import * as travel from '../../api/travel'
import { ApiError } from '../../api/auth'
import type { FootprintDraft } from '../../types/footprint'
const trip = { id: 'trip', name: '河邊散步', start_date: '2026-01-01', end_date: '2026-01-03', timezone: 'Asia/Taipei', description: '', version: 4 }
const item = { id: 'item', selected: true, place_name: '河邊', date: '2026-01-02', time: null, city: '', address: '', category: '景點', notes: '風很舒服' }
const initial: FootprintDraft = { id: 'draft', trip_id: trip.id, version: 1, trip_version: 4, status: 'editing', record_date: '2026-01-02', text: '河邊散步', items: [], issues: {}, error: null, request_id: null }
const copy = <T,>(v: T): T => JSON.parse(JSON.stringify(v))
let state: FootprintDraft
const wrappers: VueWrapper[] = []
async function open() { const w = mount(FootprintAssistant, { attachTo: document.body, props: { visible: true, trip }, global: { stubs: { teleport: true } } }); wrappers.push(w); await flushPromises(); return w }
beforeEach(() => {
  vi.restoreAllMocks(); state = copy(initial)
  vi.spyOn(travel, 'getTrip').mockResolvedValue({ trip, events: [], next_edges: [] })
  vi.spyOn(api, 'latestFootprintDrafts').mockResolvedValue({ items: [] })
  vi.spyOn(api, 'createFootprintDraft').mockImplementation(async (_, date, text) => { state = { ...state, record_date: date, text }; return copy(state) })
  vi.spyOn(api, 'updateFootprintDraft').mockImplementation(async (_, __, changes) => { state = { ...state, ...changes, version: changes.version + 1 }; return copy(state) })
  vi.spyOn(api, 'generateFootprints').mockImplementation(async () => { state = { ...state, version: state.version + 1, status: 'queued' }; return copy(state) })
  vi.spyOn(api, 'getFootprintDraft').mockImplementation(async () => { state = { ...state, version: state.version + 1, status: 'ready', items: [copy(item)] }; return copy(state) })
  vi.spyOn(api, 'commitFootprints').mockImplementation(async () => ({ events: [], trip_version: 5, draft: { ...copy(state), status: 'committed' } }))
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })
describe('Footprint assistant', () => {
  it('saves description before generation and only writes events on explicit confirmation', async () => {
    const w = await open()
    await w.get('#assist-date').setValue('2026-01-02')
    await w.get('#assist-description').setValue('河邊散步，風很舒服')
    await w.get('.generate-row button').trigger('click'); await flushPromises()
    expect(api.createFootprintDraft).toHaveBeenCalledWith('trip', '2026-01-02', '河邊散步，風很舒服')
    expect(w.text()).toContain('風很舒服')
    expect(api.commitFootprints).not.toHaveBeenCalled()
    await w.get('.assist-footer .btn-primary').trigger('click'); await flushPromises()
    expect(api.commitFootprints).toHaveBeenCalledWith('trip', 'draft', state.version, 4, expect.any(String))
    expect(w.emitted('saved')).toHaveLength(1)
    expect(w.text()).toContain('足跡已加入手記')
  })
  it('restores an incomplete draft and blocks selected missing places until edited or deselected', async () => {
    state.items = [{ ...item, place_name: null }]
    state.status = 'ready'
    vi.mocked(api.latestFootprintDrafts).mockResolvedValue({ items: [copy(state)] })
    const w = await open()
    expect(w.text()).toContain('請補上地點名稱')
    expect(w.get('.assist-footer .btn-primary').attributes('disabled')).toBeDefined()
    await w.get('.draft-fields input').setValue('抹茶店')
    expect(w.get('.assist-footer .btn-primary').attributes('disabled')).toBeUndefined()
    await w.get('.draft-summary input[type=checkbox]').setValue(false)
    expect(w.get('.assist-footer .btn-primary').attributes('disabled')).toBeDefined()
  })
  it('retains local edits made while an autosave response is in flight', async () => {
    vi.useFakeTimers()
    vi.mocked(api.latestFootprintDrafts).mockResolvedValue({ items: [copy(state)] })
    let resolve!: (value: FootprintDraft) => void
    vi.mocked(api.updateFootprintDraft).mockReturnValueOnce(new Promise(r => { resolve = r }))
    const w = await open()
    await w.get('#assist-description').setValue('第一段')
    await vi.advanceTimersByTimeAsync(600)
    await w.get('#assist-description').setValue('第一段，再補充河景')
    resolve({ ...copy(state), version: 2, text: '第一段' })
    await flushPromises()
    expect(api.updateFootprintDraft).toHaveBeenLastCalledWith('trip', 'draft', expect.objectContaining({ text: '第一段，再補充河景' }))
  })
  it('keeps drafts and waits for explicit retry when the trip version changed', async () => {
    state = { ...state, status: 'ready', items: [copy(item)] }
    vi.mocked(api.latestFootprintDrafts).mockResolvedValue({ items: [copy(state)] })
    vi.mocked(api.commitFootprints).mockRejectedValue(new ApiError(409, '手記已更新'))
    const w = await open()
    await w.get('.assist-footer .btn-primary').trigger('click'); await flushPromises()
    expect(w.text()).toContain('手記已更新')
    expect(w.text()).toContain('河邊')
    expect(w.emitted('saved')).toBeUndefined()
    expect(api.commitFootprints).toHaveBeenCalledTimes(1)
  })
  it('offers a safe exit on failed saving without discarding the local description', async () => {
    vi.mocked(api.latestFootprintDrafts).mockResolvedValue({ items: [copy(state)] })
    vi.mocked(api.updateFootprintDraft).mockRejectedValue(new ApiError(503, '暫時無法儲存'))
    const w = await open()
    await w.get('#assist-description').setValue('尚未連線儲存的描述')
    await w.get('[aria-label="關閉足跡助手"]').trigger('click'); await flushPromises()
    expect(w.emitted('close')).toBeUndefined()
    expect(w.text()).toContain('重整或離開手記可能遺失')
    w.findComponent({ name: 'ConfirmDialog' }).vm.$emit('confirm')
    await flushPromises()
    expect(w.emitted('close')).toHaveLength(1)
    expect((w.get('#assist-description').element as HTMLTextAreaElement).value).toBe('尚未連線儲存的描述')
  })
})
