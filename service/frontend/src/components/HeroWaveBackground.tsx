import { useEffect, useRef } from 'react'

// Animated 3D hero backdrop — raw WebGL point-cloud wave field (no libraries).
// A perspective camera looks across a dot grid whose height is computed in the
// vertex shader (GPU; near-zero CPU per frame). Additive blending gives the
// glow of the design reference; crests warm to amber, troughs cool to teal.
// Behaviors: DPR cap 2, resize redraw, pause in hidden tabs, reduced-motion
// drifts slowly instead of freezing, one synchronous first frame on mount.
// `dark` forces the palette (the auth screens are dark in every theme);
// omitted, it follows the document theme like the marketing hero.
export default function HeroWaveBackground({ gain = 1, amp = 1, dark }: { gain?: number; amp?: number; dark?: boolean }) {
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
      const isDark = dark ?? document.documentElement.dataset.theme !== 'light'
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
        gl.uniform1f(U.uDark, isDark ? 1 : 0)
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
  }, [gain, amp, dark])
  return (
    <canvas ref={ref} aria-hidden
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }} />
  )
}
