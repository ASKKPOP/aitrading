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
import { LOCALE_BY_LANGUAGE, Language, fearGreedLabel, regimeLabel, sideLabel, tr } from '../i18n'

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

// GET /api/dashboard/desk — the four panels from the dashboard design.
type Attention = {
  run_id: number; symbol: string; market: string; kind: string
  streak: number; strikes: number; floor: number; at_rail: boolean
}
type Decision = {
  run_id: number; symbol: string; market: string; market_type?: string
  action: 'enter' | 'exit' | 'hold'; raw_action?: string | null
  reason?: string | null; confidence?: number | null
  conviction?: number | null; thesis_alignment?: number | null
  at: string
}
type Session = {
  market: string; bands: [number, number][]; open_now: boolean; open_hours: number
}
type Desk = {
  attention: Attention[]
  decisions: Decision[]
  sessions: { timezone: string; now_hour?: number; markets: Session[] }
  rank: {
    rank: number; of: number; name?: string; profit_percent: number
    trade_count: number; risk_adjusted_score: number
    max_drawdown?: number | null
  } | null
}

const T = {
  equity: { ko: '평가 자산', en: 'Equity', ja: '評価資産', th: 'มูลค่าพอร์ต', vi: 'Tài sản', id: 'Ekuitas' },
  today: { ko: '오늘 손익', en: "Today's P&L", ja: '本日損益', th: 'กำไรวันนี้', vi: 'Lãi/lỗ hôm nay', id: 'Laba rugi hari ini' },
  idx: { ko: 'N종목 지수', en: 'Sleeve index', ja: 'N銘柄指数', th: 'ดัชนีสลีฟ', vi: 'Chỉ số sleeve', id: 'Indeks sleeve' },
  live: { ko: '가동 중', en: 'Running', ja: '稼働中', th: 'กำลังทำงาน', vi: 'Đang chạy', id: 'Berjalan' },
  desk: { ko: '지금 데스크의 판단', en: 'The desk right now', ja: 'デスクの判断', th: 'เดสก์ตอนนี้', vi: 'Bàn giao dịch lúc này', id: 'Kondisi meja saat ini' },
  live2: { ko: '실시간', en: 'live', ja: 'ライブ', th: 'สด', vi: 'trực tiếp', id: 'live' },
  size: { ko: '사이즈', en: 'size', ja: 'サイズ', th: 'ขนาด', vi: 'cỡ lệnh', id: 'ukuran' },
  advisory: {
    ko: '이 구간 값은 검증 전 단계이며 현재 주문을 강제하지 않습니다.',
    en: 'These bands are unvalidated and do not currently force any order.',
    ja: 'この区間値は検証前で、注文を強制しません。',
    th: 'ช่วงค่านี้ยังไม่ผ่านการตรวจสอบและยังไม่บังคับคำสั่ง',
    vi: 'Các ngưỡng này chưa được kiểm chứng và hiện không ép buộc lệnh nào.',
    id: 'Rentang ini belum tervalidasi dan saat ini tidak memaksa order apa pun.' },
  holding: { ko: '보유 중', en: 'Open positions', ja: '保有中', th: 'ถือครองอยู่', vi: 'Đang nắm giữ', id: 'Posisi terbuka' },
  none: { ko: '보유 중인 포지션이 없습니다', en: 'No open positions', ja: '保有ポジションなし', th: 'ไม่มีสถานะเปิด', vi: 'Không có vị thế mở', id: 'Tidak ada posisi terbuka' },
  copy: { ko: '복사 매매', en: 'Copy trading', ja: 'コピー取引', th: 'คัดลอกการเทรด', vi: 'Sao chép giao dịch', id: 'Copy trading' },
  copyNone: {
    ko: '아직 아무도 팔로우하지 않았습니다. 팔로우하면 그 트레이더의 매매가 내 모의 계좌에 그대로 복사됩니다.',
    en: 'Not following anyone yet. Following a trader mirrors their trades into your simulated account.',
    ja: 'まだ誰もフォローしていません。フォローすると、その取引が模擬口座に複製されます。',
    th: 'ยังไม่ได้ติดตามใคร เมื่อติดตาม การเทรดของเขาจะถูกคัดลอกเข้าบัญชีจำลองของคุณ',
    vi: 'Chưa theo dõi ai. Khi theo dõi, giao dịch của họ được sao chép vào tài khoản mô phỏng của bạn.',
    id: 'Belum mengikuti siapa pun. Mengikuti seorang trader akan menyalin transaksi mereka ke akun simulasi Anda.' },
  find: { ko: '트레이더 찾기 →', en: 'Find traders →', ja: 'トレーダーを探す →', th: 'ค้นหาเทรดเดอร์ →', vi: 'Tìm trader →', id: 'Cari trader →' },
  unfollow: { ko: '해제', en: 'Unfollow', ja: '解除', th: 'เลิกติดตาม', vi: 'Bỏ theo dõi', id: 'Berhenti mengikuti' },
  followers: { ko: '팔로워', en: 'followers', ja: 'フォロワー', th: 'ผู้ติดตาม', vi: 'người theo dõi', id: 'pengikut' },
  trades7: { ko: '7일 거래', en: '7d trades', ja: '7日取引', th: 'เทรด 7 วัน', vi: 'GD 7 ngày', id: 'transaksi 7 hari' },
  all: { ko: '전체 →', en: 'All →', ja: 'すべて →', th: 'ทั้งหมด →', vi: 'Tất cả →', id: 'Semua →' },
  board: { ko: '리더보드 →', en: 'Leaderboard →', ja: 'リーダーボード →', th: 'ลีดเดอร์บอร์ด →', vi: 'Bảng xếp hạng →', id: 'Papan peringkat →' },
  sim: {
    ko: '모의 원장 기준입니다. 복사된 매매도 모의 계좌에서 체결됩니다.',
    en: 'Simulated ledger. Copied trades also fill in your simulated account.',
    ja: '模擬台帳です。複製された取引も模擬口座で約定します。',
    th: 'บัญชีจำลอง การเทรดที่คัดลอกก็ทำรายการในบัญชีจำลองเช่นกัน',
    vi: 'Sổ mô phỏng. Giao dịch sao chép cũng khớp trong tài khoản mô phỏng.',
    id: 'Buku simulasi. Transaksi yang disalin juga tereksekusi di akun simulasi Anda.' },

  // ── 확인이 필요합니다 ──
  attention: { ko: '확인이 필요합니다', en: 'Needs a look', ja: '確認が必要です', th: 'ต้องตรวจสอบ', vi: 'Cần xem lại', id: 'Perlu diperiksa' },
  decayTitle: {
    ko: '{sym} — 논제가 식고 있습니다', en: '{sym} — the thesis is cooling',
    ja: '{sym} — 論拠が弱まっています', th: '{sym} — สมมติฐานกำลังอ่อนลง',
    vi: '{sym} — luận điểm đang yếu đi', id: '{sym} — tesisnya melemah' },
  decayBody: {
    ko: '데스크가 {n}회 연속 정합도 {floor} 이하로 평가했습니다. 슬롯 반납 후 교체를 검토하세요.',
    en: 'The desk scored its own thesis at or below {floor} for {n} cycles running. Consider handing the slot back.',
    ja: 'デスクが{n}回連続で整合度{floor}以下と評価しました。スロットの返却と入れ替えをご検討ください。',
    th: 'เดสก์ให้คะแนนสมมติฐานของตัวเองที่ {floor} หรือต่ำกว่า ติดต่อกัน {n} รอบ ควรพิจารณาคืนสล็อต',
    vi: 'Bàn giao dịch đã tự chấm luận điểm ở mức {floor} trở xuống trong {n} chu kỳ liên tiếp. Cân nhắc trả lại slot.',
    id: 'Meja menilai tesisnya sendiri di {floor} atau lebih rendah selama {n} siklus berturut-turut. Pertimbangkan mengembalikan slot.' },
  view: { ko: '보기', en: 'View', ja: '表示', th: 'ดู', vi: 'Xem', id: 'Lihat' },

  // ── 내 AI가 한 일 ──
  didWhat: { ko: '내 AI가 한 일', en: 'What my AI did', ja: 'AIがしたこと', th: 'สิ่งที่ AI ของฉันทำ', vi: 'AI của tôi đã làm gì', id: 'Yang dilakukan AI saya' },
  recentN: { ko: '최근 3건', en: 'last 3', ja: '直近3件', th: '3 รายการล่าสุด', vi: '3 gần nhất', id: '3 terakhir' },
  noDecisions: {
    ko: '아직 판단 기록이 없습니다. TRADING을 시작하면 이유와 함께 여기에 쌓입니다.',
    en: 'No decisions yet. Start a TRADING and they land here, reason included.',
    ja: 'まだ判断の記録がありません。TRADINGを開始すると理由付きでここに残ります。',
    th: 'ยังไม่มีบันทึกการตัดสินใจ เริ่ม TRADING แล้วจะปรากฏที่นี่พร้อมเหตุผล',
    vi: 'Chưa có quyết định nào. Bắt đầu một TRADING và chúng sẽ xuất hiện ở đây kèm lý do.',
    id: 'Belum ada keputusan. Mulai TRADING dan semuanya muncul di sini beserta alasannya.' },
  actEnter: { ko: '진입', en: 'Enter', ja: 'エントリー', th: 'เข้า', vi: 'Vào lệnh', id: 'Masuk' },
  actExit: { ko: '청산', en: 'Exit', ja: '手仕舞い', th: 'ปิด', vi: 'Thoát', id: 'Keluar' },
  actHold: { ko: '보유', en: 'Hold', ja: '保有', th: 'ถือ', vi: 'Giữ', id: 'Tahan' },
  align: { ko: '정합도', en: 'alignment', ja: '整合度', th: 'ความสอดคล้อง', vi: 'độ khớp', id: 'keselarasan' },
  conf: { ko: '확신도', en: 'confidence', ja: '確信度', th: 'ความมั่นใจ', vi: 'độ tin cậy', id: 'keyakinan' },

  // ── 내 시각 기준 개장 ──
  sessions: { ko: '내 시각 기준 개장', en: 'Open, on your clock', ja: 'あなたの時刻での開場', th: 'เวลาเปิดตามเวลาของคุณ', vi: 'Giờ mở theo giờ của bạn', id: 'Jam buka menurut waktu Anda' },
  allDay: { ko: '24시간', en: '24h', ja: '24時間', th: '24 ชม.', vi: '24 giờ', id: '24 jam' },
  weekdays: { ko: '24×5', en: '24×5', ja: '24×5', th: '24×5', vi: '24×5', id: '24×5' },
  nearlyAllDay: { ko: '거의 종일', en: 'nearly all day', ja: 'ほぼ終日', th: 'เกือบทั้งวัน', vi: 'gần cả ngày', id: 'hampir sepanjang hari' },
  closedToday: { ko: '오늘 휴장', en: 'closed today', ja: '本日休場', th: 'วันนี้ปิด', vi: 'hôm nay nghỉ', id: 'tutup hari ini' },
  opensAt: { ko: '{t} 개장', en: 'opens {t}', ja: '{t} 開場', th: 'เปิด {t}', vi: 'mở {t}', id: 'buka {t}' },

  // ── 내 순위 ──
  myRank: { ko: '내 순위', en: 'My rank', ja: '自分の順位', th: 'อันดับของฉัน', vi: 'Hạng của tôi', id: 'Peringkat saya' },
  trades: { ko: '거래', en: 'trades', ja: '取引', th: 'เทรด', vi: 'giao dịch', id: 'transaksi' },
  maxDd: { ko: '최대낙폭', en: 'max drawdown', ja: '最大ドローダウン', th: 'ดรอว์ดาวน์สูงสุด', vi: 'sụt giảm tối đa', id: 'penurunan maks' },
  unranked: {
    ko: '아직 순위에 오르지 않았습니다. 운영 신호를 한 건이라도 게시하면 순위에 포함됩니다 — 0건을 0%로 줄세우지 않기 위해서입니다.',
    en: 'Not on the board yet. Publish one operation signal and you are ranked — a record of nothing is not a record.',
    ja: 'まだランキングに載っていません。運用シグナルを1件でも公開すると対象になります — 0件を0%として並べないためです。',
    th: 'ยังไม่ติดอันดับ เผยแพร่สัญญาณการดำเนินงานสักรายการแล้วคุณจะถูกจัดอันดับ — เพราะการไม่มีสถิติไม่ใช่สถิติ',
    vi: 'Chưa lên bảng. Hãy đăng một tín hiệu vận hành và bạn sẽ được xếp hạng — không có lịch sử thì không phải là thành tích.',
    id: 'Belum masuk papan peringkat. Terbitkan satu sinyal operasi dan Anda akan diperingkat — nol transaksi bukanlah rekam jejak.' },
}

