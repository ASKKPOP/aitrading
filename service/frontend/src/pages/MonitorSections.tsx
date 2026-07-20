import { useCallback, useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { SymbolSelect } from '../components/SymbolSelect'
import { tr } from '../i18n'

// Monitoring sections, extracted from the old standalone /monitor page so the
// one auto-trading page can show live state next to the controls that produce
// it (Plan 12). The split forced users to configure on one page and navigate
// elsewhere to learn whether it worked — and rendered rules/runs/decisions
// twice from the same endpoints, where the two copies could disagree.
//
// What lives here is only what /monitor genuinely owned: the status band, open
// positions, the alert feed, and watches. Rules, runs and AI decisions stay on
// the automation page, which already renders them with full controls.

const card: any = { background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 12, padding: '14px 16px', marginBottom: 16 }
const h3: any = { fontSize: 13, fontWeight: 700, margin: '0 0 10px', textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-secondary)' }
const inp: any = { padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 12.5 }
const row: any = { display: 'flex', gap: 10, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 13, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }

const pill = (bg: string, c: string, label: string) => (
  <span style={{ background: bg, color: c, fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 8px', whiteSpace: 'nowrap' }}>{label}</span>
)

export type MonitorData = {
  positions: any[]
  alerts: any[]
  runs: any[]
  rules: any[]
  activeRuns: number
  /** True when the API rejected our credentials. Without this an auth failure
   *  renders identically to a genuinely empty account — every counter reads 0
   *  and the board looks broken rather than logged out. */
  authFailed: boolean
}

const ACTIVE_RUN_STATUSES = new Set(['running', 'armed', 'paused', 'stopping'])

/**
 * Shared poller so the band and the detail sections never disagree.
 *
 * The token is read from storage at REQUEST time, not captured once. The old
 * standalone /monitor page got a live token prop from App and re-rendered when
 * auth changed; AutomationPage snapshots localStorage at mount, so a snapshot
 * that goes stale made every monitoring call 401 and the whole board read as
 * zeros — indistinguishable from "monitoring is gone".
 */
export function useMonitorData(token?: string | null, intervalMs = 20000): MonitorData {
  const [data, setData] = useState<MonitorData>({ positions: [], alerts: [], runs: [], rules: [], activeRuns: 0, authFailed: false })

  const load = useCallback(async () => {
    const live = localStorage.getItem('claw_token') || token
    if (!live) return
    const auth = { Authorization: `Bearer ${live}` }
    let authFailed = false
    const grab = async (path: string, key: string) => {
      try {
        const r = await fetch(`${API_BASE}${path}`, { headers: auth })
        if (r.ok) return (await r.json())[key] || []
        if (r.status === 401) authFailed = true
      } catch { /* transient — keep the last good value */ }
      return []
    }
    const [positions, alerts, runs, rules, liveRuns] = await Promise.all([
      grab('/positions', 'positions'),
      grab('/alerts?limit=20', 'alerts'),
      grab('/automation/runs?limit=20', 'runs'),
      grab('/automation/configs', 'configs'),
      grab('/runs', 'runs'),
    ])
    const activeRuns = (liveRuns as any[]).filter(r => ACTIVE_RUN_STATUSES.has(r?.status)).length
    setData({ positions, alerts, runs, rules, activeRuns, authFailed })
  }, [token])

  useEffect(() => {
    load()
    const iv = setInterval(load, intervalMs)
    return () => clearInterval(iv)
  }, [load, intervalMs])

  return data
}

/**
 * Always-visible state strip. This is the piece that makes the merge work:
 * whatever level you are on, you can see whether anything is running, what you
 * are holding and what it is worth without leaving the page. Money state is
 * never hidden by a level — only configuration surface is.
 */
export function StatusBand({ data }: { data: MonitorData }) {
  const { language } = useLanguage()
  const openPnl = data.positions.reduce((sum, p) => sum + (Number(p.pnl) || 0), 0)
  const enabledRules = data.rules.filter((r: any) => r.enabled).length
  const activeRuns = data.activeRuns

  const T = {
    running: tr(language, { ko: '가동 중', en: 'Running', ja: '稼働中', th: 'กำลังทำงาน', vi: 'Đang chạy' }),
    rules: tr(language, { ko: '활성 규칙', en: 'Active rules', ja: '有効ルール', th: 'กฎที่เปิด', vi: 'Quy tắc bật' }),
    positions: tr(language, { ko: '보유 포지션', en: 'Open positions', ja: '保有ポジション', th: 'สถานะเปิด', vi: 'Vị thế mở' }),
    pnl: tr(language, { ko: '평가 손익', en: 'Open P&L', ja: '評価損益', th: 'กำไรขาดทุน', vi: 'Lãi/lỗ mở' }),
    alerts: tr(language, { ko: '알림', en: 'Alerts', ja: '通知', th: 'แจ้งเตือน', vi: 'Cảnh báo' }),
  }

  const cells: Array<[string, string, string | undefined]> = [
    [T.running, String(activeRuns), activeRuns > 0 ? 'var(--accent-primary)' : undefined],
    [T.rules, String(enabledRules), undefined],
    [T.positions, String(data.positions.length), undefined],
    [T.pnl, `${openPnl >= 0 ? '+' : ''}${openPnl.toFixed(2)}`,
      openPnl === 0 ? undefined : openPnl > 0 ? '#3fb950' : '#f0663f'],
    [T.alerts, String(data.alerts.length), undefined],
  ]

  if (data.authFailed) {
    return (
      <div style={{ ...card, borderColor: '#c98500', color: '#c98500', fontSize: 13 }}>
        ⚠️ {tr(language, {
          ko: '세션이 만료되어 모니터링 데이터를 불러오지 못했습니다. 새로고침하거나 다시 로그인해 주세요.',
          en: 'Session expired — monitoring data could not be loaded. Refresh the page or sign in again.',
          ja: 'セッションが期限切れです。再読み込みまたは再ログインしてください。',
          th: 'เซสชันหมดอายุ — โหลดข้อมูลไม่ได้ กรุณารีเฟรชหรือเข้าสู่ระบบใหม่',
          vi: 'Phiên đã hết hạn — không tải được dữ liệu. Hãy tải lại hoặc đăng nhập lại.',
        })}
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(110px,1fr))', gap: 10, marginBottom: 18 }}>
      {cells.map(([label, value, color]) => (
        <div key={label} style={{ ...card, marginBottom: 0, padding: '11px 13px' }}>
          <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted)' }}>{label}</div>
          <div style={{ fontSize: 21, fontWeight: 800, marginTop: 3, color, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
        </div>
      ))}
    </div>
  )
}

export function PositionsSection({ data }: { data: MonitorData }) {
  const { language } = useLanguage()
  const T = {
    title: tr(language, { ko: '보유 포지션', en: 'Open positions', ja: '保有ポジション', th: 'สถานะที่เปิด', vi: 'Vị thế đang mở' }),
    none: tr(language, { ko: '보유 중인 포지션이 없습니다', en: 'No open positions', ja: 'ポジションはありません', th: 'ไม่มีสถานะเปิด', vi: 'Không có vị thế' }),
  }
  return (
    <div style={card}>
      <div style={h3}>{T.title}</div>
      {data.positions.length === 0
        ? <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{T.none}</div>
        : data.positions.map((p, i) => {
          const short = Number(p.quantity) < 0 || p.side === 'short'
          const pnl = Number(p.pnl)
          return (
            <div key={i} style={row}>
              <b>{p.symbol}</b>
              {short ? pill('rgba(208,59,59,0.14)', '#f0663f', 'SHORT') : pill('rgba(12,163,12,0.14)', '#3fb950', 'LONG')}
              <span style={{ color: 'var(--text-muted)' }}>
                {Math.abs(Number(p.quantity)).toFixed(4)} @ ${Number(p.entry_price).toFixed(2)}
              </span>
              {p.stop_loss && <span style={{ color: '#f0663f' }}>SL ${Number(p.stop_loss).toFixed(2)}</span>}
              {p.take_profit && <span style={{ color: '#3fb950' }}>TP ${Number(p.take_profit).toFixed(2)}</span>}
              {!Number.isNaN(pnl) && (
                <span style={{ marginLeft: 'auto', fontWeight: 700, color: pnl >= 0 ? '#3fb950' : '#f0663f' }}>
                  {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                </span>
              )}
            </div>
          )
        })}
    </div>
  )
}

export function AlertsSection({ data }: { data: MonitorData }) {
  const { language } = useLanguage()
  const T = {
    title: tr(language, { ko: '알림', en: 'Alerts', ja: '通知', th: 'การแจ้งเตือน', vi: 'Cảnh báo' }),
    none: tr(language, { ko: '알림이 없습니다', en: 'No alerts', ja: '通知はありません', th: 'ไม่มีการแจ้งเตือน', vi: 'Không có cảnh báo' }),
  }
  return (
    <div style={card}>
      <div style={h3}>{T.title}</div>
      {data.alerts.length === 0
        ? <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{T.none}</div>
        : data.alerts.map(a => (
          <div key={a.id} style={{ padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b>{a.title}</b>
              <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                {(a.created_at || '').slice(5, 16).replace('T', ' ')}
              </span>
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>{a.body}</div>
          </div>
        ))}
    </div>
  )
}

/** Custom metric→alert conditions. Pro-level: it asks the user to name a
 *  metric and a threshold, which presumes they know which metric matters. */
export function WatchesSection({ token }: { token?: string | null }) {
  const { language } = useLanguage()
  const [watches, setWatches] = useState<any[]>([])
  const [metrics, setMetrics] = useState<string[]>([])
  const [needsSymbol, setNeedsSymbol] = useState<string[]>([])
  const [draft, setDraft] = useState({ name: '', metric: 'price', symbol: 'BTCUSDT', comparator: 'below', threshold: 60000, cooldown_min: 60 })
  const [err, setErr] = useState('')

  const auth = { Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/watches`, { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) {
        const d = await r.json()
        setWatches(d.watches || [])
        setMetrics(d.metrics || [])
        setNeedsSymbol(d.needs_symbol || [])
      }
    } catch { /* transient */ }
  }, [token])

  useEffect(() => { load() }, [load])

  async function save() {
    setErr('')
    try {
      const body: any = { ...draft, name: draft.name.trim() || `${draft.metric} ${draft.comparator} ${draft.threshold}` }
      if (!needsSymbol.includes(draft.metric)) body.symbol = null
      const r = await fetch(`${API_BASE}/watches`, {
        method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Could not save watch')
      setDraft({ ...draft, name: '' })
      await load()
    } catch (e: any) { setErr(e.message) }
  }

  async function remove(id: number) {
    try {
      await fetch(`${API_BASE}/watches/${id}`, { method: 'DELETE', headers: auth })
      await load()
    } catch { /* ignore */ }
  }

  const T = {
    title: tr(language, { ko: '내 감시 조건', en: 'My watches', ja: '監視条件', th: 'เงื่อนไขเฝ้าดู', vi: 'Điều kiện theo dõi' }),
    hint: tr(language, { ko: '조건이 충족되면 알림이 발송됩니다 (인앱 · 이메일/SMS는 설정에서 옵트인).', en: 'An alert fires when the condition crosses (in-app; email/SMS via Settings opt-in).', ja: '条件を満たすと通知します（アプリ内・メール/SMSは設定で有効化）。', th: 'แจ้งเตือนเมื่อเงื่อนไขถึงเกณฑ์', vi: 'Cảnh báo khi điều kiện vượt ngưỡng.' }),
    add: tr(language, { ko: '조건 추가', en: 'Add watch', ja: '条件を追加', th: 'เพิ่มเงื่อนไข', vi: 'Thêm điều kiện' }),
    name: tr(language, { ko: '이름 (선택)', en: 'Name (optional)', ja: '名前（任意）', th: 'ชื่อ (ไม่บังคับ)', vi: 'Tên (tùy chọn)' }),
    above: tr(language, { ko: '초과', en: 'above', ja: '超過', th: 'สูงกว่า', vi: 'trên' }),
    below: tr(language, { ko: '미만', en: 'below', ja: '未満', th: 'ต่ำกว่า', vi: 'dưới' }),
    now: tr(language, { ko: '현재', en: 'now', ja: '現在', th: 'ตอนนี้', vi: 'hiện tại' }),
  }

  return (
    <div style={card}>
      <div style={h3}>{T.title}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>{T.hint}</div>
      {watches.map(w => (
        <div key={w.id} style={{ ...row, fontSize: 12.5 }}>
          <b>{w.name}</b>
          <span style={{ color: 'var(--text-secondary)' }}>
            {w.metric}{w.symbol ? ` ${w.symbol}` : ''} {w.comparator === 'above' ? T.above : T.below} {Number(w.threshold).toLocaleString()}
          </span>
          {w.current_value != null && (
            <span style={{ color: 'var(--text-muted)' }}>
              ({T.now} {Number(w.current_value).toLocaleString(undefined, { maximumFractionDigits: 2 })})
            </span>
          )}
          {!w.enabled && pill('var(--bg-secondary)', 'var(--text-muted)', 'off')}
          <button onClick={() => remove(w.id)}
            style={{ marginLeft: 'auto', border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 11, padding: '3px 9px', cursor: 'pointer' }}>×</button>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
        <input placeholder={T.name} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} style={{ ...inp, width: 130 }} />
        <select value={draft.metric} onChange={e => setDraft({ ...draft, metric: e.target.value })} style={inp}>
          {metrics.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        {needsSymbol.includes(draft.metric) && (
          <SymbolSelect variant="pair" value={draft.symbol} onChange={symbol => setDraft({ ...draft, symbol })} style={{ ...inp, width: 120 }} />
        )}
        <select value={draft.comparator} onChange={e => setDraft({ ...draft, comparator: e.target.value })} style={inp}>
          <option value="above">{T.above}</option>
          <option value="below">{T.below}</option>
        </select>
        <input type="number" value={draft.threshold} onChange={e => setDraft({ ...draft, threshold: +e.target.value })} style={{ ...inp, width: 110 }} />
        <button onClick={save} style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 600, fontSize: 12.5, cursor: 'pointer' }}>+ {T.add}</button>
        {err && <span style={{ color: '#f0663f', fontSize: 12 }}>⚠️ {err}</span>}
      </div>
    </div>
  )
}

/**
 * Simple-level activity: the same run history the other levels get, rendered
 * as plain sentences instead of action/confidence/skip-reason columns. A
 * beginner needs to know the AI looked and chose not to act — not the
 * confidence float that drove it.
 */
export function PlainActivity({ data }: { data: MonitorData }) {
  const { language } = useLanguage()
  const T = {
    title: tr(language, { ko: '최근 활동', en: 'Recent activity', ja: '最近の動き', th: 'กิจกรรมล่าสุด', vi: 'Hoạt động gần đây' }),
    none: tr(language, { ko: '아직 활동이 없습니다. 위에서 자동매매를 시작하세요.', en: 'Nothing yet — start auto-trading above.', ja: 'まだ動きはありません。上で開始してください。', th: 'ยังไม่มีกิจกรรม เริ่มด้านบน', vi: 'Chưa có hoạt động — bắt đầu ở trên.' }),
  }
  const sentence = (r: any) => {
    const sym = r.symbol || ''
    const act = (r.action || '').toLowerCase()
    if (r.executed) {
      const verb = act === 'buy'
        ? tr(language, { ko: '매수했습니다', en: 'bought', ja: '買いました', th: 'ซื้อแล้ว', vi: 'đã mua' })
        : tr(language, { ko: '매도했습니다', en: 'sold', ja: '売りました', th: 'ขายแล้ว', vi: 'đã bán' })
      return `AI ${tr(language, { ko: '가', en: '', ja: 'が', th: '', vi: '' })}${sym} ${verb}`
    }
    if (act === 'hold') {
      return tr(language, {
        ko: `AI가 ${sym}을(를) 살펴봤지만 진입하지 않았습니다`,
        en: `AI looked at ${sym} and chose not to trade`,
        ja: `AIは${sym}を確認しましたが、エントリーしませんでした`,
        th: `AI ดู ${sym} แล้วเลือกไม่เทรด`,
        vi: `AI đã xem ${sym} và chọn không giao dịch`,
      })
    }
    return tr(language, {
      ko: `${sym} 분석은 했지만 조건을 못 넘었습니다`,
      en: `Analyzed ${sym} but the bar was not met`,
      ja: `${sym}を分析しましたが条件を満たしませんでした`,
      th: `วิเคราะห์ ${sym} แต่ไม่ผ่านเกณฑ์`,
      vi: `Đã phân tích ${sym} nhưng chưa đạt ngưỡng`,
    })
  }
  return (
    <div style={card}>
      <div style={h3}>{T.title}</div>
      {data.runs.length === 0
        ? <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{T.none}</div>
        : data.runs.slice(0, 8).map(r => (
          <div key={r.id} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 13, alignItems: 'baseline' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 11.5, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
              {(r.ran_at || '').slice(5, 16).replace('T', ' ')}
            </span>
            <span>{sentence(r)}</span>
            {r.executed && <span style={{ marginLeft: 'auto' }}>{pill('rgba(12,163,12,0.14)', '#3fb950', '✓')}</span>}
          </div>
        ))}
    </div>
  )
}

/**
 * Full-delegation decisions with their rationale. The old /monitor page showed
 * these unconditionally; the merge briefly buried them inside the delegation
 * setup card, which hid them from anyone reviewing what the AI had decided.
 */
export function AgentDecisionsSection({ token }: { token?: string | null }) {
  const { language } = useLanguage()
  const [decisions, setDecisions] = useState<any[]>([])

  useEffect(() => {
    let stop = false
    const load = async () => {
      const live = localStorage.getItem('claw_token') || token
      if (!live) return
      try {
        const r = await fetch(`${API_BASE}/automation/agent-decisions?limit=10`, {
          headers: { Authorization: `Bearer ${live}` },
        })
        if (r.ok && !stop) setDecisions((await r.json()).decisions || [])
      } catch { /* transient */ }
    }
    load()
    const iv = setInterval(load, 30000)
    return () => { stop = true; clearInterval(iv) }
  }, [token])

  if (decisions.length === 0) return null

  const T = {
    title: tr(language, { ko: 'AI 결정 (완전 위임)', en: 'AI decisions (full delegation)', ja: 'AI決定（完全委任）', th: 'การตัดสินใจ AI', vi: 'Quyết định AI' }),
  }
  return (
    <div style={card}>
      <div style={h3}>{T.title}</div>
      {decisions.map(d => {
        let p: any = {}
        try { p = JSON.parse(d.params_json || '{}') } catch { /* show what we can */ }
        return (
          <div key={d.id} style={{ padding: '7px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
              <b>{p.symbol}</b><span>${p.size_usd}</span><span>{p.interval_minutes}m</span>
              <span>≥{p.min_confidence}</span><span>{p.risk_level}</span>
              <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>
                {d.planner === 'llm' ? (d.llm_model || 'AI') : 'fallback'}
              </span>
            </div>
            {d.rationale && <div style={{ color: 'var(--text-secondary)', marginTop: 3 }}>{d.rationale}</div>}
          </div>
        )
      })}
    </div>
  )
}

/** Standard/Pro run history: action, confidence, the verifier's verdict. */
export function RunHistorySection({ data }: { data: MonitorData }) {
  const { language } = useLanguage()
  const T = {
    title: tr(language, { ko: '최근 실행', en: 'Recent runs', ja: '実行履歴', th: 'การรันล่าสุด', vi: 'Lần chạy gần đây' }),
    none: tr(language, { ko: '실행 기록이 없습니다', en: 'No runs yet', ja: '実行履歴はありません', th: 'ยังไม่มีการรัน', vi: 'Chưa có lần chạy' }),
  }
  const verifyPill = (v: any) => {
    if (!v) return null
    const map: any = {
      upheld: ['rgba(12,163,12,0.14)', '#3fb950'],
      weakened: ['rgba(201,133,0,0.16)', '#c98500'],
      rejected: ['rgba(208,59,59,0.14)', '#f0663f'],
    }
    const [bg, c] = map[v.verdict] || ['var(--bg-secondary)', 'var(--text-muted)']
    return pill(bg, c, `✓ ${v.verdict}`)
  }
  return (
    <div style={card}>
      <div style={h3}>{T.title}</div>
      {data.runs.length === 0
        ? <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{T.none}</div>
        : data.runs.map(run => {
          let verify: any = null
          try { verify = JSON.parse(run.confluence_json || '{}').verify } catch { /* ignore */ }
          return (
            <div key={run.id} style={{ ...row, fontSize: 12.5 }}>
              <span style={{ color: 'var(--text-muted)' }}>{(run.ran_at || '').slice(5, 16).replace('T', ' ')}</span>
              {run.symbol && <b>{run.symbol}</b>}
              <b>{run.action || '—'}</b>
              {run.confidence != null && <span style={{ color: 'var(--text-muted)' }}>{run.confidence}</span>}
              {verifyPill(verify)}
              {run.executed
                ? pill('rgba(12,163,12,0.14)', '#3fb950', '✓')
                : <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontSize: 11.5 }}>{run.skip_reason || ''}</span>}
            </div>
          )
        })}
    </div>
  )
}
