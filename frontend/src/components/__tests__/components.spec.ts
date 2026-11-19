import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../../App.vue'
import BrandHeader from '../BrandHeader.vue'
import LoginForm from '../LoginForm.vue'
import OtpForm from '../OtpForm.vue'
import WelcomePanel from '../WelcomePanel.vue'
import StatusAlert from '../StatusAlert.vue'
import TripWorkspace from '../TripWorkspace.vue'
import * as authApi from '../../api/auth'
import * as travelApi from '../../api/travel'

describe('Frontend Vue Components', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('BrandHeader displays TravelMemo Georgia wordmark and subtitle', () => {
    const wrapper = mount(BrandHeader)
    expect(wrapper.find('.brand-name').text()).toBe('TravelMemo')
    expect(wrapper.find('.brand-subtitle').text()).toBe('旅程手記')
  })

  it('StatusAlert displays polite status alert message', () => {
    const wrapper = mount(StatusAlert, {
      props: {
        type: 'error',
        message: '驗證碼錯誤，請重試'
      }
    })
    expect(wrapper.attributes('aria-live')).toBe('polite')
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('驗證碼錯誤，請重試')
  })

  it('LoginForm renders accessible input without password field and emits submit', async () => {
    const wrapper = mount(LoginForm)
    // Verify no password input exists
    expect(wrapper.find('input[type="password"]').exists()).toBe(false)

    const emailInput = wrapper.find('input#email-input')
    expect(emailInput.exists()).toBe(true)
    expect(emailInput.attributes('type')).toBe('email')

    await emailInput.setValue('test@travelmemo.local')
    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')![0]).toEqual(['test@travelmemo.local'])
  })

  it('OtpForm renders 6-digit input, resend button, and emits verify and back', async () => {
    const wrapper = mount(OtpForm, {
      props: {
        email: 'test@travelmemo.local',
        retryAfter: 60
      }
    })

    const otpInput = wrapper.find('input#otp-input')
    expect(otpInput.exists()).toBe(true)
    expect(otpInput.attributes('maxlength')).toBe('6')
    expect(otpInput.attributes('inputmode')).toBe('numeric')

    // Submit with 6 digits
    await otpInput.setValue('123456')
    await wrapper.find('form').trigger('submit.prevent')
    expect(wrapper.emitted('verify')).toBeTruthy()
    expect(wrapper.emitted('verify')![0]).toEqual(['123456'])

    // Click back to email
    await wrapper.find('.back-btn').trigger('click')
    expect(wrapper.emitted('back')).toBeTruthy()
  })

  it('WelcomePanel renders user email and Phase 1 notice without fake buttons', async () => {
    const wrapper = mount(WelcomePanel, {
      props: {
        user: { id: 'u-1', email: 'traveler@travelmemo.local' }
      }
    })

    expect(wrapper.text()).toContain('traveler@travelmemo.local')
    expect(wrapper.text()).toContain('旅程管理將於下一階段開放')
    // Ensure only logout button is an action button
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBe(1)
    expect(buttons[0].text()).toContain('登出手記')

    await buttons[0].trigger('click')
    expect(wrapper.emitted('logout')).toBeTruthy()
  })

  it('App switches to TripWorkspace when signed in and handles logout', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValue({
      user: { id: 'u-1', email: 'session-traveler@travelmemo.local' },
      csrf_token: 'test-token'
    })
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: [] })
    vi.spyOn(travelApi, 'listPlaces').mockResolvedValue({ items: [] })
    const logoutSpy = vi.spyOn(authApi, 'logout').mockResolvedValue(undefined)

    const wrapper = mount(App)
    await flushPromises()

    // Verify TripWorkspace is rendered
    expect(wrapper.findComponent(TripWorkspace).exists()).toBe(true)
    expect(wrapper.text()).toContain('session-traveler')
    expect(wrapper.text()).not.toContain('session-traveler@travelmemo.local')

    // Click logout
    const logoutBtn = wrapper.find('button.logout-button')
    expect(logoutBtn.exists()).toBe(true)
    await logoutBtn.trigger('click')
    await flushPromises()

    expect(logoutSpy).toHaveBeenCalled()
    // Should be back to email LoginForm
    expect(wrapper.findComponent(LoginForm).exists()).toBe(true)
  })

  it('shared auth request returns UI to login when 401 is encountered', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValue({
      user: { id: 'u-1', email: 'session-traveler@travelmemo.local' },
      csrf_token: 'test-token'
    })
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: [] })
    vi.spyOn(travelApi, 'listPlaces').mockResolvedValue({ items: [] })

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.findComponent(TripWorkspace).exists()).toBe(true)

    // Simulate an unexpected 401 from any shared request
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: '登入狀態已過期' })
    } as Response)

    try {
      await authApi.request('/trips', { method: 'GET' })
    } catch {
      // expected 401 ApiError
    }
    await flushPromises()

    // UI should return to login step with alert
    expect(wrapper.findComponent(LoginForm).exists()).toBe(true)
    expect(wrapper.text()).toContain('您的登入狀態已過期，請重新登入。')
  })

  it('wrong OTP on verify-code keeps user on OTP form and allows retry without new code', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValue(null)
    vi.spyOn(authApi, 'requestCode').mockResolvedValue({ message: '驗證碼已寄出', retry_after: 60 })

    const wrapper = mount(App)
    await flushPromises()

    // 1. Submit email to transition to OTP step
    const loginForm = wrapper.findComponent(LoginForm)
    expect(loginForm.exists()).toBe(true)
    await loginForm.vm.$emit('submit', 'retry-tester@travelmemo.local')
    await flushPromises()

    // Now on OtpForm
    const otpForm = wrapper.findComponent(OtpForm)
    expect(otpForm.exists()).toBe(true)

    // 2. Submit wrong OTP code (401 error)
    const verifySpy = vi.spyOn(authApi, 'verifyCode')
      .mockRejectedValueOnce(new authApi.ApiError(401, '驗證碼錯誤或已過期，請重新輸入或索取驗證碼。'))

    await otpForm.vm.$emit('verify', '000000')
    await flushPromises()

    // MUST remain on OtpForm to allow retry; MUST NOT reset to LoginForm
    expect(wrapper.findComponent(OtpForm).exists()).toBe(true)
    expect(wrapper.findComponent(LoginForm).exists()).toBe(false)
    expect(wrapper.text()).toContain('驗證碼錯誤或已過期，請重新輸入或索取驗證碼。')

    // 3. User immediately retries with correct code without re-requesting code
    verifySpy.mockResolvedValueOnce({
      user: { id: 'u-valid', email: 'retry-tester@travelmemo.local' },
      csrf_token: 'valid-csrf-token'
    })
    vi.spyOn(travelApi, 'listTrips').mockResolvedValue({ items: [] })
    vi.spyOn(travelApi, 'listPlaces').mockResolvedValue({ items: [] })

    await otpForm.vm.$emit('verify', '123456')
    await flushPromises()

    // Successfully logged in to TripWorkspace
    expect(wrapper.findComponent(TripWorkspace).exists()).toBe(true)
    expect(wrapper.text()).toContain('retry-tester')
    expect(wrapper.text()).not.toContain('retry-tester@travelmemo.local')
  })
})
