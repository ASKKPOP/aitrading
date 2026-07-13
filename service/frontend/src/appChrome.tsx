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

export function Sidebar({
  token,
  agentInfo,
  onLogout,
  notificationCounts,
  onMarkCategoryRead,
  isOpen = false,
  onClose,
}: {
  token: string | null
  agentInfo: any
  onLogout: () => void
  notificationCounts: NotificationCounts
  onMarkCategoryRead: (category: 'discussion' | 'strategy' | 'experiment') => void
  isOpen?: boolean
  onClose?: () => void
}) {
  const location = useLocation()
  const { t, language } = useLanguage()
  const [showToken, setShowToken] = useState(false)
  const [accountType, setAccountType] = useState<string>(() => localStorage.getItem('account_type') || 'simulator')

  type NavItem = {
    path: string
    icon: string
    label: string
    requiresAuth: boolean
    badge?: number
    category?: 'discussion' | 'strategy' | 'experiment'
  }

  // Grouped nav sections — organized around this project's three targets:
  // AI analysis (Target 2), automation (Target 3), and simulation/trading (Target 1).
  const navSections: Array<{ label: string; items: NavItem[] }> = [
    {
      label: tr(language, { en: 'AI Desk', ja: 'AIデスク', th: 'AI เดสก์', vi: 'Bàn AI' }),
      items: [
        { path: '/analyst', icon: '🧠', label: tr(language, { en: 'AI Analyst', ja: 'AIアナリスト', th: 'นักวิเคราะห์ AI', vi: 'Nhà phân tích AI' }), requiresAuth: true },
        { path: '/automation', icon: '⚙', label: tr(language, { en: 'Automation', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động hóa' }), requiresAuth: true },
      ]
    },
    {
      label: tr(language, { en: 'Trading', ja: 'トレード', th: 'การเทรด', vi: 'Giao dịch' }),
      items: [
        { path: '/assets', icon: '◈', label: tr(language, { en: 'My Assets', ja: '資産', th: 'ทรัพย์สิน', vi: 'Tài sản' }), requiresAuth: true },
        { path: '/spot', icon: '◉', label: tr(language, { en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Spot' }), requiresAuth: true },
        { path: '/futures', icon: '⚡', label: tr(language, { en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures' }), requiresAuth: true },
        { path: '/accounts', icon: '◱', label: tr(language, { en: 'Accounts', ja: 'アカウント', th: 'บัญชี', vi: 'Tài khoản' }), requiresAuth: true },
        { path: '/positions', icon: '≡', label: t.nav.positions, requiresAuth: false },
      ]
    },
    {
      label: tr(language, { en: 'Markets', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
      items: [
        { path: '/market', icon: '◈', label: t.nav.signals, requiresAuth: false },
        { path: '/leaderboard', icon: '◆', label: tr(language, { en: 'Leaderboard', ja: 'リーダーボード', th: 'อันดับ', vi: 'Bảng xếp hạng' }), requiresAuth: false },
        { path: '/financial-events', icon: '🗞', label: tr(language, { en: 'Financial Events', ja: '金融イベント', th: 'เหตุการณ์การเงิน', vi: 'Sự kiện tài chính' }), requiresAuth: false },
        { path: '/copytrading', icon: '⊞', label: tr(language, { en: 'Copy Trading', ja: 'コピートレード', th: 'คัดลอกเทรด', vi: 'Sao chép giao dịch' }), requiresAuth: true },
      ]
    },
    {
      label: tr(language, { en: 'Research', ja: 'リサーチ', th: 'วิจัย', vi: 'Nghiên cứu' }),
      items: [
        { path: '/backtest', icon: '⏮', label: tr(language, { en: 'Backtest', ja: 'バックテスト', th: 'แบ็คเทสต์', vi: 'Backtest' }), requiresAuth: false },
        { path: '/discussions', icon: '○', label: t.nav.discussions, requiresAuth: false, badge: notificationCounts.discussion, category: 'discussion' as const },
      ]
    },
  ]

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
        <div className="logo-mark">Sooppiy</div>
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
          title={tr(language, { en: 'Simulated wallet — paper trading', ja: '模擬ウォレット', th: 'กระเป๋าจำลอง — เทรดกระดาษ', vi: 'Ví mô phỏng' })}
        >
          ◐ {tr(language, { en: 'Simulator', ja: 'シミュレーター', th: 'จำลอง', vi: 'Mô phỏng' })}
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
          title={tr(language, { en: 'Real account — connect Coinbase / Bybit / Binance', ja: '実口座', th: 'บัญชีจริง — เชื่อมต่อกระดานเทรด', vi: 'Tài khoản thật' })}
        >
          ● {tr(language, { en: 'Real', ja: 'リアル', th: 'จริง', vi: 'Thật' })}
        </Link>
      </div>

      {/* Nav sections */}
      <nav className="nav-section">
        {navSections.map((section) => (
          <div key={section.label}>
            <div className="nav-section-title">{section.label}</div>
            {section.items.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${location.pathname === item.path || location.pathname.startsWith(`${item.path}/`) ? 'active' : ''}`}
                title={!token && item.requiresAuth ? tr(language, { en: 'Login required', ja: 'ログインが必要', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' }) : undefined}
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
                    alert(tr(language, { en: 'Token copied', ja: 'トークンをコピーしました', th: 'คัดลอก Token แล้ว', vi: 'Đã sao chép' }))
                  }
                  setShowToken(!showToken)
                }}
              >
                {showToken ? agentInfo.token : agentInfo.token.substring(0, 12) + '···'}
              </div>
            )}
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
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.35)', lineHeight: 1.5, marginBottom: '4px' }}>
              {tr(language, {
                en: 'Browse freely — login to trade & copy.',
                ja: 'ログインで取引・コピーが可能。',
                th: 'เข้าสู่ระบบเพื่อเทรดและคัดลอก',
                vi: 'Đăng nhập để giao dịch & sao chép.'
              })}
            </div>
            <Link to="/login" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', fontSize: '12px', padding: '6px 12px' }}>
              {tr(language, { en: 'Login / Register', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' })}
            </Link>
          </div>
        )}
      </div>
    </div>
    </>
  )
}
