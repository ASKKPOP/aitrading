import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { LANGUAGES, fearGreedLabel, tr } from '../i18n'
import type { Language } from '../i18n'

// Derived from LANGUAGES, never hand-listed. This was a literal
// Record<string, string> of five codes — the loose `string` key meant adding a
// sixth language typechecked clean while the landing page kept offering five,
// so a visitor could not select the language the rest of the product served.
const LANGS: [Language, string][] =
  LANGUAGES.map(({ value }) => [value, value.toUpperCase()])

// Public landing page — quiet editorial, zero animation, compact blocks.
// Narrative: the AI *measures* market footprints (quant × qualitative × psychology
// proxies), decides on your rules, and paper-trades with hard risk limits.
// Design system: Signal tokens from index.css (system-ui type, white cards,
// signal accent colors, automatic dark mode).

/* theme shorthands (fall back to the Signal palette) */
const V = {
  bg: 'var(--bg-primary, #f9f9f7)',
  bg2: 'var(--bg-secondary, #f1f0ec)',
  card: 'var(--bg-card, #ffffff)',
  ink: 'var(--text-primary, #0b0b0b)',
  mut: 'var(--text-secondary, #52514e)',
  faint: 'var(--text-muted, #898781)',
  line: 'var(--border-color, rgba(11,11,11,0.10))',
  lineStrong: 'var(--border-strong, #c3c2b7)',
  accent: 'var(--accent-primary, #2a78d6)',
  accentOn: 'var(--accent-contrast, #ffffff)',
  up: 'var(--up, #006300)',
  down: 'var(--down, #d03b3b)',
  display: 'var(--font-display, system-ui, sans-serif)',
  sans: 'var(--font-sans, system-ui, sans-serif)',
  mono: 'var(--font-mono, ui-monospace, monospace)',
}

const wrap: any = { maxWidth: 1040, margin: '0 auto', padding: '0 24px' }

// Animated 3D hero backdrop — raw WebGL point-cloud wave field (no libraries).
// A perspective camera looks across a dot grid whose height is computed in the
// vertex shader (GPU; near-zero CPU per frame). Additive blending gives the
// glow of the design reference; crests warm to amber, troughs cool to teal.
// Behaviors: DPR cap 2, resize redraw, pause in hidden tabs, reduced-motion
// drifts slowly instead of freezing, one synchronous first frame on mount.
function HeroWaveBackground({ gain = 1, amp = 1 }: { gain?: number; amp?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { alpha: true, antialias: true })
    if (!gl) return // graceful: hero simply has no backdrop on WebGL-less browsers
    let raf = 0
    let running = true
    let t = 6.0
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const SPEED = reduced ? 0.006 : 0.022
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    const VS = `
      attribute vec2 aGrid;            // x in [-1,1], z in [0,1] (0 near, 1 far)
      uniform float uTime;
      uniform mat4 uProj;
      uniform mat4 uView;
      uniform float uDpr;
      uniform float uAmp;
      varying float vHeat;
      varying float vDepth;
      void main() {
        float x = aGrid.x;
        float z = aGrid.y;
        float wave = sin(x * 4.0 + uTime * 0.9 + z * 6.0)
                   + 0.5 * sin(x * 7.5 - uTime * 0.6 + z * 11.0)
                   + 0.25 * sin(x * 13.0 + uTime * 1.3 + z * 3.0);
        wave /= 1.75;
        float y = wave * 0.55 * uAmp * (1.0 - z * 0.22);
        vec4 world = vec4(x * 4.2, y - 0.28, -0.9 - z * 6.5, 1.0);
        gl_Position = uProj * uView * world;
        vHeat = wave;
        vDepth = z;
        gl_PointSize = (2.6 + max(wave, 0.0) * 3.8) * (1.0 - z * 0.70) * uDpr;
      }`
    // Shared color math; two fragment shaders because gl_PointCoord may only
    // be referenced when drawing POINTS — one program for lines, one for dots
    // (referencing it while drawing LINES is undefined and kills the context
    // on ANGLE/Metal).
    const FS_COMMON = `
      precision mediump float;
      varying float vHeat;
      varying float vDepth;
      uniform float uDark;
      uniform float uGain;
      vec4 waveColor(float alphaBase, float mask) {
        float heat = max(vHeat, 0.0);
        float cold = max(-vHeat, 0.0);
        vec3 amber = vec3(1.0, 0.55 + 0.25 * (1.0 - heat), 0.13);
        vec3 teal  = vec3(0.24, 0.83, 0.75);
        vec3 base  = uDark > 0.5 ? vec3(0.82, 0.86, 0.92) : vec3(0.28, 0.34, 0.42);
        vec3 color = base;
        color = mix(color, amber, smoothstep(0.08, 0.75, heat));
        color = mix(color, teal, smoothstep(0.45, 0.95, cold) * 0.8);
        float fog = 1.0 - vDepth * 0.78;
        float a = alphaBase * uGain * fog * (0.55 + 0.85 * heat + 0.3 * cold) * mask;
        return vec4(color * a, a);               // premultiplied
      }`
    const FS_LINE = FS_COMMON + `
      void main() { gl_FragColor = waveColor(0.10, 1.0); }`
    const FS_POINT = FS_COMMON + `
      void main() {
        vec2 d = gl_PointCoord - vec2(0.5);
        float r = length(d) * 2.0;
        if (r > 1.0) discard;
        gl_FragColor = waveColor(0.34, smoothstep(1.0, 0.35, r));
      }`

    const compile = (type: number, srcText: string) => {
      const s = gl.createShader(type)!
      gl.shaderSource(s, srcText)
      gl.compileShader(s)
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.error('hero shader compile failed:', gl.getShaderInfoLog(s))
        return null
      }
      return s
    }
    const makeProgram = (fsSrc: string) => {
      const vs = compile(gl.VERTEX_SHADER, VS)
      const fs = compile(gl.FRAGMENT_SHADER, fsSrc)
      if (!vs || !fs) return null
      const pr = gl.createProgram()!
      gl.attachShader(pr, vs)
      gl.attachShader(pr, fs)
      gl.linkProgram(pr)
      if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) {
        console.error('hero shader link failed:', gl.getProgramInfoLog(pr))
        return null
      }
      return pr
    }
    const lineProg = makeProgram(FS_LINE)
    const pointProg = makeProgram(FS_POINT)
    if (!lineProg || !pointProg) return

    // grid geometry (uploaded once; the wave lives in the shader)
    const COLS = 160, ROWS = 60
    const verts = new Float32Array(COLS * ROWS * 2)
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const i = (r * COLS + c) * 2
        verts[i] = (c / (COLS - 1)) * 2 - 1
        verts[i + 1] = r / (ROWS - 1)
      }
    }
    const lineIdx: number[] = []
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS - 1; c++) lineIdx.push(r * COLS + c, r * COLS + c + 1)
    for (let r = 0; r < ROWS - 1; r++) for (let c = 0; c < COLS; c++) lineIdx.push(r * COLS + c, (r + 1) * COLS + c)
    const vbo = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo)
    gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW)
    const ibo = gl.createBuffer()
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo)
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint32Array(lineIdx), gl.STATIC_DRAW)
    const uint32ok = !!gl.getExtension('OES_element_index_uint')
    const uni = (pr: WebGLProgram) => ({
      prog: pr,
      aGrid: gl.getAttribLocation(pr, 'aGrid'),
      uTime: gl.getUniformLocation(pr, 'uTime'),
      uProj: gl.getUniformLocation(pr, 'uProj'),
      uView: gl.getUniformLocation(pr, 'uView'),
      uDpr: gl.getUniformLocation(pr, 'uDpr'),
      uDark: gl.getUniformLocation(pr, 'uDark'),
      uAmp: gl.getUniformLocation(pr, 'uAmp'),
      uGain: gl.getUniformLocation(pr, 'uGain'),
    })
    const L = uni(lineProg)
    const P = uni(pointProg)

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)   // premultiplied — glow without white-out
    gl.disable(gl.DEPTH_TEST)

    const proj = new Float32Array(16)
    const view = new Float32Array(16)
    const perspective = (out: Float32Array, fovy: number, aspect: number, near: number, far: number) => {
      const f = 1 / Math.tan(fovy / 2); out.fill(0)
      out[0] = f / aspect; out[5] = f
      out[10] = (far + near) / (near - far); out[11] = -1
      out[14] = (2 * far * near) / (near - far)
    }
    const viewMatrix = (out: Float32Array, time: number) => {
      // slight downward tilt + slow lateral sway for 3D parallax
      const rx = -0.32, ry = Math.sin(time * 0.07) * 0.05
      const cx = Math.cos(rx), sx = Math.sin(rx), cy = Math.cos(ry), sy = Math.sin(ry)
      // R = Rx * Ry, then translate camera up/back
      out.set([
        cy, sx * sy, -cx * sy, 0,
        0, cx, sx, 0,
        sy, -sx * cy, cx * cy, 0,
        0, -0.02, -0.35, 1,
      ])
    }

    const draw = () => {
      // never draw into a degenerate buffer (pre-layout measure)
      if (canvas.width < 10 || canvas.height < 10) return
      const dark = document.documentElement.dataset.theme !== 'light'
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      perspective(proj, Math.PI / 3, canvas.width / Math.max(1, canvas.height), 0.1, 30)
      viewMatrix(view, t)
      const setUniforms = (U: typeof L) => {
        gl.useProgram(U.prog)
        gl.enableVertexAttribArray(U.aGrid)
        gl.vertexAttribPointer(U.aGrid, 2, gl.FLOAT, false, 0, 0)
        gl.uniform1f(U.uTime, t)
        gl.uniformMatrix4fv(U.uProj, false, proj)
        gl.uniformMatrix4fv(U.uView, false, view)
        gl.uniform1f(U.uDpr, dpr)
        gl.uniform1f(U.uDark, dark ? 1 : 0)
        gl.uniform1f(U.uAmp, amp)
        gl.uniform1f(U.uGain, gain)
      }
      if (uint32ok) {
        setUniforms(L)
        gl.drawElements(gl.LINES, lineIdx.length, gl.UNSIGNED_INT, 0)
      }
      setUniforms(P)
      gl.drawArrays(gl.POINTS, 0, COLS * ROWS)
    }

    const resize = () => {
      const host = canvas.parentElement
      if (!host) return
      const r = host.getBoundingClientRect()
      if (r.width < 10 || r.height < 10) return   // layout not settled yet
      canvas.width = Math.round(r.width * dpr)
      canvas.height = Math.round(r.height * dpr)
      draw()
    }
    // ResizeObserver (not window resize): fires when the SECTION actually
    // gets its size — including the 0-width -> real-width transition during
    // lazy mount, which a mount-time measure races against.
    const ro = new ResizeObserver(resize)
    if (canvas.parentElement) ro.observe(canvas.parentElement)

    // A lost GL context must stop the loop (drawing into it is undefined);
    // on restore the page reload path is fine — just stop cleanly.
    const onLost = (e: Event) => { e.preventDefault(); running = false; cancelAnimationFrame(raf) }
    canvas.addEventListener('webglcontextlost', onLost)

    const loop = () => {
      if (!running) return
      t += SPEED
      draw()
      raf = requestAnimationFrame(loop)
    }
    resize()                      // first frame paints synchronously
    raf = requestAnimationFrame(loop)
    const onVis = () => {
      running = !document.hidden
      cancelAnimationFrame(raf)
      if (running) raf = requestAnimationFrame(loop)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      canvas.removeEventListener('webglcontextlost', onLost)
      document.removeEventListener('visibilitychange', onVis)
      // Do NOT loseContext() here: a canvas keeps a single context for life,
      // so under StrictMode's mount->cleanup->mount cycle the second mount
      // would receive this same, now permanently-lost context and every
      // shader compile would fail. The browser reclaims it with the canvas.
    }
  }, [gain, amp])
  return (
    <canvas ref={ref} aria-hidden
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }} />
  )
}
// ── pipeline flow diagram (verbatim port of guide.html §0 geometry) ──────
// Coordinate space shared by the SVG diagram and the particle overlay.
const FLOW_W = 960, FLOW_H = 620
// Connector polylines traced from the guide SVG; particles ride them.
// c: color group · n: particles · k: cycle speed · o: phase offset
const FLOW_PATHS: Array<{ pts: Array<[number, number]>; n: number; k: number; o: number; c: 'base' | 'acc' | 'good' | 'bad' }> = [
  // sources → collectors
  { pts: [[102, 80], [102, 108]], n: 1, k: 0.5, o: 0.0, c: 'base' },
  { pts: [[290, 80], [290, 108]], n: 1, k: 0.5, o: 0.2, c: 'base' },
  { pts: [[478, 80], [478, 108]], n: 1, k: 0.5, o: 0.4, c: 'base' },
  { pts: [[666, 80], [666, 108]], n: 1, k: 0.5, o: 0.6, c: 'base' },
  { pts: [[856, 80], [856, 108]], n: 1, k: 0.5, o: 0.8, c: 'base' },
  // collectors → snapshot store
  { pts: [[126, 168], [126, 196]], n: 1, k: 0.5, o: 0.1, c: 'base' },
  { pts: [[362, 168], [362, 196]], n: 1, k: 0.5, o: 0.35, c: 'base' },
  { pts: [[598, 168], [598, 196]], n: 1, k: 0.5, o: 0.6, c: 'base' },
  { pts: [[834, 168], [834, 196]], n: 1, k: 0.5, o: 0.85, c: 'base' },
  // snapshot store → fusion / AI analysts
  { pts: [[240, 238], [240, 266]], n: 1, k: 0.5, o: 0.0, c: 'base' },
  { pts: [[720, 238], [720, 266]], n: 1, k: 0.5, o: 0.5, c: 'base' },
  // fusion + analysts → automation rules
  { pts: [[240, 334], [240, 360], [180, 360], [180, 386]], n: 2, k: 0.28, o: 0.0, c: 'base' },
  { pts: [[720, 334], [720, 360], [184, 360]], n: 3, k: 0.13, o: 0.0, c: 'base' },
  // rules → risk gate → PASS → paper execution · FAIL ↓ journal
  { pts: [[320, 421], [366, 421]], n: 1, k: 0.5, o: 0.0, c: 'acc' },
  { pts: [[624, 421], [670, 421]], n: 1, k: 0.5, o: 0.3, c: 'good' },
  { pts: [[496, 454], [496, 488]], n: 1, k: 0.45, o: 0.0, c: 'bad' },
  // execution → tracking → journal → dashboard
  { pts: [[808, 454], [808, 488]], n: 1, k: 0.45, o: 0.5, c: 'base' },
  { pts: [[672, 517], [626, 517]], n: 1, k: 0.5, o: 0.2, c: 'base' },
  { pts: [[496, 544], [496, 572]], n: 1, k: 0.5, o: 0.6, c: 'acc' },
]
const FLOW_COLORS: Record<string, [number, number, number]> = {
  base: [0.55, 0.62, 0.85],
  acc: [0.30, 0.58, 0.98],
  good: [0.20, 0.78, 0.35],
  bad: [0.92, 0.35, 0.35],
}

