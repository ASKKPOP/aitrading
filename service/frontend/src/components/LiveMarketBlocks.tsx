import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// ── live market blocks for /market (ticker tape · movers · order book · grid) ──
// Real OKX data refetched every 15s; between fetches a tiny (±0.04%) random
// walk ticks every value once per second so the blocks feel alive without
// polling OKX per-second per visitor (the orderbook endpoint is uncached).
// Reduced-motion users tick every 5s instead; hidden tabs skip ticks.

export type Tick = { price: number; pct: number; vol: number; dir: -1 | 0 | 1 }

const UP = 'var(--success, #0ca30c)'
const DOWN = 'var(--error, #d03b3b)'
const upSoft = 'rgba(var(--success-rgb, 12,163,12), 0.12)'
const downSoft = 'rgba(var(--error-rgb, 208,59,59), 0.12)'
const card: any = { background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 10 }
const mono: any = { fontVariantNumeric: 'tabular-nums' }

const fmtPrice = (p: number) =>
  p >= 10 ? p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : p >= 1 ? p.toFixed(4)
      : Number(p.toPrecision(4)).toString()

const dirColor = (d: -1 | 0 | 1) => (d > 0 ? UP : d < 0 ? DOWN : 'var(--text-primary)')

function PctBadge({ pct }: { pct: number }) {
  return (
    <span style={{ ...mono, fontSize: 11.5, fontWeight: 600, borderRadius: 6, padding: '2px 7px', background: pct >= 0 ? upSoft : downSoft, color: pct >= 0 ? UP : DOWN, whiteSpace: 'nowrap' }}>
      {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
    </span>
  )
}

export function useLiveTickers(): Record<string, Tick> {
  const [ticks, setTicks] = useState<Record<string, Tick>>({})
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch(`${API_BASE}/markets/crypto/tickers`)
        if (!r.ok) return
        const d = await r.json()
        if (!alive) return
        setTicks(prev => {
          const next: Record<string, Tick> = {}
          for (const t of d.tickers ?? []) {
            const price = Number(t.last_price)
            if (!price) continue
            const old = prev[t.symbol]
            next[t.symbol] = { price, pct: Number(t.price_24h_pct) || 0, vol: Number(t.volume_24h) || 0, dir: old ? (Math.sign(price - old.price) as Tick['dir']) : 0 }
          }
          return next
        })
      } catch { /* transient */ }
    }
    load()
    const refetch = window.setInterval(load, 15000)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const jitter = window.setInterval(() => {
      if (document.hidden) return
      setTicks(prev => {
        const next: Record<string, Tick> = {}
        for (const [sym, t] of Object.entries(prev)) {
          const step = t.price * (Math.random() - 0.5) * 0.0008
          next[sym] = { ...t, price: t.price + step, pct: t.pct + (step / t.price) * 100, dir: step > 0 ? 1 : step < 0 ? -1 : 0 }
        }
        return next
      })
    }, reduced ? 5000 : 1000)
    return () => { alive = false; clearInterval(refetch); clearInterval(jitter) }
  }, [])
  return ticks
}

