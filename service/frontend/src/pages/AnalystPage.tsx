import { useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// AI Analyst — runs the multi-agent analysis engine (Target 2):
// News + Sentiment + Fundamentals/Macro + Technical -> Trader/Risk -> decision + report.
export function AnalystPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [symbol, setSymbol] = useState('BTC')
  const [market, setMarket] = useState('crypto')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')

  const T = {
    title: tr(language, { en: 'AI Analyst', ja: 'AIアナリスト', th: 'นักวิเคราะห์ AI', vi: 'Nhà phân tích AI' }),
    subtitle: tr(language, { en: 'Four AI analysts debate a decision + report', ja: '4人のAIアナリストが討議', th: 'นักวิเคราะห์ AI สี่คนถกเถียงเพื่อสรุปการตัดสินใจ', vi: 'Bốn nhà phân tích AI tranh luận' }),
    symbol: tr(language, { en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' }),
    market: tr(language, { en: 'Market', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    run: tr(language, { en: 'Run analysis', ja: '分析する', th: 'วิเคราะห์', vi: 'Phân tích' }),
    running: tr(language, { en: 'Analysts are debating…', ja: '分析中…', th: 'กำลังวิเคราะห์…', vi: 'Đang phân tích…' }),
    decision: tr(language, { en: 'Decision', ja: '判断', th: 'การตัดสินใจ', vi: 'Quyết định' }),
    confidence: tr(language, { en: 'Confidence', ja: '信頼度', th: 'ความมั่นใจ', vi: 'Độ tin cậy' }),
    report: tr(language, { en: 'Report', ja: 'レポート', th: 'รายงาน', vi: 'Báo cáo' }),
    analysts: tr(language, { en: 'Analyst briefs', ja: 'アナリスト概要', th: 'สรุปนักวิเคราะห์', vi: 'Tóm tắt phân tích' }),
    login: tr(language, { en: 'Please log in to run analysis.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
    provider: tr(language, { en: 'AI provider', ja: 'AIプロバイダー', th: 'ผู้ให้บริการ AI', vi: 'Nhà cung cấp AI' }),
    none: tr(language, { en: 'deterministic (no LLM key set)', ja: 'LLM未設定', th: 'ไม่ได้ตั้งค่า LLM', vi: 'chưa đặt LLM' }),
    disclaimer: tr(language, { en: 'Research only — not financial advice. All trades are simulated.', ja: '調査目的のみ。', th: 'เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน', vi: 'Chỉ nghiên cứu — không phải lời khuyên đầu tư.' }),
  }
  const roleLabels: Record<string, string> = {
    news: tr(language, { en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức' }),
    sentiment: tr(language, { en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý' }),
    fundamentals_macro: tr(language, { en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô' }),
    technical: tr(language, { en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật' }),
  }

  async function run() {
    if (!token) return
    setLoading(true); setError(''); setResult(null)
    try {
      const res = await fetch(`${API_BASE}/analysis/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ symbol, market, lang: language }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Analysis failed')
      setResult(data)
    } catch (e: any) { setError(e.message || 'Analysis failed') }
    setLoading(false)
  }

  const decisionColor = (a?: string) => a === 'buy' ? '#3fb950' : a === 'sell' ? '#f0663f' : '#e3a008'

  if (!token) {
    return (
      <div>
        <div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
        <div className="empty-state"><div className="empty-icon">🧠</div><div className="empty-title">{T.login}</div></div>
      </div>
    )
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
      </div>

      <div className="card" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 18 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
          {T.symbol}
          <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
            style={{ padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-input,#fff)', color: 'inherit', width: 120 }} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
          {T.market}
          <select value={market} onChange={e => setMarket(e.target.value)}
            style={{ padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border,#d3c8b6)', background: 'var(--bg-input,#fff)', color: 'inherit' }}>
            <option value="crypto">crypto</option>
            <option value="us-stock">us-stock</option>
          </select>
        </label>
        <button onClick={run} disabled={loading}
          style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.6 : 1 }}>
          {loading ? T.running : T.run}
        </button>
      </div>

      {error && <div className="card" style={{ borderColor: '#f0663f', color: '#f0663f', marginBottom: 18 }}>⚠️ {error}</div>}

      {result && (
        <>
          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 26, fontWeight: 800, textTransform: 'uppercase', color: decisionColor(result.decision?.action) }}>
                {result.decision?.action}
              </div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{result.symbol} · {result.market}</div>
              <div style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>
                {T.confidence}: <b>{Math.round((result.decision?.confidence ?? 0) * 100)}%</b> · {T.provider}: {result.llm_provider || T.none}
              </div>
            </div>
            {result.decision?.report && (
              <p style={{ marginTop: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{result.decision.report}</p>
            )}
          </div>

          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '0 0 10px' }}>{T.analysts}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 14 }}>
            {result.analysts && Object.entries(result.analysts).map(([role, v]: any) => (
              <div key={role} className="card">
                <div style={{ fontWeight: 700, marginBottom: 6 }}>{roleLabels[role] || role}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--text-secondary,#5f574c)', whiteSpace: 'pre-wrap' }}>{v.brief}</div>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ marginTop: 24, fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>{T.disclaimer}</div>
    </div>
  )
}

export default AnalystPage
