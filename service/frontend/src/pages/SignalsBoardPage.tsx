import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr, type Language } from '../i18n'

// Signals Board (signal-collection plan Phase 5): every number on this page is
// a real collected value from the psych feed, scanner, and fusion APIs — no
// sample data. Sections render "collecting…" until their source has data.

const REFRESH_MS = 60_000
const FUSION_SYMBOLS = 'BTC,ETH,SOL'

interface FearGreed {
  value: number
  classification: string
  delta_3d: number | null
  history: { value: number; timestamp: number }[]
}

interface PsychPayload {
  available: boolean
  fear_greed: FearGreed | null
  spikes: { category: string; z: number; latest_score: number; spike: boolean; direction: string }[]
  shock: { symbol: string; sigma_multiple: number; volume_ratio: number; shock: boolean; estimated: boolean; liq_notional_usd_1h?: number; long_liq_usd_1h?: number; short_liq_usd_1h?: number }[]
  shock_note?: string
  odds_deltas: { title: string; outcome: string; odds_from: number; odds_to: number; delta_pct: number }[]
  whales?: {
    available: boolean
    count?: number
    events: { chain: string; symbol: string; direction: string; usd_value: number; exchange?: string }[]
    totals: { btc_transfer_usd?: number; eth_exchange_in_usd?: number; eth_exchange_out_usd?: number; eth_net_flow_usd?: number }
  }
  created_at: string | null
}

interface ScannerPayload {
  available: boolean
  candidates: { symbol: string; score: number; reasons: string[] }[]
  created_at: string | null
}

interface ConfluenceRead {
  buy_confluence: number
  sell_confluence: number
  threshold: number
  conditions: Record<string, boolean | null>
  nulls: Record<string, string>
  vetoes: string[]
  direction_bias: string
}

interface FusedSignal {
  symbol: string
  score: number
  signal: string
  confidence: number
  evidence: string[]
  matched_triggers: string[]
  missing: string[]
  current_price: number | null
  confluence?: ConfluenceRead | null
  components?: { quant?: { open_interest_usd?: number | null; long_short_ratio?: number | null } | null }
  // Plan 06 D4/D5: who produced this verdict, and did the inputs check out.
  // The API has always labelled this; the board did not show it, which left
  // D4's promise — never pass a rule score off as an AI one — kept only in
  // the payload and not where anyone reads it.
  fusion_source?: 'ai' | 'rule' | 'rule-fallback'
  llm_model?: string
  cached_age_s?: number
  data_verification?: { status: 'ok' | 'suspect'; reason?: string; applied?: boolean } | null
}

