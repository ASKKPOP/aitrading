import { useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { AnalysisMonitorPanel, useAnalysisRun, useAnalysisStream } from '../components/AnalysisPipelineViz'
import ConfigProfiles from '../components/ConfigProfiles'
import { SymbolSelect } from '../components/SymbolSelect'
import { tr } from '../i18n'
import { RunsLiveSection } from './RunsLivePage'

// Automation (Target 3) — user-configured AI auto-trading rules, backed by
// /api/automation/configs. The server worker runs each enabled rule on its
// interval: multi-agent analysis -> decision -> auto paper-trade (simulator)
// when action + confidence meet the rule. Run history from /api/automation/runs.
//
// Also hosts the one-off "AI Analyst" panel (formerly its own /analyst page):
// run the multi-agent analysis once, read the decision + report + briefs, then
// optionally turn that symbol/market into a rule via the "Automate this" CTA.
//
// Three user modes (persisted in localStorage):
//   simple — pick a coin + risk preset, one button (everything else defaulted)
//   guided — key fields exposed with recommended values and inline hints
//   pro    — full control: every field incl. market/provider/account
type Rule = {
  id?: number; symbol: string; market: string; provider: string | null; interval_minutes: number;
  min_confidence: number; size_usd: number; auto_execute: boolean | number; account_type: string;
  enabled?: boolean | number; last_run_at?: string | null; risk_level?: string | null;
  mode?: string; budget_usd?: number | null;
  schedule?: { days: number[]; start_hour: number; end_hour: number; tz: string };
}

type UserMode = 'agent' | 'simple' | 'guided' | 'pro'
const MODE_KEY = 'sooppiy_automation_mode'

// Where a fill lands. Mirrors execution/gateway.py — keep the two in step.
//   simulator — platform ledger only, never contacts a broker
//   shadow    — runs by simulation; also mirrors to the broker's sandbox when
//               a gateway is connected, so you can compare real fills safely
//   live      — the real order goes to your configured trading gateway
const ACCOUNT_TYPES = ['simulator', 'shadow', 'live'] as const

// Rules created before the gateway landed store 'real'; show them as live.
const normalizeAccountType = (v: string | null | undefined): string =>
  v === 'real' ? 'live' : (ACCOUNT_TYPES as readonly string[]).includes(v || '') ? (v as string) : 'simulator'

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
    return saved === 'agent' || saved === 'simple' || saved === 'guided' || saved === 'pro' ? saved : 'simple'
  })
  useEffect(() => { localStorage.setItem(MODE_KEY, mode) }, [mode])

  const [rules, setRules] = useState<Rule[]>([])
  const [runs, setRuns] = useState<any[]>([])
  const [draft, setDraft] = useState<Rule>({ ...DEFAULT_DRAFT })
  const [simpleCoin, setSimpleCoin] = useState<string>('BTC')
  const [simpleRisk, setSimpleRisk] = useState<RiskKey>('balanced')
  const [agentBudget, setAgentBudget] = useState<number>(5000)
  const [decisions, setDecisions] = useState<any[]>([])
  const [schedOn, setSchedOn] = useState(false)
  const [sched, setSched] = useState<{ days: number[]; start_hour: number; end_hour: number; tz: string }>(
    { days: [], start_hour: 9, end_hour: 22, tz: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' })
  const [error, setError] = useState('')
  const [removeError, setRemoveError] = useState('')
  const [busy, setBusy] = useState(false)
  // Per-rule test run: streams the same analysis pipeline a scheduled run uses
  // (analysis only — the worker's execution gates are NOT part of a test run).
  const [testRuleId, setTestRuleId] = useState<number | null>(null)
  const testRun = useAnalysisStream(token)

  // One-off AI Analyst run (server-side background job — leaving the page and
  // coming back re-attaches). Never places an order.
  const [anSymbol, setAnSymbol] = useState('BTC')
  const [anMarket, setAnMarket] = useState('crypto')
  const analyze = useAnalysisRun(token)
  const ruleFormRef = useRef<HTMLDivElement | null>(null)

  // Re-attached to an existing job (e.g. returning mid-run): mirror its
  // symbol/market in the controls so the monitor matches what it shows.
  useEffect(() => {
    if (analyze.runInfo) { setAnSymbol(analyze.runInfo.symbol); setAnMarket(analyze.runInfo.market) }
  }, [analyze.runInfo?.id])

  // One step (분석 → 자동매매): create a live trading run for the analyzed
  // symbol and start it immediately — no separate rule form. Balanced
  // defaults; full control stays in the runs section's create form.
  const [runStartBusy, setRunStartBusy] = useState(false)
  const [runStartErr, setRunStartErr] = useState('')
  const [runsReload, setRunsReload] = useState(0)
  const runsSectionRef = useRef<HTMLDivElement | null>(null)

  async function startRunFromAnalysis(symbol: string, market: string) {
    setRunStartBusy(true); setRunStartErr('')
    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify({ symbol, market, market_type: 'spot', max_bet_usd: 500, interval_minutes: 60, min_confidence: 0.65 }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'could not create run')
      const start = await fetch(`${API_BASE}/runs/${data.id}/start`, { method: 'POST', headers: authHeaders })
      if (!start.ok) {
        const detail = (await start.json().catch(() => null))?.detail
        throw new Error(typeof detail === 'string' ? detail : 'could not start run')
      }
      setRunsReload(n => n + 1)
      runsSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (e: any) { setRunStartErr(e.message) }
    setRunStartBusy(false)
  }

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
    liveMoney: tr(language, { ko: '실제 자금', en: 'REAL MONEY', ja: '実資金', th: 'เงินจริง', vi: 'TIỀN THẬT' }),
    badgeAuto: tr(language, { ko: '자동', en: 'auto', ja: '自動', th: 'อัตโนมัติ', vi: 'tự động' }),
    badgeAnalysis: tr(language, { ko: '분석 전용', en: 'analysis only', ja: '分析のみ', th: 'วิเคราะห์เท่านั้น', vi: 'chỉ phân tích' }),
    add: tr(language, { ko: '규칙 추가', en: 'Add rule', ja: 'ルールを追加', th: 'เพิ่มกฎ', vi: 'Thêm quy tắc' }),
    remove: tr(language, { ko: '제거', en: 'Remove', ja: '削除', th: 'ลบ', vi: 'Xóa' }),
    removeFailed: tr(language, { ko: '규칙 제거에 실패했습니다 — 잠시 후 다시 시도하세요', en: 'Failed to remove the rule — try again shortly', ja: 'ルールの削除に失敗しました — しばらくして再試行してください', th: 'ลบกฎไม่สำเร็จ — ลองใหม่อีกครั้ง', vi: 'Xóa quy tắc thất bại — thử lại sau' }),
    yourRules: tr(language, { ko: '내 자동화 규칙', en: 'Your automation rules', ja: '自動売買ルール', th: 'กฎอัตโนมัติของคุณ', vi: 'Quy tắc của bạn' }),
    empty: tr(language, { ko: '아직 규칙이 없습니다. 위에서 추가하세요.', en: 'No rules yet. Add one above.', ja: 'ルールはまだありません。', th: 'ยังไม่มีกฎ', vi: 'Chưa có quy tắc.' }),
    history: tr(language, { ko: '최근 실행', en: 'Recent runs', ja: '実行履歴', th: 'ประวัติล่าสุด', vi: 'Lần chạy gần đây' }),
    noRuns: tr(language, { ko: '아직 실행 기록이 없습니다 — 워커가 매분 예정된 규칙을 확인합니다.', en: 'No runs yet — the worker checks due rules every minute.', ja: 'まだ実行はありません。', th: 'ยังไม่มีการทำงาน — ระบบตรวจทุกนาที', vi: 'Chưa có lần chạy nào.' }),
    executed: tr(language, { ko: '체결됨', en: 'executed', ja: '執行', th: 'ดำเนินการแล้ว', vi: 'đã thực hiện' }),
    realNote: tr(language, { ko: '계정 설정이 체결 위치를 정합니다 — simulator는 모의, shadow는 모의로 실행하며 브로커 샌드박스에 대조 주문, live는 계좌 페이지에서 연결한 게이트웨이로 실제 주문을 보냅니다.', en: 'The account setting decides where a fill lands — simulator is simulated, shadow runs by simulation with a comparison order to the broker sandbox, and live sends a real order through the gateway you connected on the Accounts page.', ja: '口座設定が約定先を決めます — simulator は模擬、shadow は模擬実行＋サンドボックス照合、live は接続したゲートウェイに実発注します。', th: 'การตั้งค่าบัญชีกำหนดจุดที่คำสั่งไปถึง — simulator จำลอง, shadow จำลองพร้อมส่งคำสั่งเทียบไปแซนด์บ็อกซ์, live ส่งคำสั่งจริงผ่านเกตเวย์', vi: 'Thiết lập tài khoản quyết định nơi khớp lệnh — simulator mô phỏng, shadow mô phỏng kèm lệnh đối chiếu tới sandbox, live gửi lệnh thật qua cổng đã kết nối.' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.' }),
    // ── mode system ──
    modeSimple: tr(language, { ko: '간편', en: 'Simple', ja: 'かんたん', th: 'ง่าย', vi: 'Đơn giản' }),
    modeGuided: tr(language, { ko: '표준', en: 'Guided', ja: '標準', th: 'มาตรฐาน', vi: 'Tiêu chuẩn' }),
    modePro: tr(language, { ko: '전문가', en: 'Pro', ja: 'プロ', th: 'มืออาชีพ', vi: 'Chuyên nghiệp' }),
    modeAgent: tr(language, { ko: '완전 위임', en: 'Agent', ja: '完全委任', th: 'มอบหมายเต็มรูปแบบ', vi: 'Ủy quyền hoàn toàn' }),
    modeAgentDesc: tr(language, { ko: '예산만 정하세요 — 종목·크기·주기·위험 수준을 AI가 매 사이클 결정하고, 모든 결정이 기록됩니다', en: 'Set only a budget — the AI decides symbol, size, cadence and risk each cycle, and every decision is journaled', ja: '予算だけ設定 — 銘柄・サイズ・周期・リスクをAIが毎サイクル決定し、全決定を記録', th: 'ตั้งแค่งบประมาณ — AI ตัดสินใจเหรียญ ขนาด รอบ และความเสี่ยงทุกรอบ พร้อมบันทึกทุกการตัดสินใจ', vi: 'Chỉ đặt ngân sách — AI quyết định mã, khối lượng, chu kỳ và rủi ro mỗi chu kỳ, mọi quyết định được ghi lại' }),
    budgetLabel: tr(language, { ko: '총 예산 ($)', en: 'Total budget ($)', ja: '総予算 ($)', th: 'งบประมาณรวม ($)', vi: 'Tổng ngân sách ($)' }),
    budgetHint: tr(language, { ko: 'AI가 배치할 수 있는 총 노출 한도 — 한 포지션은 예산의 25% 이하', en: 'Total exposure the AI may deploy — one position stays ≤ 25% of budget', ja: 'AIが展開できる総エクスポージャー上限 — 1ポジションは予算の25%以下', th: 'วงเงินรวมที่ AI ใช้ได้ — หนึ่งสถานะ ≤ 25% ของงบ', vi: 'Tổng mức AI được triển khai — một vị thế ≤ 25% ngân sách' }),
    startAgent: tr(language, { ko: 'AI에게 위임 시작', en: 'Start delegation', ja: '委任を開始', th: 'เริ่มมอบหมาย', vi: 'Bắt đầu ủy quyền' }),
    agentDecisions: tr(language, { ko: 'AI 결정 로그', en: 'AI decision log', ja: 'AI決定ログ', th: 'บันทึกการตัดสินใจของ AI', vi: 'Nhật ký quyết định AI' }),
    noDecisions: tr(language, { ko: '아직 결정이 없습니다 — 첫 사이클에서 기록됩니다.', en: 'No decisions yet — the first cycle will journal one.', ja: 'まだ決定はありません — 最初のサイクルで記録されます。', th: 'ยังไม่มีการตัดสินใจ — รอบแรกจะบันทึก', vi: 'Chưa có quyết định — chu kỳ đầu sẽ ghi lại.' }),
    agentKillNote: tr(language, { ko: '킬 스위치: 규칙을 제거하면 즉시 중단됩니다. 리스크 게이트·브레이커·예산 상한은 AI가 우회할 수 없습니다.', en: 'Kill switch: removing the rule stops it instantly. The risk gate, breakers and budget cap cannot be bypassed by the AI.', ja: 'キルスイッチ: ルール削除で即停止。リスクゲート・ブレーカー・予算上限はAIが回避できません。', th: 'สวิตช์หยุด: ลบกฎแล้วหยุดทันที AI ข้ามประตูความเสี่ยง เบรกเกอร์ และเพดานงบไม่ได้', vi: 'Công tắc dừng: xóa quy tắc là dừng ngay. AI không thể vượt cổng rủi ro, breaker và trần ngân sách.' }),
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
    scheduleLabel: tr(language, { ko: '거래 시간대 (선택)', en: 'Trading schedule (optional)', ja: '取引スケジュール（任意）', th: 'ตารางเทรด (ไม่บังคับ)', vi: 'Lịch giao dịch (tùy chọn)' }),
    scheduleHint: tr(language, { ko: '지정한 요일·시간대에만 규칙이 실행됩니다. 비워두면 항상 실행됩니다.', en: 'The rule only runs on the chosen days & hours. Leave off to run always.', ja: '指定した曜日・時間帯のみ実行。オフなら常時実行。', th: 'กฎทำงานเฉพาะวัน/เวลาที่เลือก ปิดไว้ = ทำงานตลอด', vi: 'Quy tắc chỉ chạy vào ngày/giờ đã chọn. Tắt = luôn chạy.' }),
    scheduleFrom: tr(language, { ko: '시작', en: 'From', ja: '開始', th: 'จาก', vi: 'Từ' }),
    scheduleTo: tr(language, { ko: '종료', en: 'To', ja: '終了', th: 'ถึง', vi: 'Đến' }),
    testRun: tr(language, { ko: '지금 테스트 실행', en: 'Test run now', ja: '今すぐテスト実行', th: 'ทดสอบตอนนี้', vi: 'Chạy thử ngay' }),
    testRunning: tr(language, { ko: '실행 중…', en: 'Running…', ja: '実行中…', th: 'กำลังทำงาน…', vi: 'Đang chạy…' }),
    testRunNote: tr(language, { ko: '테스트 실행은 이 규칙의 파이프라인을 즉시 실행해 보여줍니다 — 분석만 하며 주문은 실행하지 않습니다.', en: 'A test run executes this rule\'s pipeline right now — analysis only, no order is placed.', ja: 'テスト実行はこのルールのパイプラインを即時実行します — 分析のみで注文は出しません。', th: 'การทดสอบรันไปป์ไลน์ของกฎทันที — วิเคราะห์เท่านั้น ไม่ส่งคำสั่งซื้อขาย', vi: 'Chạy thử thực thi pipeline của quy tắc ngay — chỉ phân tích, không đặt lệnh.' }),
    testDecision: tr(language, { ko: '결정', en: 'Decision', ja: '判断', th: 'การตัดสินใจ', vi: 'Quyết định' }),
    testConfidence: tr(language, { ko: '신뢰도', en: 'Confidence', ja: '信頼度', th: 'ความมั่นใจ', vi: 'Độ tin cậy' }),
    wouldExecute: tr(language, { ko: '체결됐을 것', en: 'would execute', ja: '執行される見込み', th: 'จะดำเนินการ', vi: 'sẽ thực hiện' }),
    wouldSkip: tr(language, { ko: '체결 안 됨', en: 'would skip', ja: '見送りになる', th: 'จะข้าม', vi: 'sẽ bỏ qua' }),
    gateVerdict: tr(language, { ko: '실행 게이트 판정', en: 'Execution-gate verdict', ja: '執行ゲート判定', th: 'ผลตัดสินประตูดำเนินการ', vi: 'Phán quyết cổng thực thi' }),
    qty: tr(language, { ko: '수량', en: 'qty', ja: '数量', th: 'จำนวน', vi: 'KL' }),
    // ── one-off AI Analyst panel ──
    analystSection: tr(language, { ko: 'AI 애널리스트 — 지금 분석', en: 'AI Analyst — analyze now', ja: 'AIアナリスト — 今すぐ分析', th: 'นักวิเคราะห์ AI — วิเคราะห์ตอนนี้', vi: 'Nhà phân tích AI — phân tích ngay' }),
    analystSubtitle: tr(language, { ko: '네 명의 AI 애널리스트가 결정과 리포트를 두고 토론합니다 — 일회성 분석이며 주문은 실행되지 않습니다', en: 'Four AI analysts debate a decision + report — a one-off analysis, no order is placed', ja: '4人のAIアナリストが討議 — 1回限りの分析で、注文は出しません', th: 'นักวิเคราะห์ AI สี่คนถกเถียงเพื่อสรุปการตัดสินใจ — วิเคราะห์ครั้งเดียว ไม่ส่งคำสั่งซื้อขาย', vi: 'Bốn nhà phân tích AI tranh luận — phân tích một lần, không đặt lệnh' }),
    analystRun: tr(language, { ko: '분석 실행', en: 'Run analysis', ja: '分析する', th: 'วิเคราะห์', vi: 'Phân tích' }),
    analystRunning: tr(language, { ko: '애널리스트들이 토론 중…', en: 'Analysts are debating…', ja: '分析中…', th: 'กำลังวิเคราะห์…', vi: 'Đang phân tích…' }),
    analystBriefs: tr(language, { ko: '애널리스트 브리프', en: 'Analyst briefs', ja: 'アナリスト概要', th: 'สรุปนักวิเคราะห์', vi: 'Tóm tắt phân tích' }),
    analystNone: tr(language, { ko: '결정론적 (LLM 키 미설정)', en: 'deterministic (no LLM key set)', ja: 'LLM未設定', th: 'ไม่ได้ตั้งค่า LLM', vi: 'chưa đặt LLM' }),
    startRunNow: tr(language, { ko: '이 설정으로 자동매매 시작', en: 'Start auto-trading with this', ja: 'この設定で自動売買開始', th: 'เริ่มเทรดอัตโนมัติด้วยค่านี้', vi: 'Bắt đầu tự động với thiết lập này' }),
    analystDisclaimer: tr(language, { ko: '리서치 목적일 뿐 — 투자 자문이 아닙니다.', en: 'Research only — not financial advice.', ja: '調査目的のみ — 投資助言ではありません。', th: 'เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน', vi: 'Chỉ nghiên cứu — không phải lời khuyên đầu tư.' }),
  }

  const roleLabels: Record<string, string> = {
    news: tr(language, { ko: '뉴스', en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức' }),
    sentiment: tr(language, { ko: '심리', en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý' }),
    fundamentals_macro: tr(language, { ko: '펀더멘털 & 매크로', en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô' }),
    technical: tr(language, { ko: '기술적 분석', en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật' }),
  }

  const DOW = [
    tr(language, { ko: '월', en: 'Mon', ja: '月', th: 'จ', vi: 'T2' }),
    tr(language, { ko: '화', en: 'Tue', ja: '火', th: 'อ', vi: 'T3' }),
    tr(language, { ko: '수', en: 'Wed', ja: '水', th: 'พ', vi: 'T4' }),
    tr(language, { ko: '목', en: 'Thu', ja: '木', th: 'พฤ', vi: 'T5' }),
    tr(language, { ko: '금', en: 'Fri', ja: '金', th: 'ศ', vi: 'T6' }),
    tr(language, { ko: '토', en: 'Sat', ja: '土', th: 'ส', vi: 'T7' }),
    tr(language, { ko: '일', en: 'Sun', ja: '日', th: 'อา', vi: 'CN' }),
  ]

  // Backend skip_reason strings arrive in English; localize the known set,
  // fall back to the raw text for anything new (e.g. risk-gate detail).
  const skipLabel = (reason?: string | null): string => {
    if (!reason) return '—'
    if (reason === 'auto_execute off') return tr(language, { ko: '자동 실행 꺼짐', en: 'auto-execute off', ja: '自動執行オフ', th: 'ปิดการดำเนินการอัตโนมัติ', vi: 'tắt tự động thực hiện' })
    if (reason.startsWith('live trading selected but no trading gateway')) return tr(language, { ko: '라이브를 선택했지만 거래 게이트웨이가 설정되지 않았습니다 — 실거래를 하려면 계좌 페이지에서 브로커를 연결하세요', en: 'live selected but no trading gateway configured — connect a broker on the Accounts page to trade for real', ja: 'ライブ選択中ですが取引ゲートウェイが未設定です — 実取引には口座ページでブローカーを接続してください', th: 'เลือก live แต่ยังไม่ได้ตั้งค่าเกตเวย์ — เชื่อมต่อโบรกเกอร์ในหน้าบัญชีเพื่อเทรดจริง', vi: 'đã chọn live nhưng chưa cấu hình cổng giao dịch — kết nối broker ở trang Tài khoản để giao dịch thật' })
    if (reason.startsWith('live trading selected but the connected gateway')) return tr(language, { ko: '연결된 게이트웨이에 사용 가능한 API 자격 증명이 없습니다 — 브로커를 다시 연결하세요', en: 'connected gateway has no usable API credentials — reconnect the broker', ja: '接続中のゲートウェイに有効なAPI認証情報がありません — 再接続してください', th: 'เกตเวย์ที่เชื่อมต่อไม่มีข้อมูลรับรอง API ที่ใช้ได้ — เชื่อมต่อโบรกเกอร์ใหม่', vi: 'cổng đã kết nối không có thông tin API dùng được — kết nối lại broker' })
    if (reason.startsWith('live trading selected but the live-trading terms')) return tr(language, { ko: '실거래 약관에 동의하지 않았습니다 — 계좌 페이지에서 동의하세요', en: 'live-trading terms not accepted — accept them on the Accounts page', ja: '実取引の規約が未同意です — 口座ページで同意してください', th: 'ยังไม่ยอมรับข้อกำหนดการเทรดจริง — ยอมรับในหน้าบัญชี', vi: 'chưa chấp nhận điều khoản giao dịch thật — chấp nhận ở trang Tài khoản' })
    if (reason.startsWith('gateway rejected order')) return tr(language, { ko: `게이트웨이가 주문을 거부했습니다 — ${reason.replace('gateway rejected order: ', '')}`, en: reason, ja: `ゲートウェイが注文を拒否 — ${reason.replace('gateway rejected order: ', '')}`, th: `เกตเวย์ปฏิเสธคำสั่ง — ${reason.replace('gateway rejected order: ', '')}`, vi: `cổng từ chối lệnh — ${reason.replace('gateway rejected order: ', '')}` })
    if (reason.startsWith('trading gateway check')) return tr(language, { ko: '게이트웨이 확인 불가 — 안전을 위해 체결하지 않았습니다', en: 'gateway check unavailable — refused for safety', ja: 'ゲートウェイ確認不可 — 安全のため見送り', th: 'ตรวจสอบเกตเวย์ไม่ได้ — ข้ามเพื่อความปลอดภัย', vi: 'không kiểm tra được cổng — bỏ qua để an toàn' })
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
      const decRes = await fetch(`${API_BASE}/automation/agent-decisions?limit=10`, { headers: authHeaders })
      if (decRes.ok) setDecisions((await decRes.json()).decisions || [])
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

  function addAgent() {
    postRule({
      symbol: 'AGENT', market: 'crypto', provider: null,
      interval_minutes: 60, min_confidence: 0.65, size_usd: 500,
      auto_execute: true, account_type: 'simulator',
      mode: 'agent', budget_usd: agentBudget,
    } as Rule)
  }

  async function remove(id?: number) {
    if (!id) return
    setRemoveError('')
    try {
      const res = await fetch(`${API_BASE}/automation/configs/${id}`, { method: 'DELETE', headers: authHeaders })
      if (!res.ok) {
        const detail = (await res.json().catch(() => null))?.detail
        setRemoveError(typeof detail === 'string' ? detail : `${T.removeFailed} (HTTP ${res.status})`)
      }
      await refresh()
    } catch { setRemoveError(T.removeFailed) }
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

  const modeDesc = mode === 'agent' ? T.modeAgentDesc : mode === 'simple' ? T.modeSimpleDesc : mode === 'guided' ? T.modeGuidedDesc : T.modeProDesc

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
      </div>

      {/* ── Live trading runs (merged from the old /runs/live page) — the
          primary surface: one step creates AND starts a server-side run. ── */}
      <div ref={runsSectionRef} style={{ marginBottom: 22 }}>
        <RunsLiveSection token={token} embedded reloadKey={runsReload} />
      </div>

      {/* ── One-off AI Analyst (merged from the old /analyst page) ── */}
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '0 0 8px' }}>🧠 {T.analystSection}</div>
      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 12 }}>{T.analystSubtitle}</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            {T.symbol}
            <SymbolSelect market={anMarket} value={anSymbol} onChange={setAnSymbol} style={{ ...inp, width: 140 }} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            {T.market}
            <select value={anMarket} onChange={e => setAnMarket(e.target.value)} style={inp}>
              <option value="crypto">crypto</option>
              <option value="us-stock">us-stock</option>
            </select>
          </label>
          <button onClick={() => analyze.run(anSymbol, anMarket, language)} disabled={analyze.loading}
            style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: analyze.loading ? 'default' : 'pointer', opacity: analyze.loading ? 0.6 : 1 }}>
            {analyze.loading ? T.analystRunning : T.analystRun}
          </button>
        </div>

        {analyze.log.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <AnalysisMonitorPanel language={language} steps={analyze.steps} log={analyze.log} />
          </div>
        )}
        {analyze.error && <div style={{ color: '#f0663f', marginTop: 12, fontSize: 13 }}>⚠️ {analyze.error}</div>}

        {analyze.result && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginTop: 16 }}>
              <div style={{ fontSize: 24, fontWeight: 800, textTransform: 'uppercase', color: analyze.result.decision?.action === 'buy' ? '#3fb950' : analyze.result.decision?.action === 'sell' ? '#f0663f' : '#e3a008' }}>
                {analyze.result.decision?.action}
              </div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{analyze.result.symbol} · {analyze.result.market}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>
                {T.testConfidence}: <b>{Math.round((analyze.result.decision?.confidence ?? 0) * 100)}%</b> · {T.provider}: {analyze.result.llm_provider || T.analystNone}
              </div>
              <button onClick={() => startRunFromAnalysis(analyze.result.symbol, analyze.result.market)}
                disabled={runStartBusy}
                style={{ marginLeft: 'auto', padding: '8px 16px', borderRadius: 8, border: '1.5px solid var(--accent-primary,#c26a45)', background: 'rgba(194,106,69,0.12)', color: 'var(--accent-primary,#c26a45)', fontWeight: 700, fontSize: 13, cursor: runStartBusy ? 'default' : 'pointer', opacity: runStartBusy ? 0.6 : 1 }}>
                ▶ {T.startRunNow}
              </button>
            </div>
            {runStartErr && <div style={{ color: '#f0663f', marginTop: 10, fontSize: 12.5 }}>⚠️ {runStartErr}</div>}
            {analyze.result.decision?.report && (
              <p style={{ marginTop: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{analyze.result.decision.report}</p>
            )}
            {analyze.result.analysts && (
              <>
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '14px 0 10px' }}>{T.analystBriefs}</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 14 }}>
                  {Object.entries(analyze.result.analysts).map(([role, v]: any) => (
                    <div key={role} style={{ border: '1px solid var(--border-color,#d3c8b6)', borderRadius: 10, padding: 14 }}>
                      <div style={{ fontWeight: 700, marginBottom: 6 }}>{roleLabels[role] || role}</div>
                      <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--text-secondary,#5f574c)', whiteSpace: 'pre-wrap' }}>{v.brief}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.analystDisclaimer}</div>
          </>
        )}
      </div>

      {/* ── Mode selector ── */}
      <div ref={ruleFormRef} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <button style={chip(mode === 'agent')} onClick={() => setMode('agent')}>⓪ {T.modeAgent}</button>
        <button style={chip(mode === 'simple')} onClick={() => setMode('simple')}>① {T.modeSimple}</button>
        <button style={chip(mode === 'guided')} onClick={() => setMode('guided')}>② {T.modeGuided}</button>
        <button style={chip(mode === 'pro')} onClick={() => setMode('pro')}>③ {T.modePro}</button>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 14 }}>{modeDesc}</div>

      {/* Named config profiles (Plan 06 C3) — collapsed by default so it does
          not push the mode cards down for users who never save one. */}
      <ConfigProfiles token={token} />

      {/* ── Mode 0: Agent (full delegation) ── */}
      {mode === 'agent' && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 12 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              {T.budgetLabel}
              <input type="number" min={100} max={1000000} value={agentBudget}
                onChange={e => setAgentBudget(Number(e.target.value))}
                style={{ padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', width: 160 }} />
              <span style={{ fontSize: 11, color: 'var(--text-muted,#a89f92)' }}>💡 {T.budgetHint}</span>
            </label>
            <button onClick={addAgent} disabled={busy || agentBudget < 100}
              style={{ padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
              🤖 {T.startAgent}
            </button>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.agentKillNote}</div>

          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '18px 0 8px' }}>{T.agentDecisions}</div>
          {decisions.length === 0
            ? <div style={{ fontSize: 13, color: 'var(--text-muted,#a89f92)' }}>{T.noDecisions}</div>
            : decisions.map(d => {
              let p: any = {}
              try { p = JSON.parse(d.params_json || '{}') } catch { /* display raw */ }
              return (
                <div key={d.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-color)', fontSize: 12.5 }}>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontVariantNumeric: 'tabular-nums' }}>
                    <b>{p.symbol}</b>
                    <span>${p.size_usd}</span>
                    <span>{p.interval_minutes}m</span>
                    <span>≥{p.min_confidence}</span>
                    <span>{p.risk_level}</span>
                    <span style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>{d.planner === 'llm' ? (d.llm_model || 'AI') : 'fallback'} · {(d.decided_at || '').slice(5, 16).replace('T', ' ')}</span>
                  </div>
                  {d.rationale && <div style={{ color: 'var(--text-secondary,#8a8073)', marginTop: 3 }}>{d.rationale}</div>}
                </div>
              )
            })}
        </div>
      )}

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
            {fld(T.symbol, <SymbolSelect style={inp} market={draft.market} value={draft.symbol} onChange={symbol => setDraft({ ...draft, symbol })} />)}
            {fld(T.market, <select style={inp} value={draft.market} onChange={e => setDraft({ ...draft, market: e.target.value })}><option value="crypto">crypto</option><option value="us-stock">us-stock</option></select>)}
            {fld(T.provider, <select style={inp} value={draft.provider || ''} onChange={e => setDraft({ ...draft, provider: e.target.value || null })}><option value="">{T.serverDefault}</option>{['openai', 'gemini', 'grok', 'qwen', 'glm', 'local', 'anthropic'].map(p => <option key={p} value={p}>{p}</option>)}</select>)}
            {fld(T.interval, <input style={inp} type="number" min={5} value={draft.interval_minutes} onChange={e => setDraft({ ...draft, interval_minutes: +e.target.value })} />)}
            {fld(T.minConf, <input style={inp} type="number" step="0.05" min="0" max="1" value={draft.min_confidence} onChange={e => setDraft({ ...draft, min_confidence: +e.target.value })} />)}
            {fld(T.size, <input style={inp} type="number" value={draft.size_usd} onChange={e => setDraft({ ...draft, size_usd: +e.target.value })} />)}
            {fld(T.account, <select style={inp} value={normalizeAccountType(draft.account_type)} onChange={e => setDraft({ ...draft, account_type: e.target.value })}>{ACCOUNT_TYPES.map(a => <option key={a} value={a}>{a}</option>)}</select>)}
          </div>
          {/* schedule editor (Plan 06 C3) */}
          <div style={{ marginTop: 16, borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600 }}>
              <input type="checkbox" checked={schedOn} onChange={e => setSchedOn(e.target.checked)} /> {T.scheduleLabel}
            </label>
            {schedOn && (
              <div style={{ marginTop: 10 }}>
                <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 10 }}>
                  {DOW.map((d, i) => (
                    <button key={i} onClick={() => setSched(s => ({ ...s, days: s.days.includes(i) ? s.days.filter(x => x !== i) : [...s.days, i] }))}
                      style={{ padding: '5px 11px', borderRadius: 999, fontSize: 12.5, cursor: 'pointer',
                        border: sched.days.includes(i) ? '1.5px solid var(--accent-primary)' : '1px solid var(--border-color)',
                        background: sched.days.includes(i) ? 'rgba(57,135,229,0.14)' : 'transparent',
                        color: sched.days.includes(i) ? 'var(--accent-primary)' : 'inherit' }}>{d}</button>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 12.5, flexWrap: 'wrap' }}>
                  <span>{T.scheduleFrom} <input type="number" min={0} max={23} value={sched.start_hour} onChange={e => setSched(s => ({ ...s, start_hour: +e.target.value }))} style={{ ...inp, width: 62, padding: '6px 8px' }} />:00</span>
                  <span>{T.scheduleTo} <input type="number" min={0} max={24} value={sched.end_hour} onChange={e => setSched(s => ({ ...s, end_hour: +e.target.value }))} style={{ ...inp, width: 62, padding: '6px 8px' }} />:00</span>
                  <span style={{ color: 'var(--text-muted)' }}>{sched.tz}</span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 6 }}>💡 {T.scheduleHint}</div>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
              <input type="checkbox" checked={!!draft.auto_execute} onChange={e => setDraft({ ...draft, auto_execute: e.target.checked })} /> {T.autoEx}
            </label>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            <button onClick={() => postRule({ ...draft, schedule: schedOn ? sched : undefined } as Rule)} disabled={busy} style={{ marginLeft: 'auto', padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>+ {T.add}</button>
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted,#a89f92)', lineHeight: 1.5 }}>ⓘ {T.proHint}</div>
        </div>
      )}

      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '0 0 10px' }}>{T.yourRules}</div>
      {removeError && <div style={{ color: '#f0663f', fontSize: 12.5, marginBottom: 10 }}>⚠️ {removeError}</div>}
      {rules.length === 0 ? (
        <div className="card" style={{ color: 'var(--text-secondary,#8a8073)' }}>{T.empty}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rules.map((r) => {
            const testable = r.mode !== 'agent' && r.symbol !== 'SCANNER' && r.symbol !== 'AGENT'
            const testing = testRuleId === r.id
            return (
              <div key={r.id}>
                <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                  <b style={{ fontSize: 15 }}>{r.mode === 'agent' ? `🤖 ${T.modeAgent} · $${r.budget_usd}` : r.symbol === 'SCANNER' ? `🔍 ${T.coinAuto}` : r.symbol}</b>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>
                    {r.market} · {r.provider || T.serverDefault} · {r.interval_minutes}m · ≥{Math.round((r.min_confidence || 0) * 100)}% · ${r.size_usd} · {normalizeAccountType(r.account_type)}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: r.auto_execute ? 'rgba(63,185,80,0.16)' : 'rgba(138,128,115,0.18)', color: r.auto_execute ? '#3fb950' : '#8a8073' }}>
                    {r.auto_execute ? T.badgeAuto : T.badgeAnalysis}
                  </span>
                  {/* Real money is on the line here — never let it read the
                      same as a simulated rule at a glance. */}
                  {r.auto_execute && normalizeAccountType(r.account_type) === 'live' && (
                    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: 'rgba(240,102,63,0.18)', color: '#f0663f' }}>
                      ⚠ {T.liveMoney}
                    </span>
                  )}
                  {r.last_run_at && <span style={{ fontSize: 11, color: 'var(--text-secondary,#8a8073)' }}>last: {String(r.last_run_at).replace('T', ' ').slice(0, 16)}</span>}
                  {testable && (
                    <button onClick={() => { setTestRuleId(r.id ?? null); testRun.run(r.symbol, r.market, language, r.provider, r.id) }}
                      disabled={testRun.loading}
                      style={{ marginLeft: 'auto', padding: '6px 12px', borderRadius: 7, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: testRun.loading ? 'default' : 'pointer', fontSize: 12, opacity: testRun.loading ? 0.6 : 1 }}>
                      {testRun.loading && testing ? T.testRunning : `▶ ${T.testRun}`}
                    </button>
                  )}
                  <button onClick={() => remove(r.id)} style={{ marginLeft: testable ? 0 : 'auto', padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>{T.remove}</button>
                </div>
                {testing && (testRun.log.length > 0 || testRun.error) && (
                  <div className="card" style={{ marginTop: 8 }}>
                    <AnalysisMonitorPanel language={language} steps={testRun.steps} log={testRun.log} />
                    {testRun.error && <div style={{ color: '#f0663f', marginTop: 10, fontSize: 13 }}>⚠️ {testRun.error}</div>}
                    {testRun.result && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                        <b style={{ textTransform: 'uppercase', fontSize: 15, color: testRun.result.decision?.action === 'buy' ? '#3fb950' : testRun.result.decision?.action === 'sell' ? '#f0663f' : '#e3a008' }}>
                          {testRun.result.decision?.action}
                        </b>
                        <span style={{ fontSize: 13 }}>{T.testConfidence}: <b>{Math.round((testRun.result.decision?.confidence ?? 0) * 100)}%</b></span>
                        <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>{testRun.result.llm_provider || T.serverDefault}</span>
                      </div>
                    )}
                    {testRun.gates && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)' }}>{T.gateVerdict}:</span>
                        {testRun.gates.would_execute ? (
                          <span style={{ fontSize: 12, fontWeight: 700, padding: '3px 10px', borderRadius: 6, background: 'rgba(63,185,80,0.16)', color: '#3fb950' }}>
                            ✓ {T.wouldExecute} — {T.qty} {Number(testRun.gates.quantity).toFixed(6)}
                            {testRun.gates.stop_loss != null && ` · SL $${Number(testRun.gates.stop_loss).toFixed(2)}`}
                            {testRun.gates.take_profit != null && ` · TP $${Number(testRun.gates.take_profit).toFixed(2)}`}
                          </span>
                        ) : (
                          <span style={{ fontSize: 12, fontWeight: 700, padding: '3px 10px', borderRadius: 6, background: 'rgba(138,128,115,0.18)', color: '#8a8073' }}>
                            ⊘ {T.wouldSkip} — {skipLabel(testRun.gates.skip_reason)}
                          </span>
                        )}
                      </div>
                    )}
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 10 }}>ⓘ {T.testRunNote}</div>
                  </div>
                )}
              </div>
            )
          })}
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
