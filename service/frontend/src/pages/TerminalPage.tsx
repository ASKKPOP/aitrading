import { useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { TradingViewChart } from '../components/TradingViewChart'
import { POPULAR_PAIRS, TRADE_FEE_RATE, fetchFeeRate, fmtQty, fmtUsd, pair, placeOrder, pnlColor } from './tradeShared'

// Spot / Futures trade terminal — modeled on ga's TerminalLayout
// (PairStatsHeader + chart + OrderBookPanel + RecentTradesPanel +
// OrderFormPanel + BottomTabs), adapted to Sooppiy's paper engine:
// market orders fill instantly at the live price; TP/SL is registered on the
// position and enforced by the server-side risk watcher.
// mode='spot'    → buy/sell longs only (1x, like ga spot)
// mode='futures' → long/short with leverage sizing + approximate liq preview

const MAINTENANCE_MARGIN_RATE = 0.005
const SLIPPAGE_BUFFER = 0.001 // ga ALLOC_RESERVE tail
const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }
const UP = 'var(--success,#3fb950)', DOWN = 'var(--error,#f0663f)'

type Ticker = { symbol: string; last_price: number; mark_price: number; price_24h_pct: number; volume_24h: number }
type Book = { bids: number[][]; asks: number[][] }
type Trade = { ts: number; price: number; size: number; side: 'buy' | 'sell' }
type Funding = { funding_rate: number; next_funding_time: number | null }

const CONFIRM_SKIP_KEY = 'sooppiy:orderConfirm:hidden'

function hhmmss(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-GB', { hour12: false })
}

