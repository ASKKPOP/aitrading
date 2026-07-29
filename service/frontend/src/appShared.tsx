import { createContext, useContext } from 'react'

import { Language, getT, LOCALE_BY_LANGUAGE, tr } from './i18n'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: ReturnType<typeof getT>
}

export type ThemeMode = 'signal' | 'claude' | 'light'

export const THEMES: { value: ThemeMode; label: string; dotColor: string }[] = [
  { value: 'signal', label: 'Signal', dotColor: '#2a78d6' },
  { value: 'claude', label: 'Claude', dotColor: '#d97757' },
  { value: 'light',  label: 'Light',  dotColor: '#f5f4ee' },
]

export const DEFAULT_THEME: ThemeMode = 'signal'

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
// Points -> cash conversion. Must match EXCHANGE_RATE in service/server/routes_users.py.
export const POINTS_EXCHANGE_RATE = 1000
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
  if (!timestamp) return tr(language, { ko: '아직 스냅샷이 없습니다', en: 'No snapshot yet', ja: 'スナップショットなし', th: 'ยังไม่มีสแนปช็อต', vi: 'Chưa có ảnh chụp', id: 'Belum ada snapshot' })
  const parsed = parseRecordedAt(timestamp)
  if (!parsed) return tr(language, { ko: '알 수 없는 시각', en: 'Unknown time', ja: '時刻不明', th: 'เวลาไม่ทราบ', vi: 'Thời gian không rõ', id: 'Waktu tidak diketahui' })
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

/** A stored UTC timestamp rendered in the viewer's OWN timezone (no forced ET,
 *  unlike formatIntelTimestamp which is for market-data snapshots). Used by the
 *  broker order / drift lists so a KST user sees KST, not raw UTC. */
export function formatLocalDateTime(timestamp: string | null | undefined, language: Language) {
  if (!timestamp) return ''
  const parsed = parseRecordedAt(timestamp)
  if (!parsed) return String(timestamp)
  return parsed.toLocaleString(LOCALE_BY_LANGUAGE[language], {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
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
  { value: 'all', supported: true, labels: { ko: '전체', en: 'All', ja: 'すべて', th: 'ทั้งหมด', vi: 'Tất cả', id: 'Semua' } },
  { value: 'us-stock', supported: true, labels: { ko: '미국주식', en: 'US Stock', ja: '米国株', th: 'หุ้นสหรัฐ', vi: 'Cổ phiếu Mỹ', id: 'Saham AS' } },
  { value: 'crypto', supported: true, labels: { ko: '암호화폐 (테스트)', en: 'Crypto (Testing)', ja: '暗号資産（テスト中）', th: 'คริปโต (ทดสอบ)', vi: 'Tiền mã hóa (Thử nghiệm)', id: 'Kripto (Uji coba)' } },
  { value: 'a-stock', supported: true, labels: { ko: 'A주 (테스트)', en: 'A-Share (Testing)', ja: 'A株（テスト中）', th: 'A-Share (ทดสอบ)', vi: 'A-Share (Thử nghiệm)', id: 'A-Share (Uji coba)' } },
  { value: 'polymarket', supported: true, labels: { ko: 'Polymarket (테스트)', en: 'Polymarket (Testing)', ja: 'Polymarket（テスト中）', th: 'Polymarket (ทดสอบ)', vi: 'Polymarket (Thử nghiệm)', id: 'Polymarket (Uji coba)' } },
  { value: 'forex', supported: true, labels: { ko: '외환 (테스트)', en: 'Forex (Testing)', ja: '外国為替（テスト中）', th: 'Forex (ทดสอบ)', vi: 'Forex (Thử nghiệm)', id: 'Forex (Uji coba)' } },
  { value: 'options', supported: true, labels: { ko: '옵션 (테스트)', en: 'Options (Testing)', ja: 'オプション（テスト中）', th: 'ออปชั่น (ทดสอบ)', vi: 'Quyền chọn (Thử nghiệm)', id: 'Opsi (Uji coba)' } },
  { value: 'futures', supported: true, labels: { ko: '선물 (테스트)', en: 'Futures (Testing)', ja: '先物（テスト中）', th: 'ฟิวเจอร์ส (ทดสอบ)', vi: 'Hợp đồng tương lai (Thử nghiệm)', id: 'Futures (Uji coba)' } },
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
