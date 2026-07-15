import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from '../appShared'

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
  shock: { symbol: string; sigma_multiple: number; volume_ratio: number; shock: boolean; estimated: boolean }[]
  shock_note?: string
  odds_deltas: { title: string; outcome: string; odds_from: number; odds_to: number; delta_pct: number }[]
  created_at: string | null
}

interface ScannerPayload {
  available: boolean
  candidates: { symbol: string; score: number; reasons: string[] }[]
  created_at: string | null
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
}

function Tile({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: string
}) {
  return (
    <div style={{
      flex: '1 1 160px', background: 'var(--bg-secondary)', border: '1px solid var(--border)',
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

export function SignalsBoardPage() {
  const [psych, setPsych] = useState<PsychPayload | null>(null)
  const [scanner, setScanner] = useState<ScannerPayload | null>(null)
  const [fusion, setFusion] = useState<FusedSignal[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadingRef = useRef(false)

  const load = useCallback(async () => {
    // Skip ticks while a previous load is in flight, and don't poll hidden tabs
    // — every fetch of /fusion costs the server upstream API calls.
    if (loadingRef.current || document.hidden) return
    loadingRef.current = true
    try {
      const [psychRes, scannerRes, fusionRes] = await Promise.all([
        fetch(`${API_BASE}/market-intel/psych`),
        fetch(`${API_BASE}/scanner/candidates`),
        fetch(`${API_BASE}/market-intel/fusion?symbols=${FUSION_SYMBOLS}`),
      ])
      if (psychRes.ok) setPsych(await psychRes.json())
      if (scannerRes.ok) setScanner(await scannerRes.json())
      if (fusionRes.ok) setFusion((await fusionRes.json()).signals ?? [])
      if (!psychRes.ok && !scannerRes.ok && !fusionRes.ok) throw new Error('all sources failed')
      setError(null)
    } catch {
      setError('Signal APIs unreachable — is the backend running with the signal phases enabled?')
    } finally {
      loadingRef.current = false
    }
  }, [])

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
  const shockAlerts = (psych?.shock ?? []).filter(s => s.shock)
  const candidates = scanner?.candidates ?? []

  const th: React.CSSProperties = {
    padding: '10px 14px', textAlign: 'left', fontSize: 11, textTransform: 'uppercase',
    letterSpacing: '0.06em', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)',
  }
  const td: React.CSSProperties = { padding: '12px 14px', borderBottom: '1px solid var(--border)', fontSize: 13, verticalAlign: 'top' }

  return (
    <div className="page-container">
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>Signals Board</h2>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
          Live collected signals — psychology · scanner · fused score. Paper trading only, not investment advice.
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
          flex: '1 1 180px', background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '14px 16px', minWidth: 170,
        }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            Fear &amp; Greed
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>
            {fng ? fng.value : '—'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            {fng ? `${fng.classification}${fng.delta_3d != null ? ` · Δ3d ${fng.delta_3d >= 0 ? '+' : ''}${fng.delta_3d}` : ''}` : 'collecting…'}
          </div>
          {fng && <FngSparkline history={fng.history} />}
        </div>
        <Tile
          label="News Sentiment"
          value={cryptoSpike ? cryptoSpike.latest_score.toFixed(2) : '—'}
          sub={cryptoSpike
            ? `${cryptoSpike.category} · z=${cryptoSpike.z}${cryptoSpike.spike ? ` (${cryptoSpike.direction} spike)` : ''}`
            : 'collecting… (needs news snapshots)'}
          accent={cryptoSpike && cryptoSpike.latest_score < 0 ? 'var(--error)' : undefined}
        />
        <Tile
          label="Shock Alerts"
          value={psych?.available ? String(shockAlerts.length) : '—'}
          sub={psych?.available ? 'volatility σ + volume · estimated proxy' : 'collecting…'}
          accent={shockAlerts.length > 0 ? 'var(--error)' : undefined}
        />
        <Tile
          label="Scanner Candidates"
          value={scanner?.available ? String(candidates.length) : '—'}
          sub={scanner?.available ? 'volume · mentions · new listings' : 'collecting…'}
        />
      </div>

      {/* Fused signal table — framework format: coin · signal · reason · trigger · confidence */}
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 10px' }}>Fused Signals</h3>
      <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 12, marginBottom: 24 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
          <thead>
            <tr>
              <th style={th}>Coin</th><th style={th}>Signal</th><th style={th}>Reason</th>
              <th style={th}>Trigger</th><th style={th}>Conf.</th>
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
                </td>
                <td style={td}><SignalBadge signal={s.signal} /></td>
                <td style={{ ...td, color: 'var(--text-secondary)', maxWidth: 380 }}>
                  {s.evidence.length ? s.evidence.slice(0, 3).join('; ') : '—'}
                  {s.missing.length > 0 && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>missing: {s.missing.join(', ')}</div>
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
              <tr><td style={td} colSpan={5}>collecting…</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Scanner candidates with reasons */}
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 10px' }}>Which-coin Scanner</h3>
      <div style={{ border: '1px solid var(--border)', borderRadius: 12, padding: '4px 0', marginBottom: 24 }}>
        {candidates.length === 0 && (
          <div style={{ padding: '12px 16px', fontSize: 13, color: 'var(--text-muted)' }}>
            {scanner?.available ? 'no surges detected in the latest scan' : 'collecting…'}
          </div>
        )}
        {candidates.slice(0, 8).map(c => (
          <div key={c.symbol} style={{ display: 'flex', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: 13, alignItems: 'baseline' }}>
            <span style={{ fontWeight: 700, minWidth: 90 }}>{c.symbol}</span>
            <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>score {c.score}</span>
            <span style={{ color: 'var(--text-secondary)' }}>{c.reasons.join(' · ')}</span>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.6 }}>
        Fused score = weighted quant × sentiment × psychology (psych weight structurally capped — psychology never
        trades alone). Shock figures are an estimated proxy (volatility σ + volume), not real liquidation data.
        All trading is simulated.
        {psych?.created_at && <> · psych as of {psych.created_at}</>}
        {scanner?.created_at && <> · scan as of {scanner.created_at}</>}
      </p>
    </div>
  )
}

export default SignalsBoardPage
