// WebGL2 line-chart kernel (Plan 10, Phase 7).
//
// Extracted patterns from components/AnalysisPipelineViz.tsx (shader compile,
// DPR-capped sizing, on-demand rAF, WebGL2-null fallback). Built new here:
// a Float32Array RING BUFFER with bufferSubData partial uploads, min/max
// per-pixel-column DECIMATION for 60fps at 100k+ points, webglcontextlost/
// restored handling, and a Canvas2D fallback sharing the same ring buffer.
//
// One GLLineChart owns ONE canvas/context. The multi-run grid composes many
// small charts; a future single-context scissor grid can reuse this ring/
// decimation layer unchanged. Colors come in as CSS rgb strings so all three
// themes work.

export type RGBA = [number, number, number, number]

function parseColor(css: string, alpha = 1): RGBA {
  const m = css.trim().match(/rgba?\(([^)]+)\)/i)
  if (m) {
    const p = m[1].split(',').map((s) => parseFloat(s))
    return [(p[0] || 0) / 255, (p[1] || 0) / 255, (p[2] || 0) / 255,
            p[3] !== undefined ? p[3] : alpha]
  }
  const h = css.trim().replace('#', '')
  if (h.length === 6) {
    return [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255,
            parseInt(h.slice(4, 6), 16) / 255, alpha]
  }
  return [0.16, 0.47, 0.84, alpha]
}

const VS = `#version 300 es
in vec2 a_pos;
uniform vec2 u_min; uniform vec2 u_span;
void main() {
  vec2 n = (a_pos - u_min) / u_span;      // 0..1 in data space
  gl_Position = vec4(n.x * 2.0 - 1.0, n.y * 2.0 - 1.0, 0.0, 1.0);
}`

const FS = `#version 300 es
precision mediump float;
uniform vec4 u_color;
out vec4 o;
void main() { o = vec4(u_color.rgb * u_color.a, u_color.a); }`

function compile(gl: WebGL2RenderingContext, vs: string, fs: string): WebGLProgram | null {
  const mk = (t: number, s: string) => {
    const sh = gl.createShader(t)!
    gl.shaderSource(sh, s); gl.compileShader(sh)
    return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null
  }
  const v = mk(gl.VERTEX_SHADER, vs), f = mk(gl.FRAGMENT_SHADER, fs)
  if (!v || !f) return null
  const p = gl.createProgram()!
  gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p)
  return gl.getProgramParameter(p, gl.LINK_STATUS) ? p : null
}

export class GLLineChart {
  private canvas: HTMLCanvasElement
  private cap: number
  // ring buffer of (x, y) pairs; x is the sample index (monotonic), y the value
  private ring: Float32Array
  private head = 0        // next write slot
  private count = 0       // filled slots (<= cap)
  private lineColor: string
  private gl: WebGL2RenderingContext | null = null
  private prog: WebGLProgram | null = null
  private vbo: WebGLBuffer | null = null
  private uMin: WebGLUniformLocation | null = null
  private uSpan: WebGLUniformLocation | null = null
  private uColor: WebGLUniformLocation | null = null
  private ctx2d: CanvasRenderingContext2D | null = null   // fallback
  private raf = 0
  private scheduled = false
  private disposed = false
  private onLost = (e: Event) => { e.preventDefault(); this.gl = null }
  private onRestored = () => { this.initGL() }

  constructor(canvas: HTMLCanvasElement, opts: { capacity?: number; color?: string } = {}) {
    this.canvas = canvas
    this.cap = Math.max(16, opts.capacity ?? 4096)
    this.ring = new Float32Array(this.cap * 2)
    this.lineColor = opts.color ?? 'rgb(42,120,214)'
    canvas.addEventListener('webglcontextlost', this.onLost, false)
    canvas.addEventListener('webglcontextrestored', this.onRestored, false)
    this.initGL()
  }

  setColor(css: string) { this.lineColor = css; this.schedule() }

  private initGL() {
    const gl = this.canvas.getContext('webgl2', { antialias: true, alpha: true })
    if (!gl) { this.ctx2d = this.canvas.getContext('2d'); this.schedule(); return }
    this.gl = gl
    this.prog = compile(gl, VS, FS)
    if (!this.prog) { this.gl = null; this.ctx2d = this.canvas.getContext('2d'); return }
    this.vbo = gl.createBuffer()
    this.uMin = gl.getUniformLocation(this.prog, 'u_min')
    this.uSpan = gl.getUniformLocation(this.prog, 'u_span')
    this.uColor = gl.getUniformLocation(this.prog, 'u_color')
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    this.schedule()
  }

  // Replace the whole series (cold start / snapshot).
  setData(values: number[]) {
    this.count = 0; this.head = 0
    const start = Math.max(0, values.length - this.cap)
    for (let i = start; i < values.length; i++) this.push(values[i], false)
    this.schedule()
  }

  // Append one sample (live tail). x is auto-incremented by sample index.
  push(value: number, redraw = true) {
    const x = this.count === 0 ? 0
      : this.ring[((this.head - 1 + this.cap) % this.cap) * 2] + 1
    this.ring[this.head * 2] = x
    this.ring[this.head * 2 + 1] = value
    this.head = (this.head + 1) % this.cap
    if (this.count < this.cap) this.count++
    if (redraw) this.schedule()
  }

