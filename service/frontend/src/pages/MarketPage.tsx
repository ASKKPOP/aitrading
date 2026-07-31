import { BybitMarketsTable } from '../components/BybitMarketsTable'
import { MarketMovers, OrderBookBlock, PopularCryptoGrid, TickerTape, useLiveTickers } from '../components/LiveMarketBlocks'
import SignalsFeed from './SignalsFeed'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

interface Props {
  token?: string | null
}

function Divider({ label }: { label: string }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      margin: '28px 0 20px',
      color: 'var(--text-muted)',
      fontSize: 12,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      <div style={{ flex: 1, height: 1, background: 'var(--border-color)' }} />
      {label}
      <div style={{ flex: 1, height: 1, background: 'var(--border-color)' }} />
    </div>
  )
}

export function MarketPage({ token }: Props) {
  const { language } = useLanguage()
  const ticks = useLiveTickers()
  return (
    <div className="page-container">
      <TickerTape ticks={ticks} />
      <MarketMovers ticks={ticks} />

      {/* Order book beside the popular grid on wide screens, stacked on mobile. */}
      <style>{`
        .mkt-live-row { display: grid; gap: 16px; grid-template-columns: minmax(320px, 420px) 1fr; align-items: start; }
        @media (max-width: 860px) { .mkt-live-row { grid-template-columns: 1fr; } }
      `}</style>
      <div className="mkt-live-row">
        <div>
          <Divider label={tr(language, { ko: '실시간 오더북', en: 'Live order book', ja: 'リアルタイム板情報', th: 'ออร์เดอร์บุ๊กสด', vi: 'Sổ lệnh trực tiếp', id: 'Order book langsung' })} />
          <OrderBookBlock tick={ticks['BTCUSDT']} />
        </div>
        <div>
          <Divider label={tr(language, { ko: '인기 암호화폐', en: 'Popular cryptocurrencies', ja: '人気の暗号資産', th: 'คริปโตยอดนิยม', vi: 'Tiền mã hóa phổ biến', id: 'Kripto populer' })} />
          <PopularCryptoGrid ticks={ticks} />
        </div>
      </div>

      <Divider label={tr(language, { ko: '암호화폐 선물 시장', en: 'Crypto Futures Markets', ja: '暗号資産先物マーケット', th: 'ตลาดฟิวเจอร์สคริปโต', vi: 'Thị trường phái sinh Crypto', id: 'Pasar futures kripto' })} />
      <BybitMarketsTable />

      <Divider label={tr(language, { ko: '에이전트 시그널', en: 'Agent Signals', ja: 'エージェントシグナル', th: 'สัญญาณเอเจนต์', vi: 'Tín hiệu Agent', id: 'Sinyal agen' })} />
      <SignalsFeed token={token} />
    </div>
  )
}

export default MarketPage
