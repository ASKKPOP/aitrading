import { useState, useEffect } from 'react'
import { API_BASE, FINANCIAL_NEWS_PAGE_SIZE, formatIntelNumber, formatIntelTimestamp, type MarketIntelNewsCategory, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Enum vocabularies the backend emits as raw identifiers. The raw value stays
// the CSS class (intel-activity-badge ${status}); only the displayed text is
// localized. Keyed lower-cased so a value's casing can't miss the lookup.
type EnumLabel = { ko: string; en: string; ja: string; th: string; vi: string; id: string }

// Shared macro tone — used by the macro verdict, each macro signal's status,
// and a stock's trend_status (bullish | bearish | defensive | neutral |
// constructive | mixed).
const TONE_LABELS: Record<string, EnumLabel> = {
  bullish: { ko: '강세', en: 'bullish', ja: '強気', th: 'ขาขึ้น', vi: 'tăng', id: 'bullish' },
  bearish: { ko: '약세', en: 'bearish', ja: '弱気', th: 'ขาลง', vi: 'giảm', id: 'bearish' },
  defensive: { ko: '방어적', en: 'defensive', ja: '守勢', th: 'ตั้งรับ', vi: 'phòng thủ', id: 'defensif' },
  neutral: { ko: '중립', en: 'neutral', ja: '中立', th: 'เป็นกลาง', vi: 'trung tính', id: 'netral' },
  constructive: { ko: '우호적', en: 'constructive', ja: '建設的', th: 'เชิงบวก', vi: 'tích cực', id: 'konstruktif' },
  mixed: { ko: '혼조', en: 'mixed', ja: 'まちまち', th: 'ผสม', vi: 'trái chiều', id: 'campuran' },
  unavailable: { ko: '데이터 없음', en: 'unavailable', ja: 'データなし', th: 'ไม่มีข้อมูล', vi: 'không có dữ liệu', id: 'tidak tersedia' },
  quiet: { ko: '잠잠', en: 'quiet', ja: '静か', th: 'เงียบสงบ', vi: 'trầm lắng', id: 'sepi' },
}

// ETF flow direction (inflow | outflow | mixed).
const DIRECTION_LABELS: Record<string, EnumLabel> = {
  inflow: { ko: '유입', en: 'inflow', ja: '流入', th: 'ไหลเข้า', vi: 'dòng vào', id: 'masuk' },
  outflow: { ko: '유출', en: 'outflow', ja: '流出', th: 'ไหลออก', vi: 'dòng ra', id: 'keluar' },
  mixed: TONE_LABELS.mixed,
}

// News-lane activity (elevated | active | calm | quiet | unavailable).
const ACTIVITY_LABELS: Record<string, EnumLabel> = {
  elevated: { ko: '고조', en: 'elevated', ja: '高水準', th: 'สูงมาก', vi: 'rất cao', id: 'sangat aktif' },
  active: { ko: '활발', en: 'active', ja: '活発', th: 'คึกคัก', vi: 'sôi động', id: 'aktif' },
  calm: { ko: '차분', en: 'calm', ja: '平穏', th: 'เงียบ', vi: 'êm ả', id: 'tenang' },
  quiet: TONE_LABELS.quiet,
  unavailable: TONE_LABELS.unavailable,
}

// Stock signal (buy | hold | sell | watch).
const SIGNAL_LABELS: Record<string, EnumLabel> = {
  buy: { ko: '매수', en: 'buy', ja: '買い', th: 'ซื้อ', vi: 'mua', id: 'beli' },
  hold: { ko: '보유', en: 'hold', ja: '保有', th: 'ถือ', vi: 'giữ', id: 'tahan' },
  sell: { ko: '매도', en: 'sell', ja: '売り', th: 'ขาย', vi: 'bán', id: 'jual' },
  watch: { ko: '관망', en: 'watch', ja: '様子見', th: 'เฝ้าดู', vi: 'theo dõi', id: 'pantau' },
}

// Alpha Vantage news sentiment (Bullish | Somewhat-Bullish | Neutral |
// Somewhat-Bearish | Bearish).
const SENTIMENT_LABELS: Record<string, EnumLabel> = {
  bullish: TONE_LABELS.bullish,
  'somewhat-bullish': { ko: '다소 강세', en: 'Somewhat-Bullish', ja: 'やや強気', th: 'ค่อนข้างขาขึ้น', vi: 'hơi tăng', id: 'agak bullish' },
  neutral: TONE_LABELS.neutral,
  'somewhat-bearish': { ko: '다소 약세', en: 'Somewhat-Bearish', ja: 'やや弱気', th: 'ค่อนข้างขาลง', vi: 'hơi giảm', id: 'agak bearish' },
  bearish: TONE_LABELS.bearish,
}

export function FinancialEventsPage() {
  const { language } = useLanguage()

  // Localize an enum value, keeping the raw text if it isn't in the map so a
  // newly-added backend value degrades to English rather than vanishing.
  const enumLabel = (raw: unknown, map: Record<string, EnumLabel>): string => {
    if (raw === null || raw === undefined || raw === '') return ''
    const entry = map[String(raw).toLowerCase()]
    return entry ? tr(language, entry) : String(raw)
  }

  const macroVerdictLabel = (v?: string) => {
    if (!v) return tr(language, { ko: '해당 없음', en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A', id: 'T/A' })
    return enumLabel(v, TONE_LABELS)
  }
  const [macro, setMacro] = useState<any | null>(null)
  const [etfFlows, setEtfFlows] = useState<any | null>(null)
  const [featuredStocks, setFeaturedStocks] = useState<any | null>(null)
  const [stockDetailsBySymbol, setStockDetailsBySymbol] = useState<Record<string, any>>({})
  const [news, setNews] = useState<any | null>(null)
  const [newsPages, setNewsPages] = useState<Record<string, number>>({})
  const [activeNewsCategory, setActiveNewsCategory] = useState<string>('')
  const [activeStockSymbol, setActiveStockSymbol] = useState<string>('')
  const [stockHistoryBySymbol, setStockHistoryBySymbol] = useState<Record<string, any[]>>({})
  const [expandedStockHistory, setExpandedStockHistory] = useState<Record<string, boolean>>({})
  const [loadingStockHistory, setLoadingStockHistory] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async (isInitial = false) => {
      if (isInitial) {
        setLoading(true)
      }

      try {
        const [macroRes, etfRes, stocksRes, newsRes] = await Promise.all([
          fetch(`${API_BASE}/market-intel/macro-signals`),
          fetch(`${API_BASE}/market-intel/etf-flows`),
          fetch(`${API_BASE}/market-intel/stocks/featured?limit=10`),
          fetch(`${API_BASE}/market-intel/news?limit=12`)
        ])

        if (!macroRes.ok || !etfRes.ok || !stocksRes.ok || !newsRes.ok) {
          throw new Error(tr(language, { ko: '금융 이벤트를 불러오지 못했습니다', en: 'Failed to load financial events', ja: '金融イベントの読み込みに失敗しました', th: 'โหลดเหตุการณ์การเงินล้มเหลว', vi: 'Tải sự kiện tài chính thất bại', id: 'Gagal memuat peristiwa keuangan' }))
        }

        const [macroData, etfData, stocksData, newsData] = await Promise.all([
          macroRes.json(),
          etfRes.json(),
          stocksRes.json(),
          newsRes.json()
        ])

        if (cancelled) return
        setMacro(macroData)
        setEtfFlows(etfData)
        setFeaturedStocks(stocksData)
        setNews(newsData)
        setNewsPages({})
        setError(null)
      } catch (err: any) {
        if (cancelled) return
        setError(err?.message || (tr(language, { ko: '금융 이벤트를 불러오지 못했습니다', en: 'Failed to load financial events', ja: '金融イベントの読み込みに失敗しました', th: 'โหลดเหตุการณ์การเงินล้มเหลว', vi: 'Tải sự kiện tài chính thất bại', id: 'Gagal memuat peristiwa keuangan' })))
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    load(true)
    const timer = setInterval(() => load(false), 60 * 1000)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [language])

  const categories: MarketIntelNewsCategory[] = news?.categories || []
  const stockItems = (featuredStocks?.items || []).filter((item: any) => item?.available)
  const currentCategory = categories.find((section) => section.category === activeNewsCategory) || categories[0] || null
  const currentStockBase = stockItems.find((item: any) => item.symbol === activeStockSymbol) || stockItems[0] || null
  const currentStockSymbol = currentStockBase?.symbol || ''
  const currentStock = (currentStockSymbol && stockDetailsBySymbol[currentStockSymbol]) || currentStockBase || null
  const currentCategoryTitle = currentCategory
    ? ((currentCategory.category === 'equities')
      ? (tr(language, { ko: '최신 뉴스', en: 'Latest News', ja: '最新ニュース', th: 'ข่าวล่าสุด', vi: 'Tin mới nhất', id: 'Berita terbaru' }))
      : currentCategory.label)
    : ''

  useEffect(() => {
    if (categories.length === 0) {
      if (activeNewsCategory) setActiveNewsCategory('')
      return
    }
    if (!categories.some((section) => section.category === activeNewsCategory)) {
      setActiveNewsCategory(categories[0].category)
    }
  }, [categories, activeNewsCategory])

  useEffect(() => {
    if (stockItems.length === 0) {
      if (activeStockSymbol) setActiveStockSymbol('')
      return
    }
    if (!stockItems.some((item: any) => item.symbol === activeStockSymbol)) {
      setActiveStockSymbol(stockItems[0].symbol)
    }
  }, [stockItems, activeStockSymbol])

  useEffect(() => {
    if (!currentStockSymbol) {
      return
    }

    let cancelled = false

    const loadStockDetail = async () => {
      try {
        const res = await fetch(`${API_BASE}/market-intel/stocks/${currentStockSymbol}/latest`)
        if (!res.ok) {
          throw new Error('stock_detail_load_failed')
        }
        const data = await res.json()
        if (cancelled || !data?.available) {
          return
        }
        setStockDetailsBySymbol((prev) => ({
          ...prev,
          [currentStockSymbol]: data
        }))
      } catch {
        // Keep rendering the snapshot payload from the featured list when live detail fails.
      }
    }

    loadStockDetail()
    const timer = setInterval(loadStockDetail, 60 * 1000)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [currentStockSymbol])

  const toggleStockHistory = async (symbol: string) => {
    const nextExpanded = !expandedStockHistory[symbol]
    setExpandedStockHistory((prev) => ({ ...prev, [symbol]: nextExpanded }))

    if (!nextExpanded || stockHistoryBySymbol[symbol] || loadingStockHistory[symbol]) {
      return
    }

    setLoadingStockHistory((prev) => ({ ...prev, [symbol]: true }))
    try {
      const res = await fetch(`${API_BASE}/market-intel/stocks/${symbol}/history?limit=6`)
      if (!res.ok) {
        throw new Error('history_load_failed')
      }
      const data = await res.json()
      setStockHistoryBySymbol((prev) => ({
        ...prev,
        [symbol]: data.history || []
      }))
    } catch {
      setStockHistoryBySymbol((prev) => ({
        ...prev,
        [symbol]: []
      }))
    } finally {
      setLoadingStockHistory((prev) => ({ ...prev, [symbol]: false }))
    }
  }

  return (
    <div className="intel-page">
      <section className="intel-hero">
        <h1 className="intel-title">
          {tr(language, { ko: '하나의 보드에서 필요한 모든 것을 추적하세요', en: 'One board, track everything you need', ja: '1つのボードで必要なものすべてを追跡', th: 'บอร์ดเดียว ติดตามทุกอย่างที่คุณต้องการ', vi: 'Một bảng, theo dõi mọi thứ bạn cần', id: 'Satu papan, pantau semua yang Anda butuhkan' })}
        </h1>
      </section>

      <section className="intel-section">
        {loading && categories.length === 0 ? (
          <div className="intel-empty-card">
            <div className="loading"><div className="spinner"></div></div>
          </div>
        ) : error && categories.length === 0 ? (
          <div className="intel-empty-card">
            <div className="empty-title">{tr(language, { ko: '금융 이벤트 보드를 일시적으로 사용할 수 없습니다', en: 'Financial events board is temporarily unavailable', ja: '金融イベントボードは一時的に利用できません', th: 'บอร์ดเหตุการณ์การเงินใช้งานไม่ได้ชั่วคราว', vi: 'Bảng sự kiện tài chính tạm thời không khả dụng', id: 'Papan peristiwa keuangan sementara tidak tersedia' })}</div>
            <div className="text-muted">{error}</div>
          </div>
        ) : (
          <>
            <div className="intel-status-strip">
              <div className="intel-status-card">
                <span>{tr(language, { ko: '매크로 국면', en: 'Macro regime', ja: 'マクロレジーム', th: 'ระบอบมหภาค', vi: 'Chế độ vĩ mô', id: 'Kondisi makro' })}</span>
                <strong>{macroVerdictLabel(macro?.verdict)}</strong>
              </div>
              <div className="intel-status-card">
                <span>{tr(language, { ko: 'ETF 자금 흐름', en: 'ETF flow', ja: 'ETFフロー', th: 'กระแสเงิน ETF', vi: 'Dòng tiền ETF', id: 'Aliran dana ETF' })}</span>
                <strong>{enumLabel(etfFlows?.summary?.direction, DIRECTION_LABELS) || (tr(language, { ko: '해당 없음', en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A', id: 'T/A' }))}</strong>
              </div>
              <div className="intel-status-card">
                <span>{tr(language, { ko: '뉴스 레인', en: 'News lanes', ja: 'ニュースレーン', th: 'ช่องข่าว', vi: 'Luồng tin tức', id: 'Jalur berita' })}</span>
                <strong>{categories.length}</strong>
              </div>
              <div className="intel-status-card">
                <span>{tr(language, { ko: '주요 종목', en: 'Featured symbols', ja: '注目銘柄', th: 'สัญลักษณ์แนะนำ', vi: 'Mã nổi bật', id: 'Simbol unggulan' })}</span>
                <strong>{stockItems.length}</strong>
              </div>
            </div>

            <div className="intel-board">
              <div className="intel-main-column">
                {currentStock && (
                  <article className="intel-stocks-card intel-main-panel">
                    <div className="intel-news-card-header">
                      <div>
                        <div className="intel-news-title">{tr(language, { ko: '주요 종목 분석', en: 'Featured Stock Analysis', ja: '注目株分析', th: 'การวิเคราะห์หุ้นแนะนำ', vi: 'Phân tích cổ phiếu nổi bật', id: 'Analisis saham unggulan' })}</div>
                      </div>
                    </div>

                    <div className="intel-panel-tabs">
                      {stockItems.map((item: any) => (
                        <button
                          key={item.symbol}
                          type="button"
                          className={`intel-panel-tab ${item.symbol === currentStock.symbol ? 'active' : ''}`}
                          onClick={() => setActiveStockSymbol(item.symbol)}
                        >
                          <span className="intel-panel-tab-label">{item.symbol}</span>
                        </button>
                      ))}
                    </div>

                    {(() => {
                      const item = currentStock
                      const analysis = item.analysis || {}
                      const movingAverages = analysis.moving_averages || {}
                      const supportLevels = item.support_levels || analysis.support_levels || []
                      const resistanceLevels = item.resistance_levels || analysis.resistance_levels || []
                      const bullishFactors = item.bullish_factors || analysis.bullish_factors || []
                      const riskFactors = item.risk_factors || analysis.risk_factors || []
                      const isRealtimeQuote = item.price_source === 'alpha_vantage_time_series_intraday' && !item.price_stale
                      const priceStatusLabel = item.price_stale
                        ? (tr(language, { ko: '지연 시세', en: 'Delayed quote', ja: '遅延クォート', th: 'ราคาล่าช้า', vi: 'Báo giá trễ', id: 'Kutipan tertunda' }))
                        : (tr(language, { ko: '실시간 시세', en: 'Live quote', ja: 'ライブクォート', th: 'ราคาสด', vi: 'Báo giá trực tiếp', id: 'Kutipan langsung' }))
                      const priceAsOfLabel = item.price_stale
                        ? (tr(language, { ko: '시세 기준', en: 'Quote as of', ja: 'クォート時点', th: 'ราคา ณ', vi: 'Báo giá tính đến', id: 'Kutipan per' }))
                        : (tr(language, { ko: '실시간 기준', en: 'Live as of', ja: 'ライブ時点', th: 'สด ณ', vi: 'Trực tiếp tính đến', id: 'Langsung per' }))

                      return (
                        <div className="intel-stock-detail">
                          <div className="intel-stock-item-header">
                            <div>
                              <div className="intel-etf-symbol">{item.symbol}</div>
                              <div className="intel-news-item-meta">
                                <span>{tr(language, { ko: '마지막 업데이트', en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối', id: 'Pembaruan terakhir' })}: {formatIntelTimestamp(item.created_at, language)}</span>
                              </div>
                            </div>
                            <div className={`intel-activity-badge ${item.trend_status || 'quiet'}`}>{enumLabel(item.signal, SIGNAL_LABELS)}</div>
                          </div>
                          <div className="intel-stock-price-row">
                            <div className="intel-stock-price">${item.current_price}</div>
                            <span className={`intel-price-badge ${isRealtimeQuote ? 'live' : 'stale'}`}>
                              {priceStatusLabel}
                            </span>
                          </div>
                          <div className="intel-news-item-summary">{item.summary}</div>
                          <div className="intel-chip-row">
                            <span className="intel-chip">{tr(language, { ko: '점수', en: 'Score', ja: 'スコア', th: 'คะแนน', vi: 'Điểm', id: 'Skor' })} {item.signal_score}</span>
                            <span className="intel-chip">{tr(language, { ko: '추세', en: 'Trend', ja: 'トレンド', th: 'แนวโน้ม', vi: 'Xu hướng', id: 'Tren' })} {enumLabel(item.trend_status, TONE_LABELS)}</span>
                            {item.price_as_of && (
                              <span className={`intel-chip ${item.price_stale ? 'intel-chip-warn' : 'intel-chip-live'}`}>
                                {priceAsOfLabel} {formatIntelTimestamp(item.price_as_of, language)}
                              </span>
                            )}
                            {item.price_source && (
                              <span className="intel-chip">
                                {tr(language, { ko: '시세 출처', en: 'Quote source', ja: 'クォートソース', th: 'แหล่งราคา', vi: 'Nguồn báo giá', id: 'Sumber kutipan' })} {item.price_source === 'alpha_vantage_time_series_intraday' ? 'Alpha Vantage Intraday' : 'Alpha Vantage Daily'}
                              </span>
                            )}
                            {analysis.as_of && (
                              <span className="intel-chip">{tr(language, { ko: '분석 기준 시각', en: 'Analysis as of', ja: '分析時点', th: 'วิเคราะห์ ณ', vi: 'Phân tích tính đến', id: 'Analisis per' })} {analysis.as_of}</span>
                            )}
                          </div>

                          <div className="intel-stock-metrics-grid">
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { ko: '5일 수익률', en: '5d return', ja: '5日リターン', th: 'ผลตอบแทน 5 วัน', vi: 'Lợi suất 5 ngày', id: 'Imbal hasil 5 hari' })}</span>
                              <strong>{formatIntelNumber(analysis.return_5d_pct)}%</strong>
                            </div>
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { ko: '20일 수익률', en: '20d return', ja: '20日リターン', th: 'ผลตอบแทน 20 วัน', vi: 'Lợi suất 20 ngày', id: 'Imbal hasil 20 hari' })}</span>
                              <strong>{formatIntelNumber(analysis.return_20d_pct)}%</strong>
                            </div>
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { ko: '지지까지', en: 'To support', ja: 'サポートまで', th: 'ถึงแนวรับ', vi: 'Đến hỗ trợ', id: 'Ke support' })}</span>
                              <strong>{formatIntelNumber(analysis.distance_to_support_pct)}%</strong>
                            </div>
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { ko: '저항까지', en: 'To resistance', ja: 'レジスタンスまで', th: 'ถึงแนวต้าน', vi: 'Đến kháng cự', id: 'Ke resistance' })}</span>
                              <strong>{formatIntelNumber(analysis.distance_to_resistance_pct)}%</strong>
                            </div>
                          </div>

                          <div className="intel-stock-levels-grid">
                            <div className="intel-stock-levels-card">
                              <div className="intel-stock-levels-title">{tr(language, { ko: '이동평균', en: 'Moving averages', ja: '移動平均', th: 'ค่าเฉลี่ยเคลื่อนที่', vi: 'Đường trung bình động', id: 'Rata-rata bergerak' })}</div>
                              <div className="intel-stock-levels-list">
                                <span className="intel-chip">MA5 {formatIntelNumber(movingAverages.ma5)}</span>
                                <span className="intel-chip">MA10 {formatIntelNumber(movingAverages.ma10)}</span>
                                <span className="intel-chip">MA20 {formatIntelNumber(movingAverages.ma20)}</span>
                                <span className="intel-chip">MA60 {formatIntelNumber(movingAverages.ma60)}</span>
                              </div>
                            </div>
                            <div className="intel-stock-levels-card">
                              <div className="intel-stock-levels-title">{tr(language, { ko: '주요 가격대', en: 'Key levels', ja: '主要レベル', th: 'ระดับสำคัญ', vi: 'Mức quan trọng', id: 'Level kunci' })}</div>
                              <div className="intel-stock-levels-list">
                                {supportLevels.slice(0, 2).map((level: number, index: number) => (
                                  <span key={`${item.symbol}-support-${index}`} className="intel-chip">
                                    {tr(language, { ko: '지지', en: 'Support', ja: 'サポート', th: 'แนวรับ', vi: 'Hỗ trợ', id: 'Support' })} {formatIntelNumber(level)}
                                  </span>
                                ))}
                                {resistanceLevels.slice(0, 2).map((level: number, index: number) => (
                                  <span key={`${item.symbol}-resistance-${index}`} className="intel-chip">
                                    {tr(language, { ko: '저항', en: 'Resistance', ja: 'レジスタンス', th: 'แนวต้าน', vi: 'Kháng cự', id: 'Resistance' })} {formatIntelNumber(level)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>

                          <div className="intel-factors-grid">
                            <div className="intel-factor-card">
                              <div className="intel-factor-title">{tr(language, { ko: '강세 요인', en: 'Bullish factors', ja: '強気要因', th: 'ปัจจัยบวก', vi: 'Yếu tố tăng giá', id: 'Faktor bullish' })}</div>
                              {bullishFactors.length > 0 ? (
                                <ul className="intel-factor-list">
                                  {bullishFactors.map((factor: string) => (
                                    <li key={`${item.symbol}-bullish-${factor}`}>{factor}</li>
                                  ))}
                                </ul>
                              ) : (
                                <div className="intel-empty-inline">{tr(language, { ko: '뚜렷한 강세 요인이 없습니다.', en: 'No clear bullish factors.', ja: '明確な強気要因はありません。', th: 'ยังไม่มีปัจจัยบวกชัดเจน', vi: 'Chưa có yếu tố tăng giá rõ ràng.', id: 'Tidak ada faktor bullish yang jelas.' })}</div>
                              )}
                            </div>
                            <div className="intel-factor-card intel-factor-card-risk">
                              <div className="intel-factor-title">{tr(language, { ko: '위험 요인', en: 'Risk factors', ja: 'リスク要因', th: 'ปัจจัยเสี่ยง', vi: 'Yếu tố rủi ro', id: 'Faktor risiko' })}</div>
                              {riskFactors.length > 0 ? (
                                <ul className="intel-factor-list">
                                  {riskFactors.map((factor: string) => (
                                    <li key={`${item.symbol}-risk-${factor}`}>{factor}</li>
                                  ))}
                                </ul>
                              ) : (
                                <div className="intel-empty-inline">{tr(language, { ko: '뚜렷한 위험 요인이 없습니다.', en: 'No clear risk factors.', ja: '明確なリスク要因はありません。', th: 'ยังไม่มีปัจจัยเสี่ยงชัดเจน', vi: 'Chưa có yếu tố rủi ro rõ ràng.', id: 'Tidak ada faktor risiko yang jelas.' })}</div>
                              )}
                            </div>
                          </div>

                          <button
                            type="button"
                            className="intel-history-toggle"
                            onClick={() => toggleStockHistory(item.symbol)}
                          >
                            {expandedStockHistory[item.symbol]
                              ? (tr(language, { ko: '기록 숨기기', en: 'Hide history', ja: '履歴を隠す', th: 'ซ่อนประวัติ', vi: 'Ẩn lịch sử', id: 'Sembunyikan riwayat' }))
                              : (tr(language, { ko: '기록 보기', en: 'Show history', ja: '履歴を表示', th: 'แสดงประวัติ', vi: 'Hiện lịch sử', id: 'Tampilkan riwayat' }))}
                          </button>
                          {expandedStockHistory[item.symbol] && (
                            <div className="intel-history-panel">
                              {loadingStockHistory[item.symbol] ? (
                                <div className="intel-empty-inline">
                                  {tr(language, { ko: '기록 스냅샷 불러오는 중...', en: 'Loading history snapshots...', ja: '履歴スナップショットを読み込み中...', th: 'กำลังโหลดสแนปช็อตประวัติ...', vi: 'Đang tải snapshot lịch sử...', id: 'Memuat snapshot riwayat...' })}
                                </div>
                              ) : (stockHistoryBySymbol[item.symbol] || []).length > 0 ? (
                                <div className="intel-history-list">
                                  {(stockHistoryBySymbol[item.symbol] || []).map((entry: any) => (
                                    <div key={entry.analysis_id} className="intel-history-item">
                                      <div className="intel-history-item-header">
                                        <span>{formatIntelTimestamp(entry.created_at, language)}</span>
                                        <span className={`intel-activity-badge ${entry.trend_status || 'quiet'}`}>{enumLabel(entry.signal, SIGNAL_LABELS)}</span>
                                      </div>
                                      <div className="intel-chip-row">
                                        <span className="intel-chip">{tr(language, { ko: '점수', en: 'Score', ja: 'スコア', th: 'คะแนน', vi: 'Điểm', id: 'Skor' })} {entry.signal_score}</span>
                                        <span className="intel-chip">{tr(language, { ko: '추세', en: 'Trend', ja: 'トレンド', th: 'แนวโน้ม', vi: 'Xu hướng', id: 'Tren' })} {enumLabel(entry.trend_status, TONE_LABELS)}</span>
                                        {entry.analysis?.return_5d_pct !== undefined && (
                                          <span className="intel-chip">{tr(language, { ko: '5일 수익률', en: '5d return', ja: '5日リターン', th: 'ผลตอบแทน 5 วัน', vi: 'Lợi suất 5 ngày', id: 'Imbal hasil 5 hari' })} {formatIntelNumber(entry.analysis?.return_5d_pct)}%</span>
                                        )}
                                        {entry.analysis?.return_20d_pct !== undefined && (
                                          <span className="intel-chip">{tr(language, { ko: '20일 수익률', en: '20d return', ja: '20日リターン', th: 'ผลตอบแทน 20 วัน', vi: 'Lợi suất 20 ngày', id: 'Imbal hasil 20 hari' })} {formatIntelNumber(entry.analysis?.return_20d_pct)}%</span>
                                        )}
                                      </div>
                                      <div className="intel-news-item-summary">{entry.summary}</div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="intel-empty-inline">
                                  {tr(language, { ko: '아직 기록 스냅샷이 없습니다.', en: 'No historical snapshots yet.', ja: '履歴スナップショットはまだありません。', th: 'ยังไม่มีสแนปช็อตประวัติ', vi: 'Chưa có snapshot lịch sử.', id: 'Belum ada snapshot riwayat.' })}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })()}
                  </article>
                )}

                {currentCategory && (
                  <article className="intel-news-card intel-main-panel">
                    <div className="intel-news-card-header">
                      <div>
                        <div className="intel-news-title">{currentCategoryTitle}</div>
                        <div className="intel-news-description">{currentCategory.description}</div>
                      </div>
                      <div className={`intel-activity-badge ${currentCategory.summary?.activity_level || 'quiet'}`}>
                        {enumLabel(currentCategory.summary?.activity_level, ACTIVITY_LABELS) || (tr(language, { ko: '해당 없음', en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A', id: 'T/A' }))}
                      </div>
                    </div>

                    <div className="intel-news-card-meta">
                      <span>{tr(language, { ko: '마지막 업데이트', en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối', id: 'Pembaruan terakhir' })}: {formatIntelTimestamp(currentCategory.created_at, language)}</span>
                    </div>

                    <div className="intel-panel-tabs">
                      {categories.map((section) => (
                        <button
                          key={section.category}
                          type="button"
                          className={`intel-panel-tab ${section.category === currentCategory.category ? 'active' : ''}`}
                          onClick={() => setActiveNewsCategory(section.category)}
                        >
                          <span className="intel-panel-tab-label">
                            {section.category === 'equities'
                              ? (tr(language, { ko: '최신 뉴스', en: 'Latest News', ja: '最新ニュース', th: 'ข่าวล่าสุด', vi: 'Tin mới nhất', id: 'Berita terbaru' }))
                              : section.label}
                          </span>
                        </button>
                      ))}
                    </div>

                    {(() => {
                      const totalItems = currentCategory.items?.length || 0
                      const totalPages = Math.max(1, Math.ceil(totalItems / FINANCIAL_NEWS_PAGE_SIZE))
                      const currentPage = Math.min(newsPages[currentCategory.category] || 0, totalPages - 1)
                      const start = currentPage * FINANCIAL_NEWS_PAGE_SIZE
                      const pageItems = (currentCategory.items || []).slice(start, start + FINANCIAL_NEWS_PAGE_SIZE)

                      return pageItems.length ? (
                        <>
                          <div className="intel-news-list">
                            {pageItems.map((item) => (
                              <a
                                key={`${currentCategory.category}-${item.url || item.title}`}
                                className="intel-news-item"
                                href={item.url || undefined}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <div className="intel-news-item-title">{item.title}</div>
                                <div className="intel-news-item-meta">
                                  <span>{item.source}</span>
                                  <span>{formatIntelTimestamp(item.time_published, language)}</span>
                                </div>
                                {item.summary && <div className="intel-news-item-summary">{item.summary}</div>}
                                <div className="intel-chip-row">
                                  {item.overall_sentiment_label && (
                                    <span className="intel-chip">{enumLabel(item.overall_sentiment_label, SENTIMENT_LABELS)}</span>
                                  )}
                                  {(item.ticker_sentiment || []).slice(0, 4).map((ticker: any) => (
                                    <span key={`${item.title}-${ticker.ticker}`} className="intel-chip intel-chip-symbol">
                                      {ticker.ticker}
                                    </span>
                                  ))}
                                </div>
                              </a>
                            ))}
                          </div>
                          {totalPages > 1 && (
                            <div className="intel-pager">
                              <button
                                type="button"
                                className="intel-pager-button"
                                disabled={currentPage === 0}
                                onClick={() => setNewsPages((prev) => ({
                                  ...prev,
                                  [currentCategory.category]: Math.max(0, currentPage - 1)
                                }))}
                              >
                                {tr(language, { ko: '← 이전', en: '← Prev', ja: '← 前へ', th: '← ก่อนหน้า', vi: '← Trước', id: '← Sebelumnya' })}
                              </button>
                              <div className="intel-pager-status">
                                {tr(language, { ko: `페이지 ${currentPage + 1} / ${totalPages}`, en: `Page ${currentPage + 1} / ${totalPages}`, ja: `ページ ${currentPage + 1} / ${totalPages}`, th: `หน้า ${currentPage + 1} / ${totalPages}`, vi: `Trang ${currentPage + 1} / ${totalPages}`, id: `Halaman ${currentPage + 1} / ${totalPages}` })}
                              </div>
                              <button
                                type="button"
                                className="intel-pager-button"
                                disabled={currentPage >= totalPages - 1}
                                onClick={() => setNewsPages((prev) => ({
                                  ...prev,
                                  [currentCategory.category]: Math.min(totalPages - 1, currentPage + 1)
                                }))}
                              >
                                {tr(language, { ko: '다음 →', en: 'Next →', ja: '次へ →', th: 'ถัดไป →', vi: 'Tiếp →', id: 'Berikutnya →' })}
                              </button>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="intel-empty-inline">
                          {tr(language, { ko: '이 카테고리에 대한 스냅샷 콘텐츠가 아직 없습니다.', en: 'No snapshot content available for this category yet.', ja: 'このカテゴリのスナップショットコンテンツはまだありません。', th: 'ยังไม่มีเนื้อหาสแนปช็อตสำหรับหมวดนี้', vi: 'Chưa có nội dung snapshot cho danh mục này.', id: 'Belum ada konten snapshot untuk kategori ini.' })}
                        </div>
                      )
                    })()}
                  </article>
                )}
              </div>

              <aside className="intel-side-column">
                {macro?.available && (
                  <article className="intel-macro-card intel-side-panel">
                    <div className="intel-news-card-header">
                      <div>
                        <div className="intel-news-title">{tr(language, { ko: '매크로 시그널', en: 'Macro Signals', ja: 'マクロシグナル', th: 'สัญญาณมหภาค', vi: 'Tín hiệu vĩ mô', id: 'Sinyal makro' })}</div>
                        <div className="intel-news-description">
                          {macro?.meta?.summary || tr(language, { ko: '서버 측 매크로 국면 스냅샷.', en: 'A server-side macro regime snapshot.', ja: 'サーバー側のマクロレジームスナップショット。', th: 'สแนปช็อตระบอบมหภาคจากเซิร์ฟเวอร์', vi: 'Ảnh chụp chế độ vĩ mô phía máy chủ.', id: 'Snapshot kondisi makro dari sisi server.' })}
                        </div>
                      </div>
                      <div className={`intel-activity-badge ${macro?.verdict || 'quiet'}`}>
                        {macroVerdictLabel(macro?.verdict)}
                      </div>
                    </div>
                    <div className="intel-news-card-meta">
                      <span>{tr(language, { ko: '마지막 업데이트', en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối', id: 'Pembaruan terakhir' })}: {formatIntelTimestamp(macro?.created_at, language)}</span>
                    </div>
                    <div className="intel-macro-list">
                      {(macro?.signals || []).map((signal: any) => (
                        <div key={signal.id} className="intel-macro-row">
                          <div className="intel-macro-row-top">
                            <span className="intel-macro-label">{signal.label}</span>
                            <span className={`intel-activity-badge ${signal.status || 'quiet'}`}>{enumLabel(signal.status, TONE_LABELS)}</span>
                          </div>
                          <div className="intel-macro-row-value">
                            {signal.value !== null && signal.value !== undefined
                              ? `${signal.value}${signal.unit === '%' ? '%' : ''}`
                              : (tr(language, { ko: '해당 없음', en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A', id: 'T/A' }))}
                          </div>
                          <div className="intel-news-item-summary">
                            {signal.explanation}
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                )}

                {etfFlows?.available && (
                  <article className="intel-etf-card intel-side-panel">
                    <div className="intel-news-card-header">
                      <div>
                        <div className="intel-news-title">{tr(language, { ko: 'ETF 자금 흐름', en: 'ETF Flow', ja: 'ETFフロー', th: 'กระแสเงิน ETF', vi: 'Dòng tiền ETF', id: 'Aliran dana ETF' })}</div>
                      </div>
                      <div className={`intel-activity-badge ${etfFlows?.summary?.direction || 'quiet'}`}>
                        {enumLabel(etfFlows?.summary?.direction, DIRECTION_LABELS) || (tr(language, { ko: '해당 없음', en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A', id: 'T/A' }))}
                      </div>
                    </div>
                    <div className="intel-news-card-meta">
                      <span>{tr(language, { ko: '마지막 업데이트', en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối', id: 'Pembaruan terakhir' })}: {formatIntelTimestamp(etfFlows?.created_at, language)}</span>
                    </div>
                    {etfFlows?.summary?.source === 'sosovalue' && etfFlows?.summary?.btc && (
                      <div style={{ fontSize: 12.5, lineHeight: 1.6, padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
                        <div>
                          <strong>BTC</strong>{' '}
                          {tr(language, { ko: '일간 순유입', en: 'daily net flow', ja: '日次純流入', th: 'กระแสสุทธิรายวัน', vi: 'dòng ròng hàng ngày', id: 'aliran bersih harian' })}{' '}
                          <span style={{ color: etfFlows.summary.btc.latest_net_inflow_usd >= 0 ? 'var(--success)' : 'var(--error)', fontWeight: 700 }}>
                            {etfFlows.summary.btc.latest_net_inflow_usd >= 0 ? '+' : '−'}${(Math.abs(etfFlows.summary.btc.latest_net_inflow_usd) / 1e6).toFixed(0)}M
                          </span>
                          {' · 5d '}
                          <span style={{ color: etfFlows.summary.btc.flow_5d_usd >= 0 ? 'var(--success)' : 'var(--error)' }}>
                            {etfFlows.summary.btc.flow_5d_usd >= 0 ? '+' : '−'}${(Math.abs(etfFlows.summary.btc.flow_5d_usd) / 1e6).toFixed(0)}M
                          </span>
                        </div>
                        {etfFlows.summary.eth && (
                          <div>
                            <strong>ETH</strong>{' '}
                            {tr(language, { ko: '일간 순유입', en: 'daily net flow', ja: '日次純流入', th: 'กระแสสุทธิรายวัน', vi: 'dòng ròng hàng ngày', id: 'aliran bersih harian' })}{' '}
                            <span style={{ color: etfFlows.summary.eth.latest_net_inflow_usd >= 0 ? 'var(--success)' : 'var(--error)', fontWeight: 700 }}>
                              {etfFlows.summary.eth.latest_net_inflow_usd >= 0 ? '+' : '−'}${(Math.abs(etfFlows.summary.eth.latest_net_inflow_usd) / 1e6).toFixed(0)}M
                            </span>
                          </div>
                        )}
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {tr(language, { ko: '실제 자금 데이터 (SoSoValue) · 누적', en: 'real flow data (SoSoValue) · cumulative', ja: '実フローデータ (SoSoValue) · 累計', th: 'ข้อมูลจริง (SoSoValue) · สะสม', vi: 'dữ liệu thực (SoSoValue) · lũy kế', id: 'data aliran nyata (SoSoValue) · kumulatif' })}{' '}
                          ${(etfFlows.summary.btc.cum_net_inflow_usd / 1e9).toFixed(1)}B
                        </div>
                      </div>
                    )}
                    <div className="intel-etf-stack">
                      {(etfFlows?.etfs || []).slice(0, 8).map((etf: any) => (
                        <div key={etf.symbol} className="intel-etf-stack-item">
                          <div className="intel-etf-stack-top">
                            <div className="intel-etf-symbol">{etf.symbol}</div>
                            <div className={`intel-activity-badge ${etf.direction || 'quiet'}`}>{enumLabel(etf.direction, DIRECTION_LABELS)}</div>
                          </div>
                          <div className="intel-etf-stack-metrics">
                            <div className="intel-etf-metric">
                              <span>{tr(language, { ko: '변동', en: 'Change', ja: '変動', th: 'เปลี่ยนแปลง', vi: 'Thay đổi', id: 'Perubahan' })}</span>
                              <strong>{etf.price_change_pct}%</strong>
                            </div>
                            <div className="intel-etf-metric">
                              <span>{tr(language, { ko: '거래량 비율', en: 'Vol ratio', ja: '出来高比率', th: 'อัตราส่วนปริมาณ', vi: 'Tỷ lệ khối lượng', id: 'Rasio volume' })}</span>
                              <strong>{etf.volume_ratio}</strong>
                            </div>
                            <div className="intel-etf-metric">
                              <span>{tr(language, { ko: '자금 흐름 점수', en: 'Flow score', ja: 'フロースコア', th: 'คะแนนกระแส', vi: 'Điểm dòng tiền', id: 'Skor aliran' })}</span>
                              <strong>{etf.estimated_flow_score}</strong>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                )}
              </aside>
            </div>
          </>
        )}
      </section>
    </div>
  )
}

export default FinancialEventsPage
