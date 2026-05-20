import { createContext, useContext } from 'react'

import { Language, getT, LOCALE_BY_LANGUAGE, tr } from './i18n'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: ReturnType<typeof getT>
}

export type ThemeMode = 'terracotta'

export const THEMES: { value: ThemeMode; label: string; dotColor: string }[] = [
  { value: 'terracotta', label: 'Noēsis', dotColor: '#b8542f' },
]

export const DEFAULT_THEME: ThemeMode = 'terracotta'

interface ThemeContextType {
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
}

export const LanguageContext = createContext<LanguageContextType | null>(null)
export const ThemeContext = createContext<ThemeContextType | null>(null)

export const useLanguage = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider')
  }
  return context
}

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}

export const API_BASE = '/api'
export const REFRESH_INTERVAL = parseInt(import.meta.env.VITE_REFRESH_INTERVAL || '300000', 10)
export const NOTIFICATION_POLL_INTERVAL = 60 * 1000
export const FIVE_MINUTES_MS = 5 * 60 * 1000
export const ONE_DAY_MS = 24 * 60 * 60 * 1000
export const SIGNALS_FEED_PAGE_SIZE = 20
export const LEADERBOARD_PAGE_SIZE = 20
export const COPY_TRADING_PAGE_SIZE = 20
export const COMMUNITY_FEED_PAGE_SIZE = 20
export const FINANCIAL_NEWS_PAGE_SIZE = 4
export const LEADERBOARD_LINE_COLORS = ['#d66a5f', '#d49e52', '#b8b15f', '#7bb174', '#5aa7a3', '#4e88b7', '#7a78c5', '#a16cb8', '#c66f9f', '#cb7a7a']

export type LeaderboardChartRange = 'all' | '24h'

export function getLeaderboardDays(chartRange: LeaderboardChartRange) {
  return chartRange === '24h' ? 1 : 7
}

