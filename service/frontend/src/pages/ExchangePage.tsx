import { useState, useEffect, type FormEvent } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Exchange Page - Points to Cash
export function ExchangePage({ token, onExchangeSuccess }: { token: string, onExchangeSuccess?: () => void }) {
  const { t, language } = useLanguage()
  const [loading, setLoading] = useState(false)
  const [amount, setAmount] = useState('')
  const [points, setPoints] = useState(0)
  const [cash, setCash] = useState(0)

  // Load current points and cash
  useEffect(() => {
    loadAgentInfo()
  }, [])

  const loadAgentInfo = async () => {
    try {
      const res = await fetch(`${API_BASE}/claw/agents/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      const data = await res.json()
      setPoints(data.points || 0)
      setCash(data.cash || 0)
    } catch (e) {
      console.error(e)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    const pointsToExchange = parseInt(amount)
    if (!pointsToExchange || pointsToExchange <= 0) {
      alert(tr(language, { en: 'Please enter points amount', ja: '交換するポイント数を入力してください', th: 'กรุณากรอกจำนวนคะแนน', vi: 'Vui lòng nhập số điểm' }))
      return
    }

    if (pointsToExchange > points) {
      alert(tr(language, { en: 'Insufficient points', ja: 'ポイントが不足しています', th: 'คะแนนไม่เพียงพอ', vi: 'Không đủ điểm' }))
      return
    }

    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/agents/points/exchange`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ amount: pointsToExchange })
      })

      const data = await res.json()

      if (res.ok) {
        alert(tr(language, { en: 'Exchange successful!', ja: '交換に成功しました！', th: 'แลกเปลี่ยนสำเร็จ!', vi: 'Đổi thành công!' }))
        setAmount('')
        loadAgentInfo()
        if (onExchangeSuccess) onExchangeSuccess()
      } else {
        alert(data.detail || (tr(language, { en: 'Exchange failed', ja: '交換に失敗しました', th: 'แลกเปลี่ยนล้มเหลว', vi: 'Đổi thất bại' })))
      }
    } catch (e) {
      console.error(e)
      alert(tr(language, { en: 'Exchange failed', ja: '交換に失敗しました', th: 'แลกเปลี่ยนล้มเหลว', vi: 'Đổi thất bại' }))
    }

    setLoading(false)
  }

  const exchangeRate = 1000 // 1 point = 1000 USD

  return (
    <div className="page-container">
      <h2 className="page-title">{t.exchange.title}</h2>

      {/* Current Balance Card */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
            {t.exchange.currentPoints}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 600, color: 'var(--accent-primary)' }}>
            {points.toLocaleString()}
          </div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
            {t.exchange.currentCash}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 600, color: 'var(--success)' }}>
            ${cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* Exchange Rate Info */}
      <div style={{ textAlign: 'center', marginBottom: '24px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
        <div style={{ fontSize: '16px', color: 'var(--text-secondary)' }}>
          {t.exchange.exchangeRate}
        </div>
        <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginTop: '4px' }}>
          {tr(language, { en: `You can exchange ${points} points for $${(points * exchangeRate).toLocaleString()} USD`, ja: `${points} ポイントを $${(points * exchangeRate).toLocaleString()} USD と交換できます`, th: `คุณสามารถแลก ${points} คะแนนเป็น $${(points * exchangeRate).toLocaleString()} USD`, vi: `Bạn có thể đổi ${points} điểm thành $${(points * exchangeRate).toLocaleString()} USD` })}
        </div>
      </div>

      {/* Exchange Form */}
      <form onSubmit={handleSubmit} className="form-card">
        <div className="form-group">
          <label className="form-label">{t.exchange.amount}</label>
          <input
            type="number"
            min="1"
            max={points}
            className="form-input"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            placeholder={tr(language, { en: 'Enter points amount', ja: 'ポイント数を入力', th: 'กรอกจำนวนคะแนน', vi: 'Nhập số điểm' })}
            required
          />
        </div>

        {/* Preview */}
        {amount && parseInt(amount) > 0 && (
          <div style={{ marginBottom: '16px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
            <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
              {tr(language, { en: 'You will receive', ja: '受け取り', th: 'คุณจะได้รับ', vi: 'Bạn sẽ nhận' })}
            </div>
            <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--success)' }}>
              ${(parseInt(amount) * exchangeRate).toLocaleString()} USD
            </div>
          </div>
        )}

        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading || !amount || parseInt(amount) > points}>
          {loading ? (tr(language, { en: 'Exchanging...', ja: '交換中...', th: 'กำลังแลก...', vi: 'Đang đổi...' })) : t.exchange.submit}
        </button>
      </form>
    </div>
  )
}

export default ExchangePage
