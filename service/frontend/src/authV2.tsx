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

import { API_BASE, useLanguage } from './appShared'
import { tr } from './i18n'


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
        background: 'var(--bg-card, #faf6ec)',
        border: '1px solid var(--border-color, rgba(0,0,0,0.08))',
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
            <p style={{ marginTop: 8, fontSize: 14, color: 'var(--text-muted, #6b7280)' }}>
              {subtitle}
            </p>
          )}
        </div>
        {children}
        {/* Legal links must be reachable from the auth pages — A2P 10DLC
            vetting (error 30908) checks that the privacy policy is
            discoverable from the pages where users sign up. */}
        <div style={{ marginTop: 20, paddingTop: 14, borderTop: '1px solid var(--border-color, rgba(0,0,0,0.08))', fontSize: 12, color: 'var(--text-muted, #6b7280)', textAlign: 'center' }}>
          <a href="https://sooppiy.com/privacypolicy" target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>Privacy Policy</a>
          {' · '}
          <a href="https://sooppiy.com/termsconditions" target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>Terms &amp; Conditions</a>
          {' · '}
          <a href="https://sooppiy.com/smsoptin" target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>SMS Policy</a>
        </div>
      </div>
    </div>
  )
}


const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  fontSize: 14,
  border: '1px solid var(--border-color, rgba(0,0,0,0.12))',
  borderRadius: 6,
  background: 'var(--bg-secondary, #fff)',
  color: 'var(--text-primary, #0b0b0b)',
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
  const { language } = useLanguage()
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
          border: '1px solid var(--border-color, rgba(0,0,0,0.12))',
          cursor: providers.google ? 'pointer' : 'not-allowed',
        }}
      >
        {tr(language, { ko: 'Google로 로그인', en: 'Sign in with Google', ja: 'Googleでログイン', th: 'เข้าสู่ระบบด้วย Google', vi: 'Đăng nhập bằng Google', id: 'Masuk dengan Google' })} {!providers.google && tr(language, { ko: '(사용 불가)', en: '(unavailable)', ja: '(利用不可)', th: '(ไม่พร้อมใช้งาน)', vi: '(không khả dụng)', id: '(tidak tersedia)' })}
      </a>
      <button
        type="button"
        disabled
        title={tr(language, { ko: '곧 지원 — Apple Developer 자격 증명 필요', en: 'Coming soon — needs Apple Developer credentials', ja: '近日対応 — Apple Developer 資格情報が必要', th: 'เร็ว ๆ นี้ — ต้องใช้ข้อมูลรับรอง Apple Developer', vi: 'Sắp có — cần thông tin Apple Developer', id: 'Segera hadir — memerlukan kredensial Apple Developer' })}
        style={{ ...buttonDisabledStyle, background: '#fff', border: '1px solid var(--border-color, rgba(0,0,0,0.12))' }}
      >
        {tr(language, { ko: 'Apple로 로그인 · 곧 지원', en: 'Sign in with Apple · Coming soon', ja: 'Appleでログイン · 近日対応', th: 'เข้าสู่ระบบด้วย Apple · เร็ว ๆ นี้', vi: 'Đăng nhập bằng Apple · Sắp có', id: 'Masuk dengan Apple · Segera hadir' })}
      </button>
      <button
        type="button"
        disabled
        title={tr(language, { ko: '곧 지원 — Twilio SMS 자격 증명 필요', en: 'Coming soon — needs Twilio SMS credentials', ja: '近日対応 — Twilio SMS 資格情報が必要', th: 'เร็ว ๆ นี้ — ต้องใช้ข้อมูลรับรอง Twilio SMS', vi: 'Sắp có — cần thông tin Twilio SMS', id: 'Segera hadir — memerlukan kredensial SMS Twilio' })}
        style={{ ...buttonDisabledStyle, background: '#fff', border: '1px solid var(--border-color, rgba(0,0,0,0.12))' }}
      >
        {tr(language, { ko: '전화번호로 계속 · 곧 지원', en: 'Continue with Phone · Coming soon', ja: '電話番号で続行 · 近日対応', th: 'ดำเนินการต่อด้วยโทรศัพท์ · เร็ว ๆ นี้', vi: 'Tiếp tục bằng điện thoại · Sắp có', id: 'Lanjut dengan nomor telepon · Segera hadir' })}
      </button>
    </div>
  )
}


