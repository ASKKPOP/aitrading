import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Account-status pill for the top bar: subscription plan, whether trading
// money is simulated or real right now, and — when real — which gateways
// live orders can route to (crypto / US stock).
//
// Follows the AiUsagePill convention: the bar carries a compact summary and
// the detail lives in a panel behind a click.
//
// Data:
//   plan  — userInfo.subscription (already fetched by App via /api/users/me).
//   mode + gateways — GET /api/execution/status (agent token). mode is
//   server-derived from ENABLED automation rules, so connected credentials
//   alone never make the account read "live".

type Gateway = { broker: string; markets: string[]; execution_mode: string }
type Status = { mode: 'simulator' | 'shadow' | 'live'; gateways: Gateway[] }

const POLL_MS = 60000

// plan_code → display. Codes come from subscription_plans (junior/pro/
// professional); anything unknown is shown capitalized rather than hidden.
function planLabel(code: string | undefined | null): string {
  if (!code) return ''
  const known: Record<string, string> = {
    junior: 'Junior', pro: 'Pro', professional: 'Professional', enterprise: 'Enterprise',
  }
  return known[code] || code.charAt(0).toUpperCase() + code.slice(1)
}

function brokerLabel(broker: string): string {
  const known: Record<string, string> = {
    alpaca: 'Alpaca', binance: 'Binance', ibkr: 'IBKR', bybit: 'Bybit',
    okx: 'OKX', kraken: 'Kraken', cryptocom: 'Crypto.com', upbit: 'Upbit',
    kucoin: 'KuCoin', coinbase: 'Coinbase',
  }
  return known[broker] || broker
}

