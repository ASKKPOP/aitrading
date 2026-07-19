import { useEffect, useState } from 'react'

import { Link, useLocation } from 'react-router-dom'

import { useLanguage, useTheme, THEMES } from './appShared'
import { LANGUAGES, tr } from './i18n'

export function Toast({ message, type, onClose }: { message: string, type: 'success' | 'error', onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  return <div className={`toast ${type}`}>{message}</div>
}

export type NotificationCounts = {
  discussion: number
  strategy: number
  experiment: number
}

// Member-scoped badges: unread notifications and unread support replies.
export type MemberCounts = {
  unread: number
  support: number
}

function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="control-pill-group">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.value}
          type="button"
          onClick={() => setLanguage(lang.value)}
          className={`control-pill ${language === lang.value ? 'active' : ''}`}
        >
          {lang.label}
        </button>
      ))}
    </div>
  )
}

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="theme-switcher" role="tablist" aria-label="Theme">
      {THEMES.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={theme === opt.value}
          onClick={() => setTheme(opt.value)}
          className={`theme-opt ${theme === opt.value ? 'active' : ''}`}
          title={opt.label}
        >
          <span className="theme-dot" style={{ background: opt.dotColor }} />
          <span className="theme-opt-label">{opt.label}</span>
        </button>
      ))}
    </div>
  )
}

export function TopbarControls() {
  return (
    <div className="topbar-controls">
      <ThemeSwitcher />
      <LanguageSwitcher />
    </div>
  )
}

export type NavItem = {
  path: string
  icon: string
  label: string
  requiresAuth: boolean
  ownerOnly?: boolean
  badge?: number
  category?: 'discussion' | 'strategy' | 'experiment'
}

// Owner gate — mirrors the backend DOCS_OWNER_EMAILS default. Owner-only nav
// items are hidden from everyone else; the backend enforces access too.
export const isOwnerEmail = (email?: string) =>
  (email || '').trim().toLowerCase() === 'info@askkpop.com'

