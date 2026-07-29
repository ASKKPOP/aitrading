import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { AnalysisMonitorPanel, useAnalysisRun } from '../components/AnalysisPipelineViz'
import { FleetPanel } from '../components/FleetPanel'
import { SymbolSelect } from '../components/SymbolSelect'
import { tr } from '../i18n'
import { RunsLiveSection } from './RunsLivePage'
import { fmtUsd, pnlColor } from './tradeShared'

// Automation (Target 3). The page itself is deliberately one block — the live
// TRADING grid — with two ways to make a new one sitting above it:
//
//   ① Make by New Trading — opens the runs section's create modal (it owns the
//     structured-409 conflict flow). Hanging off that same modal is the
//     automation-rule panel: agent delegation, the simple risk presets, and
//     the rule list whose Remove button is the kill switch for a running rule.
//   ② Make by AI Analyst — opens a modal that runs the one-off multi-agent
//     analysis (formerly the inline panel / the old /analyst page) and offers
//     "start auto-trading with this" on the result.
//
// Rules are backed by /api/automation/configs; the server worker runs each
// enabled rule on its interval and paper-trades when the decision clears it.
type Rule = {
  id?: number; symbol: string; market: string; provider: string | null; interval_minutes: number;
  min_confidence: number; size_usd: number; auto_execute: boolean | number; account_type: string;
  enabled?: boolean | number; last_run_at?: string | null; risk_level?: string | null;
  mode?: string; budget_usd?: number | null;
}

// Where a fill lands. Mirrors execution/gateway.py — keep the two in step.
//   simulator — platform ledger only, never contacts a broker
//   shadow    — runs by simulation; also mirrors to the broker's sandbox when
//               a gateway is connected, so you can compare real fills safely
//   live      — the real order goes to your configured trading gateway
const ACCOUNT_TYPES = ['simulator', 'shadow', 'live'] as const

// Rules created before the gateway landed store 'real'; show them as live.
const normalizeAccountType = (v: string | null | undefined): string =>
  v === 'real' ? 'live' : (ACCOUNT_TYPES as readonly string[]).includes(v || '') ? (v as string) : 'simulator'

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

// Simple-mode universe: the market's current top-5 by volume/popularity
// (Plan 11 F1, /api/markets/top-symbols); this static list is the fallback
// until the fetch lands (or when it fails).
const SIMPLE_COINS_FALLBACK = ['BTC', 'ETH', 'SOL']

