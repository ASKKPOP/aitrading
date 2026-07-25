import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import {
  API_BASE,
  LanguageContext,
  LoginPage,
  type MemberCounts,
  type NotificationCounts,
  NOTIFICATION_POLL_INTERVAL,
  RegisterPage,
  Sidebar,
  StrategiesPage,
  ThemeContext,
  type ThemeMode,
  Toast,
  TopbarControls,
  TopNav,
  DiscussionsPage,
  HamburgerButton,
} from './AppPages'

import { GuideButton } from './components/GuideButton'

// Route-level pages are lazy-loaded to enable bundle code-splitting.
const LandingPage = lazy(() => import('./pages/LandingPage'))
const DevPage = lazy(() => import('./pages/DevPage'))
const FinancialEventsPage = lazy(() => import('./pages/FinancialEventsPage'))
const MarketPage = lazy(() => import('./pages/MarketPage'))
const SignalsBoardPage = lazy(() => import('./pages/SignalsBoardPage'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const DocsPage = lazy(() => import('./pages/DocsPage'))
const MonitorPage = lazy(() => import('./pages/MonitorPage'))
const ConsultPage = lazy(() => import('./pages/ConsultPage'))
const AssistantDock = lazy(() => import('./components/AssistantDock'))
const GuidePanel = lazy(() => import('./components/GuidePanel'))
const LeaderboardPage = lazy(() => import('./pages/LeaderboardPage'))
const PositionsPage = lazy(() => import('./pages/PositionsPage'))
const TradePage = lazy(() => import('./pages/TradePage'))
const ExchangePage = lazy(() => import('./pages/ExchangePage'))
const AgentProfilePage = lazy(() => import('./pages/AgentProfilePage'))
const AutomationPage = lazy(() => import('./pages/AutomationPage'))
const AccountsPage = lazy(() => import('./pages/AccountsPage'))
const AssetsPage = lazy(() => import('./pages/AssetsPage'))
const MarketingPage = lazy(() => import('./pages/MarketingPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const SupportPage = lazy(() => import('./pages/SupportPage'))
const SpotPage = lazy(() => import('./pages/TerminalPage').then(m => ({ default: m.SpotPage })))
const FuturesPage = lazy(() => import('./pages/TerminalPage').then(m => ({ default: m.FuturesPage })))
const SubscribePage = lazy(() => import('./pages/SubscribePage'))
const ContractPage = lazy(() => import('./pages/ContractPage'))
import { ChallengePage } from './ChallengePage'
import { ExperimentAdminPage } from './ExperimentAdminPage'
import { BacktestPage } from './BacktestPage'
import { ResearchExportsPage } from './ResearchExportsPage'
import { TeamMissionsPage } from './TeamMissionsPage'
import { Language, getT, DEFAULT_LANGUAGE, LANGUAGES } from './i18n'
import { THEMES, DEFAULT_THEME } from './appShared'
import {
  ForgotPasswordPage,
  GoogleCallbackPage,
  MfaSetupPage,
  SignInPage,
  SignUpPage,
  USER_TOKEN_KEY,
  signOutUser,
} from './authV2'
import { MyTradingPage } from './myTradingPage'

const DISCUSSION_NOTIFICATION_TYPES = new Set([
  'discussion_started',
  'discussion_reply',
  'discussion_mention',
  'discussion_reply_accepted'
])

const STRATEGY_NOTIFICATION_TYPES = new Set([
  'strategy_published',
  'strategy_reply',
  'strategy_mention',
  'strategy_reply_accepted'
])

const EXPERIMENT_NOTIFICATION_TYPES = new Set([
  'experiment_announcement',
  'experiment_assignment',
  'experiment_reminder',
  'experiment_rule_update',
  'experiment_result_update',
  'challenge_invite',
  'team_mission_invite'
])


function App() {
  const [language, setLanguage] = useState<Language>(() => {
    const saved = localStorage.getItem('sooppiy_language')
    return LANGUAGES.some((l) => l.value === saved) ? (saved as Language) : DEFAULT_LANGUAGE
  })
  useEffect(() => {
    localStorage.setItem('sooppiy_language', language)
  }, [language])
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('sooppiy_theme_v2')
    return THEMES.some((t) => t.value === saved) ? (saved as ThemeMode) : DEFAULT_THEME
  })
  const [token, setToken] = useState<string | null>(localStorage.getItem('claw_token'))
  const [userToken, setUserToken] = useState<string | null>(localStorage.getItem(USER_TOKEN_KEY))
  // User-initiated language changes persist to the server when logged in;
  // server-seeded changes (see /users/me effect below) use the raw setter
  // directly to avoid echoing a redundant PUT back on every mount.
  const changeLanguage = (next: Language) => {
    setLanguage(next)
    if (userToken) {
      fetch(`${API_BASE}/users/language`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${userToken}` },
        body: JSON.stringify({ lang: next }),
      }).catch(() => {})
    }
  }
  const [agentInfo, setAgentInfo] = useState<any>(null)
  const [toast, setToast] = useState<{ message: string, type: 'success' | 'error' } | null>(null)
  const [notificationCounts, setNotificationCounts] = useState<NotificationCounts>({ discussion: 0, strategy: 0, experiment: 0 })
  // Member-scoped badges (notification centre + support chat) — user session,
  // separate from the agent-scoped discussion/strategy/experiment counts.
  const [memberCounts, setMemberCounts] = useState<MemberCounts>({ unread: 0, support: 0 })

  const t = getT(language)

  const login = (newToken: string) => {
    localStorage.setItem('claw_token', newToken)
    setToken(newToken)
  }

  const logout = () => {
    localStorage.removeItem('claw_token')
    setToken(null)
    setAgentInfo(null)
    setNotificationCounts({ discussion: 0, strategy: 0, experiment: 0 })
    // Linked sessions sign out together — otherwise the auto-link effect
    // would immediately re-issue an agent token from the surviving user session.
    if (userToken) { signOutUser(); setUserToken(null); setUserInfo(null) }
  }

  // Phase 5: human-user auth lives alongside the agent claw_token.
  const userLogin = (newToken: string) => { setUserToken(newToken) }
  const userLogout = () => {
    signOutUser(); setUserToken(null); setUserInfo(null)
    localStorage.removeItem('claw_token'); setToken(null); setAgentInfo(null)
  }

  const [userInfo, setUserInfo] = useState<any>(null)
  useEffect(() => {
    if (!userToken) { setUserInfo(null); return }
    fetch(`${API_BASE}/users/me`, { headers: { 'Authorization': `Bearer ${userToken}` } })
      .then(res => {
        if (res.status === 401) { userLogout(); return null }
        return res.ok ? res.json() : null
      })
      .then(data => {
        if (data) {
          setUserInfo(data)
          if (LANGUAGES.some((l) => l.value === data.lang) && data.lang !== language) {
            setLanguage(data.lang as Language)
          }
        }
      })
      .catch(() => {})
  }, [userToken])

  // Every human account gets its own auto-provisioned simulator agent — most of
  // the app runs on agent (claw) auth. Issue/refresh the claw token from the
  // user session; returns the fresh token so callers can retry immediately.
  const linkAgent = async (): Promise<string | null> => {
    if (!userToken) return null
    try {
      const res = await fetch(`${API_BASE}/users/agent`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${userToken}` }
      })
      if (!res.ok) return null
      const data = await res.json()
      if (data?.token) { login(data.token); return data.token }
    } catch { /* transient */ }
    return null
  }

  // Link when the claw session is missing. Guarded so an existing agent
  // session is never rotated away on every render.
  useEffect(() => {
    if (!userToken || token) return
    linkAgent()
  }, [userToken, token])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('sooppiy_theme_v2', theme)
  }, [theme])

  const fetchAgentInfo = async () => {
    try {
      const res = await fetch(`${API_BASE}/claw/agents/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setAgentInfo(data)
        return
      }
      // A stale/rotated claw token (401/403) would otherwise strand every
      // agent-authed page on errors with no recovery. If a user session is
      // present, re-link to mint a fresh token and retry once.
      if ((res.status === 401 || res.status === 403) && userToken) {
        const fresh = await linkAgent()
        if (fresh) {
          const retry = await fetch(`${API_BASE}/claw/agents/me`, {
            headers: { 'Authorization': `Bearer ${fresh}` }
          })
          if (retry.ok) setAgentInfo(await retry.json())
        }
      }
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    if (token) {
      fetchAgentInfo()
    }
  }, [token])

  const fetchUnreadSummary = async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/claw/messages/unread-summary`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) return
      const data = await res.json()
      setNotificationCounts({
        discussion: data.discussion_unread || 0,
        strategy: data.strategy_unread || 0,
        experiment: data.experiment_unread || 0
      })
    } catch (e) {
      console.error(e)
    }
  }

  const markCategoryRead = async (category: 'discussion' | 'strategy' | 'experiment') => {
    if (!token) return
    setNotificationCounts((prev) => ({ ...prev, [category]: 0 }))
    try {
      await fetch(`${API_BASE}/claw/messages/mark-read`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ categories: [category] })
      })
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    if (!token) return
    fetchUnreadSummary()
    const interval = setInterval(fetchUnreadSummary, NOTIFICATION_POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [token])

  const fetchMemberSummary = async () => {
    if (!userToken) return
    try {
      const res = await fetch(`${API_BASE}/notifications/summary`, {
        headers: { 'Authorization': `Bearer ${userToken}` }
      })
      if (!res.ok) return
      const data = await res.json()
      setMemberCounts({ unread: data.unread || 0, support: data.support_unread || 0 })
    } catch { /* transient */ }
  }

  useEffect(() => {
    if (!userToken) { setMemberCounts({ unread: 0, support: 0 }); return }
    fetchMemberSummary()
    const interval = setInterval(fetchMemberSummary, NOTIFICATION_POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [userToken])

  useEffect(() => {
    if (!agentInfo?.id) return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    if (!token) return
    const wsUrl = `${protocol}//${window.location.host}/ws/notify/${agentInfo.id}?token=${encodeURIComponent(token)}`
    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (DISCUSSION_NOTIFICATION_TYPES.has(payload?.type)) {
          setNotificationCounts((prev) => ({ ...prev, discussion: prev.discussion + 1 }))
        } else if (STRATEGY_NOTIFICATION_TYPES.has(payload?.type)) {
          setNotificationCounts((prev) => ({ ...prev, strategy: prev.strategy + 1 }))
        } else if (EXPERIMENT_NOTIFICATION_TYPES.has(payload?.type)) {
          setNotificationCounts((prev) => ({ ...prev, experiment: prev.experiment + 1 }))
        }
        if (payload?.content) {
          setToast({ message: payload.content, type: 'success' })
        }
      } catch (e) {
        console.error(e)
      }
    }

    return () => {
      ws.close()
    }
  }, [agentInfo?.id, token])

  // Dedicated management domain: administr.sooppiy.com serves only the
  // manager console (own container behind the host nginx; TLS at the ALB).
  if (window.location.hostname.startsWith('administr.')) {
    return (
      <ThemeContext.Provider value={{ theme, setTheme }}>
        <LanguageContext.Provider value={{ language, setLanguage: changeLanguage, t }}>
          <Suspense fallback={<div className="loading"><div className="spinner"></div></div>}>
            <AdminPage />
          </Suspense>
        </LanguageContext.Provider>
      </ThemeContext.Provider>
    )
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      <LanguageContext.Provider value={{ language, setLanguage: changeLanguage, t }}>
        <BrowserRouter>
          <AppRouter
            token={token}
            agentInfo={agentInfo}
            login={login}
            logout={logout}
            fetchAgentInfo={fetchAgentInfo}
            notificationCounts={notificationCounts}
            memberCounts={memberCounts}
            markCategoryRead={markCategoryRead}
            userToken={userToken}
            userInfo={userInfo}
            userLogin={userLogin}
            userLogout={userLogout}
          />

          {toast && (
            <Toast
              message={toast.message}
              type={toast.type}
              onClose={() => setToast(null)}
            />
          )}
        </BrowserRouter>
      </LanguageContext.Provider>
    </ThemeContext.Provider>
  )
}

