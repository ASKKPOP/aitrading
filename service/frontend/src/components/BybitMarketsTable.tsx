import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

interface BybitTicker {
  symbol: string
  last_price: string
  mark_price: string
  price_24h_pct: string
  volume_24h: string
  open_interest: string
}

const REFRESH_MS = 10_000

function fmtPrice(p: string): string {
  const n = parseFloat(p)
  if (isNaN(n)) return '—'
  if (n >= 10_000) return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (n >= 1) return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return n.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 })
}

function fmtVolume(v: string): string {
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function PctCell({ pct }: { pct: string }) {
  const val = parseFloat(pct)
  const positive = val >= 0
  return (
    <span style={{
      color: positive ? 'var(--success)' : 'var(--error)',
      fontWeight: 500,
      fontVariantNumeric: 'tabular-nums',
    }}>
      {positive ? '+' : ''}{pct}%
    </span>
  )
}

function SkeletonRow() {
  return (
    <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
      {[1, 2, 3, 4, 5].map(i => (
        <td key={i} style={{ padding: '12px 16px' }}>
          <div style={{
            height: 14,
            borderRadius: 4,
            background: 'var(--bg-tertiary)',
            width: i === 1 ? 80 : i === 4 ? 90 : 60,
            animation: 'pulse 1.4s ease-in-out infinite',
          }} />
        </td>
      ))}
    </tr>
  )
}

export function BybitMarketsTable() {
  const { language } = useLanguage()
  const [tickers, setTickers] = useState<BybitTicker[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/markets/crypto/tickers`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setTickers(data.tickers ?? [])
      setError(null)
    } catch (e: any) {
      setError(tr(language, { ko: '실시간 가격을 불러올 수 없습니다', en: 'Unable to load live prices', ja: 'リアルタイム価格を読み込めません', th: 'ไม่สามารถโหลดราคาสดได้', vi: 'Không thể tải giá trực tiếp' }))
    } finally {
      setLoading(false)
    }
  }, [language])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  const handleTrade = (symbol: string) => {
    navigate(`/trade?symbol=${symbol}`)
  }

  return (
    <div style={{ marginBottom: 32 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>
            {tr(language, { ko: '암호화폐 선물 시장', en: 'Crypto Futures Markets', ja: '暗号資産先物マーケット', th: 'ตลาดฟิวเจอร์สคริปโต', vi: 'Thị trường phái sinh Crypto' })}
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
            {tr(language, { ko: '상위 20개 USDT 마진 무기한 선물 · OKX 실시간 가격', en: 'Top 20 USDT-margined perpetuals · Live prices via OKX', ja: 'USDT証拠金無期限先物トップ20 · OKXによるリアルタイム価格', th: 'สัญญาถาวรมาร์จิน USDT 20 อันดับแรก · ราคาสดผ่าน OKX', vi: 'Top 20 hợp đồng vĩnh cửu ký quỹ USDT · Giá trực tiếp qua OKX' })}
          </p>
        </div>
        {!loading && !error && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
            {tr(language, { ko: '실시간', en: 'Live', ja: 'ライブ', th: 'สด', vi: 'Trực tiếp' })}
          </span>
        )}
      </div>

      {error && (
        <div style={{
          padding: '12px 16px',
          background: 'rgba(var(--error-rgb, 220,53,69), 0.1)',
          border: '1px solid var(--error)',
          borderRadius: 8,
          color: 'var(--error)',
          fontSize: 13,
          marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid var(--border-color)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)' }}>
              {[tr(language, { ko: '종목', en: 'Symbol', ja: '銘柄', th: 'สัญลักษณ์', vi: 'Mã' }), tr(language, { ko: '현재가', en: 'Last Price', ja: '現在価格', th: 'ราคาล่าสุด', vi: 'Giá cuối' }), tr(language, { ko: '24시간 변동', en: '24h Change', ja: '24時間変動', th: 'เปลี่ยนแปลง 24 ชม.', vi: 'Thay đổi 24h' }), tr(language, { ko: '24시간 거래량', en: 'Volume 24h', ja: '24時間出来高', th: 'ปริมาณ 24 ชม.', vi: 'Khối lượng 24h' }), ''].map((h, i) => (
                <th key={h || i} style={{
                  padding: '10px 16px',
                  textAlign: i === 4 ? 'right' : 'left',
                  fontWeight: 600,
                  fontSize: 11,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-secondary)',
                  whiteSpace: 'nowrap',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }, (_, i) => <SkeletonRow key={i} />)
              : tickers.map(ticker => (
                <tr
                  key={ticker.symbol}
                  style={{ borderBottom: '1px solid var(--border-color)', transition: 'background 0.15s' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-secondary)')}
                  onMouseLeave={e => (e.currentTarget.style.background = '')}
                >
                  {/* Symbol */}
                  <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                    {ticker.symbol.replace('USDT', '/USDT')}
                  </td>
                  {/* Last Price */}
                  <td style={{ padding: '12px 16px', fontVariantNumeric: 'tabular-nums', color: 'var(--text-primary)' }}>
                    ${fmtPrice(ticker.last_price)}
                  </td>
                  {/* 24h Change */}
                  <td style={{ padding: '12px 16px' }}>
                    <PctCell pct={ticker.price_24h_pct} />
                  </td>
                  {/* Volume */}
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
                    {fmtVolume(ticker.volume_24h)}
                  </td>
                  {/* Action */}
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <button
                      onClick={() => handleTrade(ticker.symbol)}
                      style={{
                        padding: '5px 14px',
                        borderRadius: 6,
                        border: '1px solid var(--accent-primary)',
                        background: 'transparent',
                        color: 'var(--accent-primary)',
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.background = 'var(--accent-primary)'
                        e.currentTarget.style.color = '#fff'
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.background = 'transparent'
                        e.currentTarget.style.color = 'var(--accent-primary)'
                      }}
                    >
                      {tr(language, { ko: '거래', en: 'Trade', ja: '取引', th: 'เทรด', vi: 'Giao dịch' })}
                    </button>
                  </td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 0.9; }
        }
      `}</style>
    </div>
  )
}
