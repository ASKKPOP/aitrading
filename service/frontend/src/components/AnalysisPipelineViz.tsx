import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../appShared'
import { Language, tr } from '../i18n'

// Live WebGL2 visualization of the AI Analyst pipeline.
// Mirrors the real step events streamed from /api/analysis/run/stream:
//   gather:news|sentiment|fundamentals_macro|technical  (run concurrently)
//   brief:news|sentiment|fundamentals_macro|technical   (run concurrently)
//   decision -> verify
// Node states: pending (dim), running (pulsing amber), done (green), error (red).
// Particles flow along an edge while its downstream step is running.

export type StepStatus = 'pending' | 'running' | 'done' | 'error'
export type StepInfo = { status: StepStatus; runs: number; startedAt?: number; endedAt?: number }
export type LogEntry = { ts: string; step: string; status: string; detail?: string }

export const PIPELINE_STEPS = [
  'gather:news', 'gather:sentiment', 'gather:fundamentals_macro', 'gather:technical',
  'brief:news', 'brief:sentiment', 'brief:fundamentals_macro', 'brief:technical',
  'decision', 'verify',
] as const

const NODES: { id: string; x: number; y: number }[] = [
  { id: 'gather:news', x: 0.13, y: 0.14 },
  { id: 'gather:sentiment', x: 0.13, y: 0.38 },
  { id: 'gather:fundamentals_macro', x: 0.13, y: 0.62 },
  { id: 'gather:technical', x: 0.13, y: 0.86 },
  { id: 'brief:news', x: 0.44, y: 0.14 },
  { id: 'brief:sentiment', x: 0.44, y: 0.38 },
  { id: 'brief:fundamentals_macro', x: 0.44, y: 0.62 },
  { id: 'brief:technical', x: 0.44, y: 0.86 },
  { id: 'decision', x: 0.70, y: 0.5 },
  { id: 'verify', x: 0.90, y: 0.5 },
]

const EDGES: [string, string][] = [
  ['gather:news', 'gather:sentiment'],
  ['gather:news', 'brief:news'],
  ['gather:sentiment', 'brief:sentiment'],
  ['gather:fundamentals_macro', 'brief:fundamentals_macro'],
  ['gather:technical', 'brief:technical'],
  ['brief:news', 'decision'],
  ['brief:sentiment', 'decision'],
  ['brief:fundamentals_macro', 'decision'],
  ['brief:technical', 'decision'],
  ['decision', 'verify'],
]

const COLORS: Record<StepStatus, [number, number, number]> = {
  pending: [0.42, 0.39, 0.34],
  running: [0.96, 0.65, 0.14],
  done: [0.25, 0.73, 0.31],
  error: [0.94, 0.40, 0.25],
}

const POINT_VS = `#version 300 es
in vec2 a_pos; in float a_size; in vec3 a_color; in float a_glow;
uniform vec2 u_res;
out vec3 v_color; out float v_glow;
void main() {
  gl_Position = vec4((a_pos / u_res * 2.0 - 1.0) * vec2(1.0, -1.0), 0.0, 1.0);
  gl_PointSize = a_size;
  v_color = a_color; v_glow = a_glow;
}`

const POINT_FS = `#version 300 es
precision mediump float;
in vec3 v_color; in float v_glow;
out vec4 o;
void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float d = length(p);
  if (d > 1.0) discard;
  float core = smoothstep(0.48, 0.40, d);
  float ring = smoothstep(0.07, 0.0, abs(d - 0.60));
  float halo = (1.0 - d) * (1.0 - d) * v_glow * 0.6;
  float a = max(max(core, ring * 0.85), halo);
  o = vec4(v_color * a, a);
}`

const LINE_VS = `#version 300 es
in vec2 a_pos; in vec4 a_color;
uniform vec2 u_res;
out vec4 v_color;
void main() {
  gl_Position = vec4((a_pos / u_res * 2.0 - 1.0) * vec2(1.0, -1.0), 0.0, 1.0);
  v_color = a_color;
}`

const LINE_FS = `#version 300 es
precision mediump float;
in vec4 v_color;
out vec4 o;
void main() { o = vec4(v_color.rgb * v_color.a, v_color.a); }`

function compile(gl: WebGL2RenderingContext, vsSrc: string, fsSrc: string): WebGLProgram | null {
  const mk = (type: number, src: string) => {
    const s = gl.createShader(type)!
    gl.shaderSource(s, src); gl.compileShader(s)
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) return null
    return s
  }
  const vs = mk(gl.VERTEX_SHADER, vsSrc); const fs = mk(gl.FRAGMENT_SHADER, fsSrc)
  if (!vs || !fs) return null
  const p = gl.createProgram()!
  gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return null
  return p
}

