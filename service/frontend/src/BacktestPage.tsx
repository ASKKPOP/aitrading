import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useLocation, useNavigate } from 'react-router-dom'

import { API_BASE, MARKETS, useLanguage } from './appShared'
import { tr } from './i18n'

interface BacktestSummary {
  initial_cash: number
  final_value: number
  total_return_pct: number
  max_drawdown_pct: number
  trade_count: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  sharpe_ratio: number | null
}

interface CurvePoint {
  timestamp: string
  portfolio_value: number
  cash: number
  position_value: number
}

interface ClosedTrade {
  symbol: string
  market: string
  direction: string
  entry_price: number
  exit_price: number
  quantity: number
  pnl: number
  opened_at: string
  closed_at: string
}

interface OpenPosition {
  symbol: string
  market: string
  direction: string
  quantity: number
  avg_entry_price: number
  last_price: number
  unrealised_pnl: number
}

interface BacktestResult {
  agent_id: number
  start_at: string
  end_at: string
  summary: BacktestSummary
  closed_trades: ClosedTrade[]
  open_positions: OpenPosition[]
  curve: CurvePoint[]
}

interface RunSummary {
  run_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  config: {
    start_at: string
    end_at: string
    initial_cash: number
    market?: string | null
    symbol?: string | null
  }
  result: {
    summary: BacktestSummary
    closed_trades: ClosedTrade[]
    open_positions: OpenPosition[]
    curve: CurvePoint[]
  } | null
  error_msg: string | null
  created_at: string
  completed_at: string | null
}

interface Strategy {
  strategy_id: number
  name: string
  backtest_validated: boolean
}

function fmt(n: number, decimals = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function pct(n: number) {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${fmt(n)}%`
}

/** Format an ISO timestamp to a compact axis label: "Jan 15" or "Jan 15 10:30". */
function fmtAxisDate(ts: string): string {
  const d = new Date(ts.endsWith('Z') ? ts : ts.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return ts.slice(5, 10)
  const month = d.toLocaleString(undefined, { month: 'short' })
  const day = d.getDate()
  const h = d.getUTCHours()
  const m = d.getUTCMinutes()
  if (h !== 0 || m !== 0) return `${month} ${day} ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  return `${month} ${day}`
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="experiment-panel" style={{ padding: '16px', minWidth: 140 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || 'var(--text-primary)', fontFamily: 'monospace' }}>{value}</div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="experiment-panel" style={{ padding: '16px', minWidth: 140 }}>
      <div style={{ height: 12, width: '60%', background: 'var(--border-color, #333)', borderRadius: 4, marginBottom: 8 }} />
      <div style={{ height: 22, width: '80%', background: 'var(--border-color, #333)', borderRadius: 4 }} />
    </div>
  )
}

const RUN_STATUS_LABEL: Record<string, string> = {
  pending: 'Queued…',
  running: 'Running…',
  completed: 'Complete',
  failed: 'Failed',
}

