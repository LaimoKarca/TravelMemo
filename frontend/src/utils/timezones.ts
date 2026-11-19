/**
 * Timezone utilities and global catalog support for TravelMemo.
 *
 * Provenance: Generated from project deployed tzdata (version 2026.6, locked in requirements.lock.txt)
 * via importlib.resources tzdata.zoneinfo/zone.tab.
 * Conforms to the chat controls, timezones, and safety UI contract.
 */

import timezoneCatalog from '../data/timezones.json';

export interface TimezoneOption {
  value: string;
  label: string;
}

export interface TimezoneCatalogEntry {
  zone: string;
  country: string;
  coordinates?: string;
  comments?: string;
}

export const DEFAULT_TIMEZONE = 'Asia/Taipei';

// Curated Traditional Chinese translations for major world/Asian travel hubs
const CURATED_CITIES_ZH: Record<string, string> = {
  Taipei: '台北',
  Tokyo: '東京',
  Seoul: '首爾',
  Hong_Kong: '香港',
  Macau: '澳門',
  Singapore: '新加坡',
  Bangkok: '曼谷',
  Kuala_Lumpur: '吉隆坡',
  Manila: '馬尼拉',
  Jakarta: '雅加達',
  Ho_Chi_Minh: '胡志明市',
  Shanghai: '上海',
  Beijing: '北京',
  Urumqi: '烏魯木齊',
  Dubai: '杜拜',
  Doha: '杜哈',
  Riyadh: '利雅德',
  London: '倫敦',
  Paris: '巴黎',
  Berlin: '柏林',
  Rome: '羅馬',
  Madrid: '馬德里',
  Amsterdam: '阿姆斯特丹',
  Vienna: '維也納',
  Zurich: '蘇黎世',
  Prague: '布拉格',
  Athens: '雅典',
  Istanbul: '伊斯坦堡',
  Cairo: '開羅',
  New_York: '紐約',
  Los_Angeles: '洛杉磯',
  Chicago: '芝加哥',
  Denver: '丹佛',
  Phoenix: '鳳凰城',
  Honolulu: '檀香山',
  Anchorage: '安克拉治',
  Toronto: '多倫多',
  Vancouver: '溫哥華',
  Montreal: '蒙特婁',
  Edmonton: '艾德蒙頓',
  Winnipeg: '溫尼伯',
  Halifax: '哈利法克斯',
  Sydney: '雪梨',
  Melbourne: '墨爾本',
  Brisbane: '布里斯本',
  Perth: '伯斯',
  Adelaide: '阿德萊德',
  Darwin: '達爾文',
  Auckland: '奧克蘭',
  Sao_Paulo: '聖保羅',
  Buenos_Aires: '布宜諾斯艾利斯',
  Santiago: '聖地牙哥',
  Lima: '利馬',
  Bogota: '波哥大',
  Mexico_City: '墨西哥城',
  Johannesburg: '約翰尼斯堡',
  Reykjavik: '雷克雅維克',
  Dublin: '都柏林',
  Lisbon: '里斯本',
  Helsinki: '赫爾辛基',
  Stockholm: '斯德哥爾摩',
  Oslo: '奧斯陸',
  Copenhagen: '哥本哈根',
  Warsaw: '華沙',
  Budapest: '布達佩斯',
  Moscow: '莫斯科',
  Kolkata: '加爾各答',
  Colombo: '可倫坡',
  Kathmandu: '加德滿都',
  Dhaka: '達卡',
  Yangon: '仰光',
  Vientiane: '永珍',
  Phnom_Penh: '金邊',
};

// Familiar / default choices to pin near the top
const FAMILIAR_ZONES: string[] = [
  'Asia/Taipei',
  'Asia/Tokyo',
  'Asia/Seoul',
  'Asia/Hong_Kong',
  'Asia/Singapore',
  'Asia/Bangkok',
  'Asia/Dubai',
  'Europe/London',
  'Europe/Paris',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
];

const catalogEntries: TimezoneCatalogEntry[] = Array.isArray(timezoneCatalog)
  ? (timezoneCatalog as TimezoneCatalogEntry[])
  : (timezoneCatalog as { timezones?: TimezoneCatalogEntry[] }).timezones || [];