function AppRouter({
  token,
  agentInfo,
  login,
  logout,
  fetchAgentInfo,
  notificationCounts,
  memberCounts,
  markCategoryRead,
  userToken,
  userInfo,
  userLogin,
  userLogout,
}: {
  token: string | null
  agentInfo: any
  login: (token: string) => void
  logout: () => void
  fetchAgentInfo: () => Promise<void>
  notificationCounts: NotificationCounts
  memberCounts: MemberCounts
  markCategoryRead: (category: 'discussion' | 'strategy' | 'experiment') => void
  userToken: string | null
  userInfo: any
  userLogin: (token: string) => void
  userLogout: () => void
}) {
  const location = useLocation()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)

  // Agent-gated route: with a user session present, the agent token is being
  // auto-linked (POST /api/users/agent) — render a spinner instead of
  // redirecting, or the first click after login bounces to the leaderboard.
  const agentGate = (el: React.ReactElement) =>
    token ? el
    : userToken ? <div className="loading"><div className="spinner"></div></div>
    : <Navigate to="/login" replace />

  // Close mobile nav on route change
  useEffect(() => { setMobileNavOpen(false) }, [location.pathname])

  // Update browser tab title per route
  useEffect(() => {
    const PAGE_TITLES: Record<string, string> = {
      '/':                 'Sooppiy · Signals',
      '/market':           'Sooppiy · Signals',
      '/leaderboard':      'Sooppiy · Leaderboard',
      '/backtest':         'Sooppiy · Backtest',
      '/positions':        'Sooppiy · Positions',
      '/trade':            'Sooppiy · Trade',
      '/exchange':         'Sooppiy · Exchange',
      '/strategies':       'Sooppiy · Strategies',
      '/discussions':      'Sooppiy · Discussions',
      '/challenges':       'Sooppiy · Challenges',
      '/team-missions':    'Sooppiy · Team Missions',
      '/experiments':      'Sooppiy · Experiments',
      '/research-exports': 'Sooppiy · Research Exports',
      '/financial-events': 'Sooppiy · Financial Events',
      '/notifications':    'Sooppiy · Notifications',
      '/support':          'Sooppiy · Support',
      '/dev':              'Sooppiy · For Developers',
      '/login':            'Sooppiy · Login',
      '/register':         'Sooppiy · Register',
      '/about':            'Sooppiy',
    }
    const path = location.pathname
    // /agent/:id routes
    if (path.startsWith('/agent/')) { document.title = 'Sooppiy · Agent Profile'; return }
    document.title = PAGE_TITLES[path] ?? 'Sooppiy'
  }, [location.pathname])

  // Public leaderboard is the landing page — no login required to see top
  // agents. Marketing-style LandingPage moved to `/about` so existing copy
  // is preserved.
  if (location.pathname === '/about') {
    return (
      <Suspense fallback={<div className="loading"><div className="spinner"></div></div>}>
        <Routes>
          <Route path="/about" element={<LandingPage token={token} />} />
        </Routes>
      </Suspense>
    )
  }

  // Logged-out experience: no left menu. "/" is the marketing landing page and
  // the auth pages render full-screen. Everything else redirects to the landing.
  if (!token && !userToken) {
    return (
      <Suspense fallback={<div className="loading"><div className="spinner"></div></div>}>
        <Routes>
          <Route path="/" element={<MarketingPage />} />
          <Route path="/about" element={<MarketingPage />} />
          <Route path="/login" element={<LoginPage onLogin={login} />} />
          <Route path="/register" element={<RegisterPage onLogin={login} />} />
          <Route path="/agent-login" element={<LoginPage onLogin={login} />} />
          <Route path="/agent-register" element={<RegisterPage onLogin={login} />} />
          <Route path="/sign-in" element={<SignInPage onLogin={userLogin} />} />
          <Route path="/sign-up" element={<SignUpPage onLogin={userLogin} />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/auth/google/callback" element={<GoogleCallbackPage onLogin={userLogin} />} />
          {/* Enterprise contact is public — no account needed to ask for a contract. */}
          <Route path="/contract" element={<ContractPage />} />
          {/* Guest browsing: the leaderboard is public by design ("view profit
              curves and top agent performance without logging in"). */}
          <Route path="/leaderboard" element={<div className="page-container" style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 16px' }}><LeaderboardPage token={null} /></div>} />
          {/* docs are members-only: logged-out hits go to login first */}
          <Route path="/docs" element={<Navigate to="/login" replace />} />
          <Route path="/docs/:slug" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    )
  }

  // Membership gate: a signed-in human user without an active subscription is
  // held on the subscribe/contract pages until payment clears (login response
  // and /users/me expose subscription_status; see routes_subscriptions.py).
  if (userToken && userInfo && userInfo.subscription_status !== 'active') {
    return (
      <Suspense fallback={<div className="loading"><div className="spinner"></div></div>}>
        <Routes>
          <Route path="/subscribe" element={<SubscribePage userToken={userToken} onSignOut={userLogout} />} />
          <Route path="/contract" element={<ContractPage userToken={userToken} />} />
          <Route path="*" element={<Navigate to="/subscribe" replace />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <div className="app-container">
      {/* Desktop chrome (>768px). The Sidebar below is the mobile drawer. */}
      <TopNav
        token={token}
        agentInfo={agentInfo}
        onLogout={logout}
        userToken={userToken}
        userInfo={userInfo}
        onUserLogout={userLogout}
        notificationCounts={notificationCounts}
        memberCounts={memberCounts}
        onMarkCategoryRead={markCategoryRead}
      />

      <Sidebar
        token={token}
        agentInfo={agentInfo}
        onLogout={logout}
        userToken={userToken}
        userInfo={userInfo}
        onUserLogout={userLogout}
        notificationCounts={notificationCounts}
        memberCounts={memberCounts}
        onMarkCategoryRead={markCategoryRead}
        isOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />

      <main className="main-content" style={{ display: 'flex', gap: '24px' }}>
        {/* minWidth:0 — without it this flex item defaults to min-width:auto and
            wide children (e.g. the positions tables) push past the viewport and
            get clipped by .main-content instead of scrolling inside their own
            overflow container. */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <HamburgerButton isOpen={mobileNavOpen} onClick={() => setMobileNavOpen(o => !o)} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {/* Theme/language live in the desktop top bar; keep them here for
                  the mobile chrome only so they are not duplicated. */}
              <span className="mobile-only-chrome"><TopbarControls /></span>
              <GuideButton onClick={() => setGuideOpen(true)} />
            </div>
          </div>

          <Suspense fallback={<div className="loading"><div className="spinner"></div></div>}>
            <Routes>
              <Route path="/" element={<LeaderboardPage token={token} />} />
              <Route path="/dev" element={<DevPage />} />
              <Route path="/market" element={<MarketPage token={token} />} />
              <Route path="/leaderboard" element={<LeaderboardPage token={token} />} />
              <Route path="/challenges" element={<ChallengePage token={token} />} />
              <Route path="/challenges/:challengeKey" element={<ChallengePage token={token} />} />
              <Route path="/team-missions" element={<TeamMissionsPage token={token} />} />
              <Route path="/team-missions/:missionKey" element={<TeamMissionsPage token={token} />} />
              <Route path="/teams/:teamKey" element={<TeamMissionsPage token={token} />} />
              <Route path="/experiments" element={<ExperimentAdminPage token={token} />} />
              <Route path="/research-exports" element={<ResearchExportsPage />} />
              <Route path="/backtest" element={<BacktestPage token={token} />} />
              <Route path="/financial-events" element={<FinancialEventsPage />} />
              <Route path="/signals-board" element={<SignalsBoardPage />} />
              <Route path="/monitor" element={<MonitorPage token={token} />} />
              {/* live runs merged into /automation — keep old links working */}
              <Route path="/runs/live" element={<Navigate to="/automation" replace />} />
              <Route path="/consult" element={<ConsultPage token={token} />} />
              <Route path="/docs" element={<DocsPage token={token} userToken={userToken} />} />
              <Route path="/docs/:slug" element={<DocsPage token={token} userToken={userToken} />} />
                  <Route path="/strategies" element={<StrategiesPage />} />
              <Route path="/discussions" element={<DiscussionsPage />} />
              <Route path="/positions" element={<PositionsPage />} />
              {/* AI Analyst merged into Automation (one-off "analyze now" panel). */}
              <Route path="/analyst" element={<Navigate to="/automation" replace />} />
              <Route path="/automation" element={agentGate(<AutomationPage />)} />
              <Route path="/accounts" element={agentGate(<AccountsPage />)} />
              <Route path="/assets" element={agentGate(<AssetsPage />)} />
              <Route path="/spot" element={agentGate(<SpotPage />)} />
              <Route path="/futures" element={agentGate(<FuturesPage />)} />
              <Route path="/trade" element={agentGate(<TradePage token={token!} agentInfo={agentInfo} onTradeSuccess={fetchAgentInfo} />)} />
              <Route path="/exchange" element={agentGate(<ExchangePage token={token!} onExchangeSuccess={fetchAgentInfo} />)} />
              <Route path="/agent/:id" element={<AgentProfilePage />} />

              {/* Membership pages stay reachable for active subscribers. */}
              <Route path="/subscribe" element={<SubscribePage userToken={userToken} onSignOut={userLogout} />} />
              <Route path="/contract" element={<ContractPage userToken={userToken} />} />

              {/* Phase 5 — public-user auth (humans) */}
              <Route path="/sign-in" element={<SignInPage onLogin={userLogin} />} />
              <Route path="/sign-up" element={<SignUpPage onLogin={userLogin} />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/auth/mfa/setup" element={<MfaSetupPage userToken={userToken} />} />
              <Route path="/auth/google/callback" element={<GoogleCallbackPage onLogin={userLogin} />} />
              <Route
                path="/my-trading"
                element={userToken
                  ? <MyTradingPage userToken={userToken} onSignOut={userLogout} />
                  : <Navigate to="/sign-in" replace />}
              />
              <Route
                path="/notifications"
                element={userToken
                  ? <NotificationsPage userToken={userToken} />
                  : <Navigate to="/sign-in" replace />}
              />
              <Route
                path="/support"
                element={userToken
                  ? <SupportPage userToken={userToken} />
                  : <Navigate to="/sign-in" replace />}
              />
              <Route
                path="/settings"
                element={userToken
                  ? <SettingsPage userToken={userToken} userInfo={userInfo} onSignOut={userLogout} />
                  : <Navigate to="/sign-in" replace />}
              />

              {/* Already authenticated — auth pages redirect into the app.
                  (Logged-out auth flows are handled by the no-sidebar branch above.) */}
              <Route path="/agent-login" element={<Navigate to="/" replace />} />
              <Route path="/agent-register" element={<Navigate to="/" replace />} />
              <Route path="/login" element={<Navigate to="/" replace />} />
              <Route path="/register" element={<Navigate to="/" replace />} />

              <Route path="*" element={<Navigate to="/market" replace />} />
            </Routes>
          </Suspense>
        </div>
      </main>

      {/* Per-page guide — the topbar button opens this drawer, which resolves
          its content from the route registry in ./guides. */}
      <Suspense fallback={null}>
        <GuidePanel open={guideOpen} onClose={() => setGuideOpen(false)} />
      </Suspense>

      {/* AI Assistant — mounted once in the authed shell so it is reachable
          from every page and keeps its conversation across navigation. */}
      <Suspense fallback={null}>
        <AssistantDock token={token} />
      </Suspense>
    </div>
  )
}

export default App