export function AutomationPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()

  // Top-5 tradable universe for simple mode (fail-soft to the static fallback).
  useEffect(() => {
    fetch(`${API_BASE}/markets/top-symbols`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const coins = (d?.symbols || [])
          .map((s: any) => String(s.symbol || '').replace(/USDT$/, ''))
          .filter(Boolean)
        if (coins.length) setTopCoins(coins.slice(0, 5))
      })
      .catch(() => { /* keep fallback */ })
  }, [])

  const [rules, setRules] = useState<Rule[]>([])
  const [topCoins, setTopCoins] = useState<string[]>(SIMPLE_COINS_FALLBACK)
  const [ruleMode, setRuleMode] = useState<'agent' | 'simple' | 'fleet'>('simple')
  const [simpleCoin, setSimpleCoin] = useState<string>('BTC')
  const [simpleRisk, setSimpleRisk] = useState<RiskKey>('balanced')
  const [runLev, setRunLev] = useState(1)   // leverage for ⓪/① single-run modes
  const [agentBudget, setAgentBudget] = useState<number>(5000)
  const [error, setError] = useState('')
  const [removeError, setRemoveError] = useState('')
  const [busy, setBusy] = useState(false)

  // ① Make by New Trading — the modal lives in RunsLiveSection; bumping this
  // counter is how the button opens it.
  const [openCreate, setOpenCreate] = useState(0)

  // ② Make by AI Analyst — one-off run as a server-side background job, so
  // closing the modal and reopening it re-attaches to a run in flight.
  const [showAnalyst, setShowAnalyst] = useState(false)
  const [anSymbol, setAnSymbol] = useState('BTC')
  const [anMarket, setAnMarket] = useState('crypto')
  const analyze = useAnalysisRun(token)

  // Re-attached to an existing job (e.g. returning mid-run): mirror its
  // symbol/market in the controls so the monitor matches what it shows.
  useEffect(() => {
    if (analyze.runInfo) { setAnSymbol(analyze.runInfo.symbol); setAnMarket(analyze.runInfo.market) }
  }, [analyze.runInfo?.id])

  // One step (분석 → 자동매매): create a live trading run for the analyzed
  // symbol and start it immediately. Balanced defaults; full control stays in
  // the create modal.
  const [runStartBusy, setRunStartBusy] = useState(false)
  const [runStartErr, setRunStartErr] = useState('')
  const [runsReload, setRunsReload] = useState(0)

  // Fleet monitor → runs section: clicking a member card opens that TRADING's
  // full detail drawer (the drawer lives in RunsLiveSection).
  const [openRunReq, setOpenRunReq] = useState<{ id: number; nonce: number } | null>(null)

  // My Assets at a glance (same numbers as /assets: cash + position value,
  // unrealized from open positions, realized from closed trades).
  const [assets, setAssets] = useState<{ total: number; unrealized: number;
    realized: number; cash: number; inUse: number; since: string | null } | null>(null)
  useEffect(() => {
    if (!token) return
    let dead = false
    const loadAssets = async () => {
      try {
        const pos = await (await fetch(`${API_BASE}/positions`,
          { headers: { Authorization: `Bearer ${token}` } })).json()
        const positions = pos.positions || []
        const value = positions.reduce((s: number, p: any) =>
          s + Math.abs(p.quantity) * (p.current_price ?? p.entry_price ?? 0), 0)
        const unrealized = positions.reduce((s: number, p: any) => s + (p.pnl ?? 0), 0)
        const mine = await (await fetch(`${API_BASE}/positions/trades?limit=200`,
          { headers: { Authorization: `Bearer ${token}` } })).json()
        const mineTrades = mine.trades || []
        const realized = mineTrades.reduce(
          (s: number, t: any) => s + (t.pnl ?? 0), 0)
        // earliest trade = "lifetime" anchor (first automated activity)
        const since = mineTrades.reduce((min: string | null, t: any) => {
          const c = t.created_at
          return c && (!min || c < min) ? c : min
        }, null as string | null)
        const cash = pos.cash ?? 0
        if (!dead) setAssets({ total: cash + value, unrealized, realized, cash, inUse: value, since })
      } catch { /* transient */ }
    }
    loadAssets()
    const iv = setInterval(loadAssets, 10000)
    return () => { dead = true; clearInterval(iv) }
  }, [token])

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
        // A structured 409 carries {message, conflicts} — surface the honest
        // reason; the draft stays in the runs grid below, where its Start
        // button offers one-click conflict resolution.
        const detail = (await start.json().catch(() => null))?.detail
        setRunsReload(n => n + 1)
        const msg = typeof detail === 'string' ? detail : detail?.message
        throw new Error(msg || 'could not start run')
      }
      setRunsReload(n => n + 1)
      setShowAnalyst(false)
    } catch (e: any) { setRunStartErr(e.message) }
    setRunStartBusy(false)
  }

  const T = {
    title: tr(language, { ko: '자동화', en: 'Automation', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động hóa', id: 'Otomatisasi' }),
    subtitle: tr(language, { ko: 'AI가 설정한 일정에 따라 실행되며, 결정이 규칙에 부합할 때 모의 거래를 수행합니다', en: 'AI runs on your schedule and paper-trades when the decision meets your rules', ja: 'スケジュールに沿ってAIが自動売買', th: 'AI ทำงานตามเวลาและเทรดเมื่อเข้าเงื่อนไข', vi: 'AI chạy theo lịch và giao dịch khi đủ điều kiện', id: 'AI berjalan sesuai jadwal Anda dan melakukan paper trading ketika keputusannya memenuhi aturan Anda' }),
    myAssets: tr(language, { ko: '내 자산', en: 'My Assets', ja: '資産', th: 'ทรัพย์สิน', vi: 'Tài sản', id: 'Aset saya' }),
    assetsUnrealized: tr(language, { ko: '미실현', en: 'unrealized', ja: '含み', th: 'ยังไม่รับรู้', vi: 'chưa chốt', id: 'belum direalisasi' }),
    assetsRealized: tr(language, { ko: '실현', en: 'realized', ja: '実現', th: 'รับรู้แล้ว', vi: 'đã chốt', id: 'direalisasi' }),
    sumDeposit: tr(language, { ko: '현재 예치금', en: 'Current Deposit', ja: '現在の預入', th: 'เงินฝากปัจจุบัน', vi: 'Số dư hiện tại', id: 'Setoran saat ini' }),
    sumLifetime: tr(language, { ko: '운영 기간', en: 'Lifetime', ja: '運用期間', th: 'ระยะเวลา', vi: 'Thời gian hoạt động', id: 'Sepanjang waktu' }),
    sumProfit: tr(language, { ko: '총 수익', en: 'Profit', ja: '総収益', th: 'กำไรรวม', vi: 'Lợi nhuận', id: 'Keuntungan' }),
    sumCash: tr(language, { ko: '현금', en: 'cash', ja: '現金', th: 'เงินสด', vi: 'tiền mặt', id: 'kas' }),
    sumInUse: tr(language, { ko: '사용 중', en: 'in use', ja: '使用中', th: 'ใช้อยู่', vi: 'đang dùng', id: 'terpakai' }),
    sumSince: tr(language, { ko: '시작', en: 'since', ja: '開始', th: 'เริ่ม', vi: 'từ', id: 'sejak' }),
    sumDay: tr(language, { ko: '일', en: 'd', ja: '日', th: 'วัน', vi: 'ngày', id: 'h' }),
    sumHour: tr(language, { ko: '시간', en: 'h', ja: '時間', th: 'ชม.', vi: 'giờ', id: 'j' }),
    sumNoHistory: tr(language, { ko: '거래 내역 없음', en: 'no history yet', ja: '取引履歴なし', th: 'ยังไม่มีประวัติ', vi: 'chưa có lịch sử', id: 'belum ada riwayat' }),
    // ── the two entry points ──
    makeByTrading: tr(language, { ko: '새 TRADING으로 만들기', en: 'Make by New Trading', ja: '新しい TRADING で作成', th: 'สร้างด้วย TRADING ใหม่', vi: 'Tạo bằng TRADING mới', id: 'Buat lewat TRADING baru' }),
    makeByAnalyst: tr(language, { ko: 'AI 애널리스트로 만들기 — 지금 분석', en: 'Make by AI Analyst — analyze now', ja: 'AIアナリストで作成 — 今すぐ分析', th: 'สร้างด้วยนักวิเคราะห์ AI — วิเคราะห์ตอนนี้', vi: 'Tạo bằng nhà phân tích AI — phân tích ngay', id: 'Buat lewat Analis AI — analisis sekarang' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    symbol: tr(language, { ko: '종목', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã', id: 'Simbol' }),
    market: tr(language, { ko: '시장', en: 'Market', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường', id: 'Pasar' }),
    provider: tr(language, { ko: 'AI 제공자', en: 'AI provider', ja: 'AIプロバイダー', th: 'ผู้ให้บริการ AI', vi: 'Nhà cung cấp AI', id: 'Penyedia AI' }),
    serverDefault: tr(language, { ko: '서버 기본값', en: 'server default', ja: 'サーバー既定', th: 'ค่าเริ่มต้นเซิร์ฟเวอร์', vi: 'mặc định máy chủ', id: 'bawaan server' }),
    liveMoney: tr(language, { ko: '실제 자금', en: 'REAL MONEY', ja: '実資金', th: 'เงินจริง', vi: 'TIỀN THẬT', id: 'UANG SUNGGUHAN' }),
    badgeAuto: tr(language, { ko: '자동', en: 'auto', ja: '自動', th: 'อัตโนมัติ', vi: 'tự động', id: 'otomatis' }),
    badgeAnalysis: tr(language, { ko: '분석 전용', en: 'analysis only', ja: '分析のみ', th: 'วิเคราะห์เท่านั้น', vi: 'chỉ phân tích', id: 'hanya analisis' }),
    remove: tr(language, { ko: '제거', en: 'Remove', ja: '削除', th: 'ลบ', vi: 'Xóa', id: 'Hapus' }),
    removeFailed: tr(language, { ko: '규칙 제거에 실패했습니다 — 잠시 후 다시 시도하세요', en: 'Failed to remove the rule — try again shortly', ja: 'ルールの削除に失敗しました — しばらくして再試行してください', th: 'ลบกฎไม่สำเร็จ — ลองใหม่อีกครั้ง', vi: 'Xóa quy tắc thất bại — thử lại sau', id: 'Gagal menghapus aturan — coba lagi sebentar' }),
    yourRules: tr(language, { ko: '내 자동화 규칙', en: 'Your automation rules', ja: '自動売買ルール', th: 'กฎอัตโนมัติของคุณ', vi: 'Quy tắc của bạn', id: 'Aturan otomatisasi Anda' }),
    empty: tr(language, { ko: '아직 규칙이 없습니다. 위에서 추가하세요.', en: 'No rules yet. Add one above.', ja: 'ルールはまだありません。', th: 'ยังไม่มีกฎ', vi: 'Chưa có quy tắc.', id: 'Belum ada aturan. Tambahkan satu di atas.' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.', id: 'Silakan masuk.' }),
    // ── automation-rule panel (hangs off the create modal) ──
    ruleSection: tr(language, { ko: '또는 자동화 규칙 만들기 (AI가 일정에 따라 반복 실행)', en: 'Or create an automation rule (AI repeats it on a schedule)', ja: 'または自動売買ルールを作成（AIが定期実行）', th: 'หรือสร้างกฎอัตโนมัติ (AI ทำซ้ำตามเวลา)', vi: 'Hoặc tạo quy tắc tự động (AI lặp lại theo lịch)', id: 'Atau buat aturan otomatisasi (AI mengulanginya sesuai jadwal)' }),
    modeSimple: tr(language, { ko: '간편', en: 'Simple', ja: 'かんたん', th: 'ง่าย', vi: 'Đơn giản', id: 'Sederhana' }),
    modeAgent: tr(language, { ko: '1종목 위임', en: 'Agent (1 symbol)', ja: '1銘柄委任', th: 'มอบหมาย 1 เหรียญ', vi: 'Ủy quyền 1 mã', id: 'Agen (1 simbol)' }),
    modeFleet: tr(language, { ko: 'N종목 자동 편성', en: 'Full Auto', ja: '完全自動編成', th: 'อัตโนมัติเต็มรูปแบบ', vi: 'Tự động hoàn toàn', id: 'Full Auto' }),
    modeAgentDesc: tr(language, { ko: '예산만 정하세요 — AI가 종목을 골라 TRADING을 만들고, 매 사이클 매매 결정을 기록합니다', en: 'Set only a budget — the AI picks a symbol, creates the TRADING, and journals every cycle decision', ja: '予算だけ設定 — AIが銘柄を選んで TRADING を作成し、毎サイクルの判断を記録します', th: 'ตั้งแค่งบประมาณ — AI เลือกเหรียญ สร้าง TRADING และบันทึกการตัดสินใจทุกรอบ', vi: 'Chỉ đặt ngân sách — AI chọn mã, tạo TRADING và ghi lại quyết định mỗi chu kỳ', id: 'Cukup tetapkan anggaran — AI memilih simbol, membuat TRADING, dan mencatat setiap keputusan siklus' }),
    modeSimpleDesc: tr(language, { ko: '코인과 위험 성향만 고르세요 — 나머지는 AI가 알아서 합니다', en: 'Pick a coin and a risk level — AI handles the rest', ja: 'コインとリスクを選ぶだけ — あとはAIにおまかせ', th: 'เลือกเหรียญและระดับความเสี่ยง — ที่เหลือ AI จัดการ', vi: 'Chọn coin và mức rủi ro — AI lo phần còn lại', id: 'Pilih koin dan tingkat risiko — sisanya ditangani AI' }),
    budgetLabel: tr(language, { ko: '총 예산 ($)', en: 'Total budget ($)', ja: '総予算 ($)', th: 'งบประมาณรวม ($)', vi: 'Tổng ngân sách ($)', id: 'Total anggaran ($)' }),
    budgetHint: tr(language, { ko: 'AI가 배치할 수 있는 총 노출 한도 — 한 포지션은 예산의 25% 이하', en: 'Total exposure the AI may deploy — one position stays ≤ 25% of budget', ja: 'AIが展開できる総エクスポージャー上限 — 1ポジションは予算の25%以下', th: 'วงเงินรวมที่ AI ใช้ได้ — หนึ่งสถานะ ≤ 25% ของงบ', vi: 'Tổng mức AI được triển khai — một vị thế ≤ 25% ngân sách', id: 'Total eksposur yang boleh dipakai AI — satu posisi tetap ≤ 25% dari anggaran' }),
    startAgent: tr(language, { ko: 'AI에게 위임 시작', en: 'Start delegation', ja: '委任を開始', th: 'เริ่มมอบหมาย', vi: 'Bắt đầu ủy quyền', id: 'Mulai pendelegasian' }),
    agentKillNote: tr(language, { ko: '킬 스위치: 아래 TRADING 목록에서 중지하면 즉시 멈춥니다. 리스크 게이트·브레이커·예산 상한은 AI가 우회할 수 없습니다.', en: 'Kill switch: stop it from the TRADING list below and it halts instantly. The risk gate, breakers and budget cap cannot be bypassed by the AI.', ja: 'キルスイッチ: 下の TRADING 一覧から停止すれば即座に止まります。リスクゲート・ブレーカー・予算上限はAIが回避できません。', th: 'สวิตช์หยุด: หยุดจากรายการ TRADING ด้านล่างแล้วหยุดทันที AI ข้ามประตูความเสี่ยง เบรกเกอร์ และเพดานงบไม่ได้', vi: 'Công tắc dừng: dừng từ danh sách TRADING bên dưới là ngừng ngay. AI không thể vượt cổng rủi ro, breaker và trần ngân sách.', id: 'Tombol darurat: hentikan dari daftar TRADING di bawah dan semuanya berhenti seketika. Gerbang risiko, pemutus sirkuit, dan batas anggaran tidak dapat dilewati oleh AI.' }),
    coinAuto: tr(language, { ko: 'AI 자동 선택', en: 'AI auto-pick', ja: 'AI自動選択', th: 'AI เลือกให้', vi: 'AI tự chọn', id: 'Pilihan otomatis AI' }),
    coinAutoHint: tr(language, { ko: '스캐너가 거래량 급증·신규 상장에서 후보를 고릅니다', en: 'The scanner picks candidates from volume surges & new listings', ja: 'スキャナーが出来高急増・新規上場から選択', th: 'สแกนเนอร์เลือกจากปริมาณพุ่งและเหรียญใหม่', vi: 'Máy quét chọn từ khối lượng tăng vọt & niêm yết mới', id: 'Pemindai memilih kandidat dari lonjakan volume & pencatatan baru' }),
    topFiveHint: tr(language, { ko: '지금 거래량·관심도 상위 5개 종목입니다', en: 'The current top-5 symbols by volume & popularity', ja: '現在の出来高・注目度トップ5銘柄です', th: '5 อันดับเหรียญยอดนิยมตามปริมาณซื้อขายตอนนี้', vi: '5 mã hàng đầu theo khối lượng & mức quan tâm hiện tại', id: 'Lima simbol teratas saat ini berdasarkan volume & popularitas' }),
    riskLabel: tr(language, { ko: '위험 성향', en: 'Risk level', ja: 'リスク', th: 'ระดับความเสี่ยง', vi: 'Mức rủi ro', id: 'Tingkat risiko' }),
    riskStable: tr(language, { ko: '안정', en: 'Stable', ja: '安定', th: 'มั่นคง', vi: 'Ổn định', id: 'Stabil' }),
    riskBalanced: tr(language, { ko: '균형', en: 'Balanced', ja: 'バランス', th: 'สมดุล', vi: 'Cân bằng', id: 'Seimbang' }),
    riskAggressive: tr(language, { ko: '공격', en: 'Aggressive', ja: '積極', th: 'เชิงรุก', vi: 'Tích cực', id: 'Agresif' }),
    riskStableDesc: tr(language, { ko: '4시간마다 · 신뢰도 75%+ · $200', en: 'Every 4h · 75%+ confidence · $200', ja: '4時間毎 · 75%+ · $200', th: 'ทุก 4 ชม. · 75%+ · $200', vi: 'Mỗi 4h · 75%+ · $200', id: 'Setiap 4 jam · keyakinan 75%+ · $200' }),
    riskBalancedDesc: tr(language, { ko: '1시간마다 · 신뢰도 65%+ · $500', en: 'Every 1h · 65%+ confidence · $500', ja: '1時間毎 · 65%+ · $500', th: 'ทุก 1 ชม. · 65%+ · $500', vi: 'Mỗi 1h · 65%+ · $500', id: 'Setiap 1 jam · keyakinan 65%+ · $500' }),
    riskAggressiveDesc: tr(language, { ko: '30분마다 · 신뢰도 55%+ · $1,000', en: 'Every 30min · 55%+ confidence · $1,000', ja: '30分毎 · 55%+ · $1,000', th: 'ทุก 30 นาที · 55%+ · $1,000', vi: 'Mỗi 30 phút · 55%+ · $1.000', id: 'Setiap 30 menit · keyakinan 55%+ · $1.000' }),
    startAuto: tr(language, { ko: '자동매매 시작', en: 'Start auto-trading', ja: '自動売買を開始', th: 'เริ่มเทรดอัตโนมัติ', vi: 'Bắt đầu giao dịch tự động', id: 'Mulai trading otomatis' }),
    simpleNote: tr(language, { ko: '모의 자금으로 거래합니다 — 실제 돈이 아닙니다. 아래 TRADING 목록에서 언제든 중지할 수 있습니다.', en: 'Trades with simulated funds — not real money. Stop it anytime from the TRADING list below.', ja: 'シミュレーション資金で取引 — 実際のお金ではありません。下の TRADING 一覧からいつでも停止できます。', th: 'เทรดด้วยเงินจำลอง — ไม่ใช่เงินจริง หยุดได้ตลอดจากรายการ TRADING ด้านล่าง', vi: 'Giao dịch bằng vốn mô phỏng — không phải tiền thật. Dừng bất cứ lúc nào từ danh sách TRADING bên dưới.', id: 'Bertransaksi dengan dana simulasi — bukan uang sungguhan. Hentikan kapan saja dari daftar TRADING di bawah.' }),
    // ── AI Analyst modal ──
    analystSubtitle: tr(language, { ko: '네 명의 AI 애널리스트가 결정과 리포트를 두고 토론합니다 — 일회성 분석이며 주문은 실행되지 않습니다', en: 'Four AI analysts debate a decision + report — a one-off analysis, no order is placed', ja: '4人のAIアナリストが討議 — 1回限りの分析で、注文は出しません', th: 'นักวิเคราะห์ AI สี่คนถกเถียงเพื่อสรุปการตัดสินใจ — วิเคราะห์ครั้งเดียว ไม่ส่งคำสั่งซื้อขาย', vi: 'Bốn nhà phân tích AI tranh luận — phân tích một lần, không đặt lệnh', id: 'Empat analis AI mendebatkan sebuah keputusan + laporan — analisis sekali jalan, tidak ada order yang dipasang' }),
    analystRun: tr(language, { ko: '분석 실행', en: 'Run analysis', ja: '分析する', th: 'วิเคราะห์', vi: 'Phân tích', id: 'Jalankan analisis' }),
    analystRunning: tr(language, { ko: '애널리스트들이 토론 중…', en: 'Analysts are debating…', ja: '分析中…', th: 'กำลังวิเคราะห์…', vi: 'Đang phân tích…', id: 'Para analis sedang berdebat…' }),
    analystBriefs: tr(language, { ko: '애널리스트 브리프', en: 'Analyst briefs', ja: 'アナリスト概要', th: 'สรุปนักวิเคราะห์', vi: 'Tóm tắt phân tích', id: 'Ringkasan analis' }),
    analystNone: tr(language, { ko: '결정론적 (LLM 키 미설정)', en: 'deterministic (no LLM key set)', ja: 'LLM未設定', th: 'ไม่ได้ตั้งค่า LLM', vi: 'chưa đặt LLM', id: 'deterministik (kunci LLM belum diatur)' }),
    confidence: tr(language, { ko: '신뢰도', en: 'Confidence', ja: '信頼度', th: 'ความมั่นใจ', vi: 'Độ tin cậy', id: 'Keyakinan' }),
    startRunNow: tr(language, { ko: '이 설정으로 자동매매 시작', en: 'Start auto-trading with this', ja: 'この設定で自動売買開始', th: 'เริ่มเทรดอัตโนมัติด้วยค่านี้', vi: 'Bắt đầu tự động với thiết lập này', id: 'Mulai trading otomatis dengan ini' }),
    analystDisclaimer: tr(language, { ko: '리서치 목적일 뿐 — 투자 자문이 아닙니다.', en: 'Research only — not financial advice.', ja: '調査目的のみ — 投資助言ではありません。', th: 'เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน', vi: 'Chỉ nghiên cứu — không phải lời khuyên đầu tư.', id: 'Hanya riset — bukan nasihat keuangan.' }),
    // ── run creation from the two rule-panel modes ──
    createFailed: tr(language, { ko: 'TRADING을 만들지 못했습니다.', en: 'Could not create the TRADING.', ja: 'TRADING を作成できませんでした。', th: 'สร้าง TRADING ไม่สำเร็จ', vi: 'Không tạo được TRADING.', id: 'Tidak dapat membuat TRADING.' }),
    startFailed: tr(language, { ko: 'TRADING을 시작하지 못했습니다 — 아래 목록에서 확인하세요.', en: 'Could not start the TRADING — see the list below.', ja: 'TRADING を開始できませんでした — 下の一覧を確認してください。', th: 'เริ่ม TRADING ไม่สำเร็จ — ดูรายการด้านล่าง', vi: 'Không khởi động được TRADING — xem danh sách bên dưới.', id: 'Tidak dapat memulai TRADING — lihat daftar di bawah.' }),
    pickFailed: tr(language, { ko: '종목을 고르지 못했습니다 — 직접 선택하세요.', en: 'Could not pick a symbol — choose one yourself.', ja: '銘柄を選べませんでした — 手動で選択してください。', th: 'เลือกสัญลักษณ์ไม่สำเร็จ — เลือกเอง', vi: 'Không chọn được mã — hãy tự chọn.', id: 'Tidak dapat memilih simbol — pilih sendiri.' }),
  }

  const roleLabels: Record<string, string> = {
    news: tr(language, { ko: '뉴스', en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức', id: 'Berita' }),
    sentiment: tr(language, { ko: '심리', en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý', id: 'Sentimen' }),
    fundamentals_macro: tr(language, { ko: '펀더멘털 & 매크로', en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô', id: 'Fundamental & Makro' }),
    technical: tr(language, { ko: '기술적 분석', en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật', id: 'Teknikal' }),
  }

  const authHeaders: any = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }

  async function refresh() {
    try {
      const res = await fetch(`${API_BASE}/automation/configs`, { headers: authHeaders })
      if (res.ok) setRules((await res.json()).configs || [])
    } catch { /* transient */ }
  }

  useEffect(() => {
    if (!token) return
    refresh()
    const iv = setInterval(refresh, 30000)
    return () => clearInterval(iv)
  }, [token])

  // Both modes make a TRADING run, not an automation rule. A run already
  // carries interval/confidence/size and cycles on its own — it is everything
  // a rule provided, plus a per-run book, a lifecycle and events. Creating
  // both would also deadlock on itself: start refuses when an auto-executing
  // rule targets the same symbol (trading_runs.list_start_conflicts).
  async function createAndStartRun(body: Record<string, unknown>) {
    setBusy(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify({ market: 'crypto', market_type: 'spot', lang: language, ...body }),
      })
      const data = await res.json()
      if (!res.ok) {
        const detail = data.detail
        throw new Error((typeof detail === 'string' ? detail : detail?.message) || T.createFailed)
      }
      const start = await fetch(`${API_BASE}/runs/${data.id}/start`, { method: 'POST', headers: authHeaders })
      // The draft survives a refused start, so reload the grid either way —
      // it is where the conflict is resolved.
      setRunsReload(n => n + 1)
      if (!start.ok) {
        const detail = (await start.json().catch(() => null))?.detail
        throw new Error((typeof detail === 'string' ? detail : detail?.message) || T.startFailed)
      }
    } catch (e: any) { setError(e.message) }
    setBusy(false)
  }

  // 🔍 AI 자동 선택 and 완전 위임 name no symbol, but a run is bound to one.
  // Resolve it once at creation with the same picker the create form uses.
  async function pickSymbol(): Promise<string> {
    const r = await fetch(`${API_BASE}/markets/suggest-symbol`, {
      method: 'POST', headers: authHeaders,
    })
    if (!r.ok) throw new Error(T.pickFailed)
    const d = await r.json()
    if (!d?.symbol) throw new Error(T.pickFailed)
    return String(d.symbol)
  }

  async function addSimple() {
    const preset = RISK_PRESETS[simpleRisk]
    try {
      const symbol = simpleCoin === 'SCANNER' ? await pickSymbol() : simpleCoin
      await createAndStartRun({
        symbol,
        max_bet_usd: preset.size_usd,
        interval_minutes: preset.interval_minutes,
        min_confidence: preset.min_confidence,
        risk_level: simpleRisk,
        leverage: runLev,
      })
    } catch (e: any) { setError(e.message) }
  }

  // Budget becomes the run's cap; one position stays at the advertised 25%.
  async function addAgent() {
    try {
      const symbol = await pickSymbol()
      await createAndStartRun({
        symbol,
        max_bet_usd: Math.round(agentBudget * 0.25),
        run_budget_usd: agentBudget,
        interval_minutes: 60,
        min_confidence: 0.65,
        leverage: runLev,
      })
    } catch (e: any) { setError(e.message) }
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

  const chip = (active: boolean): any => ({
    padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 13, fontWeight: active ? 700 : 500,
    border: active ? '1.5px solid var(--accent-primary,#c26a45)' : '1px solid var(--border-color,#d3c8b6)',
    background: active ? 'rgba(194,106,69,0.12)' : 'transparent',
    color: active ? 'var(--accent-primary,#c26a45)' : 'inherit',
  })

  // Leverage picker shared by ⓪ 1종목 위임 and ① 간편 (isolated margin;
  // liquidation at a (100/L)% adverse move). 1× = fully funded.
  const leveragePicker = (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>
        {tr(language, { ko: '레버리지', en: 'Leverage', ja: 'レバレッジ', th: 'เลเวอเรจ', vi: 'Đòn bẩy', id: 'Leverage' })}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {[1, 2, 3, 5, 10].map(l => (
          <button key={l} style={chip(runLev === l)} onClick={() => setRunLev(l)}>
            {l === 1 ? tr(language, { ko: '1× 자동', en: '1× (none)', ja: '1×', th: '1×', vi: '1×', id: '1× (tanpa leverage)' }) : `${l}×`}
          </button>
        ))}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 6 }}>
        {runLev === 1
          ? tr(language, { ko: '레버리지 없음 — 완전 자금형(청산 없음).', en: 'No leverage — fully funded (no liquidation).', ja: 'レバレッジなし。', th: 'ไม่มีเลเวอเรจ', vi: 'Không đòn bẩy.', id: 'Tanpa leverage — didanai penuh (tidak ada likuidasi).' })
          : tr(language, { ko: `${runLev}배 격리 마진 — 같은 증거금으로 ${runLev}배 포지션, 진입가에서 ${(100 / runLev).toFixed(0)}% 역행 시 청산.`, en: `${runLev}× isolated margin — ${runLev}× the position for the same margin, liquidates on a ${(100 / runLev).toFixed(0)}% adverse move.`, ja: `${runLev}倍分離マージン、${(100 / runLev).toFixed(0)}%逆行で清算。`, th: `${runLev}× ล้างพอร์ตเมื่อสวน ${(100 / runLev).toFixed(0)}%`, vi: `${runLev}× thanh lý khi giá đi ngược ${(100 / runLev).toFixed(0)}%.`, id: `Margin terisolasi ${runLev}× — posisi ${runLev}× lipat dengan margin yang sama, terlikuidasi pada pergerakan berlawanan ${(100 / runLev).toFixed(0)}%.` })}
      </div>
    </div>
  )

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">⚙</div><div className="empty-title">{T.login}</div></div></div>
  }

  // Rule creation + the rule list, rendered inside the create modal under the
  // TRADING form. The list stays reachable there because Remove is the only
  // way to stop a running rule — it must never be more than one click away.
  const rulePanel = (
    <div style={{ marginTop: 16, background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 16 }}>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 10 }}>{T.ruleSection}</div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <button style={chip(ruleMode === 'agent')} onClick={() => setRuleMode('agent')}>⓪ {T.modeAgent}</button>
        <button style={chip(ruleMode === 'simple')} onClick={() => setRuleMode('simple')}>① {T.modeSimple}</button>
        <button style={chip(ruleMode === 'fleet')} onClick={() => setRuleMode('fleet')}>② {T.modeFleet}</button>
      </div>
      {ruleMode !== 'fleet' && (
        <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 14 }}>
          {ruleMode === 'agent' ? T.modeAgentDesc : T.modeSimpleDesc}
        </div>
      )}

      {ruleMode === 'fleet' && <FleetPanel token={token!} />}

      {ruleMode === 'agent' && (
        <>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 12 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              {T.budgetLabel}
              <input type="number" min={100} max={1000000} value={agentBudget}
                onChange={e => setAgentBudget(Number(e.target.value))}
                style={{ ...inp, width: 160 }} />
              <span style={{ fontSize: 11, color: 'var(--text-muted,#a89f92)' }}>💡 {T.budgetHint}</span>
            </label>
          </div>
          {leveragePicker}
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 12 }}>
            <button onClick={addAgent} disabled={busy || agentBudget < 100}
              style={{ padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
              🤖 {T.startAgent}
            </button>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.agentKillNote}</div>
        </>
      )}

      {ruleMode === 'simple' && (
        <>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>{T.symbol}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            {[...topCoins, 'SCANNER'].map(c => (
              <button key={c} style={chip(simpleCoin === c)} onClick={() => setSimpleCoin(c)}>
                {c === 'SCANNER' ? `🔍 ${T.coinAuto}` : c}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginBottom: 16 }}>{T.topFiveHint}</div>
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
          {leveragePicker}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.simpleNote}</span>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            <button onClick={addSimple} disabled={busy} style={{ marginLeft: 'auto', padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>▶ {T.startAuto}</button>
          </div>
        </>
      )}

      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '20px 0 10px' }}>{T.yourRules}</div>
      {removeError && <div style={{ color: '#f0663f', fontSize: 12.5, marginBottom: 10 }}>⚠️ {removeError}</div>}
      {rules.length === 0 ? (
        <div style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>{T.empty}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rules.map(r => (
            <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '10px 0', borderTop: '1px solid var(--border-color,#d3c8b6)' }}>
              <b style={{ fontSize: 14 }}>{r.mode === 'agent' ? `🤖 ${T.modeAgent} · $${r.budget_usd}` : r.symbol === 'SCANNER' ? `🔍 ${T.coinAuto}` : r.symbol}</b>
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
              <button onClick={() => remove(r.id)} style={{ marginLeft: 'auto', padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>{T.remove}</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  const primaryBtn: any = { padding: '12px 22px', borderRadius: 10, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer' }
  const secondaryBtn: any = { padding: '12px 22px', borderRadius: 10, border: '1.5px solid var(--accent-primary,#c26a45)', background: 'rgba(194,106,69,0.12)', color: 'var(--accent-primary,#c26a45)', fontWeight: 700, fontSize: 14, cursor: 'pointer' }

  // Account summary. Lives in the page header, right-aligned: it is reference
  // data you glance at, not the thing you came to do — the create buttons are.
  // Full-width tiles under the buttons pushed the actual TRADING list below
  // the fold on a laptop.
  const summaryStrip = assets && (() => {
    const profit = assets.realized + assets.unrealized
    let life: { d: number; h: number } | null = null
    if (assets.since) {
      const ms = Date.now() - new Date(assets.since.replace(' ', 'T')).getTime()
      if (ms > 0) life = { d: Math.floor(ms / 86400000), h: Math.floor((ms % 86400000) / 3600000) }
    }
    const tile: any = { minWidth: 140, background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 10, padding: '9px 13px' }
    const kSt: any = { fontSize: 10.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 3, whiteSpace: 'nowrap' }
    const vSt: any = { fontSize: 17, fontWeight: 800, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
    const sSt: any = { fontSize: 10, color: 'var(--text-muted,#a89f92)', marginTop: 2, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
    return (
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <Link to="/assets" style={{ ...tile, textDecoration: 'none', color: 'inherit' }}>
          <div style={kSt}>💰 {T.sumDeposit}</div>
          <div style={vSt}>{fmtUsd(assets.total)}</div>
          <div style={sSt}>{T.sumInUse} {fmtUsd(assets.inUse)} · {T.sumCash} {fmtUsd(assets.cash)}</div>
        </Link>
        <div style={tile}>
          <div style={kSt}>📅 {T.sumLifetime}</div>
          <div style={vSt}>{life ? <>{life.d}{T.sumDay} <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary,#8a8073)' }}>{life.h}{T.sumHour}</span></> : '—'}</div>
          <div style={sSt}>{assets.since ? `${assets.since.slice(0, 10)} ${T.sumSince}` : T.sumNoHistory}</div>
        </div>
        <div style={tile}>
          <div style={kSt}>📈 {T.sumProfit}</div>
          <div style={{ ...vSt, color: pnlColor(profit) }}>{profit >= 0 ? '+' : ''}{fmtUsd(profit)}</div>
          <div style={sSt}>{T.assetsRealized} {assets.realized >= 0 ? '+' : ''}{fmtUsd(assets.realized)} · {T.assetsUnrealized} {assets.unrealized >= 0 ? '+' : ''}{fmtUsd(assets.unrealized)}</div>
        </div>
      </div>
    )
  })()

  return (
    <div>
      <div className="header" style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
        {summaryStrip}
      </div>

      {/* ── The two ways to make one, above the block ── */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14, alignItems: 'stretch' }}>
        <button style={primaryBtn} onClick={() => setOpenCreate(n => n + 1)}>➕ {T.makeByTrading}</button>
        <button style={secondaryBtn} onClick={() => setShowAnalyst(true)}>🧠 {T.makeByAnalyst}</button>
      </div>


      {/* ── Full Auto fleet monitor — always visible once a fleet is live,
             so monitoring never requires reopening the create modal ── */}
      <FleetPanel token={token!} monitorOnly
        onSelectRun={(id) => setOpenRunReq(p => ({ id, nonce: (p?.nonce || 0) + 1 }))} />

      {/* ── The one block on this page ── */}
      <RunsLiveSection token={token} embedded reloadKey={runsReload}
        hideCreateButton openCreateSignal={openCreate} extraPanel={rulePanel}
        openRunRequest={openRunReq} />

      {/* ── ② Make by AI Analyst ── */}
      {showAnalyst && (
        <div role="dialog" aria-modal="true" aria-label={T.makeByAnalyst}
          onClick={() => setShowAnalyst(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: 24, overflowY: 'auto' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: '100%', maxWidth: 900, margin: 'auto', background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>🧠 {T.makeByAnalyst}</div>
                <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.analystSubtitle}</div>
              </div>
              <button onClick={() => setShowAnalyst(false)}
                style={{ padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>
                {T.close}
              </button>
            </div>

            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginTop: 16 }}>
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
                    {T.confidence}: <b>{Math.round((analyze.result.decision?.confidence ?? 0) * 100)}%</b> · {T.provider}: {analyze.result.llm_provider || T.analystNone}
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
        </div>
      )}
    </div>
  )
}

export default AutomationPage
