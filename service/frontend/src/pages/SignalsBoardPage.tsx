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
        <Tile
          label={tr(language, { ko: '김치 프리미엄', en: 'Kimchi Premium', ja: 'キムチプレミアム', th: 'พรีเมียมกิมจิ', vi: 'Kimchi Premium' })}
          value={cross?.kimchi ? `${cross.kimchi.premium_pct >= 0 ? '+' : ''}${cross.kimchi.premium_pct.toFixed(2)}%` : '—'}
          sub={cross?.kimchi
            ? (cross.kimchi.verdict === 'overheated'
              ? tr(language, { ko: '국내 과열 — 컨트래리언 주의', en: 'local overheating — contrarian caution', ja: '国内過熱 — 逆張り警戒', th: 'ร้อนแรงในประเทศ — ระวังสวนทาง', vi: 'quá nóng nội địa — thận trọng ngược chiều' })
              : cross.kimchi.verdict === 'discount'
                ? tr(language, { ko: '디스카운트 — 한국 수요 위축', en: 'discount — Korean demand contraction', ja: 'ディスカウント — 韓国需要縮小', th: 'ส่วนลด — อุปสงค์เกาหลีหด', vi: 'chiết khấu — nhu cầu Hàn Quốc giảm' })
                : tr(language, { ko: 'Upbit 대비 글로벌 스프레드', en: 'Upbit vs global spread', ja: 'Upbit対グローバル', th: 'Upbit เทียบทั่วโลก', vi: 'Upbit so với toàn cầu' }))
            : cross?.available === false
              ? tr(language, { ko: '비활성화됨 (CROSS_MARKET_ENABLED)', en: 'disabled (CROSS_MARKET_ENABLED)', ja: '無効 (CROSS_MARKET_ENABLED)', th: 'ปิดอยู่ (CROSS_MARKET_ENABLED)', vi: 'tắt (CROSS_MARKET_ENABLED)' })
              : tr(language, { ko: '수집 중…', en: 'collecting…', ja: '収集中…', th: 'กำลังเก็บ…', vi: 'Đang thu thập…' })}
          accent={cross?.kimchi && Math.abs(cross.kimchi.premium_pct) >= 3 ? 'var(--error)' : undefined}
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
                <td style={td}><SignalBadge signal={s.signal} /></td>
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
        {tr(language, { ko: '융합 점수 = 가중 퀀트 × 심리(감성) × 심리(psychology) (심리 가중치는 구조적으로 상한이 있어 — 심리만으로는 절대 거래하지 않습니다). 쇼크 수치는 추정 프록시(변동성 σ + 거래량)이며 실제 청산 데이터가 아닙니다. 모든 거래는 모의입니다.', en: 'Fused score = weighted quant × sentiment × psychology (psych weight structurally capped — psychology never trades alone). Shock figures are an estimated proxy (volatility σ + volume), not real liquidation data. All trading is simulated.', ja: '融合スコア = 加重クオンツ × センチメント × 心理 (心理の重みは構造的に上限あり — 心理だけでは決して取引しません)。ショック数値は推定プロキシ (ボラティリティσ + 出来高) であり、実際の清算データではありません。すべての取引はシミュレーションです。', th: 'คะแนนรวม = ควอนต์ถ่วงน้ำหนัก × อารมณ์ × จิตวิทยา (น้ำหนักจิตวิทยาถูกจำกัดเชิงโครงสร้าง — จิตวิทยาไม่เทรดลำพัง) ตัวเลขช็อกเป็นพรอกซีประมาณ (ความผันผวน σ + ปริมาณ) ไม่ใช่ข้อมูลการชำระบัญชีจริง การเทรดทั้งหมดเป็นการจำลอง', vi: 'Điểm tổng hợp = quant có trọng số × cảm tính × tâm lý (trọng số tâm lý bị giới hạn cấu trúc — tâm lý không bao giờ giao dịch một mình). Số liệu sốc là proxy ước tính (biến động σ + khối lượng), không phải dữ liệu thanh lý thực. Tất cả giao dịch đều được mô phỏng.' })}
        {psych?.created_at && <> · {tr(language, { ko: '심리 기준', en: 'psych as of', ja: '心理データ基準', th: 'จิตวิทยา ณ', vi: 'tâm lý tính đến' })} {psych.created_at}</>}
        {scanner?.created_at && <> · {tr(language, { ko: '스캔 기준', en: 'scan as of', ja: 'スキャン基準', th: 'สแกน ณ', vi: 'quét tính đến' })} {scanner.created_at}</>}
      </p>
    </div>
  )
}

export default SignalsBoardPage
