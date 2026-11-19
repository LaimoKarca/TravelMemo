import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ConversationView from '../ConversationView.vue'
import * as convApi from '../../api/conversation'
import type { ConversationSummary, Message } from '../../types/conversation'

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

describe('ConversationView', () => {
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

    vi.spyOn(convApi, 'listConversations').mockResolvedValue({ items: [...mockConversations] })
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({ items: [...mockMessages] })
    vi.spyOn(convApi, 'sendMessage').mockResolvedValue({
      id: 'm-default-reply',
      role: 'assistant',
      content: '預設回覆',
      status: 'answered',
      citations: [],
      created_at: '2026-11-20T10:01:00Z'
    })
  })

  it('renders conversations list, initial blank chat, and loads conversation on click', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    // Title exists, but usage disclosure and tokens/quota are removed
    expect(wrapper.text()).toContain('AI 旅程助理')
    expect(wrapper.find('.usage-disclosure').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('今日用量')
    expect(wrapper.text()).not.toContain('消耗 Tokens')
    expect(wrapper.text()).not.toContain('模型：')

    // Initial view is new blank chat
    expect(wrapper.find('.empty-chat-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('想找回哪段旅程？')
    expect(wrapper.find('#chat-message-input').exists()).toBe(true)

    // Collapsed history details with far-right chevron and aria-expanded
    const historyDetails = wrapper.find('details.history-details')
    expect(historyDetails.exists()).toBe(true)
    expect((historyDetails.element as HTMLDetailsElement).open).toBe(false)

    const summary = historyDetails.find('summary.history-summary')
    expect(summary.exists()).toBe(true)
    expect(summary.attributes('aria-expanded')).toBe('false')
    expect(summary.text()).toContain('歷史對話 (1)')

    const chevron = summary.find('.history-chevron')
    expect(chevron.exists()).toBe(true)

    // Click conversation to load messages
    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()

    // Messages
    expect(wrapper.text()).toContain('我上次在京都有去嵐山嗎？')
    expect(wrapper.text()).toContain('是的，您在 2026-11-21 走訪了嵐山天龍寺')
    expect(wrapper.find('.message-status-pill').exists()).toBe(false)

    // Citations
    expect(wrapper.text()).toContain('嵐山天龍寺')
    expect(wrapper.text()).not.toContain('最新版本')
    expect(wrapper.text()).toContain('已註銷的咖啡店')
    expect(wrapper.text()).toContain('已刪除')
    expect(wrapper.findAll('.source-link')).toHaveLength(1)
  })

  it('clicking current citation emits view-citation', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    // Select c-1 to view citations
    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()

    const inspectBtn = wrapper.find('button.source-link')
    expect(inspectBtn.exists()).toBe(true)
    await inspectBtn.trigger('click')

    expect(wrapper.emitted('view-citation')).toBeTruthy()
    expect(wrapper.emitted('view-citation')![0][0]).toEqual(mockMessages[1].citations[0])
  })

  it('new conversation button resets to blank chat without DB call and focuses composer', async () => {
    const createSpy = vi.spyOn(convApi, 'createConversation')

    const wrapper = mount(ConversationView)
    await flushPromises()

    // Select c-1 first
    await wrapper.find('.conversation-item').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('我上次在京都有去嵐山嗎？')

    // Click new conversation button
    await wrapper.find('button.btn-new-conv').trigger('click')
    await flushPromises()

    // Should NOT create conversation in DB yet
    expect(createSpy).not.toHaveBeenCalled()
    // Should be in blank chat state
    expect(wrapper.find('.empty-chat-state').exists()).toBe(true)
  })

  it('on first send in blank chat lazily creates conversation then sends message and reloads list', async () => {
    vi.spyOn(convApi, 'listMessages').mockResolvedValue({ items: [{ id: 'server-user', role: 'user', content: '我有去過宇治嗎？', status: 'answered', citations: [], created_at: '' }] })
    const createSpy = vi.spyOn(convApi, 'createConversation').mockResolvedValue({
      id: 'c-lazy-1',
      title: '新對話',
      created_at: '2026-11-20T10:05:00Z'
    })
    const sendSpy = vi.spyOn(convApi, 'sendMessage').mockResolvedValue({
      id: 'm-3',
      role: 'assistant',
      content: '手記中未提及此類別紀錄。',
      status: 'insufficient_evidence',
      citations: [],
      created_at: '2026-11-20T10:05:01Z'
    })
    const listSpy = vi.spyOn(convApi, 'listConversations')

    const wrapper = mount(ConversationView)
    await flushPromises()

    // Blank chat: type and send
    await wrapper.find('#chat-message-input').setValue('我有去過宇治嗎？')
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()

    // Lazily created conversation with empty object
    expect(createSpy).toHaveBeenCalledWith({})
    expect(sendSpy).toHaveBeenCalledWith('c-lazy-1', { content: '我有去過宇治嗎？' })
    // Reloads conversation list to update auto-generated title
    expect(listSpy).toHaveBeenCalled()
    expect(wrapper.text()).toContain('我有去過宇治嗎？')
    expect(wrapper.text()).toContain('手記中未提及此類別紀錄。')
  })

  it('if send fails on first send, keeps draft and reuses created ID on retry without deleting data', async () => {
    const createSpy = vi.spyOn(convApi, 'createConversation').mockResolvedValue({
      id: 'c-lazy-retry',
      title: '新對話',
      created_at: '2026-11-20T10:05:00Z'
    })
    const deleteSpy = vi.spyOn(convApi, 'deleteConversation')
    const sendSpy = vi.spyOn(convApi, 'sendMessage')
      .mockRejectedValueOnce(new (await import('../../api/auth')).ApiError(500, '發送失敗'))
      .mockResolvedValueOnce({
        id: 'm-retry-ok',
        role: 'assistant',
        content: '重試成功回覆',
        status: 'answered',
        citations: [],
        created_at: '2026-11-20T10:05:02Z'
      })

    const wrapper = mount(ConversationView)
    await flushPromises()

    const input = wrapper.find('#chat-message-input')
    await input.setValue('重試發問草稿')
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()

    // Create was called once
    expect(createSpy).toHaveBeenCalledTimes(1)
    // Never delete potentially persisted conversation
    expect(deleteSpy).not.toHaveBeenCalled()
    // Draft is kept in composer
    expect((input.element as HTMLTextAreaElement).value).toBe('重試發問草稿')
    expect(wrapper.text()).toContain('發送失敗')

    // Retry sending
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()

    // Reuses the created ID without re-creating
    expect(createSpy).toHaveBeenCalledTimes(1)
    expect(sendSpy).toHaveBeenLastCalledWith('c-lazy-retry', { content: '重試發問草稿' })
    expect(deleteSpy).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('重試成功回覆')
  })

  it('removes keyboard instructions from placeholder while preserving Enter shortcut', async () => {
    vi.spyOn(convApi, 'createConversation').mockResolvedValue({
      id: 'c-shortcut',
      title: '新對話',
      created_at: '2026-11-20T10:06:00Z'
    })
    const sendSpy = vi.spyOn(convApi, 'sendMessage').mockResolvedValue({
      id: 'm-enter',
      role: 'assistant',
      content: '捷徑正常回覆',
      status: 'answered',
      citations: [],
      created_at: '2026-11-20T10:06:00Z'
    })

    const wrapper = mount(ConversationView)
    await flushPromises()

    const input = wrapper.find('#chat-message-input')
    expect(input.attributes('placeholder')).toBe('詢問任何關於您旅程手記的問題...')
    expect(input.attributes('placeholder')).not.toContain('Enter')
    expect(input.attributes('placeholder')).not.toContain('Shift+Enter')

    await input.setValue('透過鍵盤發送訊息')
    await input.trigger('keydown.enter.exact')
    await flushPromises()

    expect(sendSpy).toHaveBeenCalledWith('c-shortcut', { content: '透過鍵盤發送訊息' })
  })

  it('toggles collapsed history details and updates aria-expanded', async () => {
    const wrapper = mount(ConversationView)
    await flushPromises()

    const details = wrapper.find('details.history-details')
    const summary = details.find('summary.history-summary')
    expect((details.element as HTMLDetailsElement).open).toBe(false)
    expect(summary.attributes('aria-expanded')).toBe('false')

    // Simulate native details toggle open
    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('toggle')

    expect(summary.attributes('aria-expanded')).toBe('true')
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
      // First click on c-2 (slow)
      .mockReturnValueOnce(c2Promise)
      // Next: user clicks c-1 (fast)
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

    const items = wrapper.findAll('.conversation-item')
    // Click c-2 (loads slowly)
    await items[1].trigger('click')

    // Before c-2 resolves, user clicks c-1
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

    // Select c-1
    const items = wrapper.findAll('.conversation-item')
    await items[0].trigger('click')
    await flushPromises()

    // User is on c-1, types message
    await wrapper.find('#chat-message-input').setValue('發送給對話一的新提問')
    await wrapper.find('form.chat-form').trigger('submit.prevent')

    expect(sendSpy).toHaveBeenCalledWith('c-1', { content: '發送給對話一的新提問' })

    // While send is pending, user clicks c-2
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
    const items = wrapper.findAll('.conversation-item')

    // 1. Select c-1 and type draft
    await items[0].trigger('click')
    await flushPromises()
    await input.setValue('對話一的未送出草稿')

    // 2. Switch to c-2
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

  it('handleStartNewConversation invalidates in-flight listMessages', async () => {
    let resolveC1!: (val: { items: Message[] }) => void
    const c1Promise = new Promise<{ items: Message[] }>((resolve) => {
      resolveC1 = resolve
    })

    vi.spyOn(convApi, 'listConversations').mockResolvedValue({
      items: [{ id: 'c-old', title: '舊對話', created_at: '2026-11-20T10:00:00Z' }]
    })
    vi.spyOn(convApi, 'listMessages').mockReturnValueOnce(c1Promise)

    const wrapper = mount(ConversationView)
    await flushPromises()

    // Click c-old (starts in-flight load)
    await wrapper.find('.conversation-item').trigger('click')

    // User clicks "+ 新對話" button
    await wrapper.find('.btn-new-conv').trigger('click')
    await flushPromises()

    expect(wrapper.find('.empty-chat-state').exists()).toBe(true)

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

    // The late response must NOT be placed in the blank chat
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

    // Select c-1
    await wrapper.find('.conversation-item').trigger('click')
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

  it('failed lazy createConversation on first send removes optimistic message, restores draft, and resets sendingMessage', async () => {
    vi.spyOn(convApi, 'createConversation').mockRejectedValue(
      new (await import('../../api/auth')).ApiError(500, '伺服器建立失敗')
    )

    const wrapper = mount(ConversationView)
    await flushPromises()

    const input = wrapper.find('#chat-message-input')
    await input.setValue('嘗試發送但建立對話失敗')
    await wrapper.find('form.chat-form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('伺服器建立失敗')
    expect(wrapper.text()).not.toContain('嘗試發送但建立對話失敗')
    expect((input.element as HTMLTextAreaElement).value).toBe('嘗試發送但建立對話失敗')
    // sendingMessage must be reset to false so button is not stuck in replying state
    expect(wrapper.find('button.send-btn').text()).toContain('發送')
  })

  it('first-create race: resetting to New while lazy create is in flight resets sendingMessage and preserves created conversation without deletion', async () => {
    let resolveCreate!: (val: ConversationSummary) => void
    const createPromise = new Promise<ConversationSummary>((resolve) => {
      resolveCreate = resolve
    })
    vi.spyOn(convApi, 'createConversation').mockReturnValueOnce(createPromise)
    const deleteSpy = vi.spyOn(convApi, 'deleteConversation')
    const sendSpy = vi.spyOn(convApi, 'sendMessage')

    const wrapper = mount(ConversationView)
    await flushPromises()

    // 1. In blank chat, user types and sends
    const input = wrapper.find('#chat-message-input')
    await input.setValue('發送後立即點擊新對話')
    await wrapper.find('form.chat-form').trigger('submit.prevent')

    // sending is in flight
    expect(wrapper.find('button.send-btn').text()).toContain('回覆中...')

    // 2. User clicks "+ 新對話" while lazy create is still in flight
    // Call handleStartNewConversation
    const newConvBtn = wrapper.find('button.btn-new-conv')
    await newConvBtn.trigger('click')
    await flushPromises()

    // 3. Lazy create now resolves late
    resolveCreate({
      id: 'c-late-created',
      title: '延遲建立成功的對話',
      created_at: '2026-11-20T10:10:00Z'
    })
    await flushPromises()

    // sendingMessage must NOT be stuck true
    expect(wrapper.find('button.send-btn').text()).toContain('發送')

    // Late message send should not have been called for aborted context
    expect(sendSpy).not.toHaveBeenCalled()

    // Never delete ambiguous potentially persisted data
    expect(deleteSpy).not.toHaveBeenCalled()

    // The created conversation is preserved in conversations list
    expect(wrapper.text()).toContain('延遲建立成功的對話')

    // Optimistic message from the aborted send is not left dangling
    expect(wrapper.text()).not.toContain('發送後立即點擊新對話')
  })

  it('first-create race: switching conversation while lazy create is in flight does not hijack target conversation', async () => {
    let resolveCreate!: (val: ConversationSummary) => void
    const createPromise = new Promise<ConversationSummary>((resolve) => {
      resolveCreate = resolve
    })
    vi.spyOn(convApi, 'createConversation').mockReturnValueOnce(createPromise)
    const deleteSpy = vi.spyOn(convApi, 'deleteConversation')
    const sendSpy = vi.spyOn(convApi, 'sendMessage')

    const wrapper = mount(ConversationView)
    await flushPromises()

    // 1. In blank chat, user types and sends
    await wrapper.find('#chat-message-input').setValue('發送後切換至舊對話')
    await wrapper.find('form.chat-form').trigger('submit.prevent')

    // 2. User switches to c-1
    const items = wrapper.findAll('.conversation-item')
    await items[0].trigger('click')
    await flushPromises()

    // 3. Late create resolves
    resolveCreate({
      id: 'c-late-switch',
      title: '切換期間建立的對話',
      created_at: '2026-11-20T10:12:00Z'
    })
    await flushPromises()

    // sendingMessage must reset to false
    expect(wrapper.find('button.send-btn').text()).toContain('發送')

    // Does not call send for aborted context
    expect(sendSpy).not.toHaveBeenCalled()

    // Never delete persisted row
    expect(deleteSpy).not.toHaveBeenCalled()

    // Preserved in list
    expect(wrapper.text()).toContain('切換期間建立的對話')
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

    // Select c-active
    const items = wrapper.findAll('.conversation-item')
    await items[0].trigger('click')
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
