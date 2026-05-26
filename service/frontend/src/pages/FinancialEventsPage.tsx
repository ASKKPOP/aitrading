import { useState, useEffect } from 'react'
import { API_BASE, FINANCIAL_NEWS_PAGE_SIZE, formatIntelNumber, formatIntelTimestamp, type MarketIntelNewsCategory, useLanguage } from '../appShared'
import { tr } from '../i18n'

export function FinancialEventsPage() {
  const { language } = useLanguage()
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
          throw new Error(tr(language, { en: 'Failed to load financial events', ja: '金融イベントの読み込みに失敗しました', th: 'โหลดเหตุการณ์การเงินล้มเหลว', vi: 'Tải sự kiện tài chính thất bại' }))
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
        setError(err?.message || (tr(language, { en: 'Failed to load financial events', ja: '金融イベントの読み込みに失敗しました', th: 'โหลดเหตุการณ์การเงินล้มเหลว', vi: 'Tải sự kiện tài chính thất bại' })))
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
      ? (tr(language, { en: 'Latest News', ja: '最新ニュース', th: 'ข่าวล่าสุด', vi: 'Tin mới nhất' }))
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
          {tr(language, { en: 'One board, track everything you need', ja: '1つのボードで必要なものすべてを追跡', th: 'บอร์ดเดียว ติดตามทุกอย่างที่คุณต้องการ', vi: 'Một bảng, theo dõi mọi thứ bạn cần' })}
        </h1>
      </section>

      <section className="intel-section">
        {loading && categories.length === 0 ? (
          <div className="intel-empty-card">
            <div className="loading"><div className="spinner"></div></div>
          </div>
        ) : error && categories.length === 0 ? (
          <div className="intel-empty-card">
            <div className="empty-title">{tr(language, { en: 'Financial events board is temporarily unavailable', ja: '金融イベントボードは一時的に利用できません', th: 'บอร์ดเหตุการณ์การเงินใช้งานไม่ได้ชั่วคราว', vi: 'Bảng sự kiện tài chính tạm thời không khả dụng' })}</div>
            <div className="text-muted">{error}</div>
          </div>
        ) : (
          <>
            <div className="intel-status-strip">
              <div className="intel-status-card">
                <span>{tr(language, { en: 'Macro regime', ja: 'マクロレジーム', th: 'ระบอบมหภาค', vi: 'Chế độ vĩ mô' })}</span>
                <strong>{macro?.verdict || (tr(language, { en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A' }))}</strong>
              </div>
              <div className="intel-status-card">
                <span>{tr(language, { en: 'ETF flow', ja: 'ETFフロー', th: 'กระแสเงิน ETF', vi: 'Dòng tiền ETF' })}</span>
                <strong>{etfFlows?.summary?.direction || (tr(language, { en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A' }))}</strong>
              </div>
              <div className="intel-status-card">
                <span>{tr(language, { en: 'News lanes', ja: 'ニュースレーン', th: 'ช่องข่าว', vi: 'Luồng tin tức' })}</span>
                <strong>{categories.length}</strong>
              </div>
              <div className="intel-status-card">
                <span>{tr(language, { en: 'Featured symbols', ja: '注目銘柄', th: 'สัญลักษณ์แนะนำ', vi: 'Mã nổi bật' })}</span>
                <strong>{stockItems.length}</strong>
              </div>
            </div>

            <div className="intel-board">
              <div className="intel-main-column">
                {currentStock && (
                  <article className="intel-stocks-card intel-main-panel">
                    <div className="intel-news-card-header">
                      <div>
                        <div className="intel-news-title">{tr(language, { en: 'Featured Stock Analysis', ja: '注目株分析', th: 'การวิเคราะห์หุ้นแนะนำ', vi: 'Phân tích cổ phiếu nổi bật' })}</div>
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
                        ? (tr(language, { en: 'Delayed quote', ja: '遅延クォート', th: 'ราคาล่าช้า', vi: 'Báo giá trễ' }))
                        : (tr(language, { en: 'Live quote', ja: 'ライブクォート', th: 'ราคาสด', vi: 'Báo giá trực tiếp' }))
                      const priceAsOfLabel = item.price_stale
                        ? (tr(language, { en: 'Quote as of', ja: 'クォート時点', th: 'ราคา ณ', vi: 'Báo giá tính đến' }))
                        : (tr(language, { en: 'Live as of', ja: 'ライブ時点', th: 'สด ณ', vi: 'Trực tiếp tính đến' }))

                      return (
                        <div className="intel-stock-detail">
                          <div className="intel-stock-item-header">
                            <div>
                              <div className="intel-etf-symbol">{item.symbol}</div>
                              <div className="intel-news-item-meta">
                                <span>{tr(language, { en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối' })}: {formatIntelTimestamp(item.created_at, language)}</span>
                              </div>
                            </div>
                            <div className={`intel-activity-badge ${item.trend_status || 'quiet'}`}>{item.signal}</div>
                          </div>
                          <div className="intel-stock-price-row">
                            <div className="intel-stock-price">${item.current_price}</div>
                            <span className={`intel-price-badge ${isRealtimeQuote ? 'live' : 'stale'}`}>
                              {priceStatusLabel}
                            </span>
                          </div>
                          <div className="intel-news-item-summary">{item.summary}</div>
                          <div className="intel-chip-row">
                            <span className="intel-chip">{tr(language, { en: 'Score', ja: 'スコア', th: 'คะแนน', vi: 'Điểm' })} {item.signal_score}</span>
                            <span className="intel-chip">{tr(language, { en: 'Trend', ja: 'トレンド', th: 'แนวโน้ม', vi: 'Xu hướng' })} {item.trend_status}</span>
                            {item.price_as_of && (
                              <span className={`intel-chip ${item.price_stale ? 'intel-chip-warn' : 'intel-chip-live'}`}>
                                {priceAsOfLabel} {formatIntelTimestamp(item.price_as_of, language)}
                              </span>
                            )}
                            {item.price_source && (
                              <span className="intel-chip">
                                {tr(language, { en: 'Quote source', ja: 'クォートソース', th: 'แหล่งราคา', vi: 'Nguồn báo giá' })} {item.price_source === 'alpha_vantage_time_series_intraday' ? 'Alpha Vantage Intraday' : 'Alpha Vantage Daily'}
                              </span>
                            )}
                            {analysis.as_of && (
                              <span className="intel-chip">{tr(language, { en: 'Analysis as of', ja: '分析時点', th: 'วิเคราะห์ ณ', vi: 'Phân tích tính đến' })} {analysis.as_of}</span>
                            )}
                          </div>

                          <div className="intel-stock-metrics-grid">
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { en: '5d return', ja: '5日リターン', th: 'ผลตอบแทน 5 วัน', vi: 'Lợi suất 5 ngày' })}</span>
                              <strong>{formatIntelNumber(analysis.return_5d_pct)}%</strong>
                            </div>
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { en: '20d return', ja: '20日リターン', th: 'ผลตอบแทน 20 วัน', vi: 'Lợi suất 20 ngày' })}</span>
                              <strong>{formatIntelNumber(analysis.return_20d_pct)}%</strong>
                            </div>
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { en: 'To support', ja: 'サポートまで', th: 'ถึงแนวรับ', vi: 'Đến hỗ trợ' })}</span>
                              <strong>{formatIntelNumber(analysis.distance_to_support_pct)}%</strong>
                            </div>
                            <div className="intel-stock-metric-card">
                              <span>{tr(language, { en: 'To resistance', ja: 'レジスタンスまで', th: 'ถึงแนวต้าน', vi: 'Đến kháng cự' })}</span>
                              <strong>{formatIntelNumber(analysis.distance_to_resistance_pct)}%</strong>
                            </div>
                          </div>

                          <div className="intel-stock-levels-grid">
                            <div className="intel-stock-levels-card">
                              <div className="intel-stock-levels-title">{tr(language, { en: 'Moving averages', ja: '移動平均', th: 'ค่าเฉลี่ยเคลื่อนที่', vi: 'Đường trung bình động' })}</div>
                              <div className="intel-stock-levels-list">
                                <span className="intel-chip">MA5 {formatIntelNumber(movingAverages.ma5)}</span>
                                <span className="intel-chip">MA10 {formatIntelNumber(movingAverages.ma10)}</span>
                                <span className="intel-chip">MA20 {formatIntelNumber(movingAverages.ma20)}</span>
                                <span className="intel-chip">MA60 {formatIntelNumber(movingAverages.ma60)}</span>
                              </div>
                            </div>
                            <div className="intel-stock-levels-card">
                              <div className="intel-stock-levels-title">{tr(language, { en: 'Key levels', ja: '主要レベル', th: 'ระดับสำคัญ', vi: 'Mức quan trọng' })}</div>
                              <div className="intel-stock-levels-list">
                                {supportLevels.slice(0, 2).map((level: number, index: number) => (
                                  <span key={`${item.symbol}-support-${index}`} className="intel-chip">
                                    {tr(language, { en: 'Support', ja: 'サポート', th: 'แนวรับ', vi: 'Hỗ trợ' })} {formatIntelNumber(level)}
                                  </span>
                                ))}
                                {resistanceLevels.slice(0, 2).map((level: number, index: number) => (
                                  <span key={`${item.symbol}-resistance-${index}`} className="intel-chip">
                                    {tr(language, { en: 'Resistance', ja: 'レジスタンス', th: 'แนวต้าน', vi: 'Kháng cự' })} {formatIntelNumber(level)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>

                          <div className="intel-factors-grid">
                            <div className="intel-factor-card">
                              <div className="intel-factor-title">{tr(language, { en: 'Bullish factors', ja: '強気要因', th: 'ปัจจัยบวก', vi: 'Yếu tố tăng giá' })}</div>
                              {bullishFactors.length > 0 ? (
                                <ul className="intel-factor-list">
                                  {bullishFactors.map((factor: string) => (
                                    <li key={`${item.symbol}-bullish-${factor}`}>{factor}</li>
                                  ))}
                                </ul>
                              ) : (
                                <div className="intel-empty-inline">{tr(language, { en: 'No clear bullish factors.', ja: '明確な強気要因はありません。', th: 'ยังไม่มีปัจจัยบวกชัดเจน', vi: 'Chưa có yếu tố tăng giá rõ ràng.' })}</div>
                              )}
                            </div>
                            <div className="intel-factor-card intel-factor-card-risk">
                              <div className="intel-factor-title">{tr(language, { en: 'Risk factors', ja: 'リスク要因', th: 'ปัจจัยเสี่ยง', vi: 'Yếu tố rủi ro' })}</div>
                              {riskFactors.length > 0 ? (
                                <ul className="intel-factor-list">
                                  {riskFactors.map((factor: string) => (
                                    <li key={`${item.symbol}-risk-${factor}`}>{factor}</li>
                                  ))}
                                </ul>
                              ) : (
                                <div className="intel-empty-inline">{tr(language, { en: 'No clear risk factors.', ja: '明確なリスク要因はありません。', th: 'ยังไม่มีปัจจัยเสี่ยงชัดเจน', vi: 'Chưa có yếu tố rủi ro rõ ràng.' })}</div>
                              )}
                            </div>
                          </div>

                          <button
                            type="button"
                            className="intel-history-toggle"
                            onClick={() => toggleStockHistory(item.symbol)}
                          >
                            {expandedStockHistory[item.symbol]
                              ? (tr(language, { en: 'Hide history', ja: '履歴を隠す', th: 'ซ่อนประวัติ', vi: 'Ẩn lịch sử' }))
                              : (tr(language, { en: 'Show history', ja: '履歴を表示', th: 'แสดงประวัติ', vi: 'Hiện lịch sử' }))}
                          </button>
                          {expandedStockHistory[item.symbol] && (
                            <div className="intel-history-panel">
                              {loadingStockHistory[item.symbol] ? (
                                <div className="intel-empty-inline">
                                  {tr(language, { en: 'Loading history snapshots...', ja: '履歴スナップショットを読み込み中...', th: 'กำลังโหลดสแนปช็อตประวัติ...', vi: 'Đang tải snapshot lịch sử...' })}
                                </div>
                              ) : (stockHistoryBySymbol[item.symbol] || []).length > 0 ? (
                                <div className="intel-history-list">
                                  {(stockHistoryBySymbol[item.symbol] || []).map((entry: any) => (
                                    <div key={entry.analysis_id} className="intel-history-item">
                                      <div className="intel-history-item-header">
                                        <span>{formatIntelTimestamp(entry.created_at, language)}</span>
                                        <span className={`intel-activity-badge ${entry.trend_status || 'quiet'}`}>{entry.signal}</span>
                                      </div>
                                      <div className="intel-chip-row">
                                        <span className="intel-chip">{tr(language, { en: 'Score', ja: 'スコア', th: 'คะแนน', vi: 'Điểm' })} {entry.signal_score}</span>
                                        <span className="intel-chip">{tr(language, { en: 'Trend', ja: 'トレンド', th: 'แนวโน้ม', vi: 'Xu hướng' })} {entry.trend_status}</span>
                                        {entry.analysis?.return_5d_pct !== undefined && (
                                          <span className="intel-chip">{tr(language, { en: '5d return', ja: '5日リターン', th: 'ผลตอบแทน 5 วัน', vi: 'Lợi suất 5 ngày' })} {formatIntelNumber(entry.analysis?.return_5d_pct)}%</span>
                                        )}
                                        {entry.analysis?.return_20d_pct !== undefined && (
                                          <span className="intel-chip">{tr(language, { en: '20d return', ja: '20日リターン', th: 'ผลตอบแทน 20 วัน', vi: 'Lợi suất 20 ngày' })} {formatIntelNumber(entry.analysis?.return_20d_pct)}%</span>
                                        )}
                                      </div>
                                      <div className="intel-news-item-summary">{entry.summary}</div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="intel-empty-inline">
                                  {tr(language, { en: 'No historical snapshots yet.', ja: '履歴スナップショットはまだありません。', th: 'ยังไม่มีสแนปช็อตประวัติ', vi: 'Chưa có snapshot lịch sử.' })}
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
                        {currentCategory.summary?.activity_level || (tr(language, { en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A' }))}
                      </div>
                    </div>

                    <div className="intel-news-card-meta">
                      <span>{tr(language, { en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối' })}: {formatIntelTimestamp(currentCategory.created_at, language)}</span>
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
                              ? (tr(language, { en: 'Latest News', ja: '最新ニュース', th: 'ข่าวล่าสุด', vi: 'Tin mới nhất' }))
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
                                    <span className="intel-chip">{item.overall_sentiment_label}</span>
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
                                {tr(language, { en: '← Prev', ja: '← 前へ', th: '← ก่อนหน้า', vi: '← Trước' })}
                              </button>
                              <div className="intel-pager-status">
                                {tr(language, { en: `Page ${currentPage + 1} / ${totalPages}`, ja: `ページ ${currentPage + 1} / ${totalPages}`, th: `หน้า ${currentPage + 1} / ${totalPages}`, vi: `Trang ${currentPage + 1} / ${totalPages}` })}
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
                                {tr(language, { en: 'Next →', ja: '次へ →', th: 'ถัดไป →', vi: 'Tiếp →' })}
                              </button>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="intel-empty-inline">
                          {tr(language, { en: 'No snapshot content available for this category yet.', ja: 'このカテゴリのスナップショットコンテンツはまだありません。', th: 'ยังไม่มีเนื้อหาสแนปช็อตสำหรับหมวดนี้', vi: 'Chưa có nội dung snapshot cho danh mục này.' })}
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
                        <div className="intel-news-title">{tr(language, { en: 'Macro Signals', ja: 'マクロシグナル', th: 'สัญญาณมหภาค', vi: 'Tín hiệu vĩ mô' })}</div>
                        <div className="intel-news-description">
                          {macro?.meta?.summary || tr(language, { en: 'A server-side macro regime snapshot.', ja: 'サーバー側のマクロレジームスナップショット。', th: 'สแนปช็อตระบอบมหภาคจากเซิร์ฟเวอร์', vi: 'Ảnh chụp chế độ vĩ mô phía máy chủ.' })}
                        </div>
                      </div>
                      <div className={`intel-activity-badge ${macro?.verdict || 'quiet'}`}>
                        {macro?.verdict || (tr(language, { en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A' }))}
                      </div>
                    </div>
                    <div className="intel-news-card-meta">
                      <span>{tr(language, { en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối' })}: {formatIntelTimestamp(macro?.created_at, language)}</span>
                    </div>
                    <div className="intel-macro-list">
                      {(macro?.signals || []).map((signal: any) => (
                        <div key={signal.id} className="intel-macro-row">
                          <div className="intel-macro-row-top">
                            <span className="intel-macro-label">{signal.label}</span>
                            <span className={`intel-activity-badge ${signal.status || 'quiet'}`}>{signal.status}</span>
                          </div>
                          <div className="intel-macro-row-value">
                            {signal.value !== null && signal.value !== undefined
                              ? `${signal.value}${signal.unit === '%' ? '%' : ''}`
                              : (tr(language, { en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A' }))}
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
                        <div className="intel-news-title">{tr(language, { en: 'ETF Flow', ja: 'ETFフロー', th: 'กระแสเงิน ETF', vi: 'Dòng tiền ETF' })}</div>
                      </div>
                      <div className={`intel-activity-badge ${etfFlows?.summary?.direction || 'quiet'}`}>
                        {etfFlows?.summary?.direction || (tr(language, { en: 'N/A', ja: 'N/A', th: 'N/A', vi: 'N/A' }))}
                      </div>
                    </div>
                    <div className="intel-news-card-meta">
                      <span>{tr(language, { en: 'Last update', ja: '最終更新', th: 'อัปเดตล่าสุด', vi: 'Cập nhật cuối' })}: {formatIntelTimestamp(etfFlows?.created_at, language)}</span>
                    </div>
                    <div className="intel-etf-stack">
                      {(etfFlows?.etfs || []).slice(0, 8).map((etf: any) => (
                        <div key={etf.symbol} className="intel-etf-stack-item">
                          <div className="intel-etf-stack-top">
                            <div className="intel-etf-symbol">{etf.symbol}</div>
                            <div className={`intel-activity-badge ${etf.direction || 'quiet'}`}>{etf.direction}</div>
                          </div>
                          <div className="intel-etf-stack-metrics">
                            <div className="intel-etf-metric">
                              <span>{tr(language, { en: 'Change', ja: '変動', th: 'เปลี่ยนแปลง', vi: 'Thay đổi' })}</span>
                              <strong>{etf.price_change_pct}%</strong>
                            </div>
                            <div className="intel-etf-metric">
                              <span>{tr(language, { en: 'Vol ratio', ja: '出来高比率', th: 'อัตราส่วนปริมาณ', vi: 'Tỷ lệ khối lượng' })}</span>
                              <strong>{etf.volume_ratio}</strong>
                            </div>
                            <div className="intel-etf-metric">
                              <span>{tr(language, { en: 'Flow score', ja: 'フロースコア', th: 'คะแนนกระแส', vi: 'Điểm dòng tiền' })}</span>
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