export function AccountStatusPill({ agentToken, userToken, userInfo }: {
  agentToken?: string | null
  userToken?: string | null
  userInfo?: any
}) {
  const { language } = useLanguage()
  const location = useLocation()
  const [status, setStatus] = useState<Status | null>(null)
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    if (!agentToken) return
    try {
      const r = await fetch(`${API_BASE}/execution/status`, {
        headers: { Authorization: `Bearer ${agentToken}` },
      })
      if (r.ok) setStatus(await r.json())
    } catch { /* transient — keep the last good state on screen */ }
  }, [agentToken])

  // Refetch on route change too: connecting a gateway on /accounts should be
  // visible in the bar as soon as the user navigates away.
  useEffect(() => { load() }, [load, location.pathname])
  useEffect(() => {
    if (!agentToken) return
    const id = setInterval(load, POLL_MS)
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => { clearInterval(id); window.removeEventListener('focus', onFocus) }
  }, [load, agentToken])

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const T = {
    label: tr(language, { ko: '계정 상태', en: 'Account status', ja: 'アカウント状態',
      th: 'สถานะบัญชี', vi: 'Trạng thái tài khoản', id: 'Status akun' }),
    plan: tr(language, { ko: '구독 플랜', en: 'Subscription', ja: 'サブスクリプション',
      th: 'แผนสมาชิก', vi: 'Gói đăng ký', id: 'Langganan' }),
    noPlan: tr(language, { ko: '구독 없음', en: 'No subscription', ja: '未加入',
      th: 'ไม่มีแผน', vi: 'Chưa đăng ký', id: 'Tanpa langganan' }),
    expires: tr(language, { ko: '만료일', en: 'Renews / expires', ja: '有効期限',
      th: 'หมดอายุ', vi: 'Hết hạn', id: 'Berakhir' }),
    modeTitle: tr(language, { ko: '거래 모드', en: 'Trading mode', ja: '取引モード',
      th: 'โหมดการเทรด', vi: 'Chế độ giao dịch', id: 'Mode trading' }),
    simulator: tr(language, { ko: '시뮬레이터', en: 'Simulator', ja: 'シミュレーター',
      th: 'จำลอง', vi: 'Mô phỏng', id: 'Simulator' }),
    shadow: tr(language, { ko: '섀도우', en: 'Shadow', ja: 'シャドウ',
      th: 'แชโดว์', vi: 'Shadow', id: 'Shadow' }),
    live: tr(language, { ko: '실거래', en: 'Live', ja: '実取引',
      th: 'เทรดจริง', vi: 'Thật', id: 'Live' }),
    simDesc: tr(language, {
      ko: '모의 지갑 — 실제 자금이 사용되지 않습니다.',
      en: 'Paper trading — no real money is at risk.',
      ja: 'ペーパートレード — 実資金は使われません。',
      th: 'เทรดกระดาษ — ไม่มีเงินจริง',
      vi: 'Giao dịch giấy — không dùng tiền thật.',
      id: 'Paper trading — tanpa uang sungguhan.' }),
    shadowDesc: tr(language, {
      ko: '시뮬레이터가 기준이며, 같은 주문이 브로커 샌드박스에도 전송됩니다.',
      en: 'Simulator is authoritative; the same orders also go to the broker sandbox.',
      ja: 'シミュレーターが基準。同じ注文をサンドボックスにも送信します。',
      th: 'จำลองเป็นหลัก คำสั่งเดียวกันส่งไป sandbox ของโบรกเกอร์ด้วย',
      vi: 'Mô phỏng là chính; lệnh cũng gửi tới sandbox của broker.',
      id: 'Simulator jadi acuan; order yang sama juga dikirim ke sandbox broker.' }),
    liveDesc: tr(language, {
      ko: '실제 자금 — live 규칙의 주문이 연결된 게이트웨이로 전송됩니다.',
      en: 'Real money — orders from live rules route to the connected gateway.',
      ja: '実資金 — live ルールの注文は接続済みゲートウェイに送られます。',
      th: 'เงินจริง — คำสั่งจากกฎ live ส่งผ่านเกตเวย์ที่เชื่อมต่อ',
      vi: 'Tiền thật — lệnh từ quy tắc live đi qua cổng đã kết nối.',
      id: 'Uang sungguhan — order dari aturan live lewat gateway yang terhubung.' }),
    gateways: tr(language, { ko: '연결된 게이트웨이', en: 'Connected gateways', ja: '接続済みゲートウェイ',
      th: 'เกตเวย์ที่เชื่อมต่อ', vi: 'Cổng đã kết nối', id: 'Gateway terhubung' }),
    crypto: tr(language, { ko: '크립토', en: 'Crypto', ja: '暗号資産',
      th: 'คริปโต', vi: 'Crypto', id: 'Kripto' }),
    usStock: tr(language, { ko: '미국 주식', en: 'US stock', ja: '米国株',
      th: 'หุ้นสหรัฐ', vi: 'Cổ phiếu Mỹ', id: 'Saham AS' }),
    none: tr(language, { ko: '없음', en: 'none', ja: 'なし',
      th: 'ไม่มี', vi: 'không có', id: 'tidak ada' }),
    noGateway: tr(language, { ko: '게이트웨이 없음', en: 'no gateway', ja: 'ゲートウェイなし',
      th: 'ไม่มีเกตเวย์', vi: 'chưa có cổng', id: 'tanpa gateway' }),
    managePlan: tr(language, { ko: '플랜 관리', en: 'Manage plan', ja: 'プラン管理',
      th: 'จัดการแผน', vi: 'Quản lý gói', id: 'Kelola paket' }),
    manageAccounts: tr(language, { ko: '계좌 · 게이트웨이 관리', en: 'Manage accounts & gateways',
      ja: '口座・ゲートウェイ管理', th: 'จัดการบัญชีและเกตเวย์',
      vi: 'Quản lý tài khoản & cổng', id: 'Kelola akun & gateway' }),
  }

  // Nothing to summarize for a logged-out visitor.
  if (!agentToken && !userToken) return null

  const plan = userInfo?.subscription?.plan_code as string | undefined
  const mode = status?.mode
  const gateways = status?.gateways || []
  const cryptoGws = gateways.filter(g => g.markets.includes('crypto'))
  const stockGws = gateways.filter(g => g.markets.includes('us-stock'))

  const modeText = mode === 'live' ? T.live : mode === 'shadow' ? T.shadow : T.simulator
  const modeDot = mode === 'live' ? '●' : '◐'
  const modeColor = mode === 'live' ? 'var(--accent-primary, #c26a45)' : undefined

  // Bar summary: plan · mode, and when live also the gateway names — the
  // whole point of live is knowing where real orders go.
  const barParts: string[] = []
  if (plan) barParts.push(planLabel(plan))
  if (status) barParts.push(`${modeDot} ${modeText}`)
  if (mode === 'live') {
    barParts.push(gateways.length
      ? gateways.map(g => brokerLabel(g.broker)).join(' · ')
      : `⚠ ${T.noGateway}`)
  }
  if (!barParts.length) return null

  const gatewayRow = (label: string, list: Gateway[]) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12, padding: '2px 0' }}>
      <span style={{ color: 'var(--text-muted,#8a8073)' }}>{label}</span>
      <span style={{ fontWeight: 500, whiteSpace: 'nowrap' }}>
        {list.length ? list.map(g => brokerLabel(g.broker)).join(', ') : `— ${T.none}`}
      </span>
    </div>
  )

  return (
    <div ref={wrapRef} className="topnav-ai-pill">
      <button
        className="topnav-icon-btn"
        onClick={() => setOpen(v => !v)}
        title={T.label}
        aria-label={T.label}
        aria-expanded={open}
        style={{ width: 'auto', padding: '0 8px', gap: 6, fontSize: 12.5, whiteSpace: 'nowrap' }}
      >
        {plan && <span style={{ fontWeight: 700 }}>{planLabel(plan)}</span>}
        {status && (
          <span>
            <span aria-hidden style={{ color: modeColor }}>{modeDot}</span> {modeText}
          </span>
        )}
        {mode === 'live' && (
          <span style={{ color: gateways.length ? undefined : 'var(--accent-primary, #c26a45)' }}>
            {gateways.length
              ? gateways.map(g => brokerLabel(g.broker)).join(' · ')
              : `⚠ ${T.noGateway}`}
          </span>
        )}
      </button>

      {open && (
        <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', zIndex: 70,
          width: 280, background: 'var(--bg-card,#161615)', color: 'var(--text-primary,#fff)',
          border: '1px solid var(--border-color,#2a2a28)', borderRadius: 12,
          padding: 14, boxShadow: '0 12px 32px rgba(0,0,0,.32)' }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>{T.label}</div>

          {userToken && (
            <div style={{ marginTop: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.plan}</span>
                <span style={{ fontWeight: 700 }}>{plan ? planLabel(plan) : T.noPlan}</span>
              </div>
              {userInfo?.subscription?.expires_at && (
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12, padding: '2px 0' }}>
                  <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.expires}</span>
                  <span>{String(userInfo.subscription.expires_at).slice(0, 10)}</span>
                </div>
              )}
              <Link to="/subscribe" onClick={() => setOpen(false)}
                style={{ fontSize: 11.5, color: 'var(--accent-primary,#c26a45)' }}>
                {T.managePlan} →
              </Link>
            </div>
          )}

          {status && (
            <div style={{ marginTop: 12, borderTop: '1px solid var(--border-color,#2a2a28)', paddingTop: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.modeTitle}</span>
                <span style={{ fontWeight: 700 }}>
                  <span aria-hidden style={{ color: modeColor }}>{modeDot}</span> {modeText}
                </span>
              </div>
              <p style={{ fontSize: 11, lineHeight: 1.5, color: 'var(--text-muted,#8a8073)', margin: '4px 0 0' }}>
                {mode === 'live' ? T.liveDesc : mode === 'shadow' ? T.shadowDesc : T.simDesc}
              </p>

              <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.06em',
                color: 'var(--text-muted,#8a8073)', margin: '10px 0 4px' }}>{T.gateways}</div>
              {gatewayRow(T.crypto, cryptoGws)}
              {gatewayRow(T.usStock, stockGws)}
              <Link to="/accounts" onClick={() => setOpen(false)}
                style={{ fontSize: 11.5, color: 'var(--accent-primary,#c26a45)' }}>
                {T.manageAccounts} →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default AccountStatusPill
