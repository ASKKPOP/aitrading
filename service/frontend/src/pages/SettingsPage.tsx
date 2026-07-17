import { useEffect, useState } from 'react'

import { Link } from 'react-router-dom'

import { API_BASE, useLanguage } from '../appShared'
import { LANGUAGES, tr } from '../i18n'

type ApiTarget = {
  target: string
  label: string
  description: string
  requires_key: boolean
  fields: string[]
  configured: boolean
  enabled: boolean
  masked_key: string | null
  config: Record<string, string>
  updated_at: string | null
}

const LLM_PROVIDERS = ['openai', 'gemini', 'grok', 'qwen', 'glm', 'openrouter', 'anthropic', 'local']

// Per-provider model choices. First entry mirrors the server default in
// llm_client.py; the '__custom__' option opens a free-text field so new
// model ids never require a release.
const MODEL_OPTIONS: Record<string, string[]> = {
  openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1', 'gpt-4.1-mini', 'o3-mini'],
  gemini: ['gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-pro'],
  grok: ['grok-2-latest', 'grok-3', 'grok-3-mini'],
  qwen: ['qwen-plus', 'qwen-max', 'qwen-turbo'],
  glm: ['glm-4-plus', 'glm-4-flash', 'glm-4-air'],
  openrouter: ['openai/gpt-4o-mini', 'anthropic/claude-sonnet-4.5', 'openai/gpt-4o', 'google/gemini-2.0-flash', 'meta-llama/llama-3.1-70b-instruct'],
  anthropic: ['claude-3-5-sonnet-latest', 'claude-sonnet-5', 'claude-opus-4-8', 'claude-haiku-4-5'],
  local: ['llama3.1', 'qwen2.5', 'mistral', 'deepseek-r1'],
}

