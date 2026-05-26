/**
 * myTradingPage.tsx — Phase 5 private surface.
 *
 * Everything tied to the signed-in user's own trading lives here:
 *   - account header (email, MFA status, sign-out)
 *   - my positions (with current_price + unrealized PnL)
 *   - my followed providers (copy-trading targets)
 *   - my strategies (with backtest_validated flag)
 *   - my P&L history (linked profit_history endpoint)
 *
 * The page is auth-gated at the route level: if no user token is set,
 * App.tsx redirects to /sign-in. We additionally re-check here and bail
 * to /sign-in on a 401 from any of the fetches (token expired / revoked).
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { API_BASE } from './appShared'
import { signOutUser } from './authV2'


// ─── Section primitives ──────────────────────────────────────────────────

const sectionStyle: React.CSSProperties = {
  background: 'var(--surface, #faf6ec)',
  border: '1px solid var(--border, rgba(0,0,0,0.08))',
  borderRadius: 8,
  padding: 20,
  marginBottom: 16,
}

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  marginBottom: 12,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}


function Section({ title, action, children }: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div style={sectionStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={sectionTitleStyle}>{title}</div>
        {action}
      </div>
      {children}
    </div>
  )
}


// ─── Account header ──────────────────────────────────────────────────────

interface UserInfo {
  id: number
  email: string
  points: number
}

interface MfaStatus {
  enabled: boolean
  backup_codes_remaining: number
}


function AccountHeader({ user, mfa, onSignOut }: {
  user: UserInfo | null
  mfa: MfaStatus | null
  onSignOut: () => void
}) {
  return (
    <div style={{
      ...sectionStyle,
      background: 'var(--bg, #0f172a)',
      color: '#fff',
      border: 'none',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--accent-primary, #b8542f)',
            marginBottom: 6,
          }}>My Trading</div>
          <h1 style={{ fontSize: 28, fontWeight: 500, margin: 0 }}>
            {user?.email ?? '…'}
          </h1>
          <div style={{ marginTop: 8, fontSize: 13, opacity: 0.7 }}>
            {user && (
              <>Points: <strong>{user.points}</strong> · </>
            )}
            {mfa?.enabled
              ? <span style={{ color: '#86efac' }}>2FA enabled ({mfa.backup_codes_remaining} backup codes left)</span>
              : <Link to="/auth/mfa/setup" style={{ color: '#fde68a', textDecoration: 'underline' }}>Enable 2FA</Link>
            }
          </div>
        </div>
        <button
          onClick={onSignOut}
          style={{
            background: 'transparent',
            color: '#fff',
            border: '1px solid rgba(255,255,255,0.3)',
            padding: '6px 14px',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          Sign out
        </button>
      </div>
    </div>
  )
}


// ─── Page ────────────────────────────────────────────────────────────────

interface Position {
  position_id?: number
  id?: number
  symbol: string
  market: string
  side: string
  entry_price: number
  quantity: number
  current_price: number | null
  pnl?: number
}

interface Following {
  provider_id: number
  provider_name?: string
  total_profit_percent?: number
}

interface Strategy {
  strategy_id: number
  name: string
  backtest_validated: boolean
  last_backtest_sharpe: number | null
}


export function MyTradingPage({ userToken, onSignOut }: {
  userToken: string | null
  onSignOut: () => void
}) {
  const navigate = useNavigate()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [mfa, setMfa] = useState<MfaStatus | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [following, setFollowing] = useState<Following[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const auth = useCallback(() => ({ Authorization: `Bearer ${userToken}` }), [userToken])

  const signOutAndLeave = useCallback(() => {
    signOutUser()
    onSignOut()
    navigate('/sign-in')
  }, [navigate, onSignOut])

  useEffect(() => {
    if (!userToken) { navigate('/sign-in'); return }

    let aborted = false
    setLoading(true)
    setError('')

    async function load() {
      try {
        const meRes = await fetch(`${API_BASE}/users/me`, { headers: auth() })
        if (meRes.status === 401) { signOutAndLeave(); return }
        if (!meRes.ok) throw new Error('Could not load account')
        const me: UserInfo = await meRes.json()
        if (aborted) return
        setUser(me)

        // Run the others in parallel; tolerate individual failures
        const [mfaRes, posRes, followRes, stratRes] = await Promise.all([
          fetch(`${API_BASE}/auth/mfa/status`, { headers: auth() }),
          fetch(`${API_BASE}/positions`,        { headers: auth() }),
          fetch(`${API_BASE}/signals/following`, { headers: auth() }),
          fetch(`${API_BASE}/strategies`,        { headers: auth() }),
        ])
        if (aborted) return
        if (mfaRes.ok)    setMfa(await mfaRes.json())
        if (posRes.ok) {
          const body = await posRes.json()
          setPositions(Array.isArray(body) ? body : (body.positions ?? []))
        }
        if (followRes.ok) {
          const body = await followRes.json()
          setFollowing(Array.isArray(body) ? body : (body.following ?? body.providers ?? []))
        }
        if (stratRes.ok) {
          const body = await stratRes.json()
          setStrategies(Array.isArray(body) ? body : (body.strategies ?? []))
        }
      } catch (e: any) {
        if (!aborted) setError(e?.message || 'Failed to load')
      } finally {
        if (!aborted) setLoading(false)
      }
    }
    load()
    return () => { aborted = true }
  }, [userToken, auth, navigate, signOutAndLeave])

  if (!userToken) return null

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 0' }}>
      <AccountHeader user={user} mfa={mfa} onSignOut={signOutAndLeave} />

      {loading && <div style={{ padding: 20, color: 'var(--muted, #6b7280)' }}>Loading your trading…</div>}
      {error && <div style={{ color: '#dc2626', padding: 12 }}>{error}</div>}

      <Section
        title={`📍 Positions (${positions.length})`}
        action={<Link to="/positions" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>View all →</Link>}
      >
        {positions.length === 0 ? (
          <div style={{ color: 'var(--muted, #6b7280)', fontSize: 14 }}>
            You have no open positions yet. Start by <Link to="/leaderboard">following an agent</Link>.
          </div>
        ) : (
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead style={{ textAlign: 'left' }}>
              <tr style={{ borderBottom: '1px solid var(--border, rgba(0,0,0,0.08))' }}>
                <th style={{ padding: '8px 4px' }}>Symbol</th>
                <th>Market</th>
                <th>Side</th>
                <th style={{ textAlign: 'right' }}>Qty</th>
                <th style={{ textAlign: 'right' }}>Entry</th>
                <th style={{ textAlign: 'right' }}>Current</th>
              </tr>
            </thead>
            <tbody>
              {positions.slice(0, 10).map((p, i) => (
                <tr key={p.position_id ?? p.id ?? i} style={{ borderBottom: '1px solid var(--border, rgba(0,0,0,0.04))' }}>
                  <td style={{ padding: '8px 4px', fontWeight: 500 }}>{p.symbol}</td>
                  <td>{p.market}</td>
                  <td style={{ color: p.side === 'long' ? '#15803d' : '#b91c1c' }}>{p.side}</td>
                  <td style={{ textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>{p.quantity}</td>
                  <td style={{ textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>{p.entry_price}</td>
                  <td style={{ textAlign: 'right', fontFamily: 'JetBrains Mono, monospace' }}>
                    {p.current_price ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section
        title={`⊞ Following (${following.length})`}
        action={<Link to="/copytrading" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>Manage →</Link>}
      >
        {following.length === 0 ? (
          <div style={{ color: 'var(--muted, #6b7280)', fontSize: 14 }}>
            Not following anyone yet. Find agents on the <Link to="/leaderboard">leaderboard</Link>.
          </div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
            {following.slice(0, 8).map((f, i) => (
              <li key={f.provider_id ?? i} style={{ marginBottom: 4 }}>
                {f.provider_name ?? `Provider #${f.provider_id}`}
                {f.total_profit_percent !== undefined && (
                  <span style={{ color: f.total_profit_percent >= 0 ? '#15803d' : '#b91c1c', marginLeft: 8 }}>
                    {f.total_profit_percent >= 0 ? '+' : ''}{f.total_profit_percent.toFixed(2)}%
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title={`↗ Strategies (${strategies.length})`}
        action={<Link to="/strategies" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>All →</Link>}
      >
        {strategies.length === 0 ? (
          <div style={{ color: 'var(--muted, #6b7280)', fontSize: 14 }}>
            No strategies yet.
          </div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
            {strategies.slice(0, 8).map(s => (
              <li key={s.strategy_id} style={{ marginBottom: 4 }}>
                <strong>{s.name}</strong>
                {s.backtest_validated && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: '#15803d' }}>
                    ✓ backtest-validated
                  </span>
                )}
                {s.last_backtest_sharpe !== null && s.last_backtest_sharpe !== undefined && (
                  <span style={{ marginLeft: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: 'var(--muted, #6b7280)' }}>
                    Sharpe {s.last_backtest_sharpe.toFixed(2)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="📈 P&L history"
        action={<Link to="/leaderboard" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>Open chart →</Link>}
      >
        <div style={{ color: 'var(--muted, #6b7280)', fontSize: 14 }}>
          Detailed profit chart is available on your <Link to="/leaderboard">leaderboard profile</Link>.
        </div>
      </Section>
    </div>
  )
}
