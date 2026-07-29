import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../appShared'
import { Language, tr } from '../i18n'

// Live SVG flowchart of the AI Analyst pipeline, styled like the boxed
// diagrams in docs/design/ai-trading-guide.html (§0 "10단계 파이프라인"):
// rounded step cards with title + status line, arrow markers, and a bus that
// converges the four briefs into the decision box.
// Mirrors the real step events streamed from /api/analysis/run/stream:
//   gather:news|sentiment|fundamentals_macro|technical  (run concurrently)
//   brief:news|sentiment|fundamentals_macro|technical   (run concurrently)
//   decision -> verify
// Card states: pending (dim), running (pulsing accent + flowing edge),
// done (accent + duration), error (red). No green anywhere — the guide
// diagrams reserve color for accent/critical only, and the diagram is
// width-capped so boxes stay at the guide's compact scale on wide screens.

export type StepStatus = 'pending' | 'running' | 'done' | 'error'
export type StepInfo = { status: StepStatus; runs: number; startedAt?: number; endedAt?: number }
export type LogEntry = { ts: string; step: string; status: string; detail?: string }

export const PIPELINE_STEPS = [
  'gather:news', 'gather:sentiment', 'gather:fundamentals_macro', 'gather:technical',
  'brief:news', 'brief:sentiment', 'brief:fundamentals_macro', 'brief:technical',
  'decision', 'verify',
] as const

const ROLES = ['news', 'sentiment', 'fundamentals_macro', 'technical'] as const

// Guide palette tokens (docs/design/ai-trading-guide.html :root) — scoped to
// the diagram via .plv-wrap custom props. Running = accent blue like the
// guide's active-step boxes; done = --good; error = --critical.
const ST_COLOR: Record<StepStatus, string> = {
  pending: 'var(--g-baseline)',
  running: 'var(--g-accent)',
  done: 'var(--g-accent)',
  error: 'var(--g-crit)',
}

// Geometry (viewBox 960 wide, box sizes/radii per the guide diagrams —
// rows slimmed to the guide's height:width proportion).
const COL_X = [12, 252, 492, 732]          // 4 role columns
const COL_W = 216
const cx = (i: number) => COL_X[i] + COL_W / 2
const GATHER_Y = 22, BRIEF_Y = 116, ROW_H = 46
const BUS_Y = 196
const DEC = { x: 290, y: 222, w: 380, h: 52 }
const VER = { x: 360, y: 312, w: 240, h: 46 }
const VIEW_H = 372

function StepCard({ x, y, w, h, title, stepId, info, labels }: {
  x: number; y: number; w: number; h: number
  title: string; stepId: string; info?: StepInfo; labels: Record<string, string>
}) {
  const status = info?.status || 'pending'
  const dur = info?.startedAt && info?.endedAt
    ? (info.endedAt - info.startedAt >= 1000
        ? `${((info.endedAt - info.startedAt) / 1000).toFixed(1)}s`
        : `${Math.max(1, Math.round(info.endedAt - info.startedAt))}ms`)
    : null
  const statusLine =
    status === 'running' ? labels.__running
    : status === 'error' ? `✗ ${labels.__error}`
    : status === 'done' ? `✓ ${labels.__done}` + (dur ? ` · ${dur}` : '')
    : null
  const midX = x + w / 2
  return (
    <g className={`plv-card plv-${status}`}>
      <rect x={x} y={y} width={w} height={h} rx={8} className="plv-box" />
      <text x={midX} y={y + 16} textAnchor="middle" className="plv-t"
        opacity={status === 'pending' ? 0.55 : 1}>
        {title}
        {(info?.runs ?? 0) > 1 && <tspan fill="var(--g-accent)"> ×{info!.runs}</tspan>}
      </text>
      {statusLine && (
        <text x={midX} y={y + 29} textAnchor="middle" className="plv-s" fill={ST_COLOR[status]}>
          {statusLine}
        </text>
      )}
      <text x={midX} y={y + h - 7} textAnchor="middle" className="plv-m">{stepId}</text>
    </g>
  )
}

// Edge color: accent + flowing dashes while the downstream step runs (like
// the guide's accent arrows), good/critical once resolved, baseline otherwise.
function edgeState(up?: StepInfo, down?: StepInfo): { color: string; flow: boolean } {
  const su = up?.status || 'pending'; const sd = down?.status || 'pending'
  if (sd === 'running') return { color: ST_COLOR.running, flow: true }
  if (su === 'done' && (sd === 'done' || sd === 'error')) return { color: ST_COLOR[sd], flow: false }
  return { color: 'var(--g-baseline)', flow: false }
}

