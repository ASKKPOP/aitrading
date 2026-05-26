import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// ─────────────────────────────────────────────────────────────────────────────
// Agent Profile Page
// ─────────────────────────────────────────────────────────────────────────────

type AgentProfile = {
  agent_id: number
  name: string
  cash: number
  profit_pct: number
  trade_count: number
  recent_signals: {
    signal_id: number
    symbol: string
    side: string
    entry_price: number | null
    quantity: number | null
    created_at: string
  }[]
  equity_curve: { t: string; v: number }[]
}

export function AgentProfilePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { language } = useLanguage()
  const [profile, setProfile] = useState<AgentProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!id) return
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/agents/${id}/profile`)
        if (res.status === 404) { setNotFound(true); setLoading(false); return }
        if (!res.ok) throw new Error('fetch failed')
        setProfile(await res.json())
      } catch (e) {
        console.error(e)
      }
      setLoading(false)
    }
    load()
  }, [id])

  if (loading) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '13px' }}>
        {tr(language, { en: 'Loading…', ja: '読み込み中…', th: 'กำลังโหลด…', vi: 'Đang tải…' })}
      </div>
    )
  }

  if (notFound || !profile) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center' }}>
        <div style={{ fontSize: '40px', marginBottom: '12px' }}>◇</div>
        <div style={{ fontWeight: 600, fontSize: '18px', marginBottom: '8px' }}>
          {tr(language, { en: 'Agent not found', ja: 'エージェントが見つかりません', th: 'ไม่พบเอเจนต์', vi: 'Không tìm thấy agent' })}
        </div>
        <button className="btn btn-secondary" onClick={() => navigate('/leaderboard')}>
          {tr(language, { en: '← Leaderboard', ja: '← リーダーボード', th: '← อันดับ', vi: '← Bảng xếp hạng' })}
        </button>
      </div>
    )
  }

  const pnlColor = profile.profit_pct >= 0 ? 'var(--success)' : 'var(--error)'
  const pnlSign = profile.profit_pct >= 0 ? '+' : ''
  const cashProfit = profile.cash - 100000
  const hasEquityCurve = profile.equity_curve.length > 0

  return (
    <div style={{ maxWidth: '760px' }}>
      {/* Back button */}
      <button
        className="btn btn-ghost"
        style={{ marginBottom: '20px', fontSize: '12px', fontFamily: 'var(--font-mono)' }}
        onClick={() => navigate(-1)}
      >
        ← {tr(language, { en: 'Back', ja: '戻る', th: 'กลับ', vi: 'Quay lại' })}
      </button>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '28px' }}>
        <div className="agent-avatar-sm" style={{ width: '48px', height: '48px', fontSize: '20px', borderRadius: '14px' }}>
          {profile.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: '22px', fontWeight: 700, lineHeight: 1.2 }}>{profile.name}</h1>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '4px' }}>
            id:{profile.agent_id}
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '12px',
        marginBottom: '28px',
      }}>
        {[
          {
            label: tr(language, { en: 'Portfolio', ja: 'ポートフォリオ', th: 'พอร์ตโฟลิโอ', vi: 'Danh mục' }),
            value: `$${profile.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
            sub: cashProfit >= 0 ? `+$${cashProfit.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `-$${Math.abs(cashProfit).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
            subColor: cashProfit >= 0 ? 'var(--success)' : 'var(--error)',
          },
          {
            label: tr(language, { en: 'Return', ja: 'リターン', th: 'ผลตอบแทน', vi: 'Lợi suất' }),
            value: `${pnlSign}${profile.profit_pct.toFixed(2)}%`,
            valueColor: pnlColor,
          },
          {
            label: tr(language, { en: 'Trades', ja: '取引数', th: 'จำนวนการเทรด', vi: 'Số giao dịch' }),
            value: profile.trade_count.toLocaleString(),
          },
        ].map(({ label, value, valueColor, sub, subColor }) => (
          <div key={label} className="card" style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '8px', fontFamily: 'var(--font-mono)' }}>
              {label}
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: valueColor || 'var(--text-primary)' }}>
              {value}
            </div>
            {sub && (
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: subColor || 'var(--text-muted)', marginTop: '4px' }}>
                {sub}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Equity curve */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '14px', fontFamily: 'var(--font-mono)' }}>
          {tr(language, { en: 'Equity Curve (90d)', ja: 'エクイティカーブ (90日)', th: 'เส้นทุน (90 วัน)', vi: 'Đường vốn (90 ngày)' })}
        </div>
        {hasEquityCurve ? (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={profile.equity_curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" strokeOpacity={0.4} />
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
              <YAxis
                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                tickLine={false}
                axisLine={false}
                width={64}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', fontSize: '12px' }}
                formatter={(v) => {
                  const num = typeof v === 'number' ? v : null
                  return num != null ? [`$${num.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, tr(language, { en: 'Value', ja: '価値', th: 'มูลค่า', vi: 'Giá trị' })] as [string, string] : ['-', ''] as [string, string]
                }}
              />
              <Line type="monotone" dataKey="v" stroke="var(--accent-primary)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ height: '160px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '13px', fontFamily: 'var(--font-mono)' }}>
            {tr(language, { en: 'No history yet', ja: '履歴なし', th: 'ยังไม่มีประวัติ', vi: 'Chưa có lịch sử' })}
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <button
          className="btn btn-secondary"
          onClick={() => navigate(`/backtest?agent=${profile.agent_id}&days=90`)}
          style={{ fontSize: '13px' }}
        >
          ⏮ {tr(language, { en: 'Run Backtest', ja: 'バックテスト', th: 'แบ็คเทสต์', vi: 'Backtest' })}
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => navigate(`/copytrading`)}
          style={{ fontSize: '13px' }}
        >
          ⊞ {tr(language, { en: 'Copy Trade', ja: 'コピートレード', th: 'คัดลอกเทรด', vi: 'Sao chép' })}
        </button>
      </div>

      {/* Recent trades */}
      <div className="card" style={{ padding: '20px' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: '14px', fontFamily: 'var(--font-mono)' }}>
          {tr(language, { en: 'Recent Trades', ja: '最近の取引', th: 'การเทรดล่าสุด', vi: 'Giao dịch gần đây' })}
        </div>
        {profile.recent_signals.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', fontFamily: 'var(--font-mono)', textAlign: 'center', padding: '20px 0' }}>
            {tr(language, { en: 'No trades yet', ja: '取引なし', th: 'ยังไม่มีการเทรด', vi: 'Chưa có giao dịch' })}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', fontFamily: 'var(--font-mono)' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                <th style={{ textAlign: 'left', paddingBottom: '8px', fontWeight: 500 }}>
                  {tr(language, { en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' })}
                </th>
                <th style={{ textAlign: 'left', paddingBottom: '8px', fontWeight: 500 }}>
                  {tr(language, { en: 'Side', ja: 'サイド', th: 'ด้าน', vi: 'Chiều' })}
                </th>
                <th style={{ textAlign: 'right', paddingBottom: '8px', fontWeight: 500 }}>
                  {tr(language, { en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá' })}
                </th>
                <th style={{ textAlign: 'right', paddingBottom: '8px', fontWeight: 500 }}>
                  {tr(language, { en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' })}
                </th>
                <th style={{ textAlign: 'right', paddingBottom: '8px', fontWeight: 500 }}>
                  {tr(language, { en: 'Date', ja: '日付', th: 'วันที่', vi: 'Ngày' })}
                </th>
              </tr>
            </thead>
            <tbody>
              {profile.recent_signals.map((sig) => (
                <tr key={sig.signal_id} style={{ borderTop: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px 0', fontWeight: 600 }}>{sig.symbol || '—'}</td>
                  <td style={{ padding: '8px 0' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '2px 7px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      background: sig.side === 'buy' || sig.side === 'long' ? 'rgba(var(--success-rgb,34,197,94), 0.15)' : 'rgba(var(--error-rgb,239,68,68), 0.15)',
                      color: sig.side === 'buy' || sig.side === 'long' ? 'var(--success)' : 'var(--error)',
                    }}>
                      {sig.side}
                    </span>
                  </td>
                  <td style={{ padding: '8px 0', textAlign: 'right' }}>
                    {sig.entry_price != null ? `$${sig.entry_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : '—'}
                  </td>
                  <td style={{ padding: '8px 0', textAlign: 'right' }}>{sig.quantity ?? '—'}</td>
                  <td style={{ padding: '8px 0', textAlign: 'right', color: 'var(--text-muted)', fontSize: '11px' }}>
                    {sig.created_at?.split('T')[0] ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default AgentProfilePage
