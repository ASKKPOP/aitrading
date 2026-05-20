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

export function Sidebar({
  token,
  agentInfo,
  onLogout,
  notificationCounts,
  onMarkCategoryRead
}: {
  token: string | null
  agentInfo: any
  onLogout: () => void
  notificationCounts: NotificationCounts
  onMarkCategoryRead: (category: 'discussion' | 'strategy' | 'experiment') => void
}) {
  const location = useLocation()
  const { t, language } = useLanguage()
  const [showToken, setShowToken] = useState(false)

  const navItems = [
    { path: '/financial-events', icon: '🗞️', label: tr(language, { en: 'Financial Events', ja: '金融イベント', th: 'เหตุการณ์การเงิน', vi: 'Sự kiện tài chính' }), requiresAuth: false },
    { path: '/market', icon: '📊', label: t.nav.signals, requiresAuth: false },
    { path: '/leaderboard', icon: '🏆', label: tr(language, { en: 'Leaderboard', ja: 'リーダーボード', th: 'อันดับ', vi: 'Bảng xếp hạng' }), requiresAuth: false },
    { path: '/challenges', icon: '⚔️', label: tr(language, { en: 'Challenges', ja: 'チャレンジ', th: 'การแข่งขัน', vi: 'Thách đấu' }), requiresAuth: false },
    { path: '/team-missions', icon: '▦', label: tr(language, { en: 'Team Missions', ja: 'チームミッション', th: 'ภารกิจทีม', vi: 'Nhiệm vụ nhóm' }), requiresAuth: false },
    { path: '/experiments', icon: '◇', label: tr(language, { en: 'Experiments', ja: '実験', th: 'การทดลอง', vi: 'Thí nghiệm' }), requiresAuth: true, badge: notificationCounts.experiment, category: 'experiment' as const },
    { path: '/research-exports', icon: '⇩', label: tr(language, { en: 'Research Exports', ja: 'リサーチエクスポート', th: 'ส่งออกงานวิจัย', vi: 'Xuất nghiên cứu' }), requiresAuth: false },
    { path: '/copytrading', icon: '📋', label: tr(language, { en: 'Copy Trading', ja: 'コピートレード', th: 'คัดลอกเทรด', vi: 'Sao chép giao dịch' }), requiresAuth: true },
    { path: '/strategies', icon: '📈', label: t.nav.strategies, requiresAuth: false, badge: notificationCounts.strategy, category: 'strategy' as const },
    { path: '/discussions', icon: '💬', label: t.nav.discussions, requiresAuth: false, badge: notificationCounts.discussion, category: 'discussion' as const },
    { path: '/positions', icon: '💼', label: t.nav.positions, requiresAuth: false },
    { path: '/trade', icon: '💰', label: t.nav.trade, requiresAuth: true },
    { path: '/exchange', icon: '🎁', label: t.nav.exchange, requiresAuth: true },
  ]

  useEffect(() => {
    const activeItem = navItems.find((item) => item.path === location.pathname)
    if (activeItem?.category && (activeItem.badge || 0) > 0) {
      onMarkCategoryRead(activeItem.category)
    }
  }, [location.pathname, notificationCounts.discussion, notificationCounts.strategy, notificationCounts.experiment])

  return (
    <div className="sidebar">
      <div className="logo">
        <div className="logo-icon">CT</div>
        <span className="logo-text">AI-Trader</span>
      </div>

      <nav className="nav-section">
        <div className="nav-section-title">{tr(language, { en: 'Navigation', ja: 'ナビゲーション', th: 'การนำทาง', vi: 'Điều hướng' })}</div>
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-link ${location.pathname === item.path || location.pathname.startsWith(`${item.path}/`) ? 'active' : ''}`}
            title={!token && item.requiresAuth ? tr(language, { en: 'Login required', ja: 'ログインが必要', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' }) : undefined}
            onClick={() => {
              if (item.category && (item.badge || 0) > 0) {
                onMarkCategoryRead(item.category)
              }
            }}
          >
            <span className="nav-icon">{item.icon}</span>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '8px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>{item.label}</span>
                {(item.badge || 0) > 0 && (
                  <span style={{
                    minWidth: '18px',
                    height: '18px',
                    padding: '0 6px',
                    borderRadius: '999px',
                    background: '#ef4444',
                    color: '#fff',
                    fontSize: '11px',
                    fontWeight: 700,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    lineHeight: 1
                  }}>
                    {item.badge && item.badge > 99 ? '99+' : item.badge}
                  </span>
                )}
              </span>
              {!token && item.requiresAuth && (
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {t.common.login}
                </span>
              )}
            </span>
          </Link>
        ))}
      </nav>

      <div style={{ marginTop: 'auto' }}>
        {token && agentInfo ? (
          <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '12px' }}>
            <div className="user-info">
              <div className="user-avatar">{agentInfo.name?.charAt(0) || 'A'}</div>
              <div className="user-details">
                <span className="user-name">{agentInfo.name}</span>
                <span className="user-points">{agentInfo.points} {t.common.points}</span>
              </div>
              {agentInfo.cash !== undefined && (
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  {tr(language, { en: 'Cash: ', ja: '現金: ', th: 'เงินสด: ', vi: 'Tiền mặt: ' })}
                  <span style={{ color: 'var(--accent-primary)', fontWeight: 500 }}>
                    ${agentInfo.cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              )}
            </div>

            {agentInfo.token && (
              <div style={{ marginTop: '12px', padding: '8px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {tr(language, { en: 'API Token (Click to copy)', ja: 'APIトークン（クリックでコピー）', th: 'API Token (คลิกเพื่อคัดลอก)', vi: 'API Token (Bấm để sao chép)' })}
                  </div>
                  <button
                    onClick={() => setShowToken(!showToken)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '11px',
                      padding: '2px 4px'
                    }}
                  >
                    {showToken ? '👁️' : '🙈'}
                  </button>
                </div>
                <div
                  style={{
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: 'var(--accent-primary)',
                    cursor: 'pointer',
                    wordBreak: 'break-all'
                  }}
                  onClick={() => {
                    navigator.clipboard.writeText(agentInfo.token)
                    alert(tr(language, { en: 'Token copied to clipboard', ja: 'トークンをクリップボードにコピーしました', th: 'คัดลอก Token แล้ว', vi: 'Đã sao chép Token' }))
                  }}
                >
                  {showToken ? agentInfo.token : agentInfo.token.substring(0, 10) + '***'}
                </div>
              </div>
            )}

            <button
              onClick={onLogout}
              className="btn btn-ghost"
              style={{ width: '100%', marginTop: '12px', justifyContent: 'center' }}
            >
              {t.common.logout}
            </button>
          </div>
        ) : (
          <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: '6px' }}>
                {tr(language, { en: 'Guest Mode', ja: 'ゲストモード', th: 'โหมดผู้เยี่ยมชม', vi: 'Chế độ khách' })}
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {tr(language, {
                  en: 'You can browse markets, leaderboard, strategies, and discussions now. Login to trade, copy, and exchange points.',
                  ja: 'マーケット、リーダーボード、戦略、ディスカッションは今すぐ閲覧できます。取引、コピー、ポイント交換にはログインが必要です。',
                  th: 'คุณสามารถดูตลาด อันดับ กลยุทธ์ และการสนทนาได้ทันที เข้าสู่ระบบเพื่อเทรด คัดลอก และแลกเปลี่ยนคะแนน',
                  vi: 'Bạn có thể xem thị trường, bảng xếp hạng, chiến lược và thảo luận ngay bây giờ. Đăng nhập để giao dịch, sao chép và đổi điểm.'
                })}
              </div>
            </div>
            <Link to="/login" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}>
              {tr(language, { en: 'Login / Register', ja: 'ログイン / 登録', th: 'เข้าสู่ระบบ / ลงทะเบียน', vi: 'Đăng nhập / Đăng ký' })}
            </Link>
            <Link to="/market" className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center' }}>
              {tr(language, { en: 'Browse Market', ja: 'まずマーケットを見る', th: 'ดูตลาดก่อน', vi: 'Xem thị trường trước' })}
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
