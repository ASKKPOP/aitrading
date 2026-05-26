/**
 * authV2.tsx — Phase 5 production auth UI.
 *
 * Public users sign in with email + password (optionally with TOTP MFA),
 * Google OAuth, or — when those land — Apple Sign In / Phone (SMS).
 * Keeps the existing /agent-login flow (claw_token paste) intact for
 * AI-agent developers; that's a separate audience.
 *
 * Components:
 *   SignInPage         — email+password → optional MFA step
 *   SignUpPage         — email → 6-digit code → password
 *   MfaSetupPage       — secret + otpauth URL + 10 backup codes
 *   GoogleCallbackPage — receives session, redirects to /my-trading
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { API_BASE } from './appShared'


export const USER_TOKEN_KEY = 'sooppiy_user_token'


function storeUserToken(token: string) {
  localStorage.setItem(USER_TOKEN_KEY, token)
}

function clearUserToken() {
  localStorage.removeItem(USER_TOKEN_KEY)
}


/**
 * Normalize a FastAPI error body to a renderable string.
 * Validation errors come back as `detail: [{ loc, msg, type }, ...]` — that
 * shape can't be rendered as a React child without crashing the tree.
 */
function errMessage(body: any, fallback: string): string {
  if (!body) return fallback
  const d = body.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((e: any) => e?.msg || e?.message || JSON.stringify(e)).join('; ')
  }
  if (d && typeof d === 'object') return d.msg || d.message || JSON.stringify(d)
  return fallback
}


// ─── Shared form chrome ──────────────────────────────────────────────────

function AuthShell({ title, subtitle, children }: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div style={{
      minHeight: '70vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 420,
        padding: 32,
        background: 'var(--surface, #faf6ec)',
        border: '1px solid var(--border, rgba(0,0,0,0.08))',
        borderRadius: 12,
        boxShadow: '0 2px 16px rgba(0,0,0,0.04)',
      }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--accent-primary, #b8542f)',
            marginBottom: 6,
          }}>Sooppiy</div>
          <h1 style={{ fontSize: 28, fontWeight: 500, margin: 0 }}>{title}</h1>
          {subtitle && (
            <p style={{ marginTop: 8, fontSize: 14, color: 'var(--muted, #6b7280)' }}>
              {subtitle}
            </p>
          )}
        </div>
        {children}
      </div>
    </div>
  )
}


const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  fontSize: 14,
  border: '1px solid var(--border, rgba(0,0,0,0.12))',
  borderRadius: 6,
  background: 'var(--bg, #fff)',
  marginBottom: 12,
  fontFamily: 'inherit',
}

const buttonStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  fontSize: 14,
  background: 'var(--accent-primary, #b8542f)',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  fontWeight: 500,
}

const buttonDisabledStyle: React.CSSProperties = {
  ...buttonStyle,
  background: '#cbd5e1',
  cursor: 'not-allowed',
  color: '#64748b',
}


// ─── /api/auth/providers fetch hook ──────────────────────────────────────

interface ProvidersResponse {
  email:  boolean
  google: boolean
  apple:  boolean
  phone:  boolean
}

function useProviders(): ProvidersResponse {
  const [providers, setProviders] = useState<ProvidersResponse>({
    email: true, google: false, apple: false, phone: false,
  })
  useEffect(() => {
    fetch(`${API_BASE}/auth/providers`)
      .then(r => r.json())
      .then(d => setProviders(d.providers))
      .catch(() => { /* fall back to defaults; email is always available */ })
  }, [])
  return providers
}


function OAuthButtons({ providers }: { providers: ProvidersResponse }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
      <a
        href={providers.google ? `${API_BASE}/auth/google/start` : undefined}
        onClick={e => { if (!providers.google) e.preventDefault() }}
        style={{
          ...buttonStyle,
          textDecoration: 'none',
          textAlign: 'center',
          display: 'block',
          background: providers.google ? '#fff' : '#f1f5f9',
          color: providers.google ? '#0f172a' : '#94a3b8',
          border: '1px solid var(--border, rgba(0,0,0,0.12))',
          cursor: providers.google ? 'pointer' : 'not-allowed',
        }}
      >
        Sign in with Google {!providers.google && '(unavailable)'}
      </a>
      <button
        type="button"
        disabled
        title="Coming soon — needs Apple Developer credentials"
        style={{ ...buttonDisabledStyle, background: '#fff', border: '1px solid var(--border, rgba(0,0,0,0.12))' }}
      >
        Sign in with Apple · Coming soon
      </button>
      <button
        type="button"
        disabled
        title="Coming soon — needs Twilio SMS credentials"
        style={{ ...buttonDisabledStyle, background: '#fff', border: '1px solid var(--border, rgba(0,0,0,0.12))' }}
      >
        Continue with Phone · Coming soon
      </button>
    </div>
  )
}


