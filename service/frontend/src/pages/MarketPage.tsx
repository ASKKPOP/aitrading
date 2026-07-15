import { BybitMarketsTable } from '../components/BybitMarketsTable'
import SignalsFeed from './SignalsFeed'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

interface Props {
  token?: string | null
}

export function MarketPage({ token }: Props) {
  const { language } = useLanguage()
  return (
    <div className="page-container">
      <BybitMarketsTable />

      {/* Divider */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        marginBottom: 24,
        color: 'var(--text-muted)',
        fontSize: 12,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        {tr(language, { ko: '에이전트 시그널', en: 'Agent Signals', ja: 'エージェントシグナル', th: 'สัญญาณเอเจนต์', vi: 'Tín hiệu Agent' })}
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <SignalsFeed token={token} />
    </div>
  )
}

export default MarketPage
