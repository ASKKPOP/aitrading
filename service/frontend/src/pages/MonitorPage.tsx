import { useEffect, useState, useCallback } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { SymbolSelect } from '../components/SymbolSelect'
import { tr } from '../i18n'

// Personalized monitoring dashboard (Plan 06 C3): one board composing the
// user's automation rules, recent runs (with AI-verify verdicts), open
// positions with SL/TP, the alert feed, and Agent-Mode decisions. All from
// existing endpoints — no new backend beyond what the other phases added.

interface Props { token?: string | null }

export function MonitorPage({ token }: Props) {
  const { language } = useLanguage()
  const [rules, setRules] = useState<any[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [positions, setPositions] = useState<any[]>([])
  const [alerts, setAlerts] = useState<any[]>([])
  const [decisions, setDecisions] = useState<any[]>([])
  const [watches, setWatches] = useState<any[]>([])
  const [metrics, setMetrics] = useState<string[]>([])
  const [needsSymbol, setNeedsSymbol] = useState<string[]>([])
  const [wDraft, setWDraft] = useState({ name: '', metric: 'price', symbol: 'BTCUSDT', comparator: 'below', threshold: 60000, cooldown_min: 60 })
  const [wErr, setWErr] = useState('')
  const [wBusy, setWBusy] = useState(false)
  const [removingId, setRemovingId] = useState<number | null>(null)

  const auth = { Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    if (!token) return
    const grab = async (path: string, key: string) => {
      try {
        const r = await fetch(`${API_BASE}${path}`, { headers: auth })
        if (r.ok) return (await r.json())[key] || []
      } catch { /* transient */ }
      return []
    }
    setRules(await grab('/automation/configs', 'configs'))
    setRuns(await grab('/automation/runs?limit=20', 'runs'))
    setPositions(await grab('/positions', 'positions'))
    setAlerts(await grab('/alerts?limit=20', 'alerts'))
    setDecisions(await grab('/automation/agent-decisions?limit=10', 'decisions'))
    try {
      const r = await fetch(`${API_BASE}/watches`, { headers: auth })
      if (r.ok) {
        const d = await r.json()
        setWatches(d.watches || [])
        setMetrics(d.metrics || [])
        setNeedsSymbol(d.needs_symbol || [])
      }
    } catch { /* transient */ }
  }, [token])

  async function saveWatch() {
    setWErr(''); setWBusy(true)
    try {
      const body: any = { ...wDraft, name: wDraft.name.trim() || `${wDraft.metric} ${wDraft.comparator} ${wDraft.threshold}` }
      if (!needsSymbol.includes(wDraft.metric)) body.symbol = null
      const r = await fetch(`${API_BASE}/watches`, {
        method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Could not save watch')
      setWDraft({ ...wDraft, name: '' })
      await load()
    } catch (e: any) { setWErr(e.message) }
    finally { setWBusy(false) }
  }

  async function removeWatch(id: number) {
    setWErr(''); setRemovingId(id)
    try {
      const r = await fetch(`${API_BASE}/watches/${id}`, { method: 'DELETE', headers: auth })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        setWErr(typeof d.detail === 'string' ? d.detail : `error (HTTP ${r.status})`)
        return
      }
      await load()
    } catch { setWErr('network error') }
    finally { setRemovingId(null) }
  }

  useEffect(() => {
    load()
    const iv = setInterval(load, 20000)
    return () => clearInterval(iv)
  }, [load])

  const T = {
    title: tr(language, { ko: '모니터링', en: 'Monitoring', ja: 'モニタリング', th: 'การติดตาม', vi: 'Giám sát', id: 'Pemantauan' }),
    subtitle: tr(language, { ko: '내 규칙 · 실행 · 포지션 · 알림을 한 화면에서', en: 'Your rules, runs, positions and alerts on one board', ja: 'ルール・実行・ポジション・通知を一画面で', th: 'กฎ การรัน สถานะ และการแจ้งเตือนในหน้าเดียว', vi: 'Quy tắc, lần chạy, vị thế và cảnh báo trên một bảng', id: 'Aturan, run, posisi, dan peringatan Anda dalam satu papan' }),
    rules: tr(language, { ko: '자동화 규칙', en: 'Automation rules', ja: '自動売買ルール', th: 'กฎอัตโนมัติ', vi: 'Quy tắc tự động', id: 'Aturan otomatisasi' }),
    runs: tr(language, { ko: '최근 실행', en: 'Recent runs', ja: '実行履歴', th: 'การรันล่าสุด', vi: 'Lần chạy gần đây', id: 'Run terkini' }),
    positions: tr(language, { ko: '보유 포지션', en: 'Open positions', ja: '保有ポジション', th: 'สถานะที่เปิด', vi: 'Vị thế đang mở', id: 'Posisi terbuka' }),
    alerts: tr(language, { ko: '알림', en: 'Alerts', ja: '通知', th: 'การแจ้งเตือน', vi: 'Cảnh báo', id: 'Peringatan' }),
    decisions: tr(language, { ko: 'AI 결정 (완전 위임)', en: 'AI decisions (Agent mode)', ja: 'AI決定（完全委任）', th: 'การตัดสินใจ AI', vi: 'Quyết định AI', id: 'Keputusan AI (mode Agen)' }),
    watches: tr(language, { ko: '내 감시 조건', en: 'My watches', ja: '監視条件', th: 'เงื่อนไขเฝ้าดู', vi: 'Điều kiện theo dõi', id: 'Pantauan saya' }),
    watchHint: tr(language, { ko: '조건이 충족되면 알림이 발송됩니다 (인앱 · 이메일/SMS는 설정에서 옵트인).', en: 'An alert fires when the condition crosses (in-app; email/SMS via Settings opt-in).', ja: '条件を満たすと通知します（アプリ内・メール/SMSは設定で有効化）。', th: 'แจ้งเตือนเมื่อเงื่อนไขถึงเกณฑ์ (ในแอป; อีเมล/SMS เปิดในตั้งค่า)', vi: 'Cảnh báo khi điều kiện vượt ngưỡng (trong app; email/SMS bật ở Cài đặt).', id: 'Peringatan terpicu saat kondisinya terlampaui (dalam aplikasi; email/SMS bila diaktifkan di Pengaturan).' }),
    watchAdd: tr(language, { ko: '조건 추가', en: 'Add watch', ja: '条件を追加', th: 'เพิ่มเงื่อนไข', vi: 'Thêm điều kiện', id: 'Tambah pantauan' }),
    watchName: tr(language, { ko: '이름 (선택)', en: 'Name (optional)', ja: '名前（任意）', th: 'ชื่อ (ไม่บังคับ)', vi: 'Tên (tùy chọn)', id: 'Nama (opsional)' }),
    above: tr(language, { ko: '초과', en: 'above', ja: '超過', th: 'สูงกว่า', vi: 'trên', id: 'di atas' }),
    below: tr(language, { ko: '미만', en: 'below', ja: '未満', th: 'ต่ำกว่า', vi: 'dưới', id: 'di bawah' }),
    now: tr(language, { ko: '현재', en: 'now', ja: '現在', th: 'ตอนนี้', vi: 'hiện tại', id: 'sekarang' }),
    none: tr(language, { ko: '없음', en: 'None', ja: 'なし', th: 'ไม่มี', vi: 'Không có', id: 'Tidak ada' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.', id: 'Silakan masuk.' }),
  }

  if (!token) {
    return <div className="page-container"><h1 style={{ fontSize: 22, fontWeight: 800 }}>{T.title}</h1>
      <div className="empty-state"><div className="empty-title">{T.login}</div></div></div>
  }

  const card: any = { background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 12, padding: '14px 16px', marginBottom: 16 }
  const h3: any = { fontSize: 14, fontWeight: 700, margin: '0 0 10px', textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-secondary)' }
  const empty = <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{T.none}</div>
  const inp: any = { padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 12.5 }
  const pill = (bg: string, c: string, label: string) => (
    <span style={{ background: bg, color: c, fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 8px', whiteSpace: 'nowrap' }}>{label}</span>
  )
  const verifyPill = (v: any) => {
    if (!v) return null
    const map: any = { upheld: ['rgba(12,163,12,0.14)', 'var(--up,#0ca30c)'], weakened: ['rgba(201,133,0,0.16)', 'var(--warning,#c98500)'], rejected: ['rgba(208,59,59,0.14)', 'var(--error,#d03b3b)'] }
    const [bg, c] = map[v.verdict] || ['var(--bg-secondary)', 'var(--text-muted)']
    return pill(bg, c, `✓ ${v.verdict}`)
  }

  const stat = (n: number, color?: string) => <span style={{ fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{n}</span>

  return (
    <div className="page-container">
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 2 }}>{T.title}</h1>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 18 }}>{T.subtitle}</div>

      {/* stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: 12, marginBottom: 18 }}>
        {[[T.rules, rules.filter(r => r.enabled).length], [T.positions, positions.length],
          [T.alerts, alerts.length], [T.runs, runs.length]].map(([label, n]: any, i) => (
          <div key={i} style={card}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted)' }}>{label}</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4 }}>{stat(n, 'var(--accent-primary)')}</div>
          </div>
        ))}
      </div>

      {/* rules */}
      <div style={card}>
        <div style={h3}>{T.rules}</div>
        {rules.length === 0 ? empty : rules.map(r => (
          <div key={r.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 13, flexWrap: 'wrap' }}>
            <b>{r.mode === 'agent' ? `🤖 Agent · $${r.budget_usd}` : r.symbol}</b>
            {r.risk_level && pill('var(--bg-secondary)', 'var(--text-secondary)', r.risk_level)}
            {r.schedule_json && pill('rgba(57,135,229,0.12)', 'var(--accent-primary)', '🕑')}
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{r.interval_minutes}m · ≥{r.min_confidence}</span>
            <span style={{ marginLeft: 'auto' }}>{r.enabled ? pill('rgba(12,163,12,0.14)', 'var(--up,#0ca30c)', 'on') : pill('var(--bg-secondary)', 'var(--text-muted)', 'off')}</span>
          </div>
        ))}
      </div>

      {/* positions */}
      <div style={card}>
        <div style={h3}>{T.positions}</div>
        {positions.length === 0 ? empty : positions.map((p, i) => {
          const short = Number(p.quantity) < 0
          return (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 13, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
              <b>{p.symbol}</b>
              {short ? pill('rgba(208,59,59,0.14)', 'var(--error,#d03b3b)', 'SHORT') : pill('rgba(12,163,12,0.14)', 'var(--up,#0ca30c)', 'LONG')}
              <span style={{ color: 'var(--text-muted)' }}>{Math.abs(Number(p.quantity)).toFixed(4)} @ ${Number(p.entry_price).toFixed(2)}</span>
              {p.stop_loss && <span style={{ color: 'var(--error,#d03b3b)' }}>SL ${Number(p.stop_loss).toFixed(2)}</span>}
              {p.take_profit && <span style={{ color: 'var(--up,#0ca30c)' }}>TP ${Number(p.take_profit).toFixed(2)}</span>}
            </div>
          )
        })}
      </div>

      {/* runs with verify */}
      <div style={card}>
        <div style={h3}>{T.runs}</div>
        {runs.length === 0 ? empty : runs.map(run => {
          let verify: any = null
          try { verify = JSON.parse(run.confluence_json || '{}').verify } catch { /* ignore */ }
          return (
            <div key={run.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5, flexWrap: 'wrap' }}>
              <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{(run.ran_at || '').slice(5, 16).replace('T', ' ')}</span>
              <b>{run.action || '—'}</b>
              {run.confidence != null && <span style={{ color: 'var(--text-muted)' }}>{run.confidence}</span>}
              {verifyPill(verify)}
              {run.executed ? pill('rgba(12,163,12,0.14)', 'var(--up,#0ca30c)', '✓') : <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: 11.5 }}>{run.skip_reason || ''}</span>}
            </div>
          )
        })}
      </div>

      {/* agent decisions */}
      {decisions.length > 0 && (
        <div style={card}>
          <div style={h3}>{T.decisions}</div>
          {decisions.map(d => {
            let p: any = {}
            try { p = JSON.parse(d.params_json || '{}') } catch { /* ignore */ }
            return (
              <div key={d.id} style={{ padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
                  <b>{p.symbol}</b><span>${p.size_usd}</span><span>{p.interval_minutes}m</span><span>≥{p.min_confidence}</span><span>{p.risk_level}</span>
                  <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>{d.planner === 'llm' ? (d.llm_model || 'AI') : 'fallback'}</span>
                </div>
                {d.rationale && <div style={{ color: 'var(--text-secondary)', marginTop: 3 }}>{d.rationale}</div>}
              </div>
            )
          })}
        </div>
      )}

      {/* personal watch functions */}
      <div style={card}>
        <div style={h3}>{T.watches}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>{T.watchHint}</div>
        {watches.map(w => (
          <div key={w.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5, flexWrap: 'wrap' }}>
            <b>{w.name}</b>
            <span style={{ color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
              {w.metric}{w.symbol ? ` ${w.symbol}` : ''} {w.comparator === 'above' ? T.above : T.below} {Number(w.threshold).toLocaleString()}
            </span>
            {w.current_value != null && (
              <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                ({T.now} {Number(w.current_value).toLocaleString(undefined, { maximumFractionDigits: 2 })})
              </span>
            )}
            {!w.enabled && pill('var(--bg-secondary)', 'var(--text-muted)', 'off')}
            <button onClick={() => removeWatch(w.id)} disabled={removingId !== null} style={{ marginLeft: 'auto', border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 11, padding: '3px 9px', cursor: 'pointer', opacity: removingId === w.id ? 0.5 : 1 }}>{removingId === w.id ? '⏳' : '×'}</button>
          </div>
        ))}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
          <input placeholder={T.watchName} value={wDraft.name} onChange={e => setWDraft({ ...wDraft, name: e.target.value })}
            style={{ ...inp, width: 130 }} />
          <select value={wDraft.metric} onChange={e => setWDraft({ ...wDraft, metric: e.target.value })} style={inp}>
            {metrics.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          {needsSymbol.includes(wDraft.metric) && (
            <SymbolSelect variant="pair" value={wDraft.symbol} onChange={symbol => setWDraft({ ...wDraft, symbol })}
              style={{ ...inp, width: 120 }} />
          )}
          <select value={wDraft.comparator} onChange={e => setWDraft({ ...wDraft, comparator: e.target.value })} style={inp}>
            <option value="above">{T.above}</option>
            <option value="below">{T.below}</option>
          </select>
          <input type="number" value={wDraft.threshold} onChange={e => setWDraft({ ...wDraft, threshold: +e.target.value })}
            style={{ ...inp, width: 110 }} />
          <button onClick={saveWatch} disabled={wBusy} style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 600, fontSize: 12.5, cursor: 'pointer', opacity: wBusy ? 0.6 : 1 }}>{wBusy ? '⏳' : '+'} {T.watchAdd}</button>
          {wErr && <span style={{ color: 'var(--error,#d03b3b)', fontSize: 12 }}>⚠️ {wErr}</span>}
        </div>
      </div>

      {/* alerts */}
      <div style={card}>
        <div style={h3}>{T.alerts}</div>
        {alerts.length === 0 ? empty : alerts.map(a => (
          <div key={a.id} style={{ padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b>{a.title}</b>
              <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{(a.created_at || '').slice(5, 16).replace('T', ' ')}</span>
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>{a.body}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default MonitorPage
