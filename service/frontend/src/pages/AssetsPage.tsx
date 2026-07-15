import { useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { fmtUsd, fmtQty, pnlColor } from './tradeShared'

// My Assets — modeled on ga's AssetsView (assets overview + wallet cards +
// per-coin expand + activity table), adapted to Sooppiy's paper engine:
// one cash balance + positions (long = "spot", short = "futures").
export function AssetsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [cash, setCash] = useState<number>(0)
  const [positions, setPositions] = useState<any[]>([])
  const [trades, setTrades] = useState<any[]>([])
  const [hide, setHide] = useState(false)
  const [spotOpen, setSpotOpen] = useState(true)

  const T = {
    title: tr(language, { ko: '내 자산', en: 'My Assets', ja: '資産', th: 'ทรัพย์สินของฉัน', vi: 'Tài sản' }),
    overview: tr(language, { ko: '자산 개요', en: 'ASSETS OVERVIEW', ja: '資産概要', th: 'ภาพรวมทรัพย์สิน', vi: 'TỔNG QUAN' }),
    totalNote: tr(language, { ko: '합계 = 가용 현금 + 현물 보유 + 선물 증거금 (모의)', en: 'Total = available cash + spot holdings + futures margin (simulated)', ja: '合計 = 現金 + 現物 + 先物（模擬）', th: 'รวม = เงินสด + ถือครอง + ฟิวเจอร์ส (จำลอง)', vi: 'Tổng = tiền mặt + nắm giữ + ký quỹ (mô phỏng)' }),
    funding: tr(language, { ko: '가용 자금', en: 'Available funds', ja: '利用可能資金', th: 'เงินทุนพร้อมใช้', vi: 'Vốn khả dụng' }),
    fundingDesc: tr(language, { ko: '거래용 모의 자금', en: 'Simulated cash for trading', ja: '取引用の模擬現金', th: 'เงินสดจำลองสำหรับเทรด', vi: 'Tiền mặt mô phỏng' }),
    spot: tr(language, { ko: '현물 보유', en: 'Spot holdings', ja: '現物保有', th: 'ถือครองสปอต', vi: 'Nắm giữ Spot' }),
    spotDesc: tr(language, { ko: '실시간 가격의 롱 포지션', en: 'Long positions at live prices', ja: 'ロングポジション', th: 'สถานะ Long ณ ราคาตลาด', vi: 'Vị thế Long theo giá thật' }),
    futures: tr(language, { ko: '선물 포지션', en: 'Futures positions', ja: '先物ポジション', th: 'สถานะฟิวเจอร์ส', vi: 'Vị thế Futures' }),
    futuresDesc: tr(language, { ko: '숏 노출 (모의)', en: 'Short exposure (paper)', ja: 'ショートエクスポージャー', th: 'สถานะ Short (จำลอง)', vi: 'Vị thế Short (mô phỏng)' }),
    trade: tr(language, { ko: '거래', en: 'Trade', ja: '取引', th: 'เทรด', vi: 'Giao dịch' }),
    viewCoins: tr(language, { ko: '코인별 보기', en: 'View by coin', ja: 'コイン別', th: 'ดูตามเหรียญ', vi: 'Theo coin' }),
    activity: tr(language, { ko: '최근 활동', en: 'Recent activity', ja: '最近の取引', th: 'กิจกรรมล่าสุด', vi: 'Hoạt động gần đây' }),
    noActivity: tr(language, { ko: '아직 거래가 없습니다.', en: 'No trades yet.', ja: '取引はまだありません。', th: 'ยังไม่มีการเทรด', vi: 'Chưa có giao dịch.' }),
    type: tr(language, { ko: '유형', en: 'Type', ja: '種類', th: 'ประเภท', vi: 'Loại' }),
    amount: tr(language, { ko: '수량', en: 'Amount', ja: '数量', th: 'จำนวน', vi: 'Số lượng' }),
    price: tr(language, { ko: '가격', en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá' }),
    date: tr(language, { ko: '날짜', en: 'Date', ja: '日付', th: 'วันที่', vi: 'Ngày' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
    unrealized: tr(language, { ko: '미실현 손익', en: 'Unrealized PnL', ja: '含み損益', th: 'กำไรที่ยังไม่รับรู้', vi: 'PnL chưa thực hiện' }),
  }

  async function load() {
    try {
      const res = await fetch(`${API_BASE}/positions`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await res.json()
      if (res.ok) { setPositions(data.positions || []); setCash(data.cash ?? 0) }
    } catch { /* transient */ }
    try {
      const me = await (await fetch(`${API_BASE}/claw/agents/me`, { headers: { Authorization: `Bearer ${token}` } })).json()
      const feed = await (await fetch(`${API_BASE}/signals/feed?limit=50`)).json()
      setTrades((feed.signals || []).filter((s: any) => s.agent_name === me.name && s.side).slice(0, 10))
    } catch { /* transient */ }
  }

  useEffect(() => {
    if (!token) return
    load()
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
  }, [token])

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">◱</div><div className="empty-title">{T.login}</div></div></div>
  }

  const longs = positions.filter(p => p.side === 'long')
  const shorts = positions.filter(p => p.side !== 'long')
  const val = (p: any) => Math.abs(p.quantity) * (p.current_price ?? p.entry_price ?? 0)
  const spotValue = longs.reduce((s, p) => s + val(p), 0)
  const futValue = shorts.reduce((s, p) => s + val(p), 0)
  const totalPnl = positions.reduce((s, p) => s + (p.pnl ?? 0), 0)
  const total = cash + spotValue + futValue
  const M = (v: string) => hide ? '****' : v

  const walletCard: any = { background: 'var(--bg-card,#fffdf9)', border: '1px solid var(--border,#d3c8b6)', borderRadius: 12, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }
  const icon = (bg: string, ch: string) => (
    <span style={{ width: 38, height: 38, borderRadius: '50%', background: bg, color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, flex: 'none' }}>{ch}</span>
  )
  const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontVariantNumeric: 'tabular-nums' }

  return (
    <div>
      <div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>

      {/* Assets overview (ga: masked total + note) */}
      <div className="card" style={{ marginBottom: 16 }}>
        <button onClick={() => setHide(!hide)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary,#8a8073)', fontSize: 11.5, letterSpacing: '.08em', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
          {T.overview} <span aria-hidden>{hide ? '🙈' : '👁'}</span>
        </button>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 8, flexWrap: 'wrap' }}>
          <span style={{ ...mono, fontSize: 32, fontWeight: 800 }}>{M(fmtUsd(total, 4))}</span>
          <span style={{ color: 'var(--text-secondary,#8a8073)', fontWeight: 600 }}>USDT</span>
          <span style={{ ...mono, color: pnlColor(totalPnl), fontSize: 14 }}>
            {M(`${totalPnl >= 0 ? '+' : ''}${fmtUsd(totalPnl)} ${T.unrealized}`)}
          </span>
        </div>
        <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 12.5, marginTop: 4 }}>{T.totalNote}</div>
      </div>

      {/* Wallet cards (ga: FUNDING / SPOT / FUTURE) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 22 }}>
        <div style={{ ...walletCard, borderLeft: '3px solid #4a6fa5' }}>
          {icon('#4a6fa5', '₣')}
          <div style={{ flex: 1, minWidth: 140 }}>
            <div style={{ fontWeight: 700 }}>{T.funding}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.fundingDesc}</div>
          </div>
          <div style={{ ...mono, fontSize: 18, fontWeight: 700 }}>{M(fmtUsd(cash, 4))} <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>USDT</span></div>
        </div>

        <div style={{ ...walletCard, borderLeft: '3px solid #3fb950', flexDirection: 'column', alignItems: 'stretch' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            {icon('#3fb950', 'S')}
            <div style={{ flex: 1, minWidth: 140 }}>
              <div style={{ fontWeight: 700 }}>{T.spot}</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.spotDesc}</div>
            </div>
            <div style={{ ...mono, fontSize: 18, fontWeight: 700 }}>{M(fmtUsd(spotValue, 4))} <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>USDT</span></div>
            <a href="/spot" style={{ padding: '7px 14px', borderRadius: 8, background: 'var(--accent-primary,#c26a45)', color: '#fff', fontSize: 12.5, fontWeight: 600, textDecoration: 'none' }}>{T.trade}</a>
            {longs.length > 0 && (
              <button onClick={() => setSpotOpen(!spotOpen)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary,#8a8073)', fontSize: 12 }}>
                {T.viewCoins} {spotOpen ? '▾' : '▸'}
              </button>
            )}
          </div>
          {spotOpen && longs.map((p, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0 0 52px', fontSize: 13.5 }}>
              <span style={{ width: 24, height: 24, borderRadius: '50%', background: 'var(--card2,#f3efe7)', border: '1px solid var(--border,#d3c8b6)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>{p.symbol[0]}</span>
              <b>{p.symbol}</b>
              <span style={mono}>{M(fmtQty(p.quantity))}</span>
              <span style={{ ...mono, color: 'var(--text-secondary,#8a8073)' }}>≈ {M(fmtUsd(val(p)))} USDT</span>
              <span style={{ ...mono, color: pnlColor(p.pnl), marginLeft: 'auto' }}>{M(`${(p.pnl ?? 0) >= 0 ? '+' : ''}${fmtUsd(p.pnl ?? 0)}`)}</span>
            </div>
          ))}
        </div>

        <div style={{ ...walletCard, borderLeft: '3px solid #C9A227' }}>
          {icon('#C9A227', 'F')}
          <div style={{ flex: 1, minWidth: 140 }}>
            <div style={{ fontWeight: 700 }}>{T.futures}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.futuresDesc}</div>
          </div>
          <div style={{ ...mono, fontSize: 18, fontWeight: 700 }}>{M(fmtUsd(futValue, 4))} <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>USDT</span></div>
          <a href="/futures" style={{ padding: '7px 14px', borderRadius: 8, background: 'var(--accent-primary,#c26a45)', color: '#fff', fontSize: 12.5, fontWeight: 600, textDecoration: 'none' }}>{T.trade}</a>
        </div>
      </div>

      {/* Recent activity (ga: transactions panel) */}
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '0 0 10px' }}>{T.activity}</div>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {trades.length === 0 ? (
          <div style={{ padding: 18, color: 'var(--text-secondary,#8a8073)' }}>{T.noActivity}</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
            <thead>
              <tr style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 11.5, textTransform: 'uppercase' }}>
                <th style={{ textAlign: 'left', padding: '10px 16px' }}>{T.type}</th>
                <th style={{ textAlign: 'left', padding: '10px 8px' }}>Symbol</th>
                <th style={{ textAlign: 'right', padding: '10px 8px' }}>{T.amount}</th>
                <th style={{ textAlign: 'right', padding: '10px 8px' }}>{T.price}</th>
                <th style={{ textAlign: 'right', padding: '10px 16px' }}>{T.date}</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((s, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--border,#e6ddd0)' }}>
                  <td style={{ padding: '9px 16px' }}>
                    <span style={{ fontWeight: 700, fontSize: 12, textTransform: 'uppercase', color: (s.side === 'buy' || s.side === 'cover') ? '#3fb950' : '#f0663f' }}>{s.side}</span>
                    {s.signal_type === 'automation' && <span style={{ marginLeft: 6, fontSize: 10.5, color: 'var(--text-secondary,#8a8073)' }}>AI</span>}
                  </td>
                  <td style={{ padding: '9px 8px', fontWeight: 600 }}>{s.symbol}</td>
                  <td style={{ ...mono, padding: '9px 8px', textAlign: 'right' }}>{M(fmtQty(s.quantity))}</td>
                  <td style={{ ...mono, padding: '9px 8px', textAlign: 'right' }}>{M(fmtUsd(s.entry_price))}</td>
                  <td style={{ padding: '9px 16px', textAlign: 'right', color: 'var(--text-secondary,#8a8073)', fontSize: 12 }}>{String(s.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default AssetsPage