function parseRecordedAt(recordedAt: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(recordedAt) ? recordedAt : `${recordedAt}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatIntelTimestamp(timestamp: string | null | undefined, language: Language) {
  if (!timestamp) return tr(language, { en: 'No snapshot yet', ja: 'スナップショットなし', th: 'ยังไม่มีสแนปช็อต', vi: 'Chưa có ảnh chụp' })
  const parsed = parseRecordedAt(timestamp)
  if (!parsed) return tr(language, { en: 'Unknown time', ja: '時刻不明', th: 'เวลาไม่ทราบ', vi: 'Thời gian không rõ' })
  const formatted = parsed.toLocaleString(LOCALE_BY_LANGUAGE[language], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'America/New_York'
  })
  return `${formatted} ET`
}

export function formatIntelNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'N/A'
  }
  return Number(value).toFixed(digits)
}

function formatLeaderboardLabel(date: Date, chartRange: LeaderboardChartRange, language: Language) {
  if (chartRange === '24h') {
    return date.toLocaleTimeString(LOCALE_BY_LANGUAGE[language], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    })
  }

  return date.toLocaleDateString(LOCALE_BY_LANGUAGE[language], {
    month: 'short',
    day: 'numeric'
  })
}

export function buildLeaderboardChartData(profitHistory: any[], chartRange: LeaderboardChartRange, language: Language) {
  const topAgents = profitHistory.slice(0, 10).map((agent: any) => ({
    ...agent,
    history: (agent.history || [])
      .map((entry: any) => {
        const date = parseRecordedAt(entry.recorded_at)
        if (!date) return null
        return { ...entry, date }
      })
      .filter((entry: any) => entry !== null)
      .sort((a: any, b: any) => a.date.getTime() - b.date.getTime())
  })).filter((agent: any) => agent.history.length > 0)

  if (topAgents.length === 0) {
    return []
  }

  const allTimestamps = topAgents.flatMap((agent: any) => agent.history.map((entry: any) => entry.date.getTime()))
  const earliestTimestamp = Math.min(...allTimestamps)
  const now = new Date()
  const bucketEnds: number[] = []

  if (chartRange === '24h') {
    const endTimestamp = Math.floor(now.getTime() / FIVE_MINUTES_MS) * FIVE_MINUTES_MS
    const startTimestamp = endTimestamp - ONE_DAY_MS
    for (let timestamp = startTimestamp; timestamp <= endTimestamp; timestamp += FIVE_MINUTES_MS) {
      bucketEnds.push(timestamp)
    }
  } else {
    const startDay = new Date(earliestTimestamp)
    startDay.setHours(0, 0, 0, 0)

    const endDay = new Date(now)
    endDay.setHours(0, 0, 0, 0)

    for (let timestamp = startDay.getTime(); timestamp <= endDay.getTime(); timestamp += ONE_DAY_MS) {
      bucketEnds.push(timestamp + ONE_DAY_MS - 1)
    }
  }

  return bucketEnds.map((bucketEndTimestamp) => {
    const bucketEndDate = new Date(bucketEndTimestamp)
    const point: Record<string, any> = {
      time: formatLeaderboardLabel(bucketEndDate, chartRange, language)
    }

    topAgents.forEach((agent: any) => {
      let latestReturn: number | null = null
      for (const entry of agent.history) {
        if (entry.date.getTime() <= bucketEndTimestamp) {
          latestReturn = typeof entry.profit_percent === 'number'
            ? entry.profit_percent
            : entry.profit
        } else {
          break
        }
      }

      if (latestReturn !== null) {
        point[agent.name] = latestReturn
      }
    })

    return point
  }).filter((point) => Object.keys(point).length > 1)
}

function getPolymarketDisplayTitle(item: any) {
  return item?.display_title || item?.market_title || (item?.outcome && item?.symbol ? `${item.symbol} [${item.outcome}]` : item?.symbol || '')
}

export function getInstrumentLabel(item: any) {
  if (item?.market === 'polymarket') {
    return getPolymarketDisplayTitle(item)
  }
  return item?.title || item?.symbol || ''
}

export function LeaderboardTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: any[]
  label?: string
}) {
  if (!active || !payload || payload.length === 0) {
    return null
  }

  const sortedPayload = [...payload]
    .filter((entry) => typeof entry?.value === 'number')
    .sort((a, b) => Number(b.value) - Number(a.value))

  return (
    <div style={{
      minWidth: '220px',
      padding: '12px 14px',
      borderRadius: '12px',
      background: 'var(--bg-secondary)',
      border: '1px solid var(--bg-tertiary)',
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div style={{
        marginBottom: '10px',
        color: 'var(--text-secondary)',
        fontSize: '12px',
        fontFamily: 'IBM Plex Mono, monospace'
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {sortedPayload.map((entry, idx) => (
          <div
            key={`${entry.dataKey}-${idx}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '24px 10px minmax(0, 1fr) auto',
              alignItems: 'center',
              gap: '8px',
              fontSize: '12px'
            }}
          >
            <span style={{ color: 'var(--text-muted)', fontFamily: 'IBM Plex Mono, monospace' }}>#{idx + 1}</span>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '999px',
              background: entry.color || entry.stroke || 'var(--accent-primary)'
            }}></span>
            <span style={{
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: 'var(--text-primary)',
              fontWeight: 600
            }}>
              {entry.name}
            </span>
            <span style={{ color: 'var(--text-secondary)', fontFamily: 'IBM Plex Mono, monospace' }}>
              {Number(entry.value).toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export type MarketIntelNewsCategory = {
  category: string
  label: string
  label_zh: string
  description: string
  description_zh: string
  items: any[]
  summary: any
  created_at: string | null
  available: boolean
}

export type MarketEntry = {
  value: string
  supported: boolean
  labels: Record<Language, string>
}

export const MARKETS: MarketEntry[] = [
  { value: 'all', supported: true, labels: { en: 'All', ja: 'すべて', th: 'ทั้งหมด', vi: 'Tất cả' } },
  { value: 'us-stock', supported: true, labels: { en: 'US Stock', ja: '米国株', th: 'หุ้นสหรัฐ', vi: 'Cổ phiếu Mỹ' } },
  { value: 'crypto', supported: true, labels: { en: 'Crypto (Testing)', ja: '暗号資産（テスト中）', th: 'คริปโต (ทดสอบ)', vi: 'Tiền mã hóa (Thử nghiệm)' } },
  { value: 'a-stock', supported: false, labels: { en: 'A-Share (Developing)', ja: 'A株（開発中）', th: 'A-Share (กำลังพัฒนา)', vi: 'A-Share (Đang phát triển)' } },
  { value: 'polymarket', supported: true, labels: { en: 'Polymarket (Testing)', ja: 'Polymarket（テスト中）', th: 'Polymarket (ทดสอบ)', vi: 'Polymarket (Thử nghiệm)' } },
  { value: 'forex', supported: false, labels: { en: 'Forex (Developing)', ja: '外国為替（開発中）', th: 'Forex (กำลังพัฒนา)', vi: 'Forex (Đang phát triển)' } },
  { value: 'options', supported: false, labels: { en: 'Options (Developing)', ja: 'オプション（開発中）', th: 'ออปชั่น (กำลังพัฒนา)', vi: 'Quyền chọn (Đang phát triển)' } },
  { value: 'futures', supported: false, labels: { en: 'Futures (Developing)', ja: '先物（開発中）', th: 'ฟิวเจอร์ส (กำลังพัฒนา)', vi: 'Hợp đồng tương lai (Đang phát triển)' } },
]

export function marketLabel(value: string, language: Language): string {
  return MARKETS.find((m) => m.value === value)?.labels[language] ?? value
}

export function isUSMarketOpen(): boolean {
  const now = new Date()
  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))

  const day = etNow.getDay()
  const hour = etNow.getHours()
  const minute = etNow.getMinutes()
  const timeInMinutes = hour * 60 + minute

  const isWeekday = day >= 1 && day <= 5
  const isMarketHours = timeInMinutes >= 570 && timeInMinutes < 960

  return isWeekday && isMarketHours
}

export function getCurrentETTime(): string {
  const now = new Date()
  return now.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}
