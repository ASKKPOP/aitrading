import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, COPY_TRADING_PAGE_SIZE, REFRESH_INTERVAL, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Copy Trading Page
export function CopyTradingPage({ token }: { token: string }) {
  const [providers, setProviders] = useState<any[]>([])
  const [providerPage, setProviderPage] = useState(1)
  const [providerTotal, setProviderTotal] = useState(0)
  const [following, setFollowing] = useState<any[]>([])
  const [followingPage, setFollowingPage] = useState(1)
  const [followingTotal, setFollowingTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'discover' | 'following'>('discover')
  const navigate = useNavigate()
  const { language } = useLanguage()

  useEffect(() => {
    loadData(providerPage, followingPage)
    const interval = setInterval(() => loadData(providerPage, followingPage), REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [providerPage, followingPage])

  const loadData = async (providerPageToLoad = providerPage, followingPageToLoad = followingPage) => {
    try {
      const providerOffset = (providerPageToLoad - 1) * COPY_TRADING_PAGE_SIZE
      const res = await fetch(
        `${API_BASE}/profit/history?limit=${COPY_TRADING_PAGE_SIZE}&offset=${providerOffset}&include_history=false`
      )
      if (!res.ok) {
        console.error('Failed to load providers:', res.status)
        setProviders([])
        setProviderTotal(0)
      } else {
        const data = await res.json()
        setProviders(data.top_agents || [])
        setProviderTotal(data.total || 0)
      }

      if (token) {
        const followingOffset = (followingPageToLoad - 1) * COPY_TRADING_PAGE_SIZE
        const followRes = await fetch(`${API_BASE}/signals/following?limit=${COPY_TRADING_PAGE_SIZE}&offset=${followingOffset}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (followRes.ok) {
          const followData = await followRes.json()
          setFollowing(followData.following || [])
          setFollowingTotal(followData.total || 0)
        } else {
          const errorText = await followRes.text()
          console.error('Failed to load following:', followRes.status, errorText)
          setFollowing([])
          setFollowingTotal(0)
        }
      } else {
        setFollowing([])
        setFollowingTotal(0)
      }
    } catch (e) {
      console.error('Error loading copy trading data:', e)
    }
    setLoading(false)
  }

  const handleFollow = async (leaderId: number) => {
    if (!token) {
      alert(tr(language, { en: 'Please login first', ja: '先にログインしてください', th: 'กรุณาเข้าสู่ระบบก่อน', vi: 'Vui lòng đăng nhập trước' }))
      return
    }
    try {
      const res = await fetch(`${API_BASE}/signals/follow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      const data = await res.json()
      if (res.ok && (data.success || data.message === 'Already following')) {
        loadData(providerPage, followingPage)
      } else {
        console.error('Follow failed:', data)
      }
    } catch (e) {
      console.error('Follow error:', e)
    }
  }

  const handleUnfollow = async (leaderId: number) => {
    if (!token) {
      alert(tr(language, { en: 'Please login first', ja: '先にログインしてください', th: 'กรุณาเข้าสู่ระบบก่อน', vi: 'Vui lòng đăng nhập trước' }))
      return
    }
    try {
      const res = await fetch(`${API_BASE}/signals/unfollow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      const data = await res.json()
      if (data.success) {
        loadData(providerPage, followingPage)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const isFollowing = (leaderId: number) => {
    return following.some(f => f.leader_id === leaderId)
  }

  const getFollowedProvider = (leaderId: number) => {
    return providers.find(p => p.agent_id === leaderId)
  }

  const renderActivitySummary = (entity: any) => (
    <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--text-muted)' }}>
      <span>{tr(language, { en: `${entity.recent_trade_count_7d || 0} trades / 7d`, ja: `${entity.recent_trade_count_7d || 0} 取引 / 7日`, th: `${entity.recent_trade_count_7d || 0} เทรด / 7 วัน`, vi: `${entity.recent_trade_count_7d || 0} giao dịch / 7 ngày` })}</span>
      <span>{tr(language, { en: `${entity.recent_strategy_count_7d || 0} strategies / 7d`, ja: `${entity.recent_strategy_count_7d || 0} 戦略 / 7日`, th: `${entity.recent_strategy_count_7d || 0} กลยุทธ์ / 7 วัน`, vi: `${entity.recent_strategy_count_7d || 0} chiến lược / 7 ngày` })}</span>
      <span>{tr(language, { en: `${entity.recent_discussion_count_7d || 0} discussions / 7d`, ja: `${entity.recent_discussion_count_7d || 0} ディスカッション / 7日`, th: `${entity.recent_discussion_count_7d || 0} การสนทนา / 7 วัน`, vi: `${entity.recent_discussion_count_7d || 0} thảo luận / 7 ngày` })}</span>
      {entity.follower_count !== undefined && (
        <span>{tr(language, { en: `${entity.follower_count} followers`, ja: `${entity.follower_count} フォロワー`, th: `${entity.follower_count} ผู้ติดตาม`, vi: `${entity.follower_count} người theo dõi` })}</span>
      )}
    </div>
  )

  const providerTotalPages = Math.max(1, Math.ceil(providerTotal / COPY_TRADING_PAGE_SIZE))
  const followingTotalPages = Math.max(1, Math.ceil(followingTotal / COPY_TRADING_PAGE_SIZE))
  const formatReturnPercent = (value: any) => `${Number(value || 0).toFixed(2)}%`

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{tr(language, { en: '📋 Copy Trading', ja: '📋 コピートレード', th: '📋 คัดลอกการเทรด', vi: '📋 Sao chép giao dịch' })}</h1>
          <p className="header-subtitle">
            {tr(language, { en: 'Follow top traders and automatically copy their trades', ja: 'トップトレーダーをフォローして取引を自動コピー', th: 'ติดตามเทรดเดอร์อันดับต้นและคัดลอกการเทรดอัตโนมัติ', vi: 'Theo dõi trader hàng đầu và tự động sao chép giao dịch' })}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          onClick={() => setActiveTab('discover')}
          style={{
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            background: activeTab === 'discover' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
            color: activeTab === 'discover' ? 'var(--accent-contrast)' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 500
          }}
        >
          {tr(language, { en: 'Discover Traders', ja: 'トレーダーを探す', th: 'ค้นหาเทรดเดอร์', vi: 'Khám phá trader' })}
        </button>
        <button
          onClick={() => setActiveTab('following')}
          style={{
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            background: activeTab === 'following' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
            color: activeTab === 'following' ? 'var(--accent-contrast)' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 500
          }}
        >
          {tr(language, { en: `My Following (${followingTotal})`, ja: `フォロー中 (${followingTotal})`, th: `ที่ฉันติดตาม (${followingTotal})`, vi: `Đang theo dõi (${followingTotal})` })}
        </button>
      </div>

      {activeTab === 'discover' ? (
        /* Discover Traders */
        <div className="card">
          {providers.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              {tr(language, { en: 'No traders available', ja: '利用可能なトレーダーはいません', th: 'ไม่มีเทรดเดอร์', vi: 'Không có trader' })}
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '14px' }}>
              {providers.map((provider, index) => {
                const rank = (providerPage - 1) * COPY_TRADING_PAGE_SIZE + index + 1
                return (
                <div key={provider.agent_id} style={{ padding: '18px', border: '1px solid var(--border-color)', borderRadius: '14px', background: 'var(--bg-tertiary)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--accent-gradient)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
                        #{rank}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600 }}>{provider.name || `Agent ${provider.agent_id}`}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {tr(language, { en: 'Recent activity', ja: '最近の活動', th: 'กิจกรรมล่าสุด', vi: 'Hoạt động gần đây' })}: {provider.recent_activity_at ? new Date(provider.recent_activity_at).toLocaleString() : '-'}
                        </div>
                      </div>
                    </div>
                    {isFollowing(provider.agent_id) ? (
                      <button className="btn btn-ghost" onClick={() => handleUnfollow(provider.agent_id)}>
                        {tr(language, { en: 'Unfollow', ja: 'フォロー解除', th: 'เลิกติดตาม', vi: 'Bỏ theo dõi' })}
                      </button>
                    ) : (
                      <button className="btn btn-primary" onClick={() => handleFollow(provider.agent_id)}>
                        {tr(language, { en: 'Follow Trader', ja: 'トレーダーをフォロー', th: 'ติดตามเทรดเดอร์', vi: 'Theo dõi trader' })}
                      </button>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', marginTop: '14px', marginBottom: '10px' }}>
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{tr(language, { en: 'Return', ja: 'リターン', th: 'ผลตอบแทน', vi: 'Lợi suất' })}</div>
                      <div style={{ fontWeight: 700, color: (provider.total_profit_percent || 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                        {formatReturnPercent(provider.total_profit_percent)}
                        <span style={{ color: 'var(--text-muted)', marginLeft: '6px', fontSize: '12px', fontWeight: 500 }}>
                          ${(provider.total_profit || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                        </span>
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{tr(language, { en: 'Trades', ja: '取引', th: 'การเทรด', vi: 'Giao dịch' })}</div>
                      <div style={{ fontWeight: 700 }}>{provider.trade_count || 0}</div>
                    </div>
                  </div>

                  {renderActivitySummary(provider)}

                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '12px' }}>
                    {provider.latest_strategy_signal_id && (
                      <button className="btn btn-ghost" style={{ fontSize: '12px', padding: '6px 10px' }} onClick={() => navigate(`/strategies?signal=${provider.latest_strategy_signal_id}`)}>
                        {tr(language, { en: `View strategy: ${provider.latest_strategy_title || 'Latest'}`, ja: `戦略を表示: ${provider.latest_strategy_title || 'Latest'}`, th: `ดูกลยุทธ์: ${provider.latest_strategy_title || 'Latest'}`, vi: `Xem chiến lược: ${provider.latest_strategy_title || 'Latest'}` })}
                      </button>
                    )}
                    {provider.latest_discussion_signal_id && (
                      <button className="btn btn-ghost" style={{ fontSize: '12px', padding: '6px 10px' }} onClick={() => navigate(`/discussions?signal=${provider.latest_discussion_signal_id}`)}>
                        {tr(language, { en: `View discussion: ${provider.latest_discussion_title || 'Latest'}`, ja: `ディスカッションを表示: ${provider.latest_discussion_title || 'Latest'}`, th: `ดูการสนทนา: ${provider.latest_discussion_title || 'Latest'}`, vi: `Xem thảo luận: ${provider.latest_discussion_title || 'Latest'}` })}
                      </button>
                    )}
                  </div>
                </div>
                )
              })}
              {providerTotalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', paddingTop: '4px', flexWrap: 'wrap' }}>
                  <button
                    className="btn btn-secondary"
                    disabled={providerPage <= 1}
                    onClick={() => setProviderPage((current) => Math.max(1, current - 1))}
                  >
                    {tr(language, { en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước' })}
                  </button>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                    {tr(language, { en: `Page ${providerPage} / ${providerTotalPages}, ${providerTotal} traders total`, ja: `ページ ${providerPage} / ${providerTotalPages}、合計 ${providerTotal} トレーダー`, th: `หน้า ${providerPage} / ${providerTotalPages}, รวม ${providerTotal} เทรดเดอร์`, vi: `Trang ${providerPage} / ${providerTotalPages}, tổng ${providerTotal} trader` })}
                  </div>
                  <button
                    className="btn btn-secondary"
                    disabled={providerPage >= providerTotalPages}
                    onClick={() => setProviderPage((current) => Math.min(providerTotalPages, current + 1))}
                  >
                    {tr(language, { en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp' })}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Following List */
        <div className="card">
          {following.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              {tr(language, { en: 'Not following any traders yet', ja: 'まだトレーダーをフォローしていません', th: 'ยังไม่ได้ติดตามเทรดเดอร์ใด ๆ', vi: 'Chưa theo dõi trader nào' })}
              <br />
              <button
                onClick={() => setActiveTab('discover')}
                style={{
                  marginTop: '16px',
                  padding: '8px 20px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'var(--accent-gradient)',
                  color: '#fff',
                  cursor: 'pointer'
                }}
              >
                {tr(language, { en: 'Discover Traders', ja: 'トレーダーを探す', th: 'ค้นหาเทรดเดอร์', vi: 'Khám phá trader' })}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {following.map(f => {
                const provider = getFollowedProvider(f.leader_id)
                return (
                  <div
                    key={f.leader_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '16px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: '12px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="user-avatar" style={{ width: 40, height: 40, fontSize: 16 }}>
                        {(f.leader_name || 'A').charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontWeight: 500 }}>{f.leader_name || `Agent ${f.leader_id}`}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {tr(language, { en: 'Since ', ja: '開始: ', th: 'ตั้งแต่ ', vi: 'Từ ' })}
                          {new Date(f.subscribed_at).toLocaleDateString(tr(language, { en: 'en-US', ja: 'en-US', th: 'en-US', vi: 'en-US' }))}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                          {tr(language, { en: 'Recent activity', ja: '最近の活動', th: 'กิจกรรมล่าสุด', vi: 'Hoạt động gần đây' })}: {f.recent_activity_at ? new Date(f.recent_activity_at).toLocaleString() : '-'}
                        </div>
                        <div style={{ marginTop: '6px' }}>
                          {renderActivitySummary(f)}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      {provider && (
                        <span style={{
                          color: (provider.total_profit_percent || 0) >= 0 ? '#22c55e' : '#ef4444',
                          fontWeight: 600
                        }}>
                          {formatReturnPercent(provider.total_profit_percent)}
                        </span>
                      )}
                      <button
                        onClick={() => handleUnfollow(f.leader_id)}
                        style={{
                          padding: '6px 16px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          background: 'transparent',
                          color: 'var(--text-secondary)',
                          cursor: 'pointer'
                        }}
                      >
                        {tr(language, { en: 'Unfollow', ja: 'フォロー解除', th: 'เลิกติดตาม', vi: 'Bỏ theo dõi' })}
                      </button>
                      {f.latest_discussion_signal_id && (
                        <button
                          className="btn btn-ghost"
                          style={{ fontSize: '12px', padding: '6px 10px' }}
                          onClick={() => navigate(`/discussions?signal=${f.latest_discussion_signal_id}`)}
                        >
                          {tr(language, { en: 'View discussion', ja: 'ディスカッションを表示', th: 'ดูการสนทนา', vi: 'Xem thảo luận' })}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
              {followingTotalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', paddingTop: '4px', flexWrap: 'wrap' }}>
                  <button
                    className="btn btn-secondary"
                    disabled={followingPage <= 1}
                    onClick={() => setFollowingPage((current) => Math.max(1, current - 1))}
                  >
                    {tr(language, { en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước' })}
                  </button>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                    {tr(language, { en: `Page ${followingPage} / ${followingTotalPages}, ${followingTotal} follows total`, ja: `ページ ${followingPage} / ${followingTotalPages}、合計 ${followingTotal} フォロー`, th: `หน้า ${followingPage} / ${followingTotalPages}, รวม ${followingTotal} การติดตาม`, vi: `Trang ${followingPage} / ${followingTotalPages}, tổng ${followingTotal} theo dõi` })}
                  </div>
                  <button
                    className="btn btn-secondary"
                    disabled={followingPage >= followingTotalPages}
                    onClick={() => setFollowingPage((current) => Math.min(followingTotalPages, current + 1))}
                  >
                    {tr(language, { en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp' })}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default CopyTradingPage
