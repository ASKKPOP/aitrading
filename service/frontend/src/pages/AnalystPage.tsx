import { useEffect, useState } from 'react'
import { useLanguage } from '../appShared'
import { AnalysisMonitorPanel, useAnalysisRun } from '../components/AnalysisPipelineViz'
import { SymbolSelect } from '../components/SymbolSelect'
import { tr } from '../i18n'

// AI Analyst — runs the multi-agent analysis engine (Target 2):
// News + Sentiment + Fundamentals/Macro + Technical -> Trader/Risk -> decision + report.
// The run executes server-side (background job) and per-step progress feeds a
// live WebGL2 pipeline monitor — leaving the page and coming back re-attaches.
export function AnalystPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [symbol, setSymbol] = useState('BTC')
  const [market, setMarket] = useState('crypto')
  const { loading, result, error, steps, log, runInfo, run: runStream } = useAnalysisRun(token)

  // Re-attached to an existing job (e.g. returning mid-run): mirror its
  // symbol/market in the controls so the monitor matches what they show.
  useEffect(() => {
    if (runInfo) { setSymbol(runInfo.symbol); setMarket(runInfo.market) }
  }, [runInfo?.id])

  const T = {
    title: tr(language, { ko: 'AI 애널리스트', en: 'AI Analyst', ja: 'AIアナリスト', th: 'นักวิเคราะห์ AI', vi: 'Nhà phân tích AI' }),
    subtitle: tr(language, { ko: '네 명의 AI 애널리스트가 결정과 리포트를 두고 토론합니다', en: 'Four AI analysts debate a decision + report', ja: '4人のAIアナリストが討議', th: 'นักวิเคราะห์ AI สี่คนถกเถียงเพื่อสรุปการตัดสินใจ', vi: 'Bốn nhà phân tích AI tranh luận' }),
    symbol: tr(language, { ko: '종목', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' }),
    market: tr(language, { ko: '시장', en: 'Market', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    run: tr(language, { ko: '분석 실행', en: 'Run analysis', ja: '分析する', th: 'วิเคราะห์', vi: 'Phân tích' }),
    running: tr(language, { ko: '애널리스트들이 토론 중…', en: 'Analysts are debating…', ja: '分析中…', th: 'กำลังวิเคราะห์…', vi: 'Đang phân tích…' }),
    decision: tr(language, { ko: '결정', en: 'Decision', ja: '判断', th: 'การตัดสินใจ', vi: 'Quyết định' }),
    confidence: tr(language, { ko: '신뢰도', en: 'Confidence', ja: '信頼度', th: 'ความมั่นใจ', vi: 'Độ tin cậy' }),
    report: tr(language, { ko: '리포트', en: 'Report', ja: 'レポート', th: 'รายงาน', vi: 'Báo cáo' }),
    analysts: tr(language, { ko: '애널리스트 브리프', en: 'Analyst briefs', ja: 'アナリスト概要', th: 'สรุปนักวิเคราะห์', vi: 'Tóm tắt phân tích' }),
    login: tr(language, { ko: '분석을 실행하려면 로그인하세요.', en: 'Please log in to run analysis.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
    provider: tr(language, { ko: 'AI 제공자', en: 'AI provider', ja: 'AIプロバイダー', th: 'ผู้ให้บริการ AI', vi: 'Nhà cung cấp AI' }),
    none: tr(language, { ko: '결정론적 (LLM 키 미설정)', en: 'deterministic (no LLM key set)', ja: 'LLM未設定', th: 'ไม่ได้ตั้งค่า LLM', vi: 'chưa đặt LLM' }),
    disclaimer: tr(language, { ko: '리서치 목적일 뿐 — 투자 자문이 아닙니다. 모든 거래는 모의입니다.', en: 'Research only — not financial advice. All trades are simulated.', ja: '調査目的のみ。', th: 'เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน', vi: 'Chỉ nghiên cứu — không phải lời khuyên đầu tư.' }),
  }
  const roleLabels: Record<string, string> = {
    news: tr(language, { ko: '뉴스', en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức' }),
    sentiment: tr(language, { ko: '심리', en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý' }),
    fundamentals_macro: tr(language, { ko: '펀더멘털 & 매크로', en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô' }),
    technical: tr(language, { ko: '기술적 분석', en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật' }),
  }

  function run() { runStream(symbol, market, language) }

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
          <SymbolSelect market={market} value={symbol} onChange={setSymbol}
            style={{ padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', width: 140 }} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
          {T.market}
          <select value={market} onChange={e => setMarket(e.target.value)}
            style={{ padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)' }}>
            <option value="crypto">crypto</option>
            <option value="us-stock">us-stock</option>
          </select>
        </label>
        <button onClick={run} disabled={loading}
          style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.6 : 1 }}>
          {loading ? T.running : T.run}
        </button>
      </div>

      {log.length > 0 && (
        <div className="card" style={{ marginBottom: 18 }}>
          <AnalysisMonitorPanel language={language} steps={steps} log={log} />
        </div>
      )}

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