const MARKET_LABEL: Record<string, Record<Language, string>> = {
  crypto: { ko: '크립토', en: 'Crypto', ja: '暗号資産', th: 'คริปโต', vi: 'Tiền mã hóa', id: 'Kripto' },
  forex: { ko: '외환', en: 'Forex', ja: '外国為替', th: 'ฟอเร็กซ์', vi: 'Ngoại hối', id: 'Forex' },
  futures: { ko: '선물', en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Hợp đồng tương lai', id: 'Futures' },
  'us-stock': { ko: '미국 주식', en: 'US stocks', ja: '米国株', th: 'หุ้นสหรัฐฯ', vi: 'Cổ phiếu Mỹ', id: 'Saham AS' },
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
  const [desk, setDesk] = useState<Desk | null>(null)

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
      const [pos, trades, fl, rs, following, dk] = await Promise.all([
        getJson(`${API_BASE}/positions`, token),
        getJson(`${API_BASE}/positions/trades?limit=200`, token),
        getJson(`${API_BASE}/fleets`, token),
        getJson(`${API_BASE}/runs`, token),
        getJson(`${API_BASE}/signals/following`, token),
        getJson(`${API_BASE}/dashboard/desk`, token),
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
      if (dk) setDesk(dk)
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

  const fill = (m: Record<Language, string>, vals: Record<string, string | number>) =>
    Object.entries(vals).reduce(
      (s, [k, v]) => s.replace(`{${k}}`, String(v)), t(m))
  const mkt = (m: string) => MARKET_LABEL[m] ? t(MARKET_LABEL[m]) : m
  const side = (s: string) => sideLabel(language, s)
  const hhmm = (h: number) =>
    `${String(Math.floor(h) % 24).padStart(2, '0')}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`

  /** The right-hand summary for one market's day, in words rather than bands. */
  const sessionSummary = (s: Session): string => {
    if (s.open_hours >= 23.9) return t(T.allDay)
    if (s.open_hours <= 0) return t(T.closedToday)
    if (s.open_hours >= 20) return t(T.nearlyAllDay)
    // Two or fewer windows read better as their start times than as a total.
    if (s.bands.length <= 2 && s.bands.length > 0 && s.open_hours < 12) {
      const opens = s.bands.filter(b => b[0] > 0).map(b => hhmm(b[0]))
      if (opens.length === 1) return fill(T.opensAt, { t: opens[0] })
      if (opens.length === 2) return opens.join('·')
    }
    return s.bands.map(b => hhmm(b[0])).join('·')
  }

  const actionLabel = (a: Decision['action']) =>
    a === 'enter' ? t(T.actEnter) : a === 'exit' ? t(T.actExit) : t(T.actHold)
  const actionColor = (a: Decision['action']) =>
    a === 'enter' ? 'var(--success, #3fb27f)'
      : a === 'exit' ? 'var(--accent-primary)' : 'var(--text-muted)'

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
          {/* 확인이 필요합니다 — the desk marking down its OWN thesis. The
              automatic hand-back rail is default-off, so this card is the
              only place the shadow read surfaces where a member can act. */}
          {(desk?.attention?.length ?? 0) > 0 && (
            <section style={{ marginBottom: 16 }}>
              <h2 style={h2}>
                <span style={{
                  width: 6, height: 6, borderRadius: 999,
                  background: 'var(--warning, #d8a13a)', display: 'inline-block',
                }} />
                {t(T.attention)}
              </h2>
              <div style={{ display: 'grid', gap: 6 }}>
                {desk!.attention.map(a => (
                  <div key={a.run_id} style={{
                    ...card, borderColor: 'var(--warning, #d8a13a)',
                    display: 'grid', gridTemplateColumns: '1fr auto',
                    gap: 10, alignItems: 'center',
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: 12.4 }}>
                        {fill(T.decayTitle, { sym: a.symbol })}
                      </div>
                      <p style={{
                        margin: '3px 0 0', fontSize: 11.4,
                        color: 'var(--text-secondary)', lineHeight: 1.5,
                      }}>
                        {fill(T.decayBody, { n: a.streak, floor: a.floor })}
                      </p>
                    </div>
                    <Link to={`/runs?run=${a.run_id}`} style={{
                      ...chip, textDecoration: 'none', color: 'var(--text-primary)',
                    }}>{t(T.view)}</Link>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 내 AI가 한 일 — the decision AND the reason. Without the reason
              this is just a trade log, which the Positions page already is. */}
          <section style={{ marginBottom: 16 }}>
            <h2 style={h2}>
              {t(T.didWhat)}
              <em style={{ fontStyle: 'normal' }}>{t(T.recentN)}</em>
              <Link to="/runs" style={linkSt}>{t(T.all)}</Link>
            </h2>
            {(desk?.decisions?.length ?? 0) === 0 ? (
              <div style={{
                border: '1px dashed var(--border-color)', borderRadius: 10,
                padding: '12px 14px', fontSize: 12.2, color: 'var(--text-muted)',
                lineHeight: 1.6,
              }}>{t(T.noDecisions)}</div>
            ) : (
              <div style={{ display: 'grid', gap: 6 }}>
                {desk!.decisions.map((d, i) => (
                  <div key={`${d.run_id}:${d.at}:${i}`} style={{
                    ...card, borderLeft: `2px solid ${actionColor(d.action)}`,
                  }}>
                    <div style={{
                      display: 'flex', gap: 7, alignItems: 'baseline',
                      flexWrap: 'wrap',
                    }}>
                      <span style={{ fontWeight: 700, fontSize: 12.4 }}>{d.symbol}</span>
                      <span style={{ fontSize: 10.6, color: 'var(--text-muted)' }}>
                        {mkt(d.market)}
                      </span>
                      <span style={{
                        marginLeft: 'auto', fontSize: 11, fontWeight: 700,
                        color: actionColor(d.action),
                      }}>{actionLabel(d.action)}</span>
                    </div>
                    {d.reason && (
                      <p style={{
                        margin: '4px 0 0', fontSize: 11.6, lineHeight: 1.55,
                        color: 'var(--text-secondary)',
                      }}>{d.reason}</p>
                    )}
                    <div style={{
                      marginTop: 5, fontSize: 10.4, color: 'var(--text-muted)',
                      fontVariantNumeric: 'tabular-nums',
                    }}>
                      {new Date(d.at).toLocaleTimeString(LOCALE_BY_LANGUAGE[language], {
                        hour: '2-digit', minute: '2-digit',
                      })}
                      {d.thesis_alignment != null &&
                        ` · ${t(T.align)} ${Number(d.thesis_alignment).toFixed(2)}`}
                      {d.confidence != null &&
                        ` · ${t(T.conf)} ${Number(d.confidence).toFixed(2)}`}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* the desk's read — public data, so it fills even before auth */}
          {regime && (
            <section style={{ marginBottom: 16 }}>
              <h2 style={h2}>{t(T.desk)}<em style={{
                fontStyle: 'normal', color: 'var(--accent-primary)',
                textTransform: 'none', letterSpacing: 0,
              }}>{t(T.live2)}</em></h2>
              <div style={card}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                  {/* The design reads this as a chain, not a row of tags:
                      the sentiment number PRODUCES the band, which produces
                      the stance, which produces the size. Arrows are what
                      make it a derivation a member can follow. */}
                  {fng && <>
                    <span style={chip}>F&amp;G <b style={acc}>{fng.value}</b></span>
                    <span style={arrow}>→</span>
                    <span style={chip}>{fearGreedLabel(language, fng.classification)}</span>
                    <span style={arrow}>→</span>
                  </>}
                  <span style={chip}>{regimeLabel(language, regime.regime)}</span>
                  <span style={arrow}>→</span>
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
                        {mkt(p.market)} · {side(p.side)}
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

          {/* 내 시각 기준 개장 — every band is computed from the same
              markets.is_market_open() the engine trades on, in the member's
              own timezone, so this cannot drift from what actually fills. */}
          {(desk?.sessions?.markets?.length ?? 0) > 0 && (
            <section style={{ marginTop: 16 }}>
              <h2 style={h2}>
                {t(T.sessions)}
                <em style={{
                  fontStyle: 'normal', color: 'var(--accent-primary)',
                  textTransform: 'none', letterSpacing: 0,
                }}>{(desk!.sessions.timezone || '').split('/').pop()?.replace(/_/g, ' ')}</em>
              </h2>
              <div style={{ ...card, display: 'grid', gap: 7 }}>
                {desk!.sessions.markets.map(s => (
                  <div key={s.market} style={{
                    display: 'grid', gridTemplateColumns: 'minmax(58px, max-content) 1fr auto',
                    gap: 8, alignItems: 'center',
                  }}>
                    <div style={{
                      fontSize: 10.8, color: 'var(--text-secondary)',
                      whiteSpace: 'nowrap',
                    }}>{mkt(s.market)}</div>
                    {/* 24h track; each band is positioned as a % of the day */}
                    <div style={{
                      position: 'relative', height: 6, borderRadius: 999,
                      background: 'var(--bg-tertiary)', overflow: 'hidden',
                    }}>
                      {s.bands.map((b, i) => (
                        <div key={i} style={{
                          position: 'absolute', top: 0, bottom: 0,
                          left: `${(b[0] / 24) * 100}%`,
                          width: `${((b[1] - b[0]) / 24) * 100}%`,
                          background: s.open_now
                            ? 'var(--success, #3fb27f)' : 'var(--text-muted)',
                          opacity: s.open_now ? 1 : 0.55,
                        }} />
                      ))}
                      {desk!.sessions.now_hour != null && (
                        <div style={{
                          position: 'absolute', top: -2, bottom: -2,
                          left: `${(desk!.sessions.now_hour / 24) * 100}%`,
                          width: 1.5, background: 'var(--accent-primary)',
                        }} />
                      )}
                    </div>
                    <div style={{
                      fontSize: 10.4, color: 'var(--text-muted)',
                      whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums',
                    }}>{sessionSummary(s)}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 내 순위 — my own standing, not other people's. `null` is a real
              answer: an agent with no published operation is unranked by the
              board's own rule, and inventing a position for it would be the
              "rank nothing at 0%" problem that rule exists to prevent. */}
          <section style={{ marginTop: 16 }}>
            <h2 style={h2}>
              {t(T.myRank)}
              <Link to="/leaderboard" style={linkSt}>{t(T.board)}</Link>
            </h2>
            {desk?.rank ? (
              <div style={{
                ...card, display: 'grid',
                gridTemplateColumns: '1fr auto auto', gap: 10, alignItems: 'center',
              }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 12.4 }}>
                    #{desk.rank.rank} · {desk.rank.name}
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                    {desk.rank.trade_count} {t(T.trades)}
                    {desk.rank.max_drawdown != null &&
                      ` · ${t(T.maxDd)} ${(Number(desk.rank.max_drawdown) * 100).toFixed(1)}%`}
                  </div>
                </div>
                <div style={{
                  fontWeight: 800, fontSize: 13, fontVariantNumeric: 'tabular-nums',
                  color: pos(desk.rank.profit_percent),
                }}>
                  {desk.rank.profit_percent >= 0 ? '+' : ''}
                  {desk.rank.profit_percent.toFixed(2)}%
                </div>
                <div style={{
                  fontSize: 9.5, color: 'var(--text-muted)', textAlign: 'right',
                  lineHeight: 1.35, letterSpacing: '.04em',
                }}>
                  SHARPE<br />
                  <b style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
                    {desk.rank.risk_adjusted_score.toFixed(2)}
                  </b>
                </div>
              </div>
            ) : (
              <div style={{
                border: '1px dashed var(--border-color)', borderRadius: 10,
                padding: '12px 14px', fontSize: 11.8, color: 'var(--text-muted)',
                lineHeight: 1.6,
              }}>{t(T.unranked)}</div>
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
const arrow: any = {
  color: 'var(--text-muted)', fontSize: 11, alignSelf: 'center', opacity: .8,
}