export function BacktestPage({ token }: { token?: string | null }) {
  const { language } = useLanguage()
  const location = useLocation()
  const navigate = useNavigate()

  // ── Form state ────────────────────────────────────────────────────────────
  const [agentId, setAgentId] = useState('')
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [initialCash, setInitialCash] = useState('100000')
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')

  // ── Result state ──────────────────────────────────────────────────────────
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTrades, setShowTrades] = useState(false)

  // ── Async run state (authenticated only) ─────────────────────────────────
  const [currentRunId, setCurrentRunId] = useState<number | null>(null)
  const [runStatus, setRunStatus] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Run history ───────────────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunSummary[]>([])

  // ── Promote flow ──────────────────────────────────────────────────────────
  const [promotingRunId, setPromotingRunId] = useState<number | null>(null)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [selectedStrategyId, setSelectedStrategyId] = useState('')
  const [promoteMsg, setPromoteMsg] = useState<string | null>(null)

  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

  // ── Run history loader ────────────────────────────────────────────────────
  const loadRuns = async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/backtest/runs`, { headers: authHeaders })
      if (res.ok) setRuns(((await res.json()) as { runs: RunSummary[] }).runs ?? [])
    } catch { /* ignore network hiccups */ }
  }

  useEffect(() => { void loadRuns() }, [token])

  // ── Polling ───────────────────────────────────────────────────────────────
  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  useEffect(() => () => stopPolling(), [])

  const startPolling = (runId: number) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/backtest/runs/${runId}`, { headers: authHeaders })
        if (!res.ok) { stopPolling(); setLoading(false); return }
        const run = await res.json() as RunSummary
        setRunStatus(run.status)
        if (run.status === 'completed') {
          stopPolling()
          setLoading(false)
          if (run.result) setResult({ agent_id: Number(agentId) || 0, start_at: run.config.start_at, end_at: run.config.end_at, ...run.result })
          void loadRuns()
        } else if (run.status === 'failed') {
          stopPolling()
          setLoading(false)
          setError(run.error_msg || 'Backtest failed')
          void loadRuns()
        }
      } catch { stopPolling(); setLoading(false) }
    }, 1500)
  }

  // ── URL param pre-fill + auto-run ─────────────────────────────────────────
  useEffect(() => {
    const p = new URLSearchParams(location.search)
    const agentParam = p.get('agent')
    if (!agentParam) return
    const days = Math.max(7, Math.min(365, Number(p.get('days')) || 90))
    const endDt = new Date()
    const startDt = new Date(endDt.getTime() - days * 86400_000)
    const startStr = startDt.toISOString().slice(0, 16)
    const endStr = endDt.toISOString().slice(0, 16)
    setAgentId(agentParam)
    setStartAt(startStr)
    setEndAt(endStr)
    void runSyncBacktest(agentParam, new Date(startStr).toISOString(), new Date(endStr).toISOString())
  }, [location.search])

  // ── Sync run (public / no token) ──────────────────────────────────────────
  const runSyncBacktest = async (aid: string, sat: string, eat: string) => {
    if (!aid || !sat || !eat) return
    setLoading(true); setError(null); setResult(null)
    try {
      const params = new URLSearchParams({ agent_id: aid, start_at: sat, end_at: eat, initial_cash: initialCash })
      if (market) params.set('market', market)
      if (symbol) params.set('symbol', symbol.toUpperCase())
      const res = await fetch(`${API_BASE}/research/backtest?${params}`)
      if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error((b as any).detail || `HTTP ${res.status}`) }
      setResult(await res.json())
    } catch (e: any) { setError(e.message || 'Unknown error') }
    finally { setLoading(false) }
  }

  // ── Async run (authenticated) ─────────────────────────────────────────────
  const runAsyncBacktest = async () => {
    if (!agentId || !startAt || !endAt || !token) return
    setLoading(true); setError(null); setResult(null); setRunStatus('pending'); stopPolling()
    try {
      const res = await fetch(`${API_BASE}/backtest/runs`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_at: new Date(startAt).toISOString(),
          end_at: new Date(endAt).toISOString(),
          initial_cash: Number(initialCash) || 100_000,
          market: market || null,
          symbol: symbol ? symbol.toUpperCase() : null,
        }),
      })
      if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error((b as any).detail || `HTTP ${res.status}`) }
      const { run_id } = await res.json() as { run_id: number }
      setCurrentRunId(run_id)
      startPolling(run_id)
    } catch (e: any) { setError(e.message || 'Unknown error'); setLoading(false); setRunStatus(null) }
  }

  const runBacktest = async () => {
    if (!agentId || !startAt || !endAt) return
    navigate(`/backtest?agent=${agentId}`, { replace: true })
    if (token) await runAsyncBacktest()
    else await runSyncBacktest(agentId, new Date(startAt).toISOString(), new Date(endAt).toISOString())
  }

  // ── Load a historical run into the result view ────────────────────────────
  const loadRunResult = (run: RunSummary) => {
    if (!run.result) return
    setResult({ agent_id: 0, start_at: run.config.start_at, end_at: run.config.end_at, ...run.result })
    setCurrentRunId(run.run_id)
    setRunStatus(run.status)
  }

  // ── Promote flow ──────────────────────────────────────────────────────────
  const openPromote = async (runId: number) => {
    setPromotingRunId(runId); setPromoteMsg(null); setSelectedStrategyId('')
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/strategies`, { headers: authHeaders })
      if (res.ok) setStrategies(((await res.json()) as { strategies: Strategy[] }).strategies ?? [])
    } catch { /* ignore */ }
  }

  const doPromote = async () => {
    if (!promotingRunId || !selectedStrategyId || !token) return
    try {
      const res = await fetch(`${API_BASE}/backtest/runs/${promotingRunId}/promote`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_id: Number(selectedStrategyId) }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = await res.json() as { backtest_validated: boolean }
      setPromoteMsg(body.backtest_validated ? '✅ Strategy validated' : '⚠️ Updated (Sharpe ≤ 0)')
      setPromotingRunId(null)
      void loadRuns()
    } catch (e: any) { setPromoteMsg(`Error: ${e.message}`) }
  }

  // ── Chart data ────────────────────────────────────────────────────────────
  const curveData = result?.curve.map((p) => ({
    t: fmtAxisDate(p.timestamp),
    value: p.portfolio_value,
  })) ?? []

  const returnColor = result && result.summary.total_return_pct >= 0 ? 'var(--success)' : 'var(--error)'

  const benchmark = useMemo(() => {
    if (!result || result.closed_trades.length === 0) return null
    const first = result.closed_trades[0]
    const last = result.closed_trades[result.closed_trades.length - 1]
    const shares = result.summary.initial_cash / first.entry_price
    const finalValue = shares * last.exit_price
    const returnPct = (finalValue - result.summary.initial_cash) / result.summary.initial_cash * 100
    return { finalValue, returnPct, symbol: first.symbol }
  }, [result])

  const chartData = useMemo(() => {
    if (!curveData.length) return curveData as { t: string; value: number; bh: number | null }[]
    return curveData.map((p, i) => ({
      ...p,
      bh: benchmark
        ? i === 0 ? result!.summary.initial_cash
          : i === curveData.length - 1 ? benchmark.finalValue
          : null
        : null,
    }))
  }, [curveData, benchmark, result])

  const runBtnLabel = loading
    ? (runStatus ? (RUN_STATUS_LABEL[runStatus] ?? 'Running…') : tr(language, { en: 'Running…', ja: '実行中…', th: 'กำลังรัน…', vi: 'Đang chạy…' }))
    : tr(language, { en: 'Run Backtest', ja: 'バックテスト実行', th: 'รันแบ็คเทสต์', vi: 'Chạy Backtest' })

  return (
    <div className="experiment-page">
      <div className="header">
        <div>
          <h1 className="header-title">
            {tr(language, { en: 'Backtest', ja: 'バックテスト', th: 'แบ็คเทสต์', vi: 'Backtest' })}
          </h1>
          <p className="header-subtitle">
            {tr(language, {
              en: 'Replay an agent\'s recorded trades against stored execution prices',
              ja: 'エージェントの記録済みトレードを保存された執行価格でリプレイ',
              th: 'เล่นซ้ำการเทรดที่บันทึกไว้ของเอเจนต์กับราคาที่จัดเก็บ',
              vi: 'Phát lại giao dịch đã ghi của agent với giá thực thi đã lưu',
            })}
          </p>
        </div>
      </div>

      {/* Parameters */}
      <section className="experiment-panel">
        <div className="experiment-section-header">
          <h2>{tr(language, { en: 'Parameters', ja: 'パラメーター', th: 'พารามิเตอร์', vi: 'Tham số' })}</h2>
        </div>
        <div className="research-filter-grid">
          <input
            className="form-input"
            type="number"
            min="1"
            placeholder={tr(language, { en: 'Agent ID', ja: 'エージェントID', th: 'รหัสเอเจนต์', vi: 'ID đại lý' })}
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          />
          <input
            className="form-input"
            type="datetime-local"
            placeholder="Start"
            value={startAt}
            onChange={(e) => setStartAt(e.target.value)}
          />
          <input
            className="form-input"
            type="datetime-local"
            placeholder="End"
            value={endAt}
            onChange={(e) => setEndAt(e.target.value)}
          />
          <input
            className="form-input"
            type="number"
            min="1"
            placeholder={tr(language, { en: 'Initial cash', ja: '初期資金', th: 'เงินเริ่มต้น', vi: 'Tiền ban đầu' })}
            value={initialCash}
            onChange={(e) => setInitialCash(e.target.value)}
          />
          <select className="form-select" value={market} onChange={(e) => setMarket(e.target.value)}>
            <option value="">{tr(language, { en: 'All markets', ja: 'すべての市場', th: 'ตลาดทั้งหมด', vi: 'Tất cả thị trường' })}</option>
            {MARKETS.filter((m) => m.value !== 'all').map((m) => (
              <option key={m.value} value={m.value}>{m.labels[language]}</option>
            ))}
          </select>
          <input
            className="form-input"
            placeholder={tr(language, { en: 'Symbol (optional)', ja: 'シンボル（任意）', th: 'สัญลักษณ์ (ไม่บังคับ)', vi: 'Mã (tuỳ chọn)' })}
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={runBacktest}
            disabled={loading || !agentId || !startAt || !endAt}
            style={{ gridColumn: '1 / -1' }}
          >
            {runBtnLabel}
          </button>
        </div>
        {error && <p style={{ color: 'var(--error)', marginTop: 8 }}>{error}</p>}
      </section>

      {/* Run history (authenticated) */}
      {token && runs.length > 0 && (
        <section className="experiment-panel">
          <div className="experiment-section-header">
            <h2>{tr(language, { en: 'Run History', ja: '実行履歴', th: 'ประวัติการรัน', vi: 'Lịch sử chạy' })}</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {runs.map((run) => (
              <div
                key={run.run_id}
                style={{
                  display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
                  padding: '8px 0', borderBottom: '1px solid var(--border-color, #333)',
                  background: run.run_id === currentRunId ? 'var(--surface-hover, rgba(255,255,255,.04))' : undefined,
                }}
              >
                <span style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text-muted)' }}>#{run.run_id}</span>
                <span
                  className="experiment-badge"
                  style={{ background: run.status === 'completed' ? 'var(--success-dim, #1a3a1a)' : run.status === 'failed' ? 'var(--error-dim, #3a1a1a)' : undefined }}
                >
                  {run.status}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {run.config.start_at?.slice(0, 10)} → {run.config.end_at?.slice(0, 10)}
                </span>
                {run.config.symbol && <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{run.config.symbol}</span>}
                {run.status === 'completed' && run.result && (
                  <span style={{ fontFamily: 'monospace', fontSize: 12, color: run.result.summary.total_return_pct >= 0 ? 'var(--success)' : 'var(--error)' }}>
                    {pct(run.result.summary.total_return_pct)}
                  </span>
                )}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                  {run.status === 'completed' && run.result && (
                    <>
                      <button className="btn btn-secondary" style={{ padding: '2px 10px', fontSize: 12 }} onClick={() => loadRunResult(run)}>
                        {tr(language, { en: 'View', ja: '表示', th: 'ดู', vi: 'Xem' })}
                      </button>
                      <button className="btn btn-secondary" style={{ padding: '2px 10px', fontSize: 12 }} onClick={() => openPromote(run.run_id)}>
                        {tr(language, { en: 'Promote', ja: '昇格', th: 'โปรโมต', vi: 'Thăng cấp' })}
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Promote panel */}
      {promotingRunId !== null && (
        <section className="experiment-panel">
          <div className="experiment-section-header">
            <h2>{tr(language, { en: 'Promote to Strategy', ja: 'ストラテジーに昇格', th: 'โปรโมตเป็นกลยุทธ์', vi: 'Thăng cấp thành chiến lược' })}</h2>
          </div>
          {strategies.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              {tr(language, { en: 'No strategies found.', ja: 'ストラテジーが見つかりません。', th: 'ไม่พบกลยุทธ์', vi: 'Không tìm thấy chiến lược.' })}
            </p>
          ) : (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
              <select className="form-select" value={selectedStrategyId} onChange={(e) => setSelectedStrategyId(e.target.value)} style={{ minWidth: 200 }}>
                <option value="">— {tr(language, { en: 'Select strategy', ja: 'ストラテジーを選択', th: 'เลือกกลยุทธ์', vi: 'Chọn chiến lược' })} —</option>
                {strategies.map((s) => (
                  <option key={s.strategy_id} value={s.strategy_id}>{s.name}{s.backtest_validated ? ' ✅' : ''}</option>
                ))}
              </select>
              <button className="btn btn-primary" onClick={doPromote} disabled={!selectedStrategyId}>
                {tr(language, { en: 'Confirm', ja: '確認', th: 'ยืนยัน', vi: 'Xác nhận' })}
              </button>
              <button className="btn btn-secondary" onClick={() => setPromotingRunId(null)}>
                {tr(language, { en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy' })}
              </button>
            </div>
          )}
          {promoteMsg && <p style={{ marginTop: 8, fontSize: 14 }}>{promoteMsg}</p>}
        </section>
      )}

      {/* Loading skeleton */}
      {loading && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, margin: '16px 0' }}>
            {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
          <section className="experiment-panel">
            <div style={{ height: 260, background: 'var(--border-color, #333)', borderRadius: 8, opacity: 0.4 }} />
          </section>
        </>
      )}

      {result && (
        <>
          {/* Summary */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, margin: '16px 0' }}>
            <SummaryCard
              label={tr(language, { en: 'Total Return', ja: 'トータルリターン', th: 'ผลตอบแทนรวม', vi: 'Lợi nhuận tổng' })}
              value={pct(result.summary.total_return_pct)}
              color={returnColor}
            />
            <SummaryCard
              label={tr(language, { en: 'Final Value', ja: '最終価値', th: 'มูลค่าสุดท้าย', vi: 'Giá trị cuối' })}
              value={`$${fmt(result.summary.final_value)}`}
            />
            <SummaryCard
              label={tr(language, { en: 'Max Drawdown', ja: '最大ドローダウン', th: 'ดรอดาวน์สูงสุด', vi: 'Sụt giảm tối đa' })}
              value={`−${fmt(result.summary.max_drawdown_pct)}%`}
              color="var(--error)"
            />
            <SummaryCard
              label={tr(language, { en: 'Trades', ja: 'トレード数', th: 'จำนวนการเทรด', vi: 'Số giao dịch' })}
              value={`${result.summary.trade_count} (${result.summary.winning_trades}W / ${result.summary.losing_trades}L)`}
            />
            <SummaryCard
              label={tr(language, { en: 'Win Rate', ja: '勝率', th: 'อัตราชนะ', vi: 'Tỷ lệ thắng' })}
              value={pct(result.summary.win_rate * 100)}
            />
            {result.summary.sharpe_ratio !== null && (
              <SummaryCard
                label={tr(language, { en: 'Sharpe', ja: 'シャープ比', th: 'ชาร์ป', vi: 'Sharpe' })}
                value={fmt(result.summary.sharpe_ratio, 3)}
              />
            )}
            {benchmark && (
              <SummaryCard
                label={tr(language, { en: `Alpha vs B&H ${benchmark.symbol}`, ja: `α vs B&H ${benchmark.symbol}`, th: `อัลฟา vs B&H ${benchmark.symbol}`, vi: `Alpha vs B&H ${benchmark.symbol}` })}
                value={pct(result.summary.total_return_pct - benchmark.returnPct)}
                color={result.summary.total_return_pct >= benchmark.returnPct ? 'var(--success)' : 'var(--error)'}
              />
            )}
          </div>

          {/* Portfolio curve */}
          {curveData.length > 1 && (
            <section className="experiment-panel">
              <div className="experiment-section-header">
                <h2>{tr(language, { en: 'Portfolio Curve', ja: 'ポートフォリオ推移', th: 'กราฟพอร์ตโฟลิโอ', vi: 'Đường cong danh mục' })}</h2>
              </div>
              {benchmark && (
                <div style={{ display: 'flex', gap: 20, fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ display: 'inline-block', width: 20, height: 2, background: returnColor }} />
                    {tr(language, { en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' })}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ display: 'inline-block', width: 20, height: 2, background: 'var(--text-muted, #888)', borderTop: '2px dashed var(--text-muted, #888)' }} />
                    {tr(language, { en: `Buy & Hold ${benchmark.symbol}`, ja: `${benchmark.symbol} 保有`, th: `ถือ ${benchmark.symbol}`, vi: `Giữ ${benchmark.symbol}` })}
                  </span>
                </div>
              )}
              <div style={{ height: 260, marginTop: 12 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color, #333)" />
                    <XAxis dataKey="t" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                    <YAxis
                      domain={['auto', 'auto']}
                      tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                      tick={{ fontSize: 10 }}
                      width={56}
                    />
                    <Tooltip
                      formatter={(v, name) => [
                        `$${fmt(Number(v))}`,
                        name === 'bh'
                          ? `Buy & Hold ${benchmark?.symbol ?? ''}`
                          : tr(language, { en: 'Portfolio', ja: 'ポートフォリオ', th: 'พอร์ตโฟลิโอ', vi: 'Danh mục' }),
                      ]}
                    />
                    <ReferenceLine y={result.summary.initial_cash} stroke="var(--text-muted, #888)" strokeDasharray="4 2" />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke={returnColor}
                      dot={false}
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                    {benchmark && (
                      <Line
                        type="linear"
                        dataKey="bh"
                        stroke="var(--text-muted, #888)"
                        strokeDasharray="6 3"
                        dot={false}
                        strokeWidth={1.5}
                        connectNulls
                        isAnimationActive={false}
                      />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          {/* Open positions */}
          {result.open_positions.length > 0 && (
            <section className="experiment-panel">
              <div className="experiment-section-header">
                <h2>
                  {tr(language, { en: 'Open Positions', ja: 'オープンポジション', th: 'โพซิชันที่เปิดอยู่', vi: 'Vị thế đang mở' })}
                  <span className="experiment-badge" style={{ marginLeft: 8 }}>{result.open_positions.length}</span>
                </h2>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border-color, #333)' }}>
                      {['Symbol', 'Dir', 'Qty', 'Entry', 'Last', 'Unrealised P&L'].map((h) => (
                        <th key={h} style={{ padding: '6px 8px', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.open_positions.map((p, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--border-color, #222)' }}>
                        <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>{p.symbol}</td>
                        <td style={{ padding: '6px 8px' }}>{p.direction}</td>
                        <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>{fmt(p.quantity, 4)}</td>
                        <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>${fmt(p.avg_entry_price)}</td>
                        <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>${fmt(p.last_price)}</td>
                        <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: p.unrealised_pnl >= 0 ? 'var(--success)' : 'var(--error)' }}>
                          {pct(p.unrealised_pnl / result.summary.initial_cash * 100)} (${fmt(p.unrealised_pnl)})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Closed trades toggle */}
          {result.closed_trades.length > 0 ? (
            <section className="experiment-panel">
              <div className="experiment-section-header" style={{ cursor: 'pointer' }} onClick={() => setShowTrades(!showTrades)}>
                <h2>
                  {tr(language, { en: 'Closed Trades', ja: 'クローズトレード', th: 'การเทรดที่ปิดแล้ว', vi: 'Giao dịch đã đóng' })}
                  <span className="experiment-badge" style={{ marginLeft: 8 }}>{result.closed_trades.length}</span>
                </h2>
                <span>{showTrades ? '▲' : '▼'}</span>
              </div>
              {showTrades && (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginTop: 8 }}>
                    <thead>
                      <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border-color, #333)' }}>
                        {['Symbol', 'Dir', 'Qty', 'Entry', 'Exit', 'P&L', 'Closed At'].map((h) => (
                          <th key={h} style={{ padding: '6px 8px', fontWeight: 600 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.closed_trades.map((t, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--border-color, #222)' }}>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>{t.symbol}</td>
                          <td style={{ padding: '6px 8px' }}>{t.direction}</td>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>{fmt(t.quantity, 4)}</td>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>${fmt(t.entry_price)}</td>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace' }}>${fmt(t.exit_price)}</td>
                          <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: t.pnl >= 0 ? 'var(--success)' : 'var(--error)' }}>
                            ${fmt(t.pnl)}
                          </td>
                          <td style={{ padding: '6px 8px', fontSize: 11, color: 'var(--text-muted)' }}>{fmtAxisDate(t.closed_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ) : (
            <section className="experiment-panel" style={{ textAlign: 'center', padding: '24px 16px', color: 'var(--text-muted)' }}>
              {tr(language, {
                en: 'No closed trades in this period. Try widening the date range.',
                ja: 'この期間にクローズトレードはありません。日付範囲を広げてみてください。',
                th: 'ไม่มีการเทรดที่ปิดแล้วในช่วงนี้ ลองขยายช่วงวันที่',
                vi: 'Không có giao dịch đã đóng trong kỳ này. Hãy thử mở rộng phạm vi ngày.',
              })}
              {result.open_positions.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13 }}>
                  {tr(language, {
                    en: `(${result.open_positions.length} open position(s) not yet closed)`,
                    ja: `(${result.open_positions.length} 件のオープンポジションがまだクローズされていません)`,
                    th: `(${result.open_positions.length} โพซิชันที่ยังเปิดอยู่)`,
                    vi: `(${result.open_positions.length} vị thế đang mở chưa đóng)`,
                  })}
                </div>
              )}
            </section>
          )}

          {/* CTA: follow this agent */}
          {result.summary.trade_count > 0 && (
            <section className="experiment-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, padding: '16px 20px' }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 2 }}>
                  {tr(language, {
                    en: `Agent #${result.agent_id} · ${result.summary.total_return_pct >= 0 ? '+' : ''}${fmt(result.summary.total_return_pct)}% return`,
                    ja: `エージェント #${result.agent_id} · ${result.summary.total_return_pct >= 0 ? '+' : ''}${fmt(result.summary.total_return_pct)}% リターン`,
                    th: `เอเจนต์ #${result.agent_id} · ผลตอบแทน ${result.summary.total_return_pct >= 0 ? '+' : ''}${fmt(result.summary.total_return_pct)}%`,
                    vi: `Agent #${result.agent_id} · lợi nhuận ${result.summary.total_return_pct >= 0 ? '+' : ''}${fmt(result.summary.total_return_pct)}%`,
                  })}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {tr(language, {
                    en: 'Follow this agent to mirror their trades automatically.',
                    ja: 'このエージェントをフォローしてトレードを自動ミラーリング。',
                    th: 'ติดตามเอเจนต์นี้เพื่อคัดลอกการเทรดอัตโนมัติ',
                    vi: 'Theo dõi agent này để sao chép giao dịch tự động.',
                  })}
                </div>
              </div>
              <a href={`/agent/${result.agent_id}`} className="btn btn-primary" style={{ whiteSpace: 'nowrap' }}>
                {tr(language, { en: 'View Profile', ja: 'プロフィールを見る', th: 'ดูโปรไฟล์', vi: 'Xem hồ sơ' })}
              </a>
            </section>
          )}
        </>
      )}
    </div>
  )
}
