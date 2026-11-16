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
    expect(wrapper.text()).toContain('session-traveler@travelmemo.local')

    // Click logout
    const logoutBtn = wrapper.find('button.logout-button')
    expect(logoutBtn.exists()).toBe(true)
    await logoutBtn.trigger('click')
    await flushPromises()

    expect(logoutSpy).toHaveBeenCalled()
    // Should be back to email LoginForm
    expect(wrapper.findComponent(LoginForm).exists()).toBe(true)
  })
})
