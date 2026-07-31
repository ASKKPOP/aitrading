import { useEffect, useRef, useState } from 'react'
import { tr, type Language } from '../i18n'

// TradingView Advanced Chart embed — ga's TerminalLayout chart (TradingViewChart.tsx
// + ChartToolbar), adapted to Sooppiy: OKX symbols (our market data source), theme
// from data-theme (MutationObserver — rAF/media listeners die in hidden tabs), and
// the toolbar rendered with inline styles instead of tailwind.
// The embed pulls its own OKX candles; no backend endpoint is involved.

const EMBED_SRC = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'

type ChartStyle = 'candle' | 'line' | 'area'
const STYLE_CODE: Record<ChartStyle, string> = { candle: '1', line: '2', area: '3' }
const INTERVALS: { value: string; label: string }[] = [
  { value: '1', label: '1m' },
  { value: '30', label: '30m' },
  { value: 'D', label: '1D' },
]
const STUDIES = [
  'STD;Bollinger_Bands',
  'STD;MA%1Cross',
  'STD;24h%Volume',
]

function resolveDark(): boolean {
  const theme = document.documentElement.dataset.theme
  if (theme === 'light') return false
  if (theme === 'claude') return true
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function TradingViewChart({ symbol, perp, language }: {
  symbol: string          // bare base asset, e.g. BTC
  perp: boolean           // futures terminal → OKX perpetual (.P)
  language: Language
}) {
  const holder = useRef<HTMLDivElement>(null)
  const [interval, setInterval] = useState('30')
  const [chartStyle, setChartStyle] = useState<ChartStyle>('candle')
  const [showIndicators, setShowIndicators] = useState(false)
  const [dark, setDark] = useState(resolveDark)

  // Theme flips re-render the embed. data-theme is stamped by the theme picker;
  // watch it with a MutationObserver (reliable even in hidden tabs).
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(resolveDark()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    const el = holder.current
    if (!el) return
    el.innerHTML = ''
    const container = document.createElement('div')
    container.style.height = '100%'
    container.style.width = '100%'
    el.appendChild(container)
    const script = document.createElement('script')
    script.src = EMBED_SRC
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: `OKX:${symbol.toUpperCase()}USDT${perp ? '.P' : ''}`,
      interval,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Etc/UTC',
      theme: dark ? 'dark' : 'light',
      style: STYLE_CODE[chartStyle],
      withdateranges: false,
      // Owner 2026-07-31: no drawing toolbar on the terminals — the left
      // TradingView side bar is noise next to the order panels.
      hide_side_toolbar: true,
      hide_top_toolbar: true,   // our toolbar above replaces it
      hide_legend: window.innerWidth < 1024,
      allow_symbol_change: false,
      studies: showIndicators ? STUDIES : [],
      locale: 'en',
    })
    container.appendChild(script)
    return () => { el.innerHTML = '' }
  }, [symbol, perp, interval, chartStyle, showIndicators, dark])

  const T = {
    indicators: tr(language, { ko: '지표', en: 'Indicators', ja: '指標', th: 'อินดิเคเตอร์', vi: 'Chỉ báo', id: 'Indikator' }),
    candle: tr(language, { ko: '캔들', en: 'Candles', ja: 'ローソク足', th: 'แท่งเทียน', vi: 'Nến', id: 'Candlestick' }),
    line: tr(language, { ko: '라인', en: 'Line', ja: 'ライン', th: 'เส้น', vi: 'Đường', id: 'Garis' }),
    area: tr(language, { ko: '영역', en: 'Area', ja: 'エリア', th: 'พื้นที่', vi: 'Vùng', id: 'Area' }),
  }

  const tab = (active: boolean): any => ({
    padding: '5px 10px', borderRadius: 7, fontSize: 11.5, cursor: 'pointer',
    border: '1px solid var(--border-color,#d3c8b6)',
    background: active ? 'var(--accent-primary,#c26a45)' : 'transparent',
    color: active ? 'var(--accent-contrast,#fff)' : 'var(--text-secondary,#8a8073)',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '8px 10px', borderBottom: '1px solid var(--border-color,#e6ddd0)', flexWrap: 'wrap' }}>
        {INTERVALS.map(iv => (
          <button key={iv.value} onClick={() => setInterval(iv.value)} style={tab(interval === iv.value)}>{iv.label}</button>
        ))}
        <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border-color,#e6ddd0)', margin: '0 4px' }} />
        {(['candle', 'line', 'area'] as ChartStyle[]).map(s => (
          <button key={s} onClick={() => setChartStyle(s)} style={tab(chartStyle === s)}>{T[s]}</button>
        ))}
        <span style={{ flex: 1 }} />
        <button onClick={() => setShowIndicators(v => !v)} style={tab(showIndicators)}>{T.indicators}</button>
      </div>
      <div ref={holder} style={{ flex: 1, minHeight: 0 }} />
    </div>
  )
}

export default TradingViewChart
