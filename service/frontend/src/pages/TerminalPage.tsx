import { useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { POPULAR_PAIRS, TRADE_FEE_RATE, fmtQty, fmtUsd, pair, placeOrder, pnlColor } from './tradeShared'

// Spot / Futures trade terminal — modeled on ga's shared TerminalLayout
// (PairStatsHeader + OrderBookPanel + OrderFormPanel + BottomTabs), adapted to
// Sooppiy's paper engine: market orders fill instantly at the live price.
// mode='spot'    → buy/sell longs only (1x, like ga spot)
// mode='futures' → long/short with leverage sizing + approximate liq preview

const MAINTENANCE_MARGIN_RATE = 0.005
const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }
const UP = '#3fb950', DOWN = '#f0663f'

type Ticker = { symbol: string; last_price: number; mark_price: number; price_24h_pct: number; volume_24h: number }
type Book = { bids: number[][]; asks: number[][] }

export function TerminalPage({ mode }: { mode: 'spot' | 'futures' }) {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const isSpot = mode === 'spot'

  const [symbol, setSymbol] = useState('BTC')
  const [ticker, setTicker] = useState<Ticker | null>(null)
  const [book, setBook] = useState<Book | null>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [cash, setCash] = useState(0)
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)
  const lastPriceRef = useRef<number | null>(null)

  // order form state
  const [side, setSide] = useState<'buy' | 'sell'>('buy')       // spot
  const [qty, setQty] = useState('')
  const [orderValue, setOrderValue] = useState('')
  const [pct, setPct] = useState(0)
  const [leverage, setLeverage] = useState(10)                   // futures
  const [confirm, setConfirm] = useState<null | { action: 'buy' | 'sell' | 'short' | 'cover'; label: string }>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const T = {
    spotTitle: tr(language, { en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Spot' }),
    futTitle: tr(language, { en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures' }),
    orderBook: tr(language, { en: 'Order book', ja: '板情報', th: 'สมุดคำสั่ง', vi: 'Sổ lệnh' }),
    priceCol: tr(language, { en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá' }),
    qtyCol: tr(language, { en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' }),
    totalCol: tr(language, { en: 'Total', ja: '累計', th: 'รวม', vi: 'Tổng' }),
    market: tr(language, { en: 'Market', ja: '成行', th: 'ราคาตลาด', vi: 'Thị trường' }),
    limitSoon: tr(language, { en: 'Limit (soon)', ja: '指値(準備中)', th: 'ลิมิต (เร็วๆนี้)', vi: 'Limit (sắp có)' }),
    buy: tr(language, { en: 'Buy', ja: '買い', th: 'ซื้อ', vi: 'Mua' }),
    sell: tr(language, { en: 'Sell', ja: '売り', th: 'ขาย', vi: 'Bán' }),
    long: tr(language, { en: 'Buy / Long', ja: '買い/ロング', th: 'ซื้อ / Long', vi: 'Mua / Long' }),
    short: tr(language, { en: 'Sell / Short', ja: '売り/ショート', th: 'ขาย / Short', vi: 'Bán / Short' }),
    available: tr(language, { en: 'Available', ja: '利用可能', th: 'พร้อมใช้', vi: 'Khả dụng' }),
    holding: tr(language, { en: 'Holding', ja: '保有量', th: 'ถือครอง', vi: 'Nắm giữ' }),
    orderValue: tr(language, { en: 'Order value (USDT)', ja: '注文金額 (USDT)', th: 'มูลค่าคำสั่ง (USDT)', vi: 'Giá trị lệnh (USDT)' }),
    quantity: tr(language, { en: 'Quantity', ja: '数量', th: 'จำนวน', vi: 'Số lượng' }),
    fee: tr(language, { en: 'Fee', ja: '手数料', th: 'ค่าธรรมเนียม', vi: 'Phí' }),
    margin: tr(language, { en: 'Margin', ja: '証拠金', th: 'มาร์จิน', vi: 'Ký quỹ' }),
    liqApprox: tr(language, { en: 'Liq. price (approx)', ja: '清算価格(概算)', th: 'ราคาล้างพอร์ต (ประมาณ)', vi: 'Giá thanh lý (xấp xỉ)' }),
    lev: tr(language, { en: 'Leverage', ja: 'レバレッジ', th: 'เลเวอเรจ', vi: 'Đòn bẩy' }),
    confirmTitle: tr(language, { en: 'Confirm order', ja: '注文確認', th: 'ยืนยันคำสั่ง', vi: 'Xác nhận lệnh' }),
    entry: tr(language, { en: 'Entry price (live)', ja: '約定価格(現在)', th: 'ราคาเข้า (สด)', vi: 'Giá vào (trực tiếp)' }),
    totalCost: tr(language, { en: 'Total cost', ja: '合計', th: 'รวมทั้งหมด', vi: 'Tổng chi phí' }),
    cancel: tr(language, { en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy' }),
    confirmBtn: tr(language, { en: 'Confirm', ja: '確定', th: 'ยืนยัน', vi: 'Xác nhận' }),
    holdings: tr(language, { en: 'Holdings', ja: '保有資産', th: 'ถือครอง', vi: 'Nắm giữ' }),
    positionsTab: tr(language, { en: 'Positions', ja: 'ポジション', th: 'สถานะ', vi: 'Vị thế' }),
    close: tr(language, { en: 'Market close', ja: '成行決済', th: 'ปิดที่ตลาด', vi: 'Đóng thị trường' }),
    fillNote: tr(language, { en: 'Market orders fill instantly at the live price (paper trading).', ja: '成行注文は現在価格で即時約定します（模擬取引）。', th: 'คำสั่งตลาดจะเติมทันทีที่ราคาสด (เทรดจำลอง)', vi: 'Lệnh thị trường khớp ngay theo giá thật (mô phỏng).' }),
    levNote: tr(language, { en: 'Leverage sizes the position; PnL is linear and liq is approximate in this simulator.', ja: 'レバレッジはサイズにのみ影響（清算価格は概算）。', th: 'เลเวอเรจกำหนดขนาดสถานะ ราคาล้างพอร์ตเป็นค่าประมาณ', vi: 'Đòn bẩy chỉ định cỡ vị thế; giá thanh lý là xấp xỉ.' }),
    login: tr(language, { en: 'Log in to trade.', ja: 'ログインしてください。', th: 'เข้าสู่ระบบเพื่อเทรด', vi: 'Đăng nhập để giao dịch.' }),
    change: tr(language, { en: '24h change', ja: '24h変動', th: 'เปลี่ยน 24ชม.', vi: '24h' }),
    markPrice: tr(language, { en: 'Mark', ja: 'マーク', th: 'Mark', vi: 'Mark' }),
    volume: tr(language, { en: '24h volume', ja: '24h出来高', th: 'ปริมาณ 24ชม.', vi: 'KL 24h' }),
    empty: tr(language, { en: 'Nothing here yet.', ja: 'まだありません。', th: 'ยังไม่มีข้อมูล', vi: 'Trống.' }),
  }

  /* ── data polling ─────────────────────────────────────────── */
  async function loadTicker() {
    try {
      const res = await fetch(`${API_BASE}/markets/crypto/ticker?symbol=${symbol}USDT`)
      if (!res.ok) return
      const t = await res.json()
      const last = Number(t.last_price)
      if (lastPriceRef.current !== null && last !== lastPriceRef.current) {
        setFlash(last > lastPriceRef.current ? 'up' : 'down')
        setTimeout(() => setFlash(null), 500)
      }
      lastPriceRef.current = last
      setTicker({ ...t, last_price: last, mark_price: Number(t.mark_price), price_24h_pct: Number(t.price_24h_pct), volume_24h: Number(t.volume_24h) })
    } catch { /* transient */ }
  }
  async function loadBook() {
    try {
      const res = await fetch(`${API_BASE}/markets/crypto/orderbook?symbol=${symbol}USDT&depth=12`)
      if (res.ok) setBook(await res.json())
    } catch { /* transient */ }
  }
  async function loadPositions() {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/positions`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await res.json()
      if (res.ok) { setPositions(data.positions || []); setCash(data.cash ?? 0) }
    } catch { /* transient */ }
  }
  useEffect(() => {
    lastPriceRef.current = null
    loadTicker(); loadBook(); loadPositions()
    const t1 = setInterval(loadTicker, 4000)
    const t2 = setInterval(loadBook, 4000)
    const t3 = setInterval(loadPositions, 12000)
    return () => { clearInterval(t1); clearInterval(t2); clearInterval(t3) }
  }, [symbol, token])

  const price = ticker?.last_price ?? null

  /* ── form math (ga: qty ⇄ order value two-way binding, % slider) ──
     Ledger is hedge-mode: long and short are separate rows; aggregate per side. */
  const symPositions = positions.filter(p => p.symbol === symbol && p.market === 'crypto')
  const longQty = symPositions.filter(p => p.side === 'long').reduce((s, p) => s + p.quantity, 0)
  const shortQty = Math.abs(symPositions.filter(p => p.side !== 'long').reduce((s, p) => s + p.quantity, 0))

  function syncFromQty(q: string) {
    setQty(q)
    const n = parseFloat(q)
    setOrderValue(price && n > 0 ? (n * price).toFixed(2) : '')
  }
  function syncFromValue(v: string) {
    setOrderValue(v)
    const n = parseFloat(v)
    setQty(price && n > 0 ? (n / price).toFixed(6) : '')
  }
  function applyPct(p: number) {
    setPct(p)
    if (!price) return
    if (isSpot && side === 'sell') { syncFromQty(((longQty * p) / 100).toFixed(6)); return }
    const budget = cash * (p / 100) / (1 + TRADE_FEE_RATE + 0.001)
    const notional = isSpot ? budget : budget * leverage
    syncFromValue(notional.toFixed(2))
  }

  const qtyN = parseFloat(qty) || 0
  const notional = price ? qtyN * price : 0
  const fee = notional * TRADE_FEE_RATE
  const marginReq = isSpot ? notional : notional / leverage
  const liqLong = price ? price * (1 - (1 / leverage - MAINTENANCE_MARGIN_RATE)) : null
  const liqShort = price ? price * (1 + (1 / leverage - MAINTENANCE_MARGIN_RATE)) : null

  async function submit(action: 'buy' | 'sell' | 'short' | 'cover') {
    if (!token || !price || qtyN <= 0) return
    setBusy(true); setMsg(null)
    const r = await placeOrder(token, { market: 'crypto', action, symbol, price, quantity: qtyN, content: `${mode} terminal` })
    setMsg({ ok: r.ok, text: r.ok ? `✓ ${r.message} #${r.signalId}` : r.message })
    setBusy(false); setConfirm(null)
    if (r.ok) { setQty(''); setOrderValue(''); setPct(0); loadPositions() }
  }

  async function marketClose(p: any) {
    if (!token) return
    const action = p.side === 'long' ? 'sell' : 'cover'
    const live = price && p.symbol === symbol ? price : (p.current_price ?? p.entry_price)
    const r = await placeOrder(token, { market: p.market, action, symbol: p.symbol, price: live, quantity: Math.abs(p.quantity), content: 'market close' })
    setMsg({ ok: r.ok, text: r.ok ? `✓ closed ${p.symbol}` : r.message })
    loadPositions()
  }

  /* ── styles ── */
  const inp: any = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-input,#fff)', color: 'inherit', ...mono }
  const panel: any = { background: 'var(--bg-card,#fffdf9)', border: '1px solid var(--border,#d3c8b6)', borderRadius: 12 }

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{isSpot ? T.spotTitle : T.futTitle}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">{isSpot ? '◈' : '⚡'}</div><div className="empty-title">{T.login}</div></div></div>
  }

  const bookRows = (rows: number[][], color: string, reverse = false) => {
    const max = Math.max(...rows.map(r => r[1]), 1)
    const list = reverse ? [...rows].reverse() : rows
    return list.map((r, i) => (
      <div key={i} onClick={() => syncFromQty(r[1].toFixed(6))}
        style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: 4, padding: '2px 10px', fontSize: 12, cursor: 'pointer', position: 'relative' }}>
        <span style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: `${(r[1] / max) * 100}%`, background: color, opacity: 0.10 }} />
        <span style={{ ...mono, color }}>{fmtUsd(r[0], r[0] > 100 ? 1 : 4)}</span>
        <span style={{ ...mono, textAlign: 'right' }}>{fmtQty(r[1])}</span>
        <span style={{ ...mono, textAlign: 'right', color: 'var(--text-secondary,#8a8073)' }}>{fmtUsd(r[0] * r[1], 0)}</span>
      </div>
    ))
  }
  const bidVol = (book?.bids || []).reduce((s, r) => s + r[1], 0)
  const askVol = (book?.asks || []).reduce((s, r) => s + r[1], 0)
  const buyPct = bidVol + askVol > 0 ? Math.round((bidVol / (bidVol + askVol)) * 100) : 50

  return (
    <div>
      {/* ── PairStatsHeader (ga) ── */}
      <div style={{ ...panel, display: 'flex', alignItems: 'center', gap: 22, padding: '12px 18px', marginBottom: 14, flexWrap: 'wrap' }}>
        <select value={symbol} onChange={e => { setSymbol(e.target.value); setQty(''); setOrderValue('') }}
          style={{ ...inp, width: 'auto', fontWeight: 700, fontSize: 15 }}>
          {POPULAR_PAIRS.map(s => <option key={s} value={s}>{pair(s)}</option>)}
        </select>
        <span style={{ ...mono, fontSize: 24, fontWeight: 800, color: flash === 'up' ? UP : flash === 'down' ? DOWN : (ticker && ticker.price_24h_pct >= 0 ? UP : DOWN), transition: 'color .2s' }}>
          {price ? fmtUsd(price, price > 100 ? 2 : 4) : '—'}
        </span>
        <Stat label={T.change} value={ticker ? `${ticker.price_24h_pct >= 0 ? '+' : ''}${ticker.price_24h_pct.toFixed(2)}%` : '—'} color={ticker ? (ticker.price_24h_pct >= 0 ? UP : DOWN) : undefined} />
        {!isSpot && <Stat label={T.markPrice} value={ticker ? fmtUsd(ticker.mark_price, 2) : '—'} />}
        <Stat label={T.volume} value={ticker ? fmtUsd(ticker.volume_24h, 0) : '—'} />
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-secondary,#8a8073)' }}>{isSpot ? T.spotTitle : `${T.futTitle} · Perpetual (sim)`}</span>
      </div>

      <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        {/* ── OrderBookPanel (ga) ── */}
        <div style={{ ...panel, flex: '1 1 260px', maxWidth: 340, overflow: 'hidden' }}>
          <div style={{ padding: '10px 12px', fontWeight: 700, fontSize: 13, borderBottom: '1px solid var(--border,#e6ddd0)' }}>{T.orderBook}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: 4, padding: '6px 10px', fontSize: 10.5, color: 'var(--text-secondary,#8a8073)', textTransform: 'uppercase' }}>
            <span>{T.priceCol}</span><span style={{ textAlign: 'right' }}>{T.qtyCol}</span><span style={{ textAlign: 'right' }}>{T.totalCol}</span>
          </div>
          {book ? (
            <>
              {bookRows(book.asks.slice(0, 10), DOWN, true)}
              <div style={{ ...mono, padding: '6px 10px', fontSize: 16, fontWeight: 800, borderTop: '1px solid var(--border,#e6ddd0)', borderBottom: '1px solid var(--border,#e6ddd0)', color: flash === 'down' ? DOWN : UP }}>
                {price ? fmtUsd(price, price > 100 ? 2 : 4) : '—'} {flash === 'up' ? '↑' : flash === 'down' ? '↓' : ''}
              </div>
              {bookRows(book.bids.slice(0, 10), UP)}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', fontSize: 11 }}>
                <b style={{ color: UP }}>B {buyPct}%</b>
                <div style={{ flex: 1, height: 4, borderRadius: 2, background: `linear-gradient(to right, ${UP} ${buyPct}%, ${DOWN} ${buyPct}%)` }} />
                <b style={{ color: DOWN }}>{100 - buyPct}% S</b>
              </div>
            </>
          ) : <div style={{ padding: 16, color: 'var(--text-secondary,#8a8073)', fontSize: 13 }}>…</div>}
        </div>

        {/* ── OrderFormPanel (ga) ── */}
        <div style={{ ...panel, flex: '1 1 300px', maxWidth: 380, padding: 14 }}>
          {/* order type tabs */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
            <button style={{ flex: 1, padding: '7px 0', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 12.5 }}>{T.market}</button>
            <button disabled style={{ flex: 1, padding: '7px 0', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'transparent', color: 'var(--text-secondary,#8a8073)', fontSize: 12.5, cursor: 'not-allowed' }}>{T.limitSoon}</button>
          </div>

          {isSpot && (
            <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
              <button onClick={() => { setSide('buy'); setPct(0) }} style={{ flex: 1, padding: '9px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: side === 'buy' ? UP : 'var(--card2,#f3efe7)', color: side === 'buy' ? '#fff' : 'inherit' }}>{T.buy}</button>
              <button onClick={() => { setSide('sell'); setPct(0) }} style={{ flex: 1, padding: '9px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: side === 'sell' ? DOWN : 'var(--card2,#f3efe7)', color: side === 'sell' ? '#fff' : 'inherit' }}>{T.sell}</button>
            </div>
          )}

          {/* info rows */}
          <InfoRow label={T.available} value={`${fmtUsd(cash)} USDT`} />
          <InfoRow label={`${T.holding} (${symbol})`} value={fmtQty(isSpot ? longQty : longQty - shortQty)} />

          {!isSpot && (
            <div style={{ margin: '12px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                <span>{T.lev}</span><b style={mono}>{leverage}×</b>
              </div>
              <input type="range" min={1} max={100} value={leverage} onChange={e => { setLeverage(+e.target.value); if (pct) applyPct(pct) }} style={{ width: '100%' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-secondary,#8a8073)' }}>
                <span>1×</span><span>25×</span><span>50×</span><span>75×</span><span>100×</span>
              </div>
            </div>
          )}

          <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.quantity} ({symbol})</label>
          <input style={inp} value={qty} onChange={e => syncFromQty(e.target.value)} placeholder="0.00" />
          <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.orderValue}</label>
          <input style={inp} value={orderValue} onChange={e => syncFromValue(e.target.value)} placeholder="0.00" />

          {/* % allocation (ga slider → buttons) */}
          <div style={{ display: 'flex', gap: 6, margin: '10px 0' }}>
            {[25, 50, 75, 100].map(p => (
              <button key={p} onClick={() => applyPct(p)} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--border,#d3c8b6)', background: pct === p ? 'var(--accent-primary,#c26a45)' : 'transparent', color: pct === p ? '#fff' : 'var(--text-secondary,#8a8073)', fontSize: 11.5, cursor: 'pointer' }}>{p}%</button>
            ))}
          </div>

          <InfoRow label={T.fee} value={`≈ ${fmtUsd(fee)} USDT`} />
          {!isSpot && <InfoRow label={T.margin} value={`≈ ${fmtUsd(marginReq)} USDT`} />}
          {!isSpot && qtyN > 0 && (
            <div style={{ background: 'rgba(201,162,39,0.10)', border: '1px solid rgba(201,162,39,0.45)', borderRadius: 8, padding: '8px 10px', fontSize: 12, margin: '8px 0', ...mono }}>
              {T.liqApprox}: <b style={{ color: UP }}>L {liqLong ? fmtUsd(liqLong, 1) : '—'}</b> · <b style={{ color: DOWN }}>S {liqShort ? fmtUsd(liqShort, 1) : '—'}</b>
            </div>
          )}

          {/* action buttons */}
          {isSpot ? (
            <button disabled={busy || qtyN <= 0 || !price}
              onClick={() => setConfirm({ action: side, label: side === 'buy' ? T.buy : T.sell })}
              style={{ width: '100%', marginTop: 10, padding: '11px 0', borderRadius: 9, border: 'none', fontWeight: 700, fontSize: 14, cursor: 'pointer', background: side === 'buy' ? UP : DOWN, color: '#fff', opacity: (busy || qtyN <= 0) ? 0.55 : 1 }}>
              {side === 'buy' ? T.buy : T.sell} {pair(symbol)}
            </button>
          ) : (
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button disabled={busy || qtyN <= 0 || !price} onClick={() => setConfirm({ action: 'buy', label: T.long })}
                style={{ flex: 1, padding: '11px 0', borderRadius: 9, border: 'none', fontWeight: 700, cursor: 'pointer', background: UP, color: '#fff', opacity: (busy || qtyN <= 0) ? 0.55 : 1 }}>{T.long}</button>
              <button disabled={busy || qtyN <= 0 || !price} onClick={() => setConfirm({ action: 'short', label: T.short })}
                style={{ flex: 1, padding: '11px 0', borderRadius: 9, border: 'none', fontWeight: 700, cursor: 'pointer', background: DOWN, color: '#fff', opacity: (busy || qtyN <= 0) ? 0.55 : 1 }}>{T.short}</button>
            </div>
          )}

          {msg && <div style={{ marginTop: 10, fontSize: 12.5, color: msg.ok ? UP : DOWN }}>{msg.text}</div>}
          <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.5 }}>
            {T.fillNote}{!isSpot && ` ${T.levNote}`}
          </div>
        </div>
      </div>

      {/* ── BottomTabs (ga): Holdings / Positions ── */}
      <div style={{ ...panel, marginTop: 14, overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', fontWeight: 700, fontSize: 13, borderBottom: '1px solid var(--border,#e6ddd0)' }}>
          {isSpot ? T.holdings : T.positionsTab}
        </div>
        {(() => {
          const rows = positions.filter(p => isSpot ? p.side === 'long' : true)
          if (rows.length === 0) return <div style={{ padding: 16, color: 'var(--text-secondary,#8a8073)', fontSize: 13 }}>{T.empty}</div>
          return (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 11, textTransform: 'uppercase' }}>
                    <th style={{ textAlign: 'left', padding: '8px 14px' }}>Asset</th>
                    {!isSpot && <th style={{ textAlign: 'left', padding: '8px 8px' }}>Side</th>}
                    <th style={{ textAlign: 'right', padding: '8px 8px' }}>{T.qtyCol}</th>
                    <th style={{ textAlign: 'right', padding: '8px 8px' }}>Entry</th>
                    <th style={{ textAlign: 'right', padding: '8px 8px' }}>{isSpot ? 'Current' : 'Mark'}</th>
                    <th style={{ textAlign: 'right', padding: '8px 8px' }}>Value</th>
                    <th style={{ textAlign: 'right', padding: '8px 8px' }}>PnL / ROI</th>
                    <th style={{ textAlign: 'right', padding: '8px 14px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p, i) => {
                    const cur = p.current_price ?? p.entry_price
                    const value = Math.abs(p.quantity) * (cur ?? 0)
                    const roi = p.entry_price ? ((p.pnl ?? 0) / (Math.abs(p.quantity) * p.entry_price)) * 100 : 0
                    return (
                      <tr key={i} style={{ borderTop: '1px solid var(--border,#e6ddd0)' }}>
                        <td style={{ padding: '8px 14px', fontWeight: 700 }}>{pair(p.symbol)}</td>
                        {!isSpot && <td style={{ padding: '8px 8px', color: p.side === 'long' ? UP : DOWN, fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>{p.side}</td>}
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtQty(Math.abs(p.quantity))}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(p.entry_price)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(cur)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(value)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px', color: pnlColor(p.pnl) }}>
                          {(p.pnl ?? 0) >= 0 ? '+' : ''}{fmtUsd(p.pnl ?? 0)} / {roi.toFixed(2)}%
                        </td>
                        <td style={{ textAlign: 'right', padding: '8px 14px' }}>
                          <button onClick={() => marketClose(p)} style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid var(--border,#d3c8b6)', background: 'transparent', color: 'inherit', fontSize: 11.5, cursor: 'pointer' }}>{T.close}</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        })()}
      </div>

      {/* ── OrderConfirmModal (ga) ── */}
      {confirm && price && (
        <div onClick={() => setConfirm(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ ...panel, width: 360, padding: 20 }}>
            <div style={{ fontWeight: 800, marginBottom: 12 }}>{T.confirmTitle}</div>
            <InfoRow label="Order" value={`${T.market} · ${confirm.label} · ${pair(symbol)}`} strong />
            <InfoRow label={T.entry} value={fmtUsd(price)} />
            <InfoRow label={T.qtyCol} value={`${fmtQty(qtyN)} ${symbol} ≈ ${fmtUsd(notional)} USDT`} />
            {!isSpot && <InfoRow label={`${T.margin} (${leverage}×)`} value={`${fmtUsd(marginReq)} USDT`} />}
            <InfoRow label={T.fee} value={`${fmtUsd(fee)} USDT`} />
            <InfoRow label={T.totalCost} value={`${fmtUsd((confirm.action === 'buy' || confirm.action === 'short' ? notional : 0) + fee)} USDT`} strong />
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button onClick={() => setConfirm(null)} style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>{T.cancel}</button>
              <button disabled={busy} onClick={() => submit(confirm.action)}
                style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: (confirm.action === 'buy') ? UP : DOWN, color: '#fff' }}>{T.confirmBtn}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 1 }}>
      <span style={{ fontSize: 10.5, color: 'var(--text-secondary,#8a8073)', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ ...mono, fontSize: 13, fontWeight: 600, color: color || 'inherit' }}>{value}</span>
    </span>
  )
}

function InfoRow({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, padding: '3px 0' }}>
      <span style={{ color: 'var(--text-secondary,#8a8073)' }}>{label}</span>
      <span style={{ ...mono, fontWeight: strong ? 700 : 500 }}>{value}</span>
    </div>
  )
}

export function SpotPage() { return <TerminalPage mode="spot" /> }
export function FuturesPage() { return <TerminalPage mode="futures" /> }
export default TerminalPage
