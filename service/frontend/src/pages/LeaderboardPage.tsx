import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { API_BASE, LEADERBOARD_LINE_COLORS, LEADERBOARD_PAGE_SIZE, REFRESH_INTERVAL, LeaderboardTooltip, buildLeaderboardChartData, getLeaderboardDays, type LeaderboardChartRange, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Leaderboard Page - Top 10 Traders (no market distinction)
export function LeaderboardPage({ token }: { token?: string | null }) {
  const [profitHistory, setProfitHistory] = useState<any[]>([])
  const [totalTraders, setTotalTraders] = useState(0)
  const [leaderboardPage, setLeaderboardPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [chartRange, setChartRange] = useState<LeaderboardChartRange>('24h')
  const [metric, setMetric] = useState<'return' | 'risk' | 'collaboration' | 'quality'>('return')
  const [activeChallengeCount, setActiveChallengeCount] = useState(0)
  const { language } = useLanguage()
  const navigate = useNavigate()

  useEffect(() => {
    loadProfitHistory(leaderboardPage)
    const interval = setInterval(() => {
      loadProfitHistory(leaderboardPage)
    }, REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [chartRange, leaderboardPage, metric])

  useEffect(() => {
    const loadActiveChallengeCount = async () => {
      try {
        const res = await fetch(`${API_BASE}/challenges?status=active&limit=1`)
        if (!res.ok) return
        const data = await res.json()
        setActiveChallengeCount(data.total || 0)
      } catch (e) {
        console.error(e)
      }
    }

    loadActiveChallengeCount()
  }, [])

  const loadProfitHistory = async (pageToLoad = leaderboardPage) => {
    try {
      const days = getLeaderboardDays(chartRange)
      const offset = (pageToLoad - 1) * LEADERBOARD_PAGE_SIZE
      const res = await fetch(`${API_BASE}/profit/history?limit=${LEADERBOARD_PAGE_SIZE}&offset=${offset}&days=${days}&metric=${metric}`)
      const data = await res.json()
      setProfitHistory(data.top_agents || [])
      setTotalTraders(data.total || 0)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const handleAgentClick = (agent: any) => {
    navigate(`/agent/${agent.agent_id}`)
  }

  const chartData = useMemo(
    () => buildLeaderboardChartData(profitHistory, chartRange, language),
    [profitHistory, chartRange, language]
  )
  const topChartAgents = useMemo(() => profitHistory.slice(0, 10), [profitHistory])
  const leaderboardTotalPages = Math.max(1, Math.ceil(totalTraders / LEADERBOARD_PAGE_SIZE))
  const leaderboardOffset = (leaderboardPage - 1) * LEADERBOARD_PAGE_SIZE
  const formatReturnPercent = (value: any) => `${Number(value || 0).toFixed(2)}%`
  const metricOptions = [
    ['return', tr(language, { en: 'Return', ja: 'リターン', th: 'ผลตอบแทน', vi: 'Lợi suất' })],
    ['risk', tr(language, { en: 'Risk Adjusted', ja: 'リスク調整後', th: 'ปรับตามความเสี่ยง', vi: 'Điều chỉnh rủi ro' })],
    ['collaboration', tr(language, { en: 'Collaboration', ja: 'コラボレーション', th: 'การทำงานร่วม', vi: 'Cộng tác' })],
    ['quality', tr(language, { en: 'Quality', ja: 'クオリティ', th: 'คุณภาพ', vi: 'Chất lượng' })]
  ] as const

  const metricValue = (agent: any) => {
    if (metric === 'risk') return Number(agent.risk_adjusted_score || 0).toFixed(2)
    if (metric === 'collaboration') return Number(agent.collaboration_score || 0).toFixed(0)
    if (metric === 'quality') return Number(agent.quality_score_avg || 0).toFixed(2)
    return formatReturnPercent(agent.total_profit_percent)
  }

  // ── Anonymous paper-follow ──────────────────────────────────────────
  // Stored entirely in localStorage; no backend, no email, no auth.
  // Lets a guest "follow" an agent and see their P&L delta since follow.
  type PaperFollow = { followed_at: string; snapshot_profit_pct: number }
  const PAPER_FOLLOW_KEY = 'sooppiy_paper_follows'
  const [equityCurves, setEquityCurves] = useState<Record<number, { t: string; v: number }[]>>({})

  useEffect(() => {
    if (profitHistory.length === 0) return
    const days = getLeaderboardDays(chartRange)
    profitHistory.forEach((agent: any) => {
      const id: number = agent.agent_id
      if (equityCurves[id]) return
      fetch(`${API_BASE}/agents/${id}/equity-curve?days=${days}`)
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (data?.curve?.length > 1) {
            setEquityCurves((prev) => ({ ...prev, [id]: data.curve }))
          }
        })
        .catch(() => {})
    })
  }, [profitHistory])

  const [paperFollows, setPaperFollows] = useState<Record<string, PaperFollow>>(() => {
    if (typeof window === 'undefined') return {}
    try {
      const raw = window.localStorage.getItem(PAPER_FOLLOW_KEY)
      return raw ? JSON.parse(raw) : {}
    } catch {
      return {}
    }
  })
  useEffect(() => {
    try { window.localStorage.setItem(PAPER_FOLLOW_KEY, JSON.stringify(paperFollows)) } catch {}
  }, [paperFollows])
  const togglePaperFollow = (agentId: number | string, currentProfitPct: number) => {
    setPaperFollows((prev) => {
      const key = String(agentId)
      if (prev[key]) {
        const { [key]: _removed, ...rest } = prev
        return rest
      }
      return {
        ...prev,
        [key]: { followed_at: new Date().toISOString(), snapshot_profit_pct: Number(currentProfitPct) || 0 },
      }
    })
  }

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{tr(language, { en: '🏆 Top Traders', ja: '🏆 トップトレーダー', th: '🏆 เทรดเดอร์อันดับต้น', vi: '🏆 Trader hàng đầu' })}</h1>

          <p className="header-subtitle">
            {tr(language, { en: 'Ranked by return rate (realized + unrealized PnL / capital base)', ja: 'リターン率でランク付け (実現+未実現損益 / 資本ベース)', th: 'จัดอันดับตามอัตราผลตอบแทน (กำไรขาดทุนรับรู้ + ยังไม่รับรู้ / เงินทุนตั้งต้น)', vi: 'Xếp hạng theo lợi suất (Lãi/Lỗ thực hiện + chưa thực hiện / vốn gốc)' })}
          </p>
        </div>
      </div>

      {!token && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ fontWeight: 600, marginBottom: '6px' }}>
            {tr(language, { en: 'Leaderboard Open to Guests', ja: 'ゲストにもリーダーボードを公開', th: 'อันดับเปิดให้ผู้เยี่ยมชม', vi: 'Bảng xếp hạng mở cho khách' })}
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
            {tr(language, { en: 'You can view profit curves and top trader performance without logging in. Login to trade, copy traders, and manage your account.', ja: 'ログインなしで利益曲線とトップトレーダーのパフォーマンスを閲覧できます。取引、コピー、アカウント管理にはログインしてください。', th: 'คุณสามารถดูเส้นกำไรและผลงานเทรดเดอร์อันดับต้นได้โดยไม่ต้องเข้าสู่ระบบ เข้าสู่ระบบเพื่อเทรด คัดลอก และจัดการบัญชี', vi: 'Bạn có thể xem đường lợi nhuận và hiệu suất trader hàng đầu mà không cần đăng nhập. Đăng nhập để giao dịch, sao chép và quản lý tài khoản.' })}
          </div>
        </div>
      )}

      {activeChallengeCount > 0 && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <span className="challenge-badge">{tr(language, { en: 'Challenge active', ja: 'チャレンジ進行中', th: 'ชาเลนจ์กำลังทำงาน', vi: 'Thử thách đang chạy' })}</span>
            <span style={{ marginLeft: '10px', color: 'var(--text-secondary)', fontSize: '14px' }}>
              {tr(language, { en: `${activeChallengeCount} challenge leaderboards are scoring`, ja: `${activeChallengeCount} 件のチャレンジリーダーボードが採点中`, th: `อันดับชาเลนจ์ ${activeChallengeCount} รายการกำลังให้คะแนน`, vi: `${activeChallengeCount} bảng xếp hạng thử thách đang chấm điểm` })}
            </span>
          </div>
          <button className="btn btn-ghost" onClick={() => navigate('/challenges')}>
            {tr(language, { en: 'Open challenges', ja: 'チャレンジを開く', th: 'เปิดชาเลนจ์', vi: 'Mở thử thách' })}
          </button>
        </div>
      )}

      <div className="leaderboard-metric-tabs">
        {metricOptions.map(([value, label]) => (
          <button
            key={value}
            className={metric === value ? 'active' : ''}
            onClick={() => {
              setMetric(value)
              setLeaderboardPage(1)
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Profit Chart */}
      {chartData.length > 0 && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '12px' }}>
            <h3 style={{ fontSize: '16px', margin: 0 }}>
              {tr(language, { en: 'Return Chart', ja: 'リターンチャート', th: 'กราฟผลตอบแทน', vi: 'Biểu đồ lợi suất' })}
            </h3>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => {
                  setChartRange('all')
                  setLeaderboardPage(1)
                }}
                style={{
                  padding: '4px 12px',
                  borderRadius: '4px',
                  border: 'none',
                  background: chartRange === 'all' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                  color: chartRange === 'all' ? '#fff' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '12px'
                }}
              >
                {tr(language, { en: 'All Data', ja: 'すべてのデータ', th: 'ข้อมูลทั้งหมด', vi: 'Tất cả dữ liệu' })}
              </button>
              <button
                onClick={() => {
                  setChartRange('24h')
                  setLeaderboardPage(1)
                }}
                style={{
                  padding: '4px 12px',
                  borderRadius: '4px',
                  border: 'none',
                  background: chartRange === '24h' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                  color: chartRange === '24h' ? '#fff' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '12px'
                }}
              >
                {tr(language, { en: '24 Hours', ja: '24時間', th: '24 ชั่วโมง', vi: '24 giờ' })}
              </button>
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '18px', alignItems: 'stretch' }}>
            <div style={{ flex: '1 1 620px', minWidth: 0, minHeight: 420, height: 420 }}>
              <ResponsiveContainer>
                <LineChart
                  data={chartData}
                  margin={{ top: 5, right: 20, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--bg-tertiary)" />
                  <XAxis dataKey="time" stroke="var(--text-secondary)" tick={{ fontSize: 10 }} minTickGap={24} />
                  <YAxis stroke="var(--text-secondary)" tick={{ fontSize: 12 }} tickFormatter={(value: any) => `${Number(value).toFixed(0)}%`} />
                  <Tooltip
                    content={<LeaderboardTooltip />}
                  />
                  {topChartAgents.map((agent: any, idx: number) => (
                    <Line
                      key={agent.agent_id}
                      type="monotone"
                      dataKey={agent.name}
                      stroke={LEADERBOARD_LINE_COLORS[idx % LEADERBOARD_LINE_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div style={{
              flex: '0 0 180px',
              minWidth: '170px',
              maxWidth: '190px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              maxHeight: '420px',
              overflowY: 'auto',
              padding: '10px',
              borderRadius: '16px',
              background: 'rgba(17, 25, 32, 0.56)',
              border: '1px solid var(--border-color)'
            }}>
              {topChartAgents.map((agent: any, idx: number) => {
                const rank = leaderboardOffset + idx + 1
                return (
                <button
                  key={agent.agent_id}
                  type="button"
                  onClick={() => handleAgentClick(agent)}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '24px 12px minmax(0, 1fr)',
                    alignItems: 'center',
                    gap: '8px',
                    width: '100%',
                    padding: '7px 8px',
                    borderRadius: '12px',
                    border: '1px solid transparent',
                    background: 'transparent',
                    color: 'var(--text-primary)',
                    cursor: 'pointer',
                    textAlign: 'left'
                  }}
                >
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'IBM Plex Mono, monospace', fontSize: '12px' }}>
                    #{rank}
                  </span>
                  <span style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '999px',
                    background: LEADERBOARD_LINE_COLORS[idx % LEADERBOARD_LINE_COLORS.length]
                  }}></span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '12px', fontWeight: 600 }}>
                    {agent.name}
                  </span>
                </button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Traders Cards */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">{tr(language, { en: '🏆 Traders', ja: '🏆 トレーダー', th: '🏆 เทรดเดอร์', vi: '🏆 Trader' })}</h3>
        </div>
        {profitHistory.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🏆</div>
            <div className="empty-title">{tr(language, { en: 'No data yet', ja: 'データはまだありません', th: 'ยังไม่มีข้อมูล', vi: 'Chưa có dữ liệu' })}</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
            {profitHistory.map((agent: any, idx: number) => {
              const rank = leaderboardOffset + idx + 1
              const podiumIndex = rank - 1
              return (
              <div
                key={agent.agent_id}
                onClick={() => handleAgentClick(agent)}
                style={{
                  padding: '20px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  border: rank <= 3 ? `2px solid ${['#FFD700', '#C0C0C0', '#CD7F32'][podiumIndex]}` : '1px solid var(--border-color)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
                  <div style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    background: rank <= 3 ? ['linear-gradient(135deg, #FFD700, #FFA500)', 'linear-gradient(135deg, #C0C0C0, #A0A0A0)', 'linear-gradient(135deg, #CD7F32, #8B4513)'][podiumIndex] : 'var(--accent-gradient)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 'bold',
                    fontSize: '18px',
                    color: rank <= 3 ? '#000' : '#fff'
                  }}>
                    {rank}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 600, fontSize: '16px' }}>{agent.name}</span>
                      {agent.backtest_validated_strategy && (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                          background: 'rgba(22, 163, 74, 0.12)',
                          color: 'var(--success)',
                          border: '1px solid rgba(22, 163, 74, 0.30)',
                          borderRadius: '999px',
                          padding: '2px 8px',
                          fontSize: '10px',
                          fontWeight: 600,
                          letterSpacing: '0.06em',
                          textTransform: 'uppercase',
                          fontFamily: 'var(--font-ui)',
                          flexShrink: 0,
                        }}>
                          ✓ {tr(language, { en: 'Validated', ja: '検証済', th: 'ผ่านการตรวจสอบ', vi: 'Đã xác thực' })}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {tr(language, { en: 'Last updated', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật lần cuối' })}: {agent.history ? agent.history[agent.history.length - 1]?.recorded_at?.split('T')[0] : '-'}
                    </div>
                  </div>
                </div>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                  gap: '14px 18px',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {tr(language, { en: 'Return', ja: 'リターン', th: 'ผลตอบแทน', vi: 'Lợi suất' })}
                    </div>
                    <div style={{
                      color: (agent.total_profit_percent || 0) >= 0 ? 'var(--success)' : 'var(--error)',
                      fontWeight: 700,
                      fontSize: '16px',
                    }}>
                      {formatReturnPercent(agent.total_profit_percent)}
                    </div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                      ${agent.total_profit?.toFixed(2) || '0.00'}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Sharpe
                    </div>
                    <div style={{
                      color: (agent.sharpe || 0) >= 1 ? 'var(--success)' : (agent.sharpe || 0) >= 0 ? 'var(--text-primary)' : 'var(--error)',
                      fontWeight: 700,
                      fontSize: '16px',
                    }}>
                      {Number(agent.sharpe || 0).toFixed(2)}
                    </div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                      n={agent.sample_size || 0}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {tr(language, { en: 'Max DD', ja: '最大DD', th: 'DD สูงสุด', vi: 'DD tối đa' })}
                    </div>
                    <div style={{
                      color: 'var(--error)',
                      fontWeight: 700,
                      fontSize: '16px',
                    }}>
                      {Number(agent.max_drawdown || 0).toFixed(2)}%
                    </div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {tr(language, { en: 'Trades', ja: '取引', th: 'การเทรด', vi: 'Giao dịch' })}
                    </div>
                    <div style={{ fontWeight: 700, fontSize: '16px' }}>
                      {agent.trade_count || 0}
                    </div>
                  </div>
                  {metric !== 'return' && (
                    <div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '10px', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: '4px' }}>
                        {metricOptions.find(([value]) => value === metric)?.[1]}
                      </div>
                      <div style={{ fontWeight: 700, fontSize: '16px' }}>
                        {metricValue(agent)}
                      </div>
                    </div>
                  )}
                </div>
                {/* Equity sparkline */}
                {equityCurves[agent.agent_id] && (
                  <div style={{ height: 40, marginTop: 12, marginBottom: -4 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={equityCurves[agent.agent_id]}>
                        <Line
                          type="monotone"
                          dataKey="v"
                          stroke={(agent.total_profit_percent || 0) >= 0 ? 'var(--success)' : 'var(--error)'}
                          dot={false}
                          strokeWidth={1.5}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
                {/* Anonymous paper-follow — collapses funnel from "land → email → KYC" to "land → tap follow". */}
                {(() => {
                  const follow = paperFollows[String(agent.agent_id)]
                  const currentPct = Number(agent.total_profit_percent || 0)
                  if (follow) {
                    const delta = currentPct - (follow.snapshot_profit_pct || 0)
                    const sign = delta >= 0 ? '▲' : '▼'
                    return (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '14px', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); togglePaperFollow(agent.agent_id, currentPct) }}
                          className="btn btn-ghost"
                          style={{ fontSize: '12px', padding: '6px 14px' }}
                        >
                          {tr(language, { en: '✓ Following', ja: '✓ フォロー中', th: '✓ กำลังติดตาม', vi: '✓ Đang theo dõi' })}
                        </button>
                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '12px',
                          color: delta >= 0 ? 'var(--success)' : 'var(--error)',
                          fontWeight: 600,
                        }}>
                          {tr(language, { en: 'since follow', ja: 'フォロー以降', th: 'ตั้งแต่ติดตาม', vi: 'từ khi theo dõi' })} {sign} {Math.abs(delta).toFixed(2)}%
                        </span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                          {follow.followed_at?.split('T')[0]}
                        </span>
                      </div>
                    )
                  }
                  return (
                    <div style={{ marginTop: '14px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); togglePaperFollow(agent.agent_id, currentPct) }}
                        className="btn btn-outline"
                        style={{ fontSize: '12px', padding: '6px 14px' }}
                        title={tr(language, {
                          en: 'No signup needed — paper-mode follow stored on this device',
                          ja: '登録不要 — ペーパーモードのフォローはこのデバイスに保存',
                          th: 'ไม่ต้องลงทะเบียน — ติดตามแบบเปเปอร์เก็บไว้ในอุปกรณ์นี้',
                          vi: 'Không cần đăng ký — theo dõi giả lập lưu trên thiết bị này',
                        })}
                      >
                        {tr(language, { en: 'Follow (paper)', ja: 'フォロー (ペーパー)', th: 'ติดตาม (เปเปอร์)', vi: 'Theo dõi (giả lập)' })}
                      </button>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); navigate(`/backtest?agent=${agent.agent_id}`) }}
                        className="btn btn-ghost"
                        style={{ fontSize: '12px', padding: '6px 14px' }}
                      >
                        ⏮ {tr(language, { en: 'Backtest', ja: 'バックテスト', th: 'แบ็คเทสต์', vi: 'Backtest' })}
                      </button>
                    </div>
                  )
                })()}
              </div>
              )
            })}
          </div>
        )}
        {leaderboardTotalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginTop: '20px', flexWrap: 'wrap' }}>
            <button
              className="btn btn-secondary"
              disabled={leaderboardPage <= 1}
              onClick={() => setLeaderboardPage((current) => Math.max(1, current - 1))}
            >
              {tr(language, { en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước' })}
            </button>
            <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
              {tr(language, { en: `Page ${leaderboardPage} / ${leaderboardTotalPages}, ${totalTraders} traders total`, ja: `ページ ${leaderboardPage} / ${leaderboardTotalPages}、合計 ${totalTraders} トレーダー`, th: `หน้า ${leaderboardPage} / ${leaderboardTotalPages}, รวม ${totalTraders} เทรดเดอร์`, vi: `Trang ${leaderboardPage} / ${leaderboardTotalPages}, tổng ${totalTraders} trader` })}
            </div>
            <button
              className="btn btn-secondary"
              disabled={leaderboardPage >= leaderboardTotalPages}
              onClick={() => setLeaderboardPage((current) => Math.min(leaderboardTotalPages, current + 1))}
            >
              {tr(language, { en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp' })}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default LeaderboardPage