// ═══ SignInPage ═══════════════════════════════════════════════════════════

export function SignInPage({ onLogin }: { onLogin: (token: string) => void }) {
  const navigate = useNavigate()
  const { language } = useLanguage()
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
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '로그인에 실패했습니다', en: 'Sign-in failed', ja: 'ログインに失敗しました', th: 'เข้าสู่ระบบไม่สำเร็จ', vi: 'Đăng nhập thất bại', id: 'Gagal masuk' })))
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
      setError(tr(language, { ko: `네트워크 오류: ${err}`, en: `Network error: ${err}`, ja: `ネットワークエラー: ${err}`, th: `ข้อผิดพลาดเครือข่าย: ${err}`, vi: `Lỗi mạng: ${err}`, id: `Kesalahan jaringan: ${err}` }))
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
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '잘못된 코드입니다', en: 'Invalid code', ja: '無効なコードです', th: 'รหัสไม่ถูกต้อง', vi: 'Mã không hợp lệ', id: 'Kode tidak valid' })))

        return
      }
      const body = await r.json()
      storeUserToken(body.token)
      onLogin(body.token)
      navigate('/my-trading')
    } catch (err) {
      setError(tr(language, { ko: `네트워크 오류: ${err}`, en: `Network error: ${err}`, ja: `ネットワークエラー: ${err}`, th: `ข้อผิดพลาดเครือข่าย: ${err}`, vi: `Lỗi mạng: ${err}`, id: `Kesalahan jaringan: ${err}` }))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title={mfaToken
        ? tr(language, { ko: '2단계 인증 코드', en: 'Two-factor code', ja: '2段階認証コード', th: 'รหัสยืนยันสองขั้นตอน', vi: 'Mã xác thực hai lớp', id: 'Kode dua faktor' })
        : tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' })}
      subtitle={mfaToken
        ? tr(language, { ko: '인증 앱의 6자리 코드 또는 백업 코드를 입력하세요.', en: 'Enter the 6-digit code from your authenticator app, or a backup code.', ja: '認証アプリの6桁コード、またはバックアップコードを入力してください。', th: 'กรอกรหัส 6 หลักจากแอปยืนยันตัวตน หรือรหัสสำรอง', vi: 'Nhập mã 6 chữ số từ ứng dụng xác thực, hoặc mã dự phòng.', id: 'Masukkan kode 6 digit dari aplikasi autentikator Anda, atau kode cadangan.' })
        : tr(language, { ko: 'Sooppiy에 다시 오신 것을 환영합니다.', en: 'Welcome back to Sooppiy.', ja: 'Sooppiy へおかえりなさい。', th: 'ยินดีต้อนรับกลับสู่ Sooppiy', vi: 'Chào mừng trở lại Sooppiy.', id: 'Selamat datang kembali di Sooppiy.' })}
    >
      {!mfaToken ? (
        <form onSubmit={submitLogin}>
          <input
            type="email"
            placeholder={tr(language, { ko: '이메일', en: 'Email', ja: 'メールアドレス', th: 'อีเมล', vi: 'Email', id: 'Email' })}
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            style={inputStyle}
            autoComplete="email"
          />
          <input
            type="password"
            placeholder={tr(language, { ko: '비밀번호', en: 'Password', ja: 'パスワード', th: 'รหัสผ่าน', vi: 'Mật khẩu', id: 'Kata sandi' })}
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            style={inputStyle}
            autoComplete="current-password"
          />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? tr(language, { ko: '로그인 중…', en: 'Signing in…', ja: 'ログイン中…', th: 'กำลังเข้าสู่ระบบ…', vi: 'Đang đăng nhập…', id: 'Sedang masuk…' }) : tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' })}
          </button>
          <OAuthButtons providers={providers} />
          <div style={{ marginTop: 12, fontSize: 13, textAlign: 'center' }}>
            <Link to="/forgot-password" style={{ color: 'var(--text-muted, #6b7280)' }}>{tr(language, { ko: '비밀번호를 잊으셨나요?', en: 'Forgot password?', ja: 'パスワードをお忘れですか？', th: 'ลืมรหัสผ่าน?', vi: 'Quên mật khẩu?', id: 'Lupa kata sandi?' })}</Link>
          </div>
          <div style={{ marginTop: 20, fontSize: 13, color: 'var(--text-muted, #6b7280)', textAlign: 'center' }}>
            {tr(language, { ko: '처음이신가요?', en: 'New here?', ja: 'はじめての方はこちら', th: 'เพิ่งเข้ามาใช่ไหม?', vi: 'Lần đầu ở đây?', id: 'Baru di sini?' })} <Link to="/sign-up" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '계정 만들기', en: 'Create an account', ja: 'アカウントを作成', th: 'สร้างบัญชี', vi: 'Tạo tài khoản', id: 'Buat akun' })}</Link>
            {' · '}
            <Link to="/agent-login" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: 'AI 에이전트가 있어요', en: 'I have an AI agent', ja: 'AIエージェントを持っています', th: 'ฉันมี AI เอเจนต์', vi: 'Tôi có AI agent', id: 'Saya punya agen AI' })}</Link>
          </div>
        </form>
      ) : (
        <form onSubmit={submitMfa}>
          <input
            type="text"
            inputMode="numeric"
            placeholder={tr(language, { ko: '123456 또는 백업 코드', en: '123456 or backup code', ja: '123456 またはバックアップコード', th: '123456 หรือรหัสสำรอง', vi: '123456 hoặc mã dự phòng', id: '123456 atau kode cadangan' })}
            value={mfaCode}
            onChange={e => setMfaCode(e.target.value)}
            required
            autoFocus
            style={{ ...inputStyle, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.2em', textAlign: 'center' }}
            autoComplete="one-time-code"
          />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? tr(language, { ko: '확인 중…', en: 'Verifying…', ja: '確認中…', th: 'กำลังยืนยัน…', vi: 'Đang xác minh…', id: 'Memverifikasi…' }) : tr(language, { ko: '확인', en: 'Verify', ja: '確認', th: 'ยืนยัน', vi: 'Xác minh', id: 'Verifikasi' })}
          </button>
          <button type="button" onClick={() => { setMfaToken(null); setMfaCode(''); setError('') }}
            style={{ ...buttonStyle, background: 'transparent', color: 'var(--text-muted, #6b7280)', marginTop: 8 }}>
            {tr(language, { ko: '뒤로', en: 'Back', ja: '戻る', th: 'กลับ', vi: 'Quay lại', id: 'Kembali' })}
          </button>
        </form>
      )}
    </AuthShell>
  )
}


