import { describe, it, expect } from 'vitest'
import {
  DEFAULT_TIMEZONE,
  getTimezoneOffset,
  getTimezoneOptions,
  normalizeTimezoneInput
} from '../timezones'
import timezoneCatalog from '../../data/timezones.json'

describe('Timezone UI Utilities & Catalog', () => {
  it('verifies locked provenance version and catalog count', () => {
    expect(timezoneCatalog.provenance.version).toBe('2026.6')
    expect(timezoneCatalog.provenance.source).toBe('tzdata.zoneinfo/zone.tab')
    expect(timezoneCatalog.timezones.length).toBe(419)
  })

  it('provides DEFAULT_TIMEZONE as Asia/Taipei', () => {
    expect(DEFAULT_TIMEZONE).toBe('Asia/Taipei')
  })

  it('getTimezoneOptions returns options with Asia/Taipei as familiar first choice', () => {
    const options = getTimezoneOptions('2026-06-01', 'zh-TW')
    expect(options.length).toBeGreaterThanOrEqual(418)

    const first = options[0]
    expect(first.value).toBe('Asia/Taipei')
    expect(first.label).toContain('台北')
    expect(first.label).toContain('UTC+08:00')
    expect(first.label).toContain('Asia/Taipei')
  })

  it('getTimezoneOptions reflects daylight saving time (DST) based on referenceDate', () => {
    const summerOpts = getTimezoneOptions('2026-06-01', 'zh-TW')
    const nySummer = summerOpts.find((o) => o.value === 'America/New_York')
    expect(nySummer).toBeDefined()
    expect(nySummer?.label).toContain('UTC-04:00')

    const winterOpts = getTimezoneOptions('2026-01-01', 'zh-TW')
    const nyWinter = winterOpts.find((o) => o.value === 'America/New_York')
    expect(nyWinter).toBeDefined()
    expect(nyWinter?.label).toContain('UTC-05:00')
  })

  it('multi-zone countries show city name and never imply one offset for the whole country', () => {
    const options = getTimezoneOptions('2026-06-01', 'zh-TW')
    const ny = options.find((o) => o.value === 'America/New_York')
    const la = options.find((o) => o.value === 'America/Los_Angeles')
    expect(ny?.label).toContain('紐約')
    expect(la?.label).toContain('洛杉磯')
    expect(ny?.label).not.toBe(la?.label)
  })

  it('getTimezoneOffset helper returns accurate offsets', () => {
    expect(getTimezoneOffset('Asia/Taipei')).toBe('UTC+08:00')
    expect(getTimezoneOffset('UTC')).toBe('UTC+00:00')
    expect(getTimezoneOffset('UTC+8')).toBe('UTC+08:00')
    expect(getTimezoneOffset('UTC-03:30')).toBe('UTC-03:30')
  })

  it('normalizeTimezoneInput normalizes standard IANA and case-insensitive inputs', () => {
    expect(normalizeTimezoneInput('Asia/Taipei')).toBe('Asia/Taipei')
    expect(normalizeTimezoneInput('asia/taipei')).toBe('Asia/Taipei')
    expect(normalizeTimezoneInput('europe/london')).toBe('Europe/London')
    expect(normalizeTimezoneInput('UTC')).toBe('UTC')
    expect(normalizeTimezoneInput('utc')).toBe('UTC')
  })

  it('normalizeTimezoneInput normalizes and bounds fixed UTC offsets', () => {
    expect(normalizeTimezoneInput('UTC+8')).toBe('UTC+08:00')
    expect(normalizeTimezoneInput('utc-3:30')).toBe('UTC-03:30')
    expect(normalizeTimezoneInput('+08:00')).toBe('UTC+08:00')
    expect(normalizeTimezoneInput('-05:00')).toBe('UTC-05:00')
    expect(normalizeTimezoneInput('UTC+0')).toBe('UTC+00:00')
  })

  it('normalizeTimezoneInput extracts identifier from datalist option label', () => {
    const rawLabel = '台灣 - 台北 (UTC+08:00) · Asia/Taipei'
    expect(normalizeTimezoneInput(rawLabel)).toBe('Asia/Taipei')
  })

  it('normalizeTimezoneInput maps curated city names to IANA zones', () => {
    expect(normalizeTimezoneInput('Taipei')).toBe('Asia/Taipei')
    expect(normalizeTimezoneInput('台北')).toBe('Asia/Taipei')
    expect(normalizeTimezoneInput('Tokyo')).toBe('Asia/Tokyo')
    expect(normalizeTimezoneInput('東京')).toBe('Asia/Tokyo')
  })

  it('normalizeTimezoneInput preserves custom text and handles blanks', () => {
    expect(normalizeTimezoneInput('')).toBe('')
    expect(normalizeTimezoneInput('   ')).toBe('')
    expect(normalizeTimezoneInput('Custom/NonExistent')).toBe('Custom/NonExistent')
  })
})