// Shared nav definition for both chromes: the desktop top bar and the mobile
// sidebar drawer render the same items, so they cannot drift apart.
// Grouped around this project's three targets: AI analysis (Target 2),
// automation (Target 3), and simulation/trading (Target 1).
export function buildNavSections(
  language: any, t: any, notificationCounts: NotificationCounts,
): Array<{ label: string; items: NavItem[] }> {
  return [
    {
      label: tr(language, { ko: 'AI 데스크', en: 'AI Desk', ja: 'AIデスク', th: 'AI เดสก์', vi: 'Bàn AI' }),
      items: [
        { path: '/automation', icon: '⚙', label: tr(language, { ko: '자동매매', en: 'Automation', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động hóa' }), requiresAuth: true },
        { path: '/monitor', icon: '📡', label: tr(language, { ko: '모니터링', en: 'Monitoring', ja: 'モニタリング', th: 'การติดตาม', vi: 'Giám sát' }), requiresAuth: false },
        { path: '/consult', icon: '💬', label: tr(language, { ko: 'AI 상담', en: 'Consultation', ja: 'AI相談', th: 'ปรึกษา AI', vi: 'Tư vấn AI' }), requiresAuth: false },
      ]
    },
    {
      label: tr(language, { ko: '트레이딩', en: 'Trading', ja: 'トレード', th: 'การเทรด', vi: 'Giao dịch' }),
      items: [
        { path: '/assets', icon: '◈', label: tr(language, { ko: '내 자산', en: 'My Assets', ja: '資産', th: 'ทรัพย์สิน', vi: 'Tài sản' }), requiresAuth: true },
        { path: '/spot', icon: '◉', label: tr(language, { ko: '현물', en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Spot' }), requiresAuth: true },
        { path: '/futures', icon: '⚡', label: tr(language, { ko: '선물', en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures' }), requiresAuth: true },
        { path: '/accounts', icon: '◱', label: tr(language, { ko: '계좌', en: 'Accounts', ja: 'アカウント', th: 'บัญชี', vi: 'Tài khoản' }), requiresAuth: true },
        { path: '/positions', icon: '≡', label: t.nav.positions, requiresAuth: false },
      ]
    },
    {
      label: tr(language, { ko: '마켓', en: 'Markets', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
      items: [
        { path: '/market', icon: '◈', label: t.nav.signals, requiresAuth: false },
        { path: '/leaderboard', icon: '◆', label: tr(language, { ko: '리더보드', en: 'Leaderboard', ja: 'リーダーボード', th: 'อันดับ', vi: 'Bảng xếp hạng' }), requiresAuth: false },
        { path: '/financial-events', icon: '🗞', label: tr(language, { ko: '금융 이벤트', en: 'Financial Events', ja: '金融イベント', th: 'เหตุการณ์การเงิน', vi: 'Sự kiện tài chính' }), requiresAuth: false },
        { path: '/signals-board', icon: '◬', label: tr(language, { ko: '시그널 보드', en: 'Signals Board', ja: 'シグナルボード', th: 'บอร์ดสัญญาณ', vi: 'Bảng tín hiệu' }), requiresAuth: false },
      ]
    },
    {
      label: tr(language, { ko: '리서치', en: 'Research', ja: 'リサーチ', th: 'วิจัย', vi: 'Nghiên cứu' }),
      items: [
        { path: '/backtest', icon: '⏮', label: tr(language, { ko: '백테스트', en: 'Backtest', ja: 'バックテスト', th: 'แบ็คเทสต์', vi: 'Backtest' }), requiresAuth: false },
        { path: '/docs/guide', icon: '📖', label: tr(language, { ko: '가이드 · 문서', en: 'Guide & Docs', ja: 'ガイド・文書', th: 'คู่มือ·เอกสาร', vi: 'Hướng dẫn' }), requiresAuth: true, ownerOnly: true },
        { path: '/discussions', icon: '○', label: t.nav.discussions, requiresAuth: false, badge: notificationCounts.discussion, category: 'discussion' as const },
      ]
    },
  ]
}

// The assistant dock listens for this so any chrome can open it.
export const ASSISTANT_OPEN_EVENT = 'sooppiy:assistant-open'

export function HamburgerButton({ isOpen, onClick }: { isOpen: boolean; onClick: () => void }) {
  return (
    <button
      className="hamburger-btn"
      aria-label={isOpen ? 'Close menu' : 'Open menu'}
      aria-expanded={isOpen}
      onClick={onClick}
    >
      {isOpen ? '✕' : '☰'}
    </button>
  )
}

function Badge({ count }: { count: number }) {
  if (!count) return null
  return (
    <span className="topnav-badge">{count > 99 ? '99+' : count}</span>
  )
}

// Desktop chrome: horizontal top bar. Menu groups sit on the left, the
// account cluster (AI assistant, support, notifications, profile) on the
// right. Hidden below 769px, where the Sidebar drawer takes over.
export function TopNav({
  token, agentInfo, onLogout, userToken, userInfo, onUserLogout,
  notificationCounts, memberCounts = { unread: 0, support: 0 }, onMarkCategoryRead,
}: {
  token: string | null
  agentInfo: any
  onLogout: () => void
  userToken?: string | null
  userInfo?: any
  onUserLogout?: () => void
  notificationCounts: NotificationCounts
  memberCounts?: MemberCounts
  onMarkCategoryRead: (category: 'discussion' | 'strategy' | 'experiment') => void
}) {
  const location = useLocation()
  const { t, language } = useLanguage()
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  // The account-type switcher used to live only in the sidebar, which is now
  // mobile-only — it moves into this dropdown so desktop keeps the control.
  const [accountType, setAccountType] = useState<string>(() => localStorage.getItem('account_type') || 'simulator')

  const isOwner = isOwnerEmail(userInfo?.email)
  const navSections = buildNavSections(language, t, notificationCounts)

  // Any outside click or route change closes whichever dropdown is open.
  useEffect(() => { setOpenMenu(null); setProfileOpen(false) }, [location.pathname])
  useEffect(() => {
    if (!openMenu && !profileOpen) return
    const close = (e: MouseEvent) => {
      if (!(e.target as HTMLElement)?.closest?.('.topnav-menu, .topnav-profile')) {
        setOpenMenu(null); setProfileOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [openMenu, profileOpen])

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(`${path}/`)

  const label = {
    assistant: tr(language, { ko: 'AI 어시스턴트', en: 'AI Assistant', ja: 'AIアシスタント', th: 'ผู้ช่วย AI', vi: 'Trợ lý AI' }),
    support: tr(language, { ko: '고객지원 문의', en: 'Support', ja: 'サポート', th: 'ฝ่ายสนับสนุน', vi: 'Hỗ trợ' }),
    notifications: tr(language, { ko: '알림', en: 'Notifications', ja: '通知', th: 'การแจ้งเตือน', vi: 'Thông báo' }),
    profile: tr(language, { ko: '내 계정 · 프로필', en: 'My Account · Profile', ja: 'マイアカウント', th: 'บัญชีของฉัน', vi: 'Tài khoản của tôi' }),
    settings: tr(language, { ko: '설정 · API 구성', en: 'Settings · API Config', ja: '設定 · API構成', th: 'ตั้งค่า · API', vi: 'Cài đặt · API' }),
    login: tr(language, { ko: '로그인 / 가입', en: 'Login / Register', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    lockHint: tr(language, { ko: '로그인 필요', en: 'Login required', ja: 'ログインが必要', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' }),
  }

  const avatarChar = agentInfo?.name?.charAt(0)?.toUpperCase()
    || (userInfo?.email || 'U').charAt(0).toUpperCase()

  return (
    <header className="topnav">
      <Link to="/" className="topnav-brand">
        <img src="/logo.svg" alt="" width={24} height={24} />
        <span>Sooppiy</span>
      </Link>

      {/* ── left: menu groups ── */}
      <nav className="topnav-left">
        {navSections.map(section => {
          const items = section.items.filter(i => !i.ownerOnly || isOwner)
          if (!items.length) return null
          const groupActive = items.some(i => isActive(i.path))
          const isOpen = openMenu === section.label
          return (
            <div key={section.label} className="topnav-menu">
              <button
                className={`topnav-menu-btn${groupActive ? ' active' : ''}`}
                aria-expanded={isOpen}
                onClick={() => { setProfileOpen(false); setOpenMenu(isOpen ? null : section.label) }}
              >
                {section.label}
                <span className="topnav-caret">▾</span>
              </button>
              {isOpen && (
                <div className="topnav-dropdown">
                  {items.map(item => (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`topnav-dropdown-item${isActive(item.path) ? ' active' : ''}`}
                      title={!token && item.requiresAuth ? label.lockHint : undefined}
                      onClick={() => {
                        if (item.category && (item.badge || 0) > 0) onMarkCategoryRead(item.category)
                        setOpenMenu(null)
                      }}
                    >
                      <span className="nav-icon">{item.icon}</span>
                      <span style={{ flex: 1 }}>{item.label}</span>
                      <Badge count={item.badge || 0} />
                      {!token && item.requiresAuth && <span className="topnav-lock">lock</span>}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      {/* ── right: account cluster ── */}
      <div className="topnav-right">
        <TopbarControls />

        {token && (
          <button
            className="topnav-icon-btn"
            title={label.assistant}
            aria-label={label.assistant}
            onClick={() => window.dispatchEvent(new CustomEvent(ASSISTANT_OPEN_EVENT))}
          >✨</button>
        )}

        {userToken && (
          <>
            <Link to="/support" className="topnav-icon-btn" title={label.support} aria-label={label.support}>
              💬<Badge count={memberCounts.support} />
            </Link>
            <Link to="/notifications" className="topnav-icon-btn" title={label.notifications} aria-label={label.notifications}>
              🔔<Badge count={memberCounts.unread} />
            </Link>
          </>
        )}

        {(token && agentInfo) || (userToken && userInfo) ? (
          <div className="topnav-profile">
            <button className="topnav-avatar-btn" aria-expanded={profileOpen}
              onClick={() => { setOpenMenu(null); setProfileOpen(o => !o) }}>
              <span className="agent-avatar-sm">{avatarChar}</span>
              <span className="topnav-caret">▾</span>
            </button>
            {profileOpen && (
              <div className="topnav-dropdown topnav-dropdown--right">
                <div className="topnav-profile-head">
                  <div className="topnav-profile-name">
                    {agentInfo?.name || userInfo?.email}
                  </div>
                  <div className="topnav-profile-meta">
                    {(agentInfo?.points ?? userInfo?.points ?? 0)} {t.common.points}
                    {agentInfo?.cash !== undefined && ` · $${agentInfo.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                  </div>
                </div>
                <div className="topnav-acct-switch">
                  <button
                    className={`topnav-acct-opt${accountType === 'simulator' ? ' active' : ''}`}
                    title={tr(language, { ko: '모의 지갑 — 페이퍼 트레이딩', en: 'Simulated wallet — paper trading', ja: '模擬ウォレット', th: 'กระเป๋าจำลอง — เทรดกระดาษ', vi: 'Ví mô phỏng' })}
                    onClick={() => { localStorage.setItem('account_type', 'simulator'); setAccountType('simulator') }}
                  >◐ {tr(language, { ko: '시뮬레이터', en: 'Simulator', ja: 'シミュレーター', th: 'จำลอง', vi: 'Mô phỏng' })}</button>
                  <Link
                    to="/accounts"
                    className={`topnav-acct-opt${accountType === 'real' ? ' active' : ''}`}
                    title={tr(language, { ko: '실계좌 — 거래소 연결', en: 'Real account — connect an exchange', ja: '実口座', th: 'บัญชีจริง', vi: 'Tài khoản thật' })}
                    onClick={() => setProfileOpen(false)}
                  >● {tr(language, { ko: '실계좌', en: 'Real', ja: 'リアル', th: 'จริง', vi: 'Thật' })}</Link>
                </div>
                {agentInfo?.id && (
                  <Link to={`/agent/${agentInfo.id}`} className="topnav-dropdown-item" onClick={() => setProfileOpen(false)}>
                    <span className="nav-icon">◱</span>{tr(language, { ko: '내 프로필', en: 'My Profile', ja: 'プロフィール', th: 'โปรไฟล์', vi: 'Hồ sơ' })}
                  </Link>
                )}
                {userToken && (
                  <>
                    <Link to="/my-trading" className="topnav-dropdown-item" onClick={() => setProfileOpen(false)}>
                      <span className="nav-icon">◱</span>{label.profile}
                    </Link>
                    <Link to="/settings" className="topnav-dropdown-item" onClick={() => setProfileOpen(false)}>
                      <span className="nav-icon">⚙</span>{label.settings}
                    </Link>
                  </>
                )}
                <button className="topnav-dropdown-item topnav-signout"
                  onClick={() => { setProfileOpen(false); (token ? onLogout : onUserLogout)?.() }}>
                  <span className="nav-icon">⏻</span>{t.common.logout}
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link to="/login" className="btn btn-primary topnav-login">{label.login}</Link>
        )}
      </div>
    </header>
  )
}

export function Sidebar({
  token,
  agentInfo,
  onLogout,
  userToken,
  userInfo,
  onUserLogout,
  notificationCounts,
  memberCounts = { unread: 0, support: 0 },
  onMarkCategoryRead,
  isOpen = false,
  onClose,
}: {
  token: string | null
  agentInfo: any
  onLogout: () => void
  userToken?: string | null
  userInfo?: any
  onUserLogout?: () => void
  notificationCounts: NotificationCounts
  memberCounts?: MemberCounts
  onMarkCategoryRead: (category: 'discussion' | 'strategy' | 'experiment') => void
  isOpen?: boolean
  onClose?: () => void
}) {
  const location = useLocation()
  const { t, language } = useLanguage()
  const [showToken, setShowToken] = useState(false)
  const [accountType, setAccountType] = useState<string>(() => localStorage.getItem('account_type') || 'simulator')

  const isOwner = isOwnerEmail(userInfo?.email)
  const navSections = buildNavSections(language, t, notificationCounts)

  // Notification centre and the support conversation are member-account
  // features — they need a user session, not an agent token.
  if (userToken) {
    navSections.push({
      label: tr(language, { ko: '내 계정', en: 'My Account', ja: 'マイアカウント', th: 'บัญชีของฉัน', vi: 'Tài khoản' }),
      items: [
        { path: '/notifications', icon: '🔔', label: tr(language, { ko: '알림', en: 'Notifications', ja: '通知', th: 'การแจ้งเตือน', vi: 'Thông báo' }), requiresAuth: false, badge: memberCounts.unread },
        { path: '/support', icon: '💬', label: tr(language, { ko: '고객지원 문의', en: 'Support', ja: 'サポート', th: 'ฝ่ายสนับสนุน', vi: 'Hỗ trợ' }), requiresAuth: false, badge: memberCounts.support },
      ]
    })
  }

  const allNavItems = navSections.flatMap(s => s.items)

  useEffect(() => {
    const activeItem = allNavItems.find((item) => item.path === location.pathname)
    if (activeItem?.category && (activeItem.badge || 0) > 0) {
      onMarkCategoryRead(activeItem.category)
    }
  }, [location.pathname, notificationCounts.discussion, notificationCounts.strategy, notificationCounts.experiment])

  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} aria-hidden="true" />}
      <div className={`sidebar${isOpen ? ' sidebar--open' : ''}`}>
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-row">
          <img className="logo-icon" src="/logo.svg" alt="" width={22} height={22} />
          <div className="logo-mark">Sooppiy</div>
        </div>
        <div className="logo-tagline">AI · analyze · automate</div>
      </div>

      {/* Account-type switcher: Simulator (paper) vs Real (connected exchange) */}
      <div style={{ display: 'flex', gap: '6px', margin: '0 16px 14px' }}>
        <button
          onClick={() => { localStorage.setItem('account_type', 'simulator'); setAccountType('simulator') }}
          style={{
            flex: 1, padding: '7px 6px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
            border: '1px solid ' + (accountType === 'simulator' ? 'transparent' : 'rgba(255,255,255,0.14)'),
            background: accountType === 'simulator' ? 'var(--accent-primary, #c26a45)' : 'transparent',
            color: accountType === 'simulator' ? '#fff' : 'rgba(255,255,255,0.7)',
          }}
          title={tr(language, { ko: '모의 지갑 — 페이퍼 트레이딩', en: 'Simulated wallet — paper trading', ja: '模擬ウォレット', th: 'กระเป๋าจำลอง — เทรดกระดาษ', vi: 'Ví mô phỏng' })}
        >
          ◐ {tr(language, { ko: '시뮬레이터', en: 'Simulator', ja: 'シミュレーター', th: 'จำลอง', vi: 'Mô phỏng' })}
        </button>
        <Link
          to="/accounts"
          onClick={() => onClose?.()}
          style={{
            flex: 1, padding: '7px 6px', borderRadius: '8px', fontSize: '12px', fontWeight: 600, textAlign: 'center', textDecoration: 'none',
            border: '1px solid ' + (accountType === 'real' ? 'transparent' : 'rgba(255,255,255,0.14)'),
            background: accountType === 'real' ? 'var(--accent-primary, #c26a45)' : 'transparent',
            color: accountType === 'real' ? '#fff' : 'rgba(255,255,255,0.7)',
          }}
          title={tr(language, { ko: '실계좌 — 거래소 연결', en: 'Real account — connect Coinbase / Bybit / Binance', ja: '実口座', th: 'บัญชีจริง — เชื่อมต่อกระดานเทรด', vi: 'Tài khoản thật' })}
        >
          ● {tr(language, { ko: '실계좌', en: 'Real', ja: 'リアル', th: 'จริง', vi: 'Thật' })}
        </Link>
      </div>

      {/* Nav sections */}
      <nav className="nav-section">
        {navSections.map((section) => (
          <div key={section.label}>
            <div className="nav-section-title">{section.label}</div>
            {section.items.filter((item) => !item.ownerOnly || isOwner).map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${location.pathname === item.path || location.pathname.startsWith(`${item.path}/`) ? 'active' : ''}`}
                title={!token && item.requiresAuth ? tr(language, { ko: '로그인 필요', en: 'Login required', ja: 'ログインが必要', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' }) : undefined}
                onClick={() => {
                  if (item.category && (item.badge || 0) > 0) {
                    onMarkCategoryRead(item.category)
                  }
                  onClose?.()
                }}
              >
                <span className="nav-icon">{item.icon}</span>
                <span style={{ flex: 1 }}>{item.label}</span>
                {(item.badge || 0) > 0 && (
                  <span style={{
                    minWidth: '18px',
                    height: '16px',
                    padding: '0 5px',
                    borderRadius: '99px',
                    background: 'var(--accent-primary)',
                    color: '#fff',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '9px',
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    {item.badge && item.badge > 99 ? '99+' : item.badge}
                  </span>
                )}
                {!token && item.requiresAuth && (
                  <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.25)', fontFamily: 'var(--font-mono)' }}>
                    lock
                  </span>
                )}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        {token && agentInfo ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
              <div className="agent-avatar-sm">{agentInfo.name?.charAt(0) || 'A'}</div>
              <div>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'rgba(255,255,255,0.75)' }}>{agentInfo.name}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'rgba(255,255,255,0.3)', marginTop: '1px' }}>
                  {agentInfo.points} {t.common.points}
                  {agentInfo.cash !== undefined && ` · $${agentInfo.cash.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`}
                </div>
              </div>
            </div>
            {agentInfo.token && (
              <div
                style={{
                  fontSize: '10px',
                  fontFamily: 'var(--font-mono)',
                  color: 'rgba(255,255,255,0.3)',
                  marginBottom: '8px',
                  cursor: 'pointer',
                  wordBreak: 'break-all'
                }}
                onClick={() => {
                  if (showToken) {
                    navigator.clipboard.writeText(agentInfo.token)
                    alert(tr(language, { ko: '토큰이 복사되었습니다', en: 'Token copied', ja: 'トークンをコピーしました', th: 'คัดลอก Token แล้ว', vi: 'Đã sao chép' }))
                  }
                  setShowToken(!showToken)
                }}
              >
                {showToken ? agentInfo.token : agentInfo.token.substring(0, 12) + '···'}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '8px' }}>
              {agentInfo.id && (
                <Link
                  to={`/agent/${agentInfo.id}`}
                  onClick={() => onClose?.()}
                  className="nav-link"
                  style={{ padding: '5px 10px', fontSize: '12px' }}
                >
                  <span className="nav-icon">◱</span>
                  {tr(language, { ko: '내 프로필', en: 'My Profile', ja: 'プロフィール', th: 'โปรไฟล์', vi: 'Hồ sơ' })}
                </Link>
              )}
              {userToken && (
                <Link
                  to="/settings"
                  onClick={() => onClose?.()}
                  className="nav-link"
                  style={{ padding: '5px 10px', fontSize: '12px' }}
                >
                  <span className="nav-icon">⚙</span>
                  {tr(language, { ko: '설정 · API 구성', en: 'Settings · API Config', ja: '設定 · API構成', th: 'ตั้งค่า · API', vi: 'Cài đặt · API' })}
                </Link>
              )}
            </div>
            <button
              onClick={onLogout}
              style={{
                width: '100%',
                padding: '6px 0',
                background: 'transparent',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: '8px',
                color: 'rgba(255,255,255,0.45)',
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.08em',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.75)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.45)')}
            >
              {t.common.logout}
            </button>
          </div>
        ) : userToken && userInfo ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
              <div className="agent-avatar-sm">{(userInfo.email || 'U').charAt(0).toUpperCase()}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'rgba(255,255,255,0.75)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {userInfo.email}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'rgba(255,255,255,0.3)', marginTop: '1px' }}>
                  {userInfo.points ?? 0} {t.common.points}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <Link
                to="/my-trading"
                onClick={() => onClose?.()}
                className="nav-link"
                style={{ padding: '6px 10px', fontSize: '12px' }}
              >
                <span className="nav-icon">◱</span>
                {tr(language, { ko: '내 계정 · 프로필', en: 'My Account · Profile', ja: 'マイアカウント', th: 'บัญชีของฉัน', vi: 'Tài khoản của tôi' })}
              </Link>
              <Link
                to="/settings"
                onClick={() => onClose?.()}
                className="nav-link"
                style={{ padding: '6px 10px', fontSize: '12px' }}
              >
                <span className="nav-icon">⚙</span>
                {tr(language, { ko: '설정 · API 구성', en: 'Settings · API Config', ja: '設定 · API構成', th: 'ตั้งค่า · API', vi: 'Cài đặt · API' })}
              </Link>
              <button
                onClick={onUserLogout}
                style={{
                  width: '100%',
                  padding: '6px 0',
                  background: 'transparent',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: '8px',
                  color: 'rgba(255,255,255,0.45)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.75)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.45)')}
              >
                {t.common.logout}
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.35)', lineHeight: 1.5, marginBottom: '4px' }}>
              {tr(language, {
                ko: '자유롭게 둘러보고, 로그인하면 AI 자동매매를 설정할 수 있습니다.',
                en: 'Browse freely — login to configure AI auto-trading.',
                ja: 'ログインでAI自動売買を設定できます。',
                th: 'เข้าสู่ระบบเพื่อตั้งค่าเทรดอัตโนมัติ AI',
                vi: 'Đăng nhập để cấu hình giao dịch AI.'
              })}
            </div>
            <Link to="/login" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', fontSize: '12px', padding: '6px 12px' }}>
              {tr(language, { ko: '로그인 / 가입', en: 'Login / Register', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' })}
            </Link>
          </div>
        )}
      </div>
    </div>
    </>
  )
}
