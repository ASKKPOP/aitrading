import { useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Automation (Target 3) — user-configured AI auto-trading rules, backed by
// /api/automation/configs. The server worker runs each enabled rule on its
// interval: multi-agent analysis -> decision -> auto paper-trade (simulator)
// when action + confidence meet the rule. Run history from /api/automation/runs.
//
// Three user modes (persisted in localStorage):
//   simple — pick a coin + risk preset, one button (everything else defaulted)
//   guided — key fields exposed with recommended values and inline hints
//   pro    — full control: every field incl. market/provider/account
type Rule = {
  id?: number; symbol: string; market: string; provider: string | null; interval_minutes: number;
  min_confidence: number; size_usd: number; auto_execute: boolean | number; account_type: string;
  enabled?: boolean | number; last_run_at?: string | null; risk_level?: string | null;
}

type UserMode = 'simple' | 'guided' | 'pro'
const MODE_KEY = 'sooppiy_automation_mode'

const DEFAULT_DRAFT: Rule = { symbol: 'BTC', market: 'crypto', provider: null, interval_minutes: 60, min_confidence: 0.65, size_usd: 500, auto_execute: false, account_type: 'simulator' }

// Simple-mode risk presets: conservative checks less often and demands more
// conviction with smaller size; aggressive is the inverse. All simulator-only.
// The server ALSO expands the chosen level into the agent's risk_limits exit
// profile (sl/tp shown here so the user sees it before confirming).
const RISK_PRESETS = {
  stable:     { interval_minutes: 240, min_confidence: 0.75, size_usd: 200,  sl: 3, tp: 6 },
  balanced:   { interval_minutes: 60,  min_confidence: 0.65, size_usd: 500,  sl: 5, tp: 10 },
  aggressive: { interval_minutes: 30,  min_confidence: 0.55, size_usd: 1000, sl: 8, tp: 15 },
} as const
type RiskKey = keyof typeof RISK_PRESETS

const SIMPLE_COINS = ['BTC', 'ETH', 'SOL', 'SCANNER'] as const

export function AutomationPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [mode, setMode] = useState<UserMode>(() => {
    const saved = localStorage.getItem(MODE_KEY)
    return saved === 'simple' || saved === 'guided' || saved === 'pro' ? saved : 'simple'
  })
  useEffect(() => { localStorage.setItem(MODE_KEY, mode) }, [mode])

  const [rules, setRules] = useState<Rule[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [draft, setDraft] = useState<Rule>({ ...DEFAULT_DRAFT })
  const [simpleCoin, setSimpleCoin] = useState<string>('BTC')
  const [simpleRisk, setSimpleRisk] = useState<RiskKey>('balanced')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const T = {
    title: tr(language, { ko: '자동화', en: 'Automation', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động hóa' }),
    subtitle: tr(language, { ko: 'AI가 설정한 일정에 따라 실행되며, 결정이 규칙에 부합할 때 모의 거래를 수행합니다', en: 'AI runs on your schedule and paper-trades when the decision meets your rules', ja: 'スケジュールに沿ってAIが自動売買', th: 'AI ทำงานตามเวลาและเทรดเมื่อเข้าเงื่อนไข', vi: 'AI chạy theo lịch và giao dịch khi đủ điều kiện' }),
    symbol: tr(language, { ko: '종목', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã' }),
    market: tr(language, { ko: '시장', en: 'Market', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường' }),
    provider: tr(language, { ko: 'AI 제공자', en: 'AI provider', ja: 'AIプロバイダー', th: 'ผู้ให้บริการ AI', vi: 'Nhà cung cấp AI' }),
    serverDefault: tr(language, { ko: '서버 기본값', en: 'server default', ja: 'サーバー既定', th: 'ค่าเริ่มต้นเซิร์ฟเวอร์', vi: 'mặc định máy chủ' }),
    interval: tr(language, { ko: '실행 주기 (분)', en: 'Run every (min)', ja: '実行間隔（分）', th: 'ทุกๆ (นาที)', vi: 'Mỗi (phút)' }),
    minConf: tr(language, { ko: '최소 신뢰도', en: 'Min confidence', ja: '最低信頼度', th: 'ความมั่นใจขั้นต่ำ', vi: 'Độ tin cậy tối thiểu' }),
    size: tr(language, { ko: '포지션 크기 ($)', en: 'Position size ($)', ja: 'ポジションサイズ', th: 'ขนาดโพซิชัน ($)', vi: 'Kích thước lệnh ($)' }),
    account: tr(language, { ko: '계정', en: 'Account', ja: '口座', th: 'บัญชี', vi: 'Tài khoản' }),
    autoEx: tr(language, { ko: '자동 실행', en: 'Auto-execute', ja: '自動執行', th: 'ดำเนินการอัตโนมัติ', vi: 'Tự động thực hiện' }),
    add: tr(language, { ko: '규칙 추가', en: 'Add rule', ja: 'ルールを追加', th: 'เพิ่มกฎ', vi: 'Thêm quy tắc' }),
    remove: tr(language, { ko: '제거', en: 'Remove', ja: '削除', th: 'ลบ', vi: 'Xóa' }),
    yourRules: tr(language, { ko: '내 자동화 규칙', en: 'Your automation rules', ja: '自動売買ルール', th: 'กฎอัตโนมัติของคุณ', vi: 'Quy tắc của bạn' }),
    empty: tr(language, { ko: '아직 규칙이 없습니다. 위에서 추가하세요.', en: 'No rules yet. Add one above.', ja: 'ルールはまだありません。', th: 'ยังไม่มีกฎ', vi: 'Chưa có quy tắc.' }),
    history: tr(language, { ko: '최근 실행', en: 'Recent runs', ja: '実行履歴', th: 'ประวัติล่าสุด', vi: 'Lần chạy gần đây' }),
    noRuns: tr(language, { ko: '아직 실행 기록이 없습니다 — 워커가 매분 예정된 규칙을 확인합니다.', en: 'No runs yet — the worker checks due rules every minute.', ja: 'まだ実行はありません。', th: 'ยังไม่มีการทำงาน — ระบบตรวจทุกนาที', vi: 'Chưa có lần chạy nào.' }),
    executed: tr(language, { ko: '체결됨', en: 'executed', ja: '執行', th: 'ดำเนินการแล้ว', vi: 'đã thực hiện' }),
    realNote: tr(language, { ko: '실계좌의 규칙은 분석만 실행합니다 — 이 빌드에서는 라이브 주문 실행이 비활성화되어 있습니다.', en: 'Rules on the real account run analysis only — live order execution is disabled in this build.', ja: '実口座ルールは分析のみ実行します。', th: 'กฎบัญชีจริงจะวิเคราะห์เท่านั้น — ไม่มีการส่งคำสั่งจริงในเวอร์ชันนี้', vi: 'Quy tắc tài khoản thật chỉ phân tích.' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
    // ── mode system ──
    modeSimple: tr(language, { ko: '간편', en: 'Simple', ja: 'かんたん', th: 'ง่าย', vi: 'Đơn giản' }),
    modeGuided: tr(language, { ko: '표준', en: 'Guided', ja: '標準', th: 'มาตรฐาน', vi: 'Tiêu chuẩn' }),
    modePro: tr(language, { ko: '전문가', en: 'Pro', ja: 'プロ', th: 'มืออาชีพ', vi: 'Chuyên nghiệp' }),
    modeSimpleDesc: tr(language, { ko: '코인과 위험 성향만 고르세요 — 나머지는 AI가 알아서 합니다', en: 'Pick a coin and a risk level — AI handles the rest', ja: 'コインとリスクを選ぶだけ — あとはAIにおまかせ', th: 'เลือกเหรียญและระดับความเสี่ยง — ที่เหลือ AI จัดการ', vi: 'Chọn coin và mức rủi ro — AI lo phần còn lại' }),
    modeGuidedDesc: tr(language, { ko: '핵심 설정을 직접 조정하되, 추천값이 함께 표시됩니다', en: 'Adjust the key settings yourself, with recommendations shown', ja: '主要設定を自分で調整 — 推奨値つき', th: 'ปรับการตั้งค่าหลักเอง พร้อมค่าแนะนำ', vi: 'Tự chỉnh các thiết lập chính, kèm giá trị đề xuất' }),
    modeProDesc: tr(language, { ko: '모든 설정을 직접 제어합니다 — AI 제공자, 시장, 계정 유형까지', en: 'Full control over every setting — AI provider, market, account type', ja: '全設定をフルコントロール', th: 'ควบคุมทุกการตั้งค่า', vi: 'Toàn quyền kiểm soát mọi thiết lập' }),
    coinAuto: tr(language, { ko: 'AI 자동 선택', en: 'AI auto-pick', ja: 'AI自動選択', th: 'AI เลือกให้', vi: 'AI tự chọn' }),
    coinAutoHint: tr(language, { ko: '스캐너가 거래량 급증·신규 상장에서 후보를 고릅니다', en: 'The scanner picks candidates from volume surges & new listings', ja: 'スキャナーが出来高急増・新規上場から選択', th: 'สแกนเนอร์เลือกจากปริมาณพุ่งและเหรียญใหม่', vi: 'Máy quét chọn từ khối lượng tăng vọt & niêm yết mới' }),
    riskLabel: tr(language, { ko: '위험 성향', en: 'Risk level', ja: 'リスク', th: 'ระดับความเสี่ยง', vi: 'Mức rủi ro' }),
    riskStable: tr(language, { ko: '안정', en: 'Stable', ja: '安定', th: 'มั่นคง', vi: 'Ổn định' }),
    riskBalanced: tr(language, { ko: '균형', en: 'Balanced', ja: 'バランス', th: 'สมดุล', vi: 'Cân bằng' }),
    riskAggressive: tr(language, { ko: '공격', en: 'Aggressive', ja: '積極', th: 'เชิงรุก', vi: 'Tích cực' }),
    riskStableDesc: tr(language, { ko: '4시간마다 · 신뢰도 75%+ · $200', en: 'Every 4h · 75%+ confidence · $200', ja: '4時間毎 · 75%+ · $200', th: 'ทุก 4 ชม. · 75%+ · $200', vi: 'Mỗi 4h · 75%+ · $200' }),
    riskBalancedDesc: tr(language, { ko: '1시간마다 · 신뢰도 65%+ · $500', en: 'Every 1h · 65%+ confidence · $500', ja: '1時間毎 · 65%+ · $500', th: 'ทุก 1 ชม. · 65%+ · $500', vi: 'Mỗi 1h · 65%+ · $500' }),
    riskAggressiveDesc: tr(language, { ko: '30분마다 · 신뢰도 55%+ · $1,000', en: 'Every 30min · 55%+ confidence · $1,000', ja: '30分毎 · 55%+ · $1,000', th: 'ทุก 30 นาที · 55%+ · $1,000', vi: 'Mỗi 30 phút · 55%+ · $1.000' }),
    startAuto: tr(language, { ko: '자동매매 시작', en: 'Start auto-trading', ja: '自動売買を開始', th: 'เริ่มเทรดอัตโนมัติ', vi: 'Bắt đầu giao dịch tự động' }),
    simpleNote: tr(language, { ko: '모의 자금으로 거래합니다 — 실제 돈이 아닙니다. 언제든 규칙을 제거할 수 있습니다.', en: 'Trades with simulated funds — not real money. Remove the rule anytime.', ja: 'シミュレーション資金で取引 — 実際のお金ではありません。', th: 'เทรดด้วยเงินจำลอง — ไม่ใช่เงินจริง ลบกฎได้ตลอด', vi: 'Giao dịch bằng vốn mô phỏng — không phải tiền thật.' }),
    recPrefix: tr(language, { ko: '추천', en: 'Recommended', ja: '推奨', th: 'แนะนำ', vi: 'Đề xuất' }),
    recInterval: tr(language, { ko: '60분 — 신호 빈도와 API 비용의 균형점', en: '60 min — balances signal frequency vs API cost', ja: '60分 — シグナル頻度とコストのバランス', th: '60 นาที — สมดุลระหว่างความถี่และค่าใช้จ่าย', vi: '60 phút — cân bằng tần suất và chi phí' }),
    recConf: tr(language, { ko: '0.65 — 너무 낮으면 노이즈 체결, 너무 높으면 기회 상실', en: '0.65 — lower trades noise, higher misses opportunities', ja: '0.65 — 低いとノイズ、高いと機会損失', th: '0.65 — ต่ำไปเทรดตามสัญญาณรบกวน สูงไปพลาดโอกาส', vi: '0.65 — thấp quá giao dịch nhiễu, cao quá bỏ lỡ cơ hội' }),
    recSize: tr(language, { ko: '모의 자본의 5% 이하로 시작하세요', en: 'Start at ≤5% of your simulated capital', ja: 'シミュレーション資金の5%以下で開始', th: 'เริ่มที่ ≤5% ของทุนจำลอง', vi: 'Bắt đầu ở mức ≤5% vốn mô phỏng' }),
    recSymbol: tr(language, { ko: 'BTC·ETH는 데이터가 가장 풍부합니다. SCANNER = AI 자동 선택', en: 'BTC·ETH have the richest data. SCANNER = AI auto-pick', ja: 'BTC・ETHはデータが最も豊富。SCANNER = AI自動選択', th: 'BTC·ETH ข้อมูลครบที่สุด SCANNER = AI เลือกให้', vi: 'BTC·ETH có dữ liệu phong phú nhất. SCANNER = AI tự chọn' }),
    proHint: tr(language, { ko: '이벤트 가드(EVENT_GUARD_ENABLED)가 켜져 있으면 FOMC·CPI·고용지표 발표 전후 1시간 동안 신규 진입이 차단됩니다.', en: 'With the event guard (EVENT_GUARD_ENABLED) on, new entries are blocked ±1h around FOMC/CPI/jobs releases.', ja: 'イベントガード有効時、FOMC・CPI・雇用統計の前後1時間は新規エントリーを停止します。', th: 'เมื่อเปิด event guard จะบล็อกการเข้าใหม่ ±1 ชม. รอบ FOMC/CPI/การจ้างงาน', vi: 'Khi bật event guard, chặn lệnh mới ±1h quanh FOMC/CPI/việc làm.' }),
  }

  // Backend skip_reason strings arrive in English; localize the known set,
  // fall back to the raw text for anything new (e.g. risk-gate detail).
  const skipLabel = (reason?: string | null): string => {
    if (!reason) return '—'
    if (reason === 'auto_execute off') return tr(language, { ko: '자동 실행 꺼짐', en: 'auto-execute off', ja: '自動執行オフ', th: 'ปิดการดำเนินการอัตโนมัติ', vi: 'tắt tự động thực hiện' })
    if (reason.startsWith('real account')) return tr(language, { ko: '실계좌 — 이 빌드에서는 분석만 실행', en: 'real account — analysis only in this build', ja: '実口座 — 分析のみ', th: 'บัญชีจริง — วิเคราะห์เท่านั้น', vi: 'tài khoản thật — chỉ phân tích' })
    const dm = reason.match(/^decision is '(.+)'$/)
    if (dm) return tr(language, { ko: `결정이 '${dm[1]}' — 체결 조건 아님`, en: `decision is '${dm[1]}'`, ja: `判断が'${dm[1]}'のため見送り`, th: `ผลตัดสินคือ '${dm[1]}'`, vi: `quyết định là '${dm[1]}'` })
    const cm = reason.match(/^confidence (.+) below threshold (.+)$/)
    if (cm) return tr(language, { ko: `신뢰도 ${cm[1]} — 임계값 ${cm[2]} 미달`, en: reason, ja: `信頼度 ${cm[1]} がしきい値 ${cm[2]} 未満`, th: `ความมั่นใจ ${cm[1]} ต่ำกว่าเกณฑ์ ${cm[2]}`, vi: `độ tin cậy ${cm[1]} dưới ngưỡng ${cm[2]}` })
    if (reason === 'market closed') return tr(language, { ko: '장 마감', en: 'market closed', ja: '市場クローズ', th: 'ตลาดปิด', vi: 'thị trường đóng cửa' })
    if (reason === 'no valid price in decision') return tr(language, { ko: '유효한 가격 없음', en: 'no valid price', ja: '有効な価格なし', th: 'ไม่มีราคาที่ใช้ได้', vi: 'không có giá hợp lệ' })
    if (reason.startsWith('scanner:')) return tr(language, { ko: '스캐너: 후보 없음', en: 'scanner: no candidates', ja: 'スキャナー: 候補なし', th: 'สแกนเนอร์: ไม่มีตัวเลือก', vi: 'máy quét: không có ứng viên' })
    if (reason.startsWith('event guard:')) return tr(language, { ko: '이벤트 가드: 거시 지표 발표 창 — 진입 차단', en: reason, ja: 'イベントガード: 発表ウィンドウ中', th: 'event guard: ช่วงประกาศตัวเลข', vi: 'event guard: cửa sổ công bố' })
    return reason
  }

  const authHeaders: any = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }

  async function refresh() {
    try {
      const [cfgRes, runRes] = await Promise.all([
        fetch(`${API_BASE}/automation/configs`, { headers: authHeaders }),
        fetch(`${API_BASE}/automation/runs?limit=15`, { headers: authHeaders }),
      ])
      const cfg = await cfgRes.json(); const run = await runRes.json()
      if (cfgRes.ok) setRules(cfg.configs || [])
      if (runRes.ok) setRuns(run.runs || [])
    } catch { /* transient */ }
  }

  useEffect(() => {
    if (!token) return
    refresh()
    const iv = setInterval(refresh, 30000)
    return () => clearInterval(iv)
  }, [token])

  async function postRule(rule: Rule) {
    setBusy(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/automation/configs`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify({ ...rule, provider: rule.provider || null, lang: language }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save rule')
      await refresh()
    } catch (e: any) { setError(e.message) }
    setBusy(false)
  }

  function addSimple() {
    const preset = RISK_PRESETS[simpleRisk]
    postRule({
      symbol: simpleCoin, market: 'crypto', provider: null,
      interval_minutes: preset.interval_minutes,
      min_confidence: preset.min_confidence,
      size_usd: preset.size_usd,
      auto_execute: true, account_type: 'simulator',
      risk_level: simpleRisk,
    })
  }

  async function remove(id?: number) {
    if (!id) return
    try {
      await fetch(`${API_BASE}/automation/configs/${id}`, { method: 'DELETE', headers: authHeaders })
      await refresh()
    } catch { /* ignore */ }
  }

  // --bg-input is not defined in index.css; use the theme vars that are, so
  // fields stay readable in both light and dark themes.
  const inp: any = { padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)' }
  const fld = (label: string, node: any, hint?: string) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
      {label}{node}
      {hint && <span style={{ fontSize: 11, color: 'var(--text-muted,#a89f92)', lineHeight: 1.4 }}>💡 {T.recPrefix}: {hint}</span>}
    </label>
  )

  const chip = (active: boolean): any => ({
    padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 13, fontWeight: active ? 700 : 500,
    border: active ? '1.5px solid var(--accent-primary,#c26a45)' : '1px solid var(--border-color,#d3c8b6)',
    background: active ? 'rgba(194,106,69,0.12)' : 'transparent',
    color: active ? 'var(--accent-primary,#c26a45)' : 'inherit',
  })

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">⚙</div><div className="empty-title">{T.login}</div></div></div>
  }

  const modeDesc = mode === 'simple' ? T.modeSimpleDesc : mode === 'guided' ? T.modeGuidedDesc : T.modeProDesc

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
      </div>

      {/* ── Mode selector ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <button style={chip(mode === 'simple')} onClick={() => setMode('simple')}>① {T.modeSimple}</button>
        <button style={chip(mode === 'guided')} onClick={() => setMode('guided')}>② {T.modeGuided}</button>
        <button style={chip(mode === 'pro')} onClick={() => setMode('pro')}>③ {T.modePro}</button>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 14 }}>{modeDesc}</div>

      {/* ── Mode 1: Simple ── */}
      {mode === 'simple' && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>{T.symbol}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
            {SIMPLE_COINS.map(c => (
              <button key={c} style={chip(simpleCoin === c)} onClick={() => setSimpleCoin(c)}>
                {c === 'SCANNER' ? `🔍 ${T.coinAuto}` : c}
              </button>
            ))}
          </div>
          {simpleCoin === 'SCANNER' && (
            <div style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)', marginBottom: 12 }}>💡 {T.coinAutoHint}</div>
          )}
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>{T.riskLabel}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 10, marginBottom: 16 }}>
            {(['stable', 'balanced', 'aggressive'] as RiskKey[]).map(k => (
              <button key={k} onClick={() => setSimpleRisk(k)} style={{
                ...chip(simpleRisk === k), borderRadius: 10, padding: '12px 14px', textAlign: 'left' as const,
                display: 'flex', flexDirection: 'column' as const, gap: 4,
              }}>
                <span style={{ fontSize: 14 }}>
                  {k === 'stable' ? `🛡 ${T.riskStable}` : k === 'balanced' ? `⚖️ ${T.riskBalanced}` : `🔥 ${T.riskAggressive}`}
                </span>
                <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-secondary,#8a8073)' }}>
                  {k === 'stable' ? T.riskStableDesc : k === 'balanced' ? T.riskBalancedDesc : T.riskAggressiveDesc}
                </span>
                <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-muted,#a89f92)', fontVariantNumeric: 'tabular-nums' }}>
                  SL −{RISK_PRESETS[k].sl}% · TP +{RISK_PRESETS[k].tp}%
                </span>
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.simpleNote}</span>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            <button onClick={addSimple} disabled={busy} style={{ marginLeft: 'auto', padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>▶ {T.startAuto}</button>
          </div>
        </div>
      )}

      {/* ── Mode 2: Guided ── */}
      {mode === 'guided' && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 14 }}>
            {fld(T.symbol,
              <select style={inp} value={draft.symbol} onChange={e => setDraft({ ...draft, symbol: e.target.value })}>
                {['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'SCANNER'].map(s => <option key={s} value={s}>{s === 'SCANNER' ? `🔍 ${T.coinAuto}` : s}</option>)}
              </select>, T.recSymbol)}
            {fld(T.interval, <input style={inp} type="number" min={5} value={draft.interval_minutes} onChange={e => setDraft({ ...draft, interval_minutes: +e.target.value })} />, T.recInterval)}
            {fld(T.minConf, <input style={inp} type="number" step="0.05" min="0" max="1" value={draft.min_confidence} onChange={e => setDraft({ ...draft, min_confidence: +e.target.value })} />, T.recConf)}
            {fld(T.size, <input style={inp} type="number" value={draft.size_usd} onChange={e => setDraft({ ...draft, size_usd: +e.target.value })} />, T.recSize)}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
              <input type="checkbox" checked={!!draft.auto_execute} onChange={e => setDraft({ ...draft, auto_execute: e.target.checked })} /> {T.autoEx}
            </label>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            <button onClick={() => postRule(draft)} disabled={busy} style={{ marginLeft: 'auto', padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>+ {T.add}</button>
          </div>
        </div>
      )}

      {/* ── Mode 3: Pro ── */}
      {mode === 'pro' && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 12 }}>
            {fld(T.symbol, <input style={inp} value={draft.symbol} onChange={e => setDraft({ ...draft, symbol: e.target.value.toUpperCase() })} />)}
            {fld(T.market, <select style={inp} value={draft.market} onChange={e => setDraft({ ...draft, market: e.target.value })}><option value="crypto">crypto</option><option value="us-stock">us-stock</option></select>)}
            {fld(T.provider, <select style={inp} value={draft.provider || ''} onChange={e => setDraft({ ...draft, provider: e.target.value || null })}><option value="">{T.serverDefault}</option>{['openai', 'gemini', 'grok', 'qwen', 'glm', 'local', 'anthropic'].map(p => <option key={p} value={p}>{p}</option>)}</select>)}
            {fld(T.interval, <input style={inp} type="number" min={5} value={draft.interval_minutes} onChange={e => setDraft({ ...draft, interval_minutes: +e.target.value })} />)}
            {fld(T.minConf, <input style={inp} type="number" step="0.05" min="0" max="1" value={draft.min_confidence} onChange={e => setDraft({ ...draft, min_confidence: +e.target.value })} />)}
            {fld(T.size, <input style={inp} type="number" value={draft.size_usd} onChange={e => setDraft({ ...draft, size_usd: +e.target.value })} />)}
            {fld(T.account, <select style={inp} value={draft.account_type} onChange={e => setDraft({ ...draft, account_type: e.target.value })}><option value="simulator">simulator</option><option value="real">real</option></select>)}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
              <input type="checkbox" checked={!!draft.auto_execute} onChange={e => setDraft({ ...draft, auto_execute: e.target.checked })} /> {T.autoEx}
            </label>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            <button onClick={() => postRule(draft)} disabled={busy} style={{ marginLeft: 'auto', padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>+ {T.add}</button>
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted,#a89f92)', lineHeight: 1.5 }}>ⓘ {T.proHint}</div>
        </div>
      )}

      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '0 0 10px' }}>{T.yourRules}</div>
      {rules.length === 0 ? (
        <div className="card" style={{ color: 'var(--text-secondary,#8a8073)' }}>{T.empty}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rules.map((r) => (
            <div key={r.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <b style={{ fontSize: 15 }}>{r.symbol === 'SCANNER' ? `🔍 ${T.coinAuto}` : r.symbol}</b>
              <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>
                {r.market} · {r.provider || T.serverDefault} · {r.interval_minutes}m · ≥{Math.round((r.min_confidence || 0) * 100)}% · ${r.size_usd} · {r.account_type}
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: r.auto_execute ? 'rgba(63,185,80,0.16)' : 'rgba(138,128,115,0.18)', color: r.auto_execute ? '#3fb950' : '#8a8073' }}>
                {r.auto_execute ? 'auto' : 'analysis only'}
              </span>
              {r.last_run_at && <span style={{ fontSize: 11, color: 'var(--text-secondary,#8a8073)' }}>last: {String(r.last_run_at).replace('T', ' ').slice(0, 16)}</span>}
              <button onClick={() => remove(r.id)} style={{ marginLeft: 'auto', padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>{T.remove}</button>
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '22px 0 10px' }}>{T.history}</div>
      {runs.length === 0 ? (
        <div className="card" style={{ color: 'var(--text-secondary,#8a8073)' }}>{T.noRuns}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {runs.map((run) => (
            <div key={run.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '12px 16px' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>{String(run.ran_at || '').replace('T', ' ').slice(0, 16)}</span>
              <b style={{ textTransform: 'uppercase', fontSize: 13, color: run.action === 'buy' ? '#3fb950' : run.action === 'sell' ? '#f0663f' : '#e3a008' }}>{run.action || '—'}</b>
              <span style={{ fontSize: 12 }}>{Math.round((run.confidence || 0) * 100)}%</span>
              {run.executed
                ? <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: 'rgba(63,185,80,0.16)', color: '#3fb950' }}>✓ {T.executed} #{run.signal_id}</span>
                : <span style={{ fontSize: 11.5, color: 'var(--text-secondary,#8a8073)' }}>{skipLabel(run.skip_reason)}</span>}
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 18, fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.55 }}>ℹ️ {T.realNote}</div>
    </div>
  )
}

export default AutomationPage
