const googleDomains = ['google.com', 'google.com.tw', 'google.co.jp']
const urlStart = /^(?:[a-z][a-z0-9+.-]*:|\/\/|www\.|maps\.|goo\.gl\/|google\.(?:com|co\.jp)\/)/i
const shareCode = /^[a-zA-Z0-9_-]+\/?$/

export const maxMapUrlLength = 2048
export const mapUrlError = '請貼上有效的 Google Maps HTTPS 分享連結。'

export function looksLikeUrl(value: string): boolean {
  return urlStart.test(value.trim())
}

export function validMapUrl(raw: string | null | undefined): string | null {
  const value = raw?.trim()
  if (!value || value.length > maxMapUrlLength || /[\s\u0000-\u001f\u007f\\]/.test(value)) return null
  const parts = /^https:\/\/([^/?#]+)([^?#]*)/i.exec(value)
  if (!parts) return null
  const host = parts[1].toLowerCase()
  const path = parts[2]
  if (path.replace(/%2e/gi, '.').split(/\/|%2f/i).some(segment => segment === '.' || segment === '..')) return null

  if (host === 'maps.app.goo.gl') return path.startsWith('/') && shareCode.test(path.slice(1)) ? value : null
  if (host === 'goo.gl') return path.startsWith('/maps/') && shareCode.test(path.slice(6)) ? value : null

  const mapPath = path === '/maps' || path.startsWith('/maps/')
  const allowed = googleDomains.some(domain =>
    ((host === domain || host === `www.${domain}`) && mapPath)
    || (host === `maps.${domain}` && (mapPath || path === '' || path === '/'))
  )
  return allowed ? value : null
}

export function locationInputError(value: string): string {
  const input = value.trim()
  if (looksLikeUrl(input)) return validMapUrl(input) ? '' : mapUrlError
  return input.length > 1000 ? '地址不可超過 1,000 字元。' : ''
}

export function mapsDestination(location: { map_url?: string | null; address?: string; city?: string }): string | null {
  const address = location.address?.trim() || ''
  const saved = validMapUrl(location.map_url) || validMapUrl(address)
  if (saved || !address || looksLikeUrl(address)) return saved
  const city = location.city?.trim()
  const query = city && !address.includes(city) ? `${city} ${address}` : address
  const url = `https://www.google.com/maps/search/?${new URLSearchParams({ api: '1', query })}`
  return url.length <= maxMapUrlLength ? url : null
}
