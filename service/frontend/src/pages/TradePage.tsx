import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, isUSMarketOpen, getCurrentETTime, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Trade Page - Place Order
export function TradePage({ token, agentInfo, onTradeSuccess }: { token: string, agentInfo?: any, onTradeSuccess?: () => void }) {
  const { t, language } = useLanguage()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [market, setMarket] = useState('us-stock')
  const [action, setAction] = useState('buy')
  const [symbol, setSymbol] = useState('')
  const [polymarketOutcome, setPolymarketOutcome] = useState('')
  const [polymarketTokenId, setPolymarketTokenId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [content, setContent] = useState('')
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [priceLoading, setPriceLoading] = useState(false)
  const [activeChallenges, setActiveChallenges] = useState<any[]>([])

  // Get current time for display
  const [currentTime, setCurrentTime] = useState(() => new Date().toISOString())

  // Update current time every second
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date().toISOString())
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const loadActiveChallenges = async () => {
      try {
        const res = await fetch(`${API_BASE}/challenges/me`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (!res.ok) return
        const data = await res.json()
        setActiveChallenges((data.challenges || []).filter((challenge: any) => challenge.status === 'active'))
      } catch (e) {
        console.error(e)
      }
    }

    loadActiveChallenges()
  }, [token])

  // Polymarket is spot-like in this app: no short/cover. Force a valid action when switching.
  useEffect(() => {
    if (market === 'polymarket' && (action === 'short' || action === 'cover')) {
      setAction('buy')
    }
  }, [market, action])

  // Get Price button handler
  const handleGetPrice = async () => {
    if (!symbol) {
      alert(tr(language, { en: 'Please enter symbol', ja: '銘柄を入力してください', th: 'กรุณาใส่สัญลักษณ์', vi: 'Vui lòng nhập mã' }))
      return
    }

    setPriceLoading(true)
    try {
      const requestSymbol = market === 'polymarket' ? symbol.trim() : symbol.toUpperCase()
      const priceParams = new URLSearchParams({
        symbol: requestSymbol,
        market,
      })
      if (market === 'polymarket' && polymarketOutcome.trim()) {
        priceParams.set('outcome', polymarketOutcome.trim())
      }
      if (market === 'polymarket' && polymarketTokenId.trim()) {
        priceParams.set('token_id', polymarketTokenId.trim())
      }
      const res = await fetch(`${API_BASE}/price?${priceParams.toString()}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })

      const data = await res.json()

      if (res.ok && data.price !== null && data.price !== undefined) {
        setCurrentPrice(data.price)
        // Auto-fill price input
        const priceInput = document.getElementById('price-input') as HTMLInputElement
        if (priceInput) {
          priceInput.value = data.price.toString()
        }
      } else if (res.status === 404) {
        alert(tr(language, { en: 'Unable to get price for this symbol', ja: 'この銘柄の価格を取得できません', th: 'ไม่สามารถดึงราคาของสัญลักษณ์นี้ได้', vi: 'Không thể lấy giá cho mã này' }))
      } else {
        alert(tr(language, { en: 'Failed to get price', ja: '価格の取得に失敗しました', th: 'ดึงราคาล้มเหลว', vi: 'Lấy giá thất bại' }))
      }
    } catch (e) {
      console.error(e)
      alert(tr(language, { en: 'Failed to get price', ja: '価格の取得に失敗しました', th: 'ดึงราคาล้มเหลว', vi: 'Lấy giá thất bại' }))
    }
    setPriceLoading(false)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    // Validate US market hours
    if (market === 'us-stock') {
      if (!isUSMarketOpen()) {
        alert(tr(language, {
          en: 'US market is closed. Current time: ' + getCurrentETTime() + ' ET\nUS market hours: Mon-Fri 9:30-16:00 ET',
          ja: '米国株式市場は休場です。現在時刻: ' + getCurrentETTime() + ' ET\n取引時間: 月-金 9:30-16:00 ET',
          th: 'ตลาดหุ้นสหรัฐปิดอยู่ เวลาปัจจุบัน: ' + getCurrentETTime() + ' ET\nเวลาทำการ: จันทร์-ศุกร์ 9:30-16:00 ET',
          vi: 'Thị trường Mỹ đã đóng. Giờ hiện tại: ' + getCurrentETTime() + ' ET\nGiờ giao dịch: T2-T6 9:30-16:00 ET'
        }))
        return
      }
    }

    // Require price to be fetched first
    if (!currentPrice) {
      alert(tr(language, { en: 'Please click "Get Price" first', ja: 'まず「価格を取得」をクリックしてください', th: 'กรุณาคลิก "รับราคา" ก่อน', vi: 'Vui lòng nhấp "Lấy giá" trước' }))
      return
    }

    // Check cash for buy/short actions (include 0.1% fee)
    if (action === 'buy' || action === 'short') {
      const tradeValue = currentPrice * parseFloat(quantity)
      const feeRate = 0.001 // 0.1% transaction fee
      const totalRequired = tradeValue * (1 + feeRate)
      const availableCash = agentInfo?.cash || 0
      if (availableCash < totalRequired) {
        const points = agentInfo?.points || 0
        const exchangeRate = 0.01 // 100 points = $1
        const exchangeableCash = points * exchangeRate
        const fee = tradeValue * feeRate
        alert(tr(language, { en: `Insufficient cash! Required: $${totalRequired.toFixed(2)} (trade: $${tradeValue.toFixed(2)} + fee: $${fee.toFixed(2)}), Available: $${availableCash.toFixed(2)}\n\nYou have ${points} points, can exchange for $${exchangeableCash.toFixed(2)}\nPlease go to "Points Exchange" page first`, ja: `現金が不足しています！必要: $${totalRequired.toFixed(2)} (取引: $${tradeValue.toFixed(2)} + 手数料: $${fee.toFixed(2)})、利用可能: $${availableCash.toFixed(2)}\n\n${points} ポイントを保有しており、$${exchangeableCash.toFixed(2)} と交換できます\nまず「ポイント交換」ページへ移動してください`, th: `เงินสดไม่เพียงพอ! ต้องการ: $${totalRequired.toFixed(2)} (เทรด: $${tradeValue.toFixed(2)} + ค่าธรรมเนียม: $${fee.toFixed(2)}), ใช้ได้: $${availableCash.toFixed(2)}\n\nคุณมี ${points} คะแนน แลกได้ $${exchangeableCash.toFixed(2)}\nกรุณาไปหน้า "แลกคะแนน" ก่อน`, vi: `Không đủ tiền! Yêu cầu: $${totalRequired.toFixed(2)} (giao dịch: $${tradeValue.toFixed(2)} + phí: $${fee.toFixed(2)}), Khả dụng: $${availableCash.toFixed(2)}\n\nBạn có ${points} điểm, có thể đổi $${exchangeableCash.toFixed(2)}\nVui lòng đến trang "Đổi điểm" trước` }))
        return
      }
    }

    setLoading(true)

    const now = new Date()
    const executedAt = now.toISOString()

    try {
      const requestSymbol = market === 'polymarket' ? symbol.trim() : symbol.toUpperCase()
      const res = await fetch(`${API_BASE}/signals/realtime`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          market,
          action,
          symbol: requestSymbol,
          outcome: market === 'polymarket' && polymarketOutcome.trim() ? polymarketOutcome.trim() : undefined,
          token_id: market === 'polymarket' && polymarketTokenId.trim() ? polymarketTokenId.trim() : undefined,
          price: currentPrice,
          quantity: parseFloat(quantity),
          content,
          executed_at: executedAt
        })
      })

      const data = await res.json()

      if (res.ok) {
        alert(tr(language, { en: 'Order placed successfully!', ja: '注文が成立しました！', th: 'วางคำสั่งสำเร็จ!', vi: 'Đặt lệnh thành công!' }))
        // Reset form
        setSymbol('')
        setPolymarketOutcome('')
        setPolymarketTokenId('')
        setCurrentPrice(null)
        setQuantity('')
        setContent('')
        // Refresh agent info before navigating
        if (onTradeSuccess) onTradeSuccess()
        navigate('/positions')
      } else {
        alert(data.detail || (tr(language, { en: 'Order failed', ja: '注文に失敗しました', th: 'วางคำสั่งล้มเหลว', vi: 'Đặt lệnh thất bại' })))
      }
    } catch (e) {
      console.error(e)
      alert(tr(language, { en: 'Order failed', ja: '注文に失敗しました', th: 'วางคำสั่งล้มเหลว', vi: 'Đặt lệnh thất bại' }))
    }

    setLoading(false)
  }

  const matchingChallenges = activeChallenges.filter((challenge) => {
    if (challenge.market !== market) return false
    if (!challenge.symbol || challenge.symbol === 'all') return true
    if (!symbol.trim()) return true
    return String(challenge.symbol).toUpperCase() === symbol.trim().toUpperCase()
  })

  return (
    <div className="page-container">
      <h2 className="page-title">{t.trade.title}</h2>

      {matchingChallenges.length > 0 && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ fontWeight: 700, marginBottom: '8px' }}>
            {tr(language, { en: 'This trade will count toward active challenges', ja: 'この取引はアクティブなチャレンジにカウントされます', th: 'การเทรดนี้จะถูกนับรวมในชาเลนจ์ที่ใช้งานอยู่', vi: 'Giao dịch này sẽ được tính vào các thử thách đang chạy' })}
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {matchingChallenges.map((challenge) => (
              <span key={challenge.challenge_key} className="tag">
                {challenge.title}
              </span>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="form-card">
        {/* Market */}
        <div className="form-group">
          <label className="form-label">{t.trade.market}</label>
          <select
            className="form-input"
            value={market}
            onChange={e => setMarket(e.target.value)}
          >
            <option value="us-stock">{tr(language, { en: 'US Stock', ja: '米国株', th: 'หุ้นสหรัฐ', vi: 'Cổ phiếu Mỹ' })}</option>
            <option value="crypto">{tr(language, { en: 'Crypto', ja: '暗号通貨', th: 'คริปโต', vi: 'Tiền mã hóa' })}</option>
            <option value="polymarket">{tr(language, { en: 'Polymarket (Testing)', ja: 'Polymarket (テスト)', th: 'Polymarket (ทดสอบ)', vi: 'Polymarket (Thử nghiệm)' })}</option>
          </select>
        </div>

        {/* Action */}
        <div className="form-group">
          <label className="form-label">{t.trade.action}</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              className={`btn ${action === 'buy' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('buy')}
            >
              {t.trade.buy} 📈
            </button>
            <button
              type="button"
              className={`btn ${action === 'sell' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('sell')}
            >
              {t.trade.sell} 📉
            </button>
            <button
              type="button"
              className={`btn ${action === 'short' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('short')}
              disabled={market === 'polymarket'}
              title={market === 'polymarket' ? (tr(language, { en: 'Polymarket does not support short/cover', ja: 'Polymarket はショート/カバーをサポートしません', th: 'Polymarket ไม่รองรับ short/cover', vi: 'Polymarket không hỗ trợ short/cover' })) : undefined}
            >
              {t.trade.short} 🔻
            </button>
            <button
              type="button"
              className={`btn ${action === 'cover' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('cover')}
              disabled={market === 'polymarket'}
              title={market === 'polymarket' ? (tr(language, { en: 'Polymarket does not support short/cover', ja: 'Polymarket はショート/カバーをサポートしません', th: 'Polymarket ไม่รองรับ short/cover', vi: 'Polymarket không hỗ trợ short/cover' })) : undefined}
            >
              {t.trade.cover} 🔺
            </button>
          </div>
          {market === 'polymarket' && (
            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              {tr(language, { en: 'Note: Polymarket is spot-like paper trading here (no short/cover). Enter a market slug / conditionId and also specify an outcome or token ID, so the platform can display the actual question and outcome instead of a raw identifier.', ja: '注: ここでの Polymarket はスポット風の模擬取引です (ショート/カバーなし)。market slug / conditionId を入力し、outcome または token ID も指定してください。プラットフォームが生の識別子ではなく実際の質問と結果を表示できます。', th: 'หมายเหตุ: Polymarket ที่นี่เป็นการเทรดจำลองแบบ spot (ไม่มี short/cover) ใส่ market slug / conditionId และระบุ outcome หรือ token ID ด้วย เพื่อให้แพลตฟอร์มแสดงคำถามและผลลัพธ์จริงแทนตัวระบุดิบ', vi: 'Lưu ý: Polymarket ở đây là giao dịch giả lập kiểu spot (không short/cover). Nhập market slug / conditionId và chỉ định outcome hoặc token ID để nền tảng hiển thị câu hỏi và kết quả thực thay vì định danh thô.' })}
            </div>
          )}
        </div>

        {/* Symbol */}
        <div className="form-group">
          <label className="form-label">{t.trade.symbol}</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              className="form-input"
              value={symbol}
              onChange={e => {
                setSymbol(e.target.value)
                setCurrentPrice(null)
              }}
              placeholder={tr(language, { en: 'e.g., BTC, AAPL, TSLA', ja: '例: BTC, AAPL, TSLA', th: 'เช่น BTC, AAPL, TSLA', vi: 'VD: BTC, AAPL, TSLA' })}
              required
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleGetPrice}
              disabled={!symbol || priceLoading}
            >
              {priceLoading ? '...' : (tr(language, { en: 'Get Price', ja: '価格を取得', th: 'รับราคา', vi: 'Lấy giá' }))}
            </button>
          </div>
          {currentPrice && (
            <div style={{ marginTop: '8px', color: 'var(--accent-primary)', fontWeight: 500 }}>
              {tr(language, { en: 'Current Price: $', ja: '現在価格: $', th: 'ราคาปัจจุบัน: $', vi: 'Giá hiện tại: $' })}{currentPrice.toFixed(2)}
            </div>
          )}
        </div>

        {market === 'polymarket' && (
          <>
            <div className="form-group">
              <label className="form-label">{tr(language, { en: 'Outcome', ja: '結果', th: 'ผลลัพธ์', vi: 'Kết quả' })}</label>
              <input
                type="text"
                className="form-input"
                value={polymarketOutcome}
                onChange={e => {
                  setPolymarketOutcome(e.target.value)
                  setCurrentPrice(null)
                }}
                placeholder={tr(language, { en: 'e.g. Yes / No', ja: '例: Yes / No', th: 'เช่น Yes / No', vi: 'VD: Yes / No' })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">{tr(language, { en: 'Token ID (Optional)', ja: 'トークンID (任意)', th: 'Token ID (ตัวเลือก)', vi: 'Token ID (Tùy chọn)' })}</label>
              <input
                type="text"
                className="form-input"
                value={polymarketTokenId}
                onChange={e => {
                  setPolymarketTokenId(e.target.value)
                  setCurrentPrice(null)
                }}
                placeholder={tr(language, { en: 'Fill this if you already know the outcome token', ja: '結果トークンが分かっている場合に入力', th: 'กรอกหากทราบ outcome token แล้ว', vi: 'Điền nếu bạn đã biết outcome token' })}
              />
            </div>
          </>
        )}

        {/* Price - read only, auto-filled after clicking Get Price */}
        <div className="form-group">
          <label className="form-label">{t.trade.price}</label>
          <input
            id="price-input"
            type="text"
            className="form-input"
            value={currentPrice ? `$${currentPrice.toFixed(2)}` : ''}
            readOnly
            placeholder={tr(language, { en: 'Click "Get Price" to get price', ja: '「価格を取得」をクリックして価格を取得', th: 'คลิก "รับราคา" เพื่อดึงราคา', vi: 'Nhấp "Lấy giá" để lấy giá' })}
            style={{ backgroundColor: 'var(--bg-secondary)' }}
          />
        </div>

        {/* Quantity */}
        <div className="form-group">
          <label className="form-label">{t.trade.quantity}</label>
          <input
            type="number"
            step="any"
            className="form-input"
            value={quantity}
            onChange={e => setQuantity(e.target.value)}
            placeholder={tr(language, { en: 'Quantity', ja: '数量', th: 'จำนวน', vi: 'Số lượng' })}
            required
          />
        </div>

        {/* Current Time Display */}
        <div className="form-group">
          <label className="form-label">{t.trade.executedAt}</label>
          <div style={{
            padding: '12px',
            background: 'var(--bg-tertiary)',
            borderRadius: '8px',
            fontFamily: 'monospace',
            fontSize: '14px'
          }}>
            {new Date(currentTime).toLocaleString(tr(language, { en: 'en-US', ja: 'en-US', th: 'en-US', vi: 'en-US' }), {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            })}
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {tr(language, { en: 'Eastern Time (ET)', ja: '米国東部時間 (ET)', th: 'เวลาตะวันออก (ET)', vi: 'Giờ miền Đông (ET)' })}: {getCurrentETTime()}
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="form-group">
          <label className="form-label">{t.trade.content}</label>
          <textarea
            className="form-input"
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder={tr(language, { en: 'Note (optional)', ja: 'メモ (任意)', th: 'หมายเหตุ (ตัวเลือก)', vi: 'Ghi chú (tùy chọn)' })}
            rows={3}
          />
        </div>

        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
          {loading ? (tr(language, { en: 'Submitting...', ja: '送信中...', th: 'กำลังส่ง...', vi: 'Đang gửi...' })) : t.trade.submit}
        </button>
      </form>
    </div>
  )
}

export default TradePage
