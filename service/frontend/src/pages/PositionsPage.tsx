import { useState, useEffect } from 'react'
import { API_BASE, REFRESH_INTERVAL, getInstrumentLabel, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Positions Page
export function PositionsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [positions, setPositions] = useState<any[]>([])
  const [cash, setCash] = useState<number>(100000)
  const [loading, setLoading] = useState(true)
  const { t, language } = useLanguage()

  useEffect(() => {
    if (token) loadPositions()
    else setLoading(false)

    // Refresh positions periodically
    const interval = setInterval(() => {
      if (token) loadPositions()
    }, REFRESH_INTERVAL)

    return () => clearInterval(interval)
  }, [token])

  const loadPositions = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/positions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      const data = await res.json()
      setPositions(data.positions || [])
      setCash(data.cash || 100000)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  if (!token) {
    return (
      <div>
        <div className="header">
          <div>
            <h1 className="header-title">{t.positions.title}</h1>
          </div>
        </div>
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <div className="empty-title">{t.errors.pleaseLogin}</div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.positions.title}</h1>
          <p className="header-subtitle">{tr(language, { en: 'View your positions and copied positions', ja: '自分のポジションとコピーしたポジションを表示', th: 'ดูตำแหน่งของคุณและตำแหน่งที่คัดลอก', vi: 'Xem vị thế của bạn và vị thế đã sao chép' })}</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            {tr(language, { en: 'Available Cash', ja: '利用可能な現金', th: 'เงินสดที่ใช้ได้', vi: 'Tiền khả dụng' })}
          </div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--accent-primary)' }}>
            ${cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : positions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <div className="empty-title">{t.positions.noPositions}</div>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>{tr(language, { en: 'Symbol', ja: '銘柄', th: 'สัญลักษณ์', vi: 'Mã' })}</th>
                  <th>{tr(language, { en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'SL' })}</th>
                  <th>{tr(language, { en: 'Entry Price/Time', ja: 'エントリー価格/時間', th: 'ราคา/เวลาเข้า', vi: 'Giá/Thời gian vào' })}</th>
                  <th>{tr(language, { en: 'Current Price', ja: '現在価格', th: 'ราคาปัจจุบัน', vi: 'Giá hiện tại' })}</th>
                  <th>{tr(language, { en: 'P&L', ja: '損益', th: 'กำไรขาดทุน', vi: 'Lãi/Lỗ' })}</th>
                  <th>{tr(language, { en: 'Source', ja: 'ソース', th: 'แหล่งที่มา', vi: 'Nguồn' })}</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{getInstrumentLabel(pos)}</td>
                    <td>{Math.abs(pos.quantity)}</td>
                    <td>
                      <div>{tr(language, { en: 'Entry Price', ja: 'エントリー価格', th: 'ราคาเข้า', vi: 'Giá vào' })}: ${pos.entry_price?.toLocaleString()}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {tr(language, { en: 'Entry Time', ja: 'エントリー時間', th: 'เวลาเข้า', vi: 'Thời gian vào' })}: {pos.opened_at ? new Date(pos.opened_at).toLocaleString() : '-'}
                      </div>
                    </td>
                    <td>
                      {tr(language, { en: 'Current Price', ja: '現在価格', th: 'ราคาปัจจุบัน', vi: 'Giá hiện tại' })}: ${pos.current_price?.toLocaleString() || '-'}
                    </td>
                    <td style={{ color: pos.pnl >= 0 ? 'var(--success)' : 'var(--error)' }}>
                      {pos.pnl >= 0 ? '+' : ''}{pos.pnl}
                    </td>
                    <td>
                      <span className={`tag ${pos.source === 'self' ? '' : 'signal-side long'}`}>
                        {pos.source === 'self' ? (tr(language, { en: 'Self', ja: '自分', th: 'ตนเอง', vi: 'Tự' })) : (tr(language, { en: 'Copied', ja: 'コピー済み', th: 'คัดลอกแล้ว', vi: 'Đã sao chép' }))}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default PositionsPage
