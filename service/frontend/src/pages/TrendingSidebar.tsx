import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { API_BASE, REFRESH_INTERVAL, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Find the visually first element that renders as a box (a .card, or any
// rounded container with a border/background). Scans a bounded depth of the
// page's DOM and picks the topmost match — depth in the tree says nothing
// about vertical position, so all candidates are compared by their top edge.
// Used to align the sidebar's top with the page's first content box.
function findFirstBox(root: HTMLElement): HTMLElement | null {
  let best: HTMLElement | null = null
  let bestTop = Infinity
  let level: HTMLElement[] = Array.from(root.children) as HTMLElement[]
  for (let depth = 0; depth < 6 && level.length > 0; depth++) {
    const next: HTMLElement[] = []
    for (const el of level) {
      if (el.offsetHeight < 40) continue
      let isBox = el.classList.contains('card')
      if (!isBox) {
        const s = getComputedStyle(el)
        isBox = parseFloat(s.borderRadius) >= 8
          && ((s.borderStyle !== 'none' && parseFloat(s.borderWidth) > 0)
            || (s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent'))
      }
      if (isBox) {
        // A box's children can't start above the box itself — don't descend.
        const top = el.getBoundingClientRect().top
        if (top < bestTop) { best = el; bestTop = top }
      } else {
        next.push(...(Array.from(el.children) as HTMLElement[]))
      }
    }
    level = next
  }
  return best
}

// Trending Sidebar - Shows most held symbols with current prices
export function TrendingSidebar() {
  const [trending, setTrending] = useState<any[]>([])
  const [agentCount, setAgentCount] = useState(0)
  const [topOffset, setTopOffset] = useState(0)
  const { language } = useLanguage()
  const navigate = useNavigate()
  const location = useLocation()
  const rootRef = useRef<HTMLDivElement>(null)

  // Keep the sidebar's first card top-aligned with the page's first content
  // box. Re-measure on route change and whenever the content column resizes
  // (async data loads, window resize).
  useEffect(() => {
    const el = rootRef.current
    const leftCol = el?.parentElement?.firstElementChild as HTMLElement | null
    if (!el || !leftCol || leftCol === el) return
    const measure = () => {
      // children[0] is the shared topbar row; children[1] is the routed page.
      const content = leftCol.children[1] as HTMLElement | undefined
      // Pages with no box (e.g. empty states) anchor to the content top.
      const anchor = (content ? findFirstBox(content) : null) ?? content
      setTopOffset(anchor
        ? Math.max(0, Math.round(anchor.getBoundingClientRect().top - leftCol.getBoundingClientRect().top))
        : 0)
    }
    // Coalesce re-measures; DOM mutations arrive in bursts while data loads.
    let timer: number | undefined
    const schedule = () => {
      if (timer !== undefined) return
      timer = window.setTimeout(() => { timer = undefined; measure() }, 50)
    }
    measure()
    // MutationObserver (not just ResizeObserver) because RO callbacks ride the
    // rendering pipeline and stall in hidden/background tabs, while page data
    // keeps loading; MO is delivered as a microtask regardless.
    const mo = new MutationObserver(schedule)
    mo.observe(leftCol, { childList: true, subtree: true })
    const ro = new ResizeObserver(schedule)
    ro.observe(leftCol)
    window.addEventListener('resize', schedule)
    document.fonts?.ready.then(schedule).catch(() => {})
    return () => {
      mo.disconnect()
      ro.disconnect()
      window.removeEventListener('resize', schedule)
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [location.pathname])

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
    if (market === 'us-stock') return tr(language, { ko: '미국', en: 'US', ja: 'US', th: 'US', vi: 'US' })
    if (market === 'crypto') return tr(language, { ko: '암호화폐', en: 'Crypto', ja: '暗号通貨', th: 'คริปโต', vi: 'Tiền mã hóa' })
    return market
  }

  return (
    // Outer wrapper stays in normal flow (stretched to the row height) so the
    // spacer can push the sticky block down to the page's first box without a
    // margin — a top margin on a sticky element breaks its pinning range.
    <div ref={rootRef} className="trending-rail" style={{ width: '280px', flexShrink: 0 }}>
      <div style={{ height: topOffset }} />
      <div style={{ position: 'sticky', top: '24px' }}>
      {/* Agent Count */}
      <div
        className="card"
        onClick={() => navigate('/leaderboard')}
        style={{ padding: '16px', marginBottom: '16px', cursor: 'pointer' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {tr(language, { ko: '등록 트레이더', en: 'Registered Traders', ja: '登録トレーダー', th: 'เทรดเดอร์ที่ลงทะเบียน', vi: 'Trader đã đăng ký' })}
          </span>
          <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-primary)' }}>
            {agentCount}
          </span>
        </div>
      </div>

      <div className="card" style={{ padding: '16px' }}>
        <h3 style={{ fontSize: '14px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          🔥 {tr(language, { ko: '인기', en: 'Trending', ja: 'トレンド', th: 'มาแรง', vi: 'Xu hướng' })}
        </h3>

        {trending.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', padding: '20px 0' }}>
            {tr(language, { ko: '데이터 없음', en: 'No data', ja: 'データなし', th: 'ไม่มีข้อมูล', vi: 'Không có dữ liệu' })}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {trending.map((item, idx) => (
              <div
                key={`${item.symbol}-${item.market}`}
                onClick={() => navigate('/market')}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 10px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: '8px',
                  fontSize: '13px',
                  cursor: 'pointer'
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
    </div>
  )
}

export default TrendingSidebar