export function AnalysisPipelineViz({ steps, labels }: {
  steps: Record<string, StepInfo>
  labels: Record<string, string>
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const stepsRef = useRef(steps)
  stepsRef.current = steps
  const failedRef = useRef(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: true })
    if (!gl) { failedRef.current = true; return }

    const pointProg = compile(gl, POINT_VS, POINT_FS)
    const lineProg = compile(gl, LINE_VS, LINE_FS)
    if (!pointProg || !lineProg) { failedRef.current = true; return }

    const pointBuf = gl.createBuffer()
    const lineBuf = gl.createBuffer()
    const pRes = gl.getUniformLocation(pointProg, 'u_res')
    const lRes = gl.getUniformLocation(lineProg, 'u_res')
    const pLoc = {
      pos: gl.getAttribLocation(pointProg, 'a_pos'),
      size: gl.getAttribLocation(pointProg, 'a_size'),
      color: gl.getAttribLocation(pointProg, 'a_color'),
      glow: gl.getAttribLocation(pointProg, 'a_glow'),
    }
    const lLoc = {
      pos: gl.getAttribLocation(lineProg, 'a_pos'),
      color: gl.getAttribLocation(lineProg, 'a_color'),
    }
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA) // premultiplied alpha

    let raf = 0
    const t0 = performance.now()

    const frame = () => {
      raf = requestAnimationFrame(frame)
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const W = Math.max(1, Math.round(canvas.clientWidth * dpr))
      const H = Math.max(1, Math.round(canvas.clientHeight * dpr))
      if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H }
      gl.viewport(0, 0, W, H)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)

      const t = (performance.now() - t0) / 1000
      const st = stepsRef.current
      const px = (n: { x: number; y: number }) => [n.x * W, n.y * H] as const
      const nodeById: Record<string, { x: number; y: number }> = {}
      NODES.forEach(n => { nodeById[n.id] = n })
      const statusOf = (id: string): StepStatus => st[id]?.status || 'pending'

      // ── edges ──
      const lineData: number[] = []
      for (const [a, b] of EDGES) {
        const [ax, ay] = px(nodeById[a]); const [bx, by] = px(nodeById[b])
        const sa = statusOf(a); const sb = statusOf(b)
        let c: [number, number, number] = [0.55, 0.50, 0.42]; let alpha = 0.16
        if (sb === 'running') { c = COLORS.running; alpha = 0.45 }
        else if (sa === 'done' && (sb === 'done' || sb === 'error')) { c = COLORS[sb]; alpha = 0.35 }
        lineData.push(ax, ay, c[0], c[1], c[2], alpha, bx, by, c[0], c[1], c[2], alpha)
      }
      gl.useProgram(lineProg)
      gl.uniform2f(lRes, W, H)
      gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lineData), gl.DYNAMIC_DRAW)
      gl.enableVertexAttribArray(lLoc.pos)
      gl.vertexAttribPointer(lLoc.pos, 2, gl.FLOAT, false, 24, 0)
      gl.enableVertexAttribArray(lLoc.color)
      gl.vertexAttribPointer(lLoc.color, 4, gl.FLOAT, false, 24, 8)
      gl.drawArrays(gl.LINES, 0, lineData.length / 6)

      // ── nodes + flow particles ── stride: pos(2) size(1) color(3) glow(1) = 7 floats
      const pts: number[] = []
      for (const n of NODES) {
        const s = statusOf(n.id)
        const [x, y] = px(n)
        const c = COLORS[s]
        let size = 15 * dpr; let glow = 0.05
        if (s === 'running') { size = (21 + Math.sin(t * 6 + n.y * 9) * 3.5) * dpr; glow = 1 }
        else if (s === 'done') { size = 18 * dpr; glow = 0.3 }
        else if (s === 'error') { size = 19 * dpr; glow = 0.7 }
        pts.push(x, y, size, c[0], c[1], c[2], glow)
      }
      for (const [a, b] of EDGES) {
        if (statusOf(b) !== 'running') continue
        const [ax, ay] = px(nodeById[a]); const [bx, by] = px(nodeById[b])
        for (let i = 0; i < 3; i++) {
          const f = (t * 0.55 + i / 3) % 1
          pts.push(ax + (bx - ax) * f, ay + (by - ay) * f, 5.5 * dpr,
                   COLORS.running[0], COLORS.running[1], COLORS.running[2], 1)
        }
      }
      gl.useProgram(pointProg)
      gl.uniform2f(pRes, W, H)
      gl.bindBuffer(gl.ARRAY_BUFFER, pointBuf)
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pts), gl.DYNAMIC_DRAW)
      gl.enableVertexAttribArray(pLoc.pos)
      gl.vertexAttribPointer(pLoc.pos, 2, gl.FLOAT, false, 28, 0)
      gl.enableVertexAttribArray(pLoc.size)
      gl.vertexAttribPointer(pLoc.size, 1, gl.FLOAT, false, 28, 8)
      gl.enableVertexAttribArray(pLoc.color)
      gl.vertexAttribPointer(pLoc.color, 3, gl.FLOAT, false, 28, 12)
      gl.enableVertexAttribArray(pLoc.glow)
      gl.vertexAttribPointer(pLoc.glow, 1, gl.FLOAT, false, 28, 24)
      gl.drawArrays(gl.POINTS, 0, pts.length / 7)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  const durationOf = (info?: StepInfo) => {
    if (!info?.startedAt || !info?.endedAt) return null
    const ms = info.endedAt - info.startedAt
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.max(1, Math.round(ms))}ms`
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: 260, borderRadius: 10,
                  background: 'linear-gradient(160deg,#171411,#211c17)', overflow: 'hidden' }}>
      <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
      {NODES.map(n => {
        const info = steps[n.id]
        const status = info?.status || 'pending'
        const dur = durationOf(info)
        return (
          <div key={n.id} style={{
            position: 'absolute', left: `${n.x * 100}%`, top: `${n.y * 100}%`,
            transform: n.id === 'decision' || n.id === 'verify'
              ? 'translate(-50%, -290%)' : 'translate(-50%, 60%)',
            fontSize: 10.5, lineHeight: 1.3, textAlign: 'center', pointerEvents: 'none',
            color: status === 'pending' ? '#7d7466' : '#e8e0d2', whiteSpace: 'nowrap',
            textShadow: '0 1px 3px rgba(0,0,0,.8)',
          }}>
            <div style={{ fontWeight: 600 }}>
              {labels[n.id] || n.id}
              {(info?.runs ?? 0) > 1 && <span style={{ color: '#f5a623' }}> ×{info!.runs}</span>}
            </div>
            {status === 'running' && <div style={{ color: '#f5a623' }}>{labels.__running || 'running'}</div>}
            {status === 'done' && dur && <div style={{ color: '#6fbf73' }}>{dur}</div>}
            {status === 'error' && <div style={{ color: '#f0663f' }}>{labels.__error || 'error'}</div>}
          </div>
        )
      })}
    </div>
  )
}

// ── Shared step labels (localized) ──

export function analysisStepLabels(language: Language): Record<string, string> {
  const gather = tr(language, { ko: '수집', en: 'Gather', ja: '収集', th: 'รวบรวม', vi: 'Thu thập' })
  const brief = tr(language, { ko: '브리프', en: 'Brief', ja: 'ブリーフ', th: 'สรุป', vi: 'Tóm tắt' })
  const roles: Record<string, string> = {
    news: tr(language, { ko: '뉴스', en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức' }),
    sentiment: tr(language, { ko: '심리', en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý' }),
    fundamentals_macro: tr(language, { ko: '펀더멘털 & 매크로', en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô' }),
    technical: tr(language, { ko: '기술적 분석', en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật' }),
  }
  const labels: Record<string, string> = {
    decision: tr(language, { ko: '트레이더+리스크 결정', en: 'Trader + Risk decision', ja: 'トレーダー+リスク判断', th: 'ตัดสินใจเทรด+ความเสี่ยง', vi: 'Quyết định Trader + Rủi ro' }),
    verify: tr(language, { ko: '검증', en: 'Verify', ja: '検証', th: 'ตรวจสอบ', vi: 'Xác minh' }),
    __running: tr(language, { ko: '실행 중', en: 'running', ja: '実行中', th: 'กำลังทำงาน', vi: 'đang chạy' }),
    __error: tr(language, { ko: '오류', en: 'error', ja: 'エラー', th: 'ผิดพลาด', vi: 'lỗi' }),
    __start: tr(language, { ko: '시작', en: 'start', ja: '開始', th: 'เริ่ม', vi: 'bắt đầu' }),
    __done: tr(language, { ko: '완료', en: 'done', ja: '完了', th: 'เสร็จ', vi: 'xong' }),
    __pipeline: tr(language, { ko: '실시간 파이프라인 모니터', en: 'Live pipeline monitor', ja: 'リアルタイム・パイプライン', th: 'มอนิเตอร์ไปป์ไลน์สด', vi: 'Giám sát pipeline trực tiếp' }),
    __stepLog: tr(language, { ko: '단계 로그', en: 'Step log', ja: 'ステップログ', th: 'บันทึกขั้นตอน', vi: 'Nhật ký bước' }),
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
        if (!res.ok) { if (gen === genRef.current) setLoading(false); return }
        const data = await res.json()
        if (gen !== genRef.current) return
        if (!data.job) { setLoading(false); return }
        if (applyJob(data.job) !== 'running') return
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

// ── Shared monitor panel: WebGL2 graph + timestamped step log ──

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
              <span style={{ color: e.status === 'error' ? '#f0663f' : e.status === 'done' ? '#3fb950' : 'var(--text-primary,inherit)' }}>
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
