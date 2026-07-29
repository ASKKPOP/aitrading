/**
 * The screen a member lands on after signing in.
 *
 * `/` used to render the leaderboard — a ranked list of other people. That is
 * a strange thing to show someone who just logged in, and it is also the page
 * that collapses to a single row once unowned and never-traded agents stop
 * being ranked. Ranking still lives at /leaderboard, where it is the question
 * actually being asked.
 *
 * This answers, in order: what is my money doing, what needs me, what did my
 * AI decide, and who am I copying. Every panel degrades to nothing rather than
 * inventing a number — a dashboard that lies once is never trusted again.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { Language, tr } from '../i18n'

type Position = {
  symbol: string; market: string; side: string
  quantity: number; entry_price: number; current_price?: number | null
  pnl?: number | null
}
type Trade = { pnl?: number | null; created_at?: string }
type FleetIndex = { base: number; value: number; pnl_pct: number } | null
type Fleet = { id: number; status: string; n_runs: number; index?: FleetIndex }
type Run = { id: number; symbol: string; market: string; status: string }
type Regime = {
  regime: string; reasons: string[]; size_multiplier: number
  fng_value?: number | null; vol_percentile?: number | null
  allow_new_buys: boolean; enforced?: boolean
}
type Psych = { fear_greed?: { value: number; classification: string; delta_3d?: number } }
type Leader = {
  leader_id: number; leader_name: string
  follower_count?: number; recent_trade_count_7d?: number
}

const T = {
  equity: { ko: '평가 자산', en: 'Equity', ja: '評価資産', th: 'มูลค่าพอร์ต', vi: 'Tài sản' },
  today: { ko: '오늘 손익', en: "Today's P&L", ja: '本日損益', th: 'กำไรวันนี้', vi: 'Lãi/lỗ hôm nay' },
  idx: { ko: 'N종목 지수', en: 'Sleeve index', ja: 'N銘柄指数', th: 'ดัชนีสลีฟ', vi: 'Chỉ số sleeve' },
  live: { ko: '가동 중', en: 'Running', ja: '稼働中', th: 'กำลังทำงาน', vi: 'Đang chạy' },
  desk: { ko: '지금 데스크의 판단', en: 'The desk right now', ja: 'デスクの判断', th: 'เดสก์ตอนนี้', vi: 'Bàn giao dịch lúc này' },
  live2: { ko: '실시간', en: 'live', ja: 'ライブ', th: 'สด', vi: 'trực tiếp' },
  size: { ko: '사이즈', en: 'size', ja: 'サイズ', th: 'ขนาด', vi: 'cỡ lệnh' },
  advisory: {
    ko: '이 구간 값은 검증 전 단계이며 현재 주문을 강제하지 않습니다.',
    en: 'These bands are unvalidated and do not currently force any order.',
    ja: 'この区間値は検証前で、注文を強制しません。',
    th: 'ช่วงค่านี้ยังไม่ผ่านการตรวจสอบและยังไม่บังคับคำสั่ง',
    vi: 'Các ngưỡng này chưa được kiểm chứng và hiện không ép buộc lệnh nào.' },
  holding: { ko: '보유 중', en: 'Open positions', ja: '保有中', th: 'ถือครองอยู่', vi: 'Đang nắm giữ' },
  none: { ko: '보유 중인 포지션이 없습니다', en: 'No open positions', ja: '保有ポジションなし', th: 'ไม่มีสถานะเปิด', vi: 'Không có vị thế mở' },
  copy: { ko: '복사 매매', en: 'Copy trading', ja: 'コピー取引', th: 'คัดลอกการเทรด', vi: 'Sao chép giao dịch' },
  copyNone: {
    ko: '아직 아무도 팔로우하지 않았습니다. 팔로우하면 그 트레이더의 매매가 내 모의 계좌에 그대로 복사됩니다.',
    en: 'Not following anyone yet. Following a trader mirrors their trades into your simulated account.',
    ja: 'まだ誰もフォローしていません。フォローすると、その取引が模擬口座に複製されます。',
    th: 'ยังไม่ได้ติดตามใคร เมื่อติดตาม การเทรดของเขาจะถูกคัดลอกเข้าบัญชีจำลองของคุณ',
    vi: 'Chưa theo dõi ai. Khi theo dõi, giao dịch của họ được sao chép vào tài khoản mô phỏng của bạn.' },
  find: { ko: '트레이더 찾기 →', en: 'Find traders →', ja: 'トレーダーを探す →', th: 'ค้นหาเทรดเดอร์ →', vi: 'Tìm trader →' },
  unfollow: { ko: '해제', en: 'Unfollow', ja: '解除', th: 'เลิกติดตาม', vi: 'Bỏ theo dõi' },
  followers: { ko: '팔로워', en: 'followers', ja: 'フォロワー', th: 'ผู้ติดตาม', vi: 'người theo dõi' },
  trades7: { ko: '7일 거래', en: '7d trades', ja: '7日取引', th: 'เทรด 7 วัน', vi: 'GD 7 ngày' },
  all: { ko: '전체 →', en: 'All →', ja: 'すべて →', th: 'ทั้งหมด →', vi: 'Tất cả →' },
  board: { ko: '리더보드 →', en: 'Leaderboard →', ja: 'リーダーボード →', th: 'ลีดเดอร์บอร์ด →', vi: 'Bảng xếp hạng →' },
  sim: {
    ko: '모의 원장 기준입니다. 복사된 매매도 모의 계좌에서 체결됩니다.',
    en: 'Simulated ledger. Copied trades also fill in your simulated account.',
    ja: '模擬台帳です。複製された取引も模擬口座で約定します。',
    th: 'บัญชีจำลอง การเทรดที่คัดลอกก็ทำรายการในบัญชีจำลองเช่นกัน',
    vi: 'Sổ mô phỏng. Giao dịch sao chép cũng khớp trong tài khoản mô phỏng.' },
}

const usd = (n: number) =>
  `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`

async function getJson(url: string, token: string | null) {
  try {
    const r = await fetch(url, token
      ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
    return r.ok ? await r.json() : null
  } catch { return null }
}

export default function DashboardPage({ token }: { token: string | null }) {
  const { language } = useLanguage()
  const t = (m: Record<Language, string>) => tr(language, m)

  const [positions, setPositions] = useState<Position[]>([])
  const [cash, setCash] = useState(0)
  const [realized, setRealized] = useState(0)
  const [fleet, setFleet] = useState<Fleet | null>(null)
  const [fleetIndex, setFleetIndex] = useState<FleetIndex>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [regime, setRegime] = useState<Regime | null>(null)
  const [psych, setPsych] = useState<Psych | null>(null)
  const [leaders, setLeaders] = useState<Leader[]>([])

  // Market context is public — fetched with or without a token so the panel is
  // never blank while auth is still settling.
  useEffect(() => {
    let dead = false
    const load = async () => {
      const [rg, ps] = await Promise.all([
        getJson(`${API_BASE}/market-intel/regime`, null),
        getJson(`${API_BASE}/market-intel/psych`, null),
      ])
      if (dead) return
      if (rg) setRegime(rg)
      if (ps) setPsych(ps)
    }
    load()
    const iv = setInterval(load, 60000)
    return () => { dead = true; clearInterval(iv) }
  }, [])

  useEffect(() => {
    if (!token) return
    let dead = false
    const load = async () => {
      const [pos, trades, fl, rs, following] = await Promise.all([
        getJson(`${API_BASE}/positions`, token),
        getJson(`${API_BASE}/positions/trades?limit=200`, token),
        getJson(`${API_BASE}/fleets`, token),
        getJson(`${API_BASE}/runs`, token),
        getJson(`${API_BASE}/signals/following`, token),
      ])
      if (dead) return
      if (pos) {
        setPositions((pos.positions || []).filter((p: Position) => Number(p.quantity) !== 0))
        setCash(Number(pos.cash) || 0)
      }
      if (trades) {
        const today = new Date().toISOString().slice(0, 10)
        setRealized((trades.trades || []).reduce(
          (s: number, x: Trade) => s + ((x.created_at || '').slice(0, 10) === today
            ? (Number(x.pnl) || 0) : 0), 0))
      }
      if (rs) setRuns((rs.runs || []).filter(
        (r: Run) => r.status === 'running' || r.status === 'armed'))
      if (following) setLeaders(following.following || following.leaders || [])
      // The list already carries `index` for every non-terminal fleet —
      // routes_fleets computes it inline specifically so callers do not pay a
      // second round trip per fleet. Do not re-fetch the detail for it.
      const active = (fl?.fleets || []).find(
        (f: Fleet) => f.status !== 'stopped' && f.status !== 'draft')
      setFleet(active || null)
      setFleetIndex(active?.index || null)
    }
    load()
    const iv = setInterval(load, 20000)
    return () => { dead = true; clearInterval(iv) }
  }, [token])

  const unfollow = async (leaderId: number) => {
    if (!token) return
    setLeaders(prev => prev.filter(l => l.leader_id !== leaderId))  // optimistic
    try {
      await fetch(`${API_BASE}/signals/unfollow`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ leader_id: leaderId }),
      })
    } catch { /* the next 20s poll restores truth */ }
  }

  const marketValue = positions.reduce(
    (s, p) => s + Math.abs(Number(p.quantity)) *
      (Number(p.current_price ?? p.entry_price) || 0), 0)
  const unrealized = positions.reduce((s, p) => s + (Number(p.pnl) || 0), 0)
  const equity = cash + marketValue
  const todayPnl = realized + unrealized

  const card: any = {
    background: 'var(--bg-card)', border: '1px solid var(--border-color)',
    borderRadius: 10, padding: '10px 12px',
  }
  const kSt: any = {
    fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase',
    color: 'var(--text-muted)', marginBottom: 3, whiteSpace: 'nowrap',
    overflow: 'hidden', textOverflow: 'ellipsis',
  }
  const vSt: any = {
    fontSize: 17, fontWeight: 800, fontVariantNumeric: 'tabular-nums',
    letterSpacing: '-.3px', whiteSpace: 'nowrap',
  }
  const sSt: any = { fontSize: 10.5, color: 'var(--text-muted)', marginTop: 1 }
  const h2: any = {
    fontSize: 10.5, letterSpacing: '.07em', textTransform: 'uppercase',
    color: 'var(--text-muted)', margin: '0 0 8px', fontWeight: 700,
    display: 'flex', alignItems: 'baseline', gap: 7,
  }
  const linkSt: any = {
    marginLeft: 'auto', color: 'var(--text-secondary)', fontSize: 10.5,
    textDecoration: 'none', textTransform: 'none', letterSpacing: 0,
  }
  const pos = (n: number) => n > 0 ? 'var(--success, #3fb27f)'
    : n < 0 ? 'var(--danger, #e0654a)' : 'var(--text-primary)'

  const fng = psych?.fear_greed

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '16px 14px 40px' }}>

      {/* my money first */}
      <div style={{
        display: 'grid', gap: 8, marginBottom: 16,
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
      }}>
        <Link to="/assets" style={{ ...card, textDecoration: 'none', color: 'inherit' }}>
          <div style={kSt}>{t(T.equity)}</div>
          <div style={vSt}>{usd(equity)}</div>
          <div style={sSt}>{usd(cash)} + {usd(marketValue)}</div>
        </Link>
        <div style={card}>
          <div style={kSt}>{t(T.today)}</div>
          <div style={{ ...vSt, color: pos(todayPnl) }}>
            {todayPnl >= 0 ? '+' : ''}{usd(todayPnl)}
          </div>
          <div style={sSt}>{usd(realized)} · {usd(unrealized)}</div>
        </div>
        <div style={card}>
          <div style={kSt}>{t(T.idx)}</div>
          <div style={{ ...vSt, color: fleetIndex ? pos(fleetIndex.pnl_pct) : undefined }}>
            {fleetIndex ? fleetIndex.value.toFixed(2) : '—'}
          </div>
          <div style={sSt}>
            {fleetIndex ? `${fleetIndex.pnl_pct >= 0 ? '+' : ''}${fleetIndex.pnl_pct.toFixed(2)}%` : '—'}
          </div>
        </div>
        <Link to="/automation" style={{ ...card, textDecoration: 'none', color: 'inherit' }}>
          <div style={kSt}>{t(T.live)}</div>
          <div style={vSt}>{runs.length}</div>
          <div style={sSt}>{fleet ? `${fleet.n_runs} 슬롯` : '—'}</div>
        </Link>
      </div>

      <div style={{
        display: 'grid', gap: 16,
        gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))',
      }}>
        <div>
          {/* the desk's read — public data, so it fills even before auth */}
          {regime && (
            <section style={{ marginBottom: 16 }}>
              <h2 style={h2}>{t(T.desk)}<em style={{
                fontStyle: 'normal', color: 'var(--accent-primary)',
                textTransform: 'none', letterSpacing: 0,
              }}>{t(T.live2)}</em></h2>
              <div style={card}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                  {fng && <span style={chip}>F&amp;G <b style={acc}>{fng.value}</b> {fng.classification}</span>}
                  <span style={chip}>{regime.regime}</span>
                  <span style={chip}>{t(T.size)} <b style={acc}>{regime.size_multiplier}×</b></span>
                </div>
                <p style={{ margin: 0, fontSize: 12.2, color: 'var(--text-secondary)' }}>
                  {(regime.reasons || []).join(' · ') || '—'}
                </p>
                {regime.enforced === false && (
                  <p style={{
                    fontSize: 10.8, color: 'var(--text-muted)', margin: '7px 0 0',
                    paddingTop: 7, borderTop: '1px solid var(--border-color)',
                  }}>⚠ {t(T.advisory)}</p>
                )}
              </div>
            </section>
          )}

          {/* copy trading — the real thing, not the localStorage bookmark */}
          <section>
            <h2 style={h2}>
              {t(T.copy)}
              {leaders.length > 0 && <em style={{ fontStyle: 'normal' }}>{leaders.length}</em>}
              <Link to="/leaderboard" style={linkSt}>{t(T.board)}</Link>
            </h2>
            {leaders.length === 0 ? (
              <div style={{
                border: '1px dashed var(--border-color)', borderRadius: 10,
                padding: '12px 14px', fontSize: 12.2, color: 'var(--text-muted)',
              }}>
                {t(T.copyNone)}
                <div style={{ marginTop: 8 }}>
                  <Link to="/leaderboard" style={{
                    color: 'var(--accent-primary)', fontSize: 12.2, textDecoration: 'none',
                  }}>{t(T.find)}</Link>
                </div>
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 6 }}>
                {leaders.map(l => (
                  <div key={l.leader_id} style={{
                    ...card, display: 'grid',
                    gridTemplateColumns: '1fr auto auto', gap: 9, alignItems: 'center',
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{
                        fontWeight: 700, fontSize: 12.3, whiteSpace: 'nowrap',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>{l.leader_name}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                        {l.follower_count ?? 0} {t(T.followers)} · {t(T.trades7)} {l.recent_trade_count_7d ?? 0}
                      </div>
                    </div>
                    <Link to={`/agent/${l.leader_id}`} style={{
                      fontSize: 10.5, color: 'var(--text-secondary)', textDecoration: 'none',
                    }}>→</Link>
                    <button onClick={() => unfollow(l.leader_id)} className="btn"
                      style={{ fontSize: 11, padding: '4px 9px' }}>{t(T.unfollow)}</button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <div>
          <section>
            <h2 style={h2}>
              {t(T.holding)}
              {positions.length > 0 && <em style={{ fontStyle: 'normal' }}>{positions.length}</em>}
              <Link to="/positions" style={linkSt}>{t(T.all)}</Link>
            </h2>
            {positions.length === 0 ? (
              <div style={{
                border: '1px dashed var(--border-color)', borderRadius: 10,
                padding: '12px 14px', fontSize: 12.2, color: 'var(--text-muted)',
              }}>{t(T.none)}</div>
            ) : (
              <div style={{ display: 'grid', gap: 6 }}>
                {positions.slice(0, 6).map((p, i) => (
                  <div key={`${p.market}:${p.symbol}:${i}`} style={{
                    ...card, display: 'grid',
                    gridTemplateColumns: '1fr auto', gap: 9, alignItems: 'center',
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: 12.3 }}>{p.symbol}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                        {p.market} · {p.side}
                      </div>
                    </div>
                    <div style={{
                      fontWeight: 800, fontVariantNumeric: 'tabular-nums',
                      fontSize: 12.8, whiteSpace: 'nowrap', color: pos(Number(p.pnl) || 0),
                    }}>
                      {(Number(p.pnl) || 0) >= 0 ? '+' : ''}{usd(Number(p.pnl) || 0)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <p style={{
            fontSize: 10.8, color: 'var(--text-muted)', margin: '16px 0 0',
          }}>{t(T.sim)}</p>
        </div>
      </div>
    </div>
  )
}

const chip: any = {
  background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)',
  borderRadius: 6, padding: '3px 8px', fontSize: 11.5, whiteSpace: 'nowrap',
}
const acc: any = { color: 'var(--accent-primary)' }
