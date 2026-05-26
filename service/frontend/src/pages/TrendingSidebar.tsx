import { useState, useEffect } from 'react'
import { API_BASE, REFRESH_INTERVAL, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Trending Sidebar - Shows most held symbols with current prices
export function TrendingSidebar() {
  const [trending, setTrending] = useState<any[]>([])
  const [agentCount, setAgentCount] = useState(0)
  const { language } = useLanguage()

  useEffect(() => {
    loadTrending()
    loadAgentCount()
    const interval = setInterval(() => {
      loadTrending()
      loadAgentCount()
    }, REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [])

  const loadAgentCount = async () => {
    try {
      const res = await fetch(`${API_BASE}/claw/agents/count`)
      if (!res.ok) return
      const data = await res.json()
      setAgentCount(data.count || 0)
    } catch (e) {
      console.error('Error loading agent count:', e)
    }
  }

  const loadTrending = async () => {
    try {
      const res = await fetch(`${API_BASE}/trending?limit=10`)
      if (!res.ok) {
        console.error('Failed to load trending:', res.status)
        return
      }
      const data = await res.json()
      setTrending(data.trending || [])
    } catch (e) {
      console.error('Error loading trending:', e)
    }
  }

  const getMarketLabel = (market: string) => {
    if (market === 'us-stock') return tr(language, { en: 'US', ja: 'US', th: 'US', vi: 'US' })
    if (market === 'crypto') return tr(language, { en: 'Crypto', ja: '暗号通貨', th: 'คริปโต', vi: 'Tiền mã hóa' })
    return market
  }

  return (
    <div style={{
      width: '280px',
      flexShrink: 0,
      position: 'sticky',
      top: '24px',
      alignSelf: 'flex-start'
    }}>
      {/* Agent Count */}
      <div className="card" style={{ padding: '16px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {tr(language, { en: 'Online Traders', ja: 'オンラインのトレーダー', th: 'เทรดเดอร์ออนไลน์', vi: 'Trader trực tuyến' })}
          </span>
          <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-primary)' }}>
            {agentCount}
          </span>
        </div>
      </div>

      <div className="card" style={{ padding: '16px' }}>
        <h3 style={{ fontSize: '14px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          🔥 {tr(language, { en: 'Trending', ja: 'トレンド', th: 'มาแรง', vi: 'Xu hướng' })}
        </h3>

        {trending.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', padding: '20px 0' }}>
            {tr(language, { en: 'No data', ja: 'データなし', th: 'ไม่มีข้อมูล', vi: 'Không có dữ liệu' })}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {trending.map((item, idx) => (
              <div
                key={`${item.symbol}-${item.market}`}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 10px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: '8px',
                  fontSize: '13px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', width: '16px' }}>#{idx + 1}</span>
                  <span style={{ fontWeight: 600 }}>{item.symbol}</span>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    background: item.market === 'crypto' ? 'var(--accent-secondary)' : 'var(--accent-primary)',
                    borderRadius: '4px',
                    color: '#fff'
                  }}>
                    {getMarketLabel(item.market)}
                  </span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    ${item.current_price?.toFixed(2) || '-'}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    👥 {item.holder_count}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default TrendingSidebar