// ═══ SignUpPage ═══════════════════════════════════════════════════════════

export function SignUpPage({ onLogin }: { onLogin: (token: string) => void }) {
  const navigate = useNavigate()
  const { language } = useLanguage()
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
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '코드를 보낼 수 없습니다', en: 'Could not send code', ja: 'コードを送信できませんでした', th: 'ไม่สามารถส่งรหัสได้', vi: 'Không thể gửi mã', id: 'Tidak dapat mengirim kode' })))
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
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '가입에 실패했습니다', en: 'Registration failed', ja: '登録に失敗しました', th: 'ลงทะเบียนไม่สำเร็จ', vi: 'Đăng ký thất bại', id: 'Pendaftaran gagal' })))
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
      title={tr(language, { ko: '계정을 만드세요', en: 'Create your account', ja: 'アカウントを作成しましょう', th: 'สร้างบัญชีของคุณ', vi: 'Tạo tài khoản của bạn', id: 'Buat akun Anda' })}
      subtitle={step === 'email'
        ? tr(language, { ko: '이메일로 6자리 코드를 보내드립니다.', en: "We'll send a 6-digit code to your email.", ja: 'メールに6桁のコードを送信します。', th: 'เราจะส่งรหัส 6 หลักไปยังอีเมลของคุณ', vi: 'Chúng tôi sẽ gửi mã 6 chữ số đến email của bạn.', id: 'Kami akan mengirim kode 6 digit ke email Anda.' })
        : tr(language, { ko: `${email}로 보낸 코드를 입력한 뒤 비밀번호를 설정하세요.`, en: `Enter the code we sent to ${email}, then choose a password.`, ja: `${email} に送信したコードを入力し、パスワードを設定してください。`, th: `กรอกรหัสที่เราส่งไปยัง ${email} แล้วตั้งรหัสผ่าน`, vi: `Nhập mã chúng tôi đã gửi đến ${email}, sau đó chọn mật khẩu.`, id: `Masukkan kode yang kami kirim ke ${email}, lalu pilih kata sandi.` })}
    >
      {step === 'email' ? (
        <form onSubmit={sendCode}>
          <input type="email" placeholder={tr(language, { ko: '이메일', en: 'Email', ja: 'メールアドレス', th: 'อีเมล', vi: 'Email', id: 'Email' })} value={email}
            onChange={e => setEmail(e.target.value)} required style={inputStyle} autoComplete="email" />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? tr(language, { ko: '전송 중…', en: 'Sending…', ja: '送信中…', th: 'กำลังส่ง…', vi: 'Đang gửi…', id: 'Mengirim…' }) : tr(language, { ko: '코드 보내기', en: 'Send code', ja: 'コードを送信', th: 'ส่งรหัส', vi: 'Gửi mã', id: 'Kirim kode' })}
          </button>
          <OAuthButtons providers={providers} />
          <div style={{ marginTop: 20, fontSize: 13, color: 'var(--text-muted, #6b7280)', textAlign: 'center' }}>
            {tr(language, { ko: '이미 계정이 있으신가요?', en: 'Already have an account?', ja: 'すでにアカウントをお持ちですか？', th: 'มีบัญชีอยู่แล้ว?', vi: 'Đã có tài khoản?', id: 'Sudah punya akun?' })} <Link to="/sign-in" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' })}</Link>
          </div>
        </form>
      ) : (
        <form onSubmit={completeRegister}>
          <input
            type="text"
            inputMode="numeric"
            placeholder={tr(language, { ko: '6자리 코드', en: '6-digit code', ja: '6桁のコード', th: 'รหัส 6 หลัก', vi: 'Mã 6 chữ số', id: 'Kode 6 digit' })}
            value={code}
            onChange={e => setCode(e.target.value)}
            required
            style={{ ...inputStyle, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.2em', textAlign: 'center' }}
            autoComplete="one-time-code"
          />
          <input type="password" placeholder={tr(language, { ko: '비밀번호 설정 (최소 8자)', en: 'Choose a password (min 8 chars)', ja: 'パスワードを設定 (8文字以上)', th: 'ตั้งรหัสผ่าน (อย่างน้อย 8 ตัวอักษร)', vi: 'Chọn mật khẩu (tối thiểu 8 ký tự)', id: 'Pilih kata sandi (min. 8 karakter)' })} value={password}
            onChange={e => setPassword(e.target.value)} required minLength={8} style={inputStyle}
            autoComplete="new-password" />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? tr(language, { ko: '생성 중…', en: 'Creating…', ja: '作成中…', th: 'กำลังสร้าง…', vi: 'Đang tạo…', id: 'Membuat…' }) : tr(language, { ko: '계정 만들기', en: 'Create account', ja: 'アカウントを作成', th: 'สร้างบัญชี', vi: 'Tạo tài khoản', id: 'Buat akun' })}
          </button>
          <button type="button" onClick={() => setStep('email')}
            style={{ ...buttonStyle, background: 'transparent', color: 'var(--text-muted, #6b7280)', marginTop: 8 }}>
            {tr(language, { ko: '다른 이메일 사용', en: 'Use a different email', ja: '別のメールアドレスを使う', th: 'ใช้อีเมลอื่น', vi: 'Dùng email khác', id: 'Gunakan email lain' })}
          </button>
        </form>
      )}
    </AuthShell>
  )
}