function ConfluenceCell({ c, language }: { c: ConfluenceRead | null | undefined; language: Language }) {
  if (!c) return <span style={{ color: 'var(--text-muted)' }}>—</span>
  const buyKeys = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6']
  const buyMet = c.buy_confluence >= c.threshold
  const dot = (k: string) => {
    const v = c.conditions[k]
    const color = v === true ? 'var(--success)' : v === false ? 'var(--error)' : 'var(--text-muted)'
    const title = v == null ? `${k}: ${c.nulls[k] ?? 'n/a'}` : `${k}: ${v ? 'ok' : 'no'}`
    return <span key={k} title={title} style={{ color, fontSize: 13 }}>{v == null ? '·' : '●'}</span>
  }
  return (
    <div>
      <div style={{ fontWeight: 700, color: buyMet ? 'var(--success)' : 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
        {c.buy_confluence}/6
        <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--text-muted)' }}> · {tr(language, { ko: '매도', en: 'sell', ja: '売り', th: 'ขาย', vi: 'bán' })} {c.sell_confluence}/6</span>
      </div>
      <div style={{ display: 'flex', gap: 3, marginTop: 2 }}>{buyKeys.map(dot)}</div>
      {c.vetoes.length > 0 && (
        <div style={{ fontSize: 10.5, color: 'var(--error)', marginTop: 2 }}>
          ⛔ {tr(language, { ko: '거부권 발동', en: 'veto active', ja: '拒否権発動', th: 'ยับยั้ง', vi: 'phủ quyết' })}
        </div>
      )}
    </div>
  )
}

function Tile({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: string
}) {
  return (
    <div style={{
      flex: '1 1 160px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
      borderRadius: 12, padding: '14px 16px', minWidth: 150,
    }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4, color: accent || 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function FngSparkline({ history }: { history: FearGreed['history'] }) {
  if (!history || history.length < 2) return null
  const points = [...history].sort((a, b) => a.timestamp - b.timestamp)
  const w = 140, h = 34
  const min = Math.min(...points.map(p => p.value))
  const max = Math.max(...points.map(p => p.value))
  const span = Math.max(1, max - min)
  const path = points.map((p, i) => {
    const x = (i / (points.length - 1)) * w
    const y = h - ((p.value - min) / span) * (h - 4) - 2
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={w} height={h} style={{ display: 'block', marginTop: 6 }} aria-label="Fear & Greed 30d">
      <path d={path} fill="none" stroke="var(--accent-primary)" strokeWidth={1.5} />
    </svg>
  )
}

function SignalBadge({ signal }: { signal: string }) {
  const color = signal === 'buy' ? 'var(--success)' : signal === 'sell' ? 'var(--error)' : 'var(--text-muted)'
  const mark = signal === 'buy' ? '▲' : signal === 'sell' ? '▼' : '■'
  return <span style={{ color, fontWeight: 700 }}>{mark} {signal.toUpperCase()}</span>
}

// Who produced this verdict (Plan 06 D4) and whether its inputs verified
// (D5). 'rule-fallback' is deliberately louder than 'rule': plain rule means
// the AI path is off by configuration, while a fallback means it was meant to
// run and could not — the reader should be able to tell those apart at a
// glance rather than reading a rule score as an AI one.
function SourceBadge({ s, language }: { s: FusedSignal; language: Language }) {
  const src = s.fusion_source || 'rule'
  const dv = s.data_verification
  const pill = (bg: string, fg: string, text: string, title: string) => (
    <span title={title} style={{
      fontSize: 9.5, fontWeight: 700, padding: '1px 5px', borderRadius: 4,
      background: bg, color: fg, whiteSpace: 'nowrap',
    }}>{text}</span>
  )
  const age = s.cached_age_s != null && s.cached_age_s > 0
    ? tr(language, { ko: `, ${s.cached_age_s}초 전 판정`, en: `, verdict ${s.cached_age_s}s old`, ja: `, ${s.cached_age_s}秒前の判定`, th: `, ผลเมื่อ ${s.cached_age_s} วิ.ที่แล้ว`, vi: `, phán quyết ${s.cached_age_s}s trước` })
    : ''
  return (
    <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
      {src === 'ai' && pill('rgba(88,166,255,0.16)', '#58a6ff', 'AI',
        `${tr(language, { ko: 'AI가 가중치를 정해 종합', en: 'Fused by the AI, which chose the weights', ja: 'AIが重みを決めて統合', th: 'AI รวมสัญญาณและเลือกน้ำหนักเอง', vi: 'AI tự chọn trọng số và tổng hợp' })}${s.llm_model ? ` — ${s.llm_model}` : ''}${age}`)}
      {src === 'rule' && pill('rgba(139,148,158,0.16)', 'var(--text-muted)',
        tr(language, { ko: '규칙', en: 'rule', ja: 'ルール', th: 'กฎ', vi: 'quy tắc' }),
        tr(language, { ko: '고정 가중치로 계산 — AI 종합은 꺼져 있습니다', en: 'Fixed-weight calculation — AI fusion is off', ja: '固定加重で計算 — AI統合はオフ', th: 'คำนวณด้วยน้ำหนักคงที่ — AI fusion ปิดอยู่', vi: 'Tính theo trọng số cố định — AI fusion đang tắt' }))}
      {src === 'rule-fallback' && pill('rgba(210,153,34,0.18)', '#d29922',
        tr(language, { ko: '규칙(대체)', en: 'rule (fallback)', ja: 'ルール(代替)', th: 'กฎ (สำรอง)', vi: 'quy tắc (dự phòng)' }),
        tr(language, { ko: 'AI 종합이 실패해 고정 가중치로 대체되었습니다', en: 'AI fusion was unavailable — fell back to fixed weights', ja: 'AI統合が使えず固定加重に代替', th: 'AI fusion ใช้ไม่ได้ — ใช้น้ำหนักคงที่แทน', vi: 'AI fusion không khả dụng — quay về trọng số cố định' }))}
      {dv?.status === 'suspect' && pill('rgba(210,153,34,0.18)', '#d29922',
        `⚠ ${tr(language, { ko: '입력 의심', en: 'inputs suspect', ja: '入力に疑い', th: 'อินพุตน่าสงสัย', vi: 'đầu vào đáng ngờ' })}`,
        dv.reason || '')}
    </div>
  )
}

interface MacroEvent {
  event_type: string
  title: string
  at: string
  hours_until: number
  days_until: number
}

interface EventsPayload {
  available: boolean
  next: MacroEvent[]
  event_window: { title: string; minutes_to_release: number } | null
}

interface RegimePayload {
  regime: 'trend' | 'caution' | 'panic' | 'euphoria' | 'event' | 'unknown'
  reasons: string[]
  allow_new_buys: boolean
  size_multiplier: number
  fng_value: number | null
  vol_percentile: number | null
  enforced: boolean
}

interface CrossPayload {
  available: boolean
  kimchi: { premium_pct: number; verdict: string; upbit_usd_equiv: number; global_usd: number } | null
  dollar_index: { value: number; change_1d_pct: number | null; date: string } | null
}

export function SignalsBoardPage() {
  const { language } = useLanguage()
  const [psych, setPsych] = useState<PsychPayload | null>(null)
  const [scanner, setScanner] = useState<ScannerPayload | null>(null)
  const [fusion, setFusion] = useState<FusedSignal[] | null>(null)
  const [events, setEvents] = useState<EventsPayload | null>(null)
  const [cross, setCross] = useState<CrossPayload | null>(null)
  const [regime, setRegime] = useState<RegimePayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadingRef = useRef(false)

  const load = useCallback(async () => {
    // Skip ticks while a previous load is in flight, and don't poll hidden tabs
    // — every fetch of /fusion costs the server upstream API calls.
    if (loadingRef.current || document.hidden) return
    loadingRef.current = true
    try {
      const [psychRes, scannerRes, fusionRes, eventsRes, crossRes, regimeRes] = await Promise.all([
        fetch(`${API_BASE}/market-intel/psych`),
        fetch(`${API_BASE}/scanner/candidates`),
        fetch(`${API_BASE}/market-intel/fusion?symbols=${FUSION_SYMBOLS}`),
        fetch(`${API_BASE}/market-intel/events`),
        fetch(`${API_BASE}/market-intel/cross`),
        fetch(`${API_BASE}/market-intel/regime`),
      ])
      if (psychRes.ok) setPsych(await psychRes.json())
      if (scannerRes.ok) setScanner(await scannerRes.json())
      if (fusionRes.ok) setFusion((await fusionRes.json()).signals ?? [])
      if (eventsRes.ok) setEvents(await eventsRes.json())
      if (crossRes.ok) setCross(await crossRes.json())
      if (regimeRes.ok) setRegime(await regimeRes.json())
      if (!psychRes.ok && !scannerRes.ok && !fusionRes.ok) throw new Error('all sources failed')
      setError(null)
    } catch {
      setError(tr(language, { ko: 'Signal API에 연결할 수 없습니다 — 백엔드가 시그널 단계와 함께 실행 중인가요?', en: 'Signal APIs unreachable — is the backend running with the signal phases enabled?', ja: 'Signal APIに接続できません — シグナルフェーズを有効にしてバックエンドが起動していますか？', th: 'เชื่อมต่อ Signal API ไม่ได้ — แบ็คเอนด์ทำงานพร้อมเปิดใช้เฟสสัญญาณหรือไม่?', vi: 'Không thể kết nối Signal API — backend có đang chạy với các pha tín hiệu được bật không?' }))
    } finally {
      loadingRef.current = false
    }
  }, [language])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    const onVisible = () => { if (!document.hidden) load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  const fng = psych?.fear_greed ?? null
  const cryptoSpike = psych?.spikes?.find(s => s.category === 'crypto') ?? psych?.spikes?.[0] ?? null
  const nextEvent = events?.next?.[0] ?? null
  const shockAlerts = (psych?.shock ?? []).filter(s => s.shock)
  const liqRows = (psych?.shock ?? []).filter(s => s.liq_notional_usd_1h != null)
  const liqTotal1h = liqRows.length ? liqRows.reduce((a, s) => a + (s.liq_notional_usd_1h || 0), 0) : null
  const candidates = scanner?.candidates ?? []

  const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontSize: 11, textTransform: 'uppercase',
    letterSpacing: '0.06em', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-color)',
  }
  const td: React.CSSProperties = { padding: '12px 14px', borderBottom: '1px solid var(--border-color)', fontSize: 13, verticalAlign: 'top' }

  return (
    <div className="page-container">
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{tr(language, { ko: '시그널 보드', en: 'Signals Board', ja: 'シグナルボード', th: 'บอร์ดสัญญาณ', vi: 'Bảng tín hiệu' })}</h2>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
          {tr(language, { ko: '실시간 수집 시그널 — 심리 · 스캐너 · 융합 점수. 모의 거래 전용이며 투자 자문이 아닙니다.', en: 'Live collected signals — psychology · scanner · fused score. Paper trading only, not investment advice.', ja: 'リアルタイム収集シグナル — 心理 · スキャナー · 融合スコア。ペーパートレードのみで、投資助言ではありません。', th: 'สัญญาณที่เก็บแบบเรียลไทม์ — จิตวิทยา · สแกนเนอร์ · คะแนนรวม เทรดกระดาษเท่านั้น ไม่ใช่คำแนะนำการลงทุน', vi: 'Tín hiệu thu thập trực tiếp — tâm lý · máy quét · điểm tổng hợp. Chỉ giao dịch giấy, không phải lời khuyên đầu tư.' })}
        </p>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', borderRadius: 10, border: '1px solid var(--error)', color: 'var(--error)', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Stat tiles — all real values */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        <div style={{
          flex: '1 1 180px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
          borderRadius: 12, padding: '14px 16px', minWidth: 170,
        }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            {tr(language, { ko: '공포 & 탐욕', en: 'Fear & Greed', ja: '恐怖 & 強欲', th: 'ความกลัว & ความโลภ', vi: 'Sợ hãi & Tham lam' })}
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>
            {fng ? fng.value : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            {fng ? `${fng.classification}${fng.delta_3d != null ? ` · Δ3d ${fng.delta_3d >= 0 ? '+' : ''}${fng.delta_3d}` : ''}` : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          </div>
          {fng && <FngSparkline history={fng.history} />}
        </div>
        <Tile
          label={tr(language, { ko: '시장 국면', en: 'Market Regime', ja: '市場レジーム', th: 'สภาวะตลาด', vi: 'Chế độ thị trường' })}
          value={regime ? tr(language, {
            ko: { trend: '추세', caution: '주의', panic: '패닉', euphoria: '과열', event: '이벤트', unknown: '미확정' }[regime.regime],
            en: regime.regime.toUpperCase(),
            ja: { trend: 'トレンド', caution: '注意', panic: 'パニック', euphoria: '過熱', event: 'イベント', unknown: '不明' }[regime.regime],
            th: regime.regime.toUpperCase(),
            vi: regime.regime.toUpperCase(),
          }) : '—'}
          sub={regime
            ? `${regime.allow_new_buys
                ? tr(language, { ko: `신규 진입 ×${regime.size_multiplier}`, en: `entries ×${regime.size_multiplier}`, ja: `新規 ×${regime.size_multiplier}`, th: `เข้าใหม่ ×${regime.size_multiplier}`, vi: `vào lệnh ×${regime.size_multiplier}` })
                : tr(language, { ko: '신규 매수 금지', en: 'no new buys', ja: '新規買い禁止', th: 'ห้ามซื้อใหม่', vi: 'không mua mới' })}${regime.vol_percentile != null ? ` · vol p${regime.vol_percentile.toFixed(0)}` : ''}${regime.enforced ? '' : tr(language, { ko: ' · 자문용', en: ' · advisory', ja: ' · 参考', th: ' · แนะนำ', vi: ' · tư vấn' })}`
            : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          accent={regime ? (regime.regime === 'trend' ? 'var(--success)'
            : regime.regime === 'panic' || regime.regime === 'event' ? 'var(--error)'
            : undefined) : undefined}
        />
        <Tile
          label={tr(language, { ko: '뉴스 심리', en: 'News Sentiment', ja: 'ニュースセンチメント', th: 'อารมณ์ข่าว', vi: 'Tâm lý tin tức' })}
          value={cryptoSpike ? cryptoSpike.latest_score.toFixed(2) : '—'}
          sub={cryptoSpike
            ? tr(language, { ko: `${cryptoSpike.category} · z=${cryptoSpike.z}${cryptoSpike.spike ? ` (${cryptoSpike.direction} 급등)` : ''}`, en: `${cryptoSpike.category} · z=${cryptoSpike.z}${cryptoSpike.spike ? ` (${cryptoSpike.direction} spike)` : ''}`, ja: `${cryptoSpike.category} · z=${cryptoSpike.z}${cryptoSpike.spike ? ` (${cryptoSpike.direction} 急騰)` : ''}`, th: `${cryptoSpike.category} · z=${cryptoSpike.z}${cryptoSpike.spike ? ` (${cryptoSpike.direction} พุ่ง)` : ''}`, vi: `${cryptoSpike.category} · z=${cryptoSpike.z}${cryptoSpike.spike ? ` (${cryptoSpike.direction} tăng vọt)` : ''}` })
            : tr(language, { ko: '수집 중… (뉴스 스냅샷 필요)', en: 'collecting… (needs news snapshots)', ja: '収集中… (ニューススナップショットが必要)', th: 'กำลังเก็บ… (ต้องมีสแนปช็อตข่าว)', vi: 'Đang thu thập… (cần ảnh chụp tin tức)' })}
          accent={cryptoSpike && cryptoSpike.latest_score < 0 ? 'var(--error)' : undefined}
        />
        <Tile
          label={tr(language, { ko: '쇼크 경보', en: 'Shock Alerts', ja: 'ショックアラート', th: 'แจ้งเตือนช็อก', vi: 'Cảnh báo sốc' })}
          value={psych?.available ? String(shockAlerts.length) : '—'}
          sub={!psych?.available
            ? tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })
            : liqTotal1h != null
              ? tr(language, { ko: `실제 청산 (OKX) 1h $${(liqTotal1h / 1e6).toFixed(2)}M + σ 프록시`, en: `real liquidations (OKX) 1h $${(liqTotal1h / 1e6).toFixed(2)}M + σ proxy`, ja: `実清算 (OKX) 1h $${(liqTotal1h / 1e6).toFixed(2)}M + σプロキシ`, th: `การชำระบัญชีจริง (OKX) 1 ชม. $${(liqTotal1h / 1e6).toFixed(2)}M + σ พรอกซี`, vi: `thanh lý thực (OKX) 1h $${(liqTotal1h / 1e6).toFixed(2)}M + σ proxy` })
              : tr(language, { ko: '변동성 σ + 거래량 · 추정 프록시', en: 'volatility σ + volume · estimated proxy', ja: 'ボラティリティσ + 出来高 · 推定プロキシ', th: 'ความผันผวน σ + ปริมาณ · พรอกซีประมาณ', vi: 'biến động σ + khối lượng · proxy ước tính' })}
          accent={shockAlerts.length > 0 ? 'var(--error)' : undefined}
        />
        <Tile
          label={tr(language, { ko: '스캐너 후보', en: 'Scanner Candidates', ja: 'スキャナー候補', th: 'ผู้สมัครสแกนเนอร์', vi: 'Ứng viên máy quét' })}
          value={scanner?.available ? String(candidates.length) : '—'}
          sub={scanner?.available ? tr(language, { ko: '거래량 · 언급 · 신규 상장', en: 'volume · mentions · new listings', ja: '出来高 · 言及 · 新規上場', th: 'ปริมาณ · การกล่าวถึง · เหรียญใหม่', vi: 'khối lượng · lượt nhắc · niêm yết mới' }) : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
        />
        <Tile
          label={tr(language, { ko: '다음 거시 이벤트', en: 'Next Macro Event', ja: '次のマクロイベント', th: 'เหตุการณ์มหภาคถัดไป', vi: 'Sự kiện vĩ mô tiếp theo' })}
          value={nextEvent ? (nextEvent.days_until >= 1 ? `D-${Math.ceil(nextEvent.days_until)}` : `${Math.round(nextEvent.hours_until)}h`) : '—'}
          sub={events?.event_window
            ? tr(language, { ko: `⚠ ${events.event_window.title} 발표 창 진행 중`, en: `⚠ ${events.event_window.title} release window active`, ja: `⚠ ${events.event_window.title} 発表ウィンドウ中`, th: `⚠ ช่วงประกาศ ${events.event_window.title}`, vi: `⚠ Cửa sổ công bố ${events.event_window.title}` })
            : nextEvent
              ? `${nextEvent.title} · ${nextEvent.at.slice(0, 10)}`
              : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          accent={events?.event_window ? 'var(--error)' : undefined}
        />
        {/* Keep the recognized "Kimchi" name where traders know it (ko/en/ja);
            add "Korea" context for th/vi where the bare transliteration is
            opaque. It is a market-wide signal (Korean retail demand), not a
            Korea-only readout — relevant to every region. */}
        <Tile
          label={tr(language, { ko: '김치 프리미엄', en: 'Kimchi Premium', ja: 'キムチプレミアム', th: 'พรีเมียมเกาหลี (Kimchi)', vi: 'Chênh lệch Hàn Quốc (Kimchi)' })}
          value={cross?.kimchi ? `${cross.kimchi.premium_pct >= 0 ? '+' : ''}${cross.kimchi.premium_pct.toFixed(2)}%` : '—'}
          sub={cross?.kimchi
            ? (cross.kimchi.verdict === 'overheated'
              ? tr(language, { ko: '국내 과열 — 컨트래리언 주의', en: 'local overheating — contrarian caution', ja: '国内過熱 — 逆張り警戒', th: 'ร้อนแรงในประเทศ — ระวังสวนทาง', vi: 'quá nóng nội địa — thận trọng ngược chiều' })
              : cross.kimchi.verdict === 'discount'
                ? tr(language, { ko: '디스카운트 — 한국 수요 위축', en: 'discount — Korean demand contraction', ja: 'ディスカウント — 韓国需要縮小', th: 'ส่วนลด — อุปสงค์เกาหลีหด', vi: 'chiết khấu — nhu cầu Hàn Quốc giảm' })
                : tr(language, { ko: '한국 거래소 vs 글로벌 — 한국 개인 수요 지표', en: 'Korean exchange vs global — a gauge of Korean retail demand', ja: '韓国取引所 vs グローバル — 韓国個人需要の指標', th: 'ตลาดเกาหลี vs ทั่วโลก — วัดอุปสงค์รายย่อยเกาหลี', vi: 'Sàn Hàn Quốc vs toàn cầu — thước đo nhu cầu bán lẻ Hàn Quốc' }))
            : cross?.available === false
              ? tr(language, { ko: '비활성화됨 (CROSS_MARKET_ENABLED)', en: 'disabled (CROSS_MARKET_ENABLED)', ja: '無効 (CROSS_MARKET_ENABLED)', th: 'ปิดอยู่ (CROSS_MARKET_ENABLED)', vi: 'tắt (CROSS_MARKET_ENABLED)' })
              : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          accent={cross?.kimchi && Math.abs(cross.kimchi.premium_pct) >= 3 ? 'var(--error)' : undefined}
        />
        <Tile
          label={tr(language, { ko: '고래 활동', en: 'Whale Activity', ja: 'クジラ活動', th: 'กิจกรรมวาฬ', vi: 'Hoạt động cá voi' })}
          value={psych?.whales?.available ? String(psych.whales.count ?? psych.whales.events?.length ?? 0) : '—'}
          sub={psych?.whales?.available
            ? (psych.whales.totals?.eth_net_flow_usd
              ? ((psych.whales.totals.eth_net_flow_usd ?? 0) > 0
                ? tr(language, { ko: `ETH 순유입 $${(psych.whales.totals.eth_net_flow_usd / 1e6).toFixed(1)}M → 매도 압력`, en: `ETH net inflow $${(psych.whales.totals.eth_net_flow_usd / 1e6).toFixed(1)}M → sell pressure`, ja: `ETH純流入 $${(psych.whales.totals.eth_net_flow_usd / 1e6).toFixed(1)}M → 売り圧力`, th: `ETH ไหลเข้าสุทธิ $${(psych.whales.totals.eth_net_flow_usd / 1e6).toFixed(1)}M → แรงขาย`, vi: `ETH ròng vào $${(psych.whales.totals.eth_net_flow_usd / 1e6).toFixed(1)}M → áp lực bán` })
                : tr(language, { ko: `ETH 순유출 $${(Math.abs(psych.whales.totals.eth_net_flow_usd) / 1e6).toFixed(1)}M → 축적`, en: `ETH net outflow $${(Math.abs(psych.whales.totals.eth_net_flow_usd) / 1e6).toFixed(1)}M → accumulation`, ja: `ETH純流出 $${(Math.abs(psych.whales.totals.eth_net_flow_usd) / 1e6).toFixed(1)}M → 蓄積`, th: `ETH ไหลออกสุทธิ $${(Math.abs(psych.whales.totals.eth_net_flow_usd) / 1e6).toFixed(1)}M → สะสม`, vi: `ETH ròng ra $${(Math.abs(psych.whales.totals.eth_net_flow_usd) / 1e6).toFixed(1)}M → tích lũy` }))
              : tr(language, { ko: '온체인 대형 이체 (실데이터)', en: 'large on-chain transfers (real data)', ja: 'オンチェーン大口送金（実データ）', th: 'โอนออนเชนขนาดใหญ่ (ข้อมูลจริง)', vi: 'chuyển on-chain lớn (dữ liệu thật)' }))
            : psych?.whales?.available === false
              ? tr(language, { ko: '비활성화됨 (WHALE_FEED_ENABLED)', en: 'disabled (WHALE_FEED_ENABLED)', ja: '無効 (WHALE_FEED_ENABLED)', th: 'ปิดอยู่ (WHALE_FEED_ENABLED)', vi: 'tắt (WHALE_FEED_ENABLED)' })
              : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          accent={(psych?.whales?.totals?.eth_net_flow_usd ?? 0) > 0 ? 'var(--warning)' : undefined}
        />
      </div>

      {/* Fused signal table — framework format: coin · signal · reason · trigger · confidence */}
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 10px' }}>{tr(language, { ko: '융합 시그널', en: 'Fused Signals', ja: '融合シグナル', th: 'สัญญาณรวม', vi: 'Tín hiệu tổng hợp' })}</h3>
      <div style={{ overflowX: 'auto', border: '1px solid var(--border-color)', borderRadius: 12, marginBottom: 24 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
          <thead>
            <tr>
              <th style={th}>{tr(language, { ko: '코인', en: 'Coin', ja: 'コイン', th: 'เหรียญ', vi: 'Coin' })}</th><th style={th}>{tr(language, { ko: '시그널', en: 'Signal', ja: 'シグナル', th: 'สัญญาณ', vi: 'Tín hiệu' })}</th><th style={th}>{tr(language, { ko: '컨플루언스', en: 'Confluence', ja: 'コンフルエンス', th: 'คอนฟลูเอนซ์', vi: 'Hợp lưu' })}</th><th style={th}>{tr(language, { ko: '근거', en: 'Reason', ja: '根拠', th: 'เหตุผล', vi: 'Lý do' })}</th>
              <th style={th}>{tr(language, { ko: '트리거', en: 'Trigger', ja: 'トリガー', th: 'ทริกเกอร์', vi: 'Trigger' })}</th><th style={th}>{tr(language, { ko: '신뢰도', en: 'Conf.', ja: '信頼度', th: 'ความเชื่อมั่น', vi: 'Độ tin cậy' })}</th>
            </tr>
          </thead>
          <tbody>
            {(fusion ?? []).map(s => (
              <tr key={s.symbol}>
                <td style={{ ...td, fontWeight: 700 }}>
                  {s.symbol}
                  {s.current_price != null && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
                      ${s.current_price.toLocaleString()}
                    </div>
                  )}
                  {(s.components?.quant?.open_interest_usd != null || s.components?.quant?.long_short_ratio != null) && (
                    <div style={{ fontSize: 10.5, color: 'var(--text-muted)', fontWeight: 400 }}>
                      {s.components?.quant?.open_interest_usd != null && `OI $${(s.components.quant.open_interest_usd / 1e9).toFixed(2)}B`}
                      {s.components?.quant?.open_interest_usd != null && s.components?.quant?.long_short_ratio != null && ' · '}
                      {s.components?.quant?.long_short_ratio != null && `L/S ${s.components.quant.long_short_ratio.toFixed(2)}`}
                    </div>
                  )}
                </td>
                <td style={td}>
                  <SignalBadge signal={s.signal} />
                  <SourceBadge s={s} language={language} />
                </td>
                <td style={td}><ConfluenceCell c={s.confluence} language={language} /></td>
                <td style={{ ...td, color: 'var(--text-secondary)', maxWidth: 380 }}>
                  {s.evidence.length ? s.evidence.slice(0, 3).join('; ') : '—'}
                  {s.missing.length > 0 && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{tr(language, { ko: '누락: ', en: 'missing: ', ja: '欠落: ', th: 'ขาด: ', vi: 'thiếu: ' })}{s.missing.join(', ')}</div>
                  )}
                </td>
                <td style={{ ...td, color: 'var(--text-secondary)' }}>
                  {s.matched_triggers.length ? s.matched_triggers.join('; ') : '—'}
                </td>
                <td style={{ ...td, fontVariantNumeric: 'tabular-nums' }}>
                  {(s.confidence * 100).toFixed(0)}%
                </td>
              </tr>
            ))}
            {(fusion ?? []).length === 0 && (
              <tr><td style={td} colSpan={6}>{tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Scanner candidates with reasons */}
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 10px' }}>{tr(language, { ko: '어떤 코인 스캐너', en: 'Which-coin Scanner', ja: 'どのコインスキャナー', th: 'สแกนเนอร์เลือกเหรียญ', vi: 'Máy quét chọn coin' })}</h3>
      <div style={{ border: '1px solid var(--border-color)', borderRadius: 12, padding: '4px 0', marginBottom: 24 }}>
        {candidates.length === 0 && (
          <div style={{ padding: '12px 16px', fontSize: 13, color: 'var(--text-muted)' }}>
            {scanner?.available ? tr(language, { ko: '최근 스캔에서 급등이 감지되지 않았습니다', en: 'no surges detected in the latest scan', ja: '最新スキャンで急騰は検出されませんでした', th: 'ไม่พบการพุ่งในสแกนล่าสุด', vi: 'không phát hiện đợt tăng nào trong lần quét gần nhất' }) : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          </div>
        )}
        {candidates.slice(0, 8).map(c => (
          <div key={c.symbol} style={{ display: 'flex', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border-color)', fontSize: 13, alignItems: 'baseline' }}>
            <span style={{ fontWeight: 700, minWidth: 90 }}>{c.symbol}</span>
            <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{tr(language, { ko: '점수', en: 'score', ja: 'スコア', th: 'คะแนน', vi: 'điểm' })} {c.score}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{c.reasons.join(' · ')}</span>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.6 }}>
        {/* Says which engine produced the score, because both run: the AI
            weighs the factors itself (badge: AI) and the fixed-weight path is
            the fallback (badge: 규칙). The two guarantees below hold on BOTH
            paths — psychology never trades alone, and never leads the score —
            which is what "capped" must mean now that the model picks its own
            weights. Claiming a fixed 0.5/0.3/0.2 split would be false. */}
        {tr(language, { ko: '융합 점수는 AI가 팩터 스냅샷 전체를 보고 직접 가중치를 정해 산출합니다(배지: AI). AI를 쓸 수 없으면 고정 가중치 방식으로 대체하며 배지에 표시됩니다(규칙 / 규칙(대체)). 두 경로 모두에서: 심리만으로는 절대 거래하지 않고, 심리가 점수를 주도할 수 없습니다(가중치 상한 0.3 — 초과를 선언한 AI 판정은 폐기). 쇼크 수치는 실제 청산 데이터(OKX) 기반이며, 피드 장애 시에만 변동성 σ 프록시로 대체됩니다. 모든 거래는 모의입니다.', en: 'The fused score is produced by the AI weighing the full factor snapshot itself (badge: AI). If the AI is unavailable the fixed-weight path takes over and the badge says so (rule / rule fallback). On BOTH paths: psychology never trades alone, and psychology can never lead the score (weight capped at 0.3 — an AI verdict declaring otherwise is discarded). Shock figures are based on real liquidation data (OKX), falling back to a volatility-σ proxy only if the feed is down. All trading is simulated.', ja: '融合スコアはAIがファクター全体を見て自ら重みを決めて算出します（バッジ: AI）。AIが使えない場合は固定加重に切り替わり、バッジに表示されます（ルール / ルール(代替)）。どちらの経路でも心理だけでは取引せず、心理がスコアを主導することはありません（重み上限0.3）。ショック数値は実際の清算データ (OKX) に基づきます。すべての取引はシミュレーションです。', th: 'คะแนนรวมมาจาก AI ที่ชั่งน้ำหนักปัจจัยเองทั้งหมด (ป้าย: AI) หาก AI ใช้ไม่ได้จะกลับไปใช้น้ำหนักคงที่และแสดงบนป้าย ทั้งสองเส้นทาง: จิตวิทยาไม่เทรดลำพัง และไม่นำคะแนน (จำกัดน้ำหนัก 0.3) ตัวเลขช็อกอิงข้อมูลการล้างพอร์ตจริง (OKX) การเทรดทั้งหมดเป็นการจำลอง', vi: 'Điểm tổng hợp do AI tự chọn trọng số trên toàn bộ ảnh chụp yếu tố (nhãn: AI). Nếu AI không khả dụng, hệ thống quay về trọng số cố định và nhãn sẽ nói rõ. Trên cả hai đường: tâm lý không bao giờ giao dịch một mình và không bao giờ dẫn dắt điểm số (giới hạn trọng số 0.3). Số liệu sốc dựa trên dữ liệu thanh lý thực (OKX). Tất cả giao dịch đều được mô phỏng.' })}
        {psych?.created_at && <> · {tr(language, { ko: '심리 기준', en: 'psych as of', ja: '心理データ基準', th: 'จิตวิทยา ณ', vi: 'tâm lý tính đến' })} {psych.created_at}</>}
        {scanner?.created_at && <> · {tr(language, { ko: '스캔 기준', en: 'scan as of', ja: 'スキャン基準', th: 'สแกน ณ', vi: 'quét tính đến' })} {scanner.created_at}</>}
      </p>
    </div>
  )
}

export default SignalsBoardPage
