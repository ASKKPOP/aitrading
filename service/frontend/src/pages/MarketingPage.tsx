import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

const LANGS: Record<string, string> = { ko: 'KO', en: 'EN', ja: 'JA', th: 'TH', vi: 'VI' }

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
function HeroWaveBackground() {
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
      varying float vHeat;
      varying float vDepth;
      void main() {
        float x = aGrid.x;
        float z = aGrid.y;
        float wave = sin(x * 4.0 + uTime * 0.9 + z * 6.0)
                   + 0.5 * sin(x * 7.5 - uTime * 0.6 + z * 11.0)
                   + 0.25 * sin(x * 13.0 + uTime * 1.3 + z * 3.0);
        wave /= 1.75;
        float y = wave * 0.55 * (1.0 - z * 0.22);
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
        float a = alphaBase * fog * (0.55 + 0.85 * heat + 0.3 * cold) * mask;
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
  }, [])
  return (
    <canvas ref={ref} aria-hidden
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }} />
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

    heroKicker: tr(language, { ko: 'INTELLIGENT AUTOMATE AGENT · 페이퍼 전용', en: 'INTELLIGENT AUTOMATE AGENT · PAPER ONLY', ja: 'INTELLIGENT AUTOMATE AGENT · 模擬のみ', th: 'INTELLIGENT AUTOMATE AGENT · จำลองเท่านั้น', vi: 'INTELLIGENT AUTOMATE AGENT · CHỈ MÔ PHỎNG' }),
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
    heroNote: tr(language, { ko: '연구·교육용 소프트웨어입니다. 모든 거래는 모의이며 — 실제 자금도, 투자 자문도 아닙니다.', en: 'Research & education software. Every trade is simulated — no real funds, no advice.', ja: '研究・教育用ソフトウェアです。すべての取引は模擬であり、実資金や投資助言はありません。', th: 'ซอฟต์แวร์เพื่อการวิจัยและการศึกษา ทุกการเทรดเป็นแบบจำลอง — ไม่มีเงินจริง ไม่ใช่คำแนะนำ', vi: 'Phần mềm nghiên cứu & giáo dục. Mọi giao dịch đều mô phỏng — không tiền thật, không phải lời khuyên.' }),

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
      { k: tr(language, { ko: '공포 / 탐욕', en: 'Fear / Greed', ja: '恐怖／強欲', th: 'กลัว / โลภ', vi: 'Sợ / Tham' }), v: tr(language, { ko: '공포·탐욕 지수 · 변동성 · 청산 데이터', en: 'Fear & Greed index · volatility · liquidation data', ja: 'Fear&Greed指数 · 変動率 · 清算データ', th: 'ดัชนี Fear & Greed · ความผันผวน · ข้อมูลการล้างพอร์ต', vi: 'Chỉ số Fear & Greed · biến động · dữ liệu thanh lý' }) },
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
    dashNote: tr(language, { ko: '신호 = 정량(베이시스·RSI·청산·온체인) × 정성(뉴스 감성·멘션·예측시장 확률).', en: 'Signal = quant (basis · RSI · liquidations · on-chain) × qualitative (news sentiment · mentions · prediction-market odds).', ja: 'シグナル = 定量（ベーシス·RSI·清算·オンチェーン）× 定性（ニュース感性·言及量·予測市場オッズ）。', th: 'สัญญาณ = เชิงปริมาณ (เบสิส · RSI · การล้างพอร์ต · ออนเชน) × เชิงคุณภาพ (เซนติเมนต์ข่าว · การพูดถึง · อัตราต่อรอง)', vi: 'Tín hiệu = định lượng (basis · RSI · thanh lý · on-chain) × định tính (tâm lý tin tức · lượt nhắc · tỷ lệ cược).' }),

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
      tr(language, { ko: '백테스트', en: 'Backtesting', ja: 'バックテスト', th: 'แบ็กเทสต์', vi: 'Backtest' }),
      tr(language, { ko: '신호 생성', en: 'Signal generation', ja: 'シグナル生成', th: 'สร้างสัญญาณ', vi: 'Tạo tín hiệu' }),
      tr(language, { ko: '주문 체결(모의)', en: 'Order execution (paper)', ja: '注文執行（模擬）', th: 'ส่งคำสั่ง (จำลอง)', vi: 'Khớp lệnh (mô phỏng)' }),
      tr(language, { ko: '거래 기록', en: 'Trade journaling', ja: '取引記録', th: 'บันทึกการเทรด', vi: 'Nhật ký giao dịch' }),
      tr(language, { ko: '리스크 관리', en: 'Risk management', ja: 'リスク管理', th: 'จัดการความเสี่ยง', vi: 'Quản trị rủi ro' }),
    ],

    riskKicker: tr(language, { ko: '리스크는 코드에 고정', en: 'RISK, HARD-CODED', ja: 'リスクはコードに固定', th: 'ความเสี่ยงถูกฝังในโค้ด', vi: 'RỦI RO ĐƯỢC MÃ HÓA CỨNG' }),
    riskH: tr(language, { ko: '생략할 수 없는 부분', en: 'The part that is not optional', ja: '省略できない部分', th: 'ส่วนที่ไม่มีข้อยกเว้น', vi: 'Phần không thể bỏ qua' }),
    risks: [
      { t: tr(language, { ko: '포지션 사이징', en: 'Position sizing', ja: 'ポジションサイジング', th: 'ขนาดสถานะ', vi: 'Khối lượng vị thế' }), d: tr(language, { ko: '켈리 기준 한도가 모든 베팅을 주문 전에 제한합니다.', en: 'Kelly-criterion style limits cap every bet before it is placed.', ja: 'ケリー基準の制限が、すべてのベットを発注前に制御します。', th: 'ลิมิตแบบเคลลีคุมทุกการเดิมพันก่อนส่งคำสั่ง', vi: 'Giới hạn kiểu Kelly chặn mọi lệnh trước khi đặt.' }) },
      { t: tr(language, { ko: '하드 손절', en: 'Hard stop-losses', ja: 'ハード損切り', th: 'จุดตัดขาดทุนตายตัว', vi: 'Cắt lỗ cứng' }), d: tr(language, { ko: '손절과 최대 손실 한도는 코드 안에 있어 감정이 건드릴 수 없습니다.', en: 'Stops and max-loss limits live in code, where emotions cannot touch them.', ja: '損切りと最大損失の上限はコード内にあり、感情は介入できません。', th: 'จุดตัดขาดทุนและลิมิตขาดทุนสูงสุดอยู่ในโค้ด อารมณ์แตะต้องไม่ได้', vi: 'Điểm dừng và giới hạn lỗ tối đa nằm trong code, cảm xúc không chạm tới.' }) },
      { t: tr(language, { ko: '서킷 브레이커', en: 'Circuit breakers', ja: 'サーキットブレーカー', th: 'เซอร์กิตเบรกเกอร์', vi: 'Ngắt mạch' }), d: tr(language, { ko: '3σ 변동성, API 지연, 조작 의심 시 자동 정지합니다.', en: 'Auto-halt on 3σ volatility, API lag or suspected manipulation.', ja: '3σ変動・API遅延・操作疑いで自動停止します。', th: 'หยุดอัตโนมัติเมื่อผันผวน 3σ, API หน่วง หรือสงสัยการปั่นราคา', vi: 'Tự dừng khi biến động 3σ, API trễ hoặc nghi thao túng.' }) },
    ],

    ctaH: tr(language, { ko: '모의 자금 $100,000. 실제 리스크는 0.', en: '$100,000 of paper money. Zero real risk.', ja: '10万ドルの模擬資金。実リスクはゼロ。', th: 'เงินจำลอง $100,000 ความเสี่ยงจริงเป็นศูนย์', vi: '$100.000 tiền mô phỏng. Rủi ro thật bằng không.' }),
    ctaSub: tr(language, { ko: '한 번만 설정하세요. AI가 측정하고 판단하고 기록합니다 — 당신은 검토만.', en: 'Configure once. The AI measures, decides and journals — you review.', ja: '一度設定すれば、AIが測定・判断・記録し、あなたは確認するだけ。', th: 'ตั้งค่าครั้งเดียว AI วัด ตัดสินใจ และบันทึก — คุณแค่ทบทวน', vi: 'Cấu hình một lần. AI đo, quyết định và ghi lại — bạn chỉ xem xét.' }),

    legal: tr(language, {
      ko: 'Sooppiy는 연구·교육용 소프트웨어입니다. 이 플랫폼의 모든 거래는 모의이며, 실제 자금을 보관·이동하거나 위험에 노출하지 않습니다. 시장 데이터는 정보 제공 목적입니다. 이 사이트의 어떤 내용도 투자 자문이 아닙니다.',
      en: 'Sooppiy is research and education software. All trading on this platform is simulated: no real funds are held, moved, or at risk. Market data is provided for information only. Nothing on this site is investment advice.',
      ja: 'Sooppiyは研究・教育用ソフトウェアです。すべての取引は模擬であり、実際の資金は保有・移動・リスクにさらされません。投資助言ではありません。',
      th: 'Sooppiy คือซอฟต์แวร์วิจัยและการศึกษา การเทรดทั้งหมดเป็นแบบจำลอง ไม่มีเงินจริง ไม่ใช่คำแนะนำการลงทุน',
      vi: 'Sooppiy là phần mềm nghiên cứu và giáo dục. Mọi giao dịch đều mô phỏng. Không phải lời khuyên đầu tư.',
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
      <header style={{ position: 'sticky', top: 0, zIndex: 20, background: V.card, borderBottom: `1px solid ${V.line}` }}>
        <div style={{ ...wrap, display: 'flex', alignItems: 'center', gap: 12, height: 62 }}>
          <span style={{ width: 26, height: 26, borderRadius: '50%', background: V.accent, color: V.accentOn, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14 }}>s</span>
          <span style={{ fontFamily: V.display, fontSize: 21, fontWeight: 700 }}>Sooppiy</span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 2, border: `1px solid ${V.line}`, borderRadius: 999, padding: '3px 6px' }}>
            {Object.entries(LANGS).map(([code, label]) => (
              <button key={code} onClick={() => setLanguage(code as any)}
                style={{ background: language === code ? V.accent : 'none', color: language === code ? V.accentOn : V.mut, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, padding: '4px 9px', borderRadius: 999, fontFamily: V.sans }}>{label}</button>
            ))}
          </span>
          <Link to="/login" style={{ ...pillBtn, color: V.ink, padding: '9px 16px' }}>{T.login}</Link>
          <Link to="/register" style={{ ...pillBtn, color: V.accentOn, background: V.accent, padding: '9px 18px' }}>{T.signup}</Link>
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

      {/* ── six signal elements ── */}
      <section style={{ borderBottom: `1px solid ${V.line}`, padding: '56px 0' }}>
        <div style={wrap}>
          <div style={kicker}>{T.readKicker}</div>
          <h2 style={h2S}>{T.readH}</h2>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', marginTop: 18 }}>
            {T.read.map((r, i) => (
              <div key={i} style={cardS}>
                <div style={{ fontFamily: V.mono, fontSize: 11, color: V.accent, marginBottom: 6 }}>{String(i + 1).padStart(2, '0')}</div>
                <div style={{ fontWeight: 700, fontSize: 16.5, marginBottom: 6 }}>{r.t}</div>
                <div style={{ fontSize: 14, color: V.mut }}>{r.d}</div>
              </div>
            ))}
          </div>
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
              <div style={{ fontSize: 12.5, color: V.mut }}>{fng ? `${fng.classification}${fng.delta_3d != null ? ` · Δ3d ${fng.delta_3d >= 0 ? '+' : ''}${fng.delta_3d}` : ''}` : T.collecting}</div>
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
            <span style={{ fontFamily: V.display, fontSize: 18, fontWeight: 700 }}>Sooppiy</span>
            <span style={{ fontFamily: V.mono, fontSize: 11, color: V.faint }}>AI · ANALYZE · AUTOMATE</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 13 }}>
              <Link to="/login" style={{ color: V.mut, textDecoration: 'none' }}>{T.login}</Link>
              <Link to="/register" style={{ color: V.mut, textDecoration: 'none' }}>{T.signup}</Link>
              <a href="mailto:support@sooppiy.app" style={{ color: V.mut, textDecoration: 'none' }}>Support</a>
            </span>
          </div>
          <p style={{ fontSize: 12, color: V.faint, maxWidth: '90ch', margin: 0 }}>{T.legal}</p>
          <p style={{ fontFamily: V.mono, fontSize: 11, color: V.faint, margin: 0 }}>© 2026 Sooppiy</p>
        </div>
      </footer>
    </div>
  )
}

export default MarketingPage