// ═══ ForgotPasswordPage ═══════════════════════════════════════════════════

export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const { language } = useLanguage()
  const [step, setStep] = useState<'email' | 'reset' | 'done'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function sendResetCode(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/users/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '코드를 보낼 수 없습니다', en: 'Could not send code', ja: 'コードを送信できませんでした', th: 'ไม่สามารถส่งรหัสได้', vi: 'Không thể gửi mã', id: 'Tidak dapat mengirim kode' })))
        return
      }
      setStep('reset')
    } catch (err) {
      setError(tr(language, { ko: `네트워크 오류: ${err}`, en: `Network error: ${err}`, ja: `ネットワークエラー: ${err}`, th: `ข้อผิดพลาดเครือข่าย: ${err}`, vi: `Lỗi mạng: ${err}`, id: `Kesalahan jaringan: ${err}` }))
    } finally {
      setLoading(false)
    }
  }

  async function submitReset(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/users/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code, new_password: newPassword }),
      })
      if (!r.ok) {
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '비밀번호를 변경할 수 없습니다', en: 'Could not reset password', ja: 'パスワードをリセットできませんでした', th: 'ไม่สามารถรีเซ็ตรหัสผ่านได้', vi: 'Không thể đặt lại mật khẩu', id: 'Tidak dapat mengatur ulang kata sandi' })))
        return
      }
      setStep('done')
    } catch (err) {
      setError(tr(language, { ko: `네트워크 오류: ${err}`, en: `Network error: ${err}`, ja: `ネットワークエラー: ${err}`, th: `ข้อผิดพลาดเครือข่าย: ${err}`, vi: `Lỗi mạng: ${err}`, id: `Kesalahan jaringan: ${err}` }))
    } finally {
      setLoading(false)
    }
  }

  if (step === 'done') {
    return (
      <AuthShell
        title={tr(language, { ko: '비밀번호 변경 완료 ✓', en: 'Password updated ✓', ja: 'パスワードを更新しました ✓', th: 'อัปเดตรหัสผ่านแล้ว ✓', vi: 'Đã cập nhật mật khẩu ✓', id: 'Kata sandi diperbarui ✓' })}
        subtitle={tr(language, { ko: '새 비밀번호로 로그인하세요.', en: 'Sign in with your new password.', ja: '新しいパスワードでログインしてください。', th: 'เข้าสู่ระบบด้วยรหัสผ่านใหม่', vi: 'Đăng nhập bằng mật khẩu mới của bạn.', id: 'Masuk dengan kata sandi baru Anda.' })}
      >
        <button onClick={() => navigate('/sign-in')} style={buttonStyle}>
          {tr(language, { ko: '로그인으로 이동', en: 'Go to sign in', ja: 'ログインへ', th: 'ไปที่หน้าเข้าสู่ระบบ', vi: 'Đến trang đăng nhập', id: 'Ke halaman masuk' })}
        </button>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title={tr(language, { ko: '비밀번호 재설정', en: 'Reset your password', ja: 'パスワードをリセット', th: 'รีเซ็ตรหัสผ่านของคุณ', vi: 'Đặt lại mật khẩu của bạn', id: 'Atur ulang kata sandi Anda' })}
      subtitle={step === 'email'
        ? tr(language, { ko: '가입한 이메일로 6자리 코드를 보내드립니다.', en: "Enter your account email and we'll send a 6-digit code.", ja: 'アカウントのメールアドレスに6桁のコードを送信します。', th: 'กรอกอีเมลบัญชีของคุณ แล้วเราจะส่งรหัส 6 หลักให้', vi: 'Nhập email tài khoản và chúng tôi sẽ gửi mã 6 chữ số.', id: 'Masukkan email akun Anda dan kami akan mengirim kode 6 digit.' })
        : tr(language, { ko: `${email}로 보낸 코드를 입력한 뒤 새 비밀번호를 설정하세요.`, en: `Enter the code we sent to ${email}, then choose a new password.`, ja: `${email} に送信したコードを入力し、新しいパスワードを設定してください。`, th: `กรอกรหัสที่เราส่งไปยัง ${email} แล้วตั้งรหัสผ่านใหม่`, vi: `Nhập mã chúng tôi đã gửi đến ${email}, sau đó chọn mật khẩu mới.`, id: `Masukkan kode yang kami kirim ke ${email}, lalu pilih kata sandi baru.` })}
    >
      {step === 'email' ? (
        <form onSubmit={sendResetCode}>
          <input type="email" placeholder={tr(language, { ko: '이메일', en: 'Email', ja: 'メールアドレス', th: 'อีเมล', vi: 'Email', id: 'Email' })} value={email}
            onChange={e => setEmail(e.target.value)} required style={inputStyle} autoComplete="email" />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? tr(language, { ko: '전송 중…', en: 'Sending…', ja: '送信中…', th: 'กำลังส่ง…', vi: 'Đang gửi…', id: 'Mengirim…' }) : tr(language, { ko: '코드 보내기', en: 'Send code', ja: 'コードを送信', th: 'ส่งรหัส', vi: 'Gửi mã', id: 'Kirim kode' })}
          </button>
          <div style={{ marginTop: 20, fontSize: 13, color: 'var(--text-muted, #6b7280)', textAlign: 'center' }}>
            <Link to="/sign-in" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '로그인으로 돌아가기', en: 'Back to sign in', ja: 'ログインに戻る', th: 'กลับไปหน้าเข้าสู่ระบบ', vi: 'Quay lại đăng nhập', id: 'Kembali ke halaman masuk' })}</Link>
          </div>
        </form>
      ) : (
        <form onSubmit={submitReset}>
          <input
            type="text"
            inputMode="numeric"
            placeholder={tr(language, { ko: '6자리 코드', en: '6-digit code', ja: '6桁のコード', th: 'รหัส 6 หลัก', vi: 'Mã 6 chữ số', id: 'Kode 6 digit' })}
            value={code}
            onChange={e => setCode(e.target.value)}
            required
            style={{ ...inputStyle, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.2em', textAlign: 'center' }}
            autoComplete="one-time-code"
          />
          <input type="password" placeholder={tr(language, { ko: '새 비밀번호 (최소 8자)', en: 'New password (min 8 chars)', ja: '新しいパスワード (8文字以上)', th: 'รหัสผ่านใหม่ (อย่างน้อย 8 ตัวอักษร)', vi: 'Mật khẩu mới (tối thiểu 8 ký tự)', id: 'Kata sandi baru (min. 8 karakter)' })} value={newPassword}
            onChange={e => setNewPassword(e.target.value)} required minLength={8} style={inputStyle}
            autoComplete="new-password" />
          {error && <div style={{ color: '#dc2626', fontSize: 13, marginBottom: 12 }}>{error}</div>}
          <button type="submit" disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
            {loading ? tr(language, { ko: '변경 중…', en: 'Resetting…', ja: 'リセット中…', th: 'กำลังรีเซ็ต…', vi: 'Đang đặt lại…', id: 'Mengatur ulang…' }) : tr(language, { ko: '비밀번호 변경', en: 'Reset password', ja: 'パスワードをリセット', th: 'รีเซ็ตรหัสผ่าน', vi: 'Đặt lại mật khẩu', id: 'Atur ulang kata sandi' })}
          </button>
          <button type="button" onClick={() => { setStep('email'); setCode(''); setNewPassword(''); setError('') }}
            style={{ ...buttonStyle, background: 'transparent', color: 'var(--text-muted, #6b7280)', marginTop: 8 }}>
            {tr(language, { ko: '다른 이메일 사용', en: 'Use a different email', ja: '別のメールアドレスを使う', th: 'ใช้อีเมลอื่น', vi: 'Dùng email khác', id: 'Gunakan email lain' })}
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
  const { language } = useLanguage()
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
        setError(tr(language, { ko: 'MFA 설정을 시작할 수 없습니다', en: 'Could not start MFA setup', ja: 'MFAセットアップを開始できませんでした', th: 'ไม่สามารถเริ่มตั้งค่า MFA ได้', vi: 'Không thể bắt đầu thiết lập MFA', id: 'Tidak dapat memulai penyiapan MFA' }))
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
        setError(errMessage(await r.json().catch(() => null), tr(language, { ko: '잘못된 코드입니다', en: 'Invalid code', ja: '無効なコードです', th: 'รหัสไม่ถูกต้อง', vi: 'Mã không hợp lệ', id: 'Kode tidak valid' })))

        return
      }
      setEnabled(true)
    } finally {
      setLoading(false)
    }
  }

  if (enabled) {
    return (
      <AuthShell title={tr(language, { ko: '2단계 인증 활성화됨 ✓', en: 'Two-factor enabled ✓', ja: '2段階認証を有効化 ✓', th: 'เปิดใช้งานสองขั้นตอนแล้ว ✓', vi: 'Đã bật xác thực hai lớp ✓', id: 'Autentikasi dua faktor aktif ✓' })} subtitle={tr(language, { ko: '다음 로그인부터 6자리 코드를 요청합니다.', en: "From your next sign-in, we'll ask for a 6-digit code.", ja: '次回のログインから6桁のコードを求めます。', th: 'ตั้งแต่การเข้าสู่ระบบครั้งถัดไป เราจะขอรหัส 6 หลัก', vi: 'Từ lần đăng nhập tới, chúng tôi sẽ yêu cầu mã 6 chữ số.', id: 'Mulai masuk berikutnya, kami akan meminta kode 6 digit.' })}>
        <div style={{ background: '#fef3c7', border: '1px solid #fde68a', color: '#92400e', padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13 }}>
          <strong>{tr(language, { ko: '이 백업 코드를 저장하세요', en: 'Save these backup codes', ja: 'これらのバックアップコードを保存してください', th: 'บันทึกรหัสสำรองเหล่านี้', vi: 'Lưu các mã dự phòng này', id: 'Simpan kode cadangan ini' })}</strong>{tr(language, { ko: ' 안전한 곳에. 인증 앱에 접근할 수 없을 때 각 코드는 한 번씩 사용할 수 있습니다.', en: ' somewhere safe. Each one can be used once if you lose access to your authenticator app.', ja: ' 安全な場所に。認証アプリにアクセスできなくなった場合、各コードは一度ずつ使用できます。', th: ' ไว้ในที่ปลอดภัย แต่ละรหัสใช้ได้ครั้งเดียวหากคุณเข้าถึงแอปยืนยันตัวตนไม่ได้', vi: ' ở nơi an toàn. Mỗi mã dùng được một lần nếu bạn mất quyền truy cập ứng dụng xác thực.', id: ' di tempat yang aman. Masing-masing dapat dipakai sekali jika Anda kehilangan akses ke aplikasi autentikator.' })}
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
        <button onClick={() => navigate('/my-trading')} style={buttonStyle}>{tr(language, { ko: '계속', en: 'Continue', ja: '続行', th: 'ดำเนินการต่อ', vi: 'Tiếp tục', id: 'Lanjutkan' })}</button>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title={tr(language, { ko: '2단계 인증 설정', en: 'Set up two-factor', ja: '2段階認証を設定', th: 'ตั้งค่าสองขั้นตอน', vi: 'Thiết lập xác thực hai lớp', id: 'Siapkan autentikasi dua faktor' })}
      subtitle={tr(language, { ko: 'Google Authenticator, Authy, 1Password 등 TOTP 호환 앱을 사용하세요.', en: 'Use Google Authenticator, Authy, 1Password, or any TOTP-compatible app.', ja: 'Google Authenticator、Authy、1Password など TOTP 対応アプリを使用してください。', th: 'ใช้ Google Authenticator, Authy, 1Password หรือแอปที่รองรับ TOTP', vi: 'Dùng Google Authenticator, Authy, 1Password, hoặc bất kỳ ứng dụng TOTP nào.', id: 'Gunakan Google Authenticator, Authy, 1Password, atau aplikasi apa pun yang mendukung TOTP.' })}
    >
      {!setup ? (
        <button onClick={startSetup} disabled={loading} style={loading ? buttonDisabledStyle : buttonStyle}>
          {loading ? tr(language, { ko: '생성 중…', en: 'Generating…', ja: '生成中…', th: 'กำลังสร้าง…', vi: 'Đang tạo…', id: 'Membuat…' }) : tr(language, { ko: '설정 시작', en: 'Start setup', ja: 'セットアップを開始', th: 'เริ่มตั้งค่า', vi: 'Bắt đầu thiết lập', id: 'Mulai penyiapan' })}
        </button>
      ) : (
        <form onSubmit={verifyAndEnable}>
          <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-muted, #6b7280)' }}>
            {tr(language, { ko: '인증 앱에 이 계정을 추가하세요. 아래 URL의 QR 코드를 스캔하거나 시크릿을 직접 붙여넣으세요.', en: 'Add this account to your authenticator. Either scan a QR code from the URL below, or paste the secret directly.', ja: '認証アプリにこのアカウントを追加してください。下記URLのQRコードをスキャンするか、シークレットを直接貼り付けます。', th: 'เพิ่มบัญชีนี้ในแอปยืนยันตัวตน สแกน QR จาก URL ด้านล่าง หรือวางซีเคร็ตโดยตรง', vi: 'Thêm tài khoản này vào ứng dụng xác thực. Quét mã QR từ URL bên dưới, hoặc dán secret trực tiếp.', id: 'Tambahkan akun ini ke autentikator Anda. Pindai kode QR dari URL di bawah, atau tempel secret-nya langsung.' })}
          </div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 12,
            background: '#f1f5f9',
            color: '#0f172a',
            padding: 10,
            borderRadius: 6,
            marginBottom: 12,
            wordBreak: 'break-all',
          }}>{setup.otpauth_url}</div>
          <div style={{ marginBottom: 12, fontSize: 13 }}>
            <strong>{tr(language, { ko: '시크릿:', en: 'Secret:', ja: 'シークレット:', th: 'ซีเคร็ต:', vi: 'Secret:', id: 'Secret:' })}</strong>{' '}
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
            {loading ? tr(language, { ko: '확인 중…', en: 'Verifying…', ja: '確認中…', th: 'กำลังยืนยัน…', vi: 'Đang xác minh…', id: 'Memverifikasi…' }) : tr(language, { ko: '확인 및 활성화', en: 'Verify & enable', ja: '確認して有効化', th: 'ยืนยันและเปิดใช้งาน', vi: 'Xác minh & bật', id: 'Verifikasi & aktifkan' })}
          </button>
        </form>
      )}
    </AuthShell>
  )
}


