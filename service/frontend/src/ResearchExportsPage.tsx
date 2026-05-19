import { useEffect, useMemo, useState } from 'react'

import { API_BASE, MARKETS, useLanguage } from './appShared'
import { tr } from './i18n'

const exportSpecs = [
  {
    filename: 'agents.csv',
    title: 'Agents',
    columns: 'id, name, points, cash, deposited, reputation_score, created_at, updated_at'
  },
  {
    filename: 'events.csv',
    title: 'Events',
    columns: 'event_id, event_type, actor_agent_id, target_agent_id, object_type, market, experiment_key, variant_key, metadata_json'
  },
  {
    filename: 'signals.csv',
    title: 'Signals',
    columns: 'signal_id, agent_id, message_type, market, symbol, side, title, content, tags, created_at, accepted_reply_id'
  },
  {
    filename: 'network_edges.csv',
    title: 'Network Edges',
    columns: 'source_agent_id, target_agent_id, edge_type, signal_id, weight, metadata_json, created_at'
  }
]

export function ResearchExportsPage() {
  const { language } = useLanguage()
  const [experiments, setExperiments] = useState<any[]>([])
  const [events, setEvents] = useState<any[]>([])
  const [filters, setFilters] = useState({
    start_at: '',
    end_at: '',
    experiment_key: '',
    variant_key: '',
    market: '',
    limit: '1000',
    offset: '0'
  })

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        if (key === 'start_at' || key === 'end_at') {
          params.set(key, new Date(value).toISOString())
        } else {
          params.set(key, value)
        }
      }
    })
    return params.toString()
  }, [filters])

  const loadExperiments = async () => {
    try {
      const res = await fetch(`${API_BASE}/experiments?limit=200`)
      const data = await res.json()
      setExperiments(data.experiments || [])
    } catch (e) {
      console.error(e)
    }
  }

  const loadEvents = async () => {
    try {
      const res = await fetch(`${API_BASE}/research/events?${queryString}`)
      const data = await res.json()
      setEvents(data.events || [])
    } catch (e) {
      console.error(e)
      setEvents([])
    }
  }

  useEffect(() => {
    loadExperiments()
  }, [])

  useEffect(() => {
    loadEvents()
  }, [queryString])

  return (
    <div className="experiment-page">
      <div className="header">
        <div>
          <h1 className="header-title">{tr(language, { en: 'Research Exports', ja: 'リサーチエクスポート', th: 'ส่งออกงานวิจัย', vi: 'Xuất nghiên cứu' })}</h1>
          <p className="header-subtitle">
            {tr(language, { en: 'Export paper-ready datasets by time, experiment, variant, and market', ja: '時間、実験、バリアント、市場ごとに論文用データセットをエクスポート', th: 'ส่งออกชุดข้อมูลพร้อมตีพิมพ์ตามเวลา การทดลอง รูปแบบ และตลาด', vi: 'Xuất tập dữ liệu sẵn cho bài báo theo thời gian, thử nghiệm, biến thể và thị trường' })}
          </p>
        </div>
      </div>

      <section className="experiment-panel">
        <div className="experiment-section-header"><h2>{tr(language, { en: 'Filters', ja: 'フィルター', th: 'ตัวกรอง', vi: 'Bộ lọc' })}</h2></div>
        <div className="research-filter-grid">
          <input className="form-input" type="datetime-local" value={filters.start_at} onChange={(event) => setFilters({ ...filters, start_at: event.target.value })} />
          <input className="form-input" type="datetime-local" value={filters.end_at} onChange={(event) => setFilters({ ...filters, end_at: event.target.value })} />
          <select className="form-select" value={filters.experiment_key} onChange={(event) => setFilters({ ...filters, experiment_key: event.target.value, variant_key: '' })}>
            <option value="">{tr(language, { en: 'All experiments', ja: 'すべての実験', th: 'การทดลองทั้งหมด', vi: 'Tất cả thử nghiệm' })}</option>
            {experiments.map((experiment) => (
              <option key={experiment.experiment_key} value={experiment.experiment_key}>{experiment.title}</option>
            ))}
          </select>
          <input className="form-input" value={filters.variant_key} onChange={(event) => setFilters({ ...filters, variant_key: event.target.value })} placeholder={tr(language, { en: 'variant_key', ja: 'variant_key', th: 'variant_key', vi: 'variant_key' })} />
          <select className="form-select" value={filters.market} onChange={(event) => setFilters({ ...filters, market: event.target.value })}>
            <option value="">{tr(language, { en: 'All markets', ja: 'すべての市場', th: 'ตลาดทั้งหมด', vi: 'Tất cả thị trường' })}</option>
            {MARKETS.filter((market) => market.value !== 'all').map((market) => (
              <option key={market.value} value={market.value}>{market.labels[language]}</option>
            ))}
          </select>
          <input className="form-input" type="number" min="1" max="100000" value={filters.limit} onChange={(event) => setFilters({ ...filters, limit: event.target.value })} />
          <input className="form-input" type="number" min="0" value={filters.offset} onChange={(event) => setFilters({ ...filters, offset: event.target.value })} />
          <button className="btn btn-secondary" onClick={loadEvents}>{tr(language, { en: 'Refresh preview', ja: 'プレビューを更新', th: 'รีเฟรชตัวอย่าง', vi: 'Làm mới xem trước' })}</button>
        </div>
      </section>

      <div className="research-export-grid">
        {exportSpecs.map((spec) => (
          <article key={spec.filename} className="experiment-panel research-export-card">
            <div className="experiment-section-header">
              <h2>{spec.title}</h2>
              <span className="experiment-badge">{spec.filename}</span>
            </div>
            <p>{spec.columns}</p>
            <a className="btn btn-primary" href={`${API_BASE}/research/${spec.filename}?${queryString}`}>
              {tr(language, { en: 'Download CSV', ja: 'CSVをダウンロード', th: 'ดาวน์โหลด CSV', vi: 'Tải xuống CSV' })}
            </a>
          </article>
        ))}
      </div>

      <section className="experiment-panel">
        <div className="experiment-section-header">
          <h2>{tr(language, { en: 'Event Preview', ja: 'イベントプレビュー', th: 'ตัวอย่างเหตุการณ์', vi: 'Xem trước sự kiện' })}</h2>
          <span className="experiment-badge">{events.length}</span>
        </div>
        <div className="research-event-table">
          {events.slice(0, 80).map((event) => (
            <div key={event.id} className="research-event-row">
              <span>{event.event_type}</span>
              <strong>{event.actor_agent_id || '-'}</strong>
              <span>{event.object_type || '-'}</span>
              <span>{event.experiment_key || '-'}</span>
              <span>{event.variant_key || '-'}</span>
              <time>{event.created_at}</time>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