// WebGL glow particles travelling along the diagram connectors.
// Same lifecycle rules as HeroWaveBackground (no loseContext in cleanup,
// ResizeObserver sizing, degenerate-buffer guards, hidden-tab pause).
function FlowParticles() {
  const ref = useRef<HTMLCanvasElement | null>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { alpha: true, antialias: true })
    if (!gl) return
    let raf = 0
    let running = true
    let t = 0
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const STEP = reduced ? 0.004 : 0.016
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    const VS = `
      attribute vec2 aPos;        // diagram coords
      attribute float aAlpha;
      attribute vec3 aColor;
      uniform float uDpr;
      varying float vAlpha;
      varying vec3 vColor;
      void main() {
        gl_Position = vec4(aPos.x / ${FLOW_W}.0 * 2.0 - 1.0, 1.0 - aPos.y / ${FLOW_H}.0 * 2.0, 0.0, 1.0);
        gl_PointSize = 7.0 * uDpr;
        vAlpha = aAlpha;
        vColor = aColor;
      }`
    const FS = `
      precision mediump float;
      varying float vAlpha;
      varying vec3 vColor;
      void main() {
        vec2 d = gl_PointCoord - vec2(0.5);
        float r = length(d) * 2.0;
        if (r > 1.0) discard;
        float a = vAlpha * smoothstep(1.0, 0.15, r);
        gl_FragColor = vec4(vColor * a, a);      // premultiplied
      }`
    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!
      gl.shaderSource(s, src)
      gl.compileShader(s)
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error('flow shader:', gl.getShaderInfoLog(s)); return null }
      return s
    }
    const vs = compile(gl.VERTEX_SHADER, VS)
    const fs = compile(gl.FRAGMENT_SHADER, FS)
    if (!vs || !fs) return
    const prog = gl.createProgram()!
    gl.attachShader(prog, vs)
    gl.attachShader(prog, fs)
    gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return
    const aPos = gl.getAttribLocation(prog, 'aPos')
    const aAlpha = gl.getAttribLocation(prog, 'aAlpha')
    const aColor = gl.getAttribLocation(prog, 'aColor')
    const uDpr = gl.getUniformLocation(prog, 'uDpr')
    const vbo = gl.createBuffer()
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)

    // precompute per-path segment lengths for polyline interpolation
    const geo = FLOW_PATHS.map(p => {
      const segs: number[] = []
      let len = 0
      for (let i = 1; i < p.pts.length; i++) {
        const d = Math.hypot(p.pts[i][0] - p.pts[i - 1][0], p.pts[i][1] - p.pts[i - 1][1])
        segs.push(d); len += d
      }
      return { segs, len }
    })
    const total = FLOW_PATHS.reduce((s, p) => s + p.n, 0)
    const data = new Float32Array(total * 6)
    const pointAt = (pi: number, f: number): [number, number] => {
      const { pts } = FLOW_PATHS[pi]
      const { segs, len } = geo[pi]
      let target = f * len
      for (let i = 0; i < segs.length; i++) {
        if (target <= segs[i] || i === segs.length - 1) {
          const u = segs[i] === 0 ? 0 : Math.min(1, target / segs[i])
          const a = pts[i], b = pts[i + 1]
          return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]
        }
        target -= segs[i]
      }
      return pts[pts.length - 1]
    }
    const smooth = (e0: number, e1: number, x: number) => {
      const u = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)))
      return u * u * (3 - 2 * u)
    }

    const draw = () => {
      if (canvas.width < 10 || canvas.height < 10) return
      let i = 0
      FLOW_PATHS.forEach((p, pi) => {
        const [cr, cg, cb] = FLOW_COLORS[p.c]
        for (let j = 0; j < p.n; j++) {
          const ph = ((j / p.n) + p.o + t * p.k) % 1
          const [x, y] = pointAt(pi, ph)
          const a = smooth(0, 0.08, ph) * (1 - smooth(0.92, 1, ph)) * 0.95
          data[i++] = x; data[i++] = y; data[i++] = a
          data[i++] = cr; data[i++] = cg; data[i++] = cb
        }
      })
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.useProgram(prog)
      gl.bindBuffer(gl.ARRAY_BUFFER, vbo)
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW)
      gl.enableVertexAttribArray(aPos)
      gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 24, 0)
      gl.enableVertexAttribArray(aAlpha)
      gl.vertexAttribPointer(aAlpha, 1, gl.FLOAT, false, 24, 8)
      gl.enableVertexAttribArray(aColor)
      gl.vertexAttribPointer(aColor, 3, gl.FLOAT, false, 24, 12)
      gl.uniform1f(uDpr, dpr)
      gl.drawArrays(gl.POINTS, 0, total)
    }
    const resize = () => {
      const host = canvas.parentElement
      if (!host) return
      const r = host.getBoundingClientRect()
      if (r.width < 10 || r.height < 10) return
      canvas.width = Math.round(r.width * dpr)
      canvas.height = Math.round(r.height * dpr)
      draw()
    }
    const ro = new ResizeObserver(resize)
    if (canvas.parentElement) ro.observe(canvas.parentElement)
    const onLost = (e: Event) => { e.preventDefault(); running = false; cancelAnimationFrame(raf) }
    canvas.addEventListener('webglcontextlost', onLost)
    const loop = () => {
      if (!running) return
      t += STEP
      draw()
      raf = requestAnimationFrame(loop)
    }
    resize()
    raf = requestAnimationFrame(loop)
    const onVis = () => {
      running = !document.hidden
      cancelAnimationFrame(raf)
      if (running) raf = requestAnimationFrame(loop)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      canvas.removeEventListener('webglcontextlost', onLost)
      document.removeEventListener('visibilitychange', onVis)
      // no loseContext() — see HeroWaveBackground cleanup note
    }
  }, [])
  return (
    <canvas ref={ref} aria-hidden
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', pointerEvents: 'none' }} />
  )
}

const kicker: any = { fontFamily: V.mono, fontSize: 11.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: V.accent, fontWeight: 500 }
const cardS: any = { background: V.card, border: `1px solid ${V.line}`, borderRadius: 14, padding: '16px 18px' }
const h2S: any = { fontFamily: V.display, fontWeight: 700, fontSize: 'clamp(28px,3.6vw,40px)', letterSpacing: '-0.02em', lineHeight: 1.08, color: V.ink, margin: '10px 0 10px' }

