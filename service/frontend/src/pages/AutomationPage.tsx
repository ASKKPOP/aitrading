import { useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Automation (Target 3) — user-configured AI auto-trading rules, backed by
// /api/automation/configs. The server worker runs each enabled rule on its
// interval: multi-agent analysis -> decision -> auto paper-trade (simulator)
// when action + confidence meet the rule. Run history from /api/automation/runs.
type Rule = {
  id?: number; symbol: string; market: string; provider: string | null; interval_minutes: number;
  min_confidence: number; size_usd: number; auto_execute: boolean | number; account_type: string;
  enabled?: boolean | number; last_run_at?: string | null;
}

const DEFAULT_DRAFT: Rule = { symbol: 'BTC', market: 'crypto', provider: null, interval_minutes: 60, min_confidence: 0.65, size_usd: 500, auto_execute: false, account_type: 'simulator' }

export function AutomationPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [rules, setRules] = useState<Rule[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [draft, setDraft] = useState<Rule>({ ...DEFAULT_DRAFT })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const T = {
    title: tr(language, { ko: '자동화', en: 'Automation', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động hóa' }),
    subtitle: tr(language, { ko: 'AI가 설정한 일정에 따라 실행되며, 결정이 규칙에 부합할 때 모의 거래를 수행합니다', en: 'AI runs on your schedule and paper-trades when the decision meets your rules', ja: 'スケジュールに沿ってAIが自動売買', th: 'AI ทำงานตามเวลาและเทรดเมื่อเข้าเงื่อนไข', vi: 'AI chạy theo lịch và giao dịch khi đủ điều kiện' }),
    symbol: tr(language, { ko: '종목', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' }),
    market: tr(language, { ko: '시장', en: 'Market', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    provider: tr(language, { ko: 'AI 제공자', en: 'AI provider', ja: 'AIプロバイダー', th: 'ผู้ให้บริการ AI', vi: 'Nhà cung cấp AI' }),
    serverDefault: tr(language, { ko: '서버 기본값', en: 'server default', ja: 'サーバー既定', th: 'ค่าเริ่มต้นเซิร์ฟเวอร์', vi: 'mặc định máy chủ' }),
    interval: tr(language, { ko: '실행 주기 (분)', en: 'Run every (min)', ja: '実行間隔（分）', th: 'ทุกๆ (นาที)', vi: 'Mỗi (phút)' }),
    minConf: tr(language, { ko: '최소 신뢰도', en: 'Min confidence', ja: '最低信頼度', th: 'ความมั่นใจขั้นต่ำ', vi: 'Độ tin cậy tối thiểu' }),
    size: tr(language, { ko: '포지션 크기 ($)', en: 'Position size ($)', ja: 'ポジションサイズ', th: 'ขนาดโพซิชัน ($)', vi: 'Kích thước lệnh ($)' }),
    account: tr(language, { ko: '계정', en: 'Account', ja: '口座', th: 'บัญชี', vi: 'Tài khoản' }),
    autoEx: tr(language, { ko: '자동 실행', en: 'Auto-execute', ja: '自動執行', th: 'ดำเนินการอัตโนมัติ', vi: 'Tự động thực hiện' }),
    add: tr(language, { ko: '규칙 추가', en: 'Add rule', ja: 'ルールを追加', th: 'เพิ่มกฎ', vi: 'Thêm quy tắc' }),
    remove: tr(language, { ko: '제거', en: 'Remove', ja: '削除', th: 'ลบ', vi: 'Xóa' }),
    yourRules: tr(language, { ko: '내 자동화 규칙', en: 'Your automation rules', ja: '自動売買ルール', th: 'กฎอัตโนมัติของคุณ', vi: 'Quy tắc của bạn' }),
    empty: tr(language, { ko: '아직 규칙이 없습니다. 위에서 추가하세요.', en: 'No rules yet. Add one above.', ja: 'ルールはまだありません。', th: 'ยังไม่มีกฎ', vi: 'Chưa có quy tắc.' }),
    history: tr(language, { ko: '최근 실행', en: 'Recent runs', ja: '実行履歴', th: 'ประวัติล่าสุด', vi: 'Lần chạy gần đây' }),
    noRuns: tr(language, { ko: '아직 실행 기록이 없습니다 — 워커가 매분 예정된 규칙을 확인합니다.', en: 'No runs yet — the worker checks due rules every minute.', ja: 'まだ実行はありません。', th: 'ยังไม่มีการทำงาน — ระบบตรวจทุกนาที', vi: 'Chưa có lần chạy nào.' }),
    executed: tr(language, { ko: '체결됨', en: 'executed', ja: '執行', th: 'ดำเนินการแล้ว', vi: 'đã thực hiện' }),
    realNote: tr(language, { ko: '실계좌의 규칙은 분석만 실행합니다 — 이 빌드에서는 라이브 주문 실행이 비활성화되어 있습니다.', en: 'Rules on the real account run analysis only — live order execution is disabled in this build.', ja: '実口座ルールは分析のみ実行します。', th: 'กฎบัญชีจริงจะวิเคราะห์เท่านั้น — ไม่มีการส่งคำสั่งจริงในเวอร์ชันนี้', vi: 'Quy tắc tài khoản thật chỉ phân tích.' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
  }

  const authHeaders: any = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }

  async function refresh() {
    try {
      const [cfgRes, runRes] = await Promise.all([
        fetch(`${API_BASE}/automation/configs`, { headers: authHeaders }),
        fetch(`${API_BASE}/automation/runs?limit=15`, { headers: authHeaders }),
      ])
      const cfg = await cfgRes.json(); const run = await runRes.json()
      if (cfgRes.ok) setRules(cfg.configs || [])
      if (runRes.ok) setRuns(run.runs || [])
    } catch { /* transient */ }
  }

  useEffect(() => {
    if (!token) return
    refresh()
    const iv = setInterval(refresh, 30000)
    return () => clearInterval(iv)
  }, [token])

  async function add() {
    setBusy(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/automation/configs`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify({ ...draft, provider: draft.provider || null, lang: language }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save rule')
      await refresh()
    } catch (e: any) { setError(e.message) }
    setBusy(false)
  }

  async function remove(id?: number) {
    if (!id) return
    try {
      await fetch(`${API_BASE}/automation/configs/${id}`, { method: 'DELETE', headers: authHeaders })
      await refresh()
    } catch { /* ignore */ }
  }

  const inp: any = { padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-input,#fff)', color: 'inherit' }
  const fld = (label: string, node: any) => <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>{label}{node}</label>

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">⚙</div><div className="empty-title">{T.login}</div></div></div>
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 12 }}>
          {fld(T.symbol, <input style={inp} value={draft.symbol} onChange={e => setDraft({ ...draft, symbol: e.target.value.toUpperCase() })} />)}
          {fld(T.market, <select style={inp} value={draft.market} onChange={e => setDraft({ ...draft, market: e.target.value })}><option value="crypto">crypto</option><option value="us-stock">us-stock</option></select>)}
          {fld(T.provider, <select style={inp} value={draft.provider || ''} onChange={e => setDraft({ ...draft, provider: e.target.value || null })}><option value="">{T.serverDefault}</option>{['openai', 'gemini', 'grok', 'qwen', 'glm', 'local', 'anthropic'].map(p => <option key={p} value={p}>{p}</option>)}</select>)}
          {fld(T.interval, <input style={inp} type="number" min={5} value={draft.interval_minutes} onChange={e => setDraft({ ...draft, interval_minutes: +e.target.value })} />)}
          {fld(T.minConf, <input style={inp} type="number" step="0.05" min="0" max="1" value={draft.min_confidence} onChange={e => setDraft({ ...draft, min_confidence: +e.target.value })} />)}
          {fld(T.size, <input style={inp} type="number" value={draft.size_usd} onChange={e => setDraft({ ...draft, size_usd: +e.target.value })} />)}
          {fld(T.account, <select style={inp} value={draft.account_type} onChange={e => setDraft({ ...draft, account_type: e.target.value })}><option value="simulator">simulator</option><option value="real">real</option></select>)}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={!!draft.auto_execute} onChange={e => setDraft({ ...draft, auto_execute: e.target.checked })} /> {T.autoEx}
          </label>
          {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
          <button onClick={add} disabled={busy} style={{ marginLeft: 'auto', padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>+ {T.add}</button>
        </div>
      </div>

      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '0 0 10px' }}>{T.yourRules}</div>
      {rules.length === 0 ? (
        <div className="card" style={{ color: 'var(--text-secondary,#8a8073)' }}>{T.empty}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rules.map((r) => (
            <div key={r.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <b style={{ fontSize: 15 }}>{r.symbol}</b>
              <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>
                {r.market} · {r.provider || T.serverDefault} · {r.interval_minutes}m · ≥{Math.round((r.min_confidence || 0) * 100)}% · ${r.size_usd} · {r.account_type}
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: r.auto_execute ? 'rgba(63,185,80,0.16)' : 'rgba(138,128,115,0.18)', color: r.auto_execute ? '#3fb950' : '#8a8073' }}>
                {r.auto_execute ? 'auto' : 'analysis only'}
              </span>
              {r.last_run_at && <span style={{ fontSize: 11, color: 'var(--text-secondary,#8a8073)' }}>last: {String(r.last_run_at).replace('T', ' ').slice(0, 16)}</span>}
              <button onClick={() => remove(r.id)} style={{ marginLeft: 'auto', padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>{T.remove}</button>
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '22px 0 10px' }}>{T.history}</div>
      {runs.length === 0 ? (
        <div className="card" style={{ color: 'var(--text-secondary,#8a8073)' }}>{T.noRuns}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {runs.map((run) => (
            <div key={run.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '12px 16px' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>{String(run.ran_at || '').replace('T', ' ').slice(0, 16)}</span>
              <b style={{ textTransform: 'uppercase', fontSize: 13, color: run.action === 'buy' ? '#3fb950' : run.action === 'sell' ? '#f0663f' : '#e3a008' }}>{run.action || '—'}</b>
              <span style={{ fontSize: 12 }}>{Math.round((run.confidence || 0) * 100)}%</span>
              {run.executed
                ? <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: 'rgba(63,185,80,0.16)', color: '#3fb950' }}>✓ {T.executed} #{run.signal_id}</span>
                : <span style={{ fontSize: 11.5, color: 'var(--text-secondary,#8a8073)' }}>{run.skip_reason}</span>}
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 18, fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.55 }}>ℹ️ {T.realNote}</div>
    </div>
  )
}

export default AutomationPage