export function TerminalPage({ mode }: { mode: 'spot' | 'futures' }) {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const isSpot = mode === 'spot'

  const [symbol, setSymbol] = useState('BTC')
  const [ticker, setTicker] = useState<Ticker | null>(null)
  const [book, setBook] = useState<Book | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [funding, setFunding] = useState<Funding | null>(null)
  const [countdown, setCountdown] = useState('')
  const [positions, setPositions] = useState<any[]>([])
  const [cash, setCash] = useState(0)
  const [feeRate, setFeeRate] = useState(TRADE_FEE_RATE)
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)
  const lastPriceRef = useRef<number | null>(null)

  // order form state
  const [side, setSide] = useState<'buy' | 'sell'>('buy')       // spot
  const [qty, setQty] = useState('')
  const [orderValue, setOrderValue] = useState('')
  const [pct, setPct] = useState(0)
  const [leverage, setLeverage] = useState(10)                   // futures
  const [tpInput, setTpInput] = useState('')                     // futures
  const [slInput, setSlInput] = useState('')                     // futures
  const [confirm, setConfirm] = useState<null | { action: 'buy' | 'sell' | 'short' | 'cover'; label: string }>(null)
  const [skipConfirm, setSkipConfirm] = useState(() => localStorage.getItem(CONFIRM_SKIP_KEY) === '1')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  // bottom tabs / modals
  const [tab, setTab] = useState<'positions' | 'history'>('positions')
  const [history, setHistory] = useState<any[]>([])
  const [closeTarget, setCloseTarget] = useState<null | { pos: any; qtyStr: string; pct: number }>(null)
  // Closing places a REAL order — lock while in flight (double-click
  // double-closed) and report the result AT the positions table (origin/main
  // fix, preserved through the ga-parity rewrite).
  const [closing, setClosing] = useState(false)
  const [closeMsg, setCloseMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [tpslEdit, setTpslEdit] = useState<null | { pos: any; sl: string; tp: string; err: string | null }>(null)

  const T = {
    spotTitle: tr(language, { ko: '현물', en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Spot', id: 'Spot' }),
    futTitle: tr(language, { ko: '선물', en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures', id: 'Futures' }),
    orderBook: tr(language, { ko: '호가창', en: 'Order book', ja: '板情報', th: 'สมุดคำสั่ง', vi: 'Sổ lệnh', id: 'Order book' }),
    recentTrades: tr(language, { ko: '최근 체결', en: 'Recent trades', ja: '約定履歴', th: 'การซื้อขายล่าสุด', vi: 'Giao dịch gần đây', id: 'Transaksi terbaru' }),
    spread: tr(language, { ko: '스프레드', en: 'Spread', ja: 'スプレッド', th: 'สเปรด', vi: 'Chênh lệch', id: 'Spread' }),
    priceCol: tr(language, { ko: '가격', en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá', id: 'Harga' }),
    qtyCol: tr(language, { ko: '수량', en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL', id: 'Jml' }),
    totalCol: tr(language, { ko: '합계', en: 'Total', ja: '累計', th: 'รวม', vi: 'Tổng', id: 'Total' }),
    timeCol: tr(language, { ko: '시간', en: 'Time', ja: '時刻', th: 'เวลา', vi: 'Thời gian', id: 'Waktu' }),
    market: tr(language, { ko: '시장', en: 'Market', ja: '成行', th: 'ราคาตลาด', vi: 'Thị trường', id: 'Pasar' }),
    limitSoon: tr(language, { ko: '지정가 (곧 지원)', en: 'Limit (soon)', ja: '指値(準備中)', th: 'ลิมิต (เร็วๆนี้)', vi: 'Limit (sắp có)', id: 'Limit (segera)' }),
    buy: tr(language, { ko: '매수', en: 'Buy', ja: '買い', th: 'ซื้อ', vi: 'Mua', id: 'Beli' }),
    sell: tr(language, { ko: '매도', en: 'Sell', ja: '売り', th: 'ขาย', vi: 'Bán', id: 'Jual' }),
    long: tr(language, { ko: '매수 / 롱', en: 'Buy / Long', ja: '買い/ロング', th: 'ซื้อ / Long', vi: 'Mua / Long', id: 'Beli / Long' }),
    short: tr(language, { ko: '매도 / 공매도', en: 'Sell / Short', ja: '売り/ショート', th: 'ขาย / Short', vi: 'Bán / Short', id: 'Jual / Short' }),
    available: tr(language, { ko: '사용 가능', en: 'Available', ja: '利用可能', th: 'พร้อมใช้', vi: 'Khả dụng', id: 'Tersedia' }),
    holding: tr(language, { ko: '보유', en: 'Holding', ja: '保有量', th: 'ถือครอง', vi: 'Nắm giữ', id: 'Dimiliki' }),
    orderValue: tr(language, { ko: '주문 금액 (USDT)', en: 'Order value (USDT)', ja: '注文金額 (USDT)', th: 'มูลค่าคำสั่ง (USDT)', vi: 'Giá trị lệnh (USDT)', id: 'Nilai order (USDT)' }),
    quantity: tr(language, { ko: '수량', en: 'Quantity', ja: '数量', th: 'จำนวน', vi: 'Số lượng', id: 'Kuantitas' }),
    fee: tr(language, { ko: '수수료', en: 'Fee', ja: '手数料', th: 'ค่าธรรมเนียม', vi: 'Phí', id: 'Biaya' }),
    margin: tr(language, { ko: '증거금', en: 'Margin', ja: '証拠金', th: 'มาร์จิน', vi: 'Ký quỹ', id: 'Margin' }),
    liqApprox: tr(language, { ko: '청산가 (근사치)', en: 'Liq. price (approx)', ja: '清算価格(概算)', th: 'ราคาล้างพอร์ต (ประมาณ)', vi: 'Giá thanh lý (xấp xỉ)', id: 'Harga likuidasi (perkiraan)' }),
    lev: tr(language, { ko: '레버리지', en: 'Leverage', ja: 'レバレッジ', th: 'เลเวอเรจ', vi: 'Đòn bẩy', id: 'Leverage' }),
    tp: tr(language, { ko: '이익 실현 (TP)', en: 'Take profit (TP)', ja: '利確 (TP)', th: 'ทำกำไร (TP)', vi: 'Chốt lời (TP)', id: 'Take profit (TP)' }),
    sl: tr(language, { ko: '손절 (SL)', en: 'Stop loss (SL)', ja: '損切り (SL)', th: 'ตัดขาดทุน (SL)', vi: 'Cắt lỗ (SL)', id: 'Stop loss (SL)' }),
    tpslNote: tr(language, { ko: 'TP/SL은 포지션에 등록되며 서버 리스크 워처가 주기적으로 확인해 전량 청산합니다.', en: 'TP/SL is registered on the position; the server risk watcher checks it periodically and closes the full position.', ja: 'TP/SLはポジションに登録され、サーバーが定期的に確認して全量決済します。', th: 'TP/SL จะลงทะเบียนกับสถานะ เซิร์ฟเวอร์ตรวจสอบเป็นระยะและปิดทั้งหมด', vi: 'TP/SL được đăng ký vào vị thế; máy chủ kiểm tra định kỳ và đóng toàn bộ.', id: 'TP/SL didaftarkan pada posisi; server memeriksanya berkala dan menutup seluruh posisi.' }),
    tpslInvalid: tr(language, { ko: 'TP/SL 값이 현재가 기준으로 잘못되었습니다 (롱: SL<현재가<TP, 숏: 반대).', en: 'TP/SL is on the wrong side of the current price (long: SL<price<TP; short inverted).', ja: 'TP/SLが現在価格に対して不正です（ロング: SL<価格<TP、ショートは逆）。', th: 'TP/SL อยู่ผิดฝั่งของราคาปัจจุบัน', vi: 'TP/SL nằm sai phía so với giá hiện tại.', id: 'TP/SL berada di sisi yang salah dari harga saat ini.' }),
    funding: tr(language, { ko: '펀딩 / 카운트다운', en: 'Funding / Countdown', ja: '資金調達率', th: 'ฟันดิง / นับถอยหลัง', vi: 'Funding / Đếm ngược', id: 'Funding / Hitung mundur' }),
    confirmTitle: tr(language, { ko: '주문 확인', en: 'Confirm order', ja: '注文確認', th: 'ยืนยันคำสั่ง', vi: 'Xác nhận lệnh', id: 'Konfirmasi order' }),
    dontShowAgain: tr(language, { ko: '다시 표시 안 함', en: "Don't show again", ja: '今後表示しない', th: 'ไม่ต้องแสดงอีก', vi: 'Không hiển thị lại', id: 'Jangan tampilkan lagi' }),
    entry: tr(language, { ko: '진입 가격 (실시간)', en: 'Entry price (live)', ja: '約定価格(現在)', th: 'ราคาเข้า (สด)', vi: 'Giá vào (trực tiếp)', id: 'Harga masuk (langsung)' }),
    totalCost: tr(language, { ko: '총 비용', en: 'Total cost', ja: '合計', th: 'รวมทั้งหมด', vi: 'Tổng chi phí', id: 'Total biaya' }),
    cancel: tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' }),
    confirmBtn: tr(language, { ko: '확인', en: 'Confirm', ja: '確定', th: 'ยืนยัน', vi: 'Xác nhận', id: 'Konfirmasi' }),
    save: tr(language, { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu', id: 'Simpan' }),
    holdings: tr(language, { ko: '보유 자산', en: 'Holdings', ja: '保有資産', th: 'ถือครอง', vi: 'Nắm giữ', id: 'Kepemilikan' }),
    positionsTab: tr(language, { ko: '포지션', en: 'Positions', ja: 'ポジション', th: 'สถานะ', vi: 'Vị thế', id: 'Posisi' }),
    historyTab: tr(language, { ko: '거래 내역', en: 'Trade history', ja: '取引履歴', th: 'ประวัติการเทรด', vi: 'Lịch sử giao dịch', id: 'Riwayat transaksi' }),
    close: tr(language, { ko: '시장가 청산', en: 'Market close', ja: '成行決済', th: 'ปิดที่ตลาด', vi: 'Đóng thị trường', id: 'Tutup di harga pasar' }),
    closeAmount: tr(language, { ko: '청산 수량', en: 'Close quantity', ja: '決済数量', th: 'จำนวนที่ปิด', vi: 'Số lượng đóng', id: 'Jumlah penutupan' }),
    editTpsl: tr(language, { ko: 'TP/SL 수정', en: 'Edit TP/SL', ja: 'TP/SL編集', th: 'แก้ไข TP/SL', vi: 'Sửa TP/SL', id: 'Edit TP/SL' }),
    clearHint: tr(language, { ko: '비워두면 해제됩니다.', en: 'Leave blank to clear.', ja: '空欄で解除。', th: 'เว้นว่างเพื่อล้าง', vi: 'Để trống để xóa.', id: 'Kosongkan untuk menghapus.' }),
    fillNote: tr(language, { ko: '시장가 주문은 실시간 가격으로 즉시 체결됩니다 (모의 거래).', en: 'Market orders fill instantly at the live price (paper trading).', ja: '成行注文は現在価格で即時約定します（模擬取引）。', th: 'คำสั่งตลาดจะเติมทันทีที่ราคาสด (เทรดจำลอง)', vi: 'Lệnh thị trường khớp ngay theo giá thật (mô phỏng).', id: 'Order pasar tereksekusi seketika pada harga langsung (paper trading).' }),
    levNote: tr(language, { ko: '레버리지는 포지션 규모를 결정하며, 이 시뮬레이터에서 손익은 선형이고 청산가는 근사치입니다.', en: 'Leverage sizes the position; PnL is linear and liq is approximate in this simulator.', ja: 'レバレッジはサイズにのみ影響（清算価格は概算）。', th: 'เลเวอเรจกำหนดขนาดสถานะ ราคาล้างพอร์ตเป็นค่าประมาณ', vi: 'Đòn bẩy chỉ định cỡ vị thế; giá thanh lý là xấp xỉ.', id: 'Leverage menentukan ukuran posisi; laba rugi bersifat linear dan harga likuidasi hanya perkiraan dalam simulator ini.' }),
    login: tr(language, { ko: '거래하려면 로그인하세요.', en: 'Log in to trade.', ja: 'ログインしてください。', th: 'เข้าสู่ระบบเพื่อเทรด', vi: 'Đăng nhập để giao dịch.', id: 'Masuk untuk bertransaksi.' }),
    change: tr(language, { ko: '24시간 변동', en: '24h change', ja: '24h変動', th: 'เปลี่ยน 24ชม.', vi: '24h', id: 'Perubahan 24 jam' }),
    markPrice: tr(language, { ko: '표시가', en: 'Mark', ja: 'マーク', th: 'Mark', vi: 'Mark', id: 'Harga pasar' }),
    volume: tr(language, { ko: '24시간 거래량', en: '24h volume', ja: '24h出来高', th: 'ปริมาณ 24ชม.', vi: 'KL 24h', id: 'Volume 24 jam' }),
    empty: tr(language, { ko: '아직 아무것도 없습니다.', en: 'Nothing here yet.', ja: 'まだありません。', th: 'ยังไม่มีข้อมูล', vi: 'Trống.', id: 'Belum ada apa pun di sini.' }),
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
  async function loadTrades() {
    try {
      const res = await fetch(`${API_BASE}/markets/crypto/trades?symbol=${symbol}USDT&limit=30`)
      if (!res.ok) return
      const data = await res.json()
      if (Array.isArray(data.trades)) setTrades(data.trades)
    } catch { /* transient */ }
  }
  async function loadFunding() {
    if (isSpot) return
    try {
      const res = await fetch(`${API_BASE}/markets/crypto/funding?symbol=${symbol}USDT`)
      if (res.ok) setFunding(await res.json())
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
  async function loadHistory() {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/positions/trades?limit=50`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await res.json()
      if (res.ok) setHistory(data.trades || [])
    } catch { /* transient */ }
  }
  useEffect(() => {
    lastPriceRef.current = null
    setTrades([]); setFunding(null)
    loadTicker(); loadBook(); loadTrades(); loadFunding(); loadPositions()
    const t1 = setInterval(loadTicker, 4000)
    const t2 = setInterval(loadBook, 4000)
    const t3 = setInterval(loadPositions, 12000)
    const t4 = setInterval(loadTrades, 4000)
    const t5 = setInterval(loadFunding, 60000)
    return () => { clearInterval(t1); clearInterval(t2); clearInterval(t3); clearInterval(t4); clearInterval(t5) }
  }, [symbol, token])
  useEffect(() => { fetchFeeRate('crypto').then(setFeeRate) }, [])
  useEffect(() => { if (tab === 'history') loadHistory() }, [tab])

  // funding countdown ticks every second (ga FundingStat)
  useEffect(() => {
    if (isSpot) return
    const id = setInterval(() => {
      const next = funding?.next_funding_time
      if (!next) { setCountdown(''); return }
      let left = Math.max(0, Math.floor((next - Date.now()) / 1000))
      const h = String(Math.floor(left / 3600)).padStart(2, '0')
      left %= 3600
      setCountdown(`${h}:${String(Math.floor(left / 60)).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}`)
    }, 1000)
    return () => clearInterval(id)
  }, [funding, isSpot])

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
  function applyPct(p: number, lev = leverage) {
    setPct(p)
    if (!price) return
    if (isSpot && side === 'sell') { syncFromQty(((longQty * p) / 100).toFixed(6)); return }
    // ga quantityForPct: reserve covers the fee on the LEVERAGED notional
    // plus a slippage buffer, so a 100% order is still affordable after fees.
    const lv = isSpot ? 1 : lev
    const margin = (cash * (p / 100)) / (1 + lv * feeRate + SLIPPAGE_BUFFER)
    syncFromValue((margin * lv).toFixed(2))
  }

  const qtyN = parseFloat(qty) || 0
  const notional = price ? qtyN * price : 0
  const fee = notional * feeRate
  const marginReq = isSpot ? notional : notional / leverage
  const liqLong = price ? price * (1 - (1 / leverage - MAINTENANCE_MARGIN_RATE)) : null
  const liqShort = price ? price * (1 + (1 / leverage - MAINTENANCE_MARGIN_RATE)) : null

  // ga: TP/SL sanity is side-aware and mark-anchored; a level on the wrong
  // side would trigger instantly, so it blocks the submit client-side too.
  function tpslValid(action: 'buy' | 'short'): boolean {
    if (isSpot || !price) return true
    const tp = parseFloat(tpInput), sl = parseFloat(slInput)
    if (tpInput && (!Number.isFinite(tp) || tp <= 0)) return false
    if (slInput && (!Number.isFinite(sl) || sl <= 0)) return false
    if (action === 'buy') {
      if (tpInput && tp <= price) return false
      if (slInput && sl >= price) return false
    } else {
      if (tpInput && tp >= price) return false
      if (slInput && sl <= price) return false
    }
    return true
  }

  async function applyTpslToNewPosition(action: 'buy' | 'short') {
    if (isSpot || (!tpInput && !slInput) || !token) return
    try {
      const res = await fetch(`${API_BASE}/positions`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await res.json()
      if (!res.ok) return
      const wantSide = action === 'buy' ? 'long' : 'short'
      const pos = (data.positions || []).find((p: any) =>
        p.symbol === symbol && p.market === 'crypto' && p.side === wantSide)
      if (!pos) return
      const body: any = {}
      if (tpInput) body.take_profit = parseFloat(tpInput)
      if (slInput) body.stop_loss = parseFloat(slInput)
      const r = await fetch(`${API_BASE}/positions/${pos.id}/tpsl`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => null)
        setMsg({ ok: false, text: `TP/SL: ${typeof err?.detail === 'string' ? err.detail : 'failed'}` })
      }
    } catch { /* transient */ }
  }

  async function submit(action: 'buy' | 'sell' | 'short' | 'cover') {
    if (!token || !price || qtyN <= 0) return
    setBusy(true); setMsg(null)
    const r = await placeOrder(token, { market: 'crypto', action, symbol, price, quantity: qtyN, content: `${mode} terminal` })
    if (r.ok && (action === 'buy' || action === 'short')) await applyTpslToNewPosition(action)
    setMsg(m => (m && !m.ok) ? m : { ok: r.ok, text: r.ok ? `✓ ${r.message} #${r.signalId}` : r.message })
    setBusy(false); setConfirm(null)
    if (r.ok) {
      setQty(''); setOrderValue(''); setPct(0); setTpInput(''); setSlInput('')
      loadPositions(); if (tab === 'history') loadHistory()
    }
  }

  function requestSubmit(action: 'buy' | 'sell' | 'short', label: string) {
    if (!tpslValid(action === 'sell' ? 'buy' : action as 'buy' | 'short')) {
      setMsg({ ok: false, text: T.tpslInvalid }); return
    }
    if (skipConfirm) { submit(action); return }
    setConfirm({ action, label })
  }

  async function marketClose(p: any, quantity: number) {
    if (!token || quantity <= 0 || closing) return
    const action = p.side === 'long' ? 'sell' : 'cover'
    const live = price && p.symbol === symbol ? price : (p.current_price ?? p.entry_price)
    setClosing(true); setCloseMsg(null)
    try {
      const r = await placeOrder(token, { market: p.market, action, symbol: p.symbol, price: live, quantity, content: 'market close' })
      setCloseMsg({ ok: r.ok, text: r.ok ? `✓ closed ${fmtQty(quantity)} ${p.symbol}` : `⚠️ ${r.message}` })
      setCloseTarget(null)
      loadPositions(); if (tab === 'history') loadHistory()
    } finally { setClosing(false) }
  }

  async function saveTpsl() {
    if (!token || !tpslEdit) return
    const body: any = {
      stop_loss: tpslEdit.sl.trim() === '' ? null : parseFloat(tpslEdit.sl),
      take_profit: tpslEdit.tp.trim() === '' ? null : parseFloat(tpslEdit.tp),
    }
    try {
      const r = await fetch(`${API_BASE}/positions/${tpslEdit.pos.id}/tpsl`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => null)
        setTpslEdit(e => e ? { ...e, err: typeof err?.detail === 'string' ? err.detail : 'Failed' } : e)
        return
      }
      setTpslEdit(null)
      loadPositions()
    } catch {
      setTpslEdit(e => e ? { ...e, err: 'Network error' } : e)
    }
  }

  /* ── styles ── */
  const inp: any = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', ...mono }
  const panel: any = { background: 'var(--bg-card,#fffdf9)', border: '1px solid var(--border-color,#d3c8b6)', borderRadius: 12 }

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
  const bestBid = book?.bids?.[0]?.[0], bestAsk = book?.asks?.[0]?.[0]
  const spread = bestBid && bestAsk ? bestAsk - bestBid : null
  const spreadPct = spread && bestBid ? (spread / ((bestAsk! + bestBid) / 2)) * 100 : null

  return (
    <div>
      {/* ── PairStatsHeader (ga) ── */}
      <div style={{ ...panel, display: 'flex', alignItems: 'center', gap: 22, padding: '12px 18px', marginBottom: 14, flexWrap: 'wrap' }}>
        <select value={symbol} onChange={e => { setSymbol(e.target.value); setQty(''); setOrderValue(''); setPct(0) }}
          style={{ ...inp, width: 'auto', fontWeight: 700, fontSize: 15 }}>
          {POPULAR_PAIRS.map(s => <option key={s} value={s}>{pair(s)}</option>)}
        </select>
        <span style={{ ...mono, fontSize: 24, fontWeight: 800, color: flash === 'up' ? UP : flash === 'down' ? DOWN : (ticker && ticker.price_24h_pct >= 0 ? UP : DOWN), transition: 'color .2s' }}>
          {price ? fmtUsd(price, price > 100 ? 2 : 4) : '—'}
        </span>
        <Stat label={T.change} value={ticker ? `${ticker.price_24h_pct >= 0 ? '+' : ''}${ticker.price_24h_pct.toFixed(2)}%` : '—'} color={ticker ? (ticker.price_24h_pct >= 0 ? UP : DOWN) : undefined} />
        {!isSpot && <Stat label={T.markPrice} value={ticker ? fmtUsd(ticker.mark_price, 2) : '—'} />}
        {!isSpot && (
          <Stat label={T.funding}
            value={funding ? `${funding.funding_rate >= 0 ? '+' : ''}${(funding.funding_rate * 100).toFixed(4)}%${countdown ? ` / ${countdown}` : ''}` : '—'}
            color={funding ? (funding.funding_rate >= 0 ? UP : DOWN) : undefined} />
        )}
        <Stat label={T.volume} value={ticker ? fmtUsd(ticker.volume_24h, 0) : '—'} />
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-secondary,#8a8073)' }}>{isSpot ? T.spotTitle : `${T.futTitle} · Perpetual (sim)`}</span>
      </div>

      <div style={{ display: 'flex', gap: 14, alignItems: 'stretch', flexWrap: 'wrap' }}>
        {/* ── Chart (ga TradingViewChart + ChartToolbar) ── */}
        <div style={{ ...panel, flex: '2 1 480px', minHeight: 480, height: '65vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <TradingViewChart symbol={symbol} perp={!isSpot} language={language} />
        </div>

        {/* ── OrderBookPanel + RecentTradesPanel (ga right column, 55/45) ── */}
        <div style={{ flex: '1 1 250px', maxWidth: 340, minHeight: 480, height: '65vh', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ ...panel, flex: '1 1 55%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '10px 12px', fontWeight: 700, fontSize: 13, borderBottom: '1px solid var(--border-color,#e6ddd0)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span>{T.orderBook}</span>
              {spread !== null && (
                <span style={{ ...mono, fontSize: 10.5, fontWeight: 500, color: 'var(--text-secondary,#8a8073)' }}>
                  {T.spread} {spread.toFixed(2)} ({spreadPct!.toFixed(3)}%)
                </span>
              )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: 4, padding: '6px 10px', fontSize: 10.5, color: 'var(--text-secondary,#8a8073)', textTransform: 'uppercase' }}>
              <span>{T.priceCol}</span><span style={{ textAlign: 'right' }}>{T.qtyCol}</span><span style={{ textAlign: 'right' }}>{T.totalCol}</span>
            </div>
            {book ? (
              <div style={{ overflowY: 'auto', flex: 1 }}>
                {bookRows(book.asks.slice(0, 8), DOWN, true)}
                <div style={{ ...mono, padding: '6px 10px', fontSize: 16, fontWeight: 800, borderTop: '1px solid var(--border-color,#e6ddd0)', borderBottom: '1px solid var(--border-color,#e6ddd0)', color: flash === 'down' ? DOWN : UP }}>
                  {price ? fmtUsd(price, price > 100 ? 2 : 4) : '—'} {flash === 'up' ? '↑' : flash === 'down' ? '↓' : ''}
                </div>
                {bookRows(book.bids.slice(0, 8), UP)}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', fontSize: 11 }}>
                  <b style={{ color: UP }}>B {buyPct}%</b>
                  <div style={{ flex: 1, height: 4, borderRadius: 2, background: `linear-gradient(to right, ${UP} ${buyPct}%, ${DOWN} ${buyPct}%)` }} />
                  <b style={{ color: DOWN }}>{100 - buyPct}% S</b>
                </div>
              </div>
            ) : <div style={{ padding: 16, color: 'var(--text-secondary,#8a8073)', fontSize: 13 }}>…</div>}
          </div>

          <div style={{ ...panel, flex: '1 1 45%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '10px 12px', fontWeight: 700, fontSize: 13, borderBottom: '1px solid var(--border-color,#e6ddd0)' }}>{T.recentTrades}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr 1fr', gap: 4, padding: '6px 10px', fontSize: 10.5, color: 'var(--text-secondary,#8a8073)', textTransform: 'uppercase' }}>
              <span>{T.timeCol}</span><span style={{ textAlign: 'right' }}>{T.priceCol}</span><span style={{ textAlign: 'right' }}>{T.qtyCol}</span>
            </div>
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {trades.length === 0
                ? <div style={{ padding: 16, color: 'var(--text-secondary,#8a8073)', fontSize: 13 }}>…</div>
                : trades.map((t, i) => (
                  <div key={`${t.ts}-${i}`} onClick={() => syncFromQty(t.size.toFixed(6))}
                    style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr 1fr', gap: 4, padding: '2px 10px', fontSize: 12, cursor: 'pointer' }}>
                    <span style={{ ...mono, color: 'var(--text-secondary,#8a8073)' }}>{hhmmss(t.ts)}</span>
                    <span style={{ ...mono, textAlign: 'right', color: t.side === 'buy' ? UP : DOWN }}>{fmtUsd(t.price, t.price > 100 ? 1 : 4)}</span>
                    <span style={{ ...mono, textAlign: 'right' }}>{fmtQty(t.size)}</span>
                  </div>
                ))}
            </div>
          </div>
        </div>

        {/* ── OrderFormPanel (ga) ── */}
        <div style={{ ...panel, flex: '1 1 280px', maxWidth: 380, padding: 14, alignSelf: 'flex-start' }}>
          {/* order type tabs */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
            <button style={{ flex: 1, padding: '7px 0', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: 'var(--accent-contrast,#fff)', fontWeight: 700, fontSize: 12.5 }}>{T.market}</button>
            <button disabled style={{ flex: 1, padding: '7px 0', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'var(--text-secondary,#8a8073)', fontSize: 12.5, cursor: 'not-allowed' }}>{T.limitSoon}</button>
          </div>

          {isSpot && (
            <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
              <button onClick={() => { setSide('buy'); setPct(0) }} style={{ flex: 1, padding: '9px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: side === 'buy' ? UP : 'var(--bg-secondary,#f3efe7)', color: side === 'buy' ? '#fff' : 'inherit' }}>{T.buy}</button>
              <button onClick={() => { setSide('sell'); setPct(0) }} style={{ flex: 1, padding: '9px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: side === 'sell' ? DOWN : 'var(--bg-secondary,#f3efe7)', color: side === 'sell' ? '#fff' : 'inherit' }}>{T.sell}</button>
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
              <input type="range" min={1} max={100} value={leverage} onChange={e => { const lv = +e.target.value; setLeverage(lv); if (pct) applyPct(pct, lv) }} style={{ width: '100%' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-secondary,#8a8073)' }}>
                <span>1×</span><span>25×</span><span>50×</span><span>75×</span><span>100×</span>
              </div>
            </div>
          )}

          <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.quantity} ({symbol})</label>
          <input style={inp} value={qty} onChange={e => { setPct(0); syncFromQty(e.target.value) }} placeholder="0.00" />
          <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.orderValue}</label>
          <input style={inp} value={orderValue} onChange={e => { setPct(0); syncFromValue(e.target.value) }} placeholder="0.00" />

          {/* % allocation (ga slider) */}
          <div style={{ margin: '10px 0' }}>
            <input type="range" min={0} max={100} step={1} value={pct} onChange={e => applyPct(+e.target.value)} style={{ width: '100%' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-secondary,#8a8073)' }}>
              {[0, 25, 50, 75, 100].map(p => (
                <span key={p} onClick={() => applyPct(p)} style={{ cursor: 'pointer', fontWeight: pct === p ? 700 : 400 }}>{p}%</span>
              ))}
            </div>
          </div>

          {!isSpot && (
            <>
              <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.tp}</label>
              <input style={inp} value={tpInput} onChange={e => setTpInput(e.target.value)} placeholder="0.00" />
              <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.sl}</label>
              <input style={inp} value={slInput} onChange={e => setSlInput(e.target.value)} placeholder="0.00" />
            </>
          )}

          <div style={{ marginTop: 8 }}>
            <InfoRow label={T.fee} value={`≈ ${fmtUsd(fee)} USDT (${(feeRate * 100).toFixed(3)}%)`} />
            {!isSpot && <InfoRow label={T.margin} value={`≈ ${fmtUsd(marginReq)} USDT`} />}
          </div>
          {!isSpot && qtyN > 0 && (
            <div style={{ background: 'rgba(201,162,39,0.10)', border: '1px solid rgba(201,162,39,0.45)', borderRadius: 8, padding: '8px 10px', fontSize: 12, margin: '8px 0', ...mono }}>
              {T.liqApprox}: <b style={{ color: UP }}>L {liqLong ? fmtUsd(liqLong, 1) : '—'}</b> · <b style={{ color: DOWN }}>S {liqShort ? fmtUsd(liqShort, 1) : '—'}</b>
            </div>
          )}

          {/* action buttons */}
          {isSpot ? (
            <button disabled={busy || qtyN <= 0 || !price}
              onClick={() => requestSubmit(side, side === 'buy' ? T.buy : T.sell)}
              style={{ width: '100%', marginTop: 10, padding: '11px 0', borderRadius: 9, border: 'none', fontWeight: 700, fontSize: 14, cursor: 'pointer', background: side === 'buy' ? UP : DOWN, color: '#fff', opacity: (busy || qtyN <= 0) ? 0.55 : 1 }}>
              {side === 'buy' ? T.buy : T.sell} {pair(symbol)}
            </button>
          ) : (
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button disabled={busy || qtyN <= 0 || !price} onClick={() => requestSubmit('buy', T.long)}
                style={{ flex: 1, padding: '11px 0', borderRadius: 9, border: 'none', fontWeight: 700, cursor: 'pointer', background: UP, color: '#fff', opacity: (busy || qtyN <= 0) ? 0.55 : 1 }}>{T.long}</button>
              <button disabled={busy || qtyN <= 0 || !price} onClick={() => requestSubmit('short', T.short)}
                style={{ flex: 1, padding: '11px 0', borderRadius: 9, border: 'none', fontWeight: 700, cursor: 'pointer', background: DOWN, color: '#fff', opacity: (busy || qtyN <= 0) ? 0.55 : 1 }}>{T.short}</button>
            </div>
          )}

          {msg && <div style={{ marginTop: 10, fontSize: 12.5, color: msg.ok ? UP : DOWN }}>{msg.text}</div>}
          <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.5 }}>
            {T.fillNote}{!isSpot && ` ${T.levNote}`}{!isSpot && (tpInput || slInput) && ` ${T.tpslNote}`}
          </div>
        </div>
      </div>

      {/* ── BottomTabs (ga): Positions/Holdings + Trade history ── */}
      <div style={{ ...panel, marginTop: 14, overflow: 'hidden' }}>
        <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border-color,#e6ddd0)' }}>
          {(['positions', 'history'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ padding: '10px 14px', fontWeight: 700, fontSize: 13, cursor: 'pointer', border: 'none', background: 'transparent', color: tab === t ? 'var(--text-primary,inherit)' : 'var(--text-secondary,#8a8073)', borderBottom: tab === t ? '2px solid var(--accent-primary,#c26a45)' : '2px solid transparent' }}>
              {t === 'positions' ? (isSpot ? T.holdings : T.positionsTab) : T.historyTab}
              {t === 'positions' && positions.filter(p => isSpot ? p.side === 'long' : true).length > 0 &&
                ` (${positions.filter(p => isSpot ? p.side === 'long' : true).length})`}
            </button>
          ))}
        </div>

        {closeMsg && (
          <div style={{ padding: '8px 14px', fontSize: 12.5, color: closeMsg.ok ? UP : DOWN, borderBottom: '1px solid var(--border-color,#e6ddd0)' }}>
            {closeMsg.text}
          </div>
        )}
        {tab === 'positions' ? (() => {
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
                    {!isSpot && <th style={{ textAlign: 'right', padding: '8px 8px' }}>TP / SL</th>}
                    <th style={{ textAlign: 'right', padding: '8px 14px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p, i) => {
                    const cur = p.current_price ?? p.entry_price
                    const value = Math.abs(p.quantity) * (cur ?? 0)
                    const roi = p.entry_price ? ((p.pnl ?? 0) / (Math.abs(p.quantity) * p.entry_price)) * 100 : 0
                    return (
                      <tr key={i} style={{ borderTop: '1px solid var(--border-color,#e6ddd0)' }}>
                        <td style={{ padding: '8px 14px', fontWeight: 700 }}>{pair(p.symbol)}</td>
                        {!isSpot && <td style={{ padding: '8px 8px', color: p.side === 'long' ? UP : DOWN, fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>{p.side}</td>}
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtQty(Math.abs(p.quantity))}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(p.entry_price)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(cur)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(value)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px', color: pnlColor(p.pnl) }}>
                          {(p.pnl ?? 0) >= 0 ? '+' : ''}{fmtUsd(p.pnl ?? 0)} / {roi.toFixed(2)}%
                        </td>
                        {!isSpot && (
                          <td style={{ ...mono, textAlign: 'right', padding: '8px 8px', fontSize: 12 }}>
                            <span style={{ color: UP }}>{p.take_profit ? fmtUsd(p.take_profit, 1) : '—'}</span>
                            {' / '}
                            <span style={{ color: DOWN }}>{p.stop_loss ? fmtUsd(p.stop_loss, 1) : '—'}</span>
                            <button onClick={() => setTpslEdit({ pos: p, sl: p.stop_loss ? String(p.stop_loss) : '', tp: p.take_profit ? String(p.take_profit) : '', err: null })}
                              title={T.editTpsl}
                              style={{ marginLeft: 6, padding: '2px 7px', borderRadius: 6, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', fontSize: 11, cursor: 'pointer' }}>✎</button>
                          </td>
                        )}
                        <td style={{ textAlign: 'right', padding: '8px 14px' }}>
                          <button onClick={() => setCloseTarget({ pos: p, qtyStr: String(Math.abs(p.quantity)), pct: 100 })}
                            style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', fontSize: 11.5, cursor: 'pointer' }}>{T.close}</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        })() : (
          history.length === 0
            ? <div style={{ padding: 16, color: 'var(--text-secondary,#8a8073)', fontSize: 13 }}>{T.empty}</div>
            : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 11, textTransform: 'uppercase' }}>
                      <th style={{ textAlign: 'left', padding: '8px 14px' }}>{T.timeCol}</th>
                      <th style={{ textAlign: 'left', padding: '8px 8px' }}>Asset</th>
                      <th style={{ textAlign: 'left', padding: '8px 8px' }}>Side</th>
                      <th style={{ textAlign: 'right', padding: '8px 8px' }}>Entry</th>
                      <th style={{ textAlign: 'right', padding: '8px 8px' }}>Exit</th>
                      <th style={{ textAlign: 'right', padding: '8px 8px' }}>{T.qtyCol}</th>
                      <th style={{ textAlign: 'right', padding: '8px 14px' }}>PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((t: any, i: number) => (
                      <tr key={t.signal_id ?? i} style={{ borderTop: '1px solid var(--border-color,#e6ddd0)' }}>
                        <td style={{ ...mono, padding: '8px 14px', fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>
                          {(t.executed_at || t.created_at || '').replace('T', ' ').slice(0, 19)}
                        </td>
                        <td style={{ padding: '8px 8px', fontWeight: 700 }}>{t.market === 'crypto' ? pair(t.symbol) : t.symbol}</td>
                        <td style={{ padding: '8px 8px', fontWeight: 700, fontSize: 12, textTransform: 'uppercase', color: (t.side === 'buy' || t.side === 'cover') ? UP : DOWN }}>{t.side}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtUsd(t.entry_price)}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{t.exit_price ? fmtUsd(t.exit_price) : '—'}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 8px' }}>{fmtQty(Math.abs(t.quantity))}</td>
                        <td style={{ ...mono, textAlign: 'right', padding: '8px 14px', color: pnlColor(t.pnl) }}>
                          {t.pnl == null ? '—' : `${t.pnl >= 0 ? '+' : ''}${fmtUsd(t.pnl)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
        )}
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
            {!isSpot && tpInput && <InfoRow label="TP" value={fmtUsd(parseFloat(tpInput))} />}
            {!isSpot && slInput && <InfoRow label="SL" value={fmtUsd(parseFloat(slInput))} />}
            <InfoRow label={T.fee} value={`${fmtUsd(fee)} USDT`} />
            <InfoRow label={T.totalCost} value={`${fmtUsd((confirm.action === 'buy' || confirm.action === 'short' ? notional : 0) + fee)} USDT`} strong />
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginTop: 10, color: 'var(--text-secondary,#8a8073)', cursor: 'pointer' }}>
              <input type="checkbox" checked={skipConfirm} onChange={e => {
                setSkipConfirm(e.target.checked)
                if (e.target.checked) localStorage.setItem(CONFIRM_SKIP_KEY, '1')
                else localStorage.removeItem(CONFIRM_SKIP_KEY)
              }} />
              {T.dontShowAgain}
            </label>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button onClick={() => setConfirm(null)} style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>{T.cancel}</button>
              <button disabled={busy} onClick={() => submit(confirm.action)}
                style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: (confirm.action === 'buy') ? UP : DOWN, color: '#fff' }}>{T.confirmBtn}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MarketCloseConfirmModal (ga): partial close picker ── */}
      {closeTarget && (
        <div onClick={() => setCloseTarget(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ ...panel, width: 360, padding: 20 }}>
            <div style={{ fontWeight: 800, marginBottom: 12 }}>{T.close} · {pair(closeTarget.pos.symbol)}</div>
            <InfoRow label={T.holding} value={fmtQty(Math.abs(closeTarget.pos.quantity))} />
            <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.closeAmount}</label>
            <input style={inp} value={closeTarget.qtyStr}
              onChange={e => setCloseTarget(c => c ? { ...c, qtyStr: e.target.value, pct: 0 } : c)} />
            <div style={{ display: 'flex', gap: 6, margin: '10px 0' }}>
              {[25, 50, 75, 100].map(p => (
                <button key={p}
                  onClick={() => setCloseTarget(c => c ? { ...c, pct: p, qtyStr: (Math.abs(c.pos.quantity) * p / 100).toFixed(6) } : c)}
                  style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--border-color,#d3c8b6)', background: closeTarget.pct === p ? 'var(--accent-primary,#c26a45)' : 'transparent', color: closeTarget.pct === p ? 'var(--accent-contrast,#fff)' : 'var(--text-secondary,#8a8073)', fontSize: 11.5, cursor: 'pointer' }}>{p}%</button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => setCloseTarget(null)} style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>{T.cancel}</button>
              <button
                disabled={closing || !(parseFloat(closeTarget.qtyStr) > 0) || parseFloat(closeTarget.qtyStr) > Math.abs(closeTarget.pos.quantity) + 1e-9}
                onClick={() => marketClose(closeTarget.pos, Math.min(parseFloat(closeTarget.qtyStr), Math.abs(closeTarget.pos.quantity)))}
                style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: DOWN, color: '#fff', opacity: closing ? 0.55 : 1 }}>{closing ? '⏳' : T.confirmBtn}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── TpSlEditModal (ga) ── */}
      {tpslEdit && (
        <div onClick={() => setTpslEdit(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: 20 }}>
          <div onClick={e => e.stopPropagation()} style={{ ...panel, width: 360, padding: 20 }}>
            <div style={{ fontWeight: 800, marginBottom: 12 }}>{T.editTpsl} · {pair(tpslEdit.pos.symbol)} <span style={{ color: tpslEdit.pos.side === 'long' ? UP : DOWN, fontSize: 12, textTransform: 'uppercase' }}>{tpslEdit.pos.side}</span></div>
            <InfoRow label="Entry" value={fmtUsd(tpslEdit.pos.entry_price)} />
            <InfoRow label={isSpot ? 'Current' : 'Mark'} value={fmtUsd(tpslEdit.pos.current_price ?? tpslEdit.pos.entry_price)} />
            <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.tp}</label>
            <input style={inp} value={tpslEdit.tp} onChange={e => setTpslEdit(s => s ? { ...s, tp: e.target.value } : s)} placeholder="—" />
            <label style={{ fontSize: 12, display: 'block', margin: '10px 0 4px' }}>{T.sl}</label>
            <input style={inp} value={tpslEdit.sl} onChange={e => setTpslEdit(s => s ? { ...s, sl: e.target.value } : s)} placeholder="—" />
            <div style={{ fontSize: 11, color: 'var(--text-secondary,#8a8073)', marginTop: 6 }}>{T.clearHint} {T.tpslNote}</div>
            {tpslEdit.err && <div style={{ marginTop: 8, fontSize: 12.5, color: DOWN }}>{tpslEdit.err}</div>}
            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
              <button onClick={() => setTpslEdit(null)} style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}>{T.cancel}</button>
              <button onClick={saveTpsl}
                style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: 'none', fontWeight: 700, cursor: 'pointer', background: 'var(--accent-primary,#c26a45)', color: 'var(--accent-contrast,#fff)' }}>{T.save}</button>
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
