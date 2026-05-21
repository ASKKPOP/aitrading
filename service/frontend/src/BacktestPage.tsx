import { useEffect, useMemo, useState } from 'react'
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

function fmt(n: number, decimals = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function pct(n: number) {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${fmt(n)}%`
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="experiment-panel" style={{ padding: '16px', minWidth: 140 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || 'var(--text-primary)', fontFamily: 'monospace' }}>{value}</div>
    </div>
  )
}

export function BacktestPage() {
  const { language } = useLanguage()
  const location = useLocation()
  const navigate = useNavigate()
  const [agentId, setAgentId] = useState('')
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [initialCash, setInitialCash] = useState('100000')
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTrades, setShowTrades] = useState(false)

  // Pre-fill form from URL params and auto-run when ?agent= is present.
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
    // Run immediately using local values — state hasn't flushed yet.
    void runBacktestWith(agentParam, new Date(startStr).toISOString(), new Date(endStr).toISOString())
  }, [location.search])

  const runBacktestWith = async (aid: string, sat: string, eat: string) => {
    if (!aid || !sat || !eat) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const params = new URLSearchParams({ agent_id: aid, start_at: sat, end_at: eat, initial_cash: initialCash })
      if (market) params.set('market', market)
      if (symbol) params.set('symbol', symbol.toUpperCase())
      const res = await fetch(`${API_BASE}/research/backtest?${params}`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      setResult(await res.json())
    } catch (e: any) {
      setError(e.message || 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const runBacktest = async () => {
    if (!agentId || !startAt || !endAt) return
    navigate(`/backtest?agent=${agentId}`, { replace: true })
    await runBacktestWith(agentId, new Date(startAt).toISOString(), new Date(endAt).toISOString())
  }

  const curveData = result?.curve.map((p) => ({
    t: p.timestamp.replace('T', ' ').replace('Z', ''),
    value: p.portfolio_value,
  })) ?? []

  const returnColor = result && result.summary.total_return_pct >= 0 ? 'var(--accent-green, #4caf50)' : 'var(--accent-red, #f44336)'

  // Buy-and-hold benchmark: invest all cash in first traded symbol at its entry
  // price, close at the last exit price. Computable from closed_trades alone.
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
          >
            {loading
              ? tr(language, { en: 'Running…', ja: '実行中…', th: 'กำลังรัน…', vi: 'Đang chạy…' })
              : tr(language, { en: 'Run Backtest', ja: 'バックテスト実行', th: 'รันแบ็คเทสต์', vi: 'Chạy Backtest' })}
          </button>
        </div>
        {error && <p style={{ color: 'var(--accent-red, #f44336)', marginTop: 8 }}>{error}</p>}
      </section>

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
              color="var(--accent-red, #f44336)"
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
                color={result.summary.total_return_pct >= benchmark.returnPct ? 'var(--accent-green, #4caf50)' : 'var(--accent-red, #f44336)'}
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
                      <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: p.unrealised_pnl >= 0 ? 'var(--accent-green, #4caf50)' : 'var(--accent-red, #f44336)' }}>
                        {pct(p.unrealised_pnl / result.summary.initial_cash * 100)} (${fmt(p.unrealised_pnl)})
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {/* Closed trades toggle */}
          {result.closed_trades.length > 0 && (
            <section className="experiment-panel">
              <div className="experiment-section-header" style={{ cursor: 'pointer' }} onClick={() => setShowTrades(!showTrades)}>
                <h2>
                  {tr(language, { en: 'Closed Trades', ja: 'クローズトレード', th: 'การเทรดที่ปิดแล้ว', vi: 'Giao dịch đã đóng' })}
                  <span className="experiment-badge" style={{ marginLeft: 8 }}>{result.closed_trades.length}</span>
                </h2>
                <span>{showTrades ? '▲' : '▼'}</span>
              </div>
              {showTrades && (
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
                        <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: t.pnl >= 0 ? 'var(--accent-green, #4caf50)' : 'var(--accent-red, #f44336)' }}>
                          ${fmt(t.pnl)}
                        </td>
                        <td style={{ padding: '6px 8px', fontSize: 11, color: 'var(--text-muted)' }}>{t.closed_at.replace('T', ' ').replace('Z', '')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}
