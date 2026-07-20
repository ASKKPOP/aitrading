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
  const [usdt, setUsdt] = useState<{ available: boolean; address: string; network: string }>(
    { available: false, address: '', network: 'TRC20' })
  const [txHash, setTxHash] = useState('')
  const [copied, setCopied] = useState(false)
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
    // ── USDT (the default rail) ──
    payUsdt: tr(language, { ko: 'USDT로 결제', en: 'Pay with USDT', ja: 'USDT で支払う',
      th: 'ชำระด้วย USDT', vi: 'Thanh toán bằng USDT' }),
    usdtNetwork: tr(language, { ko: '네트워크', en: 'Network', ja: 'ネットワーク',
      th: 'เครือข่าย', vi: 'Mạng lưới' }),
    usdtAddress: tr(language, { ko: '입금 주소', en: 'Deposit address', ja: '入金アドレス',
      th: 'ที่อยู่สำหรับโอน', vi: 'Địa chỉ nhận' }),
    usdtCopy: tr(language, { ko: '복사', en: 'Copy', ja: 'コピー', th: 'คัดลอก', vi: 'Sao chép' }),
    usdtCopied: tr(language, { ko: '복사됨', en: 'Copied', ja: 'コピーしました',
      th: 'คัดลอกแล้ว', vi: 'Đã sao chép' }),
    usdtHash: tr(language, { ko: '트랜잭션 해시 (TxID)', en: 'Transaction hash (TxID)',
      th: 'แฮชธุรกรรม (TxID)', ja: 'トランザクションハッシュ (TxID)', vi: 'Mã giao dịch (TxID)' }),
    usdtSubmit: tr(language, { ko: '송금 완료 — 승인 요청', en: 'I sent it — request approval',
      ja: '送金しました — 承認をリクエスト', th: 'โอนแล้ว — ขออนุมัติ',
      vi: 'Đã chuyển — yêu cầu duyệt' }),
    usdtWarn: tr(language, {
      ko: '반드시 위에 표시된 네트워크로만 보내세요. 다른 네트워크로 보내면 자금을 복구할 수 없습니다. 입금 확인 후 관리자가 구독을 활성화합니다.',
      en: 'Send only on the network shown above. Funds sent on a different network cannot be recovered. An administrator activates your subscription once the transfer is confirmed on-chain.',
      ja: '必ず上記のネットワークで送金してください。異なるネットワークに送金した資金は復元できません。入金確認後に管理者が有効化します。',
      th: 'โอนผ่านเครือข่ายที่แสดงด้านบนเท่านั้น เงินที่ส่งผิดเครือข่ายจะกู้คืนไม่ได้ ผู้ดูแลจะเปิดใช้งานหลังยืนยันบนเชน',
      vi: 'Chỉ chuyển trên mạng lưới hiển thị ở trên. Tiền gửi sai mạng lưới không thể khôi phục. Quản trị viên sẽ kích hoạt sau khi xác nhận trên chuỗi.' }),
    usdtAmount: tr(language, { ko: '보낼 금액', en: 'Amount to send', ja: '送金額',
      th: 'จำนวนที่ต้องโอน', vi: 'Số tiền cần chuyển' }),
    orOther: tr(language, { ko: '또는 다른 방법', en: 'Or another method', ja: 'または他の方法',
      th: 'หรือวิธีอื่น', vi: 'Hoặc phương thức khác' }),
  }

  const authHdr: Record<string, string> = userToken ? { 'Authorization': `Bearer ${userToken}` } : {}

  async function loadState() {
    try {
      const p = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
      setPlans(p.plans || [])
      setPaypalAvailable(!!p.paypal_available)
      setBankInfo(p.bank_transfer_info || '')
      setUsdt({ available: !!p.usdt_available, address: p.usdt_address || '',
        network: p.usdt_network || 'TRC20' })
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

  async function submitUsdt(planCode: string) {
    if (!txHash.trim()) return
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/usdt`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode, tx_hash: txHash }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      setTxHash('')
      await loadState()
    } catch (e: any) { setError(String(e?.message || e)) }
    setBusy(false)
  }

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(usdt.address)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch { /* clipboard blocked — the address is selectable on screen anyway */ }
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
          {/* USDT is the default rail — first, and the only one with a
              highlighted action. PayPal renders only when explicitly
              re-enabled server-side (PAYPAL_UI_ENABLED). */}
          {usdt.available && (
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>₮ {T.payUsdt}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
                color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>
                <span>{T.usdtNetwork}</span>
                <strong style={{ color: 'var(--text-primary,#fff)' }}>{usdt.network}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
                color: 'var(--text-muted,#8a8073)', marginBottom: 8 }}>
                <span>{T.usdtAmount}</span>
                <strong style={{ color: 'var(--text-primary,#fff)' }}>
                  {Number(plans.find(p => p.code === selected)?.price_usd || 0).toLocaleString()} USDT
                </strong>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>
                {T.usdtAddress}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
                <code style={{ flex: 1, fontSize: 12, wordBreak: 'break-all', padding: '10px 12px',
                  borderRadius: 8, background: 'var(--bg-primary,#0e0e0d)',
                  border: '1px solid var(--border-color,#2a2a28)' }}>{usdt.address}</code>
                <button style={{ ...ghostBtn, width: 'auto', whiteSpace: 'nowrap' }}
                  onClick={copyAddress}>{copied ? `✓ ${T.usdtCopied}` : T.usdtCopy}</button>
              </div>
              <p style={{ fontSize: 11.5, lineHeight: 1.5, color: '#eab308', margin: '10px 0 0' }}>
                ⚠️ {T.usdtWarn}
              </p>
              <input placeholder={T.usdtHash} value={txHash} onChange={e => setTxHash(e.target.value)}
                style={{ ...inputStyle, margin: '10px 0' }} />
              <button style={primaryBtn} disabled={busy || !txHash.trim()}
                onClick={() => submitUsdt(selected)}>{T.usdtSubmit}</button>
            </div>
          )}

          {(paypalAvailable || usdt.available) && (
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em',
              color: 'var(--text-muted,#8a8073)', borderTop: '1px solid var(--border-color,#2a2a28)',
              paddingTop: 14, marginBottom: 10 }}>{T.orOther}</div>
          )}

          {paypalAvailable && (
            <button style={{ ...ghostBtn, marginBottom: 14 }} disabled={busy}
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