export function MarketingPage() {
  const { language, setLanguage } = useLanguage()
  const [btc, setBtc] = useState<{ price: number; pct: number } | null>(null)
  // Live signal data for the dashboard preview — no hardcoded sample numbers.
  const [psych, setPsych] = useState<any | null>(null)
  const [fusion, setFusion] = useState<any[] | null>(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch('/api/markets/crypto/ticker?symbol=BTCUSDT')
        if (!r.ok) return
        const d = await r.json()
        if (alive) setBtc({ price: Number(d.last_price), pct: Number(d.price_24h_pct) })
      } catch { /* transient */ }
    }
    load()
    const iv = setInterval(load, 15000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  useEffect(() => {
    let alive = true
    const loadSignals = async () => {
      try {
        const [pRes, fRes] = await Promise.all([
          fetch('/api/market-intel/psych'),
          fetch('/api/market-intel/fusion?symbols=BTC,ETH,SOL'),
        ])
        if (alive && pRes.ok) setPsych(await pRes.json())
        if (alive && fRes.ok) setFusion((await fRes.json()).signals ?? null)
      } catch { /* transient */ }
    }
    loadSignals()
    const iv = setInterval(loadSignals, 60000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  const fng = psych?.available ? psych?.fear_greed : null
  const newsSpike = psych?.available
    ? (psych?.spikes?.find((s: any) => s.category === 'crypto') ?? psych?.spikes?.[0] ?? null)
    : null
  const shockCount = psych?.available ? (psych?.shock ?? []).filter((s: any) => s.shock).length : null

  const T = {
    login: tr(language, { ko: '로그인', en: 'Log in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    signup: tr(language, { ko: '가입하기', en: 'Sign up', ja: '登録', th: 'สมัคร', vi: 'Đăng ký' }),

    heroKicker: tr(language, { ko: 'INTELLIGENT AUTOMATE AGENT · 페이퍼 먼저', en: 'INTELLIGENT AUTOMATE AGENT · PAPER-FIRST', ja: 'INTELLIGENT AUTOMATE AGENT · まず模擬', th: 'INTELLIGENT AUTOMATE AGENT · เปเปอร์ก่อน', vi: 'INTELLIGENT AUTOMATE AGENT · PAPER TRƯỚC' }),
    heroH1a: tr(language, { ko: '신호는 예측이 아니라,', en: 'Signals are measured,', ja: 'シグナルは予測ではなく、', th: 'สัญญาณคือสิ่งที่วัดได้', vi: 'Tín hiệu là thứ đo được,' }),
    heroH1b: tr(language, { ko: '측정하는 것입니다.', en: 'not predicted.', ja: '測定するもの。', th: 'ไม่ใช่การทำนาย', vi: 'không phải dự đoán.' }),
    heroSub: tr(language, {
      ko: 'AI는 시장이 이미 남긴 흔적 — 거래량 급증, 고래 지갑, 뉴스, 군중 심리 — 을 읽고, 정량 트리거와 결합해, 엄격한 리스크 한도 안에서 당신의 규칙대로 매매합니다.',
      en: 'The AI reads the traces a market already left — volume surges, whale wallets, news, crowd psychology — combines them with quant triggers, and trades on your rules with hard risk limits.',
      ja: 'AIは市場に残された痕跡 — 出来高急増・クジラのウォレット・ニュース・群集心理 — を読み取り、定量トリガーと組み合わせ、厳格なリスク制限のもとであなたのルール通りに模擬売買します。',
      th: 'AI อ่านร่องรอยที่ตลาดทิ้งไว้ — ปริมาณพุ่ง กระเป๋าวาฬ ข่าว จิตวิทยาฝูงชน — ผสานกับทริกเกอร์เชิงปริมาณ แล้วเทรดจำลองตามกฎของคุณพร้อมลิมิตความเสี่ยงที่ตายตัว',
      vi: 'AI đọc các dấu vết thị trường để lại — khối lượng tăng vọt, ví cá voi, tin tức, tâm lý đám đông — kết hợp với trigger định lượng, rồi giao dịch mô phỏng theo quy tắc của bạn với giới hạn rủi ro cứng.',
    }),
    ctaStart: tr(language, { ko: '무료로 시작', en: 'Start free', ja: '無料で始める', th: 'เริ่มฟรี', vi: 'Bắt đầu miễn phí' }),
    ctaBoard: tr(language, { ko: '리더보드 보기', en: 'See leaderboard', ja: 'リーダーボード', th: 'ดูลีดเดอร์บอร์ด', vi: 'Xem bảng xếp hạng' }),
    heroNote: tr(language, { ko: '페이퍼로 시작 — 모든 모의 거래는 실제 자금이 없습니다. 라이브는 본인 브로커에서 검증 후 선택적으로. 투자 자문 아님.', en: 'Start on paper — every simulated trade uses no real funds. Live is opt-in on your own broker, after you verify. Not advice.', ja: 'まずは模擬から — 全ての模擬取引に実資金は不要。ライブは本人のブローカーで検証後に任意で。投資助言ではありません。', th: 'เริ่มด้วยเปเปอร์ — ทุกเทรดจำลองไม่ใช้เงินจริง ไลฟ์เป็นทางเลือกบนโบรกเกอร์ของคุณหลังยืนยัน ไม่ใช่คำแนะนำ', vi: 'Bắt đầu bằng paper — mọi giao dịch mô phỏng không dùng tiền thật. Live là tùy chọn trên broker của bạn, sau khi xác minh. Không phải lời khuyên.' }),

    readKicker: tr(language, { ko: 'AI가 읽는 것', en: 'WHAT THE AI READS', ja: 'AIが読むもの', th: 'สิ่งที่ AI อ่าน', vi: 'AI ĐỌC GÌ' }),
    readH: tr(language, { ko: '여섯 가지 신호 요소', en: 'Six signal elements', ja: '6つのシグナル要素', th: 'องค์ประกอบสัญญาณ 6 อย่าง', vi: 'Sáu yếu tố tín hiệu' }),
    read: [
      { t: tr(language, { ko: '어떤 코인을', en: 'Which coin', ja: 'どのコイン', th: 'เหรียญไหน', vi: 'Coin nào' }), d: tr(language, { ko: '거래량 급증, 소셜 멘션 급등, 고래 지갑 이동, 신규 상장을 스캔해 후보를 추립니다.', en: 'Scans volume surges, social mention spikes, whale wallet moves and new listings to shortlist candidates.', ja: '出来高急増・ソーシャル言及の急上昇・クジラの移動・新規上場をスキャンして候補を絞ります。', th: 'สแกนปริมาณพุ่ง การพูดถึงในโซเชียล การเคลื่อนไหวกระเป๋าวาฬ และเหรียญลิสต์ใหม่เพื่อคัดตัวเลือก', vi: 'Quét khối lượng tăng vọt, lượt nhắc mạng xã hội, ví cá voi và niêm yết mới để chọn ứng viên.' }) },
      { t: tr(language, { ko: '왜 움직였나', en: 'Why it moved', ja: 'なぜ動いたか', th: 'ทำไมถึงขยับ', vi: 'Vì sao biến động' }), d: tr(language, { ko: 'LLM이 가격 변동을 실시간 뉴스·이벤트와 대조해 원인을 태깅합니다.', en: 'The LLM matches each price move against live news and events — causal tagging in real time.', ja: 'LLMが価格変動をライブのニュース・イベントと照合し、リアルタイムで因果タグ付けします。', th: 'LLM จับคู่การเคลื่อนไหวราคากับข่าวและเหตุการณ์สด — ติดแท็กเชิงสาเหตุแบบเรียลไทม์', vi: 'LLM đối chiếu mỗi biến động giá với tin tức và sự kiện trực tiếp — gắn nhãn nhân quả theo thời gian thực.' }) },
      { t: tr(language, { ko: '언제 살까', en: 'When to buy', ja: 'いつ買うか', th: 'ซื้อเมื่อไร', vi: 'Khi nào mua' }), d: tr(language, { ko: '정량 트리거(RSI·베이시스·펀딩)와 정성 트리거(감성 급등·확률 변화)를 결합합니다.', en: 'Quant triggers (RSI, basis, funding) combined with qualitative ones (sentiment spikes, odds shifts).', ja: '定量トリガー（RSI・ベーシス・資金調達率）と定性トリガー（感性スパイク・オッズ変化）を結合。', th: 'ทริกเกอร์เชิงปริมาณ (RSI, เบสิส, ฟันดิง) ผสานทริกเกอร์เชิงคุณภาพ (เซนติเมนต์พุ่ง, อัตราต่อรองเปลี่ยน)', vi: 'Trigger định lượng (RSI, basis, funding) kết hợp trigger định tính (tâm lý tăng vọt, tỷ lệ cược đổi).' }) },
      { t: tr(language, { ko: '언제 팔까', en: 'When to sell', ja: 'いつ売るか', th: 'ขายเมื่อไร', vi: 'Khi nào bán' }), d: tr(language, { ko: '과열(RSI 과매수), 음의 감성 급등, 고래 유출, 3σ 변동성이 청산을 강제합니다.', en: 'Overheat (RSI overbought), negative sentiment spikes, whale outflows or 3σ volatility force exits.', ja: '過熱（RSI過買い）・部定感性の急増・クジラ流出・3σ変動で強制的に手仕舞います。', th: 'ความร้อนแรงเกิน (RSI ซื้อมากไป) เซนติเมนต์ลบพุ่ง วาฬไหลออก หรือความผันผวน 3σ บังคับปิดสถานะ', vi: 'Quá nóng (RSI quá mua), tâm lý tiêu cực tăng vọt, cá voi rút hoặc biến động 3σ buộc thoát lệnh.' }) },
      { t: tr(language, { ko: '뉴스 · 핫이슈', en: 'News & hot issues', ja: 'ニュース・注目イベント', th: 'ข่าวและประเด็นร้อน', vi: 'Tin tức & vấn đề nóng' }), d: tr(language, { ko: '뉴스 API와 소셜 피드를 LLM이 요약·중요도 평가해 시장 영향을 추정합니다.', en: 'News APIs and social feeds, summarised and importance-scored by the LLM to estimate market impact.', ja: 'ニュースAPIとソーシャルフィードをLLMが要約・重要度スコア化し、市場影響を推定します。', th: 'API ข่าวและฟีดโซเชียล ถูก LLM สรุปและให้คะแนนความสำคัญเพื่อประเมินผลกระทบต่อตลาด', vi: 'API tin tức và mạng xã hội được LLM tóm tắt, chấm điểm mức quan trọng để ước tính tác động thị trường.' }) },
      { t: tr(language, { ko: '심리', en: 'Psychology', ja: '心理', th: 'จิตวิทยา', vi: 'Tâm lý' }), d: tr(language, { ko: '공포·충격·기대 — 멘션·감성 점수·변동성·청산·확률이라는 프록시로 근사합니다.', en: 'Fear, shock and anticipation — approximated with proxies: mentions, sentiment scores, volatility, liquidations, odds.', ja: '恐怖・衝撃・期待感 — 言及量・感性スコア・変動率・清算・オッズという代用指標で近似します。', th: 'ความกลัว ช็อก และความคาดหวัง — ประมาณด้วยตัวแทน: การพูดถึง คะแนนเซนติเมนต์ ความผันผวน การล้างพอร์ต อัตราต่อรอง', vi: 'Sợ hãi, sốc và kỳ vọng — xấp xỉ bằng proxy: lượt nhắc, điểm tâm lý, biến động, thanh lý, tỷ lệ cược.' }) },
    ],

    psyKicker: tr(language, { ko: '심리의 정량화', en: 'PSYCHOLOGY, QUANTIFIED', ja: '心理の定量化', th: 'จิตวิทยาเชิงตัวเลข', vi: 'TÂM LÝ ĐƯỢC LƯỢNG HÓA' }),
    psyH: tr(language, { ko: '감정이 아니라, 감정이 남긴 발자국을', en: 'Not emotions — their footprints', ja: '感情そのものではなく、その痕跡を', th: 'ไม่ใช่อารมณ์ — แต่คือรอยเท้าของมัน', vi: 'Không phải cảm xúc — mà là dấu vết của chúng' }),
    psyRows: [
      { k: tr(language, { ko: '공포 / 탐욕', en: 'Fear / Greed', ja: '恐怖／強欲', th: 'กลัว / โลภ', vi: 'Sợ / Tham' }), v: tr(language, { ko: '공포·탐욕 지수 · 변동성 · 실제 청산 데이터(OKX)', en: 'Fear & Greed index · volatility · real liquidation data (OKX)', ja: 'Fear&Greed指数 · 変動率 · 実清算データ(OKX)', th: 'ดัชนี Fear & Greed · ความผันผวน · ข้อมูลล้างพอร์ตจริง (OKX)', vi: 'Chỉ số Fear & Greed · biến động · dữ liệu thanh lý thật (OKX)' }) },
      { k: tr(language, { ko: '충격', en: 'Shock', ja: '衝撃', th: 'ช็อก', vi: 'Sốc' }), v: tr(language, { ko: '급격한 음의 감성 스파이크 · 거래량 폭발', en: 'Sudden negative sentiment spikes · volume explosions', ja: '部定感性の急激なスパイク · 出来高の爆発', th: 'เซนติเมนต์ลบพุ่งฉับพลัน · ปริมาณระเบิด', vi: 'Tâm lý tiêu cực tăng đột biến · khối lượng bùng nổ' }) },
      { k: tr(language, { ko: '기대', en: 'Anticipation', ja: '期待感', th: 'ความคาดหวัง', vi: 'Kỳ vọng' }), v: tr(language, { ko: '이벤트 전 멘션 증가 · 예측시장 확률 변화', en: 'Pre-event mention growth · prediction-market odds shifts', ja: 'イベント前の言及増加 · 予測市場オッズの変化', th: 'การพูดถึงก่อนเหตุการณ์เพิ่มขึ้น · อัตราต่อรองตลาดคาดการณ์เปลี่ยน', vi: 'Lượt nhắc tăng trước sự kiện · tỷ lệ cược thị trường dự đoán đổi' }) },
    ],
    psyNote: tr(language, {
      ko: '정직한 한계: 심리 신호는 지연되고 노이즈가 있습니다. AI는 감정을 예측하지 않고 측정·반응합니다. 심리 단독으로는 절대 매매하지 않으며, 항상 정량 신호와 교차 검증합니다.',
      en: 'Honest limits: psychology signals lag and carry noise; the AI measures and reacts — it does not predict feelings. They are never traded alone, always cross-checked against quant signals.',
      ja: '正直な限界：心理シグナルは遅行しノイズが多く、AIは感情を予測するのではなく測定・反応します。単独では売買せず、必ず定量シグナルと照合します。',
      th: 'ข้อจำกัดตามจริง: สัญญาณจิตวิทยาล่าช้าและมีนอยส์ AI วัดและตอบสนอง — ไม่ได้ทำนายความรู้สึก จึงไม่ใช้เดี่ยว ๆ ต้องตรวจไขว้กับสัญญาณเชิงปริมาณเสมอ',
      vi: 'Giới hạn thẳng thắn: tín hiệu tâm lý trễ và nhiễu; AI đo và phản ứng — không dự đoán cảm xúc. Không bao giờ giao dịch đơn lẻ, luôn kiểm chéo với tín hiệu định lượng.',
    }),

    dashKicker: tr(language, { ko: '시그널 대시보드', en: 'SIGNAL DASHBOARD', ja: 'シグナルダッシュボード', th: 'แดชบอร์ดสัญญาณ', vi: 'BẢNG TÍN HIỆU' }),
    dashH: tr(language, { ko: '하나의 보드에 모든 신호', en: 'One board, every signal', ja: 'ひとつのボードにすべてのシグナル', th: 'บอร์ดเดียว ครบทุกสัญญาณ', vi: 'Một bảng, mọi tín hiệu' }),
    liveTag: tr(language, { ko: '라이브 데이터', en: 'LIVE DATA', ja: 'ライブデータ', th: 'ข้อมูลสด', vi: 'DỮ LIỆU TRỰC TIẾP' }),
    collecting: tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'đang thu thập…' }),
    kpiFear: tr(language, { ko: '공포·탐욕 지수', en: 'Fear & Greed', ja: '恐怖・強欲指数', th: 'Fear & Greed', vi: 'Fear & Greed' }),
    kpiNews: tr(language, { ko: '뉴스 감성 (24h)', en: 'News sentiment (24h)', ja: 'ニュース感性 (24h)', th: 'เซนติเมนต์ข่าว (24 ชม.)', vi: 'Tâm lý tin tức (24h)' }),
    kpiNewsSub: tr(language, { ko: '뉴스 스냅샷 z-점수', en: 'news snapshot z-score', ja: 'ニューススナップショットzスコア', th: 'z-score ของสแนปช็อตข่าว', vi: 'z-score ảnh chụp tin tức' }),
    kpiShock: tr(language, { ko: '충격 감지', en: 'Shock alerts', ja: '衝撃検知', th: 'แจ้งเตือนช็อก', vi: 'Cảnh báo sốc' }),
    kpiShockSub: tr(language, { ko: '실제 청산 (OKX) + 변동성', en: 'real liquidations (OKX) + volatility', ja: '実清算 (OKX) + 変動率', th: 'การชำระบัญชีจริง (OKX) + ความผันผวน', vi: 'thanh lý thực (OKX) + biến động' }),
    kpiBtc: tr(language, { ko: '실시간 BTC', en: 'Live BTC', ja: 'ライブBTC', th: 'BTC สด', vi: 'BTC trực tiếp' }),
    thCoin: tr(language, { ko: '코인', en: 'Coin', ja: 'コイン', th: 'เหรียญ', vi: 'Coin' }),
    thSignal: tr(language, { ko: '신호', en: 'Signal', ja: 'シグナル', th: 'สัญญาณ', vi: 'Tín hiệu' }),
    thWhy: tr(language, { ko: '근거', en: 'Reason', ja: '根拠', th: 'เหตุผล', vi: 'Lý do' }),
    thWhen: tr(language, { ko: '트리거', en: 'Trigger', ja: 'トリガー', th: 'ทริกเกอร์', vi: 'Trigger' }),
    sigBuy: tr(language, { ko: '매수', en: 'BUY', ja: '買い', th: 'ซื้อ', vi: 'MUA' }),
    sigSell: tr(language, { ko: '매도', en: 'SELL', ja: '売り', th: 'ขาย', vi: 'BÁN' }),
    sigHold: tr(language, { ko: '관망', en: 'HOLD', ja: '様子見', th: 'ถือ', vi: 'GIỮ' }),
    dashNote: tr(language, { ko: '신호 = 정량(베이시스·RSI·OI·롱숏·실제 청산) × 정성(뉴스 감성·멘션·예측시장 확률·ETF 흐름·김치 프리미엄).', en: 'Signal = quant (basis · RSI · OI · long/short · real liquidations) × qualitative (news sentiment · mentions · prediction-market odds · ETF flows · kimchi premium).', ja: 'シグナル = 定量（ベーシス·RSI·OI·L/S·実清算）× 定性（ニュース感性·言及量·予測市場オッズ·ETFフロー·キムチプレミアム）。', th: 'สัญญาณ = เชิงปริมาณ (เบสิส · RSI · OI · L/S · ล้างพอร์ตจริง) × เชิงคุณภาพ (เซนติเมนต์ข่าว · การพูดถึง · อัตราต่อรอง · กระแส ETF · คิมชิพรีเมียม)', vi: 'Tín hiệu = định lượng (basis · RSI · OI · L/S · thanh lý thật) × định tính (tâm lý tin · lượt nhắc · tỷ lệ cược · dòng ETF · kimchi premium).' }),

    skillKicker: tr(language, { ko: '트레이딩 스킬', en: 'TRADING SKILLS', ja: 'トレーディングスキル', th: 'สกิลเทรดดิ้ง', vi: 'KỸ NĂNG GIAO DỊCH' }),
    skillH: tr(language, { ko: '조합 가능한 스킬, 하나의 워크플로', en: 'Composable skills, one workflow', ja: '組み合わせ可能なスキル、ひとつのワークフロー', th: 'สกิลประกอบกันได้ ในเวิร์กโฟลว์เดียว', vi: 'Kỹ năng lắp ghép, một quy trình' }),
    skillSub: tr(language, {
      ko: '각 기능은 작고 재사용 가능한 스킬입니다. 연결하세요: 신호 수집 → 점수화 → 시각화 → 기록 → 복기.',
      en: 'Each capability is a small, reusable skill. Chain them: collect signals → score in a sheet → visualise → journal → review.',
      ja: '各機能は小さな再利用可能スキル。連結できます：シグナル収集 → スコアリング → 可視化 → 記録 → 振り返り。',
      th: 'ทุกความสามารถคือสกิลเล็ก ๆ ที่ใช้ซ้ำได้ ต่อกันเป็นสาย: เก็บสัญญาณ → ให้คะแนน → แสดงผล → บันทึก → ทบทวน',
      vi: 'Mỗi năng lực là một kỹ năng nhỏ, tái sử dụng. Xâu chuỗi: thu tín hiệu → chấm điểm → trực quan hóa → ghi nhật ký → đánh giá.',
    }),
    skills: [
      { n: 'trading-signal-collector', d: tr(language, { ko: '정량+감성 신호를 점수화된 하나의 피드로 수집', en: 'Gathers quant + sentiment signals into one scored feed', ja: '定量+感性シグナルを1つのスコア付きフィードに収集', th: 'รวบรวมสัญญาณเชิงปริมาณ+เซนติเมนต์เป็นฟีดเดียวพร้อมคะแนน', vi: 'Gom tín hiệu định lượng + tâm lý vào một feed có điểm' }) },
      { n: 'market-breadth-analyzer', d: tr(language, { ko: '공개 CSV로 시장 폭 점수 산출 — API 키 불필요', en: 'Breadth score distribution from public CSVs — no API key', ja: '公開CSVから市場の広がりスコアを算出 — APIキー不要', th: 'กระจายคะแนนความกว้างตลาดจาก CSV สาธารณะ — ไม่ต้องใช้คีย์', vi: 'Phân bố điểm độ rộng thị trường từ CSV công khai — không cần API key' }) },
      { n: 'uptrend-analyzer', d: tr(language, { ko: '공개 데이터로 상승 추세 참여율 측정 — API 키 불필요', en: 'Uptrend participation from public data — no API key', ja: '公開データから上昇トレンド参加率を測定 — APIキー不要', th: 'การมีส่วนร่วมในแนวโน้มขึ้นจากข้อมูลสาธารณะ — ไม่ต้องใช้คีย์', vi: 'Mức tham gia xu hướng tăng từ dữ liệu công khai — không cần API key' }) },
      { n: 'position-sizer', d: tr(language, { ko: '순수 사이징 수학 — 켈리식 베팅 한도', en: 'Pure sizing math — Kelly-style bet limits', ja: '純粋なサイジング計算 — ケリー基準のベット制限', th: 'คณิตขนาดสถานะล้วน ๆ — ลิมิตเดิมพันแบบเคลลี', vi: 'Toán khối lượng thuần — giới hạn cược kiểu Kelly' }) },
      { n: 'trader-memory-core', d: tr(language, { ko: '매매 여부와 무관하게 모든 판단을 로컬 기록', en: 'Local journaling of every decision, trade or not', ja: '売買の有無を問わず全判断をローカル記録', th: 'บันทึกทุกการตัดสินใจในเครื่อง ไม่ว่าจะเทรดหรือไม่', vi: 'Nhật ký cục bộ mọi quyết định, có lệnh hay không' }) },
      { n: 'signal-postmortem', d: tr(language, { ko: '복기 프레임워크 — 지는 것은 잘라내고 되는 것만 남김', en: 'Review framework — prune what loses, keep what works', ja: '振り返りフレームワーク — 負けを削り、勝ちを残す', th: 'กรอบทบทวน — ตัดที่แพ้ เก็บที่ได้ผล', vi: 'Khung đánh giá — cắt cái thua, giữ cái hiệu quả' }) },
    ],
    caps: [
      tr(language, { ko: '7개 마켓', en: '7 markets', ja: '7マーケット', th: '7 ตลาด', vi: '7 thị trường' }),
      tr(language, { ko: '백테스트', en: 'Backtesting', ja: 'バックテスト', th: 'แบ็กเทสต์', vi: 'Backtest' }),
      tr(language, { ko: '신호 생성', en: 'Signal generation', ja: 'シグナル生成', th: 'สร้างสัญญาณ', vi: 'Tạo tín hiệu' }),
      tr(language, { ko: '주문 체결(모의+라이브)', en: 'Order execution (paper + live)', ja: '注文執行（模擬＋ライブ）', th: 'ส่งคำสั่ง (จำลอง + ไลฟ์)', vi: 'Khớp lệnh (mô phỏng + live)' }),
      tr(language, { ko: '카피 트레이딩', en: 'Copy-trading', ja: 'コピートレード', th: 'ก๊อปปี้เทรด', vi: 'Copy-trading' }),
      tr(language, { ko: '플릿 오토파일럿', en: 'Fleet auto-pilot', ja: 'フリート自動運転', th: 'ฟลีตออโตไพลอต', vi: 'Fleet tự lái' }),
      tr(language, { ko: '레버리지 1–10×', en: 'Leverage 1–10×', ja: 'レバレッジ 1–10×', th: 'เลเวอเรจ 1–10×', vi: 'Đòn bẩy 1–10×' }),
      tr(language, { ko: '거래 기록', en: 'Trade journaling', ja: '取引記録', th: 'บันทึกการเทรด', vi: 'Nhật ký giao dịch' }),
      tr(language, { ko: '리스크 관리', en: 'Risk management', ja: 'リスク管理', th: 'จัดการความเสี่ยง', vi: 'Quản trị rủi ro' }),
    ],

    riskKicker: tr(language, { ko: '리스크는 코드에 고정', en: 'RISK, HARD-CODED', ja: 'リスクはコードに固定', th: 'ความเสี่ยงถูกฝังในโค้ด', vi: 'RỦI RO ĐƯỢC MÃ HÓA CỨNG' }),
    riskH: tr(language, { ko: '생략할 수 없는 부분', en: 'The part that is not optional', ja: '省略できない部分', th: 'ส่วนที่ไม่มีข้อยกเว้น', vi: 'Phần không thể bỏ qua' }),
    risks: [
      { t: tr(language, { ko: '포지션 사이징', en: 'Position sizing', ja: 'ポジションサイジング', th: 'ขนาดสถานะ', vi: 'Khối lượng vị thế' }), d: tr(language, { ko: '켈리 기준 한도가 모든 베팅을 주문 전에 제한합니다.', en: 'Kelly-criterion style limits cap every bet before it is placed.', ja: 'ケリー基準の制限が、すべてのベットを発注前に制御します。', th: 'ลิมิตแบบเคลลีคุมทุกการเดิมพันก่อนส่งคำสั่ง', vi: 'Giới hạn kiểu Kelly chặn mọi lệnh trước khi đặt.' }) },
      { t: tr(language, { ko: '하드 손절', en: 'Hard stop-losses', ja: 'ハード損切り', th: 'จุดตัดขาดทุนตายตัว', vi: 'Cắt lỗ cứng' }), d: tr(language, { ko: '손절과 최대 손실 한도는 코드 안에 있어 감정이 건드릴 수 없습니다.', en: 'Stops and max-loss limits live in code, where emotions cannot touch them.', ja: '損切りと最大損失の上限はコード内にあり、感情は介入できません。', th: 'จุดตัดขาดทุนและลิมิตขาดทุนสูงสุดอยู่ในโค้ด อารมณ์แตะต้องไม่ได้', vi: 'Điểm dừng và giới hạn lỗ tối đa nằm trong code, cảm xúc không chạm tới.' }) },
      { t: tr(language, { ko: '서킷 브레이커', en: 'Circuit breakers', ja: 'サーキットブレーカー', th: 'เซอร์กิตเบรกเกอร์', vi: 'Ngắt mạch' }), d: tr(language, { ko: '3σ 변동성, API 지연, 조작 의심 시 자동 정지합니다.', en: 'Auto-halt on 3σ volatility, API lag or suspected manipulation.', ja: '3σ変動・API遅延・操作疑いで自動停止します。', th: 'หยุดอัตโนมัติเมื่อผันผวน 3σ, API หน่วง หรือสงสัยการปั่นราคา', vi: 'Tự dừng khi biến động 3σ, API trễ hoặc nghi thao túng.' }) },
      { t: tr(language, { ko: '이벤트 캘린더 가드', en: 'Event-calendar guard', ja: 'イベントカレンダーガード', th: 'การ์ดปฏิทินอีเวนต์', vi: 'Chắn lịch sự kiện' }), d: tr(language, { ko: 'FOMC·CPI·NFP 이벤트 창을 표시하고, 옵션으로 해당 구간의 신규 진입을 차단할 수 있습니다.', en: 'Shows FOMC/CPI/NFP event windows and can optionally block new entries inside them.', ja: 'FOMC・CPI・NFPのイベント窓を表示し、オプションでその区間の新規エントリーを遮断できます。', th: 'แสดงหน้าต่างอีเวนต์ FOMC·CPI·NFP และเลือกบล็อกการเข้าใหม่ในช่วงนั้นได้', vi: 'Hiển thị cửa sổ sự kiện FOMC·CPI·NFP và có thể tùy chọn chặn lệnh mới trong đó.' }) },
      { t: tr(language, { ko: '레버리지 세이프티', en: 'Leverage safety', ja: 'レバレッジセーフティ', th: 'ความปลอดภัยเลเวอเรจ', vi: 'An toàn đòn bẩy' }), d: tr(language, { ko: '격리 레버리지 1–10×. 스톱은 청산가 안쪽에 두고, 확신도에 따라 크기를 조절하며, 방향 균형 가드가 한쪽 쏠림을 막습니다.', en: 'Isolated leverage 1–10×. Stops sit inside the liquidation price, size scales with conviction, and a directional-balance guard stops a market stacking one way.', ja: '分離レバレッジ1–10×。ストップは清算価格の内側に置き、確信度でサイズを調整し、方向バランスガードが一方向への偏りを防ぎます。', th: 'เลเวอเรจแยก 1–10× สต็อปอยู่ในราคาล้างพอร์ต ปรับขนาดตามความมั่นใจ และการ์ดสมดุลทิศทางกันการเทหน้าเดียว', vi: 'Đòn bẩy cô lập 1–10×. Stop nằm trong giá thanh lý, khối lượng co giãn theo độ tin cậy, và bộ chắn cân bằng hướng ngăn dồn một phía.' }) },
    ],

    mmKicker: tr(language, { ko: '마켓과 모드', en: 'MARKETS & MODES', ja: 'マーケットとモード', th: 'ตลาดและโหมด', vi: 'THỊ TRƯỜNG & CHẾ ĐỘ' }),
    mmH: tr(language, { ko: '일곱 개 마켓, 네 가지 매매 방식', en: 'Seven markets. Four ways to trade.', ja: '7つのマーケット、4つの取引方法。', th: 'เจ็ดตลาด สี่วิธีเทรด', vi: 'Bảy thị trường. Bốn cách giao dịch.' }),
    markets: [
      { n: tr(language, { ko: '크립토', en: 'Crypto', ja: '暗号資産', th: 'คริปโต', vi: 'Crypto' }), sub: 'Hyperliquid', auto: true },
      { n: tr(language, { ko: '미국 주식', en: 'US stocks', ja: '米国株', th: 'หุ้นสหรัฐ', vi: 'Cổ phiếu Mỹ' }), sub: tr(language, { ko: '주식·ETF', en: 'Stocks & ETFs', ja: '株式・ETF', th: 'หุ้น·ETF', vi: 'CP & ETF' }), auto: true },
      { n: tr(language, { ko: '외환', en: 'Forex', ja: 'FX', th: 'ฟอเร็กซ์', vi: 'Forex' }), sub: tr(language, { ko: '주요 통화쌍', en: 'Major pairs', ja: '主要通貨ペア', th: 'คู่หลัก', vi: 'Cặp chính' }), auto: true },
      { n: tr(language, { ko: '선물', en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Futures' }), sub: tr(language, { ko: '지수·상품', en: 'Index & commodity', ja: '指数・商品', th: 'ดัชนี·สินค้า', vi: 'Chỉ số & hàng hóa' }), auto: true },
      { n: tr(language, { ko: '중국 A주', en: 'China A-shares', ja: '中国A株', th: 'หุ้นจีน A', vi: 'CP loại A (TQ)' }), sub: tr(language, { ko: '본토 상장', en: 'Mainland listings', ja: '本土上場', th: 'จดทะเบียนแผ่นดินใหญ่', vi: 'Niêm yết đại lục' }), auto: true },
      { n: tr(language, { ko: '예측 시장', en: 'Prediction', ja: '予測市場', th: 'ตลาดคาดการณ์', vi: 'Dự đoán' }), sub: 'Polymarket', auto: false },
      { n: tr(language, { ko: '옵션', en: 'Options', ja: 'オプション', th: 'ออปชั่น', vi: 'Quyền chọn' }), sub: tr(language, { ko: '주식 옵션', en: 'Equity options', ja: '株式オプション', th: 'ออปชั่นหุ้น', vi: 'Quyền chọn CP' }), auto: false },
    ],
    mmAuto: tr(language, { ko: '자동매매', en: 'auto-trade', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'tự động' }),
    mmManual: tr(language, { ko: '수동', en: 'manual', ja: '手動', th: 'มือ', vi: 'thủ công' }),
    modes: [
      { t: tr(language, { ko: '수동 페이퍼', en: 'Manual paper', ja: '手動ペーパー', th: 'เปเปอร์มือ', vi: 'Paper thủ công' }), d: tr(language, { ko: '$100,000 모의 원장을 직접 매매하고, 손익·저널로 복기합니다.', en: 'Trade the $100,000 simulated ledger yourself, then review with P&L and journal.', ja: '10万ドルの模擬台帳を自分で売買し、損益とジャーナルで振り返ります。', th: 'เทรดบัญชีจำลอง $100,000 ด้วยตัวเอง แล้วทบทวนด้วย P&L และบันทึก', vi: 'Tự giao dịch sổ mô phỏng $100.000, rồi xem lại bằng P&L và nhật ký.' }) },
      { t: tr(language, { ko: '규칙 자동화', en: 'Rule-based automation', ja: 'ルールベース自動化', th: 'ระบบอัตโนมัติตามกฎ', vi: 'Tự động theo luật' }), d: tr(language, { ko: '당신이 정한 규칙이 5–1440분 주기로, 최소 신뢰도 게이트와 리스크 게이트를 거쳐 실행됩니다.', en: 'Your own rules run on a 5–1440 min interval, through a min-confidence gate and the risk gate.', ja: 'あなたのルールが5–1440分周期で、最低信頼度ゲートとリスクゲートを通って実行されます。', th: 'กฎของคุณรันทุก 5–1440 นาที ผ่านประตูความเชื่อมั่นขั้นต่ำและประตูความเสี่ยง', vi: 'Quy tắc của bạn chạy theo chu kỳ 5–1440 phút, qua cổng tin cậy tối thiểu và cổng rủi ro.' }) },
      { t: tr(language, { ko: '플릿 오토파일럿', en: 'Fleet autopilot', ja: 'フリート自動運転', th: 'ฟลีตออโตไพลอต', vi: 'Fleet tự lái' }), d: tr(language, { ko: '감독되는 AI 런의 플릿이 리스크 성향 티어(균형/고수익/고위험)와 손실 워치독으로 알아서 굴러갑니다.', en: 'A supervised fleet of AI runs drives itself with risk-appetite tiers (Balance / High-Profit / High-Risk) and a loss watchdog.', ja: '監督されたAIランのフリートが、リスク志向ティア（均衡／高収益／高リスク）と損失ウォッチドッグで自走します。', th: 'ฟลีต AI ที่มีผู้ดูแลขับเคลื่อนตัวเองด้วยเทียร์ระดับความเสี่ยง (สมดุล/กำไรสูง/เสี่ยงสูง) และวอตช์ด็อกขาดทุน', vi: 'Một đội AI được giám sát tự vận hành với các mức khẩu vị rủi ro (Cân bằng / Lợi nhuận cao / Rủi ro cao) và watchdog thua lỗ.' }) },
      { t: tr(language, { ko: '카피 트레이딩', en: 'Copy-trading', ja: 'コピートレード', th: 'ก๊อปปี้เทรด', vi: 'Copy-trading' }), d: tr(language, { ko: '리더를 팔로우하면 그의 신호가 당신의 원장에 자동으로 미러링됩니다.', en: 'Follow a leader and their signals mirror onto your own ledger automatically.', ja: 'リーダーをフォローすると、そのシグナルがあなたの台帳へ自動でミラーされます。', th: 'ติดตามลีดเดอร์แล้วสัญญาณของเขาจะมิเรอร์มายังบัญชีของคุณอัตโนมัติ', vi: 'Theo dõi một leader và tín hiệu của họ tự động sao chép vào sổ của bạn.' }) },
    ],
    mmLive: tr(language, {
      ko: '실전 준비가 되면 본인 Alpaca·Binance·IBKR 계좌를 연결하세요. 라이브는 기본 비활성이며, 검증을 마치고 각 브로커 약관에 동의한 뒤에만 시작됩니다 — AI 자동 런은 페이퍼에 그대로 남습니다.',
      en: 'Ready for real money? Connect your own Alpaca, Binance, or IBKR account. Live is off by default and starts only after you verify and accept each broker’s terms — AI auto-runs stay on paper.',
      ja: '実弾の準備ができたら、本人のAlpaca・Binance・IBKR口座を接続。ライブは既定で無効、検証を終え各社の規約に同意した後にのみ開始します — AI自動ランはペーパーのままです。',
      th: 'พร้อมเงินจริงไหม? เชื่อมบัญชี Alpaca, Binance หรือ IBKR ของคุณเอง ไลฟ์ปิดโดยค่าเริ่มต้น และเริ่มเฉพาะหลังยืนยันและยอมรับข้อกำหนดของแต่ละโบรกเกอร์ — การรันอัตโนมัติของ AI ยังอยู่บนเปเปอร์',
      vi: 'Sẵn sàng tiền thật? Kết nối tài khoản Alpaca, Binance hoặc IBKR của bạn. Live tắt mặc định và chỉ bắt đầu sau khi bạn xác minh và chấp nhận điều khoản từng broker — các lần AI tự chạy vẫn ở paper.',
    }),

    ctaH: tr(language, { ko: '모의 자금 $100,000. 실제 리스크는 0.', en: '$100,000 of paper money. Zero real risk.', ja: '10万ドルの模擬資金。実リスクはゼロ。', th: 'เงินจำลอง $100,000 ความเสี่ยงจริงเป็นศูนย์', vi: '$100.000 tiền mô phỏng. Rủi ro thật bằng không.' }),
    ctaSub: tr(language, { ko: '한 번만 설정하세요. AI가 측정하고 판단하고 기록합니다 — 당신은 검토만.', en: 'Configure once. The AI measures, decides and journals — you review.', ja: '一度設定すれば、AIが測定・判断・記録し、あなたは確認するだけ。', th: 'ตั้งค่าครั้งเดียว AI วัด ตัดสินใจ และบันทึก — คุณแค่ทบทวน', vi: 'Cấu hình một lần. AI đo, quyết định và ghi lại — bạn chỉ xem xét.' }),

    legal: tr(language, {
      ko: 'Sooppiy는 연구·교육용 소프트웨어입니다. 기본적으로 모든 거래는 모의이며 실제 자금이 위험에 노출되지 않습니다. 라이브 브로커 거래는 선택 사항이며 기본 비활성 상태입니다 — 사용자가 직접 연결한 브로커 계좌에서, 각 브로커 약관에 동의한 후에만 실행되고, AI 자동 실행은 모의 원장에 남습니다. 시장 데이터는 정보 제공 목적이며, 이 사이트의 어떤 내용도 투자 자문이 아닙니다.',
      en: 'Sooppiy is research and education software. By default all trading is simulated — no real funds are at risk. Live brokerage trading is optional and off by default: it runs only on a brokerage account you connect yourself, after you accept each broker’s terms, and AI auto-runs stay on the simulated ledger. Market data is for information only. Nothing on this site is investment advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。既定ではすべての取引は模擬で、実資金はリスクにさらされません。ライブのブローカー取引は任意で既定は無効です — 本人が接続したブローカー口座で、各社の規約に同意した後にのみ実行され、AIの自動実行は模擬台帳に残ります。市場データは情報提供のみで、投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์วิจัยและการศึกษา โดยค่าเริ่มต้นทุกการเทรดเป็นแบบจำลอง ไม่มีเงินจริงเสี่ยง การเทรดไลฟ์ผ่านโบรกเกอร์เป็นทางเลือกและปิดอยู่โดยค่าเริ่มต้น — ทำงานเฉพาะบนบัญชีโบรกเกอร์ที่คุณเชื่อมเอง หลังยอมรับข้อกำหนดของแต่ละโบรกเกอร์ และการรันอัตโนมัติของ AI ยังอยู่บนบัญชีจำลอง ข้อมูลตลาดเพื่อการให้ข้อมูลเท่านั้น ไม่ใช่คำแนะนำการลงทุน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Mặc định mọi giao dịch đều mô phỏng — không tiền thật nào chịu rủi ro. Giao dịch live qua broker là tùy chọn và tắt mặc định: chỉ chạy trên tài khoản broker bạn tự kết nối, sau khi chấp nhận điều khoản từng broker, và các lần AI tự chạy vẫn ở sổ cái mô phỏng. Dữ liệu thị trường chỉ để tham khảo. Không nội dung nào là lời khuyên đầu tư.',
    }),
  }

  const pillBtn: any = { fontFamily: V.sans, fontWeight: 600, fontSize: 14.5, textDecoration: 'none', borderRadius: 8, padding: '11px 22px', display: 'inline-block' }
  const sigPill = (sig: string) => {
    const map: any = {
      buy: { bg: 'var(--up-soft, rgba(45,158,107,0.10))', c: V.up, label: `▲ ${T.sigBuy}` },
      sell: { bg: 'var(--down-soft, rgba(139,58,42,0.10))', c: V.down, label: `▼ ${T.sigSell}` },
      hold: { bg: V.bg2, c: V.mut, label: `■ ${T.sigHold}` },
    }
    const m = map[sig]
    return <span style={{ fontFamily: V.mono, fontSize: 11.5, fontWeight: 600, background: m.bg, color: m.c, borderRadius: 999, padding: '4px 10px', whiteSpace: 'nowrap' }}>{m.label}</span>
  }

  return (
    <div style={{ minHeight: '100vh', background: V.bg, color: V.ink, fontFamily: V.sans, lineHeight: 1.55 }}>

      {/* ── topbar ── */}
      {/* Mobile: the row can't fit logo + wordmark + 5 lang pills + two auth buttons,
          so below 700px we keep only 가입하기 (signup) and compact the rest. */}
      <style>{`
        .mkt-topbar-row { display: flex; align-items: center; gap: 12px; height: 62px; }
        .mkt-auth { white-space: nowrap; flex-shrink: 0; }
        @media (max-width: 700px) {
          .mkt-topbar-row { gap: 8px; height: 54px; }
          .mkt-login { display: none !important; }
          .mkt-signup { font-size: 13px !important; padding: 7px 12px !important; }
          .mkt-langs button { font-size: 10.5px !important; padding: 3px 5px !important; }
          .mkt-wordmark { font-size: 17px !important; }
          .mkt-logo { width: 32px; height: 32px; }
        }
        @media (max-width: 430px) {
          .mkt-wordmark { display: none; }
        }
      `}</style>
      <header style={{ position: 'sticky', top: 0, zIndex: 20, background: V.card, borderBottom: `1px solid ${V.line}` }}>
        <div className="mkt-topbar-row" style={{ ...wrap }}>
          <img src="/logo.svg" alt="" width={46} height={46} className="mkt-logo" style={{ display: 'block', flexShrink: 0 }} />
          <span className="mkt-wordmark" style={{ fontFamily: V.display, fontSize: 21, fontWeight: 700 }}>Sooppiy</span>
          <span className="mkt-langs" style={{ marginLeft: 'auto', display: 'flex', gap: 2, border: `1px solid ${V.line}`, borderRadius: 999, padding: '3px 6px', flexShrink: 0 }}>
            {LANGS.map(([code, label]) => (
              <button key={code} onClick={() => setLanguage(code)}
                style={{ background: language === code ? V.accent : 'none', color: language === code ? V.accentOn : V.mut, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, padding: '4px 9px', borderRadius: 999, fontFamily: V.sans }}>{label}</button>
            ))}
          </span>
          <Link to="/login" className="mkt-auth mkt-login" style={{ ...pillBtn, color: V.ink, padding: '9px 16px' }}>{T.login}</Link>
          <Link to="/register" className="mkt-auth mkt-signup" style={{ ...pillBtn, color: V.accentOn, background: V.accent, padding: '9px 18px' }}>{T.signup}</Link>
        </div>
      </header>

      {/* ── hero ── */}
      <section style={{ position: 'relative', overflow: 'hidden', borderBottom: `1px solid ${V.line}`, padding: '64px 0 56px' }}>
        <HeroWaveBackground />
        {/* readability scrim over the animated mesh, strongest where the copy sits */}
        <div aria-hidden style={{ position: 'absolute', inset: 0, background: `linear-gradient(90deg, color-mix(in srgb, ${V.bg} 78%, transparent) 0%, color-mix(in srgb, ${V.bg} 35%, transparent) 48%, transparent 78%)` }} />
        <div style={{ ...wrap, position: 'relative', zIndex: 1 }}>
          <div style={kicker}>{T.heroKicker}</div>
          <h1 style={{ fontFamily: V.display, fontWeight: 800, fontSize: 'clamp(38px,5.6vw,66px)', lineHeight: 1.04, letterSpacing: '-0.02em', margin: '14px 0 18px', maxWidth: '18ch' }}>
            <span style={{ background: `linear-gradient(92deg, ${V.ink} 8%, #e8912d 62%, #f7b955 96%)`, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', WebkitTextFillColor: 'transparent' }}>{T.heroH1a}</span><br /><em style={{ fontStyle: 'normal', color: V.accent }}>{T.heroH1b}</em>
          </h1>
          <p style={{ fontSize: 17, color: V.mut, maxWidth: '58ch', margin: '0 0 26px' }}>{T.heroSub}</p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <Link to="/register" style={{ ...pillBtn, background: V.accent, color: V.accentOn }}>{T.ctaStart}</Link>
            <Link to="/leaderboard" style={{ ...pillBtn, color: V.ink, border: `1.5px solid ${V.lineStrong}`, background: V.card }}>{T.ctaBoard}</Link>
          </div>
          <p style={{ fontFamily: V.mono, fontSize: 11.5, color: V.faint, marginTop: 20 }}>{T.heroNote}</p>
        </div>
      </section>

      {/* ── six signal elements — guide §0 flow diagram ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.readKicker}</div>
          <h2 style={h2S}>{T.readH}</h2>
          {/* Verbatim reproduction of guide.html §0 (10-step strip, pipeline
              SVG at original geometry, KPI row), localized; FlowParticles
              animates the connectors in the same coordinate space. */}
          {(() => {
            const L = (ko: string, en: string, ja: string, th: string, vi: string) => tr(language, { ko, en, ja, th, vi })
            const svT: any = { font: `600 12px ${V.sans}`, fill: V.ink }
            const svS: any = { font: `500 10.5px ${V.sans}`, fill: V.mut }
            const svM: any = { font: `600 10px ${V.mono}`, fill: V.faint }
            const svLb: any = { font: `700 10px ${V.sans}`, fill: V.faint, letterSpacing: '.08em' }
            const GOOD = 'var(--up, #0ca30c)', BAD = 'var(--down, #d03b3b)', YELL = '#cf8f00'
            const accF = `color-mix(in srgb, ${V.accent} 12%, ${V.card})`
            const goodF = `color-mix(in srgb, ${GOOD} 12%, ${V.card})`
            const warnF = `color-mix(in srgb, ${YELL} 14%, ${V.card})`
            const steps = [
              L('데이터 수집', 'Data collection', 'データ収集', 'เก็บข้อมูล', 'Thu thập dữ liệu'),
              L('종목 발굴', 'Coin discovery', '銘柄発掘', 'ค้นหาเหรียญ', 'Tìm coin'),
              L('정량 분석', 'Quant analysis', '定量分析', 'วิเคราะห์เชิงปริมาณ', 'Phân tích định lượng'),
              L('심리 분석', 'Psych analysis', '心理分析', 'วิเคราะห์จิตวิทยา', 'Phân tích tâm lý'),
              L('신호 융합', 'Signal fusion', 'シグナル融合', 'ผสานสัญญาณ', 'Hợp nhất tín hiệu'),
              L('AI 4-분석가', 'AI 4 analysts', 'AI 4アナリスト', 'นักวิเคราะห์ AI 4', '4 nhà phân tích AI'),
              L('자동매매 규칙', 'Automation rules', '自動売買ルール', 'กฎเทรดอัตโนมัติ', 'Quy tắc tự động'),
              L('리스크 게이트', 'Risk gate', 'リスクゲート', 'ประตูความเสี่ยง', 'Cổng rủi ro'),
              L('체결·SL/TP', 'Fill · SL/TP', '約定·SL/TP', 'เติมคำสั่ง·SL/TP', 'Khớp · SL/TP'),
              L('기록·복기', 'Journal & review', '記録・振り返り', 'บันทึก·ทบทวน', 'Nhật ký & xem lại'),
            ]
            const kpis = [
              { lb: L('체결 방식', 'Execution mode', '約定方式', 'โหมดดำเนินการ', 'Chế độ khớp lệnh'), vl: L('페이퍼 먼저', 'Paper first', 'まず模擬', 'เปเปอร์ก่อน', 'Paper trước'), hint: L('검증 후 본인 브로커에서 라이브 선택', 'live optional on your broker, after you verify', '検証後に本人ブローカーで任意ライブ', 'ไลฟ์ทางเลือกบนโบรกเกอร์คุณ หลังยืนยัน', 'live tùy chọn trên broker của bạn, sau khi xác minh') },
              { lb: L('리스크 게이트', 'Risk gate', 'リスクゲート', 'ประตูความเสี่ยง', 'Cổng rủi ro'), vl: L('3중 검사', 'Triple check', '三重チェック', 'ตรวจ 3 ชั้น', 'Kiểm tra 3 lớp'), hint: L('켈리 → 한도 → 브레이커', 'Kelly → limits → breaker', 'ケリー → 上限 → ブレーカー', 'เคลลี → ลิมิต → เบรกเกอร์', 'Kelly → hạn mức → breaker') },
              { lb: L('테스트', 'Tests', 'テスト', 'เทสต์', 'Kiểm thử'), vl: '1,800+', hint: L('시그널·실행·리스크 커버리지', 'signal · execution · risk coverage', 'シグナル・実行・リスクの網羅', 'ครอบคลุมสัญญาณ·ดำเนินการ·ความเสี่ยง', 'phủ tín hiệu · thực thi · rủi ro') },
              { lb: L('백그라운드 태스크', 'Background tasks', 'バックグラウンドタスク', 'งานเบื้องหลัง', 'Tác vụ nền'), vl: '32' + L('개', '', '件', '', ''), hint: 'risk_watcher · psych · scanner · fleet' },
            ]
            return (<>
              <p style={{ fontSize: 14, color: V.mut, margin: '4px 0 14px', maxWidth: '80ch' }}>
                {L('데이터 수집부터 복기까지. 모든 매매는 페이퍼(시뮬레이터) 계정에서만 체결되고, 모든 단계는 env 플래그로 격리되며, 외부 소스 장애는 해당 부분만 조용히 빠지는 fail-soft 구조입니다.',
                  'From data collection to review. Every trade fills only on the paper (simulator) account, every stage is isolated behind env flags, and an external-source outage silently drops only its own part — fail-soft by design.',
                  'データ収集から振り返りまで。全ての売買はペーパー（シミュレーター）口座のみで約定し、各段階はenvフラグで隔離され、外部ソース障害は該当部分だけが静かに抜けるfail-soft構造です。',
                  'ตั้งแต่เก็บข้อมูลจนถึงทบทวน ทุกการเทรดเกิดในบัญชีเปเปอร์ (จำลอง) เท่านั้น ทุกขั้นถูกแยกด้วย env flag และเมื่อแหล่งข้อมูลภายนอกล่ม เฉพาะส่วนนั้นจะหายไปเงียบ ๆ — โครงสร้าง fail-soft',
                  'Từ thu thập dữ liệu đến xem lại. Mọi giao dịch chỉ khớp trên tài khoản paper (mô phỏng), mọi giai đoạn được cách ly bằng cờ env, và sự cố nguồn ngoài chỉ làm rơi phần đó một cách im lặng — thiết kế fail-soft.')}
              </p>
              <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(88px, 1fr))', margin: '14px 0' }}>
                {steps.map((s, i) => (
                  <div key={i} style={{ background: V.card, border: `1px solid ${V.line}`, borderRadius: 10, padding: '9px 8px', textAlign: 'center' }}>
                    <b style={{ display: 'block', fontSize: 11, color: V.accent, fontVariantNumeric: 'tabular-nums' }}>STEP {i + 1}</b>
                    <span style={{ fontSize: 12, fontWeight: 700, lineHeight: 1.3, display: 'block', marginTop: 2 }}>{s}</span>
                  </div>
                ))}
              </div>
              <div style={{ ...cardS, padding: 14, overflowX: 'auto', margin: '14px 0' }}>
                <div style={{ position: 'relative', minWidth: 680 }}>
                  <svg viewBox={`0 0 ${FLOW_W} ${FLOW_H}`} style={{ display: 'block', width: '100%', height: 'auto' }} role="img" aria-label={T.readH}>
                    <defs>
                      <marker id="mp-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={V.lineStrong} /></marker>
                      <marker id="mp-arA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={V.accent} /></marker>
                      <marker id="mp-arG" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={GOOD} /></marker>
                      <marker id="mp-arR" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={BAD} /></marker>
                    </defs>
                    {/* band 1: sources */}
                    <text x={16} y={24} style={svLb}>{L('외부 데이터 소스 (전부 무키 검증 완료)', 'EXTERNAL DATA SOURCES (ALL VERIFIED KEYLESS)', '外部データソース（全て無キー検証済み）', 'แหล่งข้อมูลภายนอก (ตรวจสอบแบบไร้คีย์แล้ว)', 'NGUỒN DỮ LIỆU NGOÀI (ĐÃ KIỂM CHỨNG KHÔNG CẦN KEY)')}</text>
                    <rect x={16} y={34} width={172} height={46} rx={9} fill={V.bg2} stroke={V.line} />
                    <text x={102} y={53} textAnchor="middle" style={svT}>OKX</text>
                    <text x={102} y={68} textAnchor="middle" style={svS}>{L('캔들·펀딩·OI·롱숏·청산', 'candles·funding·OI·L/S·liq.', 'ローソク足・資金調達率・OI・L/S・清算', 'แท่งเทียน·ฟันดิง·OI·L/S·ล้างพอร์ต', 'nến·funding·OI·L/S·thanh lý')}</text>
                    <rect x={204} y={34} width={172} height={46} rx={9} fill={V.bg2} stroke={V.line} />
                    <text x={290} y={53} textAnchor="middle" style={svT}>alternative.me</text>
                    <text x={290} y={68} textAnchor="middle" style={svS}>{L('공포·탐욕 지수 + 이력', 'Fear & Greed index + history', 'Fear&Greed指数＋履歴', 'ดัชนี F&G + ประวัติ', 'chỉ số F&G + lịch sử')}</text>
                    <rect x={392} y={34} width={172} height={46} rx={9} fill={V.bg2} stroke={V.line} />
                    <text x={478} y={53} textAnchor="middle" style={svT}>StockTwits · Polymarket</text>
                    <text x={478} y={68} textAnchor="middle" style={svS}>{L('군중 감성·예측시장 Δodds', 'crowd sentiment · Δodds', '群衆感情・予測市場Δodds', 'อารมณ์ฝูงชน · Δodds', 'tâm lý đám đông · Δodds')}</text>
                    <rect x={580} y={34} width={172} height={46} rx={9} fill={V.bg2} stroke={V.line} />
                    <text x={666} y={53} textAnchor="middle" style={svT}>SoSoValue · Upbit</text>
                    <text x={666} y={68} textAnchor="middle" style={svS}>{L('ETF 실흐름·김치 프리미엄', 'real ETF flows · kimchi premium', 'ETF実フロー・キムチプレミアム', 'กระแส ETF จริง · คิมชิพรีเมียม', 'dòng ETF thật · kimchi premium')}</text>
                    <rect x={768} y={34} width={176} height={46} rx={9} fill={V.bg2} stroke={V.line} />
                    <text x={856} y={53} textAnchor="middle" style={svT}>AV · FRED · FinnHub</text>
                    <text x={856} y={68} textAnchor="middle" style={svS}>{L('뉴스·매크로·DXY', 'news · macro · DXY', 'ニュース・マクロ・DXY', 'ข่าว·มหภาค·DXY', 'tin tức · vĩ mô · DXY')}</text>
                    {[102, 290, 478, 666, 856].map(x => <path key={x} d={`M${x} 80 V108`} stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />)}
                    {/* band 2: collectors */}
                    <rect x={16} y={110} width={220} height={58} rx={9} fill={accF} stroke={V.accent} />
                    <text x={126} y={130} textAnchor="middle" style={svT}>{L('STEP 2 · 스캐너', 'STEP 2 · Scanner', 'STEP 2 · スキャナー', 'STEP 2 · สแกนเนอร์', 'STEP 2 · Máy quét')}</text>
                    <text x={126} y={145} textAnchor="middle" style={svS}>{L('거래량 급증 ×2 · 멘션 +100%', 'volume surge ×2 · mentions +100%', '出来高急増×2・言及+100%', 'ปริมาณพุ่ง ×2 · การพูดถึง +100%', 'khối lượng ×2 · nhắc +100%')}</text>
                    <text x={126} y={159} textAnchor="middle" style={svM}>scanner.py · 1h</text>
                    <rect x={252} y={110} width={220} height={58} rx={9} fill={accF} stroke={V.accent} />
                    <text x={362} y={130} textAnchor="middle" style={svT}>{L('STEP 3 · 정량(퀀트)', 'STEP 3 · Quant', 'STEP 3 · 定量(クオンツ)', 'STEP 3 · ควอนต์', 'STEP 3 · Định lượng')}</text>
                    <text x={362} y={145} textAnchor="middle" style={svS}>RSI·σ·{L('펀딩·베이시스·OI·롱숏', 'funding·basis·OI·long/short', '資金調達率・ベーシス・OI・L/S', 'ฟันดิง·เบสิส·OI·L/S', 'funding·basis·OI·L/S')}</text>
                    <text x={362} y={159} textAnchor="middle" style={svM}>quant_crypto.py · {L('온디맨드', 'on-demand', 'オンデマンド', 'ออนดีมานด์', 'theo yêu cầu')}</text>
                    <rect x={488} y={110} width={220} height={58} rx={9} fill={accF} stroke={V.accent} />
                    <text x={598} y={130} textAnchor="middle" style={svT}>{L('STEP 4 · 심리 피드', 'STEP 4 · Psych feed', 'STEP 4 · 心理フィード', 'STEP 4 · ฟีดจิตวิทยา', 'STEP 4 · Nguồn tâm lý')}</text>
                    <text x={598} y={145} textAnchor="middle" style={svS}>{L('F&G·감성 스파이크·실제 청산', 'F&G · sentiment spikes · real liq.', 'F&G・感情スパイク・実清算', 'F&G·สไปก์อารมณ์·ล้างพอร์ตจริง', 'F&G · tâm lý tăng vọt · thanh lý thật')}</text>
                    <text x={598} y={159} textAnchor="middle" style={svM}>psych_feed.py · 1h</text>
                    <rect x={724} y={110} width={220} height={58} rx={9} fill={V.bg2} stroke={V.line} />
                    <text x={834} y={130} textAnchor="middle" style={svT}>{L('뉴스 · 매크로 인텔', 'News · macro intel', 'ニュース・マクロインテル', 'ข่าว · อินเทลมหภาค', 'Tin tức · vĩ mô')}</text>
                    <text x={834} y={145} textAnchor="middle" style={svS}>{L('뉴스 감성·ETF 실흐름·이벤트 캘린더', 'news sentiment · real ETF · event calendar', 'ニュース感情・ETF実フロー・イベント暦', 'เซนติเมนต์ข่าว·ETF จริง·ปฏิทินอีเวนต์', 'tâm lý tin · ETF thật · lịch sự kiện')}</text>
                    <text x={834} y={159} textAnchor="middle" style={svM}>market_intel.py · {L('주기 갱신', 'periodic refresh', '定期更新', 'รีเฟรชตามรอบ', 'làm mới định kỳ')}</text>
                    {[126, 362, 598, 834].map(x => <path key={x} d={`M${x} 168 V196`} stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />)}
                    {/* snapshot store */}
                    <rect x={16} y={198} width={928} height={40} rx={9} fill={V.card} stroke={V.lineStrong} strokeDasharray="5 4" />
                    <text x={480} y={222} textAnchor="middle" style={svT}>{L('스냅샷 저장소', 'Snapshot store', 'スナップショット保存所', 'คลังสแนปช็อต', 'Kho snapshot')} — scanner · psych · market_news/macro/etf/stock_analysis ({L('모든 판단의 증거가 DB에 남음', 'evidence of every decision stays in the DB', '全判断の証拠がDBに残る', 'หลักฐานทุกการตัดสินใจอยู่ใน DB', 'bằng chứng mọi quyết định lưu trong DB')})</text>
                    <path d="M240 238 V266" stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />
                    <path d="M720 238 V266" stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />
                    {/* band 3: fusion + AI */}
                    <rect x={60} y={268} width={360} height={66} rx={9} fill={accF} stroke={V.accent} />
                    <text x={240} y={288} textAnchor="middle" style={svT}>{L('STEP 5 · 신호 융합', 'STEP 5 · Signal fusion', 'STEP 5 · シグナル融合', 'STEP 5 · ผสานสัญญาณ', 'STEP 5 · Hợp nhất tín hiệu')}</text>
                    <text x={240} y={304} textAnchor="middle" style={svS}>{L('0.5·퀀트 + 0.3·감성 + 0.2·심리 (심리 상한 0.3)', '0.5·quant + 0.3·sentiment + 0.2·psych (psych cap 0.3)', '0.5·クオンツ+0.3·感情+0.2·心理（心理上限0.3）', '0.5·ควอนต์ + 0.3·อารมณ์ + 0.2·จิต (จำกัด 0.3)', '0.5·quant + 0.3·cảm xúc + 0.2·tâm lý (trần 0.3)')}</text>
                    <text x={240} y={320} textAnchor="middle" style={svM}>signal_fusion.py · GET /api/market-intel/fusion</text>
                    <rect x={540} y={268} width={360} height={66} rx={9} fill={accF} stroke={V.accent} />
                    <text x={720} y={288} textAnchor="middle" style={svT}>{L('STEP 6 · AI 4-분석가 + 트레이더 토론', 'STEP 6 · AI 4 analysts + trader debate', 'STEP 6 · AI 4アナリスト＋トレーダー討論', 'STEP 6 · นักวิเคราะห์ AI 4 + ดีเบต', 'STEP 6 · 4 nhà phân tích AI + tranh luận')}</text>
                    <text x={720} y={304} textAnchor="middle" style={svS}>{L('뉴스·감성·펀더멘털/매크로·기술 → BUY/SELL/HOLD + 신뢰도', 'news·sentiment·fundamental/macro·technical → BUY/SELL/HOLD + confidence', 'ニュース・感情・ファンダ/マクロ・技術 → BUY/SELL/HOLD＋信頼度', 'ข่าว·อารมณ์·พื้นฐาน/มหภาค·เทคนิค → BUY/SELL/HOLD + ความเชื่อมั่น', 'tin·cảm xúc·cơ bản/vĩ mô·kỹ thuật → BUY/SELL/HOLD + độ tin cậy')}</text>
                    <text x={720} y={320} textAnchor="middle" style={svM}>analysis_agents.py · {L('LLM 또는 룰 기반 폴백', 'LLM or rule-based fallback', 'LLMまたはルールベースのフォールバック', 'LLM หรือ fallback แบบกฎ', 'LLM hoặc fallback theo luật')}</text>
                    {/* band 4: automation → gate → execution */}
                    <path d="M240 334 V360 H180 V386" stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />
                    <path d="M720 334 V360 H180" stroke={V.lineStrong} strokeWidth={1.4} fill="none" />
                    <rect x={40} y={388} width={280} height={66} rx={9} fill={V.card} stroke={V.lineStrong} />
                    <text x={180} y={408} textAnchor="middle" style={svT}>{L('STEP 7 · 자동매매 규칙 (사용자 설정)', 'STEP 7 · Automation rules (user-set)', 'STEP 7 · 自動売買ルール（ユーザー設定）', 'STEP 7 · กฎเทรดอัตโนมัติ (ผู้ใช้ตั้ง)', 'STEP 7 · Quy tắc tự động (người dùng đặt)')}</text>
                    <text x={180} y={424} textAnchor="middle" style={svS}>{L('주기 5–1440분 · 최소 신뢰도 0.65 · 자동체결 on/off', 'interval 5–1440min · min confidence 0.65 · auto-execute on/off', '周期5–1440分・最低信頼度0.65・自動約定on/off', 'รอบ 5–1440 นาที · เชื่อมั่นขั้นต่ำ 0.65 · เทรดอัตโนมัติ on/off', 'chu kỳ 5–1440ph · tin cậy tối thiểu 0.65 · tự khớp on/off')}</text>
                    <text x={180} y={440} textAnchor="middle" style={svM}>automation.py · 60s {L('틱', 'tick', 'ティック', 'ติ๊ก', 'tick')}</text>
                    <rect x={368} y={388} width={256} height={66} rx={9} fill={warnF} stroke={YELL} />
                    <text x={496} y={408} textAnchor="middle" style={svT}>{L('STEP 8 · 리스크 게이트', 'STEP 8 · Risk gate', 'STEP 8 · リスクゲート', 'STEP 8 · ประตูความเสี่ยง', 'STEP 8 · Cổng rủi ro')}</text>
                    <text x={496} y={424} textAnchor="middle" style={svS}>{L('① 켈리 사이징 → ② 한도 → ③ 브레이커', '① Kelly sizing → ② limits → ③ breaker', '① ケリーサイジング → ② 上限 → ③ ブレーカー', '① ไซซิ่งเคลลี → ② ลิมิต → ③ เบรกเกอร์', '① Kelly sizing → ② hạn mức → ③ breaker')}</text>
                    <text x={496} y={440} textAnchor="middle" style={svM}>risk_engine.py · {L('전 주문 통과 필수', 'every order must pass', '全注文の通過必須', 'ทุกคำสั่งต้องผ่าน', 'mọi lệnh phải qua')}</text>
                    <rect x={672} y={388} width={272} height={66} rx={9} fill={goodF} stroke={GOOD} />
                    <text x={808} y={408} textAnchor="middle" style={svT}>{L('STEP 9 · 페이퍼 체결', 'STEP 9 · Paper execution', 'STEP 9 · ペーパー約定', 'STEP 9 · ดำเนินการเปเปอร์', 'STEP 9 · Khớp lệnh paper')}</text>
                    <text x={808} y={424} textAnchor="middle" style={svS}>{L('SL −5% / TP +10% 자동 등록 · 30초 워처', 'SL −5% / TP +10% auto-set · 30s watcher', 'SL−5%／TP+10%自動登録・30秒ウォッチャー', 'SL −5% / TP +10% อัตโนมัติ · วอตเชอร์ 30 วิ', 'SL −5% / TP +10% tự đặt · watcher 30s')}</text>
                    <text x={808} y={440} textAnchor="middle" style={svM}>{L('시뮬레이터 계정만 · 실계좌 체결 없음', 'simulator account only · no real orders', 'シミュレーター口座のみ・実口座約定なし', 'บัญชีจำลองเท่านั้น · ไม่มีคำสั่งจริง', 'chỉ tài khoản mô phỏng · không lệnh thật')}</text>
                    <path d="M320 421 H366" stroke={V.accent} strokeWidth={1.6} fill="none" markerEnd="url(#mp-arA)" />
                    <path d="M624 421 H670" stroke={GOOD} strokeWidth={1.6} fill="none" markerEnd="url(#mp-arG)" />
                    <text x={643} y={412} textAnchor="middle" style={{ ...svM, fill: GOOD }}>PASS</text>
                    <path d="M496 454 V488" stroke={BAD} strokeWidth={1.6} fill="none" markerEnd="url(#mp-arR)" />
                    <text x={522} y={474} style={{ ...svM, fill: BAD }}>{L('FAIL → 사유 기록', 'FAIL → reason logged', 'FAIL → 理由記録', 'FAIL → บันทึกเหตุผล', 'FAIL → ghi lý do')}</text>
                    {/* band 5: journal */}
                    <path d="M808 454 V488" stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />
                    <rect x={368} y={490} width={256} height={54} rx={9} fill={V.card} stroke={V.lineStrong} />
                    <text x={496} y={510} textAnchor="middle" style={svT}>{L('STEP 10 · 저널 · 복기', 'STEP 10 · Journal & review', 'STEP 10 · 記録・振り返り', 'STEP 10 · บันทึก·ทบทวน', 'STEP 10 · Nhật ký & xem lại')}</text>
                    <text x={496} y={526} textAnchor="middle" style={svS}>automation_runs · signals {L('원장', 'ledger', '台帳', 'บัญชีแยกประเภท', 'sổ cái')} · {L('실험 이벤트', 'experiment events', '実験イベント', 'อีเวนต์ทดลอง', 'sự kiện thử nghiệm')}</text>
                    <rect x={672} y={490} width={272} height={54} rx={9} fill={V.card} stroke={V.lineStrong} />
                    <text x={808} y={510} textAnchor="middle" style={svT}>{L('포지션 · 손익 추적', 'Position & P&L tracking', 'ポジション・損益追跡', 'ติดตามสถานะ·กำไรขาดทุน', 'Theo dõi vị thế & P&L')}</text>
                    <text x={808} y={526} textAnchor="middle" style={svS}>{L('가격 폴링 → 평가손익 · SL/TP 워처 감시', 'price polling → unrealized P&L · SL/TP watcher', '価格ポーリング → 評価損益・SL/TPウォッチャー', 'โพลราคา → P&L · วอตเชอร์ SL/TP', 'poll giá → P&L tạm tính · watcher SL/TP')}</text>
                    <path d="M672 517 H626" stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />
                    {/* dashboard */}
                    <path d="M496 544 V572" stroke={V.lineStrong} strokeWidth={1.4} fill="none" markerEnd="url(#mp-ar)" />
                    <rect x={280} y={574} width={432} height={38} rx={9} fill={accF} stroke={V.accent} />
                    <text x={496} y={597} textAnchor="middle" style={svT}>{L('시그널 보드 대시보드 + 알림 — 사람이 항상 검증 가능', 'Signal board dashboard + alerts — humans can always verify', 'シグナルボード＋アラート — 人がいつでも検証可能', 'แดชบอร์ด + แจ้งเตือน — คนตรวจสอบได้เสมอ', 'Bảng tín hiệu + cảnh báo — con người luôn kiểm chứng được')}</text>
                  </svg>
                  <FlowParticles />
                </div>
              </div>
              <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', margin: '14px 0' }}>
                {kpis.map((k, i) => (
                  <div key={i} style={{ background: V.card, border: `1px solid ${V.line}`, borderRadius: 12, padding: '11px 13px' }}>
                    <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.05em', color: V.faint, fontWeight: 700 }}>{k.lb}</div>
                    <div style={{ fontSize: 19, fontWeight: 800, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>{k.vl}</div>
                    <div style={{ fontSize: 11, color: V.faint }}>{k.hint}</div>
                  </div>
                ))}
              </div>
            </>)
          })()}
          {/* six signal elements — full descriptions */}
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', marginTop: 18 }}>
            {T.read.map((r, i) => (
              <div key={i} style={{ ...cardS, padding: '15px 17px' }}>
                <div style={{ fontFamily: V.mono, fontSize: 11, fontWeight: 700, color: V.accent, fontVariantNumeric: 'tabular-nums', marginBottom: 6 }}>{String(i + 1).padStart(2, '0')}</div>
                <div style={{ fontWeight: 700, fontSize: 16.5, marginBottom: 6 }}>{r.t}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{r.d}</div>
              </div>
            ))}
          </div>
          <Link to="/docs/guide" style={{ display: 'inline-block', marginTop: 16, fontSize: 13.5, fontWeight: 600, color: V.accent, textDecoration: 'none' }}>
            {tr(language, { ko: '전체 파이프라인 가이드 보기 (로그인) →', en: 'Read the full pipeline guide (sign in) →', ja: 'パイプライン全体ガイドを見る（ログイン）→', th: 'ดูคู่มือไปป์ไลน์ฉบับเต็ม (เข้าสู่ระบบ) →', vi: 'Xem hướng dẫn pipeline đầy đủ (đăng nhập) →' })}
          </Link>
        </div>
      </section>

      {/* ── psychology proxies ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.psyKicker}</div>
          <h2 style={h2S}>{T.psyH}</h2>
          <div style={{ ...cardS, padding: 0, marginTop: 18, overflow: 'hidden' }}>
            {T.psyRows.map((r, i) => (
              <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'baseline', padding: '14px 20px', borderBottom: i < T.psyRows.length - 1 ? `1px solid ${V.line}` : 'none' }}>
                <span style={{ fontFamily: V.mono, fontSize: 12.5, fontWeight: 600, color: V.accent, width: 150 }}>{r.k}</span>
                <span style={{ fontSize: 14.5, color: V.ink, flex: 1, minWidth: 240 }}>{r.v}</span>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13.5, color: V.mut, marginTop: 14, maxWidth: '72ch' }}>{T.psyNote}</p>
        </div>
      </section>

      {/* ── dashboard preview ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <div style={kicker}>{T.dashKicker}</div>
            <span style={{ fontFamily: V.mono, fontSize: 10.5, color: V.faint, border: `1px solid ${V.line}`, borderRadius: 999, padding: '2px 9px' }}>{T.liveTag}</span>
          </div>
          <h2 style={h2S}>{T.dashH}</h2>

          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginTop: 18 }}>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiFear}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px' }}>{fng ? fng.value : '—'}</div>
              <div style={{ fontSize: 12.5, color: V.mut }}>{fng ? `${fearGreedLabel(language, fng.classification)}${fng.delta_3d != null ? ` · Δ3d ${fng.delta_3d >= 0 ? '+' : ''}${fng.delta_3d}` : ''}` : T.collecting}</div>
            </div>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiNews}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px', color: newsSpike && newsSpike.latest_score < 0 ? V.down : V.up }}>{newsSpike ? `${newsSpike.latest_score >= 0 ? '+' : ''}${Number(newsSpike.latest_score).toFixed(2)}` : '—'}</div>
              <div style={{ fontSize: 12.5, color: V.mut }}>{newsSpike ? T.kpiNewsSub : T.collecting}</div>
            </div>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiShock}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px', color: shockCount ? V.down : undefined }}>{shockCount != null ? shockCount : '—'}</div>
              <div style={{ fontSize: 12.5, color: V.mut }}>{shockCount != null ? T.kpiShockSub : T.collecting}</div>
            </div>
            <div style={cardS}>
              <div style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{T.kpiBtc}</div>
              <div style={{ fontFamily: V.mono, fontSize: 30, fontWeight: 600, margin: '6px 0 2px' }}>{btc ? `$${btc.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}</div>
              <div style={{ fontSize: 12.5, color: btc && btc.pct >= 0 ? V.up : V.down }}>{btc ? `${btc.pct >= 0 ? '+' : ''}${btc.pct.toFixed(2)}% · 24h` : ''}</div>
            </div>
          </div>

          <div style={{ ...cardS, padding: 0, marginTop: 12, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, minWidth: 560 }}>
              <thead>
                <tr>
                  {[T.thCoin, T.thSignal, T.thWhy, T.thWhen].map((h, i) => (
                    <th key={i} style={{ textAlign: 'left', fontFamily: V.mono, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: V.faint, fontWeight: 600, padding: '10px 16px', borderBottom: `1px solid ${V.line}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(fusion && fusion.length > 0) ? fusion.map((s: any, i: number) => (
                  <tr key={s.symbol}>
                    <td style={{ padding: '12px 16px', fontFamily: V.mono, fontWeight: 700, borderBottom: i < fusion.length - 1 ? `1px solid ${V.line}` : 'none' }}>{s.symbol}</td>
                    <td style={{ padding: '12px 16px', borderBottom: i < fusion.length - 1 ? `1px solid ${V.line}` : 'none' }}>{sigPill(s.signal)}</td>
                    <td style={{ padding: '12px 16px', color: V.mut, borderBottom: i < fusion.length - 1 ? `1px solid ${V.line}` : 'none' }}>{(s.evidence || []).slice(0, 2).join('; ') || '—'}</td>
                    <td style={{ padding: '12px 16px', color: V.mut, borderBottom: i < fusion.length - 1 ? `1px solid ${V.line}` : 'none' }}>{(s.matched_triggers || []).join(' · ') || '—'}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={4} style={{ padding: '14px 16px', color: V.mut }}>{T.collecting}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p style={{ fontFamily: V.mono, fontSize: 12, color: V.mut, marginTop: 12 }}>{T.dashNote}</p>
        </div>
      </section>

      {/* ── skills ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.skillKicker}</div>
          <h2 style={h2S}>{T.skillH}</h2>
          <p style={{ fontSize: 15, color: V.mut, maxWidth: '64ch', margin: '0 0 18px' }}>{T.skillSub}</p>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
            {T.skills.map((s, i) => (
              <div key={i} style={cardS}>
                <div style={{ fontFamily: V.mono, fontSize: 13, fontWeight: 600, color: V.accent, marginBottom: 5 }}>{s.n}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{s.d}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 16 }}>
            {T.caps.map((c, i) => (
              <span key={i} style={{ fontFamily: V.mono, fontSize: 12, color: V.ink, background: V.card, border: `1px solid ${V.line}`, borderRadius: 999, padding: '6px 14px' }}>{c}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ── risk ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.riskKicker}</div>
          <h2 style={h2S}>{T.riskH}</h2>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', marginTop: 18 }}>
            {T.risks.map((r, i) => (
              <div key={i} style={{ ...cardS, borderLeft: `3px solid ${V.accent}` }}>
                <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>{r.t}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{r.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── markets & modes ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.mmKicker}</div>
          <h2 style={h2S}>{T.mmH}</h2>
          <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginTop: 18 }}>
            {T.markets.map((m, i) => (
              <div key={i} style={{ ...cardS, padding: '13px 15px' }}>
                <div style={{ fontWeight: 700, fontSize: 15.5 }}>{m.n}</div>
                <div style={{ fontSize: 12.5, color: V.mut, marginTop: 2 }}>{m.sub}</div>
                <span style={{ display: 'inline-block', marginTop: 8, fontFamily: V.mono, fontSize: 10.5, fontWeight: 600, borderRadius: 999, padding: '3px 9px', background: m.auto ? 'var(--up-soft, rgba(45,158,107,0.10))' : V.bg2, color: m.auto ? V.up : V.mut }}>{m.auto ? T.mmAuto : T.mmManual}</span>
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', marginTop: 14 }}>
            {T.modes.map((m, i) => (
              <div key={i} style={{ ...cardS, borderLeft: `3px solid ${V.accent}` }}>
                <div style={{ fontWeight: 700, fontSize: 15.5, marginBottom: 5 }}>{m.t}</div>
                <div style={{ fontSize: 13.5, color: V.mut }}>{m.d}</div>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13.5, color: V.mut, marginTop: 16, maxWidth: '76ch', borderTop: `1px solid ${V.line}`, paddingTop: 16 }}>
            <span style={{ fontWeight: 700, color: V.ink }}>{tr(language, { ko: '페이퍼 먼저, 그다음 라이브. ', en: 'Paper first, then live. ', ja: 'まず模擬、次にライブ。', th: 'เปเปอร์ก่อน แล้วค่อยไลฟ์ ', vi: 'Paper trước, rồi live. ' })}</span>
            {T.mmLive}
          </p>
        </div>
      </section>

      {/* ── closing CTA ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '64px 0', textAlign: 'center' }}>
        <div style={wrap}>
          <h2 style={{ ...h2S, fontSize: 'clamp(32px,4.6vw,52px)' }}>{T.ctaH}</h2>
          <p style={{ fontSize: 16, color: V.mut, margin: '0 0 24px' }}>{T.ctaSub}</p>
          <Link to="/register" style={{ ...pillBtn, background: V.accent, color: V.accentOn, fontSize: 15.5, padding: '13px 30px' }}>{T.ctaStart}</Link>
        </div>
      </section>

      {/* ── footer ── */}
      <footer style={{ padding: '32px 0 48px' }}>
        <div style={{ ...wrap, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <img src="/logo.svg" alt="" width={38} height={38} style={{ display: 'block' }} />
            <span style={{ fontFamily: V.display, fontSize: 18, fontWeight: 700 }}>Sooppiy</span>
            <span style={{ fontFamily: V.mono, fontSize: 11, color: V.faint }}>AI · ANALYZE · AUTOMATE</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 13 }}>
              <Link to="/login" style={{ color: V.mut, textDecoration: 'none' }}>{T.login}</Link>
              <Link to="/register" style={{ color: V.mut, textDecoration: 'none' }}>{T.signup}</Link>
              <a href="mailto:support@sooppiy.app" style={{ color: V.mut, textDecoration: 'none' }}>Support</a>
            </span>
          </div>
          <p style={{ fontSize: 12, color: V.faint, maxWidth: '90ch', margin: 0 }}>{T.legal}</p>
          {/* Legal pages must be linked from the public homepage — A2P 10DLC
              vetting (error 30908) checks the privacy policy is discoverable
              from the brand website, not just that the URL exists. */}
          <p style={{ fontSize: 12, margin: 0, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <a href="/privacypolicy" style={{ color: V.mut, textDecoration: 'none' }}>Privacy Policy</a>
            <a href="/termsconditions" style={{ color: V.mut, textDecoration: 'none' }}>Terms &amp; Conditions</a>
            <a href="/smsoptin" style={{ color: V.mut, textDecoration: 'none' }}>SMS Policy</a>
          </p>
          <p style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, margin: 0 }}>© 2026 Sooppiy</p>
        </div>
      </footer>
    </div>
  )
}

export default MarketingPage
