import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Membership gate — Sooppiy is subscription-only. A signed-in user without an
// active subscription lands here (App.tsx gate). Four tiers: junior $60 /
// pro $250 / professional $500 per month, enterprise via the contract page.
// Payment: PayPal (redirect flow, instant) or bank transfer (admin approval).
const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 14, padding: '22px 20px' }
const primaryBtn: any = { padding: '10px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 14, width: '100%' }
const ghostBtn: any = { ...primaryBtn, background: 'transparent', border: '1px solid var(--border-color,#2a2a28)', color: 'inherit' }
const inputStyle: any = { padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-primary,#0e0e0d)', color: 'var(--text-primary,#fff)', fontSize: 14, width: '100%' }

export function SubscribePage({ userToken, onSignOut }: { userToken: string | null, onSignOut?: () => void }) {
  const { language } = useLanguage()
  const [params] = useSearchParams()
  const [plans, setPlans] = useState<any[]>([])
  const [paypalAvailable, setPaypalAvailable] = useState(false)
  const [bankInfo, setBankInfo] = useState('')
  const [mine, setMine] = useState<any | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const T = {
    title: tr(language, { ko: '멤버십 구독', en: 'Choose your membership' }),
    subtitle: tr(language, { ko: 'Sooppiy는 구독 회원 전용 서비스입니다. 플랜을 선택하면 모든 기능이 열립니다.', en: 'Sooppiy is a members-only platform. Pick a plan to unlock everything.' }),
    perMonth: tr(language, { ko: '/월', en: '/month' }),
    select: tr(language, { ko: '선택', en: 'Select' }),
    selectedLabel: tr(language, { ko: '선택됨', en: 'Selected' }),
    payPaypal: tr(language, { ko: 'PayPal로 결제', en: 'Pay with PayPal' }),
    payBank: tr(language, { ko: '계좌이체로 신청', en: 'Pay by bank transfer' }),
    bankRef: tr(language, { ko: '이체 참조번호 (보낸 분 성함 등)', en: 'Transfer reference (sender name, memo…)' }),
    bankSubmit: tr(language, { ko: '이체 완료 — 승인 요청', en: 'I transferred — request approval' }),
    contactUs: tr(language, { ko: '문의하기', en: 'Contact us' }),
    enterpriseDesc: tr(language, { ko: '맞춤 계약 · 전담 지원', en: 'Custom contract · dedicated support' }),
    pendingTitle: tr(language, { ko: '승인 대기 중', en: 'Awaiting approval' }),
    pendingBody: tr(language, { ko: '이체 확인 후 관리자가 구독을 활성화합니다. 잠시 후 다시 확인해 주세요.', en: 'An administrator will activate your subscription once the transfer is confirmed. Check back soon.' }),
    activeTitle: tr(language, { ko: '구독 활성화됨', en: 'Subscription active' }),
    activeBody: tr(language, { ko: '모든 기능을 사용할 수 있습니다.', en: 'You have full access.' }),
    expires: tr(language, { ko: '만료일', en: 'Expires' }),
    goApp: tr(language, { ko: '앱으로 이동', en: 'Go to the app' }),
    signOut: tr(language, { ko: '로그아웃', en: 'Sign out' }),
    paypalDone: tr(language, { ko: '결제가 완료되었습니다! 구독이 활성화되었습니다.', en: 'Payment complete! Your subscription is active.' }),
    paypalCancel: tr(language, { ko: 'PayPal 결제가 취소되었습니다.', en: 'PayPal payment was cancelled.' }),
    paypalWorking: tr(language, { ko: 'PayPal 결제를 확인하는 중…', en: 'Confirming your PayPal payment…' }),
  }

  const authHdr: Record<string, string> = userToken ? { 'Authorization': `Bearer ${userToken}` } : {}

  async function loadState() {
    try {
      const p = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
      setPlans(p.plans || [])
      setPaypalAvailable(!!p.paypal_available)
      setBankInfo(p.bank_transfer_info || '')
      if (userToken) {
        const m = await fetch(`${API_BASE}/subscriptions/me`, { headers: authHdr }).then(r => r.ok ? r.json() : null)
        setMine(m)
      }
    } catch { /* network */ }
  }

  useEffect(() => { loadState() }, [userToken])

  // PayPal redirect return: ?paypal=return&token=<ORDER_ID> → capture.
  useEffect(() => {
    const mode = params.get('paypal')
    const orderId = params.get('token')
    if (mode === 'cancel') { setError(T.paypalCancel); return }
    if (mode !== 'return' || !orderId || !userToken) return
    setBusy(true); setNotice(T.paypalWorking)
    fetch(`${API_BASE}/subscriptions/paypal/capture`, {
      method: 'POST',
      headers: { ...authHdr, 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: orderId }),
    }).then(async r => {
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      setNotice(T.paypalDone)
      // Full reload so App refetches /users/me and lifts the gate.
      setTimeout(() => { window.location.href = '/' }, 1200)
    }).catch(e => { setError(String(e?.message || e)); setBusy(false); setNotice('') })
  }, [params, userToken])

  async function startPaypal(planCode: string) {
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/paypal/create-order`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      const body = await r.json()
      window.location.href = body.approve_url
    } catch (e: any) {
      setError(String(e?.message || e)); setBusy(false)
    }
  }

  async function submitBank(planCode: string) {
    if (!reference.trim()) return
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/bank-transfer`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode, reference }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      await loadState()
    } catch (e: any) { setError(String(e?.message || e)) }
    setBusy(false)
  }

  const status = mine?.status || 'none'

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '48px 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, margin: 0 }}>💎 {T.title}</h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary,#8a8073)', marginTop: 8 }}>{T.subtitle}</p>
      </div>

      {notice && <div style={{ ...card, borderColor: '#22c55e', color: '#22c55e', marginBottom: 16, textAlign: 'center' }}>{notice}</div>}
      {error && <div style={{ ...card, borderColor: '#7f1d1d', color: '#ef4444', marginBottom: 16, textAlign: 'center' }}>⚠️ {error}</div>}

      {status === 'active' && (
        <div style={{ ...card, textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#22c55e' }}>✓ {T.activeTitle}</div>
          <div style={{ fontSize: 14, marginTop: 6 }}>{T.activeBody}</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted,#8a8073)', marginTop: 6 }}>
            {mine?.subscription?.plan_code} · {T.expires}: {String(mine?.subscription?.expires_at || '').slice(0, 10)}
          </div>
          <div style={{ marginTop: 14 }}>
            <Link to="/"><button style={{ ...primaryBtn, width: 'auto' }}>{T.goApp}</button></Link>
          </div>
        </div>
      )}

      {status === 'pending' && (
        <div style={{ ...card, textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#eab308' }}>⏳ {T.pendingTitle}</div>
          <div style={{ fontSize: 14, marginTop: 6 }}>{T.pendingBody}</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted,#8a8073)', marginTop: 6 }}>
            {mine?.subscription?.plan_code} · {mine?.subscription?.method}
          </div>
        </div>
      )}

      {status !== 'active' && status !== 'pending' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 14 }}>
          {plans.map(p => (
            <div key={p.code} style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10, borderColor: selected === p.code ? 'var(--accent-primary,#c26a45)' : undefined }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{p.name}</div>
              {p.contact_only ? (
                <>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>—</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', flex: 1 }}>{T.enterpriseDesc}</div>
                  <Link to="/contract" style={{ textDecoration: 'none' }}><button style={ghostBtn}>{T.contactUs}</button></Link>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>${Number(p.price_usd).toLocaleString()}<span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted,#8a8073)' }}>{T.perMonth}</span></div>
                  <div style={{ flex: 1 }} />
                  <button style={selected === p.code ? primaryBtn : ghostBtn} disabled={busy}
                    onClick={() => { setSelected(p.code); setError('') }}>
                    {selected === p.code ? `✓ ${T.selectedLabel}` : T.select}
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {status !== 'active' && status !== 'pending' && selected && (
        <div style={{ ...card, marginTop: 20, maxWidth: 520, marginLeft: 'auto', marginRight: 'auto' }}>
          {paypalAvailable && (
            <button style={{ ...primaryBtn, marginBottom: 14 }} disabled={busy}
              onClick={() => startPaypal(selected)}>🅿️ {T.payPaypal}</button>
          )}
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{T.payBank}</div>
          {bankInfo && <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', background: 'var(--bg-primary,#0e0e0d)', borderRadius: 8, padding: 10, border: '1px solid var(--border-color,#2a2a28)' }}>{bankInfo}</pre>}
          <input placeholder={T.bankRef} value={reference} onChange={e => setReference(e.target.value)}
            style={{ ...inputStyle, margin: '8px 0 10px' }} />
          <button style={ghostBtn} disabled={busy || !reference.trim()}
            onClick={() => submitBank(selected)}>{T.bankSubmit}</button>
        </div>
      )}

      {onSignOut && (
        <div style={{ textAlign: 'center', marginTop: 28 }}>
          <button onClick={onSignOut} style={{ background: 'none', border: 'none', color: 'var(--text-muted,#8a8073)', cursor: 'pointer', fontSize: 13, textDecoration: 'underline' }}>{T.signOut}</button>
        </div>
      )}
    </div>
  )
}

export default SubscribePage
