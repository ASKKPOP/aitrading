import { useState, useEffect } from 'react'
import { API_BASE, REFRESH_INTERVAL, getInstrumentLabel, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { fmtQty, fmtUsd, pnlColor, placeOrder } from './tradeShared'

// Order-status view (Plan 11 F3a) — the zenix.global bottom-panel layout:
// four tabs over one account, numeric columns right-aligned and monospaced,
// multi-line cells stacking a label with its value, and one sign rule for
// every P&L figure. Market-close routes through the same /api/signals/realtime
// path the trading pages use (sell closes a long, cover closes a short).

type Tab = 'positions' | 'open' | 'orders' | 'trades'

const th: React.CSSProperties = {
  padding: '8px 10px', fontSize: 11, fontWeight: 400, textAlign: 'right',
  color: 'var(--text-secondary,#8a8073)', whiteSpace: 'nowrap',
  borderBottom: '1px solid var(--border-color)',
}
const thLeft: React.CSSProperties = { ...th, textAlign: 'left' }
const td: React.CSSProperties = {
  padding: '10px', fontSize: 12.5, textAlign: 'right', verticalAlign: 'top',
  fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
  borderBottom: '1px solid var(--border-color)',
}
const tdLeft: React.CSSProperties = { ...td, textAlign: 'left', fontFamily: 'inherit' }
const sub: React.CSSProperties = { fontSize: 11, color: 'var(--text-secondary,#8a8073)' }

export function PositionsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [tab, setTab] = useState<Tab>('positions')
  const [positions, setPositions] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const [trades, setTrades] = useState<any[]>([])
  const [cash, setCash] = useState<number>(100000)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  const { t, language } = useLanguage()

  const authHeaders = { Authorization: `Bearer ${token}` }

  const loadAll = async () => {
    try {
      const [posRes, ordRes, trdRes] = await Promise.all([
        fetch(`${API_BASE}/positions`, { headers: authHeaders }),
        fetch(`${API_BASE}/execution/orders?limit=100`, { headers: authHeaders }),
        fetch(`${API_BASE}/positions/trades?limit=100`, { headers: authHeaders }),
      ])
      const pos = await posRes.json().catch(() => ({}))
      setPositions(pos.positions || [])
      setCash(pos.cash ?? 100000)
      // Orders only exist once a broker gateway is connected; a failure here
      // must not blank the positions table.
      const ord = ordRes.ok ? await ordRes.json().catch(() => ({})) : {}
      setOrders(ord.orders || [])
      const trd = trdRes.ok ? await trdRes.json().catch(() => ({})) : {}
      setTrades(trd.trades || [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => {
    if (!token) { setLoading(false); return }
    loadAll()
    const interval = setInterval(loadAll, REFRESH_INTERVAL)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const T = {
    tabPositions: tr(language, { ko: '포지션', en: 'Positions', ja: 'ポジション', th: 'สถานะ', vi: 'Vị thế', id: 'Posisi' }),
    tabOpen: tr(language, { ko: '미체결 주문', en: 'Open Orders', ja: '未約定注文', th: 'คำสั่งค้าง', vi: 'Lệnh chờ', id: 'Order terbuka' }),
    tabOrders: tr(language, { ko: '주문 내역', en: 'Order History', ja: '注文履歴', th: 'ประวัติคำสั่ง', vi: 'Lịch sử lệnh', id: 'Riwayat order' }),
    tabTrades: tr(language, { ko: '거래 내역', en: 'Trade History', ja: '取引履歴', th: 'ประวัติเทรด', vi: 'Lịch sử giao dịch', id: 'Riwayat transaksi' }),
    contract: tr(language, { ko: '계약', en: 'Contract', ja: '契約', th: 'สัญญา', vi: 'Hợp đồng', id: 'Kontrak' }),
    price: tr(language, { ko: '가격', en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá', id: 'Harga' }),
    entry: tr(language, { ko: '진입가', en: 'Entry', ja: '進入価', th: 'ราคาเข้า', vi: 'Giá vào', id: 'Harga masuk' }),
    mark: tr(language, { ko: '현재가', en: 'Mark', ja: '現在価', th: 'ราคาปัจจุบัน', vi: 'Giá hiện tại', id: 'Harga pasar' }),
    value: tr(language, { ko: '가치', en: 'Value', ja: '価値', th: 'มูลค่า', vi: 'Giá trị', id: 'Nilai' }),
    pnl: tr(language, { ko: '손익', en: 'PnL', ja: '損益', th: 'กำไรขาดทุน', vi: 'Lãi/Lỗ', id: 'Laba rugi' }),
    close: tr(language, { ko: '청산', en: 'Close', ja: '決済', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    market: tr(language, { ko: '시장가', en: 'Market', ja: '成行', th: 'ราคาตลาด', vi: 'Thị trường', id: 'Pasar' }),
    long: tr(language, { ko: '롱', en: 'Long', ja: 'ロング', th: 'ลอง', vi: 'Long', id: 'Long' }),
    short: tr(language, { ko: '숏', en: 'Short', ja: 'ショート', th: 'ชอร์ต', vi: 'Short', id: 'Short' }),
    qty: tr(language, { ko: '수량', en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL', id: 'Jml' }),
    side: tr(language, { ko: '방향', en: 'Side', ja: '方向', th: 'ทิศทาง', vi: 'Hướng', id: 'Arah' }),
    status: tr(language, { ko: '상태', en: 'Status', ja: '状態', th: 'สถานะ', vi: 'Trạng thái', id: 'Status' }),
    time: tr(language, { ko: '시간', en: 'Time', ja: '時間', th: 'เวลา', vi: 'Thời gian', id: 'Waktu' }),
    source: tr(language, { ko: '출처', en: 'Source', ja: 'ソース', th: 'แหล่งที่มา', vi: 'Nguồn', id: 'Sumber' }),
    unmanaged: tr(language, { ko: '관리 주체 없음 · 손절 없음', en: 'No run · no stop',
      ja: '管理なし · 損切りなし', th: 'ไม่มีผู้ดูแล · ไม่มีจุดตัดขาดทุน',
      vi: 'Không ai quản lý · không cắt lỗ',
      id: 'Tanpa run · tanpa stop' }),
    unmanagedHint: tr(language, {
      ko: '이 포지션을 지켜보는 TRADING이 없고 손절·익절도 설정돼 있지 않습니다. 직접 청산하거나 손절을 지정하세요.',
      en: 'No TRADING is watching this position and it has no stop or take-profit. Close it yourself or set an exit level.',
      ja: 'このポジションを見ている TRADING がなく、損切り・利確も未設定です。手動で決済するか、決済水準を設定してください。',
      th: 'ไม่มี TRADING เฝ้าสถานะนี้ และไม่ได้ตั้งจุดตัดขาดทุนหรือทำกำไร ปิดเองหรือกำหนดจุดออก',
      vi: 'Không có TRADING nào theo dõi vị thế này và cũng không có mức cắt lỗ hay chốt lời. Hãy tự đóng hoặc đặt mức thoát.',
      id: 'Tidak ada TRADING yang mengawasi posisi ini dan posisi ini tidak punya stop loss atau take profit. Tutup sendiri atau tetapkan level keluar.' }),
    self: tr(language, { ko: '본인', en: 'Self', ja: '自分', th: 'ตนเอง', vi: 'Tự', id: 'Sendiri' }),
    copied: tr(language, { ko: '복제', en: 'Copied', ja: 'コピー', th: 'คัดลอก', vi: 'Sao chép', id: 'Salinan' }),
    cash: tr(language, { ko: '가용 현금', en: 'Available Cash', ja: '利用可能な現金', th: 'เงินสดที่ใช้ได้', vi: 'Tiền khả dụng', id: 'Kas tersedia' }),
    none: tr(language, { ko: '내역이 없습니다', en: 'Nothing here yet', ja: '履歴がありません', th: 'ยังไม่มีรายการ', vi: 'Chưa có dữ liệu', id: 'Belum ada apa pun di sini' }),
    closing: tr(language, { ko: '청산 중…', en: 'Closing…', ja: '決済中…', th: 'กำลังปิด…', vi: 'Đang đóng…', id: 'Menutup…' }),
    confirmClose: tr(language, { ko: '이 포지션을 시장가로 청산할까요?', en: 'Close this position at market price?', ja: 'このポジションを成行で決済しますか？', th: 'ปิดสถานะนี้ที่ราคาตลาด?', vi: 'Đóng vị thế này theo giá thị trường?', id: 'Tutup posisi ini pada harga pasar?' }),
  }

  const pending = orders.filter(o => (o.status || '').toLowerCase() === 'pending')

  async function closePosition(pos: any) {
    if (!token || !pos.current_price) return
    if (!window.confirm(`${T.confirmClose}\n\n${getInstrumentLabel(pos)} · ${fmtQty(Math.abs(pos.quantity))}`)) return
    setBusyId(pos.id); setNotice('')
    // A long is closed by selling, a short by covering — mirrors run_cycle's
    // futures mapping on the server.
    const action = pos.side === 'short' ? 'cover' : 'sell'
    const res = await placeOrder(token, {
      market: pos.market || 'crypto', action, symbol: pos.symbol,
      price: Number(pos.current_price), quantity: Math.abs(Number(pos.quantity)),
      content: 'Market close from positions view',
    })
    setNotice(res.ok ? '' : res.message)
    setBusyId(null)
    await loadAll()
  }

  if (!token) {
    return (
      <div>
        <div className="header"><div><h1 className="header-title">{t.positions.title}</h1></div></div>
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <div className="empty-title">{t.errors.pleaseLogin}</div>
        </div>
      </div>
    )
  }

  const tabs: Array<{ key: Tab; label: string; count?: number }> = [
    { key: 'positions', label: T.tabPositions, count: positions.length },
    { key: 'open', label: T.tabOpen, count: pending.length },
    { key: 'orders', label: T.tabOrders },
    { key: 'trades', label: T.tabTrades },
  ]

  const emptyRow = (cols: number) => (
    <tr><td colSpan={cols} style={{ ...td, textAlign: 'center', color: 'var(--text-secondary)', padding: '28px 10px' }}>{T.none}</td></tr>
  )

  const timeCell = (v?: string | null) =>
    v ? new Date(v).toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.positions.title}</h1>
          <p className="header-subtitle">
            {tr(language, { ko: '포지션 · 주문 · 체결 현황', en: 'Positions, orders and fills', ja: 'ポジション・注文・約定', th: 'สถานะ คำสั่ง และการจับคู่', vi: 'Vị thế, lệnh và khớp lệnh', id: 'Posisi, order, dan eksekusi' })}
          </p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{T.cash}</div>
          <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--accent-primary)', fontFamily: 'var(--font-mono)' }}>
            ${fmtUsd(cash)}
          </div>
        </div>
      </div>

      {notice && (
        <div className="card" style={{ padding: '10px 14px', marginBottom: 10, color: '#f0663f', fontSize: 12.5 }}>⚠️ {notice}</div>
      )}

      {/* ── tab bar ── */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
        {tabs.map(tb => (
          <button key={tb.key} onClick={() => setTab(tb.key)}
            style={{
              padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13,
              fontWeight: tab === tb.key ? 700 : 500, fontFamily: 'inherit',
              border: '1px solid ' + (tab === tb.key ? 'transparent' : 'var(--border-color)'),
              background: tab === tb.key ? 'var(--accent-primary)' : 'transparent',
              color: tab === tb.key ? '#fff' : 'var(--text-secondary,#8a8073)',
            }}>
            {tb.label}{tb.count !== undefined ? ` (${tb.count})` : ''}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>

            {tab === 'positions' && (
              <table style={{ width: '100%', minWidth: 820, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thLeft}>{T.contract}</th>
                    <th style={th}>{T.price}</th>
                    <th style={th}>{T.value}</th>
                    <th style={th}>{T.pnl}</th>
                    <th style={th}>TP/SL</th>
                    <th style={th}>{T.source}</th>
                    <th style={th}>{T.close}</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.length === 0 ? emptyRow(7) : positions.map(pos => {
                    const qty = Math.abs(Number(pos.quantity) || 0)
                    const isShort = pos.side === 'short'
                    const value = pos.current_price ? qty * Number(pos.current_price) : null
                    const cost = pos.entry_price ? qty * Number(pos.entry_price) : null
                    const pct = pos.pnl != null && cost ? (Number(pos.pnl) / cost) * 100 : null
                    return (
                      <tr key={pos.id}>
                        <td style={tdLeft}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                            <b>{getInstrumentLabel(pos)}</b>
                            <span style={{ fontSize: 11, fontWeight: 700, color: isShort ? '#f0663f' : '#3fb950' }}>
                              {isShort ? T.short : T.long}
                            </span>
                          </div>
                          <div style={sub}>{pos.market} · {timeCell(pos.opened_at)}</div>
                        </td>
                        <td style={td}>
                          <div style={sub}>{T.entry}</div>
                          <div>{fmtUsd(pos.entry_price)}</div>
                          <div style={sub}>{T.mark}</div>
                          <div>{fmtUsd(pos.current_price)}</div>
                        </td>
                        <td style={td}>
                          <div>{value != null ? `${fmtUsd(value)} USD` : '—'}</div>
                          <div style={sub}>{fmtQty(qty)} {pos.symbol}</div>
                        </td>
                        <td style={{ ...td, color: pnlColor(pos.pnl) }}>
                          <div>{pos.pnl == null ? '—' : `${Number(pos.pnl) >= 0 ? '+' : ''}${fmtUsd(pos.pnl)}`}</div>
                          {pct != null && (
                            <div style={{ fontSize: 11 }}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</div>
                          )}
                        </td>
                        <td style={td}>
                          <div style={{ color: '#3fb950' }}>TP {pos.take_profit ? fmtUsd(pos.take_profit) : '—'}</div>
                          <div style={{ color: '#f0663f' }}>SL {pos.stop_loss ? fmtUsd(pos.stop_loss) : '—'}</div>
                        </td>
                        <td style={td}>
                          <span style={sub}>{pos.source === 'self' ? T.self : T.copied}</span>
                          {/* A run releases its run_id on stop ("close it by
                              hand"), and a manual terminal fill never had one,
                              so an unowned row is normal — but silent. Prod
                              position 13 sat unowned with NO stop for 7 days at
                              −4%. Only flag the pairing that is actually
                              uncontrolled: nobody watching AND no exit level. */}
                          {!pos.managed_by && pos.unprotected && (
                            <div style={{ ...sub, marginTop: 3, color: '#f0663f', fontWeight: 600 }}
                              title={T.unmanagedHint}>
                              ⚠ {T.unmanaged}
                            </div>
                          )}
                        </td>
                        <td style={td}>
                          <button
                            onClick={() => closePosition(pos)}
                            disabled={busyId === pos.id || !pos.current_price}
                            style={{
                              padding: '6px 12px', borderRadius: 7, cursor: 'pointer', fontSize: 11.5, fontWeight: 600,
                              border: '1px solid rgba(240,102,63,0.35)', background: 'rgba(240,102,63,0.12)',
                              color: '#f0663f', opacity: busyId === pos.id || !pos.current_price ? 0.5 : 1,
                              fontFamily: 'inherit',
                            }}>
                            {busyId === pos.id ? T.closing : T.market}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            {(tab === 'open' || tab === 'orders') && (
              <table style={{ width: '100%', minWidth: 720, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thLeft}>{T.contract}</th>
                    <th style={th}>{T.side}</th>
                    <th style={th}>{T.price}</th>
                    <th style={th}>{T.qty}</th>
                    <th style={th}>{T.status}</th>
                    <th style={th}>{T.time}</th>
                  </tr>
                </thead>
                <tbody>
                  {(tab === 'open' ? pending : orders).length === 0
                    ? emptyRow(6)
                    : (tab === 'open' ? pending : orders).map(o => (
                      <tr key={o.id}>
                        <td style={tdLeft}>
                          <b>{o.symbol}</b>
                          <div style={sub}>{o.market} · {o.broker || 'paper'}</div>
                        </td>
                        <td style={{ ...td, color: ['sell', 'short'].includes((o.side || '').toLowerCase()) ? '#f0663f' : '#3fb950' }}>
                          {o.side}
                        </td>
                        <td style={td}>{fmtUsd(o.price)}</td>
                        <td style={td}>
                          <div>{fmtQty(o.quantity)}</div>
                          {o.filled_qty != null && <div style={sub}>fill {fmtQty(o.filled_qty)}</div>}
                        </td>
                        <td style={td}>
                          <div>{o.status}</div>
                          {o.error_message && <div style={{ ...sub, color: '#f0663f' }}>{String(o.error_message).slice(0, 40)}</div>}
                        </td>
                        <td style={td}>
                          <div>{timeCell(o.created_at)}</div>
                          {o.filled_at && <div style={sub}>{timeCell(o.filled_at)}</div>}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}

            {tab === 'trades' && (
              <table style={{ width: '100%', minWidth: 720, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thLeft}>{T.contract}</th>
                    <th style={th}>{T.side}</th>
                    <th style={th}>{T.price}</th>
                    <th style={th}>{T.qty}</th>
                    <th style={th}>{T.pnl}</th>
                    <th style={th}>{T.time}</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.length === 0 ? emptyRow(6) : trades.map(tr_ => (
                    <tr key={tr_.signal_id}>
                      <td style={tdLeft}>
                        <b>{getInstrumentLabel(tr_)}</b>
                        <div style={sub}>{tr_.market}</div>
                      </td>
                      <td style={{ ...td, color: ['sell', 'short'].includes((tr_.side || '').toLowerCase()) ? '#f0663f' : '#3fb950' }}>
                        {tr_.side}
                      </td>
                      <td style={td}>
                        <div>{fmtUsd(tr_.entry_price)}</div>
                        {tr_.exit_price != null && <div style={sub}>→ {fmtUsd(tr_.exit_price)}</div>}
                      </td>
                      <td style={td}>{fmtQty(tr_.quantity)}</td>
                      <td style={{ ...td, color: pnlColor(tr_.pnl) }}>
                        {tr_.pnl == null ? '—' : `${Number(tr_.pnl) >= 0 ? '+' : ''}${fmtUsd(tr_.pnl)}`}
                      </td>
                      <td style={td}>{timeCell(tr_.executed_at || tr_.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

          </div>
        </div>
      )}
    </div>
  )
}

export default PositionsPage