// ═══ GoogleCallbackPage ═══════════════════════════════════════════════════

export function GoogleCallbackPage({ onLogin }: { onLogin: (token: string) => void }) {
  const navigate = useNavigate()
  const { language } = useLanguage()
  const [params] = useSearchParams()
  const [error, setError] = useState('')

  useEffect(() => {
    const code = params.get('code')
    const state = params.get('state')
    if (!code || !state) {
      setError(tr(language, { ko: 'OAuth 응답 매개변수가 없습니다', en: 'Missing OAuth response parameters', ja: 'OAuth応答パラメーターがありません', th: 'ไม่มีพารามิเตอร์การตอบกลับ OAuth', vi: 'Thiếu tham số phản hồi OAuth', id: 'Parameter respons OAuth tidak lengkap' }))
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
      .catch(d => setError(errMessage(d, tr(language, { ko: 'Google 로그인에 실패했습니다', en: 'Google sign-in failed', ja: 'Googleログインに失敗しました', th: 'เข้าสู่ระบบด้วย Google ไม่สำเร็จ', vi: 'Đăng nhập Google thất bại', id: 'Gagal masuk dengan Google' }))))
  }, [params, onLogin, navigate, language])

  return (
    <AuthShell title={tr(language, { ko: 'Google 로그인 마무리 중…', en: 'Finishing Google sign-in…', ja: 'Googleログインを完了しています…', th: 'กำลังทำการเข้าสู่ระบบด้วย Google…', vi: 'Đang hoàn tất đăng nhập Google…', id: 'Menyelesaikan proses masuk dengan Google…' })} subtitle={tr(language, { ko: '잠시만요.', en: 'One moment.', ja: '少々お待ちください。', th: 'สักครู่', vi: 'Chờ một chút.', id: 'Mohon tunggu sebentar.' })}>
      {error
        ? <div style={{ color: '#dc2626', fontSize: 14 }}>{error}</div>
        : <div style={{ color: 'var(--text-muted, #6b7280)' }}>{tr(language, { ko: 'Google로 확인 중…', en: 'Verifying with Google…', ja: 'Googleで確認中…', th: 'กำลังยืนยันกับ Google…', vi: 'Đang xác minh với Google…', id: 'Memverifikasi dengan Google…' })}</div>}
    </AuthShell>
  )
}


// ═══ Export the token clearer for sign-out elsewhere ═════════════════════

export function signOutUser() {
  clearUserToken()
}
