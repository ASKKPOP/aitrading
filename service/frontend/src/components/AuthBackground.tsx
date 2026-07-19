// WebGL2 animated backdrop for the auth pages (/login, /register).
//
// Full-viewport fixed canvas rendered behind the borderless auth layout. One
// fullscreen triangle, one fragment shader: domain-warped fbm drift plus a
// slow sweep, tinted per theme. Follows the shader-compile / DPR-cap /
// context-loss patterns already used by webgl/GLLineChart.ts.
//
// Renders nothing when WebGL2 is unavailable — the page keeps its own CSS
// background so the layout is unaffected. Honors prefers-reduced-motion by
// holding a single still frame.
import { useEffect, useRef } from 'react'

const VS = `#version 300 es
void main() {
  // Fullscreen triangle from gl_VertexID — no vertex buffer needed.
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`

const FS = `#version 300 es
precision highp float;
uniform vec2  u_res;
uniform float u_time;
out vec4 o;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p = p * 2.03 + vec2(37.1, 17.7);
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  vec2 p  = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;

  float t = u_time * 0.035;

  // Domain warp: two fbm lookups steer a third, giving slow braided flow.
  vec2 q = vec2(fbm(p * 1.6 + vec2(0.0, t)),
                fbm(p * 1.6 + vec2(5.2, 1.3 - t)));
  vec2 r = vec2(fbm(p * 1.9 + 3.4 * q + vec2(1.7, 9.2) + 0.9 * t),
                fbm(p * 1.9 + 3.4 * q + vec2(8.3, 2.8) - 0.7 * t));
  float f = fbm(p * 2.2 + 3.0 * r);

  // Amber core drifting through a deep teal-ink field. The auth screens are
  // light-on-dark in every theme, so there is a single palette here.
  vec3 ink   = vec3(0.027, 0.039, 0.055);
  vec3 teal  = vec3(0.055, 0.129, 0.153);
  vec3 amber = vec3(0.816, 0.639, 0.353);
  vec3 col = mix(ink, teal, clamp(f * 1.35, 0.0, 1.0));
  col = mix(col, amber, clamp(pow(length(r) * 0.62, 2.6), 0.0, 0.42));

  // Slow diagonal sweep — a faint moving sheen, not a hard band.
  float sweep = sin((uv.x * 0.9 + uv.y * 0.45) * 3.14159 - u_time * 0.16);
  col += 0.018 * smoothstep(0.55, 1.0, sweep);

  // Vignette, then a touch of dither to kill banding on flat gradients.
  col *= 1.0 - 0.55 * smoothstep(0.45, 1.25, length(p));
  col += (hash(gl_FragCoord.xy) - 0.5) * 0.006;

  o = vec4(col, 1.0);
}`

function compile(gl: WebGL2RenderingContext): WebGLProgram | null {
  const mk = (type: number, src: string) => {
    const sh = gl.createShader(type)!
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null
  }
  const v = mk(gl.VERTEX_SHADER, VS)
  const f = mk(gl.FRAGMENT_SHADER, FS)
  if (!v || !f) return null
  const prog = gl.createProgram()!
  gl.attachShader(prog, v)
  gl.attachShader(prog, f)
  gl.linkProgram(prog)
  return gl.getProgramParameter(prog, gl.LINK_STATUS) ? prog : null
}

export default function AuthBackground() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const gl = canvas.getContext('webgl2', { antialias: false, alpha: false })
    if (!gl) return                       // no WebGL2 → CSS background stands in

    const prog = compile(gl)
    if (!prog) return

    const uRes = gl.getUniformLocation(prog, 'u_res')
    const uTime = gl.getUniformLocation(prog, 'u_time')
    const vao = gl.createVertexArray()    // WebGL2 requires a bound VAO to draw

    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const start = performance.now()
    let raf = 0
    let lost = false

    // Background art: half-res on HiDPI is indistinguishable and much cheaper.
    const dprCap = () => Math.min(window.devicePixelRatio || 1, 1.5)

    // Sized from the viewport, not clientWidth: the canvas is fixed inset:0,
    // and clientWidth is still 0 on the first effect pass before layout.
    const resize = () => {
      const d = dprCap()
      const w = Math.max(1, Math.round(window.innerWidth * d))
      const h = Math.max(1, Math.round(window.innerHeight * d))
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }
    }

    const frame = () => {
      if (lost) return
      resize()
      // A 0×0 viewport (pre-layout, or a backgrounded tab) would otherwise
      // paint a 1×1 opaque sheet over the whole page. Stay hidden and retry.
      if (canvas.width <= 1 || canvas.height <= 1) {
        raf = requestAnimationFrame(frame)
        return
      }
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.useProgram(prog)
      gl.bindVertexArray(vao)
      gl.uniform2f(uRes, canvas.width, canvas.height)
      gl.uniform1f(uTime, still ? 8 : (performance.now() - start) / 1000)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      canvas.style.opacity = '1'
      if (!still) raf = requestAnimationFrame(frame)
    }

    // A hidden tab starves rAF; a resize still needs a repaint.
    const repaint = () => { if (still || document.hidden) frame() }

    // On context loss the backdrop just retires to the CSS fallback. It is
    // decorative, and this is a login form — never reload and throw away
    // whatever the user was typing for the sake of an animation.
    const onLost = (e: Event) => {
      e.preventDefault()
      lost = true
      cancelAnimationFrame(raf)
      canvas.style.opacity = '0'
    }
    canvas.addEventListener('webglcontextlost', onLost)
    window.addEventListener('resize', repaint)

    // The first frame can measure a 0×0 viewport (canvas not laid out yet).
    // rAF re-measures every frame, but reduced-motion draws once — so watch
    // the element too and redraw when a real size finally arrives.
    const sizeObserver = new ResizeObserver(() => {
      if (canvas.width <= 1 || still) frame()
    })
    sizeObserver.observe(canvas)

    frame()

    return () => {
      cancelAnimationFrame(raf)
      sizeObserver.disconnect()
      window.removeEventListener('resize', repaint)
      canvas.removeEventListener('webglcontextlost', onLost)
      gl.deleteProgram(prog)
      gl.deleteVertexArray(vao)
      // Deliberately NOT calling WEBGL_lose_context here: React reuses the
      // same <canvas> node across a StrictMode remount and across /login ↔
      // /register, and a lost context can never be re-acquired on that node.
      // The context is released with the element on a real unmount.
    }
  }, [])

  return <canvas ref={ref} className="auth-bg-canvas" aria-hidden="true" />
}