export default function SettingsPage({ userToken, userInfo, onSignOut }: {
  userToken: string
  userInfo: any
  onSignOut: () => void
}) {
  const { language, setLanguage } = useLanguage()
  const [targets, setTargets] = useState<ApiTarget[]>([])
  const [guidelines, setGuidelines] = useState('')
  const [alertPrefs, setAlertPrefs] = useState<{ email_enabled: boolean; sms_enabled: boolean; phone: string }>(
    { email_enabled: false, sms_enabled: false, phone: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savedMsg, setSavedMsg] = useState('')
  // per-target editable state
  const [drafts, setDrafts] = useState<Record<string, { api_key: string; provider: string; model: string }>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [customModel, setCustomModel] = useState<Record<string, boolean>>({})

  const auth = () => ({ 'Authorization': `Bearer ${userToken}`, 'Content-Type': 'application/json' })

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/users/settings`, { headers: auth() })
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      setTargets(data.targets || [])
      const alertsTarget = (data.targets || []).find((t: ApiTarget) => t.target === 'alerts')
      if (alertsTarget?.config) {
        setAlertPrefs({
          email_enabled: String(alertsTarget.config.email_enabled).toLowerCase() === 'true',
          sms_enabled: String(alertsTarget.config.sms_enabled).toLowerCase() === 'true',
          phone: alertsTarget.config.phone || '',
        })
      }
      setError('')
    } catch {
      setError(tr(language, { ko: '설정을 불러오지 못했습니다', en: 'Failed to load settings', ja: '設定を読み込めませんでした', th: 'โหลดการตั้งค่าไม่สำเร็จ', vi: 'Không tải được cài đặt' }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [userToken])

  useEffect(() => {
    // Personalized-mode guidelines (Plan 06 C3)
    fetch(`${API_BASE}/users/guidelines`, { headers: auth() })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setGuidelines(d.guidelines || '') })
      .catch(() => { /* transient */ })
  }, [userToken])

  const flash = (msg: string) => {
    setSavedMsg(msg)
    setTimeout(() => setSavedMsg(''), 2500)
  }

  const saveAlertPrefs = async () => {
    try {
      const res = await fetch(`${API_BASE}/users/settings/api/alerts`, {
        method: 'PUT', headers: auth(),
        body: JSON.stringify({ config: {
          email_enabled: String(alertPrefs.email_enabled),
          sms_enabled: String(alertPrefs.sms_enabled),
          phone: alertPrefs.phone,
        } }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      flash(tr(language, { ko: '알림 설정이 저장되었습니다', en: 'Alert settings saved', ja: '通知設定を保存しました', th: 'บันทึกการแจ้งเตือนแล้ว', vi: 'Đã lưu cài đặt cảnh báo' }))
    } catch {
      flash(tr(language, { ko: '저장 실패', en: 'Save failed', ja: '保存失敗', th: 'บันทึกล้มเหลว', vi: 'Lưu thất bại' }))
    }
  }

  const saveGuidelines = async () => {
    try {
      const res = await fetch(`${API_BASE}/users/guidelines`, {
        method: 'PUT', headers: auth(), body: JSON.stringify({ guidelines }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      flash(tr(language, { ko: '지침이 저장되었습니다', en: 'Guidelines saved', ja: '指針を保存しました', th: 'บันทึกแนวทางแล้ว', vi: 'Đã lưu chỉ dẫn' }))
    } catch {
      flash(tr(language, { ko: '저장 실패', en: 'Save failed', ja: '保存失敗', th: 'บันทึกล้มเหลว', vi: 'Lưu thất bại' }))
    }
  }

  const saveTarget = async (t: ApiTarget) => {
    const draft = drafts[t.target] || { api_key: '', provider: t.config.provider || '', model: t.config.model || '' }
    const body: any = {}
    if (draft.api_key) body.api_key = draft.api_key
    if (t.fields.length > 0) {
      body.config = { provider: draft.provider, model: draft.model }
    }
    setSaving(t.target)
    try {
      const res = await fetch(`${API_BASE}/users/settings/api/${t.target}`, {
        method: 'PUT', headers: auth(), body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      setDrafts(d => ({ ...d, [t.target]: { ...draft, api_key: '' } }))
      flash(tr(language, { ko: '저장되었습니다', en: 'Saved', ja: '保存しました', th: 'บันทึกแล้ว', vi: 'Đã lưu' }))
      await load()
    } catch {
      flash(tr(language, { ko: '저장에 실패했습니다', en: 'Save failed', ja: '保存に失敗', th: 'บันทึกไม่สำเร็จ', vi: 'Lưu thất bại' }))
    } finally {
      setSaving(null)
    }
  }

  const toggleTarget = async (t: ApiTarget) => {
    setSaving(t.target)
    try {
      await fetch(`${API_BASE}/users/settings/api/${t.target}`, {
        method: 'PUT', headers: auth(), body: JSON.stringify({ enabled: !t.enabled }),
      })
      await load()
    } finally {
      setSaving(null)
    }
  }

  const clearTarget = async (t: ApiTarget) => {
    setSaving(t.target)
    try {
      await fetch(`${API_BASE}/users/settings/api/${t.target}`, { method: 'DELETE', headers: auth() })
      flash(tr(language, { ko: '키가 삭제되었습니다', en: 'Key removed', ja: 'キーを削除しました', th: 'ลบคีย์แล้ว', vi: 'Đã xóa khóa' }))
      await load()
    } finally {
      setSaving(null)
    }
  }

  const draftOf = (t: ApiTarget) =>
    drafts[t.target] || { api_key: '', provider: t.config.provider || '', model: t.config.model || '' }

  const setDraft = (target: string, patch: Partial<{ api_key: string; provider: string; model: string }>) => {
    setDrafts(d => {
      const t = targets.find(x => x.target === target)
      const cur = d[target] || { api_key: '', provider: t?.config.provider || '', model: t?.config.model || '' }
      return { ...d, [target]: { ...cur, ...patch } }
    })
  }

  const sectionTitle = (m: { ko: string; en: string; ja: string; th: string; vi: string }) => (
    <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '26px 0 4px' }}>
      {tr(language, m)}
    </h2>
  )

  // Backend catalog labels/descriptions arrive in English; localize known
  // targets here and fall back to the backend text for anything new.
  const targetLabel = (t: ApiTarget) =>
    t.target === 'llm' ? tr(language, { ko: 'LLM (AI 분석)', en: 'LLM (AI analysis)', ja: 'LLM (AI分析)', th: 'LLM (วิเคราะห์ AI)', vi: 'LLM (phân tích AI)' }) : t.label
  const targetDescription = (t: ApiTarget) => {
    const m: Record<string, { ko: string; en: string; ja: string; th: string; vi: string }> = {
      llm: { ko: '4-애널리스트 분석 엔진의 제공자. 키가 없으면 결정론적 규칙 기반 엔진이 동작합니다.', en: 'Provider for the 4-analyst analysis engine. Without a key the deterministic rule-based engine runs.', ja: '4アナリスト分析エンジンのプロバイダー。キーなしでは決定論的ルールエンジンが動作。', th: 'ผู้ให้บริการเอนจินวิเคราะห์ 4 นักวิเคราะห์ ไม่มีคีย์จะใช้เอนจินกฎที่กำหนดแน่นอน', vi: 'Nhà cung cấp cho engine 4 nhà phân tích. Không có khóa sẽ chạy engine quy tắc xác định.' },
      alpha_vantage: { ko: '미국 주식 시세, 뉴스+감성, ETF 자금 흐름.', en: 'US stock prices, news + sentiment, ETF flows.', ja: '米国株価、ニュース＋感性、ETFフロー。', th: 'ราคาหุ้นสหรัฐ ข่าว+เซนติเมนต์ กระแส ETF', vi: 'Giá cổ phiếu Mỹ, tin tức + tâm lý, dòng tiền ETF.' },
      finnhub: { ko: '키가 있으면 기업 뉴스가 뉴스 애널리스트에 병합됩니다.', en: 'Company news merged into the news analyst when a key is present.', ja: 'キーがあれば企業ニュースをニュースアナリストに統合。', th: 'ข่าวบริษัทถูกรวมเข้านักวิเคราะห์ข่าวเมื่อมีคีย์', vi: 'Tin doanh nghiệp được gộp vào nhà phân tích tin tức khi có khóa.' },
      fred: { ko: '거시경제 지표가 펀더멘털 애널리스트에 병합됩니다.', en: 'Macro-economic series merged into the fundamentals analyst.', ja: 'マクロ経済指標をファンダメンタルズアナリストに統合。', th: 'ข้อมูลเศรษฐกิจมหภาครวมเข้านักวิเคราะห์พื้นฐาน', vi: 'Chuỗi kinh tế vĩ mô được gộp vào nhà phân tích cơ bản.' },
      okx: { ko: '암호화폐 캔들, 펀딩비, 베이시스, 거래량. 공개 API — 키 불필요.', en: 'Crypto candles, funding rate, basis, volume. Public API — no key needed.', ja: '暗号資産のローソク足・資金調達率・ベーシス・出来高。公開API。', th: 'แท่งเทียนคริปโต ฟันดิง เบสิส ปริมาณ API สาธารณะ — ไม่ต้องใช้คีย์', vi: 'Nến crypto, funding, basis, khối lượng. API công khai — không cần khóa.' },
      stocktwits: { ko: '군중 심리와 멘션 비율. 공개 API — 키 불필요.', en: 'Crowd sentiment and mention rates. Public API — no key needed.', ja: '群集センチメントと言及率。公開API。', th: 'เซนติเมนต์ฝูงชนและอัตราการพูดถึง API สาธารณะ', vi: 'Tâm lý đám đông và tỷ lệ nhắc đến. API công khai.' },
      polymarket: { ko: '예측시장 확률 (기대 신호). 공개 API — 키 불필요.', en: 'Prediction-market odds (anticipation signal). Public API — no key needed.', ja: '予測市場オッズ（期待シグナル）。公開API。', th: 'อัตราต่อรองตลาดคาดการณ์ (สัญญาณคาดหวัง) API สาธารณะ', vi: 'Tỷ lệ cược thị trường dự đoán (tín hiệu kỳ vọng). API công khai.' },
      alternative_me: { ko: '공포·탐욕 지수. 공개 API — 키 불필요.', en: 'Fear & Greed index. Public API — no key needed.', ja: 'Fear & Greed指数。公開API。', th: 'ดัชนี Fear & Greed API สาธารณะ', vi: 'Chỉ số Fear & Greed. API công khai.' },
    }
    return m[t.target] ? tr(language, m[t.target]) : t.description
  }

  return (
    <div style={{ maxWidth: '760px' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '2px' }}>
        {tr(language, { ko: '설정', en: 'Settings', ja: '設定', th: 'ตั้งค่า', vi: 'Cài đặt' })}
      </h1>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
        {tr(language, {
          ko: '계정 · 환경설정 · 데이터/AI API 구성',
          en: 'Account · preferences · data/AI API configuration',
          ja: 'アカウント · 環境設定 · API構成',
          th: 'บัญชี · การตั้งค่า · การกำหนดค่า API',
          vi: 'Tài khoản · tùy chọn · cấu hình API',
        })}
      </div>

      {savedMsg && (
        <div style={{
          position: 'fixed', top: '18px', right: '18px', zIndex: 50,
          background: 'var(--accent-primary)', color: '#fff', borderRadius: '10px',
          padding: '8px 16px', fontSize: '13px', fontWeight: 600,
        }}>
          {savedMsg}
        </div>
      )}

      {/* ── Account ─────────────────────────────────────── */}
      {sectionTitle({ ko: '계정', en: 'Account', ja: 'アカウント', th: 'บัญชี', vi: 'Tài khoản' })}
      <div className="card" style={{ padding: '14px 16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 18px', fontSize: '13.5px' }}>
          <span style={{ color: 'var(--text-muted)' }}>{tr(language, { ko: '이메일', en: 'Email', ja: 'メール', th: 'อีเมล', vi: 'Email' })}</span>
          <span style={{ fontWeight: 600 }}>{userInfo?.email || '—'}</span>
          <span style={{ color: 'var(--text-muted)' }}>{tr(language, { ko: '포인트', en: 'Points', ja: 'ポイント', th: 'พอยต์', vi: 'Điểm' })}</span>
          <span style={{ fontWeight: 600 }}>{userInfo?.points ?? 0}</span>
        </div>
        <div style={{ display: 'flex', gap: '10px', marginTop: '14px', flexWrap: 'wrap' }}>
          <Link to="/my-trading" className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 14px' }}>
            {tr(language, { ko: '내 계정 · 프로필', en: 'My Account · Profile', ja: 'マイアカウント', th: 'บัญชีของฉัน', vi: 'Tài khoản' })}
          </Link>
          <Link to="/auth/mfa/setup" className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 14px' }}>
            {tr(language, { ko: '2단계 인증(MFA) 설정', en: 'Set up MFA', ja: 'MFA設定', th: 'ตั้งค่า MFA', vi: 'Cài đặt MFA' })}
          </Link>
          <button onClick={onSignOut} className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 14px', cursor: 'pointer' }}>
            {tr(language, { ko: '로그아웃', en: 'Sign out', ja: 'ログアウト', th: 'ออกจากระบบ', vi: 'Đăng xuất' })}
          </button>
        </div>
      </div>

      {/* ── Preferences ─────────────────────────────────── */}
      {sectionTitle({ ko: '환경설정', en: 'Preferences', ja: '環境設定', th: 'การตั้งค่า', vi: 'Tùy chọn' })}
      <div className="card" style={{ padding: '14px 16px' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>
          {tr(language, { ko: '언어', en: 'Language', ja: '言語', th: 'ภาษา', vi: 'Ngôn ngữ' })}
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {LANGUAGES.map(lang => (
            <button
              key={lang.value}
              onClick={() => setLanguage(lang.value)}
              className={`control-pill ${language === lang.value ? 'active' : ''}`}
              style={{ cursor: 'pointer' }}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── AI trading guidelines (Personalized mode) ───── */}
      {sectionTitle({ ko: 'AI 지침 — 개인화 모드', en: 'AI Guidelines — Personalized mode', ja: 'AI指針 — パーソナライズ', th: 'แนวทาง AI — โหมดส่วนบุคคล', vi: 'Chỉ dẫn AI — chế độ cá nhân hóa' })}
      <div className="card" style={{ padding: '14px 16px' }}>
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
          {tr(language, {
            ko: '자유 형식 지침이 모든 AI 분석·결정·검증 프롬프트에 주입됩니다. 지침은 AI를 더 신중하게 만들 수 있지만, 리스크 한도·브레이커·예산 상한을 완화할 수는 없습니다. (최대 2,000자)',
            en: 'Freeform guidelines injected into every AI analysis, decision and verification prompt. Guidelines can make the AI more cautious — they can never loosen risk limits, breakers or budget caps. (Max 2,000 chars)',
            ja: '自由形式の指針が全てのAI分析・決定・検証プロンプトに注入されます。指針はAIを慎重にできますが、リスク制限は緩められません。(最大2,000文字)',
            th: 'แนวทางแบบอิสระถูกแทรกในทุกพรอมป์ต์ของ AI ทำให้ AI ระมัดระวังขึ้นได้ แต่ผ่อนคลายลิมิตความเสี่ยงไม่ได้ (สูงสุด 2,000 ตัวอักษร)',
            vi: 'Chỉ dẫn tự do được đưa vào mọi prompt phân tích, quyết định và kiểm chứng của AI. Chỉ dẫn có thể khiến AI thận trọng hơn — không bao giờ nới lỏng giới hạn rủi ro. (Tối đa 2.000 ký tự)',
          })}
        </div>
        <textarea
          value={guidelines}
          onChange={e => setGuidelines(e.target.value.slice(0, 2000))}
          rows={5}
          placeholder={tr(language, { ko: '예: 주말에는 신규 진입을 피하고, 알트코인보다 BTC·ETH를 선호하며, 손실 중인 포지션에 물타기하지 마세요.', en: 'e.g. Avoid new entries on weekends, prefer BTC/ETH over alts, never average down on losing positions.', ja: '例: 週末の新規エントリーを避け、アルトよりBTC・ETHを優先、損失ポジションのナンピン禁止。', th: 'เช่น หลีกเลี่ยงการเข้าใหม่ช่วงสุดสัปดาห์ ชอบ BTC/ETH มากกว่าเหรียญเล็ก', vi: 'VD: Tránh vào lệnh cuối tuần, ưu tiên BTC/ETH, không trung bình giá lệnh lỗ.' })}
          style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit', resize: 'vertical' }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
          <button onClick={saveGuidelines} className="btn btn-primary" style={{ fontSize: '12px', padding: '7px 16px', cursor: 'pointer' }}>
            {tr(language, { ko: '지침 저장', en: 'Save guidelines', ja: '指針を保存', th: 'บันทึกแนวทาง', vi: 'Lưu chỉ dẫn' })}
          </button>
          <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{guidelines.length}/2000</span>
        </div>
      </div>

      {/* ── Alerts (email · SMS) ─────────────────────────── */}
      {sectionTitle({ ko: '알림 — 이메일 · SMS', en: 'Alerts — Email · SMS', ja: '通知 — メール · SMS', th: 'การแจ้งเตือน — อีเมล · SMS', vi: 'Cảnh báo — Email · SMS' })}
      <div className="card" style={{ padding: '14px 16px' }}>
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '10px' }}>
          {tr(language, {
            ko: '체결·손절/익절·브레이커 알림입니다. 인앱 알림은 항상 기록되며, 이메일·SMS는 여기서 켭니다 (시간당 외부 발송 제한 있음).',
            en: 'Alerts for fills, SL/TP closes and breaker halts. In-app alerts are always journaled; enable email/SMS here (external sends are rate-limited hourly).',
            ja: '約定・SL/TP・ブレーカーの通知。アプリ内通知は常に記録され、メール・SMSはここで有効化 (時間あたり制限あり)。',
            th: 'แจ้งเตือนการเทรด SL/TP และเบรกเกอร์ การแจ้งในแอปบันทึกเสมอ เปิดอีเมล/SMS ที่นี่ (จำกัดต่อชั่วโมง)',
            vi: 'Cảnh báo khớp lệnh, SL/TP và breaker. Cảnh báo trong app luôn được ghi; bật email/SMS tại đây (giới hạn theo giờ).',
          })}
        </div>
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={alertPrefs.email_enabled}
              onChange={e => setAlertPrefs(p => ({ ...p, email_enabled: e.target.checked }))} />
            {tr(language, { ko: '이메일', en: 'Email', ja: 'メール', th: 'อีเมล', vi: 'Email' })} ({userInfo?.email || '—'})
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={alertPrefs.sms_enabled}
              onChange={e => setAlertPrefs(p => ({ ...p, sms_enabled: e.target.checked }))} />
            SMS
          </label>
          <input type="tel" value={alertPrefs.phone} placeholder="+821012345678"
            onChange={e => setAlertPrefs(p => ({ ...p, phone: e.target.value.trim() }))}
            style={{ padding: '8px 11px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13, width: 170 }} />
          <button onClick={saveAlertPrefs} className="btn btn-primary" style={{ fontSize: '12px', padding: '7px 16px', cursor: 'pointer' }}>
            {tr(language, { ko: '알림 설정 저장', en: 'Save alert settings', ja: '通知設定を保存', th: 'บันทึกการแจ้งเตือน', vi: 'Lưu cài đặt cảnh báo' })}
          </button>
        </div>
      </div>

      {/* ── API configuration per target ────────────────── */}
      {sectionTitle({ ko: 'API 구성 — 데이터 · AI 소스별 설정', en: 'API Configuration — per data / AI target', ja: 'API構成 — データ · AIソース別設定', th: 'การกำหนดค่า API — แยกตามแหล่งข้อมูล/AI', vi: 'Cấu hình API — theo nguồn dữ liệu/AI' })}
      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        {tr(language, {
          ko: '키가 없어도 공개 API 소스로 전체 파이프라인이 동작합니다. 키를 등록하면 해당 소스의 데이터가 더 깊어집니다. 키는 마스킹되어 저장되며 전체 값은 다시 표시되지 않습니다.',
          en: 'The whole pipeline runs on public APIs without any key. Adding keys deepens that source. Keys are stored masked and never displayed again in full.',
          ja: 'キーなしでも公開APIで全パイプラインが動作します。キーは保存後マスキングされます。',
          th: 'ไปป์ไลน์ทำงานได้โดยไม่ต้องใช้คีย์ คีย์จะถูกปิดบังหลังบันทึก',
          vi: 'Toàn bộ pipeline chạy được không cần khóa. Khóa được che sau khi lưu.',
        })}
      </div>

      {loading && <div className="card" style={{ padding: '16px' }}>{tr(language, { ko: '불러오는 중...', en: 'Loading...', ja: '読み込み中...', th: 'กำลังโหลด...', vi: 'Đang tải...' })}</div>}
      {error && <div className="card" style={{ padding: '16px', color: 'var(--error, #d03b3b)' }}>{error}</div>}

      {targets.filter(t => t.target !== 'alerts').map(t => {
        const draft = draftOf(t)
        return (
          <div key={t.target} className="card" style={{ padding: '14px 16px', marginBottom: '10px', opacity: t.enabled ? 1 : 0.55 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <div style={{ fontWeight: 700, fontSize: '14px' }}>{targetLabel(t)}</div>
              <span style={{
                fontSize: '10.5px', fontWeight: 700, borderRadius: '999px', padding: '2px 9px',
                background: t.requires_key
                  ? (t.configured ? 'rgba(12,163,12,0.14)' : 'rgba(237,161,0,0.16)')
                  : 'rgba(42,120,214,0.13)',
                color: t.requires_key ? (t.configured ? 'var(--success, #0ca30c)' : '#a16800') : 'var(--accent-primary)',
              }}>
                {t.requires_key
                  ? (t.configured
                    ? tr(language, { ko: '키 등록됨', en: 'Key set', ja: 'キー設定済み', th: 'ตั้งคีย์แล้ว', vi: 'Đã đặt khóa' })
                    : tr(language, { ko: '키 미등록 (선택)', en: 'No key (optional)', ja: 'キー未設定', th: 'ยังไม่มีคีย์', vi: 'Chưa có khóa' }))
                  : tr(language, { ko: '공개 API — 키 불필요', en: 'Public API — no key needed', ja: '公開API', th: 'API สาธารณะ', vi: 'API công khai' })}
              </span>
              <div style={{ flex: 1 }} />
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                <input type="checkbox" checked={t.enabled} disabled={saving === t.target} onChange={() => toggleTarget(t)} />
                {tr(language, { ko: '사용', en: 'Enabled', ja: '有効', th: 'เปิดใช้', vi: 'Bật' })}
              </label>
            </div>
            <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', margin: '6px 0 0' }}>{targetDescription(t)}</div>

            {t.requires_key && (
              <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {t.fields.includes('provider') && (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <select
                      value={draft.provider}
                      onChange={e => { setDraft(t.target, { provider: e.target.value, model: '' }); setCustomModel(c => ({ ...c, [t.target]: false })) }}
                      style={{ padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px' }}
                    >
                      <option value="">{tr(language, { ko: '프로바이더 선택', en: 'Select provider', ja: 'プロバイダー選択', th: 'เลือกผู้ให้บริการ', vi: 'Chọn nhà cung cấp' })}</option>
                      {LLM_PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <select
                      value={customModel[t.target] ? '__custom__' : (draft.model || '')}
                      disabled={!draft.provider}
                      onChange={e => {
                        if (e.target.value === '__custom__') {
                          setCustomModel(c => ({ ...c, [t.target]: true }))
                        } else {
                          setCustomModel(c => ({ ...c, [t.target]: false }))
                          setDraft(t.target, { model: e.target.value })
                        }
                      }}
                      style={{ flex: 1, minWidth: '180px', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px' }}
                    >
                      <option value="">
                        {tr(language, { ko: '서버 기본 모델', en: 'Server default model', ja: 'サーバー既定モデル', th: 'โมเดลเริ่มต้นของเซิร์ฟเวอร์', vi: 'Mô hình mặc định máy chủ' })}
                        {draft.provider && MODEL_OPTIONS[draft.provider]?.[0] ? ` (${MODEL_OPTIONS[draft.provider][0]})` : ''}
                      </option>
                      {(MODEL_OPTIONS[draft.provider] || []).map(m => <option key={m} value={m}>{m}</option>)}
                      {draft.model && !customModel[t.target] && !(MODEL_OPTIONS[draft.provider] || []).includes(draft.model) && (
                        <option value={draft.model}>{draft.model}</option>
                      )}
                      <option value="__custom__">{tr(language, { ko: '직접 입력…', en: 'Custom…', ja: '直接入力…', th: 'กำหนดเอง…', vi: 'Tự nhập…' })}</option>
                    </select>
                    {customModel[t.target] && (
                      <input
                        type="text"
                        autoFocus
                        placeholder={tr(language, { ko: '모델 ID 직접 입력', en: 'Enter model id', ja: 'モデルIDを入力', th: 'ใส่รหัสโมเดล', vi: 'Nhập id mô hình' })}
                        value={draft.model}
                        onChange={e => setDraft(t.target, { model: e.target.value })}
                        style={{ flex: 1, minWidth: '160px', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px', fontFamily: 'var(--font-mono)' }}
                      />
                    )}
                  </div>
                )}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={t.masked_key
                      ? tr(language, { ko: `저장된 키 ${t.masked_key} — 새 키 입력 시 교체`, en: `Saved key ${t.masked_key} — enter new key to replace`, ja: `保存済み ${t.masked_key}`, th: `คีย์ที่บันทึก ${t.masked_key}`, vi: `Khóa đã lưu ${t.masked_key}` })
                      : tr(language, { ko: 'API 키 입력', en: 'Enter API key', ja: 'APIキー入力', th: 'ใส่คีย์ API', vi: 'Nhập khóa API' })}
                    value={draft.api_key}
                    onChange={e => setDraft(t.target, { api_key: e.target.value })}
                    style={{ flex: 1, minWidth: '200px', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px', fontFamily: 'var(--font-mono)' }}
                  />
                  <button
                    onClick={() => saveTarget(t)}
                    disabled={saving === t.target || (!draft.api_key && t.fields.length === 0)}
                    className="btn btn-primary"
                    style={{ fontSize: '12px', padding: '7px 16px', cursor: 'pointer' }}
                  >
                    {saving === t.target
                      ? tr(language, { ko: '저장 중...', en: 'Saving...', ja: '保存中...', th: 'กำลังบันทึก...', vi: 'Đang lưu...' })
                      : tr(language, { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu' })}
                  </button>
                  {t.configured && (
                    <button
                      onClick={() => clearTarget(t)}
                      disabled={saving === t.target}
                      className="btn btn-secondary"
                      style={{ fontSize: '12px', padding: '7px 12px', cursor: 'pointer' }}
                    >
                      {tr(language, { ko: '키 삭제', en: 'Remove key', ja: 'キー削除', th: 'ลบคีย์', vi: 'Xóa khóa' })}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}

      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '14px', lineHeight: 1.6 }}>
        {tr(language, {
          ko: '참고: 자동매매 규칙별 상세 설정(주기·최소 신뢰도·자동체결)은 자동매매 페이지에서, 리스크 한도(일일 손실·심볼 노출·SL/TP)는 에이전트 API(/api/risk/limits)에서 관리합니다.',
          en: 'Note: per-rule automation settings (interval, min confidence, auto-execute) live on the Automation page; risk limits (daily loss, exposure, SL/TP) via the agent API (/api/risk/limits).',
          ja: '自動売買ルール別設定は自動売買ページで管理します。',
          th: 'การตั้งค่ากฎอัตโนมัติอยู่ที่หน้า Automation',
          vi: 'Cài đặt quy tắc tự động ở trang Automation.',
        })}
      </div>
    </div>
  )
}