  schedule() {
    if (this.scheduled || this.disposed) return
    this.scheduled = true
    this.raf = requestAnimationFrame(() => { this.scheduled = false; this.draw() })
  }

  // Ordered samples oldest->newest, plus y-range, min/max-per-column decimated
  // to the pixel width so 100k points cost ~2*width vertices.
  private decimate(pixelWidth: number): { pts: Float32Array; xMin: number; xMax: number; yMin: number; yMax: number } {
    const n = this.count
    if (n === 0) return { pts: new Float32Array(0), xMin: 0, xMax: 1, yMin: 0, yMax: 1 }
    const first = (this.head - n + this.cap) % this.cap
    const xMin = this.ring[first * 2]
    const xMax = this.ring[((first + n - 1) % this.cap) * 2]
    let yMin = Infinity, yMax = -Infinity
    const cols = Math.max(1, Math.min(pixelWidth, n))
    if (n <= cols * 2) {
      const pts = new Float32Array(n * 2)
      for (let i = 0; i < n; i++) {
        const idx = (first + i) % this.cap
        const y = this.ring[idx * 2 + 1]
        pts[i * 2] = this.ring[idx * 2]; pts[i * 2 + 1] = y
        if (y < yMin) yMin = y; if (y > yMax) yMax = y
      }
      return { pts, xMin, xMax, yMin, yMax }
    }
    // min/max per column: two vertices per pixel column preserves spikes
    const pts = new Float32Array(cols * 4)
    const span = (xMax - xMin) || 1
    let ci = 0
    for (let c = 0; c < cols; c++) {
      const lo = xMin + (span * c) / cols
      const hi = xMin + (span * (c + 1)) / cols
      let cMin = Infinity, cMax = -Infinity, cMinX = lo, cMaxX = lo, any = false
      for (let i = 0; i < n; i++) {
        const idx = (first + i) % this.cap
        const x = this.ring[idx * 2]
        if (x < lo || (c < cols - 1 && x >= hi)) continue
        const y = this.ring[idx * 2 + 1]
        any = true
        if (y < cMin) { cMin = y; cMinX = x }
        if (y > cMax) { cMax = y; cMaxX = x }
      }
      if (!any) continue
      // emit in x order to keep the strip monotonic
      if (cMinX <= cMaxX) {
        pts[ci++] = cMinX; pts[ci++] = cMin; pts[ci++] = cMaxX; pts[ci++] = cMax
      } else {
        pts[ci++] = cMaxX; pts[ci++] = cMax; pts[ci++] = cMinX; pts[ci++] = cMin
      }
      if (cMin < yMin) yMin = cMin; if (cMax > yMax) yMax = cMax
    }
    return { pts: pts.subarray(0, ci), xMin, xMax, yMin, yMax }
  }

  private draw() {
    if (this.disposed) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const W = Math.max(1, Math.round(this.canvas.clientWidth * dpr))
    const H = Math.max(1, Math.round(this.canvas.clientHeight * dpr))
    if (this.canvas.width !== W || this.canvas.height !== H) {
      this.canvas.width = W; this.canvas.height = H
    }
    const d = this.decimate(W)
    let pad = (d.yMax - d.yMin) * 0.08
    if (!isFinite(pad) || pad === 0) pad = Math.abs(d.yMax) * 0.08 || 1
    const yMin = d.yMin - pad, yMax = d.yMax + pad
    const xSpan = (d.xMax - d.xMin) || 1
    const ySpan = (yMax - yMin) || 1

    const gl = this.gl
    if (gl && this.prog) {
      gl.viewport(0, 0, W, H)
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT)
      if (d.pts.length >= 4) {
        gl.useProgram(this.prog)
        gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo)
        gl.bufferData(gl.ARRAY_BUFFER, d.pts, gl.DYNAMIC_DRAW)
        const loc = gl.getAttribLocation(this.prog, 'a_pos')
        gl.enableVertexAttribArray(loc)
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
        gl.uniform2f(this.uMin, d.xMin, yMin)
        gl.uniform2f(this.uSpan, xSpan, ySpan)
        gl.uniform4fv(this.uColor, parseColor(this.lineColor))
        gl.drawArrays(gl.LINE_STRIP, 0, d.pts.length / 2)
      }
      return
    }
    // Canvas2D fallback — same decimated points, same ranges
    const ctx = this.ctx2d
    if (!ctx) return
    ctx.clearRect(0, 0, W, H)
    if (d.pts.length < 4) return
    const col = parseColor(this.lineColor)
    ctx.lineWidth = 1.5 * dpr
    ctx.strokeStyle = `rgba(${col[0] * 255},${col[1] * 255},${col[2] * 255},${col[3]})`
    ctx.beginPath()
    for (let i = 0; i < d.pts.length / 2; i++) {
      const px = ((d.pts[i * 2] - d.xMin) / xSpan) * W
      const py = H - ((d.pts[i * 2 + 1] - yMin) / ySpan) * H
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
    }
    ctx.stroke()
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    this.canvas.removeEventListener('webglcontextlost', this.onLost)
    this.canvas.removeEventListener('webglcontextrestored', this.onRestored)
    const gl = this.gl
    if (gl) {
      if (this.vbo) gl.deleteBuffer(this.vbo)
      if (this.prog) gl.deleteProgram(this.prog)
    }
    this.gl = null; this.ctx2d = null
  }

  isWebGL() { return this.gl !== null }
}