// Case-insensitive lookup map for IANA zones
const zoneLowerMap = new Map<string, string>();
for (const entry of catalogEntries) {
  zoneLowerMap.set(entry.zone.toLowerCase(), entry.zone);
}
// Ensure UTC is present
zoneLowerMap.set('utc', 'UTC');

/**
 * Parse and validate fixed UTC offset string.
 * Supports UTC+/-H[:MM], +/-H[:MM], bounded UTC-12:00 to UTC+14:00.
 */
function parseFixedUtc(str: string): string | null {
  const m = str.trim().match(/^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$/i);
  if (!m) return null;

  const sign = m[1];
  const hours = parseInt(m[2], 10);
  const minutes = m[3] ? parseInt(m[3], 10) : 0;

  if (minutes < 0 || minutes > 59) return null;

  const totalMinutes = (hours * 60 + minutes) * (sign === '-' ? -1 : 1);
  // Bounded real-world range UTC-12:00 to UTC+14:00 (-720 to 840)
  if (totalMinutes < -720 || totalMinutes > 840) return null;

  if (totalMinutes === 0) return 'UTC+00:00';

  const pad = (n: number) => String(n).padStart(2, '0');
  return `UTC${sign}${pad(hours)}:${pad(minutes)}`;
}

/** Calendar date at an instant in the trip's IANA zone or fixed UTC offset. */
export function getTripLocalDate(now: Date, timeZone: string): string {
  const fixed = parseFixedUtc(timeZone);
  if (fixed) {
    const minutes = (Number(fixed.slice(4, 6)) * 60 + Number(fixed.slice(7, 9)))
      * (fixed[3] === '-' ? -1 : 1);
    return new Date(now.getTime() + minutes * 60_000).toISOString().slice(0, 10);
  }

  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    calendar: 'gregory',
    numberingSystem: 'latn',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const value = (type: 'year' | 'month' | 'day') => parts.find(part => part.type === type)!.value;
  return `${value('year').padStart(4, '0')}-${value('month')}-${value('day')}`;
}

export function getTripStatus(
  startDate: string,
  endDate: string,
  timeZone: string,
  now: Date,
): 'upcoming' | 'current' | 'past' {
  const today = getTripLocalDate(now, timeZone);
  if (today < startDate) return 'upcoming';
  if (today > endDate) return 'past';
  return 'current';
}

/**
 * Get formatted UTC offset at a given referenceDate (handling DST).
 * Returns e.g. "UTC+08:00", "UTC-04:00".
 */
export function getTimezoneOffset(timeZone: string, referenceDate?: string | Date): string {
  const fixed = parseFixedUtc(timeZone);
  if (fixed) return fixed;

  try {
    let date: Date;
    if (!referenceDate) {
      date = new Date();
    } else if (typeof referenceDate === 'string') {
      date = referenceDate.includes('T')
        ? new Date(referenceDate)
        : new Date(`${referenceDate}T12:00:00Z`);
    } else {
      date = referenceDate;
    }

    if (isNaN(date.getTime())) {
      date = new Date();
    }

    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      timeZoneName: 'longOffset',
    }).formatToParts(date);

    const tzPart = parts.find((p) => p.type === 'timeZoneName')?.value;
    if (!tzPart || tzPart === 'GMT') {
      return 'UTC+00:00';
    }
    return tzPart.replace(/^GMT/, 'UTC');
  } catch {
    return '';
  }
}

/**
 * Returns a list of localized timezone options for datalists and dropdowns.
 *
 * @param referenceDate Optional trip date string (e.g. "2026-06-01") for DST-aware offset.
 * @param locale Optional BCP-47 locale, defaults to 'zh-TW'.
 */
