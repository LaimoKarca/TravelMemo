import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ConversationView from '../ConversationView.vue'
import * as convApi from '../../api/conversation'
import type { ConversationSummary, Message, UsageMeResponse } from '../../types/conversation'

const mockConversations: ConversationSummary[] = [
  {
    id: 'c-1',
    title: '京都行程回顧',
    created_at: '2026-11-20T10:00:00Z'
  }
]

const mockMessages: Message[] = [
  {
    id: 'm-1',
    role: 'user',
    content: '我上次在京都有去嵐山嗎？',
    status: 'answered',
    citations: [],
    created_at: '2026-11-20T10:01:00Z'
  },
  {
    id: 'm-2',
    role: 'assistant',
    content: '是的，您在 2026-11-21 走訪了嵐山天龍寺，並記錄了庭園造景。',
    status: 'answered',
    citations: [
      {
        event_id: 'e-arashiyama',
        trip_id: 't-kyoto',
        date: '2026-11-21',
        place_name: '嵐山天龍寺',
        version: 1,
        state: 'current'
      },
      {
        event_id: 'e-old-cafe',
        trip_id: 't-kyoto',
        date: '2026-11-21',
        place_name: '已註銷的咖啡店',
        version: 1,
        state: 'deleted'
      }
    ],
    created_at: '2026-11-20T10:01:03Z'
  }
]

const mockUsage: UsageMeResponse = {
  date: '2026-11-20',
  requests: 4,
  input_tokens: 650,
  output_tokens: 280,
  daily_limit: 50,
  model: 'gpt-6-luna'
}

