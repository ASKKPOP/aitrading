import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { RunSparkline } from '../components/RunSparkline'
import { useRunStream } from '../hooks/useRunStream'
import { Language, tr } from '../i18n'

// Live trading-run dashboard (Plan 10, Phase 8). Route /runs/live.
//   * multi-run grid of small multiples (equity WebGL2 sparkline + status +
//     last-update AGE BADGE — honest staleness for poll-bound markets)
//   * click-through to run detail (price/equity chart + event log)
//   * create form (settings + reporting) and lifecycle controls
// Streaming is via useRunStream (ticketed /ws/runs); the grid equity series
// come from each run's snapshot + live equity events.

interface Props { token?: string | null }

type Run = {
  id: number; symbol: string; market: string; market_type: string
  status: string; status_reason?: string
  config?: any; realized_pnl_usd?: number
  last_cycle_at?: string; last_event_seq?: number
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'var(--text-muted, #898781)',
  armed: '#eda100',
  running: '#0ca30c',
  paused: '#7a68d8',
  stopping: '#eb6834',
  stopped: '#898781',
}

function ageLabel(ts: string | undefined, lang: Language): string {
  if (!ts) return tr(lang, { ko: '대기', en: 'idle', ja: '待機', th: 'ว่าง', vi: 'chờ' })
  const secs = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000)
  if (secs < 60) return `${Math.round(secs)}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  return `${Math.round(secs / 3600)}h`
}

export function RunsLivePage({ token }: Props) {
  const { language } = useLanguage()
  const [runs, setRuns] = useState<Run[]>([])
  const [equityByRun, setEquityByRun] = useState<Record<number, number[]>>({})
  const [selected, setSelected] = useState<number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [err, setErr] = useState('')

  const auth = useMemo(() => ({ 'Content-Type': 'application/json',
    Authorization: `Bearer ${token}` }), [token])

  const load = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/runs`, { headers: auth })
      if (r.ok) setRuns((await r.json()).runs || [])
    } catch { /* transient */ }
  }, [token, auth])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const id = setInterval(load, 20000)  // low-frequency reconcile; WS carries live
    return () => clearInterval(id)
  }, [load])

  const activeRunIds = useMemo(
    () => runs.filter((r) => ['armed', 'running', 'paused', 'stopping'].includes(r.status))
      .map((r) => r.id),
    [runs])
  const { connected, eventsByRun, tickByRun } = useRunStream(token || null, activeRunIds)

  // seed equity series from snapshots for the grid
  useEffect(() => {
    for (const run of runs) {
      if (equityByRun[run.id]) continue
      fetch(`${API_BASE}/runs/${run.id}/events?limit=500`, { headers: auth })
        .then((r) => (r.ok ? r.json() : { events: [] }))
        .then((d) => {
          const series = (d.events || [])
            .filter((e: any) => e.event_type === 'equity')
            .map((e: any) => Number(e.payload?.total ?? 0))
          setEquityByRun((prev) => ({ ...prev, [run.id]: series.length ? series : [0] }))
        })
        .catch(() => { /* transient */ })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs])

  // append live equity events into the grid series
  useEffect(() => {
    setEquityByRun((prev) => {
      const next = { ...prev }
      for (const [ridStr, events] of Object.entries(eventsByRun)) {
        const rid = Number(ridStr)
        const eqs = events.filter((e) => e.event_type === 'equity')
        if (!eqs.length) continue
        const base = prev[rid] || [0]
        const merged = base.concat(eqs.map((e) => Number(e.payload?.total ?? 0)))
        next[rid] = merged.length > 4096 ? merged.slice(merged.length - 4096) : merged
      }
      return next
    })
  }, [eventsByRun])

  async function act(id: number, action: string, body?: any) {
    setErr('')
    try {
      const r = await fetch(`${API_BASE}/runs/${id}/${action}`, {
        method: 'POST', headers: auth,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!r.ok) setErr((await r.json()).detail || `${action} failed`)
      await load()
    } catch { setErr('network error') }
  }

  async function del(id: number) {
    await fetch(`${API_BASE}/runs/${id}`, { method: 'DELETE', headers: auth })
    if (selected === id) setSelected(null)
    await load()
  }

  const T = {
    title: tr(language, { ko: '실시간 자동매매 런', en: 'Live Trading Runs',
      ja: 'ライブ自動売買', th: 'รันเทรดสด', vi: 'Phiên giao dịch trực tiếp' }),
    subtitle: tr(language, {
      ko: '서버에서 실행되는 각 AI 매매 런을 실시간으로 모니터링합니다. 가격 갱신 주기 특성상 표시된 데이터 나이(age)를 함께 확인하세요.',
      en: 'Each AI run executes on the server. Watch the data-age badge — polled markets update on an interval, not instantly.',
      ja: 'サーバー実行の各AIランを監視。ポーリング市場は間隔更新のため、データ経過時間に注意。',
      th: 'แต่ละรัน AI ทำงานบนเซิร์ฟเวอร์ ดูป้ายอายุข้อมูล — ตลาดแบบ poll อัปเดตตามช่วงเวลา',
      vi: 'Mỗi phiên AI chạy trên máy chủ. Xem nhãn tuổi dữ liệu — thị trường polling cập nhật theo chu kỳ.' }),
    newRun: tr(language, { ko: '새 런', en: 'New Run', ja: '新規', th: 'รันใหม่', vi: 'Phiên mới' }),
    empty: tr(language, { ko: '아직 런이 없습니다.', en: 'No runs yet.',
      ja: 'ランがありません。', th: 'ยังไม่มีรัน', vi: 'Chưa có phiên nào.' }),
    live: tr(language, { ko: '실시간', en: 'live', ja: 'ライブ', th: 'สด', vi: 'trực tiếp' }),
    offline: tr(language, { ko: '오프라인', en: 'offline', ja: 'オフライン', th: 'ออฟไลน์', vi: 'ngoại tuyến' }),
  }

  if (!token) {
    return <div className="page"><p className="muted">
      {tr(language, { ko: '에이전트 로그인이 필요합니다.', en: 'Agent login required.',
        ja: 'エージェントログインが必要です。', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập' })}
    </p></div>
  }

  return (
    <div className="page" style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>{T.title}</h1>
          <p className="muted" style={{ margin: '4px 0 0', maxWidth: 680, fontSize: 13 }}>
            {T.subtitle}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: connected ? '#0ca30c' : '#898781',
            display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 8,
              background: connected ? '#0ca30c' : '#898781', display: 'inline-block' }} />
            {connected ? T.live : T.offline}
          </span>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            + {T.newRun}
          </button>
        </div>
      </div>

      {err && <div style={{ color: '#d03b3b', marginTop: 10, fontSize: 13 }}>{err}</div>}

      {showCreate && (
        <CreateRunForm token={token} onDone={() => { setShowCreate(false); load() }}
          onCancel={() => setShowCreate(false)} language={language} />
      )}

      {runs.length === 0 && !showCreate && (
        <p className="muted" style={{ marginTop: 24 }}>{T.empty}</p>
      )}

      <div style={{ display: 'grid', gap: 12, marginTop: 18,
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {runs.map((run) => {
          const tick = tickByRun[run.id]
          const pnl = Number(run.realized_pnl_usd || 0)
          const pnlColor = pnl > 0 ? '#0ca30c' : pnl < 0 ? '#d03b3b' : 'var(--text-muted,#898781)'
          const ageTs = run.status === 'running' ? (tick?.ts || run.last_cycle_at) : run.last_cycle_at
          return (
            <div key={run.id}
              onClick={() => setSelected(run.id)}
              style={{ background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))',
                borderRadius: 12, padding: 14, cursor: 'pointer' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <strong style={{ fontSize: 15 }}>{run.symbol}
                  <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                    {run.market}{run.market_type === 'futures' ? ' · fut' : ''}</span>
                </strong>
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                  color: STATUS_COLOR[run.status] || '#898781' }}>{run.status}</span>
              </div>
              <div style={{ marginTop: 8 }}>
                <RunSparkline values={equityByRun[run.id] || [0]}
                  color={pnl < 0 ? 'rgb(208,59,59)' : 'rgb(12,163,12)'} height={44} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginTop: 8, fontSize: 12 }}>
                <span style={{ color: pnlColor, fontWeight: 600 }}>
                  {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>
                <span className="muted" title="last data update"
                  style={{ fontSize: 11 }}>⧗ {ageLabel(ageTs, language)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {selected !== null && (
        <RunDetail runId={selected} token={token}
          events={eventsByRun[selected] || []}
          tick={tickByRun[selected]}
          onClose={() => setSelected(null)}
          onAct={act} onDelete={del} language={language} />
      )}
    </div>
  )
}

function RunDetail({ runId, token, events, tick, onClose, onAct, onDelete, language }: {
  runId: number; token: string; events: any[]; tick: any
  onClose: () => void
  onAct: (id: number, action: string, body?: any) => void
  onDelete: (id: number) => void
  language: Language
}) {
  const [snap, setSnap] = useState<any>(null)
  const auth = { Authorization: `Bearer ${token}` }

  useEffect(() => {
    fetch(`${API_BASE}/runs/${runId}/snapshot`, { headers: auth })
      .then((r) => (r.ok ? r.json() : null)).then(setSnap).catch(() => setSnap(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, events.length])

  const equity = useMemo(() => {
    const base = (snap?.pnl ? [Number(snap.pnl.total || 0)] : [0])
    const live = events.filter((e) => e.event_type === 'equity')
      .map((e) => Number(e.payload?.total ?? 0))
    return base.concat(live)
  }, [snap, events])

  const run = snap?.run
  const status = run?.status
  const canStop = ['armed', 'running', 'paused'].includes(status)
  const log = events.slice().reverse().slice(0, 60)

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.45)', display: 'flex', justifyContent: 'flex-end', zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(560px, 100%)',
        height: '100%', overflowY: 'auto', background: 'var(--bg-primary,#fff)',
        borderLeft: '1px solid var(--border-color,rgba(0,0,0,0.1))', padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>
            {run ? `${run.symbol} · ${run.market}` : `Run #${runId}`}</h2>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        {run && (
          <div style={{ marginTop: 4, fontSize: 12, color: STATUS_COLOR[status] || '#898781',
            fontWeight: 600, textTransform: 'uppercase' }}>
            {status}{run.status_reason ? ` · ${run.status_reason}` : ''}
          </div>
        )}

        {snap?.pnl && (
          <div style={{ display: 'flex', gap: 18, marginTop: 12, fontSize: 13 }}>
            <div><span className="muted">P&amp;L </span>
              <strong style={{ color: snap.pnl.total >= 0 ? '#0ca30c' : '#d03b3b' }}>
                {snap.pnl.total >= 0 ? '+' : ''}${Number(snap.pnl.total).toFixed(2)}</strong></div>
            <div><span className="muted">
              {tr(language, { ko: '실현', en: 'realized', ja: '実現', th: 'รับรู้', vi: 'đã chốt' })} </span>
              ${Number(snap.pnl.realized).toFixed(2)}</div>
            <div><span className="muted">
              {tr(language, { ko: '거래', en: 'trades', ja: '取引', th: 'ดีล', vi: 'lệnh' })} </span>
              {snap.pnl.trades}</div>
            {tick && <div><span className="muted">
              {tr(language, { ko: '현재가', en: 'mark', ja: '価格', th: 'ราคา', vi: 'giá' })} </span>
              ${Number(tick.price).toFixed(2)}</div>}
          </div>
        )}

        <div style={{ marginTop: 14, background: 'var(--bg-card,#fafafa)',
          border: '1px solid var(--border-color,rgba(0,0,0,0.08))', borderRadius: 10, padding: 8 }}>
          <RunSparkline values={equity}
            color={(snap?.pnl?.total ?? 0) < 0 ? 'rgb(208,59,59)' : 'rgb(12,163,12)'}
            height={120} />
        </div>

        {canStop && (
          <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
            {status === 'running' &&
              <button className="btn" onClick={() => onAct(runId, 'pause')}>
                {tr(language, { ko: '일시정지', en: 'Pause', ja: '一時停止', th: 'พัก', vi: 'Tạm dừng' })}</button>}
            {status === 'paused' &&
              <button className="btn" onClick={() => onAct(runId, 'resume')}>
                {tr(language, { ko: '재개', en: 'Resume', ja: '再開', th: 'ต่อ', vi: 'Tiếp tục' })}</button>}
            <button className="btn" style={{ color: '#eb6834' }}
              onClick={() => onAct(runId, 'stop', { flatten: true })}>
              {tr(language, { ko: '정지+청산', en: 'Stop & flatten', ja: '停止+清算',
                th: 'หยุด+ปิด', vi: 'Dừng + đóng' })}</button>
            <button className="btn"
              onClick={() => onAct(runId, 'stop', { flatten: false })}>
              {tr(language, { ko: '정지+보유', en: 'Stop & hold', ja: '停止+保有',
                th: 'หยุด+ถือ', vi: 'Dừng + giữ' })}</button>
          </div>
        )}
        {['draft', 'stopped'].includes(status) &&
          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            {status === 'draft' &&
              <button className="btn btn-primary" onClick={() => onAct(runId, 'start')}>
                {tr(language, { ko: '시작', en: 'Start', ja: '開始', th: 'เริ่ม', vi: 'Bắt đầu' })}</button>}
            <button className="btn" style={{ color: '#d03b3b' }} onClick={() => onDelete(runId)}>
              {tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa' })}</button>
          </div>}

        <h3 style={{ fontSize: 13, marginTop: 20, marginBottom: 6 }}>
          {tr(language, { ko: '이벤트 로그', en: 'Event log', ja: 'イベントログ',
            th: 'บันทึกเหตุการณ์', vi: 'Nhật ký sự kiện' })}</h3>
        <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11.5, lineHeight: 1.7 }}>
          {log.length === 0 && <span className="muted">—</span>}
          {log.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 8 }}>
              <span className="muted" style={{ minWidth: 62 }}>{e.ts?.slice(11, 19)}</span>
              <span style={{ minWidth: 74, color: e.event_type === 'trade' ? '#0ca30c'
                : e.event_type === 'run_status' ? '#2a78d6' : '#898781' }}>{e.event_type}</span>
              <span style={{ opacity: 0.85 }}>{summarize(e)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function summarize(e: any): string {
  const p = e.payload || {}
  if (e.event_type === 'run_status') return `${p.from ?? ''} → ${p.to ?? ''} (${p.reason ?? ''})`
  if (e.event_type === 'trade') return `${p.side} ${Number(p.quantity).toFixed(4)} @ $${Number(p.price).toFixed(2)}`
  if (e.event_type === 'decision') return `${p.action ?? '—'} conf ${p.confidence ?? '—'}`
  if (e.event_type === 'equity') return `total $${Number(p.total).toFixed(2)}`
  if (e.event_type === 'gate_skip') return `${p.stage}: ${p.reason}`
  if (e.event_type === 'alert') return p.stop_reason ?? JSON.stringify(p)
  return JSON.stringify(p).slice(0, 80)
}

function CreateRunForm({ token, onDone, onCancel, language }: {
  token: string; onDone: () => void; onCancel: () => void; language: Language
}) {
  const [f, setF] = useState({
    symbol: 'BTC', market: 'crypto', market_type: 'spot',
    max_bet_usd: 500, interval_minutes: 60, min_confidence: 0.65,
    stop_loss_usd: '', profit_target_usd: '',
    report_frequency: 'off', notify_on_trade: false,
  })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const auth = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

  async function submit() {
    setErr(''); setBusy(true)
    const stop: any = {}
    if (f.stop_loss_usd) stop.max_loss_usd = Number(f.stop_loss_usd)
    if (f.profit_target_usd) stop.profit_target_usd = Number(f.profit_target_usd)
    try {
      const r = await fetch(`${API_BASE}/runs`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({
          symbol: f.symbol, market: f.market, market_type: f.market_type,
          max_bet_usd: Number(f.max_bet_usd),
          interval_minutes: Number(f.interval_minutes),
          min_confidence: Number(f.min_confidence),
          stop_conditions: stop,
        }),
      })
      const d = await r.json()
      if (!r.ok) { setErr(d.detail || 'create failed'); setBusy(false); return }
      const runId = d.id
      if (f.report_frequency !== 'off' || f.notify_on_trade) {
        await fetch(`${API_BASE}/runs/${runId}/reporting`, {
          method: 'PUT', headers: auth,
          body: JSON.stringify({ report_frequency: f.report_frequency,
            notify_on_trade: f.notify_on_trade }),
        })
      }
      onDone()
    } catch { setErr('network error'); setBusy(false) }
  }

  const lbl = (o: any) => tr(language, o)
  const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }
  const input: React.CSSProperties = { padding: '6px 8px', borderRadius: 6,
    border: '1px solid var(--border-color,rgba(0,0,0,0.15))', background: 'var(--bg-card,#fff)',
    color: 'var(--text-primary,#111)' }

  return (
    <div style={{ marginTop: 16, background: 'var(--bg-card,#fff)',
      border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 16 }}>
      <div style={{ display: 'grid', gap: 12,
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <label style={field}>{lbl({ ko: '심볼', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' })}
          <input style={input} value={f.symbol}
            onChange={(e) => setF({ ...f, symbol: e.target.value.toUpperCase() })} /></label>
        <label style={field}>{lbl({ ko: '시장', en: 'Market', ja: '市場', th: 'ตลาด', vi: 'Thị trường' })}
          <select style={input} value={f.market}
            onChange={(e) => setF({ ...f, market: e.target.value })}>
            <option value="crypto">crypto</option><option value="us-stock">us-stock</option>
          </select></label>
        <label style={field}>{lbl({ ko: '유형', en: 'Type', ja: 'タイプ', th: 'ชนิด', vi: 'Loại' })}
          <select style={input} value={f.market_type}
            onChange={(e) => setF({ ...f, market_type: e.target.value })}>
            <option value="spot">spot</option>
            <option value="futures" disabled={f.market !== 'crypto'}>futures</option>
          </select></label>
        <label style={field}>{lbl({ ko: '최대 베팅($)', en: 'Max bet ($)', ja: '最大($)', th: 'เดิมพันสูงสุด', vi: 'Cược tối đa' })}
          <input style={input} type="number" value={f.max_bet_usd}
            onChange={(e) => setF({ ...f, max_bet_usd: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '주기(분)', en: 'Interval (min)', ja: '間隔(分)', th: 'ช่วง(นาที)', vi: 'Chu kỳ (phút)' })}
          <input style={input} type="number" min={5} value={f.interval_minutes}
            onChange={(e) => setF({ ...f, interval_minutes: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '최소 신뢰도', en: 'Min confidence', ja: '最小信頼度', th: 'ความมั่นใจ', vi: 'Độ tin tối thiểu' })}
          <input style={input} type="number" step={0.05} min={0} max={1} value={f.min_confidence}
            onChange={(e) => setF({ ...f, min_confidence: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '손절($)', en: 'Stop loss ($)', ja: '損切り($)', th: 'ตัดขาดทุน', vi: 'Cắt lỗ ($)' })}
          <input style={input} type="number" value={f.stop_loss_usd}
            onChange={(e) => setF({ ...f, stop_loss_usd: e.target.value })} /></label>
        <label style={field}>{lbl({ ko: '익절($)', en: 'Profit target ($)', ja: '利確($)', th: 'เป้ากำไร', vi: 'Chốt lời ($)' })}
          <input style={input} type="number" value={f.profit_target_usd}
            onChange={(e) => setF({ ...f, profit_target_usd: e.target.value })} /></label>
        <label style={field}>{lbl({ ko: '리포트', en: 'Reports', ja: 'レポート', th: 'รายงาน', vi: 'Báo cáo' })}
          <select style={input} value={f.report_frequency}
            onChange={(e) => setF({ ...f, report_frequency: e.target.value })}>
            <option value="off">off</option><option value="hourly">hourly</option>
            <option value="daily">daily</option><option value="weekly">weekly</option>
          </select></label>
        <label style={{ ...field, flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 18 }}>
          <input type="checkbox" checked={f.notify_on_trade}
            onChange={(e) => setF({ ...f, notify_on_trade: e.target.checked })} />
          {lbl({ ko: '체결 알림', en: 'Alert on trade', ja: '取引通知', th: 'แจ้งเมื่อเทรด', vi: 'Báo khi giao dịch' })}
        </label>
      </div>
      {err && <div style={{ color: '#d03b3b', marginTop: 10, fontSize: 12 }}>{err}</div>}
      <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
        {tr(language, {
          ko: '런은 서버에서 백그라운드로 실행되며 페이퍼(시뮬레이터) 계정으로 체결됩니다. 미국 주식은 가격 갱신 주기 특성상 정지 조건이 수 분 지연될 수 있습니다.',
          en: 'Runs execute server-side on the paper (simulator) account. US-stock stops evaluate on minutes-old marks due to the price-poll interval.',
          ja: 'ランはサーバー側でペーパー口座で執行。米国株は価格ポーリングのため停止条件が数分遅延することがあります。',
          th: 'รันทำงานฝั่งเซิร์ฟเวอร์บนบัญชีจำลอง หุ้นสหรัฐฯ เงื่อนไขหยุดอาจช้าไม่กี่นาที',
          vi: 'Phiên chạy phía máy chủ trên tài khoản mô phỏng. Cổ phiếu Mỹ có thể trễ vài phút do chu kỳ polling giá.' })}
      </p>
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary" disabled={busy} onClick={submit}>
          {tr(language, { ko: '런 생성', en: 'Create run', ja: '作成', th: 'สร้าง', vi: 'Tạo' })}</button>
        <button className="btn" onClick={onCancel}>
          {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy' })}</button>
      </div>
    </div>
  )
}

export default RunsLivePage
