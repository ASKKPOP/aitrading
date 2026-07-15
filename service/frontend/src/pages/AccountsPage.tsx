import { useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Accounts — the two account types:
//   1. Simulator (simulated wallet, paper trading)  — active
//   2. Real (connect Coinbase / Bybit / Binance)     — setup UI, live execution intentionally gated
export function AccountsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [me, setMe] = useState<any>(null)
  const [accountType, setAccountType] = useState<string>(localStorage.getItem('account_type') || 'simulator')
  const [exchange, setExchange] = useState('binance')
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!token) return
    fetch(`${API_BASE}/claw/agents/me`, { headers: { 'Authorization': `Bearer ${token}` } })
      .then(r => r.json()).then(setMe).catch(() => {})
  }, [token])

  const T = {
    title: tr(language, { ko: '계정', en: 'Accounts', ja: 'アカウント', th: 'บัญชี', vi: 'Tài khoản' }),
    subtitle: tr(language, { ko: '거래 실행 방식을 선택하세요', en: 'Choose how trades are executed', ja: '取引の実行方法を選択', th: 'เลือกวิธีดำเนินการเทรด', vi: 'Chọn cách thực hiện giao dịch' }),
    simTitle: tr(language, { ko: '시뮬레이터 계정', en: 'Simulator account', ja: 'シミュレーター口座', th: 'บัญชีจำลอง', vi: 'Tài khoản mô phỏng' }),
    simDesc: tr(language, { ko: '모의 지갑입니다. 매수와 매도는 실시간 시장 가격에 대해 모의 거래됩니다 — 실제 자금은 사용되지 않습니다.', en: 'Simulated wallet. Buys and sells are paper-traded against live market prices — no real money.', ja: '模擬ウォレット。実際の資金は動きません。', th: 'กระเป๋าจำลอง ซื้อขายแบบกระดาษกับราคาตลาดจริง — ไม่มีเงินจริง', vi: 'Ví mô phỏng. Không có tiền thật.' }),
    balance: tr(language, { ko: '모의 잔고', en: 'Simulated balance', ja: '模擬残高', th: 'ยอดจำลอง', vi: 'Số dư mô phỏng' }),
    active: tr(language, { ko: '활성', en: 'Active', ja: '有効', th: 'ใช้งาน', vi: 'Đang dùng' }),
    use: tr(language, { ko: '이 계정 사용', en: 'Use this account', ja: 'この口座を使う', th: 'ใช้บัญชีนี้', vi: 'Dùng tài khoản này' }),
    realTitle: tr(language, { ko: '실계좌', en: 'Real account', ja: '実口座', th: 'บัญชีจริง', vi: 'Tài khoản thật' }),
    realDesc: tr(language, { ko: '실제 자금으로 거래하려면 라이브 거래소를 연결하세요.', en: 'Connect a live exchange to trade with real funds.', ja: '実際の資金で取引するために取引所を接続します。', th: 'เชื่อมต่อกระดานเทรดเพื่อเทรดด้วยเงินจริง', vi: 'Kết nối sàn giao dịch thật.' }),
    exchange: tr(language, { ko: '교환', en: 'Exchange', ja: '取引所', th: 'กระดานเทรด', vi: 'Sàn' }),
    apiKey: tr(language, { ko: 'API 키', en: 'API key', ja: 'APIキー', th: 'คีย์ API', vi: 'Khóa API' }),
    apiSecret: tr(language, { ko: 'API 시크릿', en: 'API secret', ja: 'APIシークレット', th: 'ความลับ API', vi: 'Bí mật API' }),
    connect: tr(language, { ko: '거래소 연결', en: 'Connect exchange', ja: '取引所を接続', th: 'เชื่อมต่อ', vi: 'Kết nối' }),
    warn: tr(language, { ko: '실거래는 실제 자금을 위험에 노출시킵니다. 반드시 거래(TRADE) 권한으로 한정된 API 키만 사용하세요 — 출금 권한은 절대 안 됩니다. 소액으로 시작하세요.', en: 'Real trading risks real money. Only ever use API keys scoped to TRADE — never withdrawal. Start small.', ja: '実取引は実際の資金を失う恐れがあります。', th: 'การเทรดจริงมีความเสี่ยงต่อเงินจริง ใช้คีย์ที่จำกัดสิทธิ์เฉพาะการเทรดเท่านั้น', vi: 'Giao dịch thật có rủi ro mất tiền thật.' }),
    gated: tr(language, { ko: '설정이 저장되었습니다. 이 빌드에서는 라이브 주문 실행이 의도적으로 비활성화되어 있습니다 — 안전한 서버 측 키 저장과 명시적인 라이브 전환 단계가 필요합니다.', en: 'Setup saved. Live order execution is intentionally disabled in this build — it requires secure server-side key storage and an explicit go-live step.', ja: '発注実行は本ビルドでは無効です。', th: 'บันทึกการตั้งค่าแล้ว การส่งคำสั่งจริงถูกปิดไว้ในเวอร์ชันนี้', vi: 'Đã lưu. Thực thi lệnh thật đang tắt trong bản này.' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
  }

  function chooseSimulator() { localStorage.setItem('account_type', 'simulator'); setAccountType('simulator') }
  function connect() {
    // NOTE: does NOT store the secret and does NOT enable live trading — gated by design.
    localStorage.setItem('account_type', 'real')
    localStorage.setItem('real_exchange', exchange)
    setAccountType('real'); setConnected(true)
  }

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">◱</div><div className="empty-title">{T.login}</div></div></div>
  }

  const card = (active: boolean): any => ({
    flex: '1 1 320px', border: '2px solid ' + (active ? 'var(--accent-primary,#c26a45)' : 'var(--border,#d3c8b6)'),
    borderRadius: 14, padding: 22, background: 'var(--bg-card,#fffdf9)',
  })
  const badge = (bg: string): any => ({ display: 'inline-block', fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 6, background: bg, color: '#fff' })

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
        {/* Simulator */}
        <div style={card(accountType === 'simulator')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 20 }}>◐</span>
            <h2 style={{ margin: 0, fontSize: 18 }}>{T.simTitle}</h2>
            {accountType === 'simulator' && <span style={{ ...badge('#3fb950'), marginLeft: 'auto' }}>{T.active}</span>}
          </div>
          <p style={{ color: 'var(--text-secondary,#5f574c)', fontSize: 14 }}>{T.simDesc}</p>
          <div style={{ margin: '14px 0', fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>
            {T.balance}: <b style={{ fontSize: 18, color: 'inherit' }}>${(me?.cash ?? 100000).toLocaleString()}</b>
          </div>
          {accountType !== 'simulator' && (
            <button onClick={chooseSimulator} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>{T.use}</button>
          )}
        </div>

        {/* Real */}
        <div style={card(accountType === 'real')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 20 }}>●</span>
            <h2 style={{ margin: 0, fontSize: 18 }}>{T.realTitle}</h2>
            {accountType === 'real' && <span style={{ ...badge('#c26a45'), marginLeft: 'auto' }}>{T.active}</span>}
          </div>
          <p style={{ color: 'var(--text-secondary,#5f574c)', fontSize: 14 }}>{T.realDesc}</p>

          <div style={{ background: 'rgba(240,102,63,0.1)', border: '1px solid rgba(240,102,63,0.4)', borderRadius: 8, padding: '10px 12px', fontSize: 12.5, color: '#c2410c', margin: '12px 0' }}>
            ⚠️ {T.warn}
          </div>

          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>{T.exchange}</label>
          <select value={exchange} onChange={e => setExchange(e.target.value)}
            style={{ width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', marginBottom: 10 }}>
            <option value="binance">Binance</option>
            <option value="bybit">Bybit</option>
            <option value="coinbase">Coinbase</option>
          </select>
          <input placeholder={T.apiKey} style={{ width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', marginBottom: 8 }} />
          <input placeholder={T.apiSecret} type="password" style={{ width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', marginBottom: 12 }} />
          <button onClick={connect} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>{T.connect}</button>

          {connected && (
            <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.5 }}>ℹ️ {T.gated}</div>
          )}
        </div>
      </div>
    </div>
  )
}

export default AccountsPage
