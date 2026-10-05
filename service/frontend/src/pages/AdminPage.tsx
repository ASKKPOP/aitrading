import { Fragment, useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { API_BASE, useLanguage } from '../appShared'
import { LANGUAGES, tr } from '../i18n'

// Manager console — served on administr.sooppiy.com (App.tsx hostname gate).
// Admins sign in with email + password (admin_users, routes_admin_auth.py);
// the 12h session token lives in localStorage. Tabs cover the full operator
// surface: analytics dashboard, members, paid subscriptions, asset/position/
// automation statistics, discussion moderation, leaderboard management,
// admin accounts (superadmin only) and the audit trail.
const ADMIN_TOKEN_KEY = 'sooppiy_admin_token'

type Tab =
  | 'dashboard' | 'members' | 'subscriptions' | 'assets' | 'positions'
  | 'automation' | 'feeds' | 'crawl' | 'skills' | 'support' | 'discussions' | 'leaderboard' | 'admins' | 'audit'

// Prompt sites a trading skill can ride (mirror of trading_skills.PROMPT_SITES).
const SKILL_SITES = ['light', 'trader', 'verifier', 'planner'] as const
const SKILL_BODY_MAX = 4000

const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 12, padding: '16px 18px' }
const tableCard: any = { ...card, padding: 0, overflowX: 'auto' }
const th: any = { textAlign: 'left', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted,#8a8073)', padding: '8px 10px', borderBottom: '1px solid var(--border-color,#2a2a28)', whiteSpace: 'nowrap' }
const td: any = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-color,#2a2a28)' }
const chip = (active: boolean): any => ({ padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 13, fontWeight: active ? 700 : 500, border: active ? '1.5px solid var(--accent-primary,#d8a95e)' : '1px solid var(--border-color,#332d22)', background: active ? 'rgba(216,169,94,0.14)' : 'transparent', color: active ? 'var(--accent-primary,#d8a95e)' : 'inherit' })
const dangerBtn: any = { padding: '4px 10px', borderRadius: 6, border: '1px solid #7f1d1d', background: 'transparent', color: '#ef4444', cursor: 'pointer', fontSize: 12 }
const actionBtn: any = { padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border-color,#2a2a28)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }
const primaryBtn: any = { padding: '8px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 }
const inputStyle: any = { padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-secondary,#161615)', color: 'var(--text-primary,#fff)', fontSize: 13 }
const sectionTitle: any = { fontSize: 14, fontWeight: 700, margin: '18px 0 10px' }

const fmtMoney = (v: any) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
const fmtTime = (v: any) => String(v || '—').replace('T', ' ').slice(0, 16)
const fmtDate = (v: any) => String(v || '—').slice(0, 10)

// Block explorer for a USDT payment's tx hash, so verifying a pending payment
// is one click from the row instead of a copy-paste into a search box.
// The network comes from the CURRENT usdt_network setting — rows are not
// stamped with the network they were paid on, so if the receiving network is
// ever rotated, links on older rows point at the wrong chain and will simply
// not resolve. That fails safe (a missing tx, never a false match), but verify
// by hand if you have rotated networks since the payment.
const EXPLORER_TX: Record<string, string> = {
  ERC20: 'https://etherscan.io/tx/',
  TRC20: 'https://tronscan.org/#/transaction/',
  BEP20: 'https://bscscan.com/tx/',
  SOL: 'https://solscan.io/tx/',
  POLYGON: 'https://polygonscan.com/tx/',
}
const explorerUrl = (method: string, network: string, reference: string) =>
  method === 'usdt' && EXPLORER_TX[network] && reference
    ? EXPLORER_TX[network] + encodeURIComponent(reference.trim())
    : ''

function StatCards({ items }: { items: [string, any][] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 12, marginBottom: 16 }}>
      {items.map(([label, value]) => (
        <div key={label} style={card}>
          <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{String(value)}</div>
        </div>
      ))}
    </div>
  )
}

function TrendChart({ data, xKey, series, kind }: { data: any[]; xKey: string; series: [string, string][]; kind?: 'line' | 'bar' }) {
  if (!data?.length) return <div style={{ ...card, color: 'var(--text-muted,#8a8073)', fontSize: 13 }}>—</div>
  return (
    <div style={{ ...card, height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        {kind === 'bar' ? (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color,#2a2a28)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={54} />
            <Tooltip contentStyle={{ background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', fontSize: 12 }} />
            {series.map(([key, color]) => <Bar key={key} dataKey={key} fill={color} />)}
          </BarChart>
        ) : (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color,#2a2a28)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={54} />
            <Tooltip contentStyle={{ background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', fontSize: 12 }} />
            {series.map(([key, color]) => <Line key={key} type="monotone" dataKey={key} stroke={color} dot={false} strokeWidth={2} />)}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

// Live status colours for a pipeline node. `idle` is grey, never green — a
// feed that has never run has proven nothing.
const NODE_COLORS: Record<string, string> = {
  ok: '#22c55e', failing: '#ef4444', stale: '#eab308', idle: '#6b7280',
  // a switched-off collector ran cleanly and produced nothing — not health
  disabled: '#6b7280',
}
const nodeColor = (status: string) => NODE_COLORS[status] || NODE_COLORS.idle

// The blueprint's pipeline (collect -> score -> combine -> decide), drawn with
// live health on every node. Purely presentational: every value comes from
// /api/admin/crawl/overview.
function PipelineDiagram({ overview, onPick }: { overview: any; onPick: (feed: string) => void }) {
  const collect: any[] = overview?.collect || []
  const score: any[] = overview?.score || []
  if (!collect.length) return null

  const ROW = 46, TOP = 26, BOX_H = 34
  const cx1 = 8, cw = 232                    // collect column
  const px1 = 322, pw = 210                  // processor column
  const height = Math.max(collect.length, score.length) * ROW + TOP + 30
  const collectY = (i: number) => TOP + i * ROW
  const scoreSpan = height - TOP - 40
  const scoreY = (i: number) => TOP + 6 + (scoreSpan / score.length) * i
  const procIndex: Record<string, number> = {}
  score.forEach((s, i) => { procIndex[s.key] = i })

  const midY = height / 2 - 20
  const compX = 596, compW = 150
  const decX = 792, decW = 176

  const link = (x1: number, y1: number, x2: number, y2: number) =>
    `M ${x1} ${y1} C ${x1 + 44} ${y1}, ${x2 - 44} ${y2}, ${x2} ${y2}`

  const muted = 'var(--text-muted,#8a8073)'
  const border = 'var(--border-color,#2a2a28)'
  const text = 'var(--text-primary,#ece7dd)'

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 990 ${height}`} style={{ width: '100%', minWidth: 860, height: 'auto' }}
           role="img" aria-label="Swing signal stack pipeline status">
        {/* collect -> processor links */}
        {collect.map((c, i) => {
          const target = c.feeds === 'risk_gate' ? null : procIndex[c.feeds]
          const y1 = collectY(i) + BOX_H / 2
          const y2 = target != null ? scoreY(target) + BOX_H / 2 : midY + 96
          const x2 = target != null ? px1 : decX
          return (
            <path key={`l-${c.key}`} d={link(cx1 + cw, y1, x2, y2)} fill="none"
                  stroke={c.wired ? nodeColor(c.status) : muted}
                  strokeWidth={c.wired ? 1.6 : 1}
                  strokeDasharray={c.wired ? undefined : '4 4'}
                  opacity={c.wired ? 0.75 : 0.45} />
          )
        })}
        {/* processor -> composite links */}
        {score.map((s, i) => (
          <path key={`c-${s.key}`} d={link(px1 + pw, scoreY(i) + BOX_H / 2, compX, midY + 22)}
                fill="none" stroke={muted} strokeWidth={1.4} opacity={0.6} />
        ))}
        <path d={link(compX + compW, midY + 22, decX, midY - 26)} fill="none"
              stroke="var(--accent-primary,#d8a95e)" strokeWidth={1.8} opacity={0.8} />
        <path d={link(compX + compW, midY + 22, decX, midY + 96)} fill="none"
              stroke={muted} strokeWidth={1.4} opacity={0.5} strokeDasharray="4 4" />

        {/* collect nodes */}
        {collect.map((c, i) => (
          <g key={c.key} onClick={() => onPick(c.key)} style={{ cursor: 'pointer' }}>
            <rect x={cx1} y={collectY(i)} width={cw} height={BOX_H} rx={8}
                  fill="var(--bg-secondary,#161615)" stroke={nodeColor(c.status)} strokeWidth={1.4} />
            <circle cx={cx1 + 15} cy={collectY(i) + BOX_H / 2} r={4.5} fill={nodeColor(c.status)} />
            <text x={cx1 + 27} y={collectY(i) + 15} fontSize={11.5} fontWeight={600} fill={text}>
              {`${c.doc_feed} · ${c.label}`.slice(0, 30)}
            </text>
            <text x={cx1 + 27} y={collectY(i) + 27} fontSize={9.5} fill={muted}>
              {c.status === 'idle' ? 'never run'
                : c.status === 'disabled' ? 'disabled — produces nothing'
                : `${c.status}${c.last_items != null ? ` · ${c.last_items} items` : ''}`}
              {c.wired ? '' : ' · not wired'}
            </text>
          </g>
        ))}

        {/* processor nodes */}
        {score.map((s, i) => (
          <g key={s.key}>
            <rect x={px1} y={scoreY(i)} width={pw} height={BOX_H} rx={8}
                  fill="var(--bg-secondary,#161615)" stroke={border} strokeWidth={1.2} />
            <text x={px1 + 12} y={scoreY(i) + 15} fontSize={11.5} fontWeight={600} fill={text}>
              {`${s.key} · w ${s.weight.toFixed(2)}`}
            </text>
            <text x={px1 + 12} y={scoreY(i) + 27} fontSize={9.5} fill={muted}>
              {s.symbols
                ? `${s.covered_symbols}/${s.symbols} covered${s.mean_score != null ? ` · mean ${s.mean_score}` : ''}`
                : 'no decisions yet'}
            </text>
          </g>
        ))}

        {/* composite */}
        <rect x={compX} y={midY - 4} width={compW} height={52} rx={9}
              fill="var(--bg-secondary,#161615)" stroke="var(--accent-primary,#d8a95e)" strokeWidth={1.6} />
        <text x={compX + 14} y={midY + 16} fontSize={12} fontWeight={700} fill="var(--accent-primary,#d8a95e)">composite</text>
        <text x={compX + 14} y={midY + 33} fontSize={10} fill={muted}>
          {overview?.combine?.mean_composite != null
            ? `mean ${overview.combine.mean_composite} · ${overview.combine.symbols_scored} sym`
            : '−100 … +100'}
        </text>

        {/* decide */}
        <rect x={decX} y={midY - 60} width={decW} height={74} rx={9}
              fill="var(--bg-secondary,#161615)" stroke={border} strokeWidth={1.2} />
        <text x={decX + 12} y={midY - 42} fontSize={10.5} fill={text}>
          {`≥ +${overview?.decide?.buy_threshold ?? 40} → BUY (${overview?.decide?.actions?.BUY || 0})`}
        </text>
        <text x={decX + 12} y={midY - 26} fontSize={10.5} fill={text}>
          {`between → WAIT (${overview?.decide?.actions?.WAIT || 0})`}
        </text>
        <text x={decX + 12} y={midY - 10} fontSize={10.5} fill={text}>
          {`≤ ${overview?.decide?.sell_threshold ?? -40} → SELL (${overview?.decide?.actions?.SELL || 0})`}
        </text>

        {/* risk gate */}
        <rect x={decX} y={midY + 70} width={decW} height={52} rx={9}
              fill="var(--bg-secondary,#161615)" stroke={border} strokeWidth={1.2} strokeDasharray="5 4" />
        <text x={decX + 12} y={midY + 90} fontSize={11} fontWeight={600} fill={text}>risk gate (veto)</text>
        <text x={decX + 12} y={midY + 106} fontSize={9.5} fill={muted}>
          {`event blackout ${overview?.decide?.event_blackout_hours ?? 24}h · vetoed ${overview?.decide?.vetoed || 0}`}
        </text>
      </svg>
    </div>
  )
}

export function AdminPage() {
  const { language } = useLanguage()
  const [token, setToken] = useState<string>(() => localStorage.getItem(ADMIN_TOKEN_KEY) || '')
  const [me, setMe] = useState<any | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tab, setTab] = useState<Tab>('dashboard')
  const [error, setError] = useState('')
  // One shared in-flight flag for the ~35 act() buttons: while a write is
  // running a floating chip shows, and when it fails the same chip carries
  // the error — the top banner alone sat off-screen for buttons below the
  // fold, so failures looked like dead clicks.
  const [actBusy, setActBusy] = useState(false)
  const [loggingIn, setLoggingIn] = useState(false)

  const [analytics, setAnalytics] = useState<any | null>(null)
  const [overview, setOverview] = useState<any | null>(null)
  const [users, setUsers] = useState<any | null>(null)
  const [agents, setAgents] = useState<any | null>(null)
  const [memberDetail, setMemberDetail] = useState<any | null>(null)
  const [subs, setSubs] = useState<any | null>(null)
  const [subFilter, setSubFilter] = useState('')
  const [copiedRef, setCopiedRef] = useState<number | null>(null)
  const [paySettings, setPaySettings] = useState<any>(null)
  const [usdtAddr, setUsdtAddr] = useState('')
  const [usdtNet, setUsdtNet] = useState('TRC20')
  const [bankInfo, setBankInfo] = useState('')
  const [alertSettings, setAlertSettings] = useState<any>(null)
  const [alertEmail, setAlertEmail] = useState('')
  const [alertPhone, setAlertPhone] = useState('')
  // View/edit toggles for the saved-row pattern on the Subscriptions tab: a set
  // value shows an "applied" row (edit/delete); editing or an unset value shows
  // the form. Reset to false after a successful save.
  const [editUsdt, setEditUsdt] = useState(false)
  const [editBank, setEditBank] = useState(false)
  const [editAlerts, setEditAlerts] = useState(false)
  const [contracts, setContracts] = useState<any | null>(null)
  const [planList, setPlanList] = useState<any[]>([])
  const [adminPlans, setAdminPlans] = useState<any[]>([])
  const [grant, setGrant] = useState({ email: '', plan_code: 'junior', days: '30', note: '',
    method: 'manual', reference: '', amount_usd: '' })
  // Manual member creation. `invite` holds the last result so the admin can see
  // whether the set-password email actually went out.
  const [newMember, setNewMember] = useState({ email: '', lang: 'en', plan_code: '', days: '30' })
  const [invite, setInvite] = useState<any | null>(null)
  // Which member rows have their agent sub-table open.
  const [openAgents, setOpenAgents] = useState<Record<number, boolean>>({})
  const [newPlan, setNewPlan] = useState({ code: '', name: '', price: '', sort: '10' })
  const [assets, setAssets] = useState<any | null>(null)
  const [positions, setPositions] = useState<any | null>(null)
  const [autoStats, setAutoStats] = useState<any | null>(null)
  const [autoRules, setAutoRules] = useState<any | null>(null)
  const [regimeRead, setRegimeRead] = useState<any | null>(null)
  // Swing signal stack (research/SWING_SIGNAL_STACK.md): live crawl status of
  // the six data feeds, probed server-side and cached 60s.
  const [feedStatus, setFeedStatus] = useState<any | null>(null)
  const [feedProbing, setFeedProbing] = useState(false)
  // Crawling & monitoring console: the pipeline overview (per-node health),
  // the crawl history behind it, and the decisions it produced.
  const [crawlOverview, setCrawlOverview] = useState<any | null>(null)
  const [crawlRuns, setCrawlRuns] = useState<any[]>([])
  const [crawlDecisions, setCrawlDecisions] = useState<any[]>([])
  const [crawlFeed, setCrawlFeed] = useState<string>('')
  const [crawlSymbols, setCrawlSymbols] = useState('')
  const [crawlBusy, setCrawlBusy] = useState(false)
  const [crawlResult, setCrawlResult] = useState<any | null>(null)
  const [llmSettings, setLlmSettings] = useState<any | null>(null)
  // Trend accounts (Plan 32): user accounts dedicated to the trend rule.
  const [trendAccounts, setTrendAccounts] = useState<any | null>(null)
  const [trendForm, setTrendForm] = useState({ agent_id: '', account_type: 'simulator', risk_usd: '25' })
  const [llmForm, setLlmForm] = useState({ local_base_url: '', local_model: '',
    brief_provider: '', brief_model: '', decision_provider: '', decision_model: '' })
  // Trading skills (Plan 20): the desk's house decision methods. `skillEdit`
  // holds the working copy for the editor card (isNew = create form); markets
  // travel as a comma-separated string in the editor and become an array (or
  // [] = all markets) only at save time.
  const [skills, setSkills] = useState<any[]>([])
  const [skillEdit, setSkillEdit] = useState<any | null>(null)
  // Which skill rows have their full body unfolded (read-only view — the
  // 16 bodies together run ~9KB, so the table shows summaries and each row
  // expands on demand instead of rendering every body inline).
  const [openSkills, setOpenSkills] = useState<Record<string, boolean>>({})
  const [threads, setThreads] = useState<any | null>(null)
  const [activeThread, setActiveThread] = useState<any | null>(null)
  const [reply, setReply] = useState('')
  const [broadcast, setBroadcast] = useState({ title: '', body: '' })
  const [discussions, setDiscussions] = useState<any | null>(null)
  const [replies, setReplies] = useState<Record<number, any[]>>({})
  const [leaderboard, setLeaderboard] = useState<any | null>(null)
  const [lbMetric, setLbMetric] = useState('return')
  const [admins, setAdmins] = useState<any | null>(null)
  const [audit, setAudit] = useState<any | null>(null)
  const [q, setQ] = useState('')
  const [dq, setDq] = useState('')
  const [newAdmin, setNewAdmin] = useState({ email: '', password: '', role: 'operator' })
  const [exclusion, setExclusion] = useState({ agent_id: '', reason: '' })

  const T = {
    title: tr(language, { ko: '관리자 콘솔', en: 'Manager Console', ja: '管理コンソール', th: 'คอนโซลผู้ดูแล', vi: 'Bảng quản trị', id: 'Konsol manajer' }),
    email: tr(language, { ko: '이메일', en: 'Email', ja: 'メール', th: 'อีเมล', vi: 'Email', id: 'Email' }),
    password: tr(language, { ko: '비밀번호', en: 'Password', ja: 'パスワード', th: 'รหัสผ่าน', vi: 'Mật khẩu', id: 'Kata sandi' }),
    signIn: tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' }),
    signOut: tr(language, { ko: '로그아웃', en: 'Sign out', ja: 'ログアウト', th: 'ออกจากระบบ', vi: 'Đăng xuất', id: 'Keluar' }),
    loginHint: tr(language, { ko: '관리자 계정으로 로그인하세요. 첫 계정은 서버에서 scripts/create_admin.py로 생성합니다.', en: 'Sign in with an admin account. Bootstrap the first one with scripts/create_admin.py on the server.', ja: '管理者アカウントでログインしてください。最初のアカウントはサーバー上で scripts/create_admin.py を実行して作成します。', th: 'เข้าสู่ระบบด้วยบัญชีผู้ดูแล บัญชีแรกสร้างด้วย scripts/create_admin.py บนเซิร์ฟเวอร์', vi: 'Đăng nhập bằng tài khoản quản trị. Tạo tài khoản đầu tiên bằng scripts/create_admin.py trên máy chủ.', id: 'Masuk dengan akun admin. Buat akun pertamanya dengan scripts/create_admin.py di server.' }),
    invalid: tr(language, { ko: '이메일 또는 비밀번호가 올바르지 않습니다', en: 'Invalid email or password', ja: 'メールアドレスまたはパスワードが正しくありません', th: 'อีเมลหรือรหัสผ่านไม่ถูกต้อง', vi: 'Email hoặc mật khẩu không đúng', id: 'Email atau kata sandi tidak valid' }),
    sessionExpired: tr(language, { ko: '세션이 만료되었습니다 — 다시 로그인하세요', en: 'Session expired — sign in again', ja: 'セッションが期限切れです — 再度ログインしてください', th: 'เซสชันหมดอายุ — เข้าสู่ระบบใหม่', vi: 'Phiên đã hết hạn — đăng nhập lại', id: 'Sesi berakhir — masuk kembali' }),
    tabDashboard: tr(language, { ko: '대시보드', en: 'Dashboard', ja: 'ダッシュボード', th: 'แดชบอร์ด', vi: 'Bảng điều khiển', id: 'Dasbor' }),
    tabMembers: tr(language, { ko: '회원 관리', en: 'Members', ja: '会員管理', th: 'จัดการสมาชิก', vi: 'Thành viên', id: 'Anggota' }),
    tabSubs: tr(language, { ko: '구독 관리', en: 'Subscriptions', ja: '購読管理', th: 'จัดการการสมัคร', vi: 'Đăng ký', id: 'Langganan' }),
    tabAssets: tr(language, { ko: '자산 통계', en: 'Assets', ja: '資産統計', th: 'สถิติสินทรัพย์', vi: 'Tài sản', id: 'Aset' }),
    tabPositions: tr(language, { ko: '포지션 통계', en: 'Positions', ja: 'ポジション統計', th: 'สถิติสถานะ', vi: 'Vị thế', id: 'Posisi' }),
    tabAutomation: tr(language, { ko: '자동화 통계', en: 'Automation', ja: '自動化統計', th: 'สถิติระบบอัตโนมัติ', vi: 'Tự động hóa', id: 'Otomatisasi' }),
    tabFeeds: tr(language, { ko: '피드 상태', en: 'Feed status', ja: 'フィード状態', th: 'สถานะฟีด', vi: 'Trạng thái feed', id: 'Status feed' }),
    feedsTitle: tr(language, { ko: '📡 스윙 시그널 스택 — 6개 피드 크롤링 상태', en: '📡 Swing signal stack — 6 feed crawl status', ja: '📡 スイングシグナルスタック — 6フィードのクロール状態', th: '📡 สแต็กสัญญาณสวิง — สถานะการรวบรวม 6 ฟีด', vi: '📡 Ngăn xếp tín hiệu swing — trạng thái thu thập 6 feed', id: '📡 Tumpukan sinyal swing — status perayapan 6 feed' }),
    feedsHint: tr(language, { ko: '각 피드의 공개 소스를 서버에서 직접 프로브합니다 (60초 캐시). 실패한 피드는 스택의 해당 점수 커버리지가 줄어듭니다.', en: 'Each feed\'s public source is probed server-side (60s cache). A failed feed shrinks that score\'s coverage in the stack.', ja: '各フィードの公開ソースをサーバー側で直接プローブします（60秒キャッシュ）。失敗したフィードはスタック内の該当スコアのカバレッジが縮小します。', th: 'ตรวจสอบแหล่งข้อมูลสาธารณะของแต่ละฟีดฝั่งเซิร์ฟเวอร์ (แคช 60 วินาที) ฟีดที่ล้มเหลวจะลดความครอบคลุมของคะแนนนั้นในสแต็ก', vi: 'Nguồn công khai của từng feed được thăm dò phía máy chủ (bộ đệm 60 giây). Feed hỏng làm giảm độ phủ của điểm đó trong ngăn xếp.', id: 'Sumber publik tiap feed diperiksa dari sisi server (cache 60 detik). Feed yang gagal mengecilkan cakupan skor itu dalam tumpukan.' }),
    feedCol: tr(language, { ko: '피드', en: 'Feed', ja: 'フィード', th: 'ฟีด', vi: 'Feed', id: 'Feed' }),
    feedDocCol: tr(language, { ko: '문서상 피드', en: 'Doc feed', ja: 'ドキュメント上のフィード', th: 'ฟีดตามเอกสาร', vi: 'Feed theo tài liệu', id: 'Feed dokumen' }),
    feedSourceCol: tr(language, { ko: '소스', en: 'Source', ja: 'ソース', th: 'แหล่งข้อมูล', vi: 'Nguồn', id: 'Sumber' }),
    feedStatusCol: tr(language, { ko: '상태', en: 'Status', ja: '状態', th: 'สถานะ', vi: 'Trạng thái', id: 'Status' }),
    feedLatencyCol: tr(language, { ko: '지연', en: 'Latency', ja: '遅延', th: 'ความหน่วง', vi: 'Độ trễ', id: 'Latensi' }),
    feedDetailCol: tr(language, { ko: '상세', en: 'Detail', ja: '詳細', th: 'รายละเอียด', vi: 'Chi tiết', id: 'Detail' }),
    feedReprobe: tr(language, { ko: '지금 다시 프로브', en: 'Re-probe now', ja: '今すぐ再プローブ', th: 'ตรวจสอบใหม่ตอนนี้', vi: 'Thăm dò lại ngay', id: 'Periksa ulang sekarang' }),
    feedCached: tr(language, { ko: '캐시됨', en: 'cached', ja: 'キャッシュ済み', th: 'จากแคช', vi: 'đã lưu đệm', id: 'dari cache' }),
    feedCheckedAt: tr(language, { ko: '확인 시각', en: 'checked', ja: '確認時刻', th: 'ตรวจเมื่อ', vi: 'kiểm tra lúc', id: 'diperiksa' }),
    tabCrawl: tr(language, { ko: '크롤링 · 모니터링', en: 'Crawl & monitor', ja: 'クロール・監視', th: 'รวบรวม · ตรวจสอบ', vi: 'Thu thập · Giám sát', id: 'Perayapan & pemantauan' }),
    crawlTitle: tr(language, { ko: '🕸 크롤링 & 모니터링 — 수집 → 점수 → 합성 → 결정', en: '🕸 Crawling & monitoring — collect → score → combine → decide', ja: '🕸 クロール＆監視 — 収集 → スコア → 合成 → 判断', th: '🕸 การรวบรวมและตรวจสอบ — เก็บ → ให้คะแนน → รวม → ตัดสิน', vi: '🕸 Thu thập & giám sát — thu thập → chấm điểm → tổng hợp → quyết định', id: '🕸 Perayapan & pemantauan — kumpulkan → skor → gabungkan → putuskan' }),
    crawlHint: tr(language, { ko: '업스트림 URL 프로브가 아니라 우리 크롤러가 실제로 한 일(crawl_runs)을 보여줍니다. 한 번도 실행되지 않은 피드는 회색(idle)이며 정상이 아닙니다.', en: 'Shows what our crawlers actually did (crawl_runs), not a one-shot probe of an upstream URL. A feed that never ran is grey (idle) — not healthy.', ja: 'アップストリームURLの単発プローブではなく、当社のクローラーが実際に行ったこと（crawl_runs）を表示します。一度も実行されていないフィードはグレー（idle）であり、正常ではありません。', th: 'แสดงสิ่งที่ตัวรวบรวมของเราทำจริง (crawl_runs) ไม่ใช่การตรวจสอบ URL ต้นทางครั้งเดียว ฟีดที่ไม่เคยทำงานจะเป็นสีเทา (idle) ไม่ใช่ปกติ', vi: 'Hiển thị những gì trình thu thập của chúng tôi thực sự đã làm (crawl_runs), không phải một lần thăm dò URL nguồn. Feed chưa từng chạy có màu xám (idle) — không phải khỏe mạnh.', id: 'Menampilkan apa yang benar-benar dilakukan perayap kami (crawl_runs), bukan pemeriksaan sekali jalan atas URL hulu. Feed yang belum pernah berjalan berwarna abu-abu (idle) — bukan sehat.' }),
    crawlRunNow: tr(language, { ko: '지금 실행', en: 'Run a pass now', ja: '今すぐ実行', th: 'รันตอนนี้', vi: 'Chạy ngay', id: 'Jalankan sekarang' }),
    crawlSymbolsPh: tr(language, { ko: '심볼 (쉼표 구분, 비우면 설정값)', en: 'symbols, comma separated (blank = configured)', ja: 'シンボル（カンマ区切り、空欄で設定値）', th: 'สัญลักษณ์ คั่นด้วยจุลภาค (เว้นว่าง = ค่าที่ตั้งไว้)', vi: 'mã, phân tách bằng dấu phẩy (để trống = cấu hình)', id: 'simbol, dipisah koma (kosong = terkonfigurasi)' }),
    crawlHistory: tr(language, { ko: '크롤 이력', en: 'Crawl history', ja: 'クロール履歴', th: 'ประวัติการรวบรวม', vi: 'Lịch sử thu thập', id: 'Riwayat perayapan' }),
    crawlDecisionsTitle: tr(language, { ko: '심볼별 최신 결정', en: 'Latest decision per symbol', ja: 'シンボル別の最新判断', th: 'การตัดสินล่าสุดต่อสัญลักษณ์', vi: 'Quyết định mới nhất theo mã', id: 'Keputusan terbaru per simbol' }),
    crawlDisabled: tr(language, { ko: '파이프라인 비활성 (SWING_PIPELINE_ENABLED)', en: 'pipeline disabled (SWING_PIPELINE_ENABLED)', ja: 'パイプライン無効 (SWING_PIPELINE_ENABLED)', th: 'ไปป์ไลน์ปิดอยู่ (SWING_PIPELINE_ENABLED)', vi: 'pipeline đã tắt (SWING_PIPELINE_ENABLED)', id: 'pipeline nonaktif (SWING_PIPELINE_ENABLED)' }),
    crawlAll: tr(language, { ko: '전체', en: 'all feeds', ja: '全フィード', th: 'ทุกฟีด', vi: 'tất cả feed', id: 'semua feed' }),
    crawlBlend: tr(language, { ko: '심볼별 sentiment 혼합', en: 'Per-symbol sentiment blend', ja: 'シンボル別センチメント混合', th: 'การผสมเซนทิเมนต์รายสัญลักษณ์', vi: 'Trộn tâm lý theo mã', id: 'Campuran sentimen per simbol' }),
    crawlBlendShadow: tr(language, { ko: '섀도우 측정 중 — 결정에는 사용되지 않음', en: 'measuring in shadow — not used to decide', ja: 'シャドー測定中 — 判断には未使用', th: 'กำลังวัดแบบเงา — ไม่ใช้ตัดสิน', vi: 'đang đo ở chế độ bóng — không dùng để quyết định', id: 'mengukur dalam bayangan — tidak dipakai memutuskan' }),
    crawlBlendFlips: tr(language, { ko: '결정이 뒤집힌 건수', en: 'decisions it would have flipped', ja: '判断が反転する件数', th: 'จำนวนการตัดสินที่จะพลิก', vi: 'số quyết định sẽ đảo chiều', id: 'keputusan yang akan berbalik' }),
    crawlNoRuns: tr(language, { ko: '아직 크롤 기록이 없습니다.', en: 'No crawl recorded yet.', ja: 'クロール記録はまだありません。', th: 'ยังไม่มีบันทึกการรวบรวม', vi: 'Chưa có bản ghi thu thập nào.', id: 'Belum ada perayapan tercatat.' }),
    tabSupport: tr(language, { ko: '문의 · 알림', en: 'Support & alerts', ja: '問い合わせ・通知', th: 'ซัพพอร์ต · การแจ้งเตือน', vi: 'Hỗ trợ · Thông báo', id: 'Dukungan & peringatan' }),
    tabDiscussions: tr(language, { ko: '토론 관리', en: 'Discussions', ja: '議論管理', th: 'จัดการกระทู้', vi: 'Thảo luận', id: 'Diskusi' }),
    tabLeaderboard: tr(language, { ko: '리더보드 관리', en: 'Leaderboard', ja: 'リーダーボード管理', th: 'จัดการลีดเดอร์บอร์ด', vi: 'Bảng xếp hạng', id: 'Papan peringkat' }),
    tabAdmins: tr(language, { ko: '관리자 계정', en: 'Admins', ja: '管理者アカウント', th: 'บัญชีผู้ดูแล', vi: 'Quản trị viên', id: 'Admin' }),
    tabAudit: tr(language, { ko: '감사 로그', en: 'Audit', ja: '監査ログ', th: 'บันทึกตรวจสอบ', vi: 'Nhật ký kiểm toán', id: 'Audit' }),
    noData: tr(language, { ko: '데이터 없음', en: 'No data', ja: 'データなし', th: 'ไม่มีข้อมูล', vi: 'Không có dữ liệu', id: 'Tidak ada data' }),
    search: tr(language, { ko: '검색', en: 'Search', ja: '検索', th: 'ค้นหา', vi: 'Tìm kiếm', id: 'Cari' }),
    del: tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa', id: 'Hapus' }),
    delConfirm: tr(language, { ko: '정말 삭제할까요? 이 계정의 모든 데이터가 함께 삭제됩니다.', en: 'Really delete? All of this account\'s data is deleted with it.', ja: '本当に削除しますか？このアカウントの全データも一緒に削除されます。', th: 'ลบจริงหรือไม่ ข้อมูลทั้งหมดของบัญชีนี้จะถูกลบไปด้วย', vi: 'Xóa thật chứ? Toàn bộ dữ liệu của tài khoản này sẽ bị xóa theo.', id: 'Yakin ingin menghapus? Seluruh data akun ini ikut terhapus.' }),
    suspend: tr(language, { ko: '정지', en: 'Suspend', ja: '停止', th: 'ระงับ', vi: 'Tạm ngưng', id: 'Tangguhkan' }),
    resetCap: tr(language, { ko: '자본 리셋', en: 'Reset $', ja: '資本リセット', th: 'รีเซ็ตทุน', vi: 'Đặt lại vốn', id: 'Reset modal' }),
    resetCapPrompt: tr(language, { ko: '리셋할 자본 금액(USD) — 모든 에이전트의 현금·시작자본이 이 값이 되고, 보유 포지션과 수익 이력이 삭제되어 수익이 0이 됩니다', en: 'Capital amount (USD) — every agent of this member is set to this cash & starting capital; open positions and the profit history are wiped so profit reads zero', ja: 'リセットする資本額 (USD) — この会員の全エージェントの現金・開始資本がこの値になり、保有ポジションと損益履歴が削除され、利益は0になります', th: 'จำนวนทุน (USD) — เอเจนต์ทั้งหมดของสมาชิกจะถูกตั้งเงินสด·ทุนเริ่มต้นเป็นค่านี้ ลบสถานะที่ถืออยู่และประวัติกำไรให้กำไรเป็นศูนย์', vi: 'Số vốn (USD) — mọi agent của thành viên được đặt tiền mặt & vốn khởi điểm bằng giá trị này; vị thế mở và lịch sử lợi nhuận bị xóa nên lợi nhuận về 0', id: 'Jumlah modal (USD) — semua agen anggota ini disetel ke kas & modal awal ini; posisi terbuka dan riwayat laba dihapus sehingga laba menjadi nol' }),
    resetCapBad: tr(language, { ko: '금액이 올바르지 않습니다', en: 'Invalid amount', ja: '金額が正しくありません', th: 'จำนวนไม่ถูกต้อง', vi: 'Số tiền không hợp lệ', id: 'Jumlah tidak valid' }),
    resetCapConfirm: (email: string, v: number) => tr(language, { ko: `${email} 계정을 $${v.toLocaleString()}로 리셋할까요? 포지션·수익 이력이 삭제됩니다 (되돌릴 수 없음)`, en: `Reset ${email} to $${v.toLocaleString()}? Open positions and profit history are deleted (cannot be undone)`, ja: `${email} を $${v.toLocaleString()} にリセットしますか？ポジションと損益履歴が削除されます（元に戻せません）`, th: `รีเซ็ต ${email} เป็น $${v.toLocaleString()} หรือไม่ สถานะและประวัติกำไรจะถูกลบ (ย้อนกลับไม่ได้)`, vi: `Đặt lại ${email} về $${v.toLocaleString()}? Vị thế mở và lịch sử lợi nhuận sẽ bị xóa (không hoàn tác được)`, id: `Reset ${email} ke $${v.toLocaleString()}? Posisi terbuka dan riwayat laba dihapus (tidak bisa dibatalkan)` }),
    activate: tr(language, { ko: '해제', en: 'Activate', ja: '解除', th: 'ปลดระงับ', vi: 'Kích hoạt', id: 'Aktifkan' }),
    detail: tr(language, { ko: '상세', en: 'Detail', ja: '詳細', th: 'รายละเอียด', vi: 'Chi tiết', id: 'Detail' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    approve: tr(language, { ko: '승인', en: 'Approve', ja: '承認', th: 'อนุมัติ', vi: 'Duyệt', id: 'Setujui' }),
    reject: tr(language, { ko: '거절', en: 'Reject', ja: '却下', th: 'ปฏิเสธ', vi: 'Từ chối', id: 'Tolak' }),
    extend30: tr(language, { ko: '+30일', en: '+30 days', ja: '+30日', th: '+30 วัน', vi: '+30 ngày', id: '+30 hari' }),
    cancelSub: tr(language, { ko: '해지', en: 'Cancel', ja: '解約', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' }),
    cancelConfirm: tr(language, { ko: '이 구독을 해지할까요? 회원은 즉시 구독 페이지로 이동됩니다.', en: 'Cancel this subscription? The member is gated to the subscribe page immediately.', ja: 'この購読を解約しますか？会員は直ちに購読ページへ誘導されます。', th: 'ยกเลิกการสมัครนี้หรือไม่ สมาชิกจะถูกพาไปหน้าสมัครทันที', vi: 'Hủy đăng ký này? Thành viên sẽ bị chuyển ngay tới trang đăng ký.', id: 'Batalkan langganan ini? Anggota tersebut langsung diarahkan ke halaman berlangganan.' }),
    grantTitle: tr(language, { ko: '수동 부여 — 결제 없이 플랜 지급 (무료 제공·기존회원·엔터프라이즈 계약)', en: 'Manual grant — assign a plan without payment (comps, grandfathered members, enterprise contracts)', ja: '手動付与 — 決済なしでプランを割り当て（無償提供・既存会員・エンタープライズ契約）', th: 'ให้สิทธิ์เอง — กำหนดแพลนโดยไม่ต้องชำระเงิน (ให้ฟรี, สมาชิกเดิม, สัญญาองค์กร)', vi: 'Cấp thủ công — gán gói không cần thanh toán (tặng, thành viên cũ, hợp đồng doanh nghiệp)', id: 'Pemberian manual — tetapkan paket tanpa pembayaran (kompensasi, anggota lama, kontrak enterprise)' }),
    grantBtn: tr(language, { ko: '부여', en: 'Grant', ja: '付与', th: 'ให้สิทธิ์', vi: 'Cấp', id: 'Berikan' }),
    payMethod: tr(language, { ko: '결제 수단', en: 'Payment method', ja: '決済手段', th: 'วิธีชำระเงิน', vi: 'Phương thức thanh toán', id: 'Metode pembayaran' }),
    payMethodComp: tr(language, { ko: 'manual — 무상 제공 (매출 미집계)', en: 'manual — comp (not counted as revenue)', ja: 'manual — 無償提供（売上に計上しない）', th: 'manual — ให้ฟรี (ไม่นับเป็นรายได้)', vi: 'manual — tặng (không tính doanh thu)', id: 'manual — gratis (tidak dihitung sebagai pendapatan)' }),
    payReference: tr(language, { ko: '입금 참조 (tx 해시·입금자명)', en: 'Payment reference (tx hash, sender name)', ja: '入金参照 (txハッシュ・振込名義)', th: 'อ้างอิงการชำระ (tx hash, ชื่อผู้โอน)', vi: 'Tham chiếu thanh toán (tx hash, tên người gửi)', id: 'Referensi pembayaran (tx hash, nama pengirim)' }),
    payAmount: tr(language, { ko: '금액 (USD)', en: 'Amount (USD)', ja: '金額 (USD)', th: 'จำนวนเงิน (USD)', vi: 'Số tiền (USD)', id: 'Jumlah (USD)' }),
    payRecordHint: tr(language, { ko: '사이트 밖에서 받은 결제를 기록하려면 수단·참조·금액을 채우세요. 금액이 0보다 크면 매출로 집계됩니다.', en: 'Fill in method, reference and amount to record a payment taken outside the site. Any amount above 0 counts as revenue.', ja: 'サイト外で受け取った決済を記録するには、手段・参照・金額を入力してください。0より大きい金額は売上に計上されます。', th: 'กรอกวิธี อ้างอิง และจำนวนเงิน เพื่อบันทึกการชำระที่รับนอกเว็บไซต์ จำนวนที่มากกว่า 0 จะนับเป็นรายได้', vi: 'Điền phương thức, tham chiếu và số tiền để ghi nhận khoản thanh toán nhận ngoài trang web. Số tiền lớn hơn 0 được tính là doanh thu.', id: 'Isi metode, referensi, dan jumlah untuk mencatat pembayaran yang diterima di luar situs. Jumlah di atas 0 dihitung sebagai pendapatan.' }),
    addMember: tr(language, { ko: '회원 추가', en: 'Add member', ja: '会員を追加', th: 'เพิ่มสมาชิก', vi: 'Thêm thành viên', id: 'Tambah anggota' }),
    addMemberHint: tr(language, { ko: '계정을 만들고 비밀번호 설정 코드를 이메일로 보냅니다. 관리자는 비밀번호를 정하지 않으며, 회원이 코드로 직접 설정하기 전까지는 로그인할 수 없습니다. 코드는 7일간 유효합니다.', en: 'Creates the account and emails a code to set a password. You never choose their password — they cannot sign in until they set one. The code is valid for 7 days.', ja: 'アカウントを作成し、パスワード設定コードをメールで送ります。管理者はパスワードを決めず、会員がコードで設定するまでログインできません。コードの有効期間は7日間です。', th: 'สร้างบัญชีและส่งรหัสสำหรับตั้งรหัสผ่านทางอีเมล ผู้ดูแลไม่ได้ตั้งรหัสผ่านให้ และสมาชิกจะเข้าสู่ระบบไม่ได้จนกว่าจะตั้งเอง รหัสใช้ได้ 7 วัน', vi: 'Tạo tài khoản và gửi email mã để đặt mật khẩu. Bạn không chọn mật khẩu cho họ — họ không thể đăng nhập cho đến khi tự đặt. Mã có hiệu lực 7 ngày.', id: 'Membuat akun dan mengirim kode via email untuk mengatur kata sandi. Anda tidak memilih kata sandi mereka — mereka tidak bisa masuk sampai mengaturnya sendiri. Kode berlaku 7 hari.' }),
    addMemberBtn: tr(language, { ko: '추가하고 초대 보내기', en: 'Add and send invite', ja: '追加して招待を送る', th: 'เพิ่มและส่งคำเชิญ', vi: 'Thêm và gửi lời mời', id: 'Tambah dan kirim undangan' }),
    memberLang: tr(language, { ko: '메일 언어', en: 'Email language', ja: 'メールの言語', th: 'ภาษาอีเมล', vi: 'Ngôn ngữ email', id: 'Bahasa email' }),
    planNone: tr(language, { ko: '(플랜 없음)', en: '(no plan)', ja: '（プランなし）', th: '(ไม่มีแพลน)', vi: '(không gói)', id: '(tanpa paket)' }),
    inviteSent: tr(language, { ko: '초대 메일을 보냈습니다', en: 'Invite email sent', ja: '招待メールを送信しました', th: 'ส่งอีเมลคำเชิญแล้ว', vi: 'Đã gửi email mời', id: 'Email undangan terkirim' }),
    inviteFailed: tr(language, { ko: '계정은 생성됐지만 메일 발송에 실패했습니다 — 서버 로그의 코드를 전달하거나, 회원에게 비밀번호 찾기를 안내하세요', en: 'Account created but the email failed — pass on the code from the server log, or tell the member to use "forgot password"', ja: 'アカウントは作成されましたがメール送信に失敗しました — サーバーログのコードを伝えるか、会員にパスワード再設定を案内してください', th: 'สร้างบัญชีแล้วแต่ส่งอีเมลไม่สำเร็จ — ส่งรหัสจากล็อกเซิร์ฟเวอร์ให้ หรือแนะนำให้สมาชิกใช้ "ลืมรหัสผ่าน"', vi: 'Đã tạo tài khoản nhưng gửi email thất bại — chuyển mã từ log máy chủ, hoặc bảo thành viên dùng "quên mật khẩu"', id: 'Akun dibuat tetapi email gagal terkirim — sampaikan kode dari log server, atau minta anggota memakai "lupa kata sandi"' }),
    agentsCount: (n: number) => tr(language, { ko: `에이전트 ${n}개`, en: `${n} agent${n === 1 ? '' : 's'}`, ja: `エージェント${n}件`, th: `${n} เอเจนต์`, vi: `${n} agent`, id: `${n} agen` }),
    noAgents: tr(language, { ko: '에이전트 없음', en: 'No agents', ja: 'エージェントなし', th: 'ไม่มีเอเจนต์', vi: 'Không có agent', id: 'Tidak ada agen' }),
    equityOfAgent: tr(language, { ko: '에이전트별 곡선 — 표시 중', en: 'Per-agent curve — showing', ja: 'エージェント別の推移 — 表示中', th: 'กราฟรายเอเจนต์ — กำลังแสดง', vi: 'Đường theo từng agent — đang hiện', id: 'Kurva per agen — menampilkan' }),
    llmTitle: tr(language, { ko: '🤖 AI 모델 라우팅 (LLM)', en: '🤖 AI model routing (LLM)', ja: '🤖 AIモデルルーティング (LLM)', th: '🤖 การกำหนดเส้นทางโมเดล AI (LLM)', vi: '🤖 Định tuyến mô hình AI (LLM)', id: '🤖 Perutean model AI (LLM)' }),
    llmHint: tr(language, {
      ko: '티어별 프로바이더/모델을 플랫폼 전역으로 지정합니다. Local AI 서버 URL은 운영자의 자체 AI 서버(Ollama 등, OpenAI 호환)를 가리킵니다. 저장한 값이 .env보다 우선하며, 비우면 .env로 돌아갑니다. 사용자가 직접 프로바이더를 지정한 실행에는 적용되지 않고, 워커에는 30초 안에 반영됩니다.',
      en: 'Routes each tier\'s provider/model platform-wide. The local AI server URL points at your own AI server (Ollama etc., OpenAI-compatible). Saved values win over .env; clearing a field falls back to .env. Runs where a user picked their own provider are not overridden. The worker picks changes up within 30 seconds.',
      ja: 'ティアごとのプロバイダー/モデルをプラットフォーム全体に指定します。ローカルAIサーバーURLは運営者自身のAIサーバー（Ollamaなど、OpenAI互換）を指します。保存した値は.envより優先され、空欄にすると.envに戻ります。ユーザーが自分でプロバイダーを指定した実行には適用されず、ワーカーには30秒以内に反映されます。',
      th: 'กำหนดผู้ให้บริการ/โมเดลของแต่ละเทียร์ทั้งแพลตฟอร์ม URL เซิร์ฟเวอร์ AI ท้องถิ่นชี้ไปยังเซิร์ฟเวอร์ AI ของคุณเอง (Ollama ฯลฯ, เข้ากับ OpenAI) ค่าที่บันทึกมีผลเหนือ .env เว้นว่างเพื่อกลับไปใช้ .env ไม่ทับการรันที่ผู้ใช้เลือกผู้ให้บริการเอง เวิร์กเกอร์รับการเปลี่ยนแปลงภายใน 30 วินาที',
      vi: 'Định tuyến provider/model của từng tầng trên toàn nền tảng. URL máy chủ AI cục bộ trỏ tới máy chủ AI của riêng bạn (Ollama v.v., tương thích OpenAI). Giá trị đã lưu thắng .env; xóa trống sẽ quay về .env. Không ghi đè các lượt chạy mà người dùng tự chọn provider. Worker nhận thay đổi trong vòng 30 giây.',
      id: 'Mengarahkan penyedia/model tiap tingkatan untuk seluruh platform. URL server AI lokal menunjuk ke server AI Anda sendiri (Ollama dsb., kompatibel OpenAI). Nilai tersimpan menang atas .env; mengosongkan kolom akan kembali ke .env. Run di mana pengguna memilih penyedianya sendiri tidak ditimpa. Worker menerapkan perubahan dalam 30 detik.' }),
    llmLocalUrl: tr(language, { ko: 'Local AI 서버 URL', en: 'Local AI server URL', ja: 'ローカルAIサーバーURL', th: 'URL เซิร์ฟเวอร์ AI ท้องถิ่น', vi: 'URL máy chủ AI cục bộ', id: 'URL server AI lokal' }),
    llmLocalModel: tr(language, { ko: '로컬 모델', en: 'Local model', ja: 'ローカルモデル', th: 'โมเดลท้องถิ่น', vi: 'Model cục bộ', id: 'Model lokal' }),
    llmBrief: tr(language, { ko: '브리핑 티어 (애널리스트)', en: 'Brief tier (analysts)', ja: 'ブリーフティア（アナリスト）', th: 'เทียร์สรุป (นักวิเคราะห์)', vi: 'Tầng brief (phân tích)', id: 'Tingkat ringkasan (analis)' }),
    llmDecision: tr(language, { ko: '결정 티어 (트레이더·검증)', en: 'Decision tier (trader & verify)', ja: '決定ティア（トレーダー・検証）', th: 'เทียร์ตัดสินใจ (เทรดเดอร์·ตรวจสอบ)', vi: 'Tầng quyết định (trader & xác minh)', id: 'Tingkat keputusan (trader & verifikasi)' }),
    llmProviderDefault: tr(language, { ko: '(기본값 유지)', en: '(keep default)', ja: '（デフォルト維持）', th: '(ค่าเริ่มต้น)', vi: '(giữ mặc định)', id: '(pakai bawaan)' }),
    llmModelPlaceholder: tr(language, { ko: '모델 (비우면 프로바이더 기본값)', en: 'model (empty = provider default)', ja: 'モデル（空欄＝プロバイダー既定）', th: 'โมเดล (ว่าง = ค่าเริ่มต้นผู้ให้บริการ)', vi: 'model (trống = mặc định provider)', id: 'model (kosong = bawaan penyedia)' }),
    llmEffective: tr(language, { ko: '현재 적용 라우팅', en: 'Effective routing now', ja: '現在適用中のルーティング', th: 'เส้นทางที่มีผลตอนนี้', vi: 'Định tuyến hiệu lực hiện tại', id: 'Perutean yang berlaku sekarang' }),
    usdtTitle: tr(language, { ko: 'USDT 입금 주소 등록', en: 'USDT receiving address', ja: 'USDT入金アドレス', th: 'ที่อยู่รับ USDT', vi: 'Địa chỉ nhận USDT', id: 'Alamat penerima USDT' }),
    usdtHint: tr(language, {
      ko: '구독자에게 이 주소로 송금하라고 안내합니다. 여기 저장한 값이 곧바로 결제 페이지에 표시되므로, 지갑에서 복사해 붙여넣고 저장 전에 반드시 확인하세요. 비워두면 결제 페이지에서 USDT 항목이 사라집니다.',
      en: 'Subscribers are told to send real money to whatever is saved here, and it appears on the payment page immediately. Paste it straight from your wallet and check it before saving. Leaving it empty removes USDT from the payment page.',
      ja: 'ここに保存したアドレスへ送金するよう購読者に案内され、決済ページに即座に表示されます。ウォレットから直接コピーして貼り付け、保存前に必ず確認してください。空欄にすると決済ページからUSDTが消えます。',
      th: 'ผู้สมัครจะถูกแจ้งให้โอนเงินจริงมายังที่อยู่ที่บันทึกไว้ที่นี่ และจะแสดงบนหน้าชำระเงินทันที คัดลอกจากกระเป๋าเงินโดยตรงและตรวจสอบก่อนบันทึก ถ้าเว้นว่างไว้ USDT จะหายไปจากหน้าชำระเงิน',
      vi: 'Người đăng ký được hướng dẫn gửi tiền thật tới địa chỉ lưu ở đây, và nó hiện ngay trên trang thanh toán. Dán trực tiếp từ ví và kiểm tra trước khi lưu. Để trống sẽ gỡ USDT khỏi trang thanh toán.',
      id: 'Pelanggan diminta mengirim uang sungguhan ke alamat apa pun yang tersimpan di sini, dan alamat itu langsung muncul di halaman pembayaran. Tempel langsung dari dompet Anda dan periksa sebelum menyimpan. Mengosongkannya akan menghapus USDT dari halaman pembayaran.' }),
    usdtAddrPlaceholder: tr(language, { ko: '지갑에서 복사한 USDT 주소', en: 'USDT address, pasted from your wallet', ja: 'ウォレットからコピーしたUSDTアドレス', th: 'ที่อยู่ USDT ที่คัดลอกจากกระเป๋าเงิน', vi: 'Địa chỉ USDT dán từ ví của bạn', id: 'Alamat USDT, ditempel dari dompet Anda' }),
    trendTitle: tr(language, { ko: '추세 전용 계정', en: 'Trend accounts (dedicated)', ja: 'トレンド専用口座', th: 'บัญชีเทรนด์เฉพาะ', vi: 'Tài khoản xu hướng chuyên dụng', id: 'Akun tren khusus' }),
    trendHint: tr(language, { ko: '등록된 계정은 추세 규칙만 거래합니다 (롱 전용, 일봉 종가 청산). 런·플릿·수동·카피 주문은 이 계정에서 신규 진입할 수 없습니다. shadow는 각 주문을 연결된 브로커에 모의(dry-run)로도 보냅니다. 실제 자금은 사용되지 않습니다.', en: 'An enrolled account is traded by the trend rule only — long-only, exits on the daily close. Runs, fleets, manual and copy orders cannot open a position on it. "shadow" also sends each order to the account\'s connected broker as a dry run. No real money.', ja: '登録した口座はトレンドルールだけが取引します（ロングのみ、日足終値で決済）。ラン・フリート・手動・コピー注文はこの口座で新規建てできません。shadow は各注文を接続済みブローカーにもドライランで送ります。実資金は使いません。', th: 'บัญชีที่ลงทะเบียนจะถูกเทรดโดยกฎเทรนด์เท่านั้น (เฉพาะฝั่งซื้อ ปิดที่ราคาปิดรายวัน) รัน ฟลีต คำสั่งมือ และคำสั่งคัดลอกเปิดสถานะในบัญชีนี้ไม่ได้ shadow จะส่งแต่ละคำสั่งไปยังโบรกเกอร์ที่เชื่อมไว้แบบ dry-run ด้วย ไม่ใช้เงินจริง', vi: 'Tài khoản đã đăng ký chỉ do quy tắc xu hướng giao dịch (chỉ mua, thoát theo giá đóng cửa ngày). Run, fleet, lệnh thủ công và lệnh sao chép không thể mở vị thế trên đó. shadow còn gửi từng lệnh tới sàn đã kết nối dưới dạng chạy thử. Không dùng tiền thật.', id: 'Akun terdaftar hanya diperdagangkan oleh aturan tren (hanya long, keluar pada penutupan harian). Run, fleet, order manual dan salinan tidak dapat membuka posisi di sana. shadow juga mengirim tiap order ke broker terhubung sebagai uji coba. Tanpa uang sungguhan.' }),
    trendAgentId: tr(language, { ko: '에이전트 ID', en: 'agent id', ja: 'エージェントID', th: 'รหัสเอเจนต์', vi: 'ID agent', id: 'ID agen' }),
    trendRisk: tr(language, { ko: '거래당 리스크 ($)', en: 'risk per trade ($)', ja: '1取引あたりリスク ($)', th: 'ความเสี่ยงต่อเทรด ($)', vi: 'rủi ro mỗi lệnh ($)', id: 'risiko per trade ($)' }),
    trendAdd: tr(language, { ko: '등록', en: 'Enrol', ja: '登録', th: 'ลงทะเบียน', vi: 'Đăng ký', id: 'Daftarkan' }),
    trendRemove: tr(language, { ko: '해제', en: 'Remove', ja: '解除', th: 'นำออก', vi: 'Gỡ', id: 'Hapus' }),
    trendNone: tr(language, { ko: '등록된 계정 없음', en: 'No account enrolled', ja: '登録口座なし', th: 'ยังไม่มีบัญชีที่ลงทะเบียน', vi: 'Chưa có tài khoản nào', id: 'Belum ada akun terdaftar' }),
    trendOff: tr(language, { ko: '추세 모듈이 꺼져 있어 계정이 실행되지 않습니다', en: 'The trend module is off — no account runs', ja: 'トレンドモジュールがオフのため口座は動きません', th: 'โมดูลเทรนด์ปิดอยู่ — ไม่มีบัญชีทำงาน', vi: 'Mô-đun xu hướng đang tắt — không tài khoản nào chạy', id: 'Modul tren mati — tidak ada akun yang berjalan' }),
    trendUnmanaged: tr(language, { ko: '모듈이 꺼진 동안 이 계정들의 보유 포지션은 아무도 청산하지 않습니다', en: 'While the module is off, nothing exits the positions these accounts hold', ja: 'モジュールがオフの間、これらの口座の保有ポジションは誰も決済しません', th: 'ขณะที่โมดูลปิดอยู่ ไม่มีอะไรปิดสถานะที่บัญชีเหล่านี้ถืออยู่', vi: 'Khi mô-đun tắt, không gì đóng các vị thế mà những tài khoản này đang giữ', id: 'Selama modul mati, tidak ada yang menutup posisi yang dipegang akun-akun ini' }),
    trendNoBroker: tr(language, { ko: '연결된 브로커 없음', en: 'no broker linked', ja: 'ブローカー未接続', th: 'ยังไม่เชื่อมโบรกเกอร์', vi: 'chưa kết nối sàn', id: 'belum ada broker terhubung' }),
    usdtSave: tr(language, { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu', id: 'Simpan' }),
    usdtConfirm: tr(language, {
      ko: '이 주소로 구독자의 실제 자금이 입금됩니다. 지갑의 주소와 정확히 일치하는지 확인하셨습니까?',
      en: 'Subscribers will send real funds to this address. Have you checked it character-for-character against your wallet?',
      ja: 'このアドレスに購読者の実際の資金が入金されます。ウォレットのアドレスと一字一句一致することを確認しましたか？',
      th: 'เงินจริงของผู้สมัครจะถูกส่งไปยังที่อยู่นี้ คุณตรวจสอบตรงกันทุกตัวอักษรกับกระเป๋าเงินแล้วหรือยัง',
      vi: 'Người đăng ký sẽ gửi tiền thật tới địa chỉ này. Bạn đã đối chiếu từng ký tự với ví chưa?',
      id: 'Pelanggan akan mengirim dana sungguhan ke alamat ini. Sudahkah Anda memeriksanya karakter demi karakter terhadap dompet Anda?' }),
    usdtLive: tr(language, { ko: '결제 페이지에 표시 중', en: 'Live on the payment page', ja: '決済ページに表示中', th: 'แสดงอยู่บนหน้าชำระเงิน', vi: 'Đang hiển thị trên trang thanh toán', id: 'Aktif di halaman pembayaran' }),
    refCopy: tr(language, { ko: '복사', en: 'Copy', ja: 'コピー', th: 'คัดลอก', vi: 'Sao chép', id: 'Salin' }),
    refCopied: tr(language, { ko: '복사됨', en: 'Copied', ja: 'コピー済み', th: 'คัดลอกแล้ว', vi: 'Đã sao chép', id: 'Tersalin' }),
    refVerify: tr(language, { ko: '체인에서 확인', en: 'Verify on chain', ja: 'チェーンで確認', th: 'ตรวจสอบบนเชน', vi: 'Kiểm tra trên chuỗi', id: 'Verifikasi di blockchain' }),
    bankTitle: tr(language, { ko: '계좌이체 정보 등록', en: 'Bank transfer details', ja: '銀行振込先の登録', th: 'ข้อมูลโอนเงินธนาคาร', vi: 'Thông tin chuyển khoản', id: 'Detail transfer bank' }),
    bankHint: tr(language, { ko: '구독 페이지에 그대로 표시됩니다. 은행명·계좌번호·예금주를 줄바꿈으로 적어주세요.', en: 'Shown verbatim on the Subscribe page. Bank, account number and holder name, one per line.', ja: '購読ページにそのまま表示されます。銀行名・口座番号・名義を改行で入力してください。', th: 'แสดงตามที่กรอกบนหน้าสมัคร ใส่ธนาคาร เลขบัญชี และชื่อบัญชี บรรทัดละรายการ', vi: 'Hiển thị nguyên văn trên trang đăng ký. Ngân hàng, số tài khoản và chủ tài khoản, mỗi dòng một mục.', id: 'Ditampilkan apa adanya di halaman Berlangganan. Bank, nomor rekening, dan nama pemilik, satu per baris.' }),
    bankPlaceholder: tr(language, { ko: '국민은행 123456-78-901234\n예금주: (주)수피', en: 'Bank of America 123456789\nAccount holder: Sooppiy Inc.', ja: '三菱UFJ銀行 123-4567890\n名義: Sooppiy', th: 'ธนาคารกสิกรไทย 123-4-56789-0\nชื่อบัญชี: Sooppiy', vi: 'Vietcombank 0123456789\nChủ tài khoản: Sooppiy', id: 'Bank Central Asia 1234567890\nAtas nama: Sooppiy' }),
    bankUnset: tr(language, { ko: '미등록 — 계좌이체를 선택한 회원에게 보낼 곳이 표시되지 않습니다', en: 'Not set — members choosing bank transfer are shown no destination', ja: '未登録 — 銀行振込を選んだ会員に送金先が表示されません', th: 'ยังไม่ตั้งค่า — สมาชิกที่เลือกโอนธนาคารจะไม่เห็นปลายทาง', vi: 'Chưa đặt — thành viên chọn chuyển khoản không thấy nơi nhận', id: 'Belum diatur — anggota yang memilih transfer bank tidak melihat tujuan transfer' }),
    usdtFromEnv: tr(language, { ko: '.env 값 사용 중 (저장하면 대체됨)', en: 'currently from .env (saving replaces it)', ja: '.env の値を使用中（保存すると置き換わります）', th: 'ใช้ค่าจาก .env อยู่ (บันทึกแล้วจะแทนที่)', vi: 'Đang dùng giá trị .env (lưu sẽ thay thế)', id: 'saat ini dari .env (menyimpan akan menggantinya)' }),
    usdtUnset: tr(language, { ko: '주소 미등록 — 결제 페이지에 USDT가 표시되지 않습니다', en: 'No address set — USDT is not offered on the payment page', ja: 'アドレス未登録 — 決済ページにUSDTは表示されません', th: 'ยังไม่ตั้งที่อยู่ — ไม่มี USDT บนหน้าชำระเงิน', vi: 'Chưa đặt địa chỉ — không hiển thị USDT trên trang thanh toán', id: 'Belum ada alamat — USDT tidak ditawarkan di halaman pembayaran' }),
    alertsTitle: tr(language, { ko: '구독 요청 알림 수신처', en: 'Subscription request alerts', ja: '購読リクエスト通知先', th: 'การแจ้งเตือนคำขอสมัคร', vi: 'Cảnh báo yêu cầu đăng ký', id: 'Peringatan permintaan langganan' }),
    alertsHint: tr(language, { ko: '누군가 /subscribe에서 구독을 요청하면 이 이메일·문자로 알림을 보냅니다. 비워두면 해당 채널은 꺼집니다.', en: 'When someone requests a subscription on /subscribe, an alert is sent to this email and/or phone. Leave a field empty to turn that channel off.', ja: '誰かが /subscribe で購読を申請すると、この메ール・電話に通知します。空欄にするとそのチャンネルはオフになります。', th: 'เมื่อมีคนขอสมัครที่ /subscribe ระบบจะแจ้งไปยังอีเมล/เบอร์นี้ เว้นว่างเพื่อปิดช่องทางนั้น', vi: 'Khi ai đó yêu cầu đăng ký trên /subscribe, cảnh báo sẽ gửi tới email/điện thoại này. Để trống để tắt kênh đó.', id: 'Ketika seseorang mengajukan langganan di /subscribe, peringatan dikirim ke email dan/atau nomor telepon ini. Kosongkan kolomnya untuk menonaktifkan kanal tersebut.' }),
    alertEmailPlaceholder: tr(language, { ko: '알림 이메일 (예: ops@sooppiy.com)', en: 'Alert email (e.g. ops@sooppiy.com)', ja: '通知メール (例: ops@sooppiy.com)', th: 'อีเมลแจ้งเตือน (เช่น ops@sooppiy.com)', vi: 'Email cảnh báo (vd: ops@sooppiy.com)', id: 'Email peringatan (mis. ops@sooppiy.com)' }),
    alertPhonePlaceholder: tr(language, { ko: '알림 전화번호 (예: +821012345678)', en: 'Alert phone (e.g. +821012345678)', ja: '通知電話 (例: +821012345678)', th: 'เบอร์แจ้งเตือน (เช่น +821012345678)', vi: 'Điện thoại cảnh báo (vd: +821012345678)', id: 'Telepon peringatan (mis. +821012345678)' }),
    alertsSave: tr(language, { ko: '알림 수신처 저장', en: 'Save alert recipients', ja: '通知先を保存', th: 'บันทึกผู้รับการแจ้งเตือน', vi: 'Lưu người nhận cảnh báo', id: 'Simpan penerima peringatan' }),
    alertsOff: tr(language, { ko: '수신처 미등록 — 새 구독 요청 알림이 발송되지 않습니다 (콘솔에는 계속 표시됨)', en: 'No recipient set — new subscription requests raise no alert (they still appear in the console)', ja: '受信先未登録 — 新しい購読リクエストの通知は送信されません（コンソールには表示されます）', th: 'ยังไม่ตั้งผู้รับ — คำขอสมัครใหม่จะไม่ส่งการแจ้งเตือน (ยังแสดงในคอนโซล)', vi: 'Chưa đặt người nhận — yêu cầu đăng ký mới không gửi cảnh báo (vẫn hiển thị trong console)', id: 'Belum ada penerima — permintaan langganan baru tidak memunculkan peringatan (tetap muncul di konsol)' }),
    trading: tr(language, { ko: '거래', en: 'Trading', ja: '取引', th: 'การเทรด', vi: 'Giao dịch', id: 'Trading' }),
    edit: tr(language, { ko: '수정', en: 'Edit', ja: '編集', th: 'แก้ไข', vi: 'Sửa', id: 'Ubah' }),
    cancelEdit: tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' }),
    clearConfirm: tr(language, { ko: '이 설정을 삭제할까요?', en: 'Delete this setting?', ja: 'この設定を削除しますか？', th: 'ลบการตั้งค่านี้?', vi: 'Xóa cài đặt này?', id: 'Hapus pengaturan ini?' }),
    activeGrants: tr(language, { ko: '부여된 플랜 (활성)', en: 'Granted plans (active)', ja: '付与済みプラン（有効）', th: 'แพลนที่ให้ (ใช้งาน)', vi: 'Gói đã cấp (đang hoạt động)', id: 'Paket yang diberikan (aktif)' }),
    cancelGrantConfirm: tr(language, { ko: '이 부여를 취소(해지)할까요?', en: 'Cancel (revoke) this grant?', ja: 'この付与を取り消しますか？', th: 'ยกเลิก (เพิกถอน) การให้สิทธิ์นี้?', vi: 'Hủy (thu hồi) khoản cấp này?', id: 'Batalkan (cabut) pemberian ini?' }),
    grantDays: tr(language, { ko: '일수', en: 'Days', ja: '日数', th: 'จำนวนวัน', vi: 'Số ngày', id: 'Hari' }),
    grantNote: tr(language, { ko: '메모 (선택)', en: 'Note (optional)', ja: 'メモ（任意）', th: 'หมายเหตุ (ไม่บังคับ)', vi: 'Ghi chú (tùy chọn)', id: 'Catatan (opsional)' }),
    grantReplaces: tr(language, { ko: '기존 활성/대기 구독은 자동으로 대체됩니다.', en: 'Replaces any existing active/pending subscription.', ja: '既存の有効・保留中の購読は自動的に置き換えられます。', th: 'จะแทนที่การสมัครที่ใช้งานอยู่หรือรออยู่เดิม', vi: 'Thay thế mọi đăng ký đang hoạt động/chờ xử lý.', id: 'Menggantikan langganan aktif/tertunda yang sudah ada.' }),
    planMgmt: tr(language, { ko: '플랜 관리', en: 'Plan management', ja: 'プラン管理', th: 'จัดการแพลน', vi: 'Quản lý gói', id: 'Manajemen paket' }),
    planMgmtHint: tr(language, { ko: '가격·이름 변경은 신규 결제부터 적용됩니다. 구독 이력이 있는 플랜은 삭제 대신 비활성화하세요.', en: 'Price/name changes apply to new payments. Plans with history deactivate instead of delete.', ja: '価格・名称の変更は新規決済から適用されます。購読履歴のあるプランは削除せず無効化してください。', th: 'การเปลี่ยนราคา/ชื่อมีผลกับการชำระเงินใหม่ แพลนที่มีประวัติให้ปิดใช้งานแทนการลบ', vi: 'Đổi giá/tên áp dụng cho thanh toán mới. Gói đã có lịch sử thì vô hiệu hóa thay vì xóa.', id: 'Perubahan harga/nama berlaku untuk pembayaran baru. Paket yang punya riwayat dinonaktifkan, bukan dihapus.' }),
    planAdd: tr(language, { ko: '플랜 추가', en: 'Add plan', ja: 'プラン追加', th: 'เพิ่มแพลน', vi: 'Thêm gói', id: 'Tambah paket' }),
    planCode: tr(language, { ko: '코드 (예: gold)', en: 'Code (e.g. gold)', ja: 'コード（例: gold）', th: 'โค้ด (เช่น gold)', vi: 'Mã (vd: gold)', id: 'Kode (mis. gold)' }),
    planName: tr(language, { ko: '이름', en: 'Name', ja: '名称', th: 'ชื่อ', vi: 'Tên', id: 'Nama' }),
    planPrice: tr(language, { ko: '월 $', en: '$/month', ja: '月額 $', th: '$ / เดือน', vi: '$ / tháng', id: '$/bulan' }),
    planSort: tr(language, { ko: '순서', en: 'Sort', ja: '順序', th: 'ลำดับ', vi: 'Thứ tự', id: 'Urutan' }),
    editName: tr(language, { ko: '이름 변경', en: 'Rename', ja: '名称変更', th: 'เปลี่ยนชื่อ', vi: 'Đổi tên', id: 'Ganti nama' }),
    editPrice: tr(language, { ko: '가격 변경', en: 'Set price', ja: '価格変更', th: 'ตั้งราคา', vi: 'Đặt giá', id: 'Tetapkan harga' }),
    planOff: tr(language, { ko: '비활성', en: 'Deactivate', ja: '無効', th: 'ปิดใช้งาน', vi: 'Vô hiệu', id: 'Nonaktifkan' }),
    planOn: tr(language, { ko: '활성', en: 'Activate', ja: '有効', th: 'เปิดใช้งาน', vi: 'Kích hoạt', id: 'Aktifkan' }),
    subscriberRows: tr(language, { ko: '구독 이력', en: 'History', ja: '履歴', th: 'ประวัติ', vi: 'Lịch sử', id: 'Riwayat' }),
    planBilling: tr(language, { ko: '결제 연동 ID', en: 'Billing IDs', ja: '決済連携ID', th: 'รหัสการชำระเงิน', vi: 'ID thanh toán', id: 'ID penagihan' }),
    editStripeId: tr(language, { ko: 'Stripe 가격 ID', en: 'Stripe price id', ja: 'Stripe価格ID', th: 'รหัสราคา Stripe', vi: 'ID giá Stripe', id: 'ID harga Stripe' }),
    billingUnset: tr(language, { ko: '미설정', en: 'not set', ja: '未設定', th: 'ยังไม่ตั้ง', vi: 'chưa đặt', id: 'belum diatur' }),
    billingHint: tr(language, {
      ko: '이 값이 비어 있으면 API 키가 올바르더라도 결제가 503으로 실패합니다. Stripe는 price_… 형식입니다(prod_… 아님).',
      en: 'While these are empty, checkout fails with 503 even when the API keys are correct. Stripe wants price_… (not prod_…).',
      ja: 'これらが空のままだと、APIキーが正しくても決済は503で失敗します。Stripeはprice_…です（prod_…ではない）。',
      th: 'หากเว้นว่างไว้ การชำระเงินจะล้มเหลวด้วย 503 แม้คีย์ API จะถูกต้อง Stripe ใช้ price_… (ไม่ใช่ prod_…)',
      vi: 'Khi để trống, thanh toán sẽ lỗi 503 dù khóa API đúng. Stripe cần price_… (không phải prod_…).',
      id: 'Selama kosong, checkout gagal dengan 503 meski kunci API benar. Stripe memakai price_… (bukan prod_…).',
    }),
    status: tr(language, { ko: '상태', en: 'Status', ja: '状態', th: 'สถานะ', vi: 'Trạng thái', id: 'Status' }),
    plan: tr(language, { ko: '플랜', en: 'Plan', ja: 'プラン', th: 'แพลน', vi: 'Gói', id: 'Paket' }),
    method: tr(language, { ko: '결제수단', en: 'Method', ja: '決済手段', th: 'ช่องทางชำระ', vi: 'Phương thức', id: 'Metode' }),
    reference: tr(language, { ko: '참조', en: 'Reference', ja: '参照', th: 'อ้างอิง', vi: 'Tham chiếu', id: 'Referensi' }),
    amount: tr(language, { ko: '금액', en: 'Amount', ja: '金額', th: 'จำนวนเงิน', vi: 'Số tiền', id: 'Jumlah' }),
    created: tr(language, { ko: '생성일', en: 'Created', ja: '作成日', th: 'วันที่สร้าง', vi: 'Ngày tạo', id: 'Dibuat' }),
    expires: tr(language, { ko: '만료일', en: 'Expires', ja: '有効期限', th: 'วันหมดอายุ', vi: 'Ngày hết hạn', id: 'Berakhir' }),
    member: tr(language, { ko: '회원', en: 'Member', ja: '会員', th: 'สมาชิก', vi: 'Thành viên', id: 'Anggota' }),
    agent: tr(language, { ko: '에이전트', en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent', id: 'Agen' }),
    contracts: tr(language, { ko: '엔터프라이즈 상담 요청', en: 'Enterprise contract requests', ja: 'エンタープライズ相談リクエスト', th: 'คำขอสัญญาองค์กร', vi: 'Yêu cầu hợp đồng doanh nghiệp', id: 'Permintaan kontrak enterprise' }),
    contacted: tr(language, { ko: '연락함', en: 'Contacted', ja: '連絡済み', th: 'ติดต่อแล้ว', vi: 'Đã liên hệ', id: 'Sudah dihubungi' }),
    closed: tr(language, { ko: '종료', en: 'Closed', ja: '終了', th: 'ปิดแล้ว', vi: 'Đã đóng', id: 'Ditutup' }),
    signups: tr(language, { ko: '일별 가입', en: 'Signups per day', ja: '日別登録', th: 'สมัครต่อวัน', vi: 'Đăng ký mỗi ngày', id: 'Pendaftaran per hari' }),
    trades: tr(language, { ko: '일별 거래', en: 'Trades per day', ja: '日別取引', th: 'เทรดต่อวัน', vi: 'Giao dịch mỗi ngày', id: 'Transaksi per hari' }),
    revenue: tr(language, { ko: '월별 매출', en: 'Revenue per month', ja: '月別売上', th: 'รายได้ต่อเดือน', vi: 'Doanh thu mỗi tháng', id: 'Pendapatan per bulan' }),
    equityCurve: tr(language, { ko: '플랫폼 자산 추이 (30일)', en: 'Platform equity (30 days)', ja: 'プラットフォーム資産推移（30日）', th: 'มูลค่าสินทรัพย์แพลตฟอร์ม (30 วัน)', vi: 'Tài sản nền tảng (30 ngày)', id: 'Ekuitas platform (30 hari)' }),
    topMembers: tr(language, { ko: '자산 상위 회원', en: 'Top members by equity', ja: '資産上位会員', th: 'สมาชิกสินทรัพย์สูงสุด', vi: 'Thành viên tài sản cao nhất', id: 'Anggota teratas berdasarkan ekuitas' }),
    runsPerDay: tr(language, { ko: '일별 자동화 실행 (14일)', en: 'Automation runs per day (14d)', ja: '日別自動化実行（14日）', th: 'การรันอัตโนมัติต่อวัน (14 วัน)', vi: 'Lượt chạy tự động mỗi ngày (14 ngày)', id: 'Run otomatisasi per hari (14 hari)' }),
    byAgent: tr(language, { ko: '에이전트별 실행 (30일)', en: 'Runs by agent (30d)', ja: 'エージェント別実行（30日）', th: 'การรันตามเอเจนต์ (30 วัน)', vi: 'Lượt chạy theo agent (30 ngày)', id: 'Run per agen (30 hari)' }),
    skipReasons: tr(language, { ko: '결과 분포 (30일)', en: 'Outcome breakdown (30d)', ja: '結果分布（30日）', th: 'สัดส่วนผลลัพธ์ (30 วัน)', vi: 'Phân bố kết quả (30 ngày)', id: 'Rincian hasil (30 hari)' }),
    rules: tr(language, { ko: '자동화 규칙', en: 'Automation rules', ja: '自動化ルール', th: 'กฎอัตโนมัติ', vi: 'Quy tắc tự động', id: 'Aturan otomatisasi' }),
    replies: tr(language, { ko: '답글', en: 'Replies', ja: '返信', th: 'การตอบกลับ', vi: 'Trả lời', id: 'Balasan' }),
    exclude: tr(language, { ko: '리더보드 제외', en: 'Exclude', ja: 'リーダーボード除外', th: 'ยกเว้นจากลีดเดอร์บอร์ด', vi: 'Loại khỏi bảng xếp hạng', id: 'Kecualikan' }),
    include: tr(language, { ko: '제외 해제', en: 'Include', ja: '除外解除', th: 'ยกเลิกการยกเว้น', vi: 'Đưa lại vào', id: 'Sertakan' }),
    refreshNow: tr(language, { ko: '지금 갱신', en: 'Refresh now', ja: '今すぐ更新', th: 'รีเฟรชตอนนี้', vi: 'Làm mới ngay', id: 'Muat ulang sekarang' }),
    exclusions: tr(language, { ko: '제외 목록', en: 'Exclusions', ja: '除外リスト', th: 'รายการที่ยกเว้น', vi: 'Danh sách loại trừ', id: 'Pengecualian' }),
    reason: tr(language, { ko: '사유', en: 'Reason', ja: '理由', th: 'เหตุผล', vi: 'Lý do', id: 'Alasan' }),
    addAdmin: tr(language, { ko: '관리자 추가', en: 'Add admin', ja: '管理者追加', th: 'เพิ่มผู้ดูแล', vi: 'Thêm quản trị viên', id: 'Tambah admin' }),
    role: tr(language, { ko: '역할', en: 'Role', ja: '役割', th: 'บทบาท', vi: 'Vai trò', id: 'Peran' }),
    disable: tr(language, { ko: '비활성화', en: 'Disable', ja: '無効化', th: 'ปิดใช้งาน', vi: 'Vô hiệu hóa', id: 'Nonaktifkan' }),
    enable: tr(language, { ko: '활성화', en: 'Enable', ja: '有効化', th: 'เปิดใช้งาน', vi: 'Bật', id: 'Aktifkan' }),
    resetPw: tr(language, { ko: '비밀번호 재설정', en: 'Reset password', ja: 'パスワード再設定', th: 'รีเซ็ตรหัสผ่าน', vi: 'Đặt lại mật khẩu', id: 'Atur ulang kata sandi' }),
    lastLogin: tr(language, { ko: '마지막 로그인', en: 'Last login', ja: '最終ログイン', th: 'เข้าสู่ระบบล่าสุด', vi: 'Đăng nhập cuối', id: 'Login terakhir' }),
    action: tr(language, { ko: '작업', en: 'Action', ja: '操作', th: 'การกระทำ', vi: 'Hành động', id: 'Aksi' }),
    target: tr(language, { ko: '대상', en: 'Target', ja: '対象', th: 'เป้าหมาย', vi: 'Đối tượng', id: 'Target' }),
    time: tr(language, { ko: '시각', en: 'Time', ja: '時刻', th: 'เวลา', vi: 'Thời gian', id: 'Waktu' }),
    tabSkills: tr(language, { ko: '트레이딩 스킬', en: 'Trading skills', ja: 'トレーディングスキル', th: 'ทักษะการเทรด', vi: 'Kỹ năng giao dịch', id: 'Keterampilan trading' }),
    skillsTitle: tr(language, { ko: '🧭 트레이딩 스킬 — 데스크가 읽는 하우스 의사결정 방법론', en: '🧭 Trading skills — house decision methods the desk reads', ja: '🧭 トレーディングスキル — デスクが読むハウス意思決定手法', th: '🧭 ทักษะการเทรด — วิธีการตัดสินใจของบริษัทที่เดสก์อ่าน', vi: '🧭 Kỹ năng giao dịch — phương pháp quyết định mà bàn giao dịch đọc', id: '🧭 Keterampilan trading — metode keputusan internal yang dibaca desk' }),
    skillsHint: tr(language, { ko: '스킬 본문은 AI 의사결정 프롬프트(light·trader·verifier·planner)에 주입됩니다. 저장 후 약 30초 안에 트레이딩 워커에 반영됩니다. 기본(base) 스킬은 수정·비활성화·기본값 복원만 가능하고 삭제할 수 없습니다.', en: 'Skill bodies are injected into the AI decision prompts (light · trader · verifier · planner). Changes reach the trading worker within ~30 s. Base skills can be edited, disabled, or reset to defaults — never deleted.', ja: 'スキル本文はAI意思決定プロンプト（light・trader・verifier・planner）に注入されます。保存後約30秒でトレーディングワーカーに反映されます。基本（base）スキルは編集・無効化・既定値への復元のみ可能で、削除はできません。', th: 'เนื้อหาทักษะจะถูกแทรกเข้าไปในพรอมป์การตัดสินใจของ AI (light · trader · verifier · planner) การเปลี่ยนแปลงจะมีผลกับเวิร์กเกอร์ภายใน ~30 วินาที ทักษะพื้นฐาน (base) แก้ไข ปิดใช้งาน หรือคืนค่าเริ่มต้นได้ แต่ลบไม่ได้', vi: 'Nội dung kỹ năng được đưa vào các prompt quyết định của AI (light · trader · verifier · planner). Thay đổi có hiệu lực với worker trong ~30 giây. Kỹ năng cơ bản (base) có thể sửa, tắt hoặc khôi phục mặc định — không bao giờ xóa được.', id: 'Isi keterampilan disuntikkan ke prompt keputusan AI (light · trader · verifier · planner). Perubahan berlaku di worker dalam ~30 detik. Keterampilan dasar (base) bisa diedit, dinonaktifkan, atau dikembalikan ke bawaan — tidak pernah bisa dihapus.' }),
    skillNew: tr(language, { ko: '스킬 추가', en: 'Add skill', ja: 'スキル追加', th: 'เพิ่มทักษะ', vi: 'Thêm kỹ năng', id: 'Tambah keterampilan' }),
    skillEditTitle: tr(language, { ko: '스킬 편집', en: 'Edit skill', ja: 'スキル編集', th: 'แก้ไขทักษะ', vi: 'Sửa kỹ năng', id: 'Edit keterampilan' }),
    skillName: tr(language, { ko: '이름', en: 'Name', ja: '名前', th: 'ชื่อ', vi: 'Tên', id: 'Nama' }),
    skillDesc: tr(language, { ko: '설명 (한 줄)', en: 'Description (one line)', ja: '説明（1行）', th: 'คำอธิบาย (หนึ่งบรรทัด)', vi: 'Mô tả (một dòng)', id: 'Deskripsi (satu baris)' }),
    skillBody: tr(language, { ko: '본문 — 프롬프트에 그대로 주입되는 방법론 텍스트', en: 'Body — the method text injected verbatim into the prompt', ja: '本文 — プロンプトへそのまま注入される手法テキスト', th: 'เนื้อหา — ข้อความวิธีการที่ถูกแทรกเข้าพรอมป์โดยตรง', vi: 'Nội dung — văn bản phương pháp được đưa nguyên văn vào prompt', id: 'Isi — teks metode yang disuntikkan apa adanya ke prompt' }),
    skillPrompts: tr(language, { ko: '적용 프롬프트', en: 'Prompt sites', ja: '適用プロンプト', th: 'พรอมป์ที่ใช้', vi: 'Prompt áp dụng', id: 'Situs prompt' }),
    skillMarkets: tr(language, { ko: '시장', en: 'Markets', ja: '市場', th: 'ตลาด', vi: 'Thị trường', id: 'Pasar' }),
    skillMarketsPh: tr(language, { ko: '쉼표 구분, 비우면 모든 시장 (예: crypto, us-stock)', en: 'comma-separated, empty = all markets (e.g. crypto, us-stock)', ja: 'カンマ区切り、空欄＝全市場（例: crypto, us-stock）', th: 'คั่นด้วยจุลภาค เว้นว่าง = ทุกตลาด (เช่น crypto, us-stock)', vi: 'phân cách bằng dấu phẩy, trống = mọi thị trường (vd: crypto, us-stock)', id: 'dipisah koma, kosong = semua pasar (mis. crypto, us-stock)' }),
    skillAllMarkets: tr(language, { ko: '모든 시장', en: 'all markets', ja: '全市場', th: 'ทุกตลาด', vi: 'mọi thị trường', id: 'semua pasar' }),
    skillPriority: tr(language, { ko: '우선순위 (낮을수록 먼저)', en: 'Priority (lower = first)', ja: '優先度（小さいほど先）', th: 'ลำดับ (น้อย = ก่อน)', vi: 'Ưu tiên (thấp = trước)', id: 'Prioritas (kecil = duluan)' }),
    skillReset: tr(language, { ko: '기본값 복원', en: 'Reset to default', ja: '既定値に戻す', th: 'คืนค่าเริ่มต้น', vi: 'Khôi phục mặc định', id: 'Kembalikan bawaan' }),
    skillResetConfirm: tr(language, { ko: '이 기본 스킬을 출고 기본값으로 복원할까요? 현재 편집 내용은 사라집니다.', en: 'Restore this base skill to its shipped default? Current edits are lost.', ja: 'この基本スキルを出荷時の既定値に戻しますか？現在の編集内容は失われます。', th: 'คืนทักษะพื้นฐานนี้เป็นค่าเริ่มต้นจากโรงงานหรือไม่ การแก้ไขปัจจุบันจะหายไป', vi: 'Khôi phục kỹ năng cơ bản này về mặc định gốc? Chỉnh sửa hiện tại sẽ mất.', id: 'Kembalikan keterampilan dasar ini ke bawaan pabrik? Editan saat ini akan hilang.' }),
    skillDelConfirm: tr(language, { ko: '이 커스텀 스킬을 삭제할까요?', en: 'Delete this custom skill?', ja: 'このカスタムスキルを削除しますか？', th: 'ลบทักษะที่กำหนดเองนี้หรือไม่', vi: 'Xóa kỹ năng tùy chỉnh này?', id: 'Hapus keterampilan kustom ini?' }),
    save: tr(language, { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu', id: 'Simpan' }),
    cancel: tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' }),
  }

  const hdr = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }

  async function call(path: string, opts: RequestInit = {}) {
    const used = token
    const r = await fetch(`${API_BASE}/admin/${path}`, { headers: hdr, ...opts })
    if (r.status === 401) {
      // Only kill the session when the 401 belongs to the CURRENT token — a
      // stale in-flight request resolving late must not log out a fresh login.
      if (localStorage.getItem(ADMIN_TOKEN_KEY) === used) {
        localStorage.removeItem(ADMIN_TOKEN_KEY)
        setToken(''); setMe(null); setError(T.sessionExpired)
      }
      throw new Error('401')
    }
    if (!r.ok) {
      const body = await r.json().catch(() => null)
      throw new Error(body?.detail || String(r.status))
    }
    return r.json()
  }

  async function login() {
    setError(''); setLoggingIn(true)
    const r = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!r.ok) { setError(T.invalid); setLoggingIn(false); return }
    const body = await r.json()
    localStorage.setItem(ADMIN_TOKEN_KEY, body.token)
    setToken(body.token)
    setMe({ id: body.admin_id, email: body.email, role: body.role })
    setPassword('')
    setLoggingIn(false)
  }

  async function logout() {
    try { await fetch(`${API_BASE}/admin/logout`, { method: 'POST', headers: hdr }) } catch { /* ignore */ }
    localStorage.removeItem(ADMIN_TOKEN_KEY)
    setToken(''); setMe(null)
  }

  useEffect(() => {
    if (!token) return
    call('me').then(setMe).catch(() => { /* handled in call */ })
  }, [token])

  async function refresh(which: Tab = tab) {
    if (!token) return
    setError('')
    try {
      if (which === 'dashboard') {
        setAnalytics(await call('analytics'))
        setOverview(await call('overview'))
      }
      if (which === 'members') {
        setUsers(await call('users?limit=200'))
        setAgents(await call(`agents?q=${encodeURIComponent(q)}&limit=100`))
        // The add-member form offers a plan, so this tab needs the plan list too.
        const mp = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
        setPlanList(mp.plans || [])
      }
      if (which === 'subscriptions') {
        setSubs(await call(`subscriptions?status=${encodeURIComponent(subFilter)}&limit=100`))
        setContracts(await call('contracts?limit=100'))
        setAdminPlans((await call('plans')).plans || [])
        const p = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
        setPlanList(p.plans || [])
        const pay = await call('settings/payment')
        setPaySettings(pay)
        setUsdtAddr(pay?.usdt_address?.value || '')
        setUsdtNet(pay?.usdt_network?.value || 'TRC20')
        setBankInfo(pay?.bank_transfer_info?.value || '')
        const al = await call('settings/alerts')
        setAlertSettings(al)
        setAlertEmail(al?.admin_alert_email?.value || '')
        setAlertPhone(al?.admin_alert_phone?.value || '')
      }
      if (which === 'assets') setAssets(await call('stats/assets'))
      if (which === 'positions') setPositions(await call('stats/positions'))
      if (which === 'automation') {
        setAutoStats(await call('stats/automation'))
        setAutoRules(await call('automation?limit=100'))
        // Plan 21 P3: crypto composite rides the public regime payload.
        try { setRegimeRead(await (await fetch('/api/market-intel/regime')).json()) } catch { /* advisory card only */ }
        try { setTrendAccounts(await call('settings/trend-accounts')) } catch { /* card stays hidden */ }
        const llm = await call('settings/llm')
        setLlmSettings(llm)
        const s = llm?.settings || {}
        setLlmForm({
          local_base_url: s.llm_local_base_url?.value || '',
          local_model: s.llm_local_model?.value || '',
          brief_provider: s.llm_brief_provider?.value || '',
          brief_model: s.llm_brief_model?.value || '',
          decision_provider: s.llm_decision_provider?.value || '',
          decision_model: s.llm_decision_model?.value || '',
        })
      }
      if (which === 'feeds') setFeedStatus(await call('swing-feeds/status'))
      if (which === 'crawl') {
        setCrawlOverview(await call('crawl/overview'))
        setCrawlRuns((await call(`crawl/runs?limit=80${crawlFeed ? `&feed=${encodeURIComponent(crawlFeed)}` : ''}`)).runs || [])
        setCrawlDecisions((await call('crawl/decisions')).decisions || [])
      }
      if (which === 'skills') setSkills((await call('skills')).skills || [])
      if (which === 'support') setThreads(await call('support/threads?limit=200'))
      if (which === 'discussions') setDiscussions(await call(`discussions?q=${encodeURIComponent(dq)}&limit=100`))
      if (which === 'leaderboard') setLeaderboard(await call(`leaderboard?metric=${lbMetric}&limit=100`))
      if (which === 'admins') setAdmins(await call('admins'))
      if (which === 'audit') setAudit(await call('audit?limit=200'))
    } catch (e: any) {
      if (e?.message !== '401') setError(String(e?.message || e))
    }
  }

  useEffect(() => { refresh(tab) }, [tab, token, subFilter, lbMetric, crawlFeed])

  // Paint the whole viewport (not just the centered column) in the design-doc
  // background; restore on unmount.
  useEffect(() => {
    const prev = document.body.style.background
    document.body.style.background = '#17150f'
    return () => { document.body.style.background = prev }
  }, [])

  // Returns true only when the write succeeded — callers must not clear a typed
  // reply/broadcast composer on failure, or the admin loses what they wrote.
  async function act(path: string, opts: RequestInit, then: Tab): Promise<boolean> {
    setError(''); setActBusy(true)
    try { await call(path, opts); await refresh(then); return true }
    catch (e: any) { if (e?.message !== '401') setError(String(e?.message || e)); return false }
    finally { setActBusy(false) }
  }

  // ── Login screen ──
  if (!token) {
    return (
      <div style={{ maxWidth: 420, margin: '80px auto', padding: 24 }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>🔐 {T.title}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)', marginBottom: 16 }}>{T.loginHint}</p>
        <input placeholder={T.email} value={email} onChange={e => setEmail(e.target.value)}
          style={{ ...inputStyle, width: '100%', marginBottom: 10 }} autoComplete="username" />
        <input placeholder={T.password} type="password" value={password} onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && login()}
          style={{ ...inputStyle, width: '100%', marginBottom: 14 }} autoComplete="current-password" />
        {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>⚠️ {error}</div>}
        <button onClick={login} disabled={loggingIn} style={{ ...primaryBtn, width: '100%', padding: '10px 20px', opacity: loggingIn ? 0.6 : 1 }}>{loggingIn ? '⏳ ' : ''}{T.signIn}</button>
      </div>
    )
  }

  const tabs: [Tab, string][] = [
    ['dashboard', T.tabDashboard], ['members', T.tabMembers], ['subscriptions', T.tabSubs],
    ['assets', T.tabAssets], ['positions', T.tabPositions], ['automation', T.tabAutomation],
    ['feeds', T.tabFeeds], ['crawl', T.tabCrawl], ['skills', T.tabSkills], ['support', T.tabSupport],
    ['discussions', T.tabDiscussions], ['leaderboard', T.tabLeaderboard],
    ...(me?.role === 'superadmin' ? [['admins', T.tabAdmins] as [Tab, string]] : []),
    ['audit', T.tabAudit],
  ]

  const ov = overview?.overview
  const subStatusColor = (s: string) =>
    s === 'active' ? '#22c55e' : s === 'pending' ? '#eab308' : s === 'rejected' ? '#ef4444' : 'var(--text-muted,#8a8073)'

  // Per-user trading mode badge — colours mirror the design doc: live is red
  // (real money), shadow amber, simulator neutral, no rules a muted dash.
  const tradingBadge = (mode: string | null | undefined) => {
    const spec: Record<string, [string, string]> = {
      live: ['🔴 Live', '#ef4444'],
      shadow: ['🟡 Shadow', '#eab308'],
      simulator: ['⚪ Simulator', 'var(--text-muted,#8a8073)'],
    }
    const [label, color] = spec[mode || ''] || ['—', 'var(--text-muted,#8a8073)']
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 12, fontWeight: 700,
        color, border: `1px solid ${mode && spec[mode] ? color : 'var(--border-color,#2a2a28)'}`,
        borderRadius: 7, padding: '2px 8px', whiteSpace: 'nowrap' }}>{label}</span>
    )
  }

  // Saved-row for the Subscriptions tab: shows a persisted value with Edit /
  // Delete, so a saved setting reads as an applied record rather than a form.
  const appliedRow = (primary: any, meta: any, onEdit: () => void, onDelete: () => void) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px',
      border: '1px solid var(--border-color,#332d22)', borderRadius: 8,
      background: 'var(--bg-primary,#1b1811)' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontFamily: 'ui-monospace, monospace', fontSize: 13,
          wordBreak: 'break-all', whiteSpace: 'pre-line' }}>{primary}</div>
        {meta && <div style={{ fontSize: 11, color: 'var(--text-muted,#a49b8a)', marginTop: 3 }}>{meta}</div>}
      </div>
      <button style={actionBtn} onClick={onEdit}>{T.edit}</button>
      <button style={dangerBtn} onClick={onDelete}>{T.del}</button>
    </div>
  )

  // Design-doc palette (docs/admin-alerts-trading-mode-design.html, dark) applied
  // as CSS variables on the console root so every `var(--x, fallback)` style below
  // resolves to the warm gold/cream theme. The body background is set to match so
  // the full viewport (not just the centered column) picks it up.
  const themeVars: any = {
    '--bg-primary': '#1b1811', '--bg-secondary': '#211d16', '--border-color': '#332d22',
    '--accent-primary': '#d8a95e', '--text-primary': '#ece7dc', '--text-muted': '#a49b8a',
    background: '#17150f', color: '#ece7dc', minHeight: '100vh',
  }

  return (
    // The console renders on its own domain with no top nav above it, so the
    // heading sat 24px from the viewport edge and read as clipped. Give it real
    // breathing room at the top. themeVars restyles the whole console to the
    // design-doc palette (dark, warm gold/cream).
    <div style={{ ...themeVars, maxWidth: 1200, margin: '0 auto', padding: '48px 16px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>🔐 {T.title}</h1>
        <span style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)' }}>{me?.email} · {me?.role}</span>
        <button onClick={logout} style={{ ...actionBtn, marginLeft: 'auto' }}>{T.signOut}</button>
      </div>
      <div style={{ display: 'flex', gap: 8, margin: '14px 0', flexWrap: 'wrap' }}>
        {tabs.map(([key, label]) => (
          <button key={key} style={chip(tab === key)} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>
      {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>⚠️ {error}</div>}
      {/* Floating write-status chip: visible no matter how deep the pressed
          button sits. Shows in-flight, then sticks around on failure. */}
      {(actBusy || error) && (
        <div style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 900,
          padding: '9px 14px', borderRadius: 9, fontSize: 12.5, maxWidth: 360,
          background: actBusy ? 'rgba(40,38,30,0.92)' : 'rgba(90,26,26,0.94)',
          color: '#fff', boxShadow: '0 4px 14px rgba(0,0,0,0.35)' }}>
          {actBusy ? '⏳ …' : `⚠️ ${error}`}
        </div>
      )}

      {/* ── Dashboard ── */}
      {tab === 'dashboard' && analytics && ov && (
        <>
          <StatCards items={[
            [tr(language, { ko: '전체 회원', en: 'Total members', ja: '総会員数', th: 'สมาชิกทั้งหมด', vi: 'Tổng thành viên', id: 'Total anggota' }), analytics.total_users],
            [tr(language, { ko: '활성 구독', en: 'Active subscriptions', ja: '有効な購読', th: 'การสมัครที่ใช้งาน', vi: 'Đăng ký đang hoạt động', id: 'Langganan aktif' }), analytics.active_subscriptions],
            [tr(language, { ko: '에이전트', en: 'Agents', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent', id: 'Agen' }), ov.agents],
            [tr(language, { ko: '거래', en: 'Trades', ja: '取引', th: 'การเทรด', vi: 'Giao dịch', id: 'Transaksi' }), ov.trades],
            [tr(language, { ko: '미결제 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะที่เปิดอยู่', vi: 'Vị thế đang mở', id: 'Posisi terbuka' }), ov.open_positions],
            [tr(language, { ko: '자동화 규칙 (활성)', en: 'Automation rules (on)', ja: '自動化ルール（有効）', th: 'กฎอัตโนมัติ (เปิด)', vi: 'Quy tắc tự động (bật)', id: 'Aturan otomatisasi (aktif)' }), `${ov.automation_rules} (${ov.automation_rules_enabled})`],
            [tr(language, { ko: '토론', en: 'Discussions', ja: '議論', th: 'กระทู้', vi: 'Thảo luận', id: 'Diskusi' }), ov.discussions],
            [tr(language, { ko: '모의 자금 합계', en: 'Total sim cash', ja: 'シミュレーション資金合計', th: 'เงินจำลองรวม', vi: 'Tổng tiền mô phỏng', id: 'Total kas simulasi' }), fmtMoney(ov.total_sim_cash)],
          ]} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 12 }}>
            <div><div style={sectionTitle}>{T.signups}</div>
              <TrendChart data={analytics.signups_by_day} xKey="day" series={[['c', '#c26a45']]} /></div>
            <div><div style={sectionTitle}>{T.trades}</div>
              <TrendChart data={analytics.trades_by_day} xKey="day" series={[['c', '#22c55e']]} /></div>
            <div><div style={sectionTitle}>{T.revenue}</div>
              <TrendChart data={analytics.revenue_by_month} xKey="month" series={[['revenue', '#c26a45']]} kind="bar" /></div>
          </div>
          <div style={sectionTitle}>{tr(language, { ko: '플랜별 구독 현황', en: 'Subscriptions by plan', ja: 'プラン別購読状況', th: 'การสมัครตามแพลน', vi: 'Đăng ký theo gói', id: 'Langganan per paket' })}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 480 }}>
              <thead><tr><th style={th}>{T.plan}</th><th style={th}>{T.status}</th><th style={th}>#</th></tr></thead>
              <tbody>
                {(analytics.subscriptions_matrix || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.plan_code}</td>
                    <td style={{ ...td, color: subStatusColor(r.status) }}>{r.status}</td><td style={td}>{r.c}</td></tr>
                ))}
                {!(analytics.subscriptions_matrix || []).length && <tr><td style={td} colSpan={3}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Members ── */}
      {tab === 'members' && (
        <>
          {/* Add a member by hand — accounts sold or comped offline. No password
              is chosen here: the member sets their own from the emailed code. */}
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>＋ {T.addMember}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#a49b8a)', marginBottom: 10 }}>{T.addMemberHint}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input placeholder={T.email} value={newMember.email} type="email"
                onChange={e => setNewMember(p => ({ ...p, email: e.target.value }))}
                style={{ ...inputStyle, width: 240 }} />
              <select value={newMember.lang} onChange={e => setNewMember(p => ({ ...p, lang: e.target.value }))}
                style={inputStyle} title={T.memberLang}>
                {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
              <select value={newMember.plan_code} onChange={e => setNewMember(p => ({ ...p, plan_code: e.target.value }))} style={inputStyle}>
                <option value="">{T.planNone}</option>
                {planList.map((p: any) => (
                  <option key={p.code} value={p.code}>{p.name || p.code}</option>
                ))}
              </select>
              {newMember.plan_code && (
                <input placeholder={T.grantDays} value={newMember.days} inputMode="numeric"
                  onChange={e => setNewMember(p => ({ ...p, days: e.target.value }))}
                  style={{ ...inputStyle, width: 80 }} />
              )}
              <button style={primaryBtn} disabled={!newMember.email.trim()}
                onClick={async () => {
                  setError(''); setInvite(null)
                  try {
                    const res = await call('members', {
                      method: 'POST',
                      body: JSON.stringify({
                        email: newMember.email.trim(), lang: newMember.lang,
                        plan_code: newMember.plan_code,
                        days: parseInt(newMember.days, 10) || 30,
                      }),
                    })
                    setInvite(res)
                    setNewMember(p => ({ ...p, email: '' }))
                    await refresh('members')
                  } catch (e: any) {
                    if (e?.message !== '401') setError(String(e?.message || e))
                  }
                }}>{T.addMemberBtn}</button>
            </div>
            {invite && (
              <div style={{ fontSize: 12, marginTop: 10, color: invite.invite_sent ? '#22c55e' : '#eab308' }}>
                {invite.invite_sent ? `✓ ${invite.email} — ${T.inviteSent}` : `⚠️ ${invite.email} — ${T.inviteFailed}`}
              </div>
            )}
          </div>

          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.email}</th><th style={th}>{T.status}</th><th style={th}>{T.plan}</th><th style={th}>{T.trading}</th><th style={th}>MFA</th><th style={th}>{T.agent}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(users?.users || []).map((u: any) => (
                  <Fragment key={u.id}>
                    <tr>
                      <td style={td}>{u.id}</td><td style={{ ...td, fontWeight: 600 }}>{u.email}</td>
                      <td style={{ ...td, color: u.status === 'suspended' ? '#ef4444' : '#22c55e' }}>{u.status}</td>
                      <td style={td}>{u.plan_code || '—'}</td>
                      <td style={td}>{tradingBadge(u.trading_mode)}</td>
                      <td style={td}>{u.mfa_enabled ? '✓' : '—'}</td>
                      {/* A member can own several agents. One row per member,
                          agents in the sub-table below — the list used to
                          repeat the member once per agent. */}
                      <td style={td}>
                        {u.agent_count
                          ? <button style={actionBtn}
                              onClick={() => setOpenAgents(p => ({ ...p, [u.id]: !p[u.id] }))}>
                              {openAgents[u.id] ? '▾' : '▸'} {T.agentsCount(u.agent_count)}
                            </button>
                          : <span style={{ color: 'var(--text-muted,#8a8073)' }}>—</span>}
                      </td>
                      <td style={td}>{fmtDate(u.created_at)}</td>
                      <td style={{ ...td, whiteSpace: 'nowrap' }}>
                        <button style={actionBtn} onClick={async () => {
                          setMemberDetail(null)
                          try { setMemberDetail(await call(`members/${u.id}`)) } catch { /* handled */ }
                        }}>{T.detail}</button>{' '}
                        {u.status === 'suspended'
                          ? <button style={actionBtn} onClick={() => act(`members/${u.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'active' }) }, 'members')}>{T.activate}</button>
                          : <button style={dangerBtn} onClick={() => act(`members/${u.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'suspended' }) }, 'members')}>{T.suspend}</button>}{' '}
                        <button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`users/${u.id}`, { method: 'DELETE' }, 'members')}>{T.del}</button>{' '}
                        <button style={dangerBtn} onClick={() => {
                          const amt = window.prompt(T.resetCapPrompt, '10000')
                          if (amt === null) return
                          const v = Number(amt)
                          if (!Number.isFinite(v) || v <= 0) { setError(T.resetCapBad); return }
                          if (window.confirm(T.resetCapConfirm(u.email, v)))
                            act(`members/${u.id}/reset-capital`, { method: 'POST', body: JSON.stringify({ amount: v }) }, 'members')
                        }}>{T.resetCap}</button>
                      </td>
                    </tr>
                    {openAgents[u.id] && (
                      <tr>
                        <td style={{ ...td, padding: '4px 10px 12px 34px' }} colSpan={9}>
                          <table style={{ width: '100%', borderCollapse: 'collapse',
                            border: '1px solid var(--border-color,#332d22)', borderRadius: 8 }}>
                            <thead><tr><th style={th}>ID</th><th style={th}>{T.agent}</th><th style={th}>Cash</th><th style={th}>Points</th><th style={th}>Trades</th><th style={th}>{T.tabPositions}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
                            <tbody>
                              {(u.agents || []).map((a: any) => (
                                <tr key={a.id}>
                                  <td style={td}>{a.id}</td>
                                  <td style={{ ...td, fontWeight: 600 }}>{a.name}</td>
                                  <td style={td}>{fmtMoney(a.cash)}</td>
                                  <td style={td}>{a.points}</td>
                                  <td style={td}>{a.trade_count}</td>
                                  <td style={td}>{a.open_positions}</td>
                                  <td style={td}>{fmtDate(a.created_at)}</td>
                                  <td style={td}><button style={dangerBtn}
                                    onClick={() => window.confirm(T.delConfirm) && act(`agents/${a.id}`, { method: 'DELETE' }, 'members')}>{T.del}</button></td>
                                </tr>
                              ))}
                              {!(u.agents || []).length && <tr><td style={td} colSpan={8}>{T.noAgents}</td></tr>}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!(users?.users || []).length && <tr><td style={td} colSpan={9}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>

          {memberDetail && (
            <div style={{ ...card, marginTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <strong style={{ fontSize: 14 }}>{memberDetail.user.email}</strong>
                <span style={{ fontSize: 12, color: subStatusColor(memberDetail.user.status === 'active' ? 'active' : 'rejected') }}>{memberDetail.user.status}</span>
                <button style={{ ...actionBtn, marginLeft: 'auto' }} onClick={() => setMemberDetail(null)}>{T.close}</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 12, marginTop: 12 }}>
                <div>
                  <div style={sectionTitle}>{tr(language, { ko: '구독 이력', en: 'Subscription history', ja: '購読履歴', th: 'ประวัติการสมัคร', vi: 'Lịch sử đăng ký', id: 'Riwayat langganan' })}</div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead><tr><th style={th}>{T.plan}</th><th style={th}>{T.status}</th><th style={th}>{T.method}</th><th style={th}>{T.expires}</th></tr></thead>
                    <tbody>
                      {(memberDetail.subscriptions || []).map((s: any) => (
                        <tr key={s.id}><td style={td}>{s.plan_code}</td>
                          <td style={{ ...td, color: subStatusColor(s.status) }}>{s.status}</td>
                          <td style={td}>{s.method}</td><td style={td}>{fmtDate(s.expires_at)}</td></tr>
                      ))}
                      {!(memberDetail.subscriptions || []).length && <tr><td style={td} colSpan={4}>{T.noData}</td></tr>}
                    </tbody>
                  </table>
                </div>
                <div>
                  <div style={sectionTitle}>{tr(language, { ko: '자산 추이', en: 'Equity history', ja: '資産推移', th: 'ประวัติสินทรัพย์', vi: 'Lịch sử tài sản', id: 'Riwayat ekuitas' })}</div>
                  {/* Snapshots are per agent and not on a shared clock, so they
                      cannot be summed — say whose curve this is. */}
                  {(memberDetail.agents || []).length > 1 && memberDetail.equity_agent_name && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted,#a49b8a)', marginBottom: 6 }}>
                      {T.equityOfAgent}: {memberDetail.equity_agent_name}
                    </div>
                  )}
                  <TrendChart data={memberDetail.equity_history || []} xKey="recorded_at" series={[['total_value', '#c26a45']]} />
                </div>
              </div>
              <div style={sectionTitle}>{tr(language, { ko: '보유 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะที่เปิดอยู่', vi: 'Vị thế đang mở', id: 'Posisi terbuka' })} ({(memberDetail.positions || []).length})</div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>{T.agent}</th><th style={th}>Symbol</th><th style={th}>Side</th><th style={th}>Qty</th><th style={th}>Entry</th><th style={th}>Now</th></tr></thead>
                <tbody>
                  {(memberDetail.positions || []).slice(0, 10).map((p: any, i: number) => (
                    <tr key={i}><td style={td}>{p.agent_name || '—'}</td>
                      <td style={{ ...td, fontWeight: 600 }}>{p.symbol}</td><td style={td}>{p.side}</td>
                      <td style={td}>{p.quantity}</td><td style={td}>{p.entry_price}</td><td style={td}>{p.current_price ?? '—'}</td></tr>
                  ))}
                  {!(memberDetail.positions || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {/* Kept alongside the per-member sub-tables above: this one is
              searchable and also covers agents with no member behind them
              (self-registered claw agents), which a per-member view cannot. */}
          <div style={sectionTitle}>{tr(language, { ko: '에이전트 계정 — 활성', en: 'Agent accounts — active', ja: 'エージェントアカウント — アクティブ', th: 'บัญชีเอเจนต์ — ใช้งานอยู่', vi: 'Tài khoản agent — đang hoạt động', id: 'Akun agen — aktif' })}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted,#a49b8a)', marginBottom: 10 }}>
            {tr(language, { ko: '거래 이력 또는 보유 포지션이 있는 활성 에이전트만 표시합니다(회원 미연결 포함). 회원별 에이전트는 위 표에서 펼쳐 보세요.', en: 'Only active agents — ones with at least one trade or an open position (including agents not linked to a member). For a member\'s own agents, expand their row above.', ja: '取引履歴か保有ポジションのあるアクティブなエージェントのみ表示します（会員に紐づかないものも含む）。会員ごとのエージェントは上の表を展開してください。', th: 'แสดงเฉพาะเอเจนต์ที่ใช้งานอยู่ — มีการซื้อขายหรือมีโพซิชันเปิดอยู่ (รวมเอเจนต์ที่ไม่ผูกกับสมาชิก) สำหรับเอเจนต์ของสมาชิก ให้กางแถวด้านบน', vi: 'Chỉ hiển thị agent đang hoạt động — có ít nhất một giao dịch hoặc vị thế đang mở (gồm cả agent không gắn với thành viên). Xem agent của từng thành viên bằng cách mở rộng hàng phía trên.', id: 'Hanya agen aktif — punya minimal satu transaksi atau posisi terbuka (termasuk agen yang tidak terkait anggota). Untuk agen milik anggota, buka barisnya di tabel atas.' })}
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder={T.search} value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && refresh('members')} style={{ ...inputStyle, width: 260 }} />
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.agent}</th><th style={th}>Cash</th><th style={th}>Points</th><th style={th}>Trades</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(agents?.agents || []).map((a: any) => (
                  <tr key={a.id}>
                    <td style={td}>{a.id}</td><td style={{ ...td, fontWeight: 600 }}>{a.name}</td>
                    <td style={td}>{fmtMoney(a.cash)}</td><td style={td}>{a.points}</td>
                    <td style={td}>{a.trade_count}</td><td style={td}>{fmtDate(a.created_at)}</td>
                    <td style={td}><button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`agents/${a.id}`, { method: 'DELETE' }, 'members')}>{T.del}</button></td>
                  </tr>
                ))}
                {!(agents?.agents || []).length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Subscriptions ── */}
      {tab === 'subscriptions' && (
        <>
          {/* USDT receiving address — registered here rather than in .env so it
              can be rotated without a deploy. Subscribers are told to send real
              money to whatever is saved here, so the field is deliberately
              blunt about that. */}
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>₮ {T.usdtTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>
              {T.usdtHint}
            </div>
            {paySettings?.usdt_address?.value && !editUsdt ? (
              appliedRow(
                `${paySettings.usdt_network?.value || usdtNet} · ${paySettings.usdt_address.value}`,
                <>✓ {T.usdtLive}
                  {paySettings.usdt_address.source === 'env' && ` · ${T.usdtFromEnv}`}
                  {paySettings.usdt_address.updated_by && ` · ${paySettings.usdt_address.updated_by}`}
                  {paySettings.usdt_address.updated_at && ` · ${fmtDate(paySettings.usdt_address.updated_at)}`}</>,
                () => { setUsdtAddr(paySettings.usdt_address.value); setEditUsdt(true) },
                async () => { if (!window.confirm(T.clearConfirm)) return
                  setUsdtAddr('')
                  await act('settings/payment', { method: 'PUT',
                    body: JSON.stringify({ usdt_address: '', usdt_network: usdtNet }) }, 'subscriptions') },
              )
            ) : (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <select value={usdtNet} onChange={e => setUsdtNet(e.target.value)} style={inputStyle}>
                  {(paySettings?.networks || ['TRC20']).map((n: string) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
                <input placeholder={T.usdtAddrPlaceholder} value={usdtAddr}
                  onChange={e => setUsdtAddr(e.target.value)}
                  style={{ ...inputStyle, width: 380, fontFamily: 'ui-monospace, monospace' }} />
                <button style={primaryBtn}
                  onClick={async () => {
                    if (usdtAddr.trim() && !window.confirm(T.usdtConfirm)) return
                    const ok = await act('settings/payment', {
                      method: 'PUT',
                      body: JSON.stringify({ usdt_address: usdtAddr.trim(), usdt_network: usdtNet }),
                    }, 'subscriptions')
                    if (ok) setEditUsdt(false)
                  }}>{T.usdtSave}</button>
                {paySettings?.usdt_address?.value
                  ? <button style={actionBtn} onClick={() => { setEditUsdt(false); setUsdtAddr(paySettings.usdt_address.value) }}>{T.cancelEdit}</button>
                  : <span style={{ fontSize: 11, color: '#eab308' }}>⚠️ {T.usdtUnset}</span>}
              </div>
            )}
            {/* Bank details — its own saved row; a targeted PUT keeps the USDT
                address untouched when only the bank rail changes. */}
            <div style={{ borderTop: '1px solid var(--border-color,#332d22)',
              marginTop: 14, paddingTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.bankTitle}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted,#a49b8a)', marginBottom: 8 }}>
                {T.bankHint}
              </div>
              {paySettings?.bank_transfer_info?.value && !editBank ? (
                appliedRow(
                  paySettings.bank_transfer_info.value,
                  null,
                  () => { setBankInfo(paySettings.bank_transfer_info.value); setEditBank(true) },
                  async () => { if (!window.confirm(T.clearConfirm)) return
                    setBankInfo('')
                    await act('settings/payment', { method: 'PUT',
                      body: JSON.stringify({ usdt_address: usdtAddr, usdt_network: usdtNet, bank_transfer_info: '' }) }, 'subscriptions') },
                )
              ) : (
                <>
                  <textarea value={bankInfo} onChange={e => setBankInfo(e.target.value)}
                    placeholder={T.bankPlaceholder} rows={3} maxLength={2000}
                    style={{ ...inputStyle, width: '100%', resize: 'vertical',
                      fontFamily: 'ui-monospace, monospace' }} />
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
                    <button style={primaryBtn} onClick={async () => {
                      const ok = await act('settings/payment', { method: 'PUT',
                        body: JSON.stringify({ usdt_address: usdtAddr, usdt_network: usdtNet, bank_transfer_info: bankInfo }) }, 'subscriptions')
                      if (ok) setEditBank(false)
                    }}>{T.usdtSave}</button>
                    {paySettings?.bank_transfer_info?.value
                      ? <button style={actionBtn} onClick={() => { setEditBank(false); setBankInfo(paySettings.bank_transfer_info.value) }}>{T.cancelEdit}</button>
                      : <span style={{ fontSize: 11, color: '#eab308' }}>⚠️ {T.bankUnset}</span>}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Admin alert recipients — where new subscription-request emails/SMS
              go. Console-registered like the payment settings above so the
              number can change without a deploy. */}
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>🔔 {T.alertsTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>
              {T.alertsHint}
            </div>
            {(alertSettings?.admin_alert_email?.value || alertSettings?.admin_alert_phone?.value) && !editAlerts ? (
              appliedRow(
                <>{alertSettings.admin_alert_email?.value ? `📧 ${alertSettings.admin_alert_email.value}` : ''}
                  {alertSettings.admin_alert_email?.value && alertSettings.admin_alert_phone?.value ? '     ' : ''}
                  {alertSettings.admin_alert_phone?.value ? `📱 ${alertSettings.admin_alert_phone.value}` : ''}</>,
                null,
                () => { setAlertEmail(alertSettings.admin_alert_email?.value || ''); setAlertPhone(alertSettings.admin_alert_phone?.value || ''); setEditAlerts(true) },
                async () => { if (!window.confirm(T.clearConfirm)) return
                  setAlertEmail(''); setAlertPhone('')
                  await act('settings/alerts', { method: 'PUT',
                    body: JSON.stringify({ admin_alert_email: '', admin_alert_phone: '' }) }, 'subscriptions') },
              )
            ) : (
              <>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input placeholder={T.alertEmailPlaceholder} value={alertEmail}
                    onChange={e => setAlertEmail(e.target.value)}
                    style={{ ...inputStyle, width: 320 }} />
                  <input placeholder={T.alertPhonePlaceholder} value={alertPhone}
                    onChange={e => setAlertPhone(e.target.value)}
                    style={{ ...inputStyle, width: 260, fontFamily: 'ui-monospace, monospace' }} />
                  <button style={primaryBtn}
                    onClick={async () => {
                      const ok = await act('settings/alerts', {
                        method: 'PUT',
                        body: JSON.stringify({ admin_alert_email: alertEmail.trim(),
                          admin_alert_phone: alertPhone.trim() }),
                      }, 'subscriptions')
                      if (ok) setEditAlerts(false)
                    }}>{T.alertsSave}</button>
                  {(alertSettings?.admin_alert_email?.value || alertSettings?.admin_alert_phone?.value) && (
                    <button style={actionBtn} onClick={() => { setEditAlerts(false); setAlertEmail(alertSettings.admin_alert_email?.value || ''); setAlertPhone(alertSettings.admin_alert_phone?.value || '') }}>{T.cancelEdit}</button>
                  )}
                </div>
                {!(alertSettings?.admin_alert_email?.value || alertSettings?.admin_alert_phone?.value) && (
                  <div style={{ fontSize: 11, color: '#eab308', marginTop: 8 }}>⚠️ {T.alertsOff}</div>
                )}
              </>
            )}
          </div>

          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.grantTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>{T.grantReplaces}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input placeholder={T.email} value={grant.email}
                onChange={e => setGrant(p => ({ ...p, email: e.target.value }))} style={{ ...inputStyle, width: 220 }} />
              <select value={grant.plan_code} onChange={e => setGrant(p => ({ ...p, plan_code: e.target.value }))} style={inputStyle}>
                {(planList.length ? planList : [{ code: 'junior' }, { code: 'pro' }, { code: 'professional' }, { code: 'enterprise' }]).map((p: any) => (
                  <option key={p.code} value={p.code}>{p.name || p.code}{p.price_usd ? ` ($${p.price_usd})` : ''}</option>
                ))}
              </select>
              <input placeholder={T.grantDays} value={grant.days} inputMode="numeric"
                onChange={e => setGrant(p => ({ ...p, days: e.target.value }))} style={{ ...inputStyle, width: 80 }} />
              <input placeholder={T.grantNote} value={grant.note}
                onChange={e => setGrant(p => ({ ...p, note: e.target.value }))} style={{ ...inputStyle, width: 200 }} />
              <button style={primaryBtn} disabled={!grant.email.trim() || !(parseInt(grant.days, 10) > 0)}
                onClick={() => {
                  act('subscriptions/grant', {
                    method: 'POST',
                    body: JSON.stringify({ email: grant.email.trim(), plan_code: grant.plan_code,
                      days: parseInt(grant.days, 10) || 30, note: grant.note,
                      method: grant.method, reference: grant.reference,
                      amount_usd: parseFloat(grant.amount_usd) || 0 }),
                  }, 'subscriptions')
                  setGrant(p => ({ ...p, email: '', note: '', reference: '', amount_usd: '' }))
                }}>{T.grantBtn}</button>
            </div>
            {/* Record a payment taken off-site (in-person transfer, a USDT hash
                sent over chat) rather than only comping the plan. An amount
                above 0 lands in the revenue chart; 'manual' + 0 does not. */}
            <div style={{ borderTop: '1px solid var(--border-color,#332d22)', marginTop: 12, paddingTop: 12 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted,#a49b8a)', marginBottom: 8 }}>{T.payRecordHint}</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <select value={grant.method} onChange={e => setGrant(p => ({ ...p, method: e.target.value }))}
                  style={inputStyle} title={T.payMethod}>
                  <option value="manual">{T.payMethodComp}</option>
                  <option value="usdt">usdt</option>
                  <option value="bank">bank</option>
                </select>
                <input placeholder={T.payReference} value={grant.reference}
                  onChange={e => setGrant(p => ({ ...p, reference: e.target.value }))}
                  style={{ ...inputStyle, width: 280, fontFamily: 'ui-monospace, monospace' }} />
                <input placeholder={T.payAmount} value={grant.amount_usd} inputMode="decimal"
                  onChange={e => setGrant(p => ({ ...p, amount_usd: e.target.value }))}
                  style={{ ...inputStyle, width: 120 }} />
              </div>
            </div>
            {(subs?.subscriptions || []).filter((s: any) => s.method === 'manual' && s.status === 'active').length > 0 && (
              <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted,#a49b8a)' }}>{T.activeGrants}</div>
                {(subs?.subscriptions || []).filter((s: any) => s.method === 'manual' && s.status === 'active').map((s: any) => (
                  <Fragment key={s.id}>{appliedRow(
                    `${s.email || `user ${s.user_id}`} · ${s.plan_code}`,
                    `~ ${fmtDate(s.expires_at)}`,
                    () => setGrant(p => ({ ...p, email: s.email || '', plan_code: s.plan_code })),
                    () => { if (window.confirm(T.cancelGrantConfirm)) act(`subscriptions/${s.id}/cancel`, { method: 'POST', body: JSON.stringify({ note: 'admin removed grant' }) }, 'subscriptions') },
                  )}</Fragment>
                ))}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            {['', 'pending', 'active', 'rejected', 'expired'].map(s => (
              <button key={s || 'all'} style={chip(subFilter === s)} onClick={() => setSubFilter(s)}>
                {s || tr(language, { ko: '전체', en: 'All', ja: 'すべて', th: 'ทั้งหมด', vi: 'Tất cả', id: 'Semua' })}
                {subs?.by_status && s ? ` (${subs.by_status[s] || 0})` : ''}
              </button>
            ))}
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.member}</th><th style={th}>{T.plan}</th><th style={th}>{T.method}</th><th style={th}>{T.reference}</th><th style={th}>{T.amount}</th><th style={th}>{T.status}</th><th style={th}>{T.expires}</th><th style={th}></th></tr></thead>
              <tbody>
                {(subs?.subscriptions || []).map((s: any) => (
                  <tr key={s.id}>
                    <td style={td}>{s.id}</td><td style={{ ...td, fontWeight: 600 }}>{s.email || s.user_id}</td>
                    <td style={td}>
                      {s.plan_code}
                      {/* A prorated upgrade: approving flips the plan and keeps
                          the original expiry — the amount is the difference,
                          not a full month. The tag is what tells the admin. */}
                      {s.change_kind === 'upgrade' && (
                        <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 700, borderRadius: 999, padding: '1px 7px', background: 'rgba(42,120,214,0.15)', color: 'var(--accent-primary,#2a78d6)' }}>
                          ⬆ {tr(language, { ko: '업그레이드', en: 'upgrade', ja: 'アップグレード', th: 'อัปเกรด', vi: 'nâng cấp', id: 'peningkatan' })}
                        </span>
                      )}
                    </td><td style={td}>{s.method}</td>
                    {/* The proof of payment. Shown in full and copyable — a
                        truncated tx hash cannot be checked against a chain. */}
                    <td style={{ ...td, maxWidth: 300 }}>
                      {s.reference ? (
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
                          <code style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11,
                            wordBreak: 'break-all', lineHeight: 1.45 }}>{s.reference}</code>
                          <button style={{ ...actionBtn, padding: '2px 8px', fontSize: 11 }}
                            onClick={() => {
                              navigator.clipboard?.writeText(s.reference)
                              setCopiedRef(s.id)
                              setTimeout(() => setCopiedRef(c => (c === s.id ? null : c)), 1500)
                            }}>{copiedRef === s.id ? `✓ ${T.refCopied}` : T.refCopy}</button>
                          {explorerUrl(s.method, paySettings?.usdt_network?.value || '', s.reference) && (
                            <a href={explorerUrl(s.method, paySettings?.usdt_network?.value || '', s.reference)}
                              target="_blank" rel="noopener noreferrer"
                              style={{ fontSize: 11, color: 'var(--accent-primary,#c26a45)' }}>
                              {T.refVerify} ↗
                            </a>
                          )}
                        </div>
                      ) : '—'}
                    </td>
                    <td style={td}>{fmtMoney(s.amount_usd)}</td>
                    <td style={{ ...td, color: subStatusColor(s.status), fontWeight: 600 }}>{s.status}</td>
                    <td style={td}>{fmtDate(s.expires_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {s.status === 'pending' && <>
                        <button style={actionBtn} onClick={() => act(`subscriptions/${s.id}/approve`, { method: 'POST', body: JSON.stringify({ note: '' }) }, 'subscriptions')}>{T.approve}</button>{' '}
                        <button style={dangerBtn} onClick={() => {
                          const note = window.prompt(T.reason) || ''
                          act(`subscriptions/${s.id}/reject`, { method: 'POST', body: JSON.stringify({ note }) }, 'subscriptions')
                        }}>{T.reject}</button>
                      </>}
                      {(s.status === 'active' || s.status === 'expired') &&
                        <button style={actionBtn} onClick={() => act(`subscriptions/${s.id}/extend`, { method: 'POST', body: JSON.stringify({ days: 30 }) }, 'subscriptions')}>{T.extend30}</button>}{' '}
                      {s.status === 'active' &&
                        <button style={dangerBtn} onClick={() => {
                          if (!window.confirm(T.cancelConfirm)) return
                          const note = window.prompt(T.grantNote) || ''
                          act(`subscriptions/${s.id}/cancel`, { method: 'POST', body: JSON.stringify({ note }) }, 'subscriptions')
                        }}>{T.cancelSub}</button>}
                    </td>
                  </tr>
                ))}
                {!(subs?.subscriptions || []).length && <tr><td style={td} colSpan={9}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>

          <div style={sectionTitle}>{T.planMgmt}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>{T.planMgmtHint}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>{T.billingHint}</div>
          <div style={{ ...tableCard, marginBottom: 12 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
              <thead><tr><th style={th}>{T.planCode}</th><th style={th}>{T.planName}</th><th style={th}>{T.planPrice}</th><th style={th}>{T.planBilling}</th><th style={th}>{T.planSort}</th><th style={th}>{T.subscriberRows}</th><th style={th}>{T.status}</th><th style={th}></th></tr></thead>
              <tbody>
                {adminPlans.map((p: any) => (
                  <tr key={p.code}>
                    <td style={{ ...td, fontWeight: 600 }}>{p.code}{p.contact_only ? ' 📞' : ''}</td>
                    <td style={td}>{p.name}</td>
                    <td style={td}>{p.contact_only ? '—' : fmtMoney(p.price_usd)}</td>
                    <td style={{ ...td, fontSize: 11, whiteSpace: 'nowrap' }}>
                      {p.contact_only ? '—' : <>
                        <div style={{ color: p.stripe_price_id ? undefined : 'var(--text-muted,#8a8073)' }}>
                          Stripe: {p.stripe_price_id || T.billingUnset}
                        </div>
                      </>}
                    </td>
                    <td style={td}>{p.sort_order}</td>
                    <td style={td}>{p.subscriber_rows}</td>
                    <td style={{ ...td, color: p.active ? '#22c55e' : 'var(--text-muted,#8a8073)' }}>{p.active ? 'active' : 'off'}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      <button style={actionBtn} onClick={() => {
                        const name = window.prompt(T.editName, p.name)
                        if (name) act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ name }) }, 'subscriptions')
                      }}>{T.editName}</button>{' '}
                      {!p.contact_only && <><button style={actionBtn} onClick={() => {
                        const price = window.prompt(T.editPrice, String(p.price_usd))
                        if (price !== null && !isNaN(parseFloat(price))) act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ price_usd: parseFloat(price) }) }, 'subscriptions')
                      }}>{T.editPrice}</button>{' '}
                      <button style={actionBtn} onClick={() => {
                        const v = window.prompt(T.editStripeId, p.stripe_price_id || '')
                        if (v !== null) act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ stripe_price_id: v }) }, 'subscriptions')
                      }}>{T.editStripeId}</button>{' '}
                      </>}
                      {p.active
                        ? <button style={actionBtn} onClick={() => act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ active: 0 }) }, 'subscriptions')}>{T.planOff}</button>
                        : <button style={actionBtn} onClick={() => act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ active: 1 }) }, 'subscriptions')}>{T.planOn}</button>}{' '}
                      {!p.subscriber_rows && <button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`plans/${p.code}`, { method: 'DELETE' }, 'subscriptions')}>{T.del}</button>}
                    </td>
                  </tr>
                ))}
                {!adminPlans.length && <tr><td style={td} colSpan={8}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
            <input placeholder={T.planCode} value={newPlan.code}
              onChange={e => setNewPlan(p => ({ ...p, code: e.target.value }))} style={{ ...inputStyle, width: 140 }} />
            <input placeholder={T.planName} value={newPlan.name}
              onChange={e => setNewPlan(p => ({ ...p, name: e.target.value }))} style={{ ...inputStyle, width: 160 }} />
            <input placeholder={T.planPrice} value={newPlan.price} inputMode="decimal"
              onChange={e => setNewPlan(p => ({ ...p, price: e.target.value }))} style={{ ...inputStyle, width: 90 }} />
            <input placeholder={T.planSort} value={newPlan.sort} inputMode="numeric"
              onChange={e => setNewPlan(p => ({ ...p, sort: e.target.value }))} style={{ ...inputStyle, width: 70 }} />
            <button style={primaryBtn}
              disabled={!newPlan.code.trim() || !newPlan.name.trim() || isNaN(parseFloat(newPlan.price))}
              onClick={() => {
                act('plans', {
                  method: 'POST',
                  body: JSON.stringify({ code: newPlan.code.trim(), name: newPlan.name.trim(), price_usd: parseFloat(newPlan.price) || 0, sort_order: parseInt(newPlan.sort, 10) || 0 }),
                }, 'subscriptions')
                setNewPlan({ code: '', name: '', price: '', sort: '10' })
              }}>{T.planAdd}</button>
          </div>

          <div style={sectionTitle}>{T.contracts}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.email}</th><th style={th}>Company</th><th style={th}>Phone</th><th style={th}>Message</th><th style={th}>{T.status}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(contracts?.contracts || []).map((c: any) => (
                  <tr key={c.id}>
                    <td style={td}>{c.id}</td><td style={{ ...td, fontWeight: 600 }}>{c.email}</td>
                    <td style={td}>{c.company || '—'}</td><td style={td}>{c.phone || '—'}</td>
                    <td style={{ ...td, maxWidth: 260 }}>{c.message}</td>
                    <td style={{ ...td, color: c.status === 'new' ? '#eab308' : c.status === 'contacted' ? '#22c55e' : 'var(--text-muted,#8a8073)' }}>{c.status}</td>
                    <td style={td}>{fmtDate(c.created_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {c.status !== 'contacted' && <button style={actionBtn} onClick={() => act(`contracts/${c.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'contacted' }) }, 'subscriptions')}>{T.contacted}</button>}{' '}
                      {c.status !== 'closed' && <button style={actionBtn} onClick={() => act(`contracts/${c.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'closed' }) }, 'subscriptions')}>{T.closed}</button>}
                    </td>
                  </tr>
                ))}
                {!(contracts?.contracts || []).length && <tr><td style={td} colSpan={8}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Assets ── */}
      {tab === 'assets' && assets && (
        <>
          <StatCards items={[
            [tr(language, { ko: '현금 합계', en: 'Total cash', ja: '現金合計', th: 'เงินสดรวม', vi: 'Tổng tiền mặt', id: 'Total kas' }), fmtMoney(assets.totals.cash)],
            [tr(language, { ko: '입금 합계', en: 'Total deposited', ja: '入金合計', th: 'ยอดฝากรวม', vi: 'Tổng đã nạp', id: 'Total setoran' }), fmtMoney(assets.totals.deposited)],
            [tr(language, { ko: '포지션 가치', en: 'Position value', ja: 'ポジション評価額', th: 'มูลค่าสถานะ', vi: 'Giá trị vị thế', id: 'Nilai posisi' }), fmtMoney(assets.totals.position_value)],
            [tr(language, { ko: '에이전트 수', en: 'Agents', ja: 'エージェント数', th: 'จำนวนเอเจนต์', vi: 'Số agent', id: 'Agen' }), assets.totals.agents],
          ]} />
          <div style={sectionTitle}>{T.equityCurve}</div>
          <TrendChart data={assets.equity_curve} xKey="day" series={[['total_value', '#c26a45'], ['profit', '#22c55e']]} />
          <div style={sectionTitle}>{T.topMembers}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>{T.agent}</th><th style={th}>{T.email}</th><th style={th}>Equity</th><th style={th}>Cash</th><th style={th}>Positions</th><th style={th}>Profit</th></tr></thead>
              <tbody>
                {(assets.top_members || []).map((m: any) => (
                  <tr key={m.agent_id}>
                    <td style={{ ...td, fontWeight: 600 }}>{m.name}</td><td style={td}>{m.email || '—'}</td>
                    <td style={td}>{fmtMoney(m.total_value)}</td><td style={td}>{fmtMoney(m.cash)}</td>
                    <td style={td}>{fmtMoney(m.position_value)}</td>
                    <td style={{ ...td, color: (m.profit || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{fmtMoney(m.profit)}</td>
                  </tr>
                ))}
                {!(assets.top_members || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Positions ── */}
      {tab === 'positions' && positions && (
        <>
          <StatCards items={[
            [tr(language, { ko: '미결제 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะที่เปิดอยู่', vi: 'Vị thế đang mở', id: 'Posisi terbuka' }), positions.totals.open_positions],
            [tr(language, { ko: '총 가치', en: 'Total value', ja: '総額', th: 'มูลค่ารวม', vi: 'Tổng giá trị', id: 'Total nilai' }), fmtMoney(positions.totals.total_value)],
            [tr(language, { ko: '미실현 손익', en: 'Unrealized PnL', ja: '未実現損益', th: 'กำไรขาดทุนที่ยังไม่รับรู้', vi: 'Lãi/lỗ chưa thực hiện', id: 'Laba rugi belum direalisasi' }), fmtMoney(positions.totals.unrealized_pnl)],
          ]} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 12 }}>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Market</th><th style={th}>#</th><th style={th}>Value</th></tr></thead>
                <tbody>{(positions.by_market || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.market}</td><td style={td}>{r.c}</td><td style={td}>{fmtMoney(r.value)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Side</th><th style={th}>#</th></tr></thead>
                <tbody>{(positions.by_side || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.side}</td><td style={td}>{r.c}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Symbol</th><th style={th}>#</th><th style={th}>Value</th></tr></thead>
                <tbody>{(positions.top_symbols || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.symbol}</td><td style={td}>{r.c}</td><td style={td}>{fmtMoney(r.value)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
          <div style={sectionTitle}>{tr(language, { ko: '대형 포지션', en: 'Largest positions', ja: '大口ポジション', th: 'สถานะขนาดใหญ่สุด', vi: 'Vị thế lớn nhất', id: 'Posisi terbesar' })}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr><th style={th}>Symbol</th><th style={th}>{T.agent}</th><th style={th}>{T.email}</th><th style={th}>Side</th><th style={th}>Qty</th><th style={th}>Entry</th><th style={th}>Now</th><th style={th}>PnL</th></tr></thead>
              <tbody>
                {(positions.largest || []).map((p: any) => (
                  <tr key={p.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{p.symbol} <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{p.market}</span></td>
                    <td style={td}>{p.agent_name || '—'}</td><td style={td}>{p.email || '—'}</td>
                    <td style={{ ...td, color: ['buy', 'long', 'yes'].includes(p.side) ? '#22c55e' : '#ef4444' }}>{p.side}</td>
                    <td style={td}>{p.quantity}</td><td style={td}>{p.entry_price}</td><td style={td}>{p.current_price ?? '—'}</td>
                    <td style={{ ...td, color: (p.unrealized_pnl || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{fmtMoney(p.unrealized_pnl)}</td>
                  </tr>
                ))}
                {!(positions.largest || []).length && <tr><td style={td} colSpan={8}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Automation ── */}
      {tab === 'automation' && autoStats && (
        <>
          {/* Plan 21 P3: crypto regime composite (advisory) — six-component
              0-100 posture score from the public regime payload. */}
          {regimeRead?.crypto_composite && (
            <div style={{ ...card, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                {tr(language, { ko: '크립토 레짐 컴포지트', en: 'Crypto regime composite', ja: 'クリプトレジーム総合スコア', th: 'คะแนนรวม regime คริปโต', vi: 'Điểm tổng hợp regime crypto', id: 'Skor komposit regime kripto' })}
              </div>
              <div style={{ display: 'flex', gap: 16, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 28, fontWeight: 700, color: regimeRead.crypto_composite.score >= 80 ? '#22c55e' : regimeRead.crypto_composite.score >= 40 ? '#c2a545' : '#ef4444' }}>
                  {regimeRead.crypto_composite.score}<span style={{ fontSize: 13, fontWeight: 400 }}>/100</span>
                </span>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{regimeRead.crypto_composite.zone}</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>
                  {tr(language, { ko: '100 = 광범위한 리스크온 · 자문용(집행 게이트 아님)', en: '100 = broad risk-on · advisory only (not an execution gate)', ja: '100 = 広範なリスクオン · 参考値（執行ゲートではない）', th: '100 = risk-on แบบกว้าง · เพื่ออ้างอิงเท่านั้น', vi: '100 = risk-on rộng · chỉ tham khảo', id: '100 = risk-on luas · hanya penasihat' })}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
                {Object.entries(regimeRead.crypto_composite.components || {}).map(([k, v]: [string, any]) => (
                  <span key={k} style={{ fontSize: 11, fontFamily: 'ui-monospace, monospace', color: v == null ? 'var(--text-muted,#8a8073)' : undefined }}>
                    {k}: {v == null ? '—' : v}
                  </span>
                ))}
              </div>
              {regimeRead.crypto_composite.as_of && (
                <div style={{ fontSize: 10, color: 'var(--text-muted,#8a8073)', marginTop: 6 }}>as of {regimeRead.crypto_composite.as_of}</div>
              )}
            </div>
          )}
          {/* Trend accounts (Plan 32) — hand a user's account to the trend
              rule. simulator | shadow; the server refuses anything else. */}
          {trendAccounts && (
            <div style={{ ...card, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.trendTitle}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 6 }}>{T.trendHint}</div>
              <div style={{ fontSize: 11, fontFamily: 'ui-monospace, monospace', marginBottom: 10 }}>
                {(trendAccounts.symbols || []).join(' · ')}
              </div>
              {!trendAccounts.module_enabled && (
                <div style={{ fontSize: 12, color: '#ef4444', marginBottom: 8 }}>⚠️ {T.trendOff}</div>
              )}
              {!trendAccounts.module_enabled && (trendAccounts.accounts || []).some((a: any) => (a.open_positions || []).length > 0) && (
                <div style={{ fontSize: 12, color: '#ef4444', marginBottom: 8 }}>⚠️ {T.trendUnmanaged}</div>
              )}
              {trendAccounts.problem && (
                <div style={{ fontSize: 12, color: '#ef4444', marginBottom: 8 }}>⚠️ {trendAccounts.problem}</div>
              )}
              {(trendAccounts.accounts || []).length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 8 }}>{T.trendNone}</div>
              )}
              {(trendAccounts.accounts || []).map((a: any) => (
                <div key={a.agent_id} style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 6, fontSize: 12, fontFamily: 'ui-monospace, monospace' }}>
                  <span>agent {a.agent_id}</span>
                  <span>{a.account_type}</span>
                  <span>${a.risk_usd}</span>
                  {a.account_type === 'shadow' && (
                    <span style={a.broker ? undefined : { color: '#ef4444' }}>{a.broker || T.trendNoBroker}</span>
                  )}
                  <span style={{ color: 'var(--text-muted,#8a8073)' }}>
                    {(a.open_positions || []).join(' ')}
                    {a.stats ? ` n=${a.stats.n_trades ?? 0} · pnl ${a.stats.total_pnl ?? 0}` : ''}
                  </span>
                  <button style={{ ...inputStyle, cursor: 'pointer' }} disabled={actBusy}
                    onClick={() => act(`settings/trend-accounts/${a.agent_id}`, { method: 'DELETE' }, 'automation')}>{T.trendRemove}</button>
                </div>
              ))}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
                <input placeholder={T.trendAgentId} value={trendForm.agent_id}
                  onChange={e => setTrendForm(p => ({ ...p, agent_id: e.target.value }))}
                  style={{ ...inputStyle, width: 120, fontFamily: 'ui-monospace, monospace' }} />
                <select value={trendForm.account_type}
                  onChange={e => setTrendForm(p => ({ ...p, account_type: e.target.value }))}
                  style={{ ...inputStyle, fontFamily: 'ui-monospace, monospace' }}>
                  {(trendAccounts.account_types || ['simulator']).map((t: string) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <input placeholder={T.trendRisk} value={trendForm.risk_usd}
                  onChange={e => setTrendForm(p => ({ ...p, risk_usd: e.target.value }))}
                  style={{ ...inputStyle, width: 160, fontFamily: 'ui-monospace, monospace' }} />
                <button style={primaryBtn} disabled={actBusy || !/^\d+$/.test(trendForm.agent_id.trim())}
                  onClick={async () => {
                    const ok = await act('settings/trend-accounts', {
                      method: 'POST',
                      body: JSON.stringify({ agent_id: Number(trendForm.agent_id), account_type: trendForm.account_type, risk_usd: Number(trendForm.risk_usd) }),
                    }, 'automation')
                    if (ok) setTrendForm({ agent_id: '', account_type: 'simulator', risk_usd: '25' })
                  }}>{T.trendAdd}</button>
              </div>
            </div>
          )}
          {/* LLM routing — the operator's own AI server + per-tier models,
              editable without a deploy (platform_settings). */}
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.llmTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>{T.llmHint}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
              <input placeholder={`${T.llmLocalUrl} — http://100.x.x.x:11434/v1`} value={llmForm.local_base_url}
                onChange={e => setLlmForm(p => ({ ...p, local_base_url: e.target.value }))}
                style={{ ...inputStyle, width: 320, fontFamily: 'ui-monospace, monospace' }} />
              <input placeholder={`${T.llmLocalModel} — gpt-oss:120b`} value={llmForm.local_model}
                onChange={e => setLlmForm(p => ({ ...p, local_model: e.target.value }))}
                style={{ ...inputStyle, width: 200, fontFamily: 'ui-monospace, monospace' }} />
            </div>
            {([['brief', T.llmBrief], ['decision', T.llmDecision]] as const).map(([tier, label]) => (
              <div key={tier} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12, width: 220 }}>{label}</span>
                <select value={(llmForm as any)[`${tier}_provider`]}
                  onChange={e => setLlmForm(p => ({ ...p, [`${tier}_provider`]: e.target.value }))}
                  style={inputStyle}>
                  <option value="">{T.llmProviderDefault}</option>
                  {(llmSettings?.providers || []).map((p: string) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
                <input placeholder={T.llmModelPlaceholder} value={(llmForm as any)[`${tier}_model`]}
                  onChange={e => setLlmForm(p => ({ ...p, [`${tier}_model`]: e.target.value }))}
                  style={{ ...inputStyle, width: 240, fontFamily: 'ui-monospace, monospace' }} />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 4 }}>
              <button style={primaryBtn}
                onClick={() => act('settings/llm', {
                  method: 'PUT', body: JSON.stringify(llmForm),
                }, 'automation')}>{T.usdtSave}</button>
              {llmSettings?.effective && (
                <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', fontFamily: 'ui-monospace, monospace' }}>
                  {T.llmEffective}: {(['brief', 'decision'] as const)
                    .map(t => `${t} → ${llmSettings.effective[t]?.provider || '—'}:${llmSettings.effective[t]?.model || '—'}`)
                    .join(' · ')}
                </span>
              )}
            </div>
          </div>
          <StatCards items={[
            [tr(language, { ko: '규칙 (활성)', en: 'Rules (on)', ja: 'ルール（有効）', th: 'กฎ (เปิด)', vi: 'Quy tắc (bật)', id: 'Aturan (aktif)' }), `${autoStats.totals.rules} (${autoStats.totals.enabled})`],
            [tr(language, { ko: '자동 실행 규칙', en: 'Auto-execute rules', ja: '自動実行ルール', th: 'กฎรันอัตโนมัติ', vi: 'Quy tắc tự thực thi', id: 'Aturan eksekusi otomatis' }), autoStats.totals.auto_execute],
            [tr(language, { ko: '실행 (30일)', en: 'Runs (30d)', ja: '実行（30日）', th: 'การรัน (30 วัน)', vi: 'Lượt chạy (30 ngày)', id: 'Run (30 hari)' }), autoStats.totals.runs_30d],
            [tr(language, { ko: '실행률 (30일)', en: 'Execute rate (30d)', ja: '実行率（30日）', th: 'อัตราการรัน (30 วัน)', vi: 'Tỷ lệ thực thi (30 ngày)', id: 'Tingkat eksekusi (30 hari)' }), `${Math.round((autoStats.totals.execute_rate_30d || 0) * 100)}%`],
          ]} />
          <div style={sectionTitle}>{T.runsPerDay}</div>
          <TrendChart data={autoStats.runs_by_day} xKey="day" series={[['runs', '#c26a45'], ['executed', '#22c55e']]} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 12, marginTop: 16 }}>
            <div>
              <div style={sectionTitle}>{T.byAgent}</div>
              <div style={tableCard}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr><th style={th}>{T.agent}</th><th style={th}>Runs</th><th style={th}>Executed</th></tr></thead>
                  <tbody>{(autoStats.by_agent || []).map((r: any, i: number) => (
                    <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.agent_name || r.agent_id}</td><td style={td}>{r.runs}</td><td style={td}>{r.executed}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
            <div>
              <div style={sectionTitle}>{T.skipReasons}</div>
              <div style={tableCard}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr><th style={th}>{T.reason}</th><th style={th}>#</th></tr></thead>
                  <tbody>{(autoStats.skip_reasons || []).map((r: any, i: number) => (
                    <tr key={i}><td style={td}>{r.reason}</td><td style={td}>{r.c}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          </div>
          <div style={sectionTitle}>{T.rules}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>Rule</th><th style={th}>{T.agent}</th><th style={th}>Interval</th><th style={th}>Conf.</th><th style={th}>$</th><th style={th}>{T.status}</th><th style={th}>Last run</th></tr></thead>
              <tbody>
                {(autoRules?.rules || []).map((r: any) => (
                  <tr key={r.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{r.symbol} <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{r.market} · {r.provider || 'default'}</span></td>
                    <td style={td}>{r.agent_name || r.agent_id}</td>
                    <td style={td}>{r.interval_minutes}m</td>
                    <td style={td}>≥{Math.round((r.min_confidence || 0) * 100)}%</td>
                    <td style={td}>${r.size_usd}</td>
                    <td style={td}>{r.enabled ? (r.auto_execute ? '🟢 auto' : '🟡 analysis') : '⚪ off'} · {r.account_type}</td>
                    <td style={td}>{fmtTime(r.last_run_at)}</td>
                  </tr>
                ))}
                {!(autoRules?.rules || []).length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Support conversations + announcements ── */}
      {/* ── Swing signal stack feed crawl status ── */}
      {tab === 'feeds' && (
        <div style={{ ...card }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{T.feedsTitle}</div>
            {feedStatus && (
              <span style={{ fontSize: 12, color: feedStatus.ok_count === 6 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>
                {feedStatus.ok_count}/6
              </span>
            )}
            {feedStatus?.checked_at && (
              <span style={{ fontSize: 11.5, color: 'var(--text-muted,#8a8073)' }}>
                {T.feedCheckedAt} {new Date(feedStatus.checked_at).toLocaleTimeString()}
                {feedStatus.cached ? ` · ${T.feedCached}` : ''}
              </span>
            )}
            <button
              style={{ ...actionBtn, marginLeft: 'auto', opacity: feedProbing ? 0.5 : 1 }}
              disabled={feedProbing}
              onClick={async () => {
                setFeedProbing(true)
                try { setFeedStatus(await call('swing-feeds/status?refresh=true')) }
                catch (e: any) { if (e?.message !== '401') setError(String(e?.message || e)) }
                finally { setFeedProbing(false) }
              }}>
              {feedProbing ? '⏳…' : `🔄 ${T.feedReprobe}`}
            </button>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 12 }}>{T.feedsHint}</div>
          {!feedStatus && <div style={{ fontSize: 13 }}>⏳…</div>}
          {feedStatus && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr>
                  <th style={th}>{T.feedStatusCol}</th>
                  <th style={th}>{T.feedCol}</th>
                  <th style={th}>{T.feedDocCol}</th>
                  <th style={th}>{T.feedSourceCol}</th>
                  <th style={th}>{T.feedLatencyCol}</th>
                  <th style={th}>{T.feedDetailCol}</th>
                </tr></thead>
                <tbody>
                  {(feedStatus.feeds || []).map((f: any) => (
                    <tr key={f.feed}>
                      <td style={td}>{f.ok ? '🟢' : '🔴'}</td>
                      <td style={{ ...td, fontWeight: 600 }}>{f.label}</td>
                      <td style={td}>{f.doc_feed}</td>
                      <td style={td}>{f.source}</td>
                      <td style={td}>{f.latency_ms != null ? `${f.latency_ms} ms` : '—'}</td>
                      <td style={{ ...td, color: f.ok ? 'inherit' : '#ef4444' }}>{f.ok ? f.detail : f.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'crawl' && (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ ...card }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{T.crawlTitle}</div>
              {crawlOverview && (
                <span style={{ fontSize: 12, fontWeight: 700, color: crawlOverview.failing_count ? '#ef4444' : '#22c55e' }}>
                  {crawlOverview.ok_count}/{(crawlOverview.collect || []).length}
                </span>
              )}
              {crawlOverview && !crawlOverview.pipeline_enabled && (
                <span style={{ fontSize: 11.5, color: '#eab308' }}>⚠ {T.crawlDisabled}</span>
              )}
              <button style={{ ...actionBtn, marginLeft: 'auto' }} onClick={() => refresh('crawl')}>🔄</button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', margin: '6px 0 10px' }}>{T.crawlHint}</div>
            {!crawlOverview && <div style={{ fontSize: 13 }}>⏳…</div>}
            {crawlOverview && <PipelineDiagram overview={crawlOverview} onPick={(f) => setCrawlFeed(f)} />}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
              <input
                value={crawlSymbols}
                onChange={e => setCrawlSymbols(e.target.value)}
                placeholder={T.crawlSymbolsPh}
                style={{ flex: '1 1 260px', minWidth: 200, padding: '7px 10px', fontSize: 12.5, borderRadius: 8,
                  border: '1px solid var(--border-color,#2a2a28)', background: 'transparent', color: 'inherit' }} />
              <button
                style={{ ...actionBtn, opacity: crawlBusy ? 0.5 : 1 }}
                disabled={crawlBusy}
                onClick={async () => {
                  setCrawlBusy(true); setCrawlResult(null)
                  try {
                    const symbols = crawlSymbols.split(',').map(s => s.trim()).filter(Boolean)
                    // `hdr` already carries Content-Type; passing headers here
                    // would replace it and drop the Authorization token.
                    const res = await call('crawl/run', {
                      method: 'POST',
                      body: JSON.stringify(symbols.length ? { symbols } : {}),
                    })
                    setCrawlResult(res)
                    await refresh('crawl')
                  } catch (e: any) { if (e?.message !== '401') setError(String(e?.message || e)) }
                  finally { setCrawlBusy(false) }
                }}>
                {crawlBusy ? '⏳…' : `▶ ${T.crawlRunNow}`}
              </button>
              {crawlResult && (
                <span style={{ fontSize: 11.5, color: crawlResult.ok === false ? '#ef4444' : 'var(--text-muted,#8a8073)' }}>
                  {crawlResult.ok === false
                    ? crawlResult.error
                    : `evaluated ${crawlResult.evaluated} · failed ${crawlResult.failed}`}
                </span>
              )}
            </div>
          </div>

          <div style={{ ...card }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{T.crawlHistory}</div>
              <select
                value={crawlFeed}
                onChange={e => setCrawlFeed(e.target.value)}
                style={{ padding: '5px 8px', fontSize: 12, borderRadius: 7, background: 'transparent',
                  color: 'inherit', border: '1px solid var(--border-color,#2a2a28)' }}>
                <option value="">{T.crawlAll}</option>
                {(crawlOverview?.collect || []).map((c: any) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
                <option value="pipeline">pipeline</option>
              </select>
            </div>
            {!crawlRuns.length && <div style={{ fontSize: 12.5, color: 'var(--text-muted,#8a8073)' }}>{T.crawlNoRuns}</div>}
            {!!crawlRuns.length && (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr>
                    <th style={th}>{T.feedStatusCol}</th>
                    <th style={th}>{T.feedCol}</th>
                    <th style={th}>{T.feedCheckedAt}</th>
                    <th style={th}>{T.feedLatencyCol}</th>
                    <th style={th}>items</th>
                    <th style={th}>{T.feedDetailCol}</th>
                  </tr></thead>
                  <tbody>
                    {crawlRuns.map((r: any) => (
                      <tr key={r.id}>
                        <td style={td}>{r.ok ? '🟢' : '🔴'}</td>
                        <td style={{ ...td, fontWeight: 600 }}>{r.feed}</td>
                        <td style={td}>{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                        <td style={td}>{r.duration_ms != null ? `${r.duration_ms} ms` : '—'}</td>
                        <td style={td}>{r.items ?? '—'}</td>
                        <td style={{ ...td, color: r.ok ? 'var(--text-muted,#8a8073)' : '#ef4444', maxWidth: 380 }}>
                          {r.ok ? JSON.stringify(r.detail || {}) : r.error}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {crawlOverview?.blend && crawlOverview.blend.mode !== 'off' && (
            <div style={{ ...card }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{T.crawlBlend}</div>
                <span style={{ fontSize: 11.5, padding: '2px 8px', borderRadius: 7, fontWeight: 700,
                  color: crawlOverview.blend.mode === 'live' ? '#22c55e' : '#eab308',
                  border: `1px solid ${crawlOverview.blend.mode === 'live' ? '#22c55e' : '#eab308'}` }}>
                  {crawlOverview.blend.mode}
                </span>
                {crawlOverview.blend.mode === 'shadow' && (
                  <span style={{ fontSize: 11.5, color: 'var(--text-muted,#8a8073)' }}>{T.crawlBlendShadow}</span>
                )}
              </div>
              <div style={{ fontSize: 12.5, marginTop: 8 }}>
                {T.crawlBlendFlips}:{' '}
                <b>{crawlOverview.blend.action_flips}</b> / {crawlOverview.blend.measured}
                {crawlOverview.blend.flip_rate != null &&
                  ` (${(crawlOverview.blend.flip_rate * 100).toFixed(0)}%)`}
                {!!(crawlOverview.blend.flipped_symbols || []).length && (
                  <span style={{ color: 'var(--text-muted,#8a8073)' }}>
                    {' '}· {crawlOverview.blend.flipped_symbols.join(', ')}
                  </span>
                )}
              </div>
            </div>
          )}

          <div style={{ ...card }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{T.crawlDecisionsTitle}</div>
            {!crawlDecisions.length && <div style={{ fontSize: 12.5, color: 'var(--text-muted,#8a8073)' }}>—</div>}
            {!!crawlDecisions.length && (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr>
                    <th style={th}>symbol</th>
                    <th style={th}>action</th>
                    <th style={th}>composite</th>
                    <th style={th}>axis</th>
                    {['sentiment', 'macro', 'thesis', 'smart_money', 'technical'].map(k => (
                      <th key={k} style={th}>{k}</th>
                    ))}
                    <th style={th}>shadow</th>
                    <th style={th}>veto</th>
                    <th style={th}>{T.feedCheckedAt}</th>
                  </tr></thead>
                  <tbody>
                    {crawlDecisions.map((d: any) => (
                      <tr key={d.id}>
                        <td style={{ ...td, fontWeight: 700 }}>{d.symbol}</td>
                        <td style={{ ...td, fontWeight: 700,
                          color: d.action === 'BUY' ? '#22c55e' : d.action === 'SELL' ? '#ef4444' : 'var(--text-muted,#8a8073)' }}>
                          {d.action}
                        </td>
                        <td style={td}>{d.composite != null ? d.composite.toFixed(1) : '—'}</td>
                        <td style={{ ...td, fontSize: 11.5 }}>{d.axis}</td>
                        {['sentiment', 'macro', 'thesis', 'smart_money', 'technical'].map(k => (
                          <td key={k} style={{ ...td, color: (d.scores || {})[k] == null ? 'var(--text-muted,#8a8073)' : 'inherit' }}>
                            {(d.scores || {})[k] == null ? '—' : (d.scores || {})[k].toFixed(0)}
                          </td>
                        ))}
                        <td style={{ ...td, color: 'var(--text-muted,#8a8073)' }}>
                          {d.sentiment_shadow == null ? '—' : d.sentiment_shadow.toFixed(0)}
                        </td>
                        <td style={{ ...td, color: d.veto ? '#eab308' : 'inherit' }}>{d.veto || '—'}</td>
                        <td style={{ ...td, fontSize: 11.5 }}>
                          {d.computed_at ? new Date(d.computed_at).toLocaleString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'skills' && (
        <>
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.skillsTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{T.skillsHint}</div>
          </div>
          {skillEdit ? (
            <div style={{ ...card, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
                {skillEdit.isNew ? `➕ ${T.skillNew}` : `✏️ ${T.skillEditTitle} — ${skillEdit.slug}`}
                {!skillEdit.isNew && skillEdit.is_base && (
                  <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, border: '1px solid var(--accent-primary,#d8a95e)', color: 'var(--accent-primary,#d8a95e)', borderRadius: 6, padding: '1px 6px' }}>BASE</span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                {skillEdit.isNew && (
                  <input placeholder="slug (a-z0-9-)" value={skillEdit.slug}
                    onChange={e => setSkillEdit((p: any) => ({ ...p, slug: e.target.value }))}
                    style={{ ...inputStyle, width: 220, fontFamily: 'ui-monospace, monospace' }} />
                )}
                <input placeholder={T.skillName} value={skillEdit.name}
                  onChange={e => setSkillEdit((p: any) => ({ ...p, name: e.target.value }))}
                  style={{ ...inputStyle, width: 280 }} />
                <input type="number" title={T.skillPriority} placeholder={T.skillPriority} value={skillEdit.priority}
                  onChange={e => setSkillEdit((p: any) => ({ ...p, priority: e.target.value }))}
                  style={{ ...inputStyle, width: 170 }} />
              </div>
              <input placeholder={T.skillDesc} value={skillEdit.description}
                onChange={e => setSkillEdit((p: any) => ({ ...p, description: e.target.value }))}
                style={{ ...inputStyle, width: '100%', marginBottom: 8 }} />
              <textarea placeholder={T.skillBody} value={skillEdit.body} rows={9}
                onChange={e => setSkillEdit((p: any) => ({ ...p, body: e.target.value }))}
                style={{ ...inputStyle, width: '100%', fontFamily: 'ui-monospace, monospace', fontSize: 12.5, lineHeight: 1.5, resize: 'vertical' }} />
              <div style={{ fontSize: 11, marginBottom: 10, color: skillEdit.body.length > SKILL_BODY_MAX ? '#ef4444' : 'var(--text-muted,#8a8073)' }}>
                {skillEdit.body.length} / {SKILL_BODY_MAX}
              </div>
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>{T.skillPrompts}:</span>
                {SKILL_SITES.map(site => (
                  <label key={site} style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                    <input type="checkbox" checked={(skillEdit.prompts || []).includes(site)}
                      onChange={e => setSkillEdit((p: any) => ({
                        ...p,
                        prompts: e.target.checked
                          ? [...(p.prompts || []), site]
                          : (p.prompts || []).filter((x: string) => x !== site),
                      }))} />
                    {site}
                  </label>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>{T.skillMarkets}:</span>
                <input placeholder={T.skillMarketsPh} value={skillEdit.marketsText}
                  onChange={e => setSkillEdit((p: any) => ({ ...p, marketsText: e.target.value }))}
                  style={{ ...inputStyle, width: 340, fontFamily: 'ui-monospace, monospace' }} />
                <label style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                  <input type="checkbox" checked={!!skillEdit.enabled}
                    onChange={e => setSkillEdit((p: any) => ({ ...p, enabled: e.target.checked }))} />
                  {T.enable}
                </label>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={primaryBtn} disabled={actBusy} onClick={async () => {
                  const markets = skillEdit.marketsText.trim()
                    ? skillEdit.marketsText.split(',').map((s: string) => s.trim()).filter(Boolean)
                    : []
                  const payload: any = {
                    name: skillEdit.name, description: skillEdit.description,
                    body: skillEdit.body, prompts: skillEdit.prompts,
                    markets, priority: parseInt(skillEdit.priority, 10) || 100,
                    enabled: !!skillEdit.enabled,
                  }
                  const ok = skillEdit.isNew
                    ? await act('skills', { method: 'POST', body: JSON.stringify({ ...payload, slug: skillEdit.slug.trim() }) }, 'skills')
                    : await act(`skills/${encodeURIComponent(skillEdit.slug)}`, { method: 'PATCH', body: JSON.stringify(payload) }, 'skills')
                  if (ok) setSkillEdit(null)
                }}>{T.save}</button>
                <button style={actionBtn} onClick={() => setSkillEdit(null)}>{T.cancel}</button>
              </div>
            </div>
          ) : (
            <button style={{ ...primaryBtn, marginBottom: 14 }} onClick={() => setSkillEdit({
              isNew: true, slug: '', name: '', description: '', body: '',
              prompts: ['trader'], marketsText: '', priority: '100', enabled: true,
            })}>➕ {T.skillNew}</button>
          )}
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={th}>slug</th>
                  <th style={th}>{T.skillName}</th>
                  <th style={th}>{T.skillPrompts}</th>
                  <th style={th}>{T.skillMarkets}</th>
                  <th style={th}>{T.skillPriority}</th>
                  <th style={th}>{T.action}</th>
                </tr>
              </thead>
              <tbody>
                {skills.map((s: any) => (
                  <Fragment key={s.slug}>
                  <tr style={{ opacity: s.enabled ? 1 : 0.5 }}>
                    <td style={{ ...td, fontFamily: 'ui-monospace, monospace', whiteSpace: 'nowrap' }}>
                      <button style={{ ...actionBtn, padding: '1px 7px', marginRight: 6 }} title={T.detail}
                        onClick={() => setOpenSkills(p => ({ ...p, [s.slug]: !p[s.slug] }))}>
                        {openSkills[s.slug] ? '▾' : '▸'}
                      </button>
                      {s.slug}
                      {s.is_base && <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, border: '1px solid var(--accent-primary,#d8a95e)', color: 'var(--accent-primary,#d8a95e)', borderRadius: 5, padding: '0px 4px' }}>base</span>}
                    </td>
                    <td style={td}>
                      <div style={{ fontWeight: 600 }}>{s.enabled ? '' : '⏸ '}{s.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', maxWidth: 420 }}>{s.description}</div>
                    </td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>{(s.prompts || []).join(' · ')}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>{s.markets?.length ? s.markets.join(', ') : T.skillAllMarkets}</td>
                    <td style={td}>{s.priority}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      <button style={actionBtn} onClick={() => setSkillEdit({
                        ...s, isNew: false,
                        marketsText: (s.markets || []).join(', '),
                        priority: String(s.priority),
                      })}>{T.edit}</button>{' '}
                      <button style={actionBtn} disabled={actBusy} onClick={() =>
                        act(`skills/${encodeURIComponent(s.slug)}`, { method: 'PATCH', body: JSON.stringify({ enabled: !s.enabled }) }, 'skills')
                      }>{s.enabled ? T.disable : T.enable}</button>{' '}
                      {s.is_base ? (
                        <button style={actionBtn} disabled={actBusy} onClick={() =>
                          window.confirm(T.skillResetConfirm) &&
                          act(`skills/${encodeURIComponent(s.slug)}/reset`, { method: 'POST' }, 'skills')
                        }>{T.skillReset}</button>
                      ) : (
                        <button style={dangerBtn} disabled={actBusy} onClick={() =>
                          window.confirm(T.skillDelConfirm) &&
                          act(`skills/${encodeURIComponent(s.slug)}`, { method: 'DELETE' }, 'skills')
                        }>{T.del}</button>
                      )}
                    </td>
                  </tr>
                  {openSkills[s.slug] && (
                    <tr>
                      <td style={{ ...td, background: 'var(--bg-primary,#1b1811)' }} colSpan={6}>
                        <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 6 }}>
                          {T.skillBody} · {s.body.length} / {SKILL_BODY_MAX}
                          {s.updated_by ? ` · ${s.updated_by} · ${s.updated_at || ''}` : ''}
                        </div>
                        <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12.5, lineHeight: 1.6,
                          whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxWidth: 980 }}>{s.body}</div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
                {!skills.length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'support' && (
        <>
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={sectionTitle}>
              {tr(language, { ko: '공지 발송 — 전체 회원 알림', en: 'Broadcast — announcement to every member', ja: '一斉配信 — 全会員へのお知らせ', th: 'ประกาศ — แจ้งสมาชิกทุกคน', vi: 'Phát thông báo — gửi tới mọi thành viên', id: 'Siaran — pengumuman ke seluruh anggota' })}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>
              {tr(language, {
                ko: '회원의 알림함에 공지가 표시됩니다. 공지 알림을 끈 회원은 자동으로 제외됩니다.',
                en: "Lands in each member's notification centre. Members who switched announcements off are skipped automatically.",
                ja: '会員の通知センターに表示されます。お知らせ通知をオフにした会員は自動的に除外されます。',
                th: 'จะแสดงในศูนย์แจ้งเตือนของสมาชิกแต่ละคน สมาชิกที่ปิดการแจ้งเตือนประกาศจะถูกข้ามอัตโนมัติ',
                vi: 'Hiển thị trong trung tâm thông báo của từng thành viên. Thành viên đã tắt thông báo sẽ tự động bị bỏ qua.',
                id: 'Masuk ke pusat notifikasi setiap anggota. Anggota yang menonaktifkan pengumuman otomatis dilewati.',
              })}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input placeholder={tr(language, { ko: '제목', en: 'Title', ja: 'タイトル', th: 'หัวข้อ', vi: 'Tiêu đề', id: 'Judul' })} value={broadcast.title}
                onChange={e => setBroadcast(b => ({ ...b, title: e.target.value }))}
                style={{ ...inputStyle, width: 240 }} />
              <input placeholder={tr(language, { ko: '내용 (선택)', en: 'Body (optional)', ja: '本文（任意）', th: 'เนื้อหา (ไม่บังคับ)', vi: 'Nội dung (tùy chọn)', id: 'Isi (opsional)' })} value={broadcast.body}
                onChange={e => setBroadcast(b => ({ ...b, body: e.target.value }))}
                style={{ ...inputStyle, flex: 1, minWidth: 240 }} />
              <button style={primaryBtn} disabled={!broadcast.title.trim()}
                onClick={async () => {
                  if (!confirm(tr(language, {
                    ko: '모든 회원에게 이 공지를 보낼까요?',
                    en: 'Send this announcement to every member?',
                    ja: 'このお知らせを全会員に送信しますか？',
                    th: 'ส่งประกาศนี้ให้สมาชิกทุกคนหรือไม่',
                    vi: 'Gửi thông báo này tới mọi thành viên?',
                    id: 'Kirim pengumuman ini ke seluruh anggota?',
                  }))) return
                  const ok = await act('notifications/broadcast',
                    { method: 'POST', body: JSON.stringify(broadcast) }, 'support')
                  if (ok) setBroadcast({ title: '', body: '' })
                }}>
                {tr(language, { ko: '발송', en: 'Send', ja: '送信', th: 'ส่ง', vi: 'Gửi', id: 'Kirim' })}
              </button>
            </div>
          </div>

          <div style={sectionTitle}>
            {tr(language, { ko: '회원 문의', en: 'Member conversations', ja: '会員問い合わせ', th: 'บทสนทนากับสมาชิก', vi: 'Hội thoại thành viên', id: 'Percakapan anggota' })}
            {threads?.unread_total > 0 && (
              <span style={{ marginLeft: 8, color: '#c26a45' }}>
                · {threads.unread_total} {tr(language, { ko: '건 대기', en: 'waiting', ja: '件 待機中', th: 'รออยู่', vi: 'đang chờ', id: 'menunggu' })}
              </span>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px,1fr) minmax(320px,1.4fr)', gap: 12, alignItems: 'start' }}>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr>
                  <th style={th}>{T.member}</th>
                  <th style={th}>{T.status}</th>
                  <th style={th}>{tr(language, { ko: '최근', en: 'Last', ja: '最終', th: 'ล่าสุด', vi: 'Gần nhất', id: 'Terakhir' })}</th>
                </tr></thead>
                <tbody>
                  {(threads?.threads || []).map((t: any) => (
                    <tr key={t.id} onClick={async () => {
                      setReply('')
                      setActiveThread(await call(`support/threads/${t.id}`))
                      await refresh('support')
                    }} style={{ cursor: 'pointer', background: activeThread?.thread?.id === t.id ? 'rgba(194,106,69,0.10)' : undefined }}>
                      <td style={td}>
                        {t.user_email}
                        {t.admin_unread > 0 && (
                          <span style={{ marginLeft: 6, background: '#c26a45', color: '#fff', borderRadius: 999, padding: '1px 7px', fontSize: 10, fontWeight: 700 }}>
                            {t.admin_unread}
                          </span>
                        )}
                        <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{t.subject || '—'}</div>
                      </td>
                      <td style={{ ...td, color: t.status === 'open' ? '#22c55e' : 'var(--text-muted,#8a8073)' }}>{t.status}</td>
                      <td style={{ ...td, fontSize: 11 }}>{fmtTime(t.last_message_at)}</td>
                    </tr>
                  ))}
                  {!(threads?.threads || []).length && (
                    <tr><td style={td} colSpan={3}>{T.noData}</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={card}>
              {!activeThread && (
                <div style={{ color: 'var(--text-muted,#8a8073)', fontSize: 13 }}>
                  {tr(language, { ko: '왼쪽에서 대화를 선택하세요.', en: 'Pick a conversation on the left.', ja: '左側から会話を選択してください。', th: 'เลือกบทสนทนาทางซ้าย', vi: 'Chọn một hội thoại ở bên trái.', id: 'Pilih percakapan di sebelah kiri.' })}
                </div>
              )}
              {activeThread && (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 14 }}>{activeThread.thread.user_email}</strong>
                    <button style={actionBtn} onClick={async () => {
                      const next = activeThread.thread.status === 'open' ? 'closed' : 'open'
                      await act(`support/threads/${activeThread.thread.id}/status`,
                        { method: 'POST', body: JSON.stringify({ status: next }) }, 'support')
                      setActiveThread(await call(`support/threads/${activeThread.thread.id}`))
                    }}>
                      {activeThread.thread.status === 'open'
                        ? tr(language, { ko: '문의 종료', en: 'Close thread', ja: '問い合わせ終了', th: 'ปิดเธรด', vi: 'Đóng chủ đề', id: 'Tutup utas' })
                        : tr(language, { ko: '다시 열기', en: 'Reopen', ja: '再開', th: 'เปิดใหม่', vi: 'Mở lại', id: 'Buka kembali' })}
                    </button>
                  </div>
                  <div style={{ maxHeight: 340, overflowY: 'auto', marginBottom: 10 }}>
                    {activeThread.messages.map((m: any) => (
                      <div key={m.id} style={{ display: 'flex', justifyContent: m.sender === 'admin' ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
                        <div style={{ maxWidth: '80%' }}>
                          <div style={{
                            padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
                            background: m.sender === 'admin' ? 'var(--accent-primary,#c26a45)' : 'var(--bg-primary,#0f0f0e)',
                            color: m.sender === 'admin' ? '#fff' : 'inherit',
                            border: m.sender === 'admin' ? 'none' : '1px solid var(--border-color,#2a2a28)',
                          }}>{m.body}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted,#8a8073)', marginTop: 2, textAlign: m.sender === 'admin' ? 'right' : 'left' }}>
                            {m.sender === 'admin' ? (m.admin_email || 'admin') : activeThread.thread.user_email} · {fmtTime(m.created_at)}
                          </div>
                        </div>
                      </div>
                    ))}
                    {!activeThread.messages.length && (
                      <div style={{ color: 'var(--text-muted,#8a8073)', fontSize: 13 }}>{T.noData}</div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                    <textarea value={reply} onChange={e => setReply(e.target.value.slice(0, 4000))} rows={3}
                      placeholder={tr(language, { ko: '답변을 입력하세요…', en: 'Write a reply…', ja: '返信を入力…', th: 'เขียนคำตอบ…', vi: 'Viết trả lời…', id: 'Tulis balasan…' })}
                      style={{ ...inputStyle, flex: 1, resize: 'vertical', fontFamily: 'inherit' }} />
                    <button style={primaryBtn} disabled={!reply.trim()} onClick={async () => {
                      const id = activeThread.thread.id
                      const ok = await act(`support/threads/${id}/reply`,
                        { method: 'POST', body: JSON.stringify({ body: reply }) }, 'support')
                      if (!ok) return  // keep the typed reply so the admin can retry
                      setReply('')
                      try { setActiveThread(await call(`support/threads/${id}`)) }
                      catch { /* refresh() already re-rendered the list; thread reload is best-effort */ }
                    }}>
                      {tr(language, { ko: '답변 전송', en: 'Send reply', ja: '返信送信', th: 'ส่งคำตอบ', vi: 'Gửi trả lời', id: 'Kirim balasan' })}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Discussions ── */}
      {tab === 'discussions' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder={T.search} value={dq} onChange={e => setDq(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && refresh('discussions')} style={{ ...inputStyle, width: 280 }} />
            <button style={actionBtn} onClick={() => refresh('discussions')}>{T.search}</button>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>Title</th><th style={th}>{T.agent}</th><th style={th}>{T.replies}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(discussions?.discussions || []).map((d: any) => (
                  <Fragment key={d.signal_id}>
                    <tr>
                      <td style={td}>{d.signal_id}</td>
                      <td style={{ ...td, maxWidth: 340 }}>
                        <div style={{ fontWeight: 600 }}>{d.title || '(untitled)'}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.content}</div>
                      </td>
                      <td style={td}>{d.agent_name || d.agent_id}</td>
                      <td style={td}>
                        <button style={actionBtn} onClick={async () => {
                          if (replies[d.signal_id]) { setReplies(p => { const n = { ...p }; delete n[d.signal_id]; return n }); return }
                          try {
                            const body = await call(`discussions/${d.signal_id}/replies`)
                            setReplies(p => ({ ...p, [d.signal_id]: body.replies }))
                          } catch { /* handled */ }
                        }}>{d.reply_count} ▾</button>
                      </td>
                      <td style={td}>{fmtTime(d.created_at)}</td>
                      <td style={td}><button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`discussions/${d.signal_id}`, { method: 'DELETE' }, 'discussions')}>{T.del}</button></td>
                    </tr>
                    {replies[d.signal_id] && (
                      <tr>
                        <td style={td} colSpan={6}>
                          {(replies[d.signal_id] || []).map((r: any) => (
                            <div key={r.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 0 4px 24px', fontSize: 13 }}>
                              <strong>{r.agent_name || r.agent_id}</strong>
                              <span style={{ flex: 1 }}>{r.content}</span>
                              <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{fmtTime(r.created_at)}</span>
                              <button style={dangerBtn} onClick={() => act(`replies/${r.id}`, { method: 'DELETE' }, 'discussions').then(() => setReplies(p => { const n = { ...p }; delete n[d.signal_id]; return n }))}>{T.del}</button>
                            </div>
                          ))}
                          {!(replies[d.signal_id] || []).length && <div style={{ paddingLeft: 24, fontSize: 13, color: 'var(--text-muted,#8a8073)' }}>{T.noData}</div>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!(discussions?.discussions || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Leaderboard ── */}
      {tab === 'leaderboard' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            {['return', 'risk', 'collaboration', 'quality'].map(m => (
              <button key={m} style={chip(lbMetric === m)} onClick={() => setLbMetric(m)}>{m}</button>
            ))}
            <button style={{ ...actionBtn, marginLeft: 'auto' }} onClick={() => act('leaderboard/refresh', { method: 'POST' }, 'leaderboard')}>{T.refreshNow}</button>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>#</th><th style={th}>{T.agent}</th><th style={th}>Profit</th><th style={th}>Profit %</th><th style={th}>Trades</th><th style={th}></th></tr></thead>
              <tbody>
                {(leaderboard?.snapshot || []).map((r: any, i: number) => (
                  <tr key={r.agent_id ?? i}>
                    <td style={td}>{i + 1}</td>
                    <td style={{ ...td, fontWeight: 600 }}>{r.name || r.agent_id}</td>
                    <td style={{ ...td, color: (r.profit || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{fmtMoney(r.profit)}</td>
                    <td style={td}>{Number(r.profit_percent || 0).toFixed(2)}%</td>
                    <td style={td}>{r.trade_count ?? '—'}</td>
                    <td style={td}><button style={dangerBtn} onClick={() => {
                      const reason = window.prompt(T.reason) || ''
                      act('leaderboard/exclusions', { method: 'POST', body: JSON.stringify({ agent_id: r.agent_id, reason }) }, 'leaderboard')
                    }}>{T.exclude}</button></td>
                  </tr>
                ))}
                {!(leaderboard?.snapshot || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={sectionTitle}>{T.exclusions}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder="agent_id" value={exclusion.agent_id}
              onChange={e => setExclusion(p => ({ ...p, agent_id: e.target.value }))} style={{ ...inputStyle, width: 110 }} />
            <input placeholder={T.reason} value={exclusion.reason}
              onChange={e => setExclusion(p => ({ ...p, reason: e.target.value }))} style={{ ...inputStyle, width: 240 }} />
            <button style={actionBtn} onClick={() => {
              const id = parseInt(exclusion.agent_id, 10)
              if (!id) return
              act('leaderboard/exclusions', { method: 'POST', body: JSON.stringify({ agent_id: id, reason: exclusion.reason }) }, 'leaderboard')
              setExclusion({ agent_id: '', reason: '' })
            }}>{T.exclude}</button>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
              <thead><tr><th style={th}>{T.agent}</th><th style={th}>{T.reason}</th><th style={th}>{T.status}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(leaderboard?.exclusions || []).map((e: any, i: number) => (
                  <tr key={i}>
                    <td style={{ ...td, fontWeight: 600 }}>{e.agent_name || e.agent_id}</td>
                    <td style={td}>{e.reason || '—'}</td>
                    <td style={{ ...td, color: e.active ? '#ef4444' : 'var(--text-muted,#8a8073)' }}>{e.active ? tr(language, { ko: '제외됨', en: 'excluded', ja: '除外済み', th: 'ถูกยกเว้น', vi: 'đã loại trừ', id: 'dikecualikan' }) : tr(language, { ko: '해제됨', en: 'included', ja: '解除済み', th: 'ยกเลิกยกเว้นแล้ว', vi: 'đã đưa lại', id: 'disertakan' })}</td>
                    <td style={td}>{fmtDate(e.created_at)}</td>
                    <td style={td}>{!!e.active && <button style={actionBtn} onClick={() => act(`leaderboard/exclusions/${e.agent_id}`, { method: 'DELETE' }, 'leaderboard')}>{T.include}</button>}</td>
                  </tr>
                ))}
                {!(leaderboard?.exclusions || []).length && <tr><td style={td} colSpan={5}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Admins (superadmin only) ── */}
      {tab === 'admins' && me?.role === 'superadmin' && (
        <>
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>{T.addAdmin}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input placeholder={T.email} value={newAdmin.email}
                onChange={e => setNewAdmin(p => ({ ...p, email: e.target.value }))} style={{ ...inputStyle, width: 220 }} />
              <input placeholder={T.password} type="password" value={newAdmin.password}
                onChange={e => setNewAdmin(p => ({ ...p, password: e.target.value }))} style={{ ...inputStyle, width: 180 }} />
              <select value={newAdmin.role} onChange={e => setNewAdmin(p => ({ ...p, role: e.target.value }))} style={inputStyle}>
                <option value="operator">operator</option>
                <option value="superadmin">superadmin</option>
              </select>
              <button style={primaryBtn} onClick={() => {
                act('admins', { method: 'POST', body: JSON.stringify(newAdmin) }, 'admins')
                setNewAdmin({ email: '', password: '', role: 'operator' })
              }}>{T.addAdmin}</button>
            </div>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.email}</th><th style={th}>{T.role}</th><th style={th}>{T.status}</th><th style={th}>{T.lastLogin}</th><th style={th}></th></tr></thead>
              <tbody>
                {(admins?.admins || []).map((a: any) => (
                  <tr key={a.id}>
                    <td style={td}>{a.id}</td><td style={{ ...td, fontWeight: 600 }}>{a.email}</td>
                    <td style={td}>{a.role}</td>
                    <td style={{ ...td, color: a.status === 'active' ? '#22c55e' : '#ef4444' }}>{a.status}</td>
                    <td style={td}>{fmtTime(a.last_login_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {/* Password reset is allowed on your own row (backend only
                          blocks self-disable/demote/delete). Resetting your own
                          password revokes the session — you log back in. */}
                      <button style={actionBtn} onClick={() => {
                        const pw = window.prompt(T.resetPw)
                        if (pw) act(`admins/${a.id}`, { method: 'PATCH', body: JSON.stringify({ password: pw }) }, 'admins')
                      }}>{T.resetPw}</button>{' '}
                      {a.id !== me.id && <>
                        {a.status === 'active'
                          ? <button style={dangerBtn} onClick={() => act(`admins/${a.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'disabled' }) }, 'admins')}>{T.disable}</button>
                          : <button style={actionBtn} onClick={() => act(`admins/${a.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'active' }) }, 'admins')}>{T.enable}</button>}{' '}
                        <button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`admins/${a.id}`, { method: 'DELETE' }, 'admins')}>{T.del}</button>
                      </>}
                    </td>
                  </tr>
                ))}
                {!(admins?.admins || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Audit ── */}
      {tab === 'audit' && (
        <div style={tableCard}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
            <thead><tr><th style={th}>{T.time}</th><th style={th}>{T.email}</th><th style={th}>{T.action}</th><th style={th}>{T.target}</th><th style={th}>{tr(language, { ko: '내용', en: 'Detail', ja: '内容', th: 'รายละเอียด', vi: 'Chi tiết', id: 'Detail' })}</th></tr></thead>
            <tbody>
              {(audit?.entries || []).map((e: any) => (
                <tr key={e.id}>
                  <td style={td}>{fmtTime(e.created_at)}</td>
                  <td style={{ ...td, fontWeight: 600 }}>{e.admin_email || '—'}</td>
                  <td style={td}>{e.action}</td>
                  <td style={td}>{e.target || '—'}</td>
                  <td style={{ ...td, maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.detail || '—'}</td>
                </tr>
              ))}
              {!(audit?.entries || []).length && <tr><td style={td} colSpan={5}>{T.noData}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default AdminPage