describe('ConversationView', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: [...mockConversations] })
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({ items: [...mockMessages] })
    vi.spyOn(convApi, 'getUsage').mockResolvedValue(mockUsage)
  })

  it('renders conversations list, active messages, citations, and usage banner', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    // Title and usage
    expect(wrapper.text()).toContain('AI 旅程助理')
    expect(wrapper.text()).toContain('4 / 50 次')
    expect(wrapper.text()).toContain('消耗 Tokens：930')
    expect(wrapper.text()).toContain('模型：gpt-6-luna')

    // Conversations sidebar
    expect(wrapper.text()).toContain('京都行程回顧')

    // Messages
    expect(wrapper.text()).toContain('我上次在京都有去嵐山嗎？')
    expect(wrapper.text()).toContain('是的，您在 2026-11-21 走訪了嵐山天龍寺')
    expect(wrapper.text()).toContain('已依手記回答')

    // Citations
    expect(wrapper.text()).toContain('嵐山天龍寺')
    expect(wrapper.text()).toContain('最新版本')
    expect(wrapper.text()).toContain('已註銷的咖啡店')
    expect(wrapper.text()).toContain('足跡已刪除')
    expect(wrapper.text()).toContain('已刪除不可檢視')
  })

  it('clicking current citation emits view-citation', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    const inspectBtn = wrapper.find('button.btn-cite-inspect')
    expect(inspectBtn.exists()).toBe(true)
    await inspectBtn.trigger('click')

    expect(wrapper.emitted('view-citation')).toBeTruthy()
    expect(wrapper.emitted('view-citation')![0][0]).toEqual(mockMessages[1].citations[0])
  })

  it('creates a new conversation', async () => {
    const createSpy = vi.spyOn(convApi, 'createConversation').mockResolvedValue({
      id: 'c-2',
      title: '花東縱谷美食',
      created_at: '2026-11-20T11:00:00Z'
    })

    const wrapper = mount(ConversationView)
    await flushPromises()

    await wrapper.find('.conv-title-input').setValue('花東縱谷美食')
    await wrapper.find('form.create-conv-form').trigger('submit.prevent')
    await flushPromises()

    expect(createSpy).toHaveBeenCalledWith({ title: '花東縱谷美食' })
    expect(wrapper.text()).toContain('花東縱谷美食')
  })

  it('sends message and renders new assistant response and updates usage', async () => {
    const sendSpy = vi.spyOn(convApi, 'sendMessage').mockResolvedValue({
      id: 'm-3',
      role: 'assistant',
      content: '手記中未提及此類別紀錄。',
      status: 'insufficient_evidence',
      citations: [],
      created_at: '2026-11-20T10:05:00Z'
    })

    const wrapper = mount(ConversationView)
    await flushPromises()

    await wrapper.find('#chat-message-input').setValue('我有去過宇治嗎？')
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()

    expect(sendSpy).toHaveBeenCalledWith('c-1', { content: '我有去過宇治嗎？' })
    expect(wrapper.text()).toContain('我有去過宇治嗎？')
    expect(wrapper.text()).toContain('手記中未提及此類別紀錄。')
    expect(wrapper.text()).toContain('手記證據不足')
  })

  it('prompts and executes delete conversation', async () => {
    const deleteSpy = vi.spyOn(convApi, 'deleteConversation').mockResolvedValue(undefined)

    const wrapper = mount(ConversationView)
    await flushPromises()

    // Click delete icon on c-1
    await wrapper.find('button.btn-delete-conv').trigger('click')
    await flushPromises()

    // Confirm dialog is shown
    expect(wrapper.text()).toContain('確認刪除對話')

    // Find confirm button and click
    const confirmBtn = wrapper.find('.dialog-actions button.btn-danger')
    expect(confirmBtn.exists()).toBe(true)
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(deleteSpy).toHaveBeenCalledWith('c-1')
  })

  it('selectConversation async old listMessages response does not overwrite newly active conversation', async () => {
    const twoConversations = [
      { id: 'c-1', title: '京都行程', created_at: '2026-11-20T10:00:00Z' },
      { id: 'c-2', title: '台東行程', created_at: '2026-11-20T11:00:00Z' }
    ]
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: twoConversations })

    let resolveC2!: (val: { items: Message[] }) => void
    const c2Promise = new Promise<{ items: Message[] }>((resolve) => {
      resolveC2 = resolve
    })

    const listMessagesSpy = vi.spyOn(convApi, 'listMessages')
      // Initial mount loads c-1
      .mockResolvedValueOnce({
        items: [
          {
            id: 'm-c1-init',
            role: 'assistant',
            content: '這是京都的初始訊息',
            status: 'answered',
            citations: [],
            created_at: '2026-11-20T10:00:00Z'
          }
        ]
      })
      // Next: user clicks c-2 (slow)
      .mockReturnValueOnce(c2Promise)
      // Next: user clicks back to c-1 (fast)
      .mockResolvedValueOnce({
        items: [
          {
            id: 'm-c1-fast',
            role: 'assistant',
            content: '這是京都最新載入的訊息',
            status: 'answered',
            citations: [],
            created_at: '2026-11-20T10:02:00Z'
          }
        ]
      })

    const wrapper = mount(ConversationView)
    await flushPromises()
    expect(wrapper.text()).toContain('這是京都的初始訊息')

    const items = wrapper.findAll('.conversation-item')
    // Click c-2 (loads slowly)
    await items[1].trigger('click')

    // Before c-2 resolves, user clicks back to c-1
    await items[0].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('這是京都最新載入的訊息')

    // Now c-2 resolves late
    resolveC2({
      items: [
        {
          id: 'm-c2-late',
          role: 'assistant',
          content: '這是台東的過期訊息，不應顯示在京都',
          status: 'answered',
          citations: [],
          created_at: '2026-11-20T11:00:00Z'
        }
      ]
    })
    await flushPromises()

    // c-1 messages must NOT be overwritten by late c-2 response
    expect(wrapper.text()).toContain('這是京都最新載入的訊息')
    expect(wrapper.text()).not.toContain('這是台東的過期訊息，不應顯示在京都')
  })

  it('handleSendMessage captures target conversation ID and does not append reply to another conversation if switched during send', async () => {
    const twoConversations = [
      { id: 'c-1', title: '對話一', created_at: '2026-11-20T10:00:00Z' },
      { id: 'c-2', title: '對話二', created_at: '2026-11-20T11:00:00Z' }
    ]
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: twoConversations })
    vi.spyOn(convApi, 'listMessages').mockImplementation(async (id: string) => {
      if (id === 'c-1') {
        return {
          items: [
            { id: 'm-1', role: 'user', content: '對話一的舊訊息', status: 'answered', citations: [], created_at: '2026-11-20T10:00:00Z' }
          ]
        }
      }
      return {
        items: [
          { id: 'm-2', role: 'user', content: '對話二的舊訊息', status: 'answered', citations: [], created_at: '2026-11-20T11:00:00Z' }
        ]
      }
    })

    let resolveSend!: (val: Message) => void
    const sendPromise = new Promise<Message>((resolve) => {
      resolveSend = resolve
    })
    const sendSpy = vi.spyOn(convApi, 'sendMessage').mockReturnValueOnce(sendPromise)

    const wrapper = mount(ConversationView)
    await flushPromises()

    // User is on c-1, types message
    await wrapper.find('#chat-message-input').setValue('發送給對話一的新提問')
    await wrapper.find('form.chat-form').trigger('submit.prevent')

    expect(sendSpy).toHaveBeenCalledWith('c-1', { content: '發送給對話一的新提問' })

    // While send is pending, user clicks c-2
    const items = wrapper.findAll('.conversation-item')
    await items[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('對話二的舊訊息')

    // Send on c-1 now resolves with reply
    resolveSend({
      id: 'm-reply-c1',
      role: 'assistant',
      content: '這是專屬於對話一的助理回覆',
      status: 'answered',
      citations: [],
      created_at: '2026-11-20T10:05:00Z'
    })
    await flushPromises()

    // Reply must NOT be appended to conversation c-2
    expect(wrapper.text()).not.toContain('這是專屬於對話一的助理回覆')
    expect(wrapper.text()).toContain('對話二的舊訊息')
  })

  it('preserves user draft across conversation switches and clears draft on message send', async () => {
    const twoConversations = [
      { id: 'c-1', title: '對話一', created_at: '2026-11-20T10:00:00Z' },
      { id: 'c-2', title: '對話二', created_at: '2026-11-20T11:00:00Z' }
    ]
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: twoConversations })
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({ items: [] })
    vi.spyOn(convApi, 'sendMessage').mockResolvedValue({
      id: 'reply-1',
      role: 'assistant',
      content: '已回覆',
      status: 'answered',
      citations: [],
      created_at: '2026-11-20T10:00:00Z'
    })

    const wrapper = mount(ConversationView)
    await flushPromises()

    const input = wrapper.find('#chat-message-input')

    // 1. Type draft on c-1
    await input.setValue('對話一的未送出草稿')

    // 2. Switch to c-2
    const items = wrapper.findAll('.conversation-item')
    await items[1].trigger('click')
    await flushPromises()

    // Draft on c-2 is initially empty
    expect((input.element as HTMLTextAreaElement).value).toBe('')

    // 3. Type draft on c-2
    await input.setValue('對話二的草稿備忘')

    // 4. Switch back to c-1 -> c-1 draft is restored!
    await items[0].trigger('click')
    await flushPromises()
    expect((input.element as HTMLTextAreaElement).value).toBe('對話一的未送出草稿')

    // 5. Send message on c-1 -> clears input and draft
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()
    expect((input.element as HTMLTextAreaElement).value).toBe('')

    // 6. Switch back to c-2 -> c-2 draft is still preserved!
    await items[1].trigger('click')
    await flushPromises()
    expect((input.element as HTMLTextAreaElement).value).toBe('對話二的草稿備忘')

    // 7. Switch back to c-1 -> draft is still empty (was sent)
    await items[0].trigger('click')
    await flushPromises()
    expect((input.element as HTMLTextAreaElement).value).toBe('')
  })

  it('handleCreateConversation invalidates in-flight listMessages', async () => {
    let resolveC1!: (val: { items: Message[] }) => void
    const c1Promise = new Promise<{ items: Message[] }>((resolve) => {
      resolveC1 = resolve
    })

    vi.spyOn(convApi, 'listConversations').mockResolvedValue({
      items: [{ id: 'c-old', title: '舊對話', created_at: '2026-11-20T10:00:00Z' }]
    })
    vi.spyOn(convApi, 'listMessages').mockReturnValueOnce(c1Promise)
    vi.spyOn(convApi, 'createConversation').mockResolvedValue({
      id: 'c-new',
      title: '全新對話',
      created_at: '2026-11-20T10:10:00Z'
    })

    const wrapper = mount(ConversationView)
    // Old listMessages is in flight

    // User creates new conversation
    await wrapper.find('.conv-title-input').setValue('全新對話')
    await wrapper.find('form.create-conv-form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('全新對話')

    // Old listMessages resolves late
    resolveC1({
      items: [
        {
          id: 'm-old',
          role: 'assistant',
          content: '舊對話的幽靈訊息',
          status: 'answered',
          citations: [],
          created_at: '2026-11-20T10:00:00Z'
        }
      ]
    })
    await flushPromises()

    // The late response must NOT be placed in the new conversation
    expect(wrapper.text()).not.toContain('舊對話的幽靈訊息')
  })

  it('failed send including 429 removes optimistic message, restores draft, and shows error', async () => {
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({
      items: [{ id: 'c-1', title: '測試對話', created_at: '2026-11-20T10:00:00Z' }]
    })
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({ items: [] })
    vi.spyOn(convApi, 'sendMessage').mockRejectedValue(
      new (await import('../../api/auth')).ApiError(429, '請求過於頻繁或已達用量上限，請稍候再試。')
    )

    const wrapper = mount(ConversationView)
    await flushPromises()

    const input = wrapper.find('#chat-message-input')
    await input.setValue('429 超額提問筆記')
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()

    // 1. Optimistic message must be removed (server rejected it)
    expect(wrapper.text()).not.toContain('429 超額提問筆記')

    // 2. Draft content must be restored into input so user does not lose their text
    expect((input.element as HTMLTextAreaElement).value).toBe('429 超額提問筆記')

    // 3. Error alert is shown
    expect(wrapper.text()).toContain('請求過於頻繁或已達用量上限，請稍候再試。')
  })

  it('failed createConversation does not invalidate active conversation loading', async () => {
    let resolveC1!: (val: { items: Message[] }) => void
    const c1Promise = new Promise<{ items: Message[] }>((resolve) => {
      resolveC1 = resolve
    })

    vi.spyOn(convApi, 'listConversations').mockResolvedValue({
      items: [{ id: 'c-active', title: '既有對話', created_at: '2026-11-20T10:00:00Z' }]
    })
    vi.spyOn(convApi, 'listMessages').mockReturnValueOnce(c1Promise)
    vi.spyOn(convApi, 'createConversation').mockRejectedValue(
      new (await import('../../api/auth')).ApiError(500, '伺服器建立失敗')
    )

    const wrapper = mount(ConversationView)
    await flushPromises()
    // listMessages for c-active is in flight

    // Attempt to create conversation which fails
    await wrapper.find('.conv-title-input').setValue('嘗試建立但失敗')
    await wrapper.find('form.create-conv-form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('伺服器建立失敗')

    // Active load completes
    resolveC1({
      items: [
        {
          id: 'm-active',
          role: 'assistant',
          content: '既有對話的重要紀錄',
          status: 'answered',
          citations: [],
          created_at: '2026-11-20T10:00:00Z'
        }
      ]
    })
    await flushPromises()

    // Active load must NOT be discarded
    expect(wrapper.text()).toContain('既有對話的重要紀錄')
  })

  it('deleting inactive conversation does not invalidate active conversation loading', async () => {
    const twoConversations = [
      { id: 'c-active', title: '目前中對話', created_at: '2026-11-20T10:00:00Z' },
      { id: 'c-inactive', title: '次要對話', created_at: '2026-11-20T11:00:00Z' }
    ]
    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: twoConversations })

    let resolveActive!: (val: { items: Message[] }) => void
    const activePromise = new Promise<{ items: Message[] }>((resolve) => {
      resolveActive = resolve
    })
    vi.spyOn(convApi, 'listMessages').mockReturnValueOnce(activePromise)
    vi.spyOn(convApi, 'deleteConversation').mockResolvedValue(undefined)

    const wrapper = mount(ConversationView)
    await flushPromises()
    // listMessages for c-active is in flight

    // Delete inactive conversation c-inactive
    const deleteButtons = wrapper.findAll('button.btn-delete-conv')
    expect(deleteButtons.length).toBe(2)
    await deleteButtons[1].trigger('click') // click delete on c-inactive
    await flushPromises()

    // Confirm deletion
    const confirmBtn = wrapper.find('.dialog-actions button.btn-danger')
    await confirmBtn.trigger('click')
    await flushPromises()

    // Active load finishes
    resolveActive({
      items: [
        {
          id: 'm-preserved',
          role: 'assistant',
          content: '在刪除其他對話期間載入完成的訊息',
          status: 'answered',
          citations: [],
          created_at: '2026-11-20T10:00:00Z'
        }
      ]
    })
    await flushPromises()

    // Active conversation load was not invalidated by deleting an inactive conversation
    expect(wrapper.text()).toContain('在刪除其他對話期間載入完成的訊息')
  })
})