export function AnalysisPipelineViz({ steps, labels }: {
  steps: Record<string, StepInfo>
  labels: Record<string, string>
}) {
  const marker = (id: string, color: string) => (
    <marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
      orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill={color} />
    </marker>
  )
  const markerFor = (color: string) =>
    color === ST_COLOR.running ? 'url(#plv-ar-run)'
    : color === ST_COLOR.error ? 'url(#plv-ar-err)'
    : 'url(#plv-ar)'

  const edge = (key: string, d: string, state: { color: string; flow: boolean }, arrow = true) => (
    <path key={key} d={d} fill="none" stroke={state.color}
      strokeWidth={state.color === 'var(--g-baseline)' ? 1.4 : 1.6}
      className={state.flow ? 'plv-flow' : undefined}
      strokeDasharray={state.flow ? '6 5' : undefined}
      markerEnd={arrow ? markerFor(state.color) : undefined} />
  )

  const dec = steps['decision']; const ver = steps['verify']
  return (
    <div className="plv-wrap" style={{ width: '100%', borderRadius: 14,
                  border: '1px solid var(--g-border)', background: 'var(--g-card)',
                  padding: 14, overflowX: 'auto' }}>
      <svg viewBox={`0 0 960 ${VIEW_H}`}
        style={{ display: 'block', minWidth: 680, width: '100%', maxWidth: 980,
                 margin: '0 auto', height: 'auto' }}
        xmlns="http://www.w3.org/2000/svg" role="img" aria-label={labels.__pipeline}>
        <style>{`
          /* Guide palette (docs/design/ai-trading-guide.html :root) — dark by
             default (app themes signal/claude), light values under light. */
          .plv-wrap {
            --g-card:#202020; --g-surface:#1a1a19; --g-border:rgba(255,255,255,0.10);
            --g-baseline:#383835; --g-ink:#fff; --g-ink2:#c3c2b7; --g-muted:#898781;
            --g-accent:#3987e5; --g-crit:#d03b3b; --g-yellow:#c98500;
          }
          :root[data-theme='light'] .plv-wrap {
            --g-card:#ffffff; --g-surface:#f1f0ec; --g-border:rgba(11,11,11,0.10);
            --g-baseline:#c3c2b7; --g-ink:#0b0b0b; --g-ink2:#52514e; --g-muted:#898781;
            --g-accent:#2a78d6; --g-crit:#d03b3b; --g-yellow:#eda100;
          }
          .plv-t { font: 600 11.5px system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif; fill: var(--g-ink); }
          .plv-s { font: 500 10px system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif; }
          .plv-m { font: 600 9.5px ui-monospace,"SF Mono",Menlo,monospace; fill: var(--g-muted); }
          .plv-pending .plv-box { fill: var(--g-surface); stroke: var(--g-border); stroke-width: 1; }
          .plv-running .plv-box { fill: color-mix(in srgb, var(--g-accent) 12%, var(--g-card)); stroke: var(--g-accent); stroke-width: 1.6;
                                  animation: plv-pulse 1.4s ease-in-out infinite; }
          .plv-done .plv-box { fill: color-mix(in srgb, var(--g-accent) 8%, var(--g-card)); stroke: var(--g-accent); stroke-width: 1.2; }
          .plv-error .plv-box { fill: color-mix(in srgb, var(--g-crit) 10%, var(--g-card)); stroke: var(--g-crit); stroke-width: 1.6; }
          .plv-done .plv-s { fill: var(--g-accent); }
          .plv-flow { animation: plv-dash 0.9s linear infinite; }
          @keyframes plv-pulse { 0%,100% { stroke-opacity: 1 } 50% { stroke-opacity: 0.35 } }
          @keyframes plv-dash { to { stroke-dashoffset: -11 } }
        `}</style>
        <defs>
          {marker('plv-ar', 'var(--g-baseline)')}
          {marker('plv-ar-run', ST_COLOR.running)}
          {marker('plv-ar-err', ST_COLOR.error)}
        </defs>

        {/* band 1: gather */}
        {ROLES.map((r, i) => (
          <StepCard key={`g${r}`} x={COL_X[i]} y={GATHER_Y} w={COL_W} h={ROW_H} stepId={`gather:${r}`}
            title={labels[`gather:${r}`] || `gather:${r}`} info={steps[`gather:${r}`]} labels={labels} />
        ))}

        {/* gather -> brief */}
        {ROLES.map((r, i) => edge(
          `e-gb-${r}`,
          `M${cx(i)} ${GATHER_Y + ROW_H} V${BRIEF_Y - 2}`,
          edgeState(steps[`gather:${r}`], steps[`brief:${r}`]),
        ))}

        {/* band 2: brief */}
        {ROLES.map((r, i) => (
          <StepCard key={`b${r}`} x={COL_X[i]} y={BRIEF_Y} w={COL_W} h={ROW_H} stepId={`brief:${r}`}
            title={labels[`brief:${r}`] || `brief:${r}`} info={steps[`brief:${r}`]} labels={labels} />
        ))}

        {/* brief -> bus -> decision */}
        {ROLES.map((r, i) => edge(
          `e-bd-${r}`,
          `M${cx(i)} ${BRIEF_Y + ROW_H} V${BUS_Y}`,
          edgeState(steps[`brief:${r}`], dec), false,
        ))}
        <path d={`M${cx(0)} ${BUS_Y} H${cx(3)}`} fill="none"
          stroke={dec?.status === 'running' ? ST_COLOR.running : 'var(--g-baseline)'} strokeWidth={1.4} />
        {edge('e-bus-dec', `M480 ${BUS_Y} V${DEC.y - 2}`,
          { color: dec?.status === 'running' ? ST_COLOR.running : dec?.status === 'done' ? ST_COLOR.done : dec?.status === 'error' ? ST_COLOR.error : 'var(--g-baseline)', flow: dec?.status === 'running' })}

        {/* band 3: decision */}
        <StepCard x={DEC.x} y={DEC.y} w={DEC.w} h={DEC.h} stepId="decision"
          title={labels['decision'] || 'decision'} info={dec} labels={labels} />

        {/* decision -> verify */}
        {edge('e-dec-ver', `M480 ${DEC.y + DEC.h} V${VER.y - 2}`, edgeState(dec, ver))}

        {/* band 4: verify */}
        <StepCard x={VER.x} y={VER.y} w={VER.w} h={VER.h} stepId="verify"
          title={labels['verify'] || 'verify'} info={ver} labels={labels} />
      </svg>
    </div>
  )
}