export function getTimezoneOptions(
  referenceDate?: string,
  locale = 'zh-TW'
): TimezoneOption[] {
  const isZh = locale.toLowerCase().startsWith('zh');

  // Intl region display names if available
  let displayNames: Intl.DisplayNames | null = null;
  if (typeof Intl !== 'undefined' && Intl.DisplayNames) {
    try {
      displayNames = new Intl.DisplayNames([locale, 'zh-TW', 'zh-Hant', 'en'], {
        type: 'region',
      });
    } catch {
      displayNames = null;
    }
  }

  const formatOption = (entry: TimezoneCatalogEntry): TimezoneOption => {
    const offset = getTimezoneOffset(entry.zone, referenceDate);
    if (!offset) {
      // Fallback for unsupported zones in browser
      return { value: entry.zone, label: entry.zone };
    }

    if (entry.zone === 'UTC') {
      const utcLabel = isZh ? '世界協調時間 (UTC)' : 'Coordinated Universal Time (UTC)';
      return {
        value: 'UTC',
        label: `${utcLabel} (${offset}) · UTC`,
      };
    }

    let countryName = entry.country;
    if (entry.country && displayNames) {
      try {
        countryName = displayNames.of(entry.country) || entry.country;
      } catch {
        countryName = entry.country;
      }
    }

    // Extract city name from zone
    const parts = entry.zone.split('/');
    const rawCity = parts[parts.length - 1];
    let cityName = rawCity.replace(/_/g, ' ');

    if (isZh && CURATED_CITIES_ZH[rawCity]) {
      cityName = CURATED_CITIES_ZH[rawCity];
    }

    const label = countryName
      ? `${countryName} - ${cityName} (${offset}) · ${entry.zone}`
      : `${cityName} (${offset}) · ${entry.zone}`;

    return {
      value: entry.zone,
      label,
    };
  };

  const options: TimezoneOption[] = [];
  const seen = new Set<string>();

  // 1. Familiar zones first
  for (const fz of FAMILIAR_ZONES) {
    const entry = catalogEntries.find((e) => e.zone === fz) || {
      zone: fz,
      country: fz === 'UTC' ? '' : fz.startsWith('Asia/Taipei') ? 'TW' : '',
    };
    const opt = formatOption(entry);
    options.push(opt);
    seen.add(entry.zone);
  }

  // 2. All remaining catalog entries
  const remaining: TimezoneOption[] = [];
  for (const entry of catalogEntries) {
    if (seen.has(entry.zone)) continue;
    remaining.push(formatOption(entry));
    seen.add(entry.zone);
  }

  // Sort remaining by label alphabetically
  remaining.sort((a, b) => a.label.localeCompare(b.label, locale));

  return [...options, ...remaining];
}

/**
 * Normalize user-entered timezone value into a canonical IANA identifier
 * or canonical fixed UTC offset (e.g. UTC+08:00).
 *
 * Preserves custom text or existing non-common zones if they cannot be mapped.
 */
export function normalizeTimezoneInput(value: string): string {
  if (!value || typeof value !== 'string') return '';
  const trimmed = value.trim();
  if (!trimmed) return '';

  // 1. Plain UTC or GMT
  if (/^(?:UTC|GMT)$/i.test(trimmed)) {
    return 'UTC';
  }

  // 2. Fixed UTC offset: e.g. UTC+8, UTC-03:30, +08:00, -5
  const fixed = parseFixedUtc(trimmed);
  if (fixed) {
    return fixed;
  }

  // 3. Option label format: e.g. "台灣 - 台北 (UTC+08:00) · Asia/Taipei"
  if (trimmed.includes('·')) {
    const candidate = trimmed.split('·').pop()?.trim() || '';
    if (zoneLowerMap.has(candidate.toLowerCase())) {
      return zoneLowerMap.get(candidate.toLowerCase())!;
    }
  }

  // 4. Exact or case-insensitive match against known IANA zones
  if (zoneLowerMap.has(trimmed.toLowerCase())) {
    return zoneLowerMap.get(trimmed.toLowerCase())!;
  }

  // 5. Check if user typed a curated city name directly (e.g. "Taipei" -> "Asia/Taipei")
  for (const [enCity, zhCity] of Object.entries(CURATED_CITIES_ZH)) {
    if (
      trimmed.toLowerCase() === enCity.toLowerCase() ||
      trimmed.toLowerCase() === zhCity.toLowerCase() ||
      trimmed.toLowerCase() === enCity.replace(/_/g, ' ').toLowerCase()
    ) {
      const match = catalogEntries.find((e) => e.zone.endsWith('/' + enCity));
      if (match) {
        return match.zone;
      }
    }
  }

  // 6. Preserve custom text / existing non-common zones
  return trimmed;
}
