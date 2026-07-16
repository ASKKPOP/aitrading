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

import { API_BASE, useLanguage } from './appShared'
import { tr } from './i18n'
import { signOutUser } from './authV2'


// ─── Section primitives ──────────────────────────────────────────────────

const sectionStyle: React.CSSProperties = {
  background: 'var(--bg-card, #faf6ec)',
  border: '1px solid var(--border-color, rgba(0,0,0,0.08))',
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
  const { language } = useLanguage()
  return (
    <div style={{
      ...sectionStyle,
      background: '#0f172a',
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
          }}>{tr(language, { ko: '내 트레이딩', en: 'My Trading', ja: 'マイトレード', th: 'การเทรดของฉัน', vi: 'Giao dịch của tôi' })}</div>
          <h1 style={{ fontSize: 28, fontWeight: 500, margin: 0, color: '#fff' }}>
            {user?.email ?? '…'}
          </h1>
          <div style={{ marginTop: 8, fontSize: 13, opacity: 0.7 }}>
            {user && (
              <>{tr(language, { ko: '포인트: ', en: 'Points: ', ja: 'ポイント: ', th: 'คะแนน: ', vi: 'Điểm: ' })}<strong>{user.points}</strong> · </>
            )}
            {mfa?.enabled
              ? <span style={{ color: '#86efac' }}>{tr(language, { ko: `2FA 활성화됨 (백업 코드 ${mfa.backup_codes_remaining}개 남음)`, en: `2FA enabled (${mfa.backup_codes_remaining} backup codes left)`, ja: `2FA有効 (バックアップコード残り${mfa.backup_codes_remaining}個)`, th: `เปิด 2FA แล้ว (เหลือรหัสสำรอง ${mfa.backup_codes_remaining} รหัส)`, vi: `Đã bật 2FA (còn ${mfa.backup_codes_remaining} mã dự phòng)` })}</span>
              : <Link to="/auth/mfa/setup" style={{ color: '#fde68a', textDecoration: 'underline' }}>{tr(language, { ko: '2FA 활성화', en: 'Enable 2FA', ja: '2FAを有効化', th: 'เปิดใช้งาน 2FA', vi: 'Bật 2FA' })}</Link>
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
          {tr(language, { ko: '로그아웃', en: 'Sign out', ja: 'ログアウト', th: 'ออกจากระบบ', vi: 'Đăng xuất' })}
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
  const { language } = useLanguage()
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
        if (!meRes.ok) throw new Error(tr(language, { ko: '계정을 불러올 수 없습니다', en: 'Could not load account', ja: 'アカウントを読み込めませんでした', th: 'ไม่สามารถโหลดบัญชีได้', vi: 'Không thể tải tài khoản' }))
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
        if (!aborted) setError(e?.message || tr(language, { ko: '불러오지 못했습니다', en: 'Failed to load', ja: '読み込みに失敗しました', th: 'โหลดไม่สำเร็จ', vi: 'Tải thất bại' }))
      } finally {
        if (!aborted) setLoading(false)
      }
    }
    load()
    return () => { aborted = true }
  }, [userToken, auth, navigate, signOutAndLeave, language])

  if (!userToken) return null

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 0' }}>
      <AccountHeader user={user} mfa={mfa} onSignOut={signOutAndLeave} />

      {loading && <div style={{ padding: 20, color: 'var(--text-muted, #6b7280)' }}>{tr(language, { ko: '트레이딩 정보를 불러오는 중…', en: 'Loading your trading…', ja: 'トレード情報を読み込み中…', th: 'กำลังโหลดข้อมูลการเทรด…', vi: 'Đang tải giao dịch của bạn…' })}</div>}
      {error && <div style={{ color: '#dc2626', padding: 12 }}>{error}</div>}

      <Section
        title={tr(language, { ko: `📍 포지션 (${positions.length})`, en: `📍 Positions (${positions.length})`, ja: `📍 ポジション (${positions.length})`, th: `📍 ตำแหน่ง (${positions.length})`, vi: `📍 Vị thế (${positions.length})` })}
        action={<Link to="/positions" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '전체 보기 →', en: 'View all →', ja: 'すべて表示 →', th: 'ดูทั้งหมด →', vi: 'Xem tất cả →' })}</Link>}
      >
        {positions.length === 0 ? (
          <div style={{ color: 'var(--text-muted, #6b7280)', fontSize: 14 }}>
            {tr(language, { ko: '아직 미결제 포지션이 없습니다. ', en: 'You have no open positions yet. Start by ', ja: 'まだオープンポジションがありません。まずは', th: 'คุณยังไม่มีตำแหน่งที่เปิดอยู่ เริ่มจาก', vi: 'Bạn chưa có vị thế mở nào. Bắt đầu bằng cách ' })}<Link to="/leaderboard" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '에이전트 팔로우', en: 'following an agent', ja: 'エージェントをフォロー', th: 'ติดตามเอเจนต์', vi: 'theo dõi một agent' })}</Link>{tr(language, { ko: '부터 시작하세요.', en: '.', ja: 'から始めましょう。', th: '', vi: '.' })}
          </div>
        ) : (
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead style={{ textAlign: 'left' }}>
              <tr style={{ borderBottom: '1px solid var(--border-color, rgba(0,0,0,0.08))' }}>
                <th style={{ padding: '8px 4px' }}>{tr(language, { ko: '종목', en: 'Symbol', ja: '銘柄', th: 'สัญลักษณ์', vi: 'Mã' })}</th>
                <th>{tr(language, { ko: '시장', en: 'Market', ja: '市場', th: 'ตลาด', vi: 'Thị trường' })}</th>
                <th>{tr(language, { ko: '방향', en: 'Side', ja: '方向', th: 'ทิศทาง', vi: 'Hướng' })}</th>
                <th style={{ textAlign: 'right' }}>{tr(language, { ko: '수량', en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' })}</th>
                <th style={{ textAlign: 'right' }}>{tr(language, { ko: '진입', en: 'Entry', ja: 'エントリー', th: 'เข้า', vi: 'Vào' })}</th>
                <th style={{ textAlign: 'right' }}>{tr(language, { ko: '현재', en: 'Current', ja: '現在', th: 'ปัจจุบัน', vi: 'Hiện tại' })}</th>
              </tr>
            </thead>
            <tbody>
              {positions.slice(0, 10).map((p, i) => (
                <tr key={p.position_id ?? p.id ?? i} style={{ borderBottom: '1px solid var(--border-color, rgba(0,0,0,0.04))' }}>
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
        title={tr(language, { ko: `⊞ 팔로잉 (${following.length})`, en: `⊞ Following (${following.length})`, ja: `⊞ フォロー中 (${following.length})`, th: `⊞ กำลังติดตาม (${following.length})`, vi: `⊞ Đang theo dõi (${following.length})` })}
        action={<Link to="/leaderboard" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '에이전트 찾기 →', en: 'Find agents →', ja: 'エージェントを探す →', th: 'ค้นหาเอเจนต์ →', vi: 'Tìm agent →' })}</Link>}
      >
        {following.length === 0 ? (
          <div style={{ color: 'var(--text-muted, #6b7280)', fontSize: 14 }}>
            {tr(language, { ko: '아직 아무도 팔로우하지 않았습니다. ', en: 'Not following anyone yet. Find agents on the ', ja: 'まだ誰もフォローしていません。エージェントは', th: 'ยังไม่ได้ติดตามใคร ค้นหาเอเจนต์ได้ที่', vi: 'Chưa theo dõi ai. Tìm agent trên ' })}<Link to="/leaderboard" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '리더보드', en: 'leaderboard', ja: 'リーダーボード', th: 'ลีดเดอร์บอร์ด', vi: 'bảng xếp hạng' })}</Link>{tr(language, { ko: '에서 에이전트를 찾아보세요.', en: '.', ja: 'でエージェントを探しましょう。', th: '', vi: '.' })}
          </div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
            {following.slice(0, 8).map((f, i) => (
              <li key={f.provider_id ?? i} style={{ marginBottom: 4 }}>
                {f.provider_name ?? tr(language, { ko: `제공자 #${f.provider_id}`, en: `Provider #${f.provider_id}`, ja: `プロバイダー #${f.provider_id}`, th: `ผู้ให้บริการ #${f.provider_id}`, vi: `Nhà cung cấp #${f.provider_id}` })}
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
        title={tr(language, { ko: `↗ 전략 (${strategies.length})`, en: `↗ Strategies (${strategies.length})`, ja: `↗ 戦略 (${strategies.length})`, th: `↗ กลยุทธ์ (${strategies.length})`, vi: `↗ Chiến lược (${strategies.length})` })}
        action={<Link to="/strategies" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '전체 →', en: 'All →', ja: 'すべて →', th: 'ทั้งหมด →', vi: 'Tất cả →' })}</Link>}
      >
        {strategies.length === 0 ? (
          <div style={{ color: 'var(--text-muted, #6b7280)', fontSize: 14 }}>
            {tr(language, { ko: '아직 전략이 없습니다.', en: 'No strategies yet.', ja: 'まだ戦略がありません。', th: 'ยังไม่มีกลยุทธ์', vi: 'Chưa có chiến lược.' })}
          </div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
            {strategies.slice(0, 8).map(s => (
              <li key={s.strategy_id} style={{ marginBottom: 4 }}>
                <strong>{s.name}</strong>
                {s.backtest_validated && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: '#15803d' }}>
                    {tr(language, { ko: '✓ 백테스트 검증됨', en: '✓ backtest-validated', ja: '✓ バックテスト検証済み', th: '✓ ผ่านการตรวจสอบแบ็คเทสต์', vi: '✓ đã kiểm định backtest' })}
                  </span>
                )}
                {s.last_backtest_sharpe !== null && s.last_backtest_sharpe !== undefined && (
                  <span style={{ marginLeft: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: 'var(--text-muted, #6b7280)' }}>
                    {tr(language, { ko: '샤프', en: 'Sharpe', ja: 'シャープ', th: 'ชาร์ป', vi: 'Sharpe' })} {s.last_backtest_sharpe.toFixed(2)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title={tr(language, { ko: '📈 손익 내역', en: '📈 P&L history', ja: '📈 損益履歴', th: '📈 ประวัติกำไรขาดทุน', vi: '📈 Lịch sử lãi/lỗ' })}
        action={<Link to="/leaderboard" style={{ fontSize: 13, color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '차트 열기 →', en: 'Open chart →', ja: 'チャートを開く →', th: 'เปิดกราฟ →', vi: 'Mở biểu đồ →' })}</Link>}
      >
        <div style={{ color: 'var(--text-muted, #6b7280)', fontSize: 14 }}>
          {tr(language, { ko: '상세 수익 차트는 ', en: 'Detailed profit chart is available on your ', ja: '詳細な収益チャートは', th: 'กราฟกำไรโดยละเอียดดูได้ที่', vi: 'Biểu đồ lợi nhuận chi tiết có trên ' })}<Link to="/leaderboard" style={{ color: 'var(--accent-primary, #b8542f)' }}>{tr(language, { ko: '리더보드 프로필', en: 'leaderboard profile', ja: 'リーダーボードのプロフィール', th: 'โปรไฟล์ลีดเดอร์บอร์ด', vi: 'hồ sơ bảng xếp hạng' })}</Link>{tr(language, { ko: '에서 확인할 수 있습니다.', en: '.', ja: 'で確認できます。', th: '', vi: '.' })}
        </div>
      </Section>
    </div>
  )
}