// Thin auto-scrolling strip of every pair. Reduced motion gets a static,
// horizontally scrollable row instead of the marquee.
export function TickerTape({ ticks }: { ticks: Record<string, Tick> }) {
  const entries = Object.entries(ticks)
  if (entries.length === 0) return null
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const cell = ([sym, t]: [string, Tick], i: number) => (
    <span key={`${sym}${i}`} style={{ display: 'inline-flex', alignItems: 'baseline', gap: 7, padding: '0 18px', borderRight: '1px solid var(--border-color)' }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>{sym.replace(/USDT$/, '')}</span>
      <span style={{ ...mono, fontSize: 12.5, fontWeight: 600, color: dirColor(t.dir) }}>{fmtPrice(t.price)}</span>
      <span style={{ ...mono, fontSize: 11.5, color: t.pct >= 0 ? UP : DOWN }}>{t.pct >= 0 ? '+' : ''}{t.pct.toFixed(2)}%</span>
    </span>
  )
  return (
    <div style={{ ...card, overflow: 'hidden', marginBottom: 20, padding: '8px 0', whiteSpace: 'nowrap', ...(reduced ? { overflowX: 'auto' } : {}) }}>
      <style>{`@keyframes lmb-tape { from { transform: translateX(0); } to { transform: translateX(-50%); } }`}</style>
      <div style={reduced ? {} : { display: 'inline-block', animation: 'lmb-tape 60s linear infinite' }}>
        {entries.map(cell)}
        {!reduced && entries.map((e, i) => cell(e, i + entries.length))}
      </div>
    </div>
  )
}

// Three derived KPI cards: best gainer, worst loser, combined 24h volume.
export function MarketMovers({ ticks }: { ticks: Record<string, Tick> }) {
  const { language } = useLanguage()
  const entries = Object.entries(ticks)
  if (entries.length === 0) return null
  const byPct = [...entries].sort((a, b) => b[1].pct - a[1].pct)
  const gainer = byPct[0]
  const loser = byPct[byPct.length - 1]
  const volume = entries.reduce((s, [, t]) => s + t.vol, 0)
  const fmtVol = (n: number) => n >= 1e9 ? `$${(n / 1e9).toFixed(2)}B` : `$${(n / 1e6).toFixed(1)}M`
  const cells = [
    { lb: tr(language, { ko: '24시간 최고 상승', en: 'Top gainer 24h', ja: '24時間最高上昇', th: 'ขึ้นสูงสุด 24 ชม.', vi: 'Tăng mạnh nhất 24h', id: 'Kenaikan teratas 24 jam' }), sym: gainer[0].replace(/USDT$/, ''), val: <PctBadge pct={gainer[1].pct} />, price: fmtPrice(gainer[1].price) },
    { lb: tr(language, { ko: '24시간 최고 하락', en: 'Top loser 24h', ja: '24時間最大下落', th: 'ลงหนักสุด 24 ชม.', vi: 'Giảm mạnh nhất 24h', id: 'Penurunan terdalam 24 jam' }), sym: loser[0].replace(/USDT$/, ''), val: <PctBadge pct={loser[1].pct} />, price: fmtPrice(loser[1].price) },
    { lb: tr(language, { ko: '24시간 합산 거래량', en: 'Combined volume 24h', ja: '24時間合算出来高', th: 'ปริมาณรวม 24 ชม.', vi: 'Tổng khối lượng 24h', id: 'Volume gabungan 24 jam' }), sym: `${entries.length} ${tr(language, { ko: '종목', en: 'pairs', ja: '銘柄', th: 'คู่', vi: 'cặp', id: 'pasangan' })}`, val: null, price: fmtVol(volume) },
  ]
  return (
    <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginBottom: 20 }}>
      {cells.map((c, i) => (
        <div key={i} style={{ ...card, padding: '12px 16px' }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', fontWeight: 600 }}>{c.lb}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
            <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>{c.sym}</span>
            {c.val}
          </div>
          <div style={{ ...mono, fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{c.price}</div>
        </div>
      ))}
    </div>
  )
}

// BTC/USDT depth-4 order book. Server levels are stored as offsets from the
// fetched mid and re-anchored to the ticking live price each render, so the
// whole ladder moves with the price while spread/ordering stay exact.
export function OrderBookBlock({ tick }: { tick?: Tick }) {
  const { language } = useLanguage()
  const navigate = useNavigate()
  type Row = { off: number; qty: number; dir: -1 | 0 | 1 }
  const [book, setBook] = useState<{ mid: number; asks: Row[]; bids: Row[] } | null>(null)
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch(`${API_BASE}/markets/crypto/orderbook?symbol=BTCUSDT&depth=4`)
        if (!r.ok) return
        const d = await r.json()
        if (!alive || !d.asks?.length || !d.bids?.length) return
        const mid = (d.asks[0][0] + d.bids[0][0]) / 2
        // OKX SWAP book sizes are contracts; BTC-USDT-SWAP ctVal is 0.01 BTC.
        const CT_VAL = 0.01
        const rows = (lv: [number, number][]): Row[] => lv.map(([p, q]) => ({ off: p - mid, qty: q * CT_VAL, dir: 0 as const }))
        setBook({ mid, asks: rows(d.asks), bids: rows(d.bids) })
      } catch { /* transient */ }
    }
    load()
    const refetch = window.setInterval(load, 15000)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const jitter = window.setInterval(() => {
      if (document.hidden) return
      setBook(prev => {
        if (!prev) return prev
        const wobble = (r: Row): Row => {
          if (Math.random() < 0.35) return { ...r, dir: 0 }         // some rows rest each tick
          const qty = Math.max(0.001, r.qty * (1 + (Math.random() - 0.5) * 0.3))
          return { off: r.off, qty, dir: qty > r.qty ? 1 : -1 }
        }
        return { mid: prev.mid, asks: prev.asks.map(wobble), bids: prev.bids.map(wobble) }
      })
    }, reduced ? 5000 : 1000)
    return () => { alive = false; clearInterval(refetch); clearInterval(jitter) }
  }, [])

  const T = {
    price: tr(language, { ko: '가격', en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá', id: 'Harga' }),
    qty: tr(language, { ko: '수량', en: 'Amount', ja: '数量', th: 'จำนวน', vi: 'Số lượng', id: 'Jumlah' }),
    total: tr(language, { ko: '합계', en: 'Total', ja: '合計', th: 'รวม', vi: 'Tổng', id: 'Total' }),
    spread: tr(language, { ko: '스프레드', en: 'Spread', ja: 'スプレッド', th: 'สเปรด', vi: 'Chênh lệch', id: 'Selisih' }),
    buy: tr(language, { ko: '매수', en: 'Buy', ja: '買い', th: 'ซื้อ', vi: 'Mua', id: 'Beli' }),
    sell: tr(language, { ko: '매도', en: 'Sell', ja: '売り', th: 'ขาย', vi: 'Bán', id: 'Jual' }),
    collecting: tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'đang thu thập…', id: 'mengumpulkan…' }),
  }
  const anchor = tick?.price ?? book?.mid
  const rowS: any = { display: 'grid', gridTemplateColumns: '1fr 1fr 1.2fr', gap: 8, padding: '5px 16px', fontSize: 13, ...mono }
  const level = (r: Row, side: 'ask' | 'bid', key: number) => {
    const price = (anchor as number) + r.off
    return (
      <div key={`${side}${key}`} style={rowS}>
        <span style={{ color: side === 'ask' ? DOWN : UP }}>{price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span style={{ textAlign: 'center', color: dirColor(r.dir) }}>{r.qty.toFixed(4)}</span>
        <span style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>{(price * r.qty).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      </div>
    )
  }
  const spread = book ? book.asks[0].off - book.bids[0].off : null

  return (
    <div style={{ ...card, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px', borderBottom: '1px solid var(--border-color)' }}>
        <span style={{ fontWeight: 700, fontSize: 15.5, color: 'var(--text-primary)' }}>BTC / USDT</span>
        {tick && <PctBadge pct={tick.pct} />}
        <span style={{ marginLeft: 'auto', ...mono, fontSize: 18, fontWeight: 700, color: dirColor(tick?.dir ?? 0) }}>
          {anchor != null ? `$${anchor.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
        </span>
      </div>
      {book && anchor != null ? (
        <div style={{ padding: '8px 0' }}>
          <div style={{ ...rowS, fontVariantNumeric: 'normal', fontSize: 11, color: 'var(--text-muted)', paddingBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            <span>{T.price} (USDT)</span>
            <span style={{ textAlign: 'center' }}>{T.qty} (BTC)</span>
            <span style={{ textAlign: 'right' }}>{T.total}</span>
          </div>
          {[...book.asks].reverse().map((r, i) => level(r, 'ask', i))}
          <div style={{ margin: '5px 0', padding: '5px 16px', borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)', textAlign: 'center', ...mono, fontSize: 12, color: 'var(--text-secondary)' }}>
            {T.spread} {spread!.toFixed(2)} · {((spread! / anchor) * 100).toFixed(2)}%
          </div>
          {book.bids.map((r, i) => level(r, 'bid', i))}
        </div>
      ) : (
        <div style={{ padding: 16, fontSize: 13, color: 'var(--text-secondary)' }}>{T.collecting}</div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px 16px 14px' }}>
        {([['buy', UP], ['sell', DOWN]] as const).map(([side, color]) => (
          <button key={side} onClick={() => navigate('/trade?symbol=BTCUSDT')}
            style={{ flex: 1, border: 'none', cursor: 'pointer', fontWeight: 700, fontSize: 14, borderRadius: 8, padding: '10px 0', background: color, color: '#fff' }}>
            {side === 'buy' ? T.buy : T.sell}
          </button>
        ))}
      </div>
    </div>
  )
}

export function PopularCryptoGrid({ ticks }: { ticks: Record<string, Tick> }) {
  const { language } = useLanguage()
  const navigate = useNavigate()
  const trade = tr(language, { ko: '거래', en: 'Trade', ja: '取引', th: 'เทรด', vi: 'Giao dịch', id: 'Transaksi' })
  const collecting = tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'đang thu thập…', id: 'mengumpulkan…' })
  const entries = Object.entries(ticks)
  if (entries.length === 0) return <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{collecting}</p>
  return (
    <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))' }}>
      {entries.map(([sym, t]) => {
        const base = sym.replace(/USDT$/, '')
        return (
          <div key={sym} style={{ ...card, padding: '12px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span aria-hidden style={{ width: 32, height: 32, flexShrink: 0, borderRadius: '50%', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13, color: 'var(--text-secondary)' }}>{base[0]}</span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'block', fontWeight: 700, fontSize: 13.5, color: 'var(--text-primary)' }}>{base}/USDT</span>
                <span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-muted)' }}>{base}</span>
              </span>
              <span style={{ marginLeft: 'auto', textAlign: 'right' }}>
                <span style={{ display: 'block', ...mono, fontSize: 14, fontWeight: 700, color: dirColor(t.dir) }}>{fmtPrice(t.price)}</span>
                <span style={{ display: 'inline-block', marginTop: 2 }}><PctBadge pct={t.pct} /></span>
              </span>
            </div>
            <button onClick={() => navigate(`/trade?symbol=${sym}`)}
              style={{ display: 'block', width: '100%', marginTop: 10, textAlign: 'center', cursor: 'pointer', fontWeight: 600, fontSize: 13, borderRadius: 7, padding: '8px 0', border: '1px solid var(--accent-primary)', background: 'transparent', color: 'var(--accent-primary)' }}>
              {trade}
            </button>
          </div>
        )
      })}
    </div>
  )
}
