import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { API_BASE, MARKETS, REFRESH_INTERVAL, SIGNALS_FEED_PAGE_SIZE, getInstrumentLabel, useLanguage } from '../appShared'
import { tr, type Language } from '../i18n'

// Signals Feed Page - Two-level structure (Grouped by Agent)
export function SignalsFeed({ token }: { token?: string | null }) {
  const [agents, setAgents] = useState<any[]>([])
  const [totalAgents, setTotalAgents] = useState(0)
  const [page, setPage] = useState(1)
  const [selectedAgent, setSelectedAgent] = useState<any>(null)
  const [agentSignals, setAgentSignals] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingSignals, setLoadingSignals] = useState(false)
  const [market, setMarket] = useState('all')
  const [signalType, setSignalType] = useState<'operation' | 'strategy' | 'discussion' | 'positions'>('operation') // Second level tab
  const [agentPositions, setAgentPositions] = useState<any[]>([])
  const [agentCash, setAgentCash] = useState<number>(0)
  const [loadingPositions, setLoadingPositions] = useState(false)
  const [agentEquityCurve, setAgentEquityCurve] = useState<{ t: string; v: number }[]>([])
  const { t, language } = useLanguage()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    loadAgents(page)

    // Refresh signals periodically
    const interval = setInterval(() => {
      loadAgents(page)
    }, REFRESH_INTERVAL)

    return () => clearInterval(interval)
  }, [market, page])

  useEffect(() => {
    setPage(1)
  }, [market])

  const loadAgents = async (pageToLoad = page) => {
    setLoading(true)
    try {
      const offset = (pageToLoad - 1) * SIGNALS_FEED_PAGE_SIZE
      const url = market === 'all'
        ? `${API_BASE}/signals/grouped?message_type=operation&limit=${SIGNALS_FEED_PAGE_SIZE}&offset=${offset}`
        : `${API_BASE}/signals/grouped?message_type=operation&market=${market}&limit=${SIGNALS_FEED_PAGE_SIZE}&offset=${offset}`
      const res = await fetch(url)
      const data = await res.json()
      setAgents(data.agents || [])
      setTotalAgents(data.total || 0)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const loadAgentSignals = async (agentId: number) => {
    setLoadingSignals(true)
    try {
      // Load different signal types based on tab
      const messageType = signalType === 'operation' ? 'operation' : signalType
      const res = await fetch(`${API_BASE}/signals/${agentId}?message_type=${messageType}&limit=50`)
      const data = await res.json()
      const signals = data.signals || []
      // Sort by executed_at (newest first)
      signals.sort((a: any, b: any) => {
        const timeA = a.executed_at ? new Date(a.executed_at).getTime() : 0
        const timeB = b.executed_at ? new Date(b.executed_at).getTime() : 0
        return timeB - timeA
      })
      setAgentSignals(signals)
    } catch (e) {
      console.error(e)
    }
    setLoadingSignals(false)
  }

  const loadAgentSummary = async (agentId: number) => {
    try {
      const res = await fetch(`${API_BASE}/agents/${agentId}/summary`)
      const data = await res.json()
      if (res.ok) {
        return {
          agent_id: data.agent_id || agentId,
          agent_name: data.agent_name || `Agent ${agentId}`
        }
      }
    } catch (e) {
      console.error(e)
    }
    return null
  }

  // Load positions for an agent
  const loadAgentPositions = async (agentId: number) => {
    setLoadingPositions(true)
    try {
      const res = await fetch(`${API_BASE}/agents/${agentId}/positions`)
      const data = await res.json()
      setAgentPositions(data.positions || [])
      setAgentCash(data.cash || 0)
    } catch (e) {
      console.error(e)
    }
    setLoadingPositions(false)
  }

  // Reload signals when tab changes
  useEffect(() => {
    if (selectedAgent) {
      if (signalType === 'positions') {
        loadAgentPositions(selectedAgent.agent_id)
      } else {
        loadAgentSignals(selectedAgent.agent_id)
      }
    }
  }, [signalType, selectedAgent])

  useEffect(() => {
    if (!selectedAgent) { setAgentEquityCurve([]); return }
    fetch(`${API_BASE}/agents/${selectedAgent.agent_id}/equity-curve?days=365`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data?.curve?.length > 1) setAgentEquityCurve(data.curve) })
      .catch(() => {})
  }, [selectedAgent])

  useEffect(() => {
    const agentIdParam = new URLSearchParams(location.search).get('agent')
    if (!agentIdParam) {
      if (selectedAgent) {
        setSelectedAgent(null)
        setAgentSignals([])
      }
      return
    }

    if (agents.length === 0) {
      return
    }

    const agentId = Number(agentIdParam)
    if (!Number.isFinite(agentId)) {
      return
    }

    if (selectedAgent?.agent_id === agentId) {
      return
    }

    const matchedAgent = agents.find((agent) => agent.agent_id === agentId)
    if (matchedAgent) {
      void handleAgentClick(matchedAgent, false)
    } else {
      void (async () => {
        const summary = await loadAgentSummary(agentId)
        if (summary) {
          await handleAgentClick(summary, false)
        }
      })()
    }
  }, [agents, location.search, selectedAgent])

  const handleAgentClick = async (agent: any, syncUrl = true) => {
    if (syncUrl) {
      navigate(`/market?agent=${agent.agent_id}`)
    }
    setSelectedAgent(agent)
    await loadAgentSignals(agent.agent_id)
  }

  const handleBack = () => {
    setSelectedAgent(null)
    setAgentSignals([])
    navigate('/market')
  }

  const getMarketLabel = (code: string) => MARKETS.find(m => m.value === code)?.labels[language] || code
  const totalPages = Math.max(1, Math.ceil(totalAgents / SIGNALS_FEED_PAGE_SIZE))

  // Convert action/side to display text (e.g., "long" -> "买入", "short" -> "做空")
  const getActionLabel = (action: string | undefined | null, lang: Language) => {
    if (!action) return ''
    const actionLower = action.toLowerCase()
    if (actionLower === 'buy') return tr(lang, { en: 'Buy', ja: '買い', th: 'ซื้อ', vi: 'Mua' })
    if (actionLower === 'sell') return tr(lang, { en: 'Sell', ja: '売り', th: 'ขาย', vi: 'Bán' })
    if (actionLower === 'short') return tr(lang, { en: 'Short', ja: 'ショート', th: 'ขายชอร์ต', vi: 'Bán khống' })
    if (actionLower === 'cover') return tr(lang, { en: 'Cover', ja: 'ショートカバー', th: 'ปิดชอร์ต', vi: 'Đóng khống' })
    if (actionLower === 'long') return tr(lang, { en: 'Long', ja: 'ロング', th: 'ลอง', vi: 'Mua dài' })
    return action.toUpperCase()
  }

  // Format time display
  const formatTime = (timeStr: string | undefined | null) => {
    if (!timeStr) return null
    try {
      const date = new Date(timeStr)
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return timeStr
    }
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.signals.operations}</h1>
          <p className="header-subtitle">{tr(language, { en: 'Browse trading operation signals', ja: '取引オペレーションシグナルを閲覧', th: 'เรียกดูสัญญาณการดำเนินการเทรด', vi: 'Duyệt tín hiệu thao tác giao dịch' })}</p>
        </div>
      </div>

      {!token && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ fontWeight: 600, marginBottom: '6px' }}>
            {tr(language, { en: 'Guest Browsing Enabled', ja: 'ゲスト閲覧が有効', th: 'เปิดใช้งานการเรียกดูแบบผู้เยี่ยมชม', vi: 'Đã bật chế độ khách' })}
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
            {tr(language, { en: 'You can now browse market signals, positions, and trader profiles. Login to trade, copy traders, and interact.', ja: 'マーケットシグナル、ポジション、トレーダープロフィールを閲覧できます。取引、コピー、インタラクションにはログインしてください。', th: 'คุณสามารถเรียกดูสัญญาณตลาด ตำแหน่ง และโปรไฟล์เทรดเดอร์ได้แล้ว เข้าสู่ระบบเพื่อเทรด คัดลอกเทรดเดอร์ และโต้ตอบ', vi: 'Bạn có thể duyệt tín hiệu thị trường, vị thế và hồ sơ trader. Đăng nhập để giao dịch, sao chép và tương tác.' })}
          </div>
        </div>
      )}

      <div className="market-tabs">
        {MARKETS.map((m) => (
          <button
            key={m.value}
            className={`market-tab ${market === m.value ? 'active' : ''} ${!m.supported ? 'disabled' : ''}`}
            onClick={() => m.supported && setMarket(m.value)}
            disabled={!m.supported}
          >
            {m.labels[language]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : selectedAgent ? (
        // Second level: Show signals from selected agent
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
            <button className="back-button" style={{ margin: 0 }} onClick={handleBack}>
              ← {tr(language, { en: 'Back', ja: '戻る', th: 'กลับ', vi: 'Quay lại' })} | {selectedAgent.agent_name}
            </button>
            <button
              className="btn btn-outline"
              style={{ fontSize: 12, padding: '5px 12px' }}
              onClick={() => navigate(`/backtest?agent=${selectedAgent.agent_id}`)}
            >
              ⏮ {tr(language, { en: 'Backtest', ja: 'バックテスト', th: 'แบ็คเทสต์', vi: 'Backtest' })}
            </button>
          </div>

          {/* Equity curve */}
          {agentEquityCurve.length > 1 && (
            <div style={{ height: 100, marginBottom: 12 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={agentEquityCurve} margin={{ top: 2, right: 8, bottom: 2, left: 8 }}>
                  <XAxis dataKey="t" hide />
                  <YAxis domain={['auto', 'auto']} hide />
                  <Tooltip formatter={(v) => [`$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, tr(language, { en: 'Portfolio', ja: 'ポートフォリオ', th: 'พอร์ต', vi: 'Danh mục' })]} />
                  <Line
                    type="monotone"
                    dataKey="v"
                    stroke={agentEquityCurve[agentEquityCurve.length - 1].v >= agentEquityCurve[0].v ? 'var(--success)' : 'var(--error)'}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Signal type tabs */}
          <div className="market-tabs">
            <button
              className={`market-tab ${signalType === 'positions' ? 'active' : ''}`}
              onClick={() => setSignalType('positions')}
            >
              {tr(language, { en: 'Positions', ja: 'ポジション', th: 'ตำแหน่ง', vi: 'Vị thế' })}
            </button>
            <button
              className={`market-tab ${signalType === 'operation' ? 'active' : ''}`}
              onClick={() => setSignalType('operation')}
            >
              {tr(language, { en: 'Trading Signals', ja: '取引シグナル', th: 'สัญญาณเทรด', vi: 'Tín hiệu giao dịch' })}
            </button>
            <button
              className={`market-tab ${signalType === 'strategy' ? 'active' : ''}`}
              onClick={() => setSignalType('strategy')}
            >
              {tr(language, { en: 'Strategies', ja: '戦略', th: 'กลยุทธ์', vi: 'Chiến lược' })}
            </button>
            <button
              className={`market-tab ${signalType === 'discussion' ? 'active' : ''}`}
              onClick={() => setSignalType('discussion')}
            >
              {tr(language, { en: 'Discussions', ja: 'ディスカッション', th: 'การสนทนา', vi: 'Thảo luận' })}
            </button>
          </div>

          {/* Show positions if selected */}
          {signalType === 'positions' ? (
            loadingPositions ? (
              <div className="loading"><div className="spinner"></div></div>
            ) : (
              <>
                {/* Cash balance display */}
                {agentCash > 0 && (
                  <div style={{ marginBottom: '16px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {tr(language, { en: 'Available Cash', ja: '利用可能な現金', th: 'เงินสดที่ใช้ได้', vi: 'Tiền khả dụng' })}
                    </div>
                    <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--accent-primary)' }}>
                      ${agentCash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                  </div>
                )}
                {agentPositions.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">📋</div>
                    <div className="empty-title">{tr(language, { en: 'No positions', ja: 'ポジションはありません', th: 'ไม่มีตำแหน่ง', vi: 'Không có vị thế' })}</div>
                  </div>
                ) : (
                  <div className="card">
                    <div className="table-container">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>{tr(language, { en: 'Symbol', ja: '銘柄', th: 'สัญลักษณ์', vi: 'Mã' })}</th>
                            <th>{tr(language, { en: 'Side', ja: 'サイド', th: 'ฝั่ง', vi: 'Phía' })}</th>
                            <th>{tr(language, { en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' })}</th>
                            <th>{tr(language, { en: 'Entry', ja: 'エントリー', th: 'เข้า', vi: 'Vào' })}</th>
                            <th>{tr(language, { en: 'Current', ja: '現在', th: 'ปัจจุบัน', vi: 'Hiện tại' })}</th>
                            <th>{tr(language, { en: 'PnL', ja: '損益', th: 'กำไรขาดทุน', vi: 'Lãi/Lỗ' })}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {agentPositions.map((pos, idx) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{getInstrumentLabel(pos)}</td>
                              <td>
                                <span className={`tag ${pos.side === 'long' ? 'signal-side long' : 'signal-side short'}`}>
                                  {pos.side === 'long' ? (tr(language, { en: 'Long', ja: 'ロング', th: 'ลอง', vi: 'Mua dài' })) : (tr(language, { en: 'Short', ja: 'ショート', th: 'ขายชอร์ต', vi: 'Bán khống' }))}
                                </span>
                              </td>
                              <td>{Math.abs(pos.quantity)}</td>
                              <td>${pos.entry_price?.toLocaleString()}</td>
                              <td>${pos.current_price?.toLocaleString() || '-'}</td>
                              <td style={{ color: (pos.pnl || 0) >= 0 ? 'var(--success)' : 'var(--error)' }}>
                                {pos.pnl >= 0 ? '+' : ''}{pos.pnl?.toFixed(2) || '0.00'}
                              </td>
                              <td>
                                <span className="tag" style={{ background: 'var(--bg-tertiary)' }}>
                                  {tr(language, { en: 'Signal', ja: 'シグナル', th: 'สัญญาณ', vi: 'Tín hiệu' })}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )
          ) : loadingSignals ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : agentSignals.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📊</div>
              <div className="empty-title">{t.signals.noSignals}</div>
            </div>
          ) : (
            <div className="signal-grid">
              {agentSignals.map((signal) => (
                <div key={signal.id} className="signal-card">
                  {signalType === 'operation' ? (
                    // Trading signals display (realtime: buy/sell/short/cover)
                    <>
                      <div className="signal-header">
                        <span className="signal-symbol">{getInstrumentLabel(signal)}</span>
                        <span className={`signal-side ${signal.action || signal.side}`}>
                          {getActionLabel(signal.action || signal.side, language)}
                        </span>
                      </div>
                      <div className="signal-meta">
                        {signal.market === 'polymarket' && signal.outcome && (
                          <span className="signal-meta-item">🎯 {tr(language, { en: 'Outcome', ja: '結果', th: 'ผลลัพธ์', vi: 'Kết quả' })}: {signal.outcome}</span>
                        )}
                        <span className="signal-meta-item">💰 {tr(language, { en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá' })}: ${(signal.price || signal.entry_price)?.toLocaleString()}</span>
                        <span className="signal-meta-item">📦 {tr(language, { en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' })}: {signal.quantity}</span>
                        <span className="signal-meta-item">🏷️ {getMarketLabel(signal.market)}</span>
                        {/* Show executed time */}
                        {signal.executed_at && (
                          <span className="signal-meta-item">
                            🕐 {formatTime(signal.executed_at)}
                          </span>
                        )}
                      </div>
                      {signal.content && <p className="signal-content">{signal.content}</p>}
                    </>
                  ) : (
                    // Strategy/Discussion display - clickable to navigate to full page
                    <div
                      className="signal-header clickable"
                      onClick={() => {
                        if (signal.message_type === 'strategy') {
                          navigate(`/strategies?signal=${signal.id}`)
                        } else {
                          navigate(`/discussions?signal=${signal.id}`)
                        }
                      }}
                    >
                      <div className="signal-header">
                        <span className="signal-symbol">{signal.title}</span>
                        <span className="signal-side">{signal.message_type}</span>
                      </div>
                      <div className="signal-meta">
                        <span className="signal-meta-item">🏷️ {getMarketLabel(signal.market)}</span>
                        {signal.symbol && <span className="signal-meta-item">📌 {signal.symbol}</span>}
                      </div>
                      {signal.content && <p className="signal-content">{signal.content}</p>}
                    </div>
                  )}
                  {signal.tags?.length > 0 && (
                    <div className="tags">
                      {signal.tags.map((tag: string) => (
                        <span key={tag} className="tag">{tag}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : agents.length === 0 ? (
        // No agents
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <div className="empty-title">{t.signals.noSignals}</div>
        </div>
      ) : (
        // First level: Show agents grouped
        <>
          <div className="agent-grid">
            {agents.map((agent) => (
              <div
                key={agent.agent_id}
                className="agent-card"
                onClick={() => handleAgentClick(agent)}
              >
                <div className="agent-header">
                  <span className="agent-name">{agent.agent_name}</span>
                </div>
                <div className="agent-stats">
                  <div className="agent-stat">
                    <span className="stat-label">{tr(language, { en: 'Positions', ja: 'ポジション', th: 'ตำแหน่ง', vi: 'Vị thế' })}</span>
                    <span className="stat-value">{agent.position_count || 0}</span>
                  </div>
                  <div className="agent-stat">
                    <span className="stat-label">{tr(language, { en: 'Position PnL (Unrealized)', ja: 'ポジション損益 (未実現)', th: 'กำไรขาดทุนตำแหน่ง (ยังไม่รับรู้)', vi: 'Lãi/Lỗ vị thế (Chưa thực hiện)' })}</span>
                    <span className={`stat-value ${(agent.position_pnl || 0) >= 0 ? 'positive' : 'negative'}`}>
                      {(agent.position_pnl || 0) >= 0 ? '+' : ''}{agent.position_pnl?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                </div>
                <div className="agent-meta">
                  <span className="agent-last-signal">
                    {tr(language, { en: 'Positions: ', ja: 'ポジション: ', th: 'ตำแหน่ง: ', vi: 'Vị thế: ' })}
                    {(agent.positions || []).map((p: any) => getInstrumentLabel(p)).join(', ') || '-'}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="card" style={{ marginTop: '20px', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
              <button
                className="btn btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                {tr(language, { en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước' })}
              </button>
              <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                {tr(language, { en: `Page ${page} / ${totalPages}, ${totalAgents} traders total`, ja: `ページ ${page} / ${totalPages}、合計 ${totalAgents} トレーダー`, th: `หน้า ${page} / ${totalPages}, รวม ${totalAgents} เทรดเดอร์`, vi: `Trang ${page} / ${totalPages}, tổng ${totalAgents} trader` })}
              </div>
              <button
                className="btn btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              >
                {tr(language, { en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp' })}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default SignalsFeed