// ── Shared step labels (localized) ──

export function analysisStepLabels(language: Language): Record<string, string> {
  const gather = tr(language, { ko: '수집', en: 'Gather', ja: '収集', th: 'รวบรวม', vi: 'Thu thập', id: 'Kumpulkan' })
  const brief = tr(language, { ko: '브리프', en: 'Brief', ja: 'ブリーフ', th: 'สรุป', vi: 'Tóm tắt', id: 'Ringkasan' })
  const roles: Record<string, string> = {
    news: tr(language, { ko: '뉴스', en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức', id: 'Berita' }),
    sentiment: tr(language, { ko: '심리', en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý', id: 'Sentimen' }),
    fundamentals_macro: tr(language, { ko: '펀더멘털 & 매크로', en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô', id: 'Fundamental & Makro' }),
    technical: tr(language, { ko: '기술적 분석', en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật', id: 'Teknikal' }),
  }
  const labels: Record<string, string> = {
    decision: tr(language, { ko: '트레이더+리스크 결정', en: 'Trader + Risk decision', ja: 'トレーダー+リスク判断', th: 'ตัดสินใจเทรด+ความเสี่ยง', vi: 'Quyết định Trader + Rủi ro', id: 'Keputusan trader + risiko' }),
    verify: tr(language, { ko: '검증', en: 'Verify', ja: '検証', th: 'ตรวจสอบ', vi: 'Xác minh', id: 'Verifikasi' }),
    __running: tr(language, { ko: '실행 중', en: 'running', ja: '実行中', th: 'กำลังทำงาน', vi: 'đang chạy', id: 'berjalan' }),
    __error: tr(language, { ko: '오류', en: 'error', ja: 'エラー', th: 'ผิดพลาด', vi: 'lỗi', id: 'galat' }),
    __start: tr(language, { ko: '시작', en: 'start', ja: '開始', th: 'เริ่ม', vi: 'bắt đầu', id: 'mulai' }),
    __done: tr(language, { ko: '완료', en: 'done', ja: '完了', th: 'เสร็จ', vi: 'xong', id: 'selesai' }),
    __pipeline: tr(language, { ko: '실시간 파이프라인 모니터', en: 'Live pipeline monitor', ja: 'リアルタイム・パイプライン', th: 'มอนิเตอร์ไปป์ไลน์สด', vi: 'Giám sát pipeline trực tiếp', id: 'Monitor alur langsung' }),
    __stepLog: tr(language, { ko: '단계 로그', en: 'Step log', ja: 'ステップログ', th: 'บันทึกขั้นตอน', vi: 'Nhật ký bước', id: 'Catatan langkah' }),
  }
  for (const role of Object.keys(roles)) {
    labels[`gather:${role}`] = `${gather} · ${roles[role]}`
    labels[`brief:${role}`] = `${brief} · ${roles[role]}`
  }
  return labels
}

// ── Shared streaming runner ──
// Consumes POST /api/analysis/run/stream (SSE) and tracks step/log/result state.
// Falls back to the one-shot /api/analysis/run on servers without the endpoint.

export function useAnalysisStream(token: string | null) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [steps, setSteps] = useState<Record<string, StepInfo>>({})
  const [log, setLog] = useState<LogEntry[]>([])
  // Automation test-run verdict: {would_execute, skip_reason, quantity, ...}
  const [gates, setGates] = useState<any>(null)

  function applyStepEvent(evt: any) {
    const now = performance.now()
    setSteps(prev => {
      const cur: StepInfo = prev[evt.step] || { status: 'pending', runs: 0 }
      const next: StepInfo = { ...cur }
      if (evt.status === 'start') {
        next.status = 'running'; next.runs = cur.runs + 1; next.startedAt = now; next.endedAt = undefined
      } else if (evt.status === 'done') {
        next.status = 'done'; next.endedAt = now
      } else if (evt.status === 'error') {
        next.status = 'error'; next.endedAt = now
      }
      return { ...prev, [evt.step]: next }
    })
    const extras = Object.entries(evt)
      .filter(([k]) => !['step', 'status', 'ts', 'event'].includes(k))
      .map(([k, v]) => `${k}=${v}`).join(' ')
    setLog(prev => [...prev, { ts: evt.ts, step: evt.step, status: evt.status, detail: extras || undefined }])
  }

  async function run(symbol: string, market: string, lang: string,
                     provider?: string | null, configId?: number | null) {
    if (!token) return
    setLoading(true); setError(''); setResult(null); setLog([]); setGates(null)
    setSteps(Object.fromEntries(PIPELINE_STEPS.map(s => [s, { status: 'pending', runs: 0 }])))
    const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }
    const body = JSON.stringify({ symbol, market, lang, provider: provider || null,
                                  config_id: configId || null })
    const runPlain = async () => {
      const res = await fetch(`${API_BASE}/analysis/run`, { method: 'POST', headers, body })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Analysis failed')
      setResult(data)
    }
    try {
      const res = await fetch(`${API_BASE}/analysis/run/stream`, { method: 'POST', headers, body })
      if (res.status === 404 || res.status === 405) { await runPlain(); setLoading(false); return }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error((data as any).detail || 'Analysis failed')
      }
      if (!res.body) { await runPlain(); setLoading(false); return }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let sawFinal = false
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let i
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2)
          const line = chunk.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          const evt = JSON.parse(line.slice(6))
          if (evt.event === 'step') applyStepEvent(evt)
          else if (evt.event === 'gates') setGates(evt)
          else if (evt.event === 'result') { setResult(evt.result); sawFinal = true }
          else if (evt.event === 'error') { setError(evt.detail || 'Analysis failed'); sawFinal = true }
        }
      }
      if (!sawFinal) throw new Error('Stream ended unexpectedly')
    } catch (e: any) { setError(e.message || 'Analysis failed') }
    setLoading(false)
  }

  return { loading, result, error, steps, log, gates, run }
}

// ── Background-job runner (Analyst page) ──
// The pipeline executes server-side (POST /api/analysis/jobs) in a daemon
// thread detached from this tab; we poll GET /api/analysis/jobs/current so
// the member can leave the page mid-run and re-attach when they come back.

export type RunInfo = { id: number; symbol: string; market: string; created_at?: string }

export function useAnalysisRun(token: string | null) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [steps, setSteps] = useState<Record<string, StepInfo>>({})
  const [log, setLog] = useState<LogEntry[]>([])
  const [runInfo, setRunInfo] = useState<RunInfo | null>(null)
  const genRef = useRef(0) // bump to cancel any in-flight poll loop

  const authHeaders = () => ({ 'Authorization': `Bearer ${token}` })

  // Rebuild the full monitor state from the job's persisted event list.
  function applyJob(job: any): string {
    const next: Record<string, StepInfo> =
      Object.fromEntries(PIPELINE_STEPS.map(s => [s, { status: 'pending', runs: 0 }]))
    const entries: LogEntry[] = []
    for (const evt of job.events || []) {
      const t = Date.parse(evt.ts || '') || undefined
      const cur: StepInfo = next[evt.step] || { status: 'pending', runs: 0 }
      if (evt.status === 'start') {
        cur.status = 'running'; cur.runs += 1; cur.startedAt = t; cur.endedAt = undefined
      } else if (evt.status === 'done') { cur.status = 'done'; cur.endedAt = t }
      else if (evt.status === 'error') { cur.status = 'error'; cur.endedAt = t }
      next[evt.step] = cur
      const extras = Object.entries(evt)
        .filter(([k]) => !['step', 'status', 'ts', 'event'].includes(k))
        .map(([k, v]) => `${k}=${v}`).join(' ')
      entries.push({ ts: evt.ts, step: evt.step, status: evt.status, detail: extras || undefined })
    }
    setSteps(next); setLog(entries)
    setRunInfo({ id: job.job_id, symbol: job.symbol, market: job.market, created_at: job.created_at })
    setResult(job.result || null)
    setError(job.status === 'error' ? (job.error || 'Analysis failed') : '')
    setLoading(job.status === 'running')
    return job.status
  }

  async function poll(gen: number) {
    for (;;) {
      if (gen !== genRef.current) return
      try {
        const res = await fetch(`${API_BASE}/analysis/jobs/current`, { headers: authHeaders() })
        if (res.status === 401 || res.status === 403) {
          if (gen === genRef.current) setLoading(false)
          return
        }
        if (res.ok) {
          const data = await res.json()
          if (gen !== genRef.current) return
          if (!data.job) { setLoading(false); return }
          if (applyJob(data.job) !== 'running') return
        }
        // other statuses (5xx during a deploy, etc.) — keep polling
      } catch { /* transient network error — keep polling */ }
      await new Promise(r => setTimeout(r, 2000))
    }
  }

  async function run(symbol: string, market: string, lang: string) {
    if (!token) return
    const gen = ++genRef.current
    setLoading(true); setError(''); setResult(null); setLog([])
    setSteps(Object.fromEntries(PIPELINE_STEPS.map(s => [s, { status: 'pending', runs: 0 }])))
    try {
      const res = await fetch(`${API_BASE}/analysis/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ symbol, market, lang }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error((data as any).detail || 'Analysis failed')
      poll(gen)
    } catch (e: any) {
      if (gen === genRef.current) { setError(e.message || 'Analysis failed'); setLoading(false) }
    }
  }

  // On mount: re-attach to the member's most recent job (live or finished).
  useEffect(() => {
    if (!token) return
    const gen = ++genRef.current
    poll(gen)
    return () => { genRef.current++ }
  }, [token])

  return { loading, result, error, steps, log, runInfo, run }
}

// ── Shared monitor panel: flowchart + timestamped step log ──

export function AnalysisMonitorPanel({ language, steps, log }: {
  language: Language
  steps: Record<string, StepInfo>
  log: LogEntry[]
}) {
  const labels = analysisStepLabels(language)
  if (log.length === 0) return null
  return (
    <>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 10 }}>
        {labels.__pipeline}
      </div>
      <AnalysisPipelineViz steps={steps} labels={labels} />
      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 6 }}>
          {labels.__stepLog}
        </div>
        <div style={{ maxHeight: 180, overflowY: 'auto', fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 11.5, lineHeight: 1.7 }}>
          {log.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
              <span style={{ color: 'var(--text-secondary,#8a8073)' }}>{(e.ts || '').slice(11, 23)}</span>
              <span style={{ width: 14, textAlign: 'center' }}>
                {e.status === 'start' ? '▶' : e.status === 'done' ? '✓' : '✗'}
              </span>
              <span style={{ color: e.status === 'error' ? '#f0663f' : e.status === 'done' ? '#3987e5' : 'var(--text-primary,inherit)' }}>
                {labels[e.step] || e.step} — {e.status === 'start' ? labels.__start : e.status === 'done' ? labels.__done : labels.__error}
              </span>
              {e.detail && <span style={{ color: 'var(--text-secondary,#8a8073)' }}>{e.detail}</span>}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

export default AnalysisPipelineViz