// ═══ SignInPage ═══════════════════════════════════════════════════════════

export function SignInPage({ onLogin }: { onLogin: (token: string) => void }) {
  const navigate = useNavigate()
  const providers = useProviders()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const [mfaCode, setMfaCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submitLogin(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/users/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), 'Sign-in failed'))
        return
      }
      const body = await r.json()
      if (body.requires_mfa) {
        setMfaToken(body.mfa_token)
        return
      }
      storeUserToken(body.token)
      onLogin(body.token)
      navigate('/my-trading')
    } catch (err) {
      setError(`Network error: ${err}`)
    } finally {
      setLoading(false)
    }
  }

  async function submitMfa(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/auth/mfa/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mfa_token: mfaToken, code: mfaCode }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), 'Invalid code'))

        return
      }
      const body = await r.json()
      storeUserToken(body.token)
      onLogin(body.token)
      navigate('/my-trading')
    } catch (err) {
      setError(`Network error: ${err}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title={mfaToken ? 'Two-factor code' : 'Sign in'}
      subtitle={mfaToken
        ? 'Enter the 6-digit code from your authenticator app, or a backup code.'
        : 'Welcome back to Sooppiy.'}
    >
      {!mfaToken ? (
        <form onSubmit={submitLogin}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            style={inputStyle}
            autoComplete="email"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            style={inputStyle}
            autoComplete="current-password"
          />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
          <OAuthButtons providers={providers} />
          <div style={{ marginTop: 20, fontSize: 13, color: 'var(--muted, #6b7280)', textAlign: 'center' }}>
            New here? <Link to="/sign-up" style={{ color: 'var(--accent-primary, #b8542f)' }}>Create an account</Link>
            {' · '}
            <Link to="/agent-login" style={{ color: 'var(--accent-primary, #b8542f)' }}>I have an AI agent</Link>
          </div>
        </form>
      ) : (
        <form onSubmit={submitMfa}>
          <input
            type="text"
            inputMode="numeric"
            placeholder="123456 or backup code"
            value={mfaCode}
            onChange={e => setMfaCode(e.target.value)}
            required
            autoFocus
            style={{ ...inputStyle, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.2em', textAlign: 'center' }}
            autoComplete="one-time-code"
          />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? 'Verifying…' : 'Verify'}
          </button>
          <button type="button" onClick={() => { setMfaToken(null); setMfaCode(''); setError('') }}
            style={{ ...buttonStyle, background: 'transparent', color: 'var(--muted, #6b7280)', marginTop: 8 }}>
            Back
          </button>
        </form>
      )}
    </AuthShell>
  )
}


// ═══ SignUpPage ═══════════════════════════════════════════════════════════

export function SignUpPage({ onLogin }: { onLogin: (token: string) => void }) {
  const navigate = useNavigate()
  const providers = useProviders()
  const [step, setStep] = useState<'email' | 'verify'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function sendCode(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/users/send-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), 'Could not send code'))
        return
      }
      setStep('verify')
    } finally {
      setLoading(false)
    }
  }

  async function completeRegister(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/users/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code, password }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), 'Registration failed'))
        return
      }
      const body = await r.json()
      storeUserToken(body.token)
      onLogin(body.token)
      navigate('/my-trading')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle={step === 'email'
        ? "We'll send a 6-digit code to your email."
        : `Enter the code we sent to ${email}, then choose a password.`}
    >
      {step === 'email' ? (
        <form onSubmit={sendCode}>
          <input type="email" placeholder="Email" value={email}
            onChange={e => setEmail(e.target.value)} required style={inputStyle} autoComplete="email" />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? 'Sending…' : 'Send code'}
          </button>
          <OAuthButtons providers={providers} />
          <div style={{ marginTop: 20, fontSize: 13, color: 'var(--muted, #6b7280)', textAlign: 'center' }}>
            Already have an account? <Link to="/sign-in" style={{ color: 'var(--accent-primary, #b8542f)' }}>Sign in</Link>
          </div>
        </form>
      ) : (
        <form onSubmit={completeRegister}>
          <input
            type="text"
            inputMode="numeric"
            placeholder="6-digit code"
            value={code}
            onChange={e => setCode(e.target.value)}
            required
            style={{ ...inputStyle, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.2em', textAlign: 'center' }}
            autoComplete="one-time-code"
          />
          <input type="password" placeholder="Choose a password (min 8 chars)" value={password}
            onChange={e => setPassword(e.target.value)} required minLength={8} style={inputStyle}
            autoComplete="new-password" />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? 'Creating…' : 'Create account'}
          </button>
          <button type="button" onClick={() => setStep('email')}
            style={{ ...buttonStyle, background: 'transparent', color: 'var(--muted, #6b7280)', marginTop: 8 }}>
            Use a different email
          </button>
        </form>
      )}
    </AuthShell>
  )
}


// ═══ MfaSetupPage ═════════════════════════════════════════════════════════

interface MfaSetupResponse {
  secret: string
  otpauth_url: string
  backup_codes: string[]
}

export function MfaSetupPage({ userToken }: { userToken: string | null }) {
  const navigate = useNavigate()
  const [setup, setSetup] = useState<MfaSetupResponse | null>(null)
  const [code, setCode] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Redirect to sign-in if not logged in.
  useEffect(() => {
    if (!userToken) navigate('/sign-in')
  }, [userToken, navigate])

  async function startSetup() {
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/auth/mfa/setup`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${userToken}` },
      })
      if (!r.ok) {
        setError('Could not start MFA setup')
        return
      }
      setSetup(await r.json())
    } finally {
      setLoading(false)
    }
  }

  async function verifyAndEnable(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/auth/mfa/verify-setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${userToken}` },
        body: JSON.stringify({ code }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), 'Invalid code'))

        return
      }
      setEnabled(true)
    } finally {
      setLoading(false)
    }
  }

  if (enabled) {
    return (
      <AuthShell title="Two-factor enabled ✓" subtitle="From your next sign-in, we'll ask for a 6-digit code.">
        <div style={{ background: '#fef3c7', border: '1px solid #fde68a', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          <strong>Save these backup codes</strong> somewhere safe. Each one can be used once if you lose access to your authenticator app.
        </div>
        <div style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 13,
          background: '#0f172a',
          color: '#fbbf24',
          padding: 16,
          borderRadius: 6,
          marginBottom: 16,
          lineHeight: 1.8,
          letterSpacing: '0.1em',
        }}>
          {setup?.backup_codes.map(c => <div key={c}>{c}</div>)}
        </div>
        <button onClick={() => navigate('/my-trading')} style={buttonStyle}>Continue</button>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Set up two-factor"
      subtitle="Use Google Authenticator, Authy, 1Password, or any TOTP-compatible app."
    >
      {!setup ? (
        <button onClick={startSetup} disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
          {loading ? 'Generating…' : 'Start setup'}
        </button>
      ) : (
        <form onSubmit={verifyAndEnable}>
          <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--muted, #6b7280)' }}>
            Add this account to your authenticator. Either scan a QR code from the URL below, or paste the secret directly.
          </div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 12,
            background: '#f1f5f9',
            padding: 10,
            borderRadius: 6,
            marginBottom: 12,
            wordBreak: 'break-all',
          }}>{setup.otpauth_url}</div>
          <div style={{ marginBottom: 12, fontSize: 13 }}>
            <strong>Secret:</strong>{' '}
            <code style={{ fontFamily: 'JetBrains Mono, monospace', userSelect: 'all' }}>{setup.secret}</code>
          </div>
          <input
            type="text"
            inputMode="numeric"
            placeholder="123456"
            value={code}
            onChange={e => setCode(e.target.value)}
            required
            style={{ ...inputStyle, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.2em', textAlign: 'center' }}
            autoComplete="one-time-code"
          />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? 'Verifying…' : 'Verify & enable'}
          </button>
        </form>
      )}
    </AuthShell>
  )
}


// ═══ GoogleCallbackPage ═══════════════════════════════════════════════════

export function GoogleCallbackPage({ onLogin }: { onLogin: (token: string) => void }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState('')

  useEffect(() => {
    const code = params.get('code')
    const state = params.get('state')
    if (!code || !state) {
      setError('Missing OAuth response parameters')
      return
    }
    // Forward to the backend callback; backend returns JSON with the token.
    fetch(`${API_BASE}/auth/google/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`)
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(d)))
      .then(d => {
        storeUserToken(d.token)
        onLogin(d.token)
        navigate('/my-trading')
      })
      .catch(d => setError(errMessage(d, 'Google sign-in failed')))
  }, [params, onLogin, navigate])

  return (
    <AuthShell title="Finishing Google sign-in…" subtitle="One moment.">
      {error
        ? <div style={{ color: '#dc2626', fontSize: 14 }}>{error}</div>
        : <div style={{ color: 'var(--muted, #6b7280)' }}>Verifying with Google…</div>}
    </AuthShell>
  )
}


// ═══ Export the token clearer for sign-out elsewhere ═════════════════════

export function signOutUser() {
  clearUserToken()
}
