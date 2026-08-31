import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { API_BASE, useLanguage } from '../appShared'
import { planFeatures } from '../entitlements'
import { AnalysisMonitorPanel, analysisStepLabels, useAnalysisRun } from '../components/AnalysisPipelineViz'
import { DeskCyclesPanel } from '../components/DeskCyclesPanel'
import { FleetPanel } from '../components/FleetPanel'
import { SlotOutlookPanel } from '../components/SlotOutlookPanel'
import { MonitorPanel } from '../components/MonitorPanel'
import { HelpTip } from '../components/HelpTip'
import { SymbolSelect } from '../components/SymbolSelect'
import { fearGreedLabel, tr } from '../i18n'
import { RunsLiveSection } from './RunsLivePage'
import { fmtUsd, pnlColor, positionEquity, positionMargin } from './tradeShared'

// The day the fleet's exit rails were replaced: stops rescaled from the run
// budget to the position, plus the peak-tracked trailing lock. Trades before
// this ran under a structure that could not close itself, so a single
// lifetime P&L number reads as current performance when it is not.
const EXIT_RAILS_EPOCH = '2026-07-25'

// Calendar-period start in local time: today 00:00 / Monday / 1st / Jan 1.
// Shared by the summary fetch (as the server aggregate's `since`) and the
// strip's client-side window over the capped fill list.
const periodStartMs = (p: 'today' | 'week' | 'month' | 'year') => {
  const d = new Date(); d.setHours(0, 0, 0, 0)
  if (p === 'week') d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  else if (p === 'month') d.setDate(1)
  else if (p === 'year') { d.setMonth(0); d.setDate(1) }
  return d.getTime()
}

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
  // tp 16, not 15: the card must match RISK_LEVEL_PRESETS on the server, and
  // at 15 the 8/15 geometry graded 1.875 against the house RR_FLOOR of 2.0 —
  // the rr_floor gate refused every deferred-bracket entry on this profile.
  aggressive: { interval_minutes: 30,  min_confidence: 0.55, size_usd: 1000, sl: 8, tp: 16 },
} as const
type RiskKey = keyof typeof RISK_PRESETS

// Simple-mode universe: the market's current top-5 by volume/popularity
// (Plan 11 F1, /api/markets/top-symbols); this static list is the fallback
// until the fetch lands (or when it fails).
const SIMPLE_COINS_FALLBACK = ['BTC', 'ETH', 'SOL']

// Simple-mode US-stock universe (owner 2026-08-31: "make simple slot block
// need USA stock" + the hot-5 tech MUST rule): the chips are the 5 hottest
// US tech names from /api/markets/top-us-tech — the SAME hotness ranking the
// Full-Auto fleet's us-stock selection is restricted to. Static mega-cap
// fallback until the fetch lands (or when it fails).
const SIMPLE_US_TECH_FALLBACK = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'META']

export function AutomationPage({ planCode = null }: { planCode?: string | null }) {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  // Subscription-tier shape (server-enforced too; see entitlements.ts).
  const features = planFeatures(planCode)

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
    fetch(`${API_BASE}/markets/top-us-tech`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const stocks = (d?.symbols || []).map((s: any) => String(s)).filter(Boolean)
        if (stocks.length) setTopUsTech(stocks.slice(0, 5))
      })
      .catch(() => { /* keep fallback */ })
  }, [])

  const [rules, setRules] = useState<Rule[]>([])
  const [topCoins, setTopCoins] = useState<string[]>(SIMPLE_COINS_FALLBACK)
  const [ruleMode, setRuleMode] = useState<'agent' | 'simple' | 'fleet'>(
    () => planFeatures(planCode).simpleMode ? 'simple' : 'agent')
  // Plan resolves async (App fetches /users/me); clamp a mode the tier
  // doesn't include back to ⓪, which every tier has.
  useEffect(() => {
    if ((ruleMode === 'simple' && !features.simpleMode)
      || (ruleMode === 'fleet' && !features.fleetMode)) setRuleMode('agent')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planCode, ruleMode])
  const [simpleCoin, setSimpleCoin] = useState<string>('BTC')
  const [simpleRisk, setSimpleRisk] = useState<RiskKey>('balanced')
  // ① Simple market: crypto (24/7) or USA stock (hot-5 tech chips; spot-only
  // long book, so the futures/leverage picker is hidden in us-stock mode).
  const [simpleMarket, setSimpleMarket] = useState<'crypto' | 'us-stock'>('crypto')
  const [topUsTech, setTopUsTech] = useState<string[]>(SIMPLE_US_TECH_FALLBACK)
  const [runLev, setRunLev] = useState(1)   // leverage for ⓪/① single-run modes
  // Book type for ⓪/① single-run modes. A spot book is long-only cash — the
  // backend refuses leveraged spot with no stop (routes_runs
  // validate_run_payload), so leverage is only offered on futures books and
  // spot always submits 1×.
  const [runType, setRunType] = useState<'spot' | 'futures'>('spot')
  const [agentBudget, setAgentBudget] = useState<number>(5000)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [removeError, setRemoveError] = useState('')
  const [removingId, setRemovingId] = useState<number | null>(null)
  // Simulator / real-account context switch (top of page). Shares the
  // chrome's localStorage key. 'real' is only reachable when a trading
  // gateway is actually connected — picking it without one goes to /accounts.
  const [acctMode, setAcctMode] = useState<'simulator' | 'real'>(
    () => (localStorage.getItem('account_type') === 'real' ? 'real' : 'simulator'))
  const [gwBroker, setGwBroker] = useState<string | null>(null)
  const [acctBusy, setAcctBusy] = useState(false)
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  // ① Make by New Trading — the modal lives in RunsLiveSection; bumping this
  // counter is how the button opens it.
  const [openCreate, setOpenCreate] = useState(0)

  // ② Make by AI Analyst — one-off run as a server-side background job, so
  // closing the modal and reopening it re-attaches to a run in flight.
  const [showAnalyst, setShowAnalyst] = useState(false)

  // AI Analysis — the desk's own 30-minute cycles, read from the run journal.
  const [showCycles, setShowCycles] = useState(false)
  // Slot Strategy Outlook (Plan 26) — the desk's kept forward plan per slot.
  const [showOutlook, setShowOutlook] = useState(false)
  // Monitoring board — the old /monitor page, now opened from here.
  const [showMonitor, setShowMonitor] = useState(false)
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
  //
  // The lifetime realized figure spans two generations of exit rails. Runs
  // built before 2026-07-25 carried budget-scaled stops ($1,299–$2,596 on runs
  // that lost $60–$219, i.e. 13–24x the loss they actually took) and no
  // trailing lock at all, so nothing could ever close them but a manual
  // stop-all — that cohort is most of the lifetime loss and cannot recur.
  // Reporting it as one number reads as current performance. Show both.
  const [assets, setAssets] = useState<{ total: number; unrealized: number;
    realized: number; realizedCurrent: number; cash: number; inUse: number;
    since: string | null; trades: any[]; positions: any[]; summary: any } | null>(null)
  // Summary-strip period filter — scopes lifetime, profit and the rails tile
  // (deposit is a point-in-time balance no period can apply to). Each tile
  // opens a detail modal with the numbers behind it.
  const [sumPeriod, setSumPeriod] = useState<'today' | 'week' | 'month' | 'year'>('week')
  const [sumDetail, setSumDetail] = useState<null | 'deposit' | 'lifetime' | 'profit' | 'rails'>(null)
  // Profit-graph data for the open tile modal: hourly realized-P&L buckets
  // from the capless server aggregate (the 200-row trades list would flatten
  // a long window's oldest days — same trap as #219). Every tile charts the
  // active period window — day chart shows day data, week shows week data
  // (owner rule 2026-08-25: never mix other periods' data into a chart).
  const [seriesPts, setSeriesPts] = useState<Array<{ t: string; pnl: number; trades: number; split_pnl?: number }> | null>(null)
  useEffect(() => {
    if (!token || !sumDetail) { setSeriesPts(null); return }
    let dead = false
    const qs = `?since=${encodeURIComponent(new Date(periodStartMs(sumPeriod)).toISOString())}&split=${EXIT_RAILS_EPOCH}`
    fetch(`${API_BASE}/positions/trades/series${qs}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (!dead) setSeriesPts(d?.points ?? null) })
      .catch(() => { if (!dead) setSeriesPts(null) })
    return () => { dead = true }
  }, [token, sumDetail, sumPeriod])
  useEffect(() => {
    if (!token) return
    let dead = false
    const loadAssets = async () => {
      try {
        const auth = { headers: { Authorization: `Bearer ${token}` } }
        const sinceIso = new Date(periodStartMs(sumPeriod)).toISOString()
        // The three requests are independent, so they go out together. Chained
        // with await they cost three serial round-trips before the strip could
        // paint anything at all, and the strip is the first thing in the page
        // header — it must not wait on a queue of its own making. Each request
        // now pays network latency once, concurrently, instead of three times
        // end to end.
        //
        // The trades list is capped at 200 rows (server cap) — it feeds the
        // fill lists in the tile modals only. Every SUM comes from the
        // server-side aggregate, which has no row cap. That aggregate is
        // optional: if it fails, the capped-list sums below stand in, so it
        // resolves to null on error rather than sinking the whole batch.
        const [pos, mine, sm] = await Promise.all([
          fetch(`${API_BASE}/positions`, auth).then(r => r.json()),
          fetch(`${API_BASE}/positions/trades?limit=200`, auth).then(r => r.json()),
          fetch(`${API_BASE}/positions/trades/summary?since=${encodeURIComponent(sinceIso)}&split=${EXIT_RAILS_EPOCH}`,
            auth).then(r => r.json()).catch(() => null),
        ])
        const positions = pos.positions || []
        // Margin escrowed, NOT qty*price: notional counts the borrowed half
        // of a leveraged position as deposit (prod showed 1040.83 for a
        // 1000.93 book — the "extra" 39.90 was the broker's money).
        const value = positions.reduce((s: number, p: any) =>
          s + positionMargin(p), 0)
        const unrealized = positions.reduce((s: number, p: any) => s + (p.pnl ?? 0), 0)
        const mineTrades = mine.trades || []
        const summary: any = typeof sm?.pnl === 'number' ? sm : null
        const realized = summary ? summary.pnl : mineTrades.reduce(
          (s: number, t: any) => s + (t.pnl ?? 0), 0)
        const realizedCurrent = summary ? summary.split.pnl : mineTrades.reduce(
          (s: number, t: any) =>
            (t.created_at || '') >= EXIT_RAILS_EPOCH ? s + (t.pnl ?? 0) : s, 0)
        // earliest trade = "lifetime" anchor (first automated activity)
        const since = summary ? summary.first_trade : mineTrades.reduce(
          (min: string | null, t: any) => {
            const c = t.created_at
            return c && (!min || c < min) ? c : min
          }, null as string | null)
        const cash = pos.cash ?? 0
        if (!dead) setAssets({ total: cash + value + unrealized, unrealized, realized, realizedCurrent, cash, inUse: value, since, trades: mineTrades, positions, summary })
      } catch { /* transient */ }
    }
    loadAssets()
    const iv = setInterval(loadAssets, 10000)
    return () => { dead = true; clearInterval(iv) }
  }, [token, sumPeriod])

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
    sumCurrentRails: tr(language, { ko: '현재 청산 구조', en: 'current exit rails', ja: '現行の決済ルール', th: 'กติกาปิดสถานะปัจจุบัน', vi: 'cơ chế thoát hiện tại', id: 'aturan keluar saat ini' }),
    sumRailsSince: tr(language, { ko: '이후 실현', en: 'realized since', ja: '以降の実現', th: 'รับรู้แล้วตั้งแต่', vi: 'đã chốt từ', id: 'direalisasi sejak' }),
    aiAnalysis: tr(language, { ko: 'AI 분석 (30분)', en: 'AI Analysis (30 min)', ja: 'AI分析（30分）', th: 'การวิเคราะห์ AI (30 นาที)', vi: 'Phân tích AI (30 phút)', id: 'Analisis AI (30 menit)' }),
    slotOutlook: tr(language, { ko: '슬롯 전략 전망', en: 'Slot Strategy Outlook', ja: 'スロット戦略アウトルック', th: 'แผนกลยุทธ์ของสล็อต', vi: 'Triển vọng chiến lược slot', id: 'Prospek Strategi Slot' }),
    monitoring: tr(language, { ko: '모니터링', en: 'Monitoring', ja: 'モニタリング', th: 'การติดตาม', vi: 'Giám sát', id: 'Pemantauan' }),
    sumDeposit: tr(language, { ko: '현재 예치금', en: 'Current Deposit', ja: '現在の預入', th: 'เงินฝากปัจจุบัน', vi: 'Số dư hiện tại', id: 'Setoran saat ini' }),
    sumLifetime: tr(language, { ko: '운영 기간', en: 'Lifetime', ja: '運用期間', th: 'ระยะเวลา', vi: 'Thời gian hoạt động', id: 'Sepanjang waktu' }),
    sumProfit: tr(language, { ko: '총 수익', en: 'Profit', ja: '総収益', th: 'กำไรรวม', vi: 'Lợi nhuận', id: 'Keuntungan' }),
    sumNet: tr(language, { ko: '순', en: 'net', ja: '純', th: 'สุทธิ', vi: 'ròng', id: 'bersih' }),
    dGain: tr(language, { ko: '수익 합계 (+)', en: 'Gross gains (+)', ja: '利益合計 (+)', th: 'กำไรรวม (+)', vi: 'Tổng lãi (+)', id: 'Total untung (+)' }),
    dLoss: tr(language, { ko: '손실 합계 (−)', en: 'Gross losses (−)', ja: '損失合計 (−)', th: 'ขาดทุนรวม (−)', vi: 'Tổng lỗ (−)', id: 'Total rugi (−)' }),
    sumToday: tr(language, { ko: '오늘', en: 'Today', ja: '今日', th: 'วันนี้', vi: 'Hôm nay', id: 'Hari ini' }),
    sumWeek: tr(language, { ko: '이번 주', en: 'This week', ja: '今週', th: 'สัปดาห์นี้', vi: 'Tuần này', id: 'Minggu ini' }),
    sumMonth: tr(language, { ko: '이번 달', en: 'This month', ja: '今月', th: 'เดือนนี้', vi: 'Tháng này', id: 'Bulan ini' }),
    sumYear: tr(language, { ko: '올해', en: 'This year', ja: '今年', th: 'ปีนี้', vi: 'Năm nay', id: 'Tahun ini' }),
    sumCash: tr(language, { ko: '현금', en: 'cash', ja: '現金', th: 'เงินสด', vi: 'tiền mặt', id: 'kas' }),
    sumInUse: tr(language, { ko: '사용 중', en: 'in use', ja: '使用中', th: 'ใช้อยู่', vi: 'đang dùng', id: 'terpakai' }),
    sumSince: tr(language, { ko: '시작', en: 'since', ja: '開始', th: 'เริ่ม', vi: 'từ', id: 'sejak' }),
    sumDay: tr(language, { ko: '일', en: 'd', ja: '日', th: 'วัน', vi: 'ngày', id: 'h' }),
    sumHour: tr(language, { ko: '시간', en: 'h', ja: '時間', th: 'ชม.', vi: 'giờ', id: 'j' }),
    sumNoHistory: tr(language, { ko: '거래 내역 없음', en: 'no history yet', ja: '取引履歴なし', th: 'ยังไม่มีประวัติ', vi: 'chưa có lịch sử', id: 'belum ada riwayat' }),
    // ── tile detail modals ──
    dHint: tr(language, { ko: '클릭하면 상세 보기', en: 'click for details', ja: 'クリックで詳細', th: 'คลิกเพื่อดูรายละเอียด', vi: 'nhấn để xem chi tiết', id: 'klik untuk detail' }),
    dOpenPositions: tr(language, { ko: '보유 포지션', en: 'Open positions', ja: '保有ポジション', th: 'สถานะที่ถืออยู่', vi: 'Vị thế đang mở', id: 'Posisi terbuka' }),
    dNoPositions: tr(language, { ko: '열린 포지션 없음', en: 'no open positions', ja: '保有ポジションなし', th: 'ไม่มีสถานะเปิดอยู่', vi: 'không có vị thế mở', id: 'tidak ada posisi terbuka' }),
    dGoAssets: tr(language, { ko: '자산 페이지 전체 보기 →', en: 'Open the full assets page →', ja: '資産ページを開く →', th: 'เปิดหน้าทรัพย์สินทั้งหมด →', vi: 'Mở trang tài sản đầy đủ →', id: 'Buka halaman aset lengkap →' }),
    dFirstTrade: tr(language, { ko: '첫 자동매매', en: 'First automated trade', ja: '最初の自動売買', th: 'เทรดอัตโนมัติครั้งแรก', vi: 'Giao dịch tự động đầu tiên', id: 'Perdagangan otomatis pertama' }),
    dTotalSpan: tr(language, { ko: '총 운영 기간', en: 'Total lifetime', ja: '総運用期間', th: 'ระยะเวลารวม', vi: 'Tổng thời gian hoạt động', id: 'Total masa operasi' }),
    dWindowSpan: tr(language, { ko: '선택 기간 내 운영', en: 'Operated within selected period', ja: '選択期間内の運用', th: 'ดำเนินการในช่วงที่เลือก', vi: 'Hoạt động trong kỳ đã chọn', id: 'Beroperasi dalam periode terpilih' }),
    dTradeCount: tr(language, { ko: '기간 내 체결', en: 'Fills in period', ja: '期間内の約定', th: 'รายการจับคู่ในช่วงเวลา', vi: 'Lệnh khớp trong kỳ', id: 'Eksekusi dalam periode' }),
    dLastTrade: tr(language, { ko: '마지막 체결', en: 'Last fill', ja: '直近の約定', th: 'จับคู่ล่าสุด', vi: 'Lệnh khớp gần nhất', id: 'Eksekusi terakhir' }),
    dRealizedPeriod: tr(language, { ko: '실현 손익 (기간)', en: 'Realized P&L (period)', ja: '実現損益（期間）', th: 'กำไรที่รับรู้ (ช่วงเวลา)', vi: 'Lãi/lỗ đã chốt (kỳ)', id: 'Laba rugi direalisasi (periode)' }),
    dUnrealizedNow: tr(language, { ko: '미실현 손익 (현재 보유)', en: 'Unrealized P&L (current open book)', ja: '含み損益（現在の保有）', th: 'กำไรที่ยังไม่รับรู้ (สถานะปัจจุบัน)', vi: 'Lãi/lỗ chưa chốt (vị thế hiện tại)', id: 'Laba rugi belum direalisasi (posisi saat ini)' }),
    dRealizedLife: tr(language, { ko: '실현 손익 (전체)', en: 'Realized P&L (lifetime)', ja: '実現損益（累計）', th: 'กำไรที่รับรู้ (ทั้งหมด)', vi: 'Lãi/lỗ đã chốt (toàn bộ)', id: 'Laba rugi direalisasi (sepanjang waktu)' }),
    dUnrealNote: tr(language, {
      ko: '미실현은 지금 열려 있는 포지션의 평가손익입니다 — 기간 필터와 무관하게 항상 현재 기준입니다.',
      en: 'Unrealized is the mark-to-market of the positions open right now — always current, regardless of the period filter.',
      ja: '含み損益は現在保有中のポジションの評価損益です — 期間フィルタに関係なく常に現時点の値です。',
      th: 'กำไรที่ยังไม่รับรู้คือมูลค่าตลาดของสถานะที่เปิดอยู่ตอนนี้ — เป็นค่าปัจจุบันเสมอ ไม่ขึ้นกับตัวกรองช่วงเวลา',
      vi: 'Lãi/lỗ chưa chốt là giá trị thị trường của các vị thế đang mở — luôn là số hiện tại, không phụ thuộc bộ lọc kỳ.',
      id: 'Belum direalisasi adalah nilai pasar posisi yang terbuka saat ini — selalu terkini, terlepas dari filter periode.' }),
    dFills: tr(language, { ko: '기간 내 체결 내역', en: 'Fills in this period', ja: '期間内の約定履歴', th: 'รายการจับคู่ในช่วงนี้', vi: 'Lệnh khớp trong kỳ này', id: 'Eksekusi pada periode ini' }),
    dNoFills: tr(language, { ko: '기간 내 체결 없음', en: 'no fills in this period', ja: '期間内の約定なし', th: 'ไม่มีรายการจับคู่ในช่วงนี้', vi: 'không có lệnh khớp trong kỳ này', id: 'tidak ada eksekusi pada periode ini' }),
    dRailsWhat: tr(language, {
      ko: `${EXIT_RAILS_EPOCH}에 청산 구조가 교체되었습니다. 이전 구조는 손절 폭이 예산 기준으로 과도하게 넓어 포지션을 스스로 닫지 못했고, 누적 손실의 대부분이 그 구간에서 발생했습니다. 이 숫자는 현행 구조(포지션 기준 손절 + 트레일링 락)에서의 실현 손익만 분리한 것입니다.`,
      en: `The exit rails were replaced on ${EXIT_RAILS_EPOCH}. The old structure sized stops off the run budget — too wide to ever close a position on its own — and most of the lifetime loss comes from that cohort. This figure isolates realized P&L under the current rails (position-scaled stops + trailing lock).`,
      ja: `${EXIT_RAILS_EPOCH} に決済ルールが刷新されました。旧ルールは損切り幅が予算基準で広すぎて自らポジションを閉じられず、累計損失の大半はその期間のものです。この数字は現行ルール（ポジション基準の損切り＋トレーリングロック）での実現損益だけを切り出したものです。`,
      th: `กติกาปิดสถานะถูกเปลี่ยนเมื่อ ${EXIT_RAILS_EPOCH} โครงสร้างเดิมตั้งจุดตัดขาดทุนตามงบของรอบซึ่งกว้างเกินกว่าจะปิดสถานะเองได้ และการขาดทุนสะสมส่วนใหญ่มาจากช่วงนั้น ตัวเลขนี้แยกเฉพาะกำไรที่รับรู้ภายใต้กติกาปัจจุบัน (ตัดขาดทุนตามขนาดสถานะ + trailing lock)`,
      vi: `Cơ chế thoát lệnh được thay thế ngày ${EXIT_RAILS_EPOCH}. Cơ chế cũ đặt mức cắt lỗ theo ngân sách của phiên — quá rộng để tự đóng vị thế — và phần lớn khoản lỗ tích lũy đến từ giai đoạn đó. Con số này tách riêng lãi/lỗ đã chốt dưới cơ chế hiện tại (cắt lỗ theo vị thế + trailing lock).`,
      id: `Aturan keluar diganti pada ${EXIT_RAILS_EPOCH}. Struktur lama menetapkan stop berdasarkan anggaran run — terlalu lebar untuk pernah menutup posisi sendiri — dan sebagian besar kerugian kumulatif berasal dari masa itu. Angka ini memisahkan laba rugi direalisasi di bawah aturan saat ini (stop berskala posisi + trailing lock).` }),
    dRailsCur: tr(language, { ko: '현행 구조 실현 (전체)', en: 'Current rails, realized (all)', ja: '現行ルールの実現（累計）', th: 'กติกาปัจจุบัน รับรู้แล้ว (ทั้งหมด)', vi: 'Cơ chế hiện tại, đã chốt (toàn bộ)', id: 'Aturan saat ini, direalisasi (semua)' }),
    dRailsOld: tr(language, { ko: '이전 구조 실현', en: 'Legacy rails, realized', ja: '旧ルールの実現', th: 'กติกาเดิม รับรู้แล้ว', vi: 'Cơ chế cũ, đã chốt', id: 'Aturan lama, direalisasi' }),
    dRailsWin: tr(language, { ko: '현행 구조 실현 (기간)', en: 'Current rails, realized (period)', ja: '現行ルールの実現（期間）', th: 'กติกาปัจจุบัน รับรู้แล้ว (ช่วงเวลา)', vi: 'Cơ chế hiện tại, đã chốt (kỳ)', id: 'Aturan saat ini, direalisasi (periode)' }),
    // ── tile detail modal graphs ──
    gProfit: tr(language, { ko: '누적 실현 손익', en: 'Cumulative realized P&L', ja: '累積実現損益', th: 'กำไรรับรู้สะสม', vi: 'Lãi/lỗ đã chốt lũy kế', id: 'Laba rugi direalisasi kumulatif' }),
    gDeposit: tr(language, { ko: '예치금 추이', en: 'Deposit over time', ja: '預入残高の推移', th: 'เงินฝากตามช่วงเวลา', vi: 'Số dư theo thời gian', id: 'Setoran dari waktu ke waktu' }),
    gDepositNote: tr(language, {
      ko: '실현 체결 기준으로 재구성한 추정 곡선입니다 — 미실현 평가 변동은 포함하지 않습니다.',
      en: 'Reconstructed from realized fills — an estimate that excludes unrealized mark-to-market swings.',
      ja: '実現約定から再構成した推定曲線です — 含み損益の変動は含みません。',
      th: 'สร้างขึ้นใหม่จากรายการที่รับรู้แล้ว — เป็นค่าประมาณ ไม่รวมความผันผวนของกำไรที่ยังไม่รับรู้',
      vi: 'Tái dựng từ các lệnh đã chốt — là ước tính, không gồm biến động lãi/lỗ chưa chốt.',
      id: 'Direkonstruksi dari eksekusi yang direalisasi — perkiraan yang tidak mencakup fluktuasi belum direalisasi.' }),
    gRails: tr(language, { ko: '누적 실현 손익 (현행 구조)', en: 'Cumulative realized P&L (current rails)', ja: '累積実現損益（現行ルール）', th: 'กำไรรับรู้สะสม (กติกาปัจจุบัน)', vi: 'Lãi/lỗ đã chốt lũy kế (cơ chế hiện tại)', id: 'Laba rugi direalisasi kumulatif (aturan saat ini)' }),
    gNoData: tr(language, { ko: '그래프를 그릴 체결이 부족합니다', en: 'not enough fills to draw a graph', ja: 'グラフを描くには約定が不足しています', th: 'รายการไม่พอสำหรับวาดกราฟ', vi: 'chưa đủ lệnh khớp để vẽ biểu đồ', id: 'eksekusi belum cukup untuk menggambar grafik' }),
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
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.', id: 'Silakan masuk.' }),
    // ── automation-rule panel (hangs off the create modal) ──
    ruleSection: tr(language, { ko: '자동화 만들기 (AI가 일정에 따라 반복 실행)', en: 'Create automation (AI repeats it on a schedule)', ja: '自動売買を作成（AIが定期実行）', th: 'สร้างระบบอัตโนมัติ (AI ทำซ้ำตามเวลา)', vi: 'Tạo tự động hóa (AI lặp lại theo lịch)', id: 'Buat otomatisasi (AI mengulanginya sesuai jadwal)' }),
    modeSimple: tr(language, { ko: '간편', en: 'Simple', ja: 'かんたん', th: 'ง่าย', vi: 'Đơn giản', id: 'Sederhana' }),
    modeAgent: tr(language, { ko: '1종목 위임', en: 'Agent (1 symbol)', ja: '1銘柄委任', th: 'มอบหมาย 1 เหรียญ', vi: 'Ủy quyền 1 mã', id: 'Agen (1 simbol)' }),
    modeFleet: tr(language, { ko: 'N종목 자동 편성', en: 'Full Auto', ja: '完全自動編成', th: 'อัตโนมัติเต็มรูปแบบ', vi: 'Tự động hoàn toàn', id: 'Full Auto' }),
    modeAgentDesc: tr(language, { ko: '예산만 정하세요 — AI가 종목을 골라 TRADING을 만들고, 매 사이클 매매 결정을 기록합니다', en: 'Set only a budget — the AI picks a symbol, creates the TRADING, and journals every cycle decision', ja: '予算だけ設定 — AIが銘柄を選んで TRADING を作成し、毎サイクルの判断を記録します', th: 'ตั้งแค่งบประมาณ — AI เลือกเหรียญ สร้าง TRADING และบันทึกการตัดสินใจทุกรอบ', vi: 'Chỉ đặt ngân sách — AI chọn mã, tạo TRADING và ghi lại quyết định mỗi chu kỳ', id: 'Cukup tetapkan anggaran — AI memilih simbol, membuat TRADING, dan mencatat setiap keputusan siklus' }),
    modeSimpleDesc: tr(language, { ko: '코인이나 미국 주식과 위험 성향만 고르세요 — 나머지는 AI가 알아서 합니다', en: 'Pick a coin or a US stock and a risk level — AI handles the rest', ja: 'コインか米国株とリスクを選ぶだけ — あとはAIにおまかせ', th: 'เลือกเหรียญหรือหุ้นสหรัฐและระดับความเสี่ยง — ที่เหลือ AI จัดการ', vi: 'Chọn coin hoặc cổ phiếu Mỹ và mức rủi ro — AI lo phần còn lại', id: 'Pilih koin atau saham AS dan tingkat risiko — sisanya ditangani AI' }),
    budgetLabel: tr(language, { ko: '총 예산 ($)', en: 'Total budget ($)', ja: '総予算 ($)', th: 'งบประมาณรวม ($)', vi: 'Tổng ngân sách ($)', id: 'Total anggaran ($)' }),
    budgetHint: tr(language, { ko: 'AI가 배치할 수 있는 총 노출 한도 — 한 포지션은 예산의 25% 이하', en: 'Total exposure the AI may deploy — one position stays ≤ 25% of budget', ja: 'AIが展開できる総エクスポージャー上限 — 1ポジションは予算の25%以下', th: 'วงเงินรวมที่ AI ใช้ได้ — หนึ่งสถานะ ≤ 25% ของงบ', vi: 'Tổng mức AI được triển khai — một vị thế ≤ 25% ngân sách', id: 'Total eksposur yang boleh dipakai AI — satu posisi tetap ≤ 25% dari anggaran' }),
    startAgent: tr(language, { ko: 'AI에게 위임 시작', en: 'Start delegation', ja: '委任を開始', th: 'เริ่มมอบหมาย', vi: 'Bắt đầu ủy quyền', id: 'Mulai pendelegasian' }),
    agentKillNote: tr(language, { ko: '킬 스위치: 아래 TRADING 목록에서 중지하면 즉시 멈춥니다. 리스크 게이트·브레이커·예산 상한은 AI가 우회할 수 없습니다.', en: 'Kill switch: stop it from the TRADING list below and it halts instantly. The risk gate, breakers and budget cap cannot be bypassed by the AI.', ja: 'キルスイッチ: 下の TRADING 一覧から停止すれば即座に止まります。リスクゲート・ブレーカー・予算上限はAIが回避できません。', th: 'สวิตช์หยุด: หยุดจากรายการ TRADING ด้านล่างแล้วหยุดทันที AI ข้ามประตูความเสี่ยง เบรกเกอร์ และเพดานงบไม่ได้', vi: 'Công tắc dừng: dừng từ danh sách TRADING bên dưới là ngừng ngay. AI không thể vượt cổng rủi ro, breaker và trần ngân sách.', id: 'Tombol darurat: hentikan dari daftar TRADING di bawah dan semuanya berhenti seketika. Gerbang risiko, pemutus sirkuit, dan batas anggaran tidak dapat dilewati oleh AI.' }),
    coinAuto: tr(language, { ko: 'AI 자동 선택', en: 'AI auto-pick', ja: 'AI自動選択', th: 'AI เลือกให้', vi: 'AI tự chọn', id: 'Pilihan otomatis AI' }),
    coinAutoHint: tr(language, { ko: '스캐너가 거래량 급증·신규 상장에서 후보를 고릅니다', en: 'The scanner picks candidates from volume surges & new listings', ja: 'スキャナーが出来高急増・新規上場から選択', th: 'สแกนเนอร์เลือกจากปริมาณพุ่งและเหรียญใหม่', vi: 'Máy quét chọn từ khối lượng tăng vọt & niêm yết mới', id: 'Pemindai memilih kandidat dari lonjakan volume & pencatatan baru' }),
    topFiveHint: tr(language, { ko: '지금 거래량·관심도 상위 5개 종목입니다', en: 'The current top-5 symbols by volume & popularity', ja: '現在の出来高・注目度トップ5銘柄です', th: '5 อันดับเหรียญยอดนิยมตามปริมาณซื้อขายตอนนี้', vi: '5 mã hàng đầu theo khối lượng & mức quan tâm hiện tại', id: 'Lima simbol teratas saat ini berdasarkan volume & popularitas' }),
    simpleMarketLabel: tr(language, { ko: '시장', en: 'Market', ja: '市場', th: 'ตลาด', vi: 'Thị trường', id: 'Pasar' }),
    marketCrypto: tr(language, { ko: '크립토', en: 'Crypto', ja: '暗号資産', th: 'คริปโต', vi: 'Crypto', id: 'Kripto' }),
    marketUsStock: tr(language, { ko: '미국 주식', en: 'US Stock', ja: '米国株', th: 'หุ้นสหรัฐ', vi: 'Cổ phiếu Mỹ', id: 'Saham AS' }),
    usTechHint: tr(language, { ko: '지금 가장 이슈가 뜨거운 미국 테크 5종목 (2일 변동 × 거래량 기준) — 현물 매수 전용, 정규장에서만 거래합니다', en: 'The 5 hottest US tech stocks right now (2-day move × volume) — spot long-only, trades during market hours', ja: '今最も話題の米国テック5銘柄（2日変動×出来高基準）— 現物買いのみ、取引時間中のみ売買', th: 'หุ้นเทคสหรัฐที่ร้อนแรงสุด 5 ตัวตอนนี้ (การเคลื่อนไหว 2 วัน × ปริมาณ) — ซื้อสปอตเท่านั้น เทรดเฉพาะเวลาทำการ', vi: '5 cổ phiếu công nghệ Mỹ nóng nhất hiện tại (biến động 2 ngày × khối lượng) — chỉ mua giao ngay, giao dịch trong giờ thị trường', id: '5 saham teknologi AS terpanas saat ini (pergerakan 2 hari × volume) — hanya beli spot, berdagang selama jam pasar' }),
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
    // ── decision detail (component scores · verification · order intent) ──
    decisionDetail: tr(language, { ko: '결정 상세', en: 'Decision detail', ja: '判断の詳細', th: 'รายละเอียดการตัดสินใจ', vi: 'Chi tiết quyết định', id: 'Detail keputusan' }),
    scoreThesis: tr(language, { ko: '논지 정합', en: 'Thesis alignment', ja: '論旨整合', th: 'สอดคล้องธีสิส', vi: 'Khớp luận điểm', id: 'Keselarasan tesis' }),
    scoreMomentum: tr(language, { ko: '모멘텀 질', en: 'Momentum quality', ja: '勢いの質', th: 'คุณภาพโมเมนตัม', vi: 'Chất lượng đà', id: 'Kualitas momentum' }),
    scoreEntry: tr(language, { ko: '진입 질', en: 'Entry quality', ja: 'エントリーの質', th: 'คุณภาพจุดเข้า', vi: 'Chất lượng điểm vào', id: 'Kualitas entry' }),
    scoreRisk: tr(language, { ko: '리스크 맥락', en: 'Risk context', ja: 'リスク文脈', th: 'บริบทความเสี่ยง', vi: 'Bối cảnh rủi ro', id: 'Konteks risiko' }),
    verifyLabel: tr(language, { ko: '검증', en: 'Verification', ja: '検証', th: 'การตรวจสอบ', vi: 'Kiểm chứng', id: 'Verifikasi' }),
    orderIntentLabel: tr(language, { ko: '주문 의도', en: 'Order intent', ja: '注文意図', th: 'เจตนาออเดอร์', vi: 'Ý định lệnh', id: 'Niat order' }),
    targetLabel: tr(language, { ko: '목표가', en: 'Target', ja: '目標値', th: 'เป้าหมาย', vi: 'Mục tiêu', id: 'Target' }),
    stopLabel: tr(language, { ko: '손절가', en: 'Stop', ja: '損切り', th: 'จุดตัดขาดทุน', vi: 'Cắt lỗ', id: 'Stop' }),
    suggestedEntryLabel: tr(language, { ko: '제안 진입가', en: 'Suggested entry', ja: '提案エントリー', th: 'จุดเข้าที่แนะนำ', vi: 'Điểm vào đề xuất', id: 'Entry usulan' }),
    ruleFallback: tr(language, { ko: '규칙 기반 결정 — AI가 결정하지 않았습니다', en: 'Rule-based decision — not authored by the AI', ja: 'ルールベース判断 — AIによる判断ではありません', th: 'ตัดสินโดยกฎ — ไม่ใช่การตัดสินของ AI', vi: 'Quyết định theo quy tắc — không phải do AI', id: 'Keputusan berbasis aturan — bukan dari AI' }),
    // ── brief-card data chips ──
    chipHeadlines: tr(language, { ko: '헤드라인', en: 'headlines', ja: '見出し', th: 'พาดหัว', vi: 'tin', id: 'berita' }),
    chipFearGreed: tr(language, { ko: '공포·탐욕', en: 'Fear&Greed', ja: '恐怖強欲', th: 'Fear&Greed', vi: 'Fear&Greed', id: 'Fear&Greed' }),
    chipWhale: tr(language, { ko: '고래 이벤트', en: 'whale events', ja: 'クジラ動向', th: 'ธุรกรรมวาฬ', vi: 'giao dịch cá voi', id: 'aktivitas whale' }),
    chipMacro: tr(language, { ko: '매크로', en: 'Macro', ja: 'マクロ', th: 'มหภาค', vi: 'Vĩ mô', id: 'Makro' }),
    chipPrice: tr(language, { ko: '현재가', en: 'Price', ja: '現在値', th: 'ราคา', vi: 'Giá', id: 'Harga' }),
    chipSignal: tr(language, { ko: '시그널', en: 'Signal', ja: 'シグナル', th: 'สัญญาณ', vi: 'Tín hiệu', id: 'Sinyal' }),
    // ── run creation from the two rule-panel modes ──
    createFailed: tr(language, { ko: 'TRADING을 만들지 못했습니다.', en: 'Could not create the TRADING.', ja: 'TRADING を作成できませんでした。', th: 'สร้าง TRADING ไม่สำเร็จ', vi: 'Không tạo được TRADING.', id: 'Tidak dapat membuat TRADING.' }),
    startFailed: tr(language, { ko: 'TRADING을 시작하지 못했습니다 — 아래 목록에서 확인하세요.', en: 'Could not start the TRADING — see the list below.', ja: 'TRADING を開始できませんでした — 下の一覧を確認してください。', th: 'เริ่ม TRADING ไม่สำเร็จ — ดูรายการด้านล่าง', vi: 'Không khởi động được TRADING — xem danh sách bên dưới.', id: 'Tidak dapat memulai TRADING — lihat daftar di bawah.' }),
    manipWarn: tr(language, { ko: '조작 의심 형태 감지 — AI가 신중히 진입합니다', en: 'Manipulation-shaped tape detected — the AI will enter cautiously', ja: '相場操縦の疑いがある形状を検出 — AIは慎重にエントリーします', th: 'ตรวจพบรูปแบบต้องสงสัยว่าปั่นราคา — AI จะเข้าอย่างระมัดระวัง', vi: 'Phát hiện hình thái nghi thao túng — AI sẽ vào lệnh thận trọng', id: 'Terdeteksi pola dicurigai manipulasi — AI akan masuk dengan hati-hati' }),
    pickFailed: tr(language, { ko: '종목을 고르지 못했습니다 — 직접 선택하세요.', en: 'Could not pick a symbol — choose one yourself.', ja: '銘柄を選べませんでした — 手動で選択してください。', th: 'เลือกสัญลักษณ์ไม่สำเร็จ — เลือกเอง', vi: 'Không chọn được mã — hãy tự chọn.', id: 'Tidak dapat memilih simbol — pilih sendiri.' }),
  }

  const roleLabels: Record<string, string> = {
    news: tr(language, { ko: '뉴스', en: 'News', ja: 'ニュース', th: 'ข่าว', vi: 'Tin tức', id: 'Berita' }),
    sentiment: tr(language, { ko: '심리', en: 'Sentiment', ja: 'センチメント', th: 'ความรู้สึก', vi: 'Tâm lý', id: 'Sentimen' }),
    fundamentals_macro: tr(language, { ko: '펀더멘털 & 매크로', en: 'Fundamentals & Macro', ja: 'ファンダメンタル・マクロ', th: 'ปัจจัยพื้นฐานและมหภาค', vi: 'Cơ bản & Vĩ mô', id: 'Fundamental & Makro' }),
    technical: tr(language, { ko: '기술적 분석', en: 'Technical', ja: 'テクニカル', th: 'เทคนิค', vi: 'Kỹ thuật', id: 'Teknikal' }),
  }

  // Pipeline-step labels (role descriptions + verdict words) shared with the
  // monitor so the brief cards and decision detail speak the same language.
  const stepLabels = analysisStepLabels(language)

  // Key data behind each analyst's brief, as small chips — what the role
  // actually saw (headline tone, F&G, whales, macro regime, signal score).
  function briefChips(role: string, data: any): string[] {
    if (!data || typeof data !== 'object') return []
    const chips: string[] = []
    if (role === 'news') {
      if (typeof data.count === 'number') chips.push(`${data.count} ${T.chipHeadlines}`)
      const bd = data.sentiment_breakdown || {}
      const bull = (bd['bullish'] || 0) + (bd['somewhat-bullish'] || 0)
      const bear = (bd['bearish'] || 0) + (bd['somewhat-bearish'] || 0)
      if (bull || bear) chips.push(`▲${bull} ▼${bear}`)
    } else if (role === 'sentiment') {
      const fng = data.psych?.fear_greed
      if (fng?.value != null) chips.push(`${T.chipFearGreed} ${fng.value}${fng.classification ? ` (${fearGreedLabel(language, fng.classification)})` : ''}`)
      const st = data.stocktwits
      if (st && (st.bullish != null || st.bearish != null)) chips.push(`StockTwits ▲${st.bullish ?? '?'} ▼${st.bearish ?? '?'}`)
      const whales = data.whales?.events
      if (Array.isArray(whales) && whales.length) chips.push(`${whales.length} ${T.chipWhale}`)
    } else if (role === 'fundamentals_macro') {
      const m = data.macro
      if (m?.verdict) chips.push(`${T.chipMacro} ${m.verdict} (${m.bullish_count ?? 0}/${m.total_count ?? 0})`)
      if (Array.isArray(data.polymarket) && data.polymarket.length) chips.push(`Polymarket ${data.polymarket.length}`)
      if (data.fred) chips.push('FRED')
    } else if (role === 'technical') {
      if (data.current_price != null) chips.push(`${T.chipPrice} ${data.current_price}`)
      if (data.signal) chips.push(`${T.chipSignal} ${String(data.signal).toUpperCase()}${data.signal_score != null ? ` (${data.signal_score})` : ''}`)
      if (data.trend_status) chips.push(String(data.trend_status))
    }
    return chips
  }

  const authHeaders: any = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }

  // A stored 'real' with no connected gateway is a lie — re-check on mount and
  // fall back to simulator so the switch never claims an account that isn't there.
  useEffect(() => {
    if (!token) return
    fetch(`${API_BASE}/execution/health`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : null)
      .then(h => {
        if (!h) return
        if (h.configured) setGwBroker(h.broker || null)
        else if (acctMode === 'real') {
          localStorage.setItem('account_type', 'simulator')
          setAcctMode('simulator')
        }
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function pickReal() {
    if (acctBusy) return
    setAcctBusy(true)
    try {
      const r = await fetch(`${API_BASE}/execution/health`, { headers: authHeaders })
      const h = r.ok ? await r.json() : null
      if (h?.configured) {
        localStorage.setItem('account_type', 'real')
        setAcctMode('real')
        setGwBroker(h.broker || null)
      } else {
        // No real account set up yet — take them where they connect one.
        navigate('/accounts')
      }
    } catch {
      navigate('/accounts')
    } finally {
      setAcctBusy(false)
    }
  }

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
    setBusy(true); setError(''); setNotice('')
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
      // Research 04: server-side manipulation advisory (localized) — the run
      // is created either way; the user is informed, never blocked.
      if (data.manipulation_advisory?.text) setNotice(`${T.manipWarn}: ${data.manipulation_advisory.text}`)
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
    const isUs = simpleMarket === 'us-stock'
    try {
      const symbol = simpleCoin === 'SCANNER' ? await pickSymbol() : simpleCoin
      await createAndStartRun({
        symbol,
        market: simpleMarket,
        max_bet_usd: preset.size_usd,
        interval_minutes: preset.interval_minutes,
        min_confidence: preset.min_confidence,
        risk_level: simpleRisk,
        // US stock is a cash long-only book — never futures, never levered.
        market_type: isUs ? 'spot' : runType,
        leverage: !isUs && runType === 'futures' ? runLev : 1,
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
        market_type: runType,
        leverage: runType === 'futures' ? runLev : 1,
      })
    } catch (e: any) { setError(e.message) }
  }

  async function remove(id?: number) {
    if (!id) return
    setRemoveError(''); setRemovingId(id)
    try {
      const res = await fetch(`${API_BASE}/automation/configs/${id}`, { method: 'DELETE', headers: authHeaders })
      if (!res.ok) {
        const detail = (await res.json().catch(() => null))?.detail
        setRemoveError(typeof detail === 'string' ? detail : `${T.removeFailed} (HTTP ${res.status})`)
      }
      await refresh()
    } catch { setRemoveError(T.removeFailed) }
    finally { setRemovingId(null) }
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

  // Book picker shared by ⓪ 1종목 위임 and ① 간편: spot (long-only cash, no
  // leverage shown — always submits 1×) or futures (can short; isolated
  // margin, liquidation at a (100/L)% adverse move).
  const leveragePicker = (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>
        {tr(language, { ko: '거래 유형', en: 'Book type', ja: '取引タイプ', th: 'ประเภทบัญชี', vi: 'Loại sổ', id: 'Jenis akun' })}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button style={chip(runType === 'spot')} onClick={() => setRunType('spot')}>
          {tr(language, { ko: '현물', en: 'Spot', ja: '現物', th: 'สปอต', vi: 'Giao ngay', id: 'Spot' })}
        </button>
        <button style={chip(runType === 'futures')} onClick={() => setRunType('futures')}>
          {tr(language, { ko: '선물', en: 'Futures', ja: '先物', th: 'ฟิวเจอร์ส', vi: 'Hợp đồng tương lai', id: 'Futures' })}
        </button>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 6 }}>
        {runType === 'spot'
          ? tr(language, { ko: '현물 — 완전 자금형 매수 전용(레버리지·청산 없음).', en: 'Spot — fully funded, long-only (no leverage, no liquidation).', ja: '現物 — 全額拠出の買いのみ(レバレッジ・清算なし)。', th: 'สปอต — เงินเต็มจำนวน ซื้อเท่านั้น (ไม่มีเลเวอเรจ)', vi: 'Giao ngay — vốn đầy đủ, chỉ mua (không đòn bẩy, không thanh lý).', id: 'Spot — didanai penuh, hanya beli (tanpa leverage, tanpa likuidasi).' })
          : tr(language, { ko: '선물 — 하락장에서 숏 진입 가능.', en: 'Futures — the desk can also short a bearish read.', ja: '先物 — 弱気読みではショートも可能。', th: 'ฟิวเจอร์ส — เปิดชอร์ตได้', vi: 'Hợp đồng tương lai — có thể bán khống khi thị trường giảm.', id: 'Futures — bisa short saat pasar turun.' })}
      </div>
      {runType === 'futures' && <div style={{ marginTop: 12 }}>
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
      </div>}
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
        {features.simpleMode && (
          <button style={chip(ruleMode === 'simple')} onClick={() => setRuleMode('simple')}>① {T.modeSimple}</button>
        )}
        {features.fleetMode && (
          <button style={chip(ruleMode === 'fleet')} onClick={() => setRuleMode('fleet')}>② {T.modeFleet}</button>
        )}
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
          {features.leverage && leveragePicker}
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 12 }}>
            <button onClick={addAgent} disabled={busy || agentBudget < 100}
              style={{ padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
              {busy ? '⏳' : '🤖'} {T.startAgent}
            </button>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            {notice && <span style={{ color: '#d9a334', fontSize: 12.5 }}>⚠️ {notice}</span>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.agentKillNote}</div>
        </>
      )}

      {ruleMode === 'simple' && (
        <>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>{T.simpleMarketLabel}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            <button style={chip(simpleMarket === 'crypto')}
              onClick={() => { setSimpleMarket('crypto'); setSimpleCoin(topCoins[0] || 'BTC') }}>
              {T.marketCrypto}
            </button>
            <button style={chip(simpleMarket === 'us-stock')}
              onClick={() => { setSimpleMarket('us-stock'); setSimpleCoin(topUsTech[0] || 'NVDA') }}>
              {T.marketUsStock}
            </button>
          </div>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>{T.symbol}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            {(simpleMarket === 'us-stock' ? topUsTech : [...topCoins, 'SCANNER']).map(c => (
              <button key={c} style={chip(simpleCoin === c)} onClick={() => setSimpleCoin(c)}>
                {c === 'SCANNER' ? `🔍 ${T.coinAuto}` : c}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginBottom: 16 }}>
            {simpleMarket === 'us-stock' ? T.usTechHint : T.topFiveHint}
          </div>
          {simpleCoin === 'SCANNER' && simpleMarket === 'crypto' && (
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
          {features.leverage && simpleMarket !== 'us-stock' && leveragePicker}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>{T.simpleNote}</span>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
            {notice && <span style={{ color: '#d9a334', fontSize: 12.5 }}>⚠️ {notice}</span>}
            <button onClick={addSimple} disabled={busy} style={{ marginLeft: 'auto', padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>{busy ? '⏳' : '▶'} {T.startAuto}</button>
          </div>
        </>
      )}

      {/* Legacy list: nothing on this page creates a rule anymore (both modes
          above make TRADING runs), so an empty list means the section has no
          job — hide it. It must still render when rules exist, because Remove
          is the only way to stop a running rule. */}
      {rules.length > 0 && <>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '20px 0 10px' }}>{T.yourRules}</div>
      {removeError && <div style={{ color: '#f0663f', fontSize: 12.5, marginBottom: 10 }}>⚠️ {removeError}</div>}
      {/* Aligned columns (owner ask 2026-08-09 "inside each block, arrange"):
          name | settings | state | remove under a header row. ONE grid
          container (per-row grids let the auto tracks drift per row), wrapped
          in its own overflow-x scroller so a phone can still reach the Remove
          button — the only way to stop a running rule — instead of the modal
          clipping it. Cells stretch to row height (no alignItems on the
          container) so their borderTops draw one level separator; each cell
          centers its own content. */}
      {(() => {
        const cell: any = { borderTop: '1px solid var(--border-color,#d3c8b6)', padding: '10px 0', display: 'flex', alignItems: 'center' }
        return (
          <div style={{ overflowX: 'auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(110px,1fr) minmax(200px,2.2fr) max-content max-content', columnGap: 12, minWidth: 520 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted,#a89f92)', paddingBottom: 6 }}>
                {tr(language, { ko: '규칙', en: 'Rule', ja: 'ルール', th: 'กฎ', vi: 'Quy tắc', id: 'Aturan' })}</span>
              <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted,#a89f92)', paddingBottom: 6 }}>
                {tr(language, { ko: '설정', en: 'Settings', ja: '設定', th: 'การตั้งค่า', vi: 'Thiết lập', id: 'Pengaturan' })}</span>
              <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted,#a89f92)', paddingBottom: 6 }}>
                {tr(language, { ko: '상태', en: 'State', ja: '状態', th: 'สถานะ', vi: 'Trạng thái', id: 'Status' })}</span>
              <span />
              {rules.map(r => (
                <div key={r.id} style={{ display: 'contents' }}>
                  <b style={{ ...cell, fontSize: 13.5 }}>{r.mode === 'agent' ? `🤖 ${T.modeAgent} · $${r.budget_usd}` : r.symbol === 'SCANNER' ? `🔍 ${T.coinAuto}` : r.symbol}</b>
                  <span style={{ ...cell, fontSize: 12, color: 'var(--text-secondary,#8a8073)', fontVariantNumeric: 'tabular-nums' }}>
                    {r.market} · {r.provider || T.serverDefault} · {r.interval_minutes}m · ≥{Math.round((r.min_confidence || 0) * 100)}% · ${r.size_usd} · {normalizeAccountType(r.account_type)}
                  </span>
                  <span style={{ ...cell, gap: 6, whiteSpace: 'nowrap' }}>
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
                  </span>
                  <span style={{ ...cell, justifyContent: 'flex-end' }}>
                    <button onClick={() => remove(r.id)} disabled={removingId !== null} style={{ padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12, opacity: removingId === r.id ? 0.5 : 1 }}>{removingId === r.id ? '⏳ ' : ''}{T.remove}</button>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}
      </>}
    </div>
  )

  const primaryBtn: any = { padding: '12px 22px', borderRadius: 10, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer' }
  const secondaryBtn: any = { padding: '12px 22px', borderRadius: 10, border: '1.5px solid var(--accent-primary,#c26a45)', background: 'rgba(194,106,69,0.12)', color: 'var(--accent-primary,#c26a45)', fontWeight: 700, fontSize: 14, cursor: 'pointer' }

  // Everything the period chips govern, shared by the strip and the tile
  // detail modals. Calendar-period start is local time: today 00:00 / Monday /
  // 1st / Jan 1. Unrealized is the current open book — a period cannot
  // re-price the past — so it stays constant across chips and the labels say
  // which side is windowed.
  const periodLabel: Record<string, string> = { today: T.sumToday, week: T.sumWeek, month: T.sumMonth, year: T.sumYear }
  const win = assets && (() => {
    const periodStart = periodStartMs(sumPeriod)
    const ts = (c: any) => c ? new Date(String(c).replace(' ', 'T')).getTime() : NaN
    const localDate = (ms: number) => {
      const x = new Date(ms)
      return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
    }
    // trades arrive newest-first from the API; both lists keep that order.
    // The lists feed the modal fill views only — the window is [periodStart,
    // now], so the newest fills are always inside the 200-row cap; only a
    // long window's tail can truncate, and the sums don't come from here.
    const trades = assets.trades.filter((t: any) => ts(t.created_at) >= periodStart)
    const railsTrades = trades.filter((t: any) => (t.created_at || '') >= EXIT_RAILS_EPOCH)
    // Windowed sums: the server aggregate when it matches the active chip
    // (fetches keyed on sumPeriod, so right after a chip switch the stored
    // window is the previous chip's — fall back to the capped-list sums for
    // that one poll rather than show the wrong period's number).
    const sm = assets.summary?.window?.since === new Date(periodStart).toISOString()
      ? assets.summary : null
    const realized = sm ? sm.window.pnl
      : trades.reduce((s: number, t: any) => s + (t.pnl ?? 0), 0)
    // Gross winning vs gross losing that sum to `realized` (owner ask
    // 2026-08-09: a net figure hides that +3.79 can be big wins minus big
    // losses). Server aggregate is fee-accurate; the capped-list fallback is
    // used only for the one poll right after a chip switch.
    const gain = sm ? sm.window.gain
      : trades.reduce((s: number, t: any) => s + Math.max(0, t.pnl ?? 0), 0)
    const loss = sm ? sm.window.loss
      : trades.reduce((s: number, t: any) => s + Math.min(0, t.pnl ?? 0), 0)
    // Rails inside the window: both boundaries apply — the fixed epoch (same
    // string compare as the lifetime figure) AND the chip's start.
    const realizedRails = sm ? sm.window.split_pnl
      : railsTrades.reduce((s: number, t: any) => s + (t.pnl ?? 0), 0)
    const tradeCount = sm ? sm.window.trades : trades.length
    const railsSince = periodStart > ts(`${EXIT_RAILS_EPOCH} 00:00:00`) ? localDate(periodStart) : EXIT_RAILS_EPOCH
    const dur = (ms: number) => ({ d: Math.floor(ms / 86400000), h: Math.floor((ms % 86400000) / 3600000) })
    const sinceMs = assets.since ? ts(assets.since) : NaN
    const life = Number.isFinite(sinceMs) && Date.now() > sinceMs ? dur(Date.now() - sinceMs) : null
    // 운영 기간 under a chip = the overlap of [first trade, now] with the window
    const opStartMs = Number.isFinite(sinceMs) ? Math.max(sinceMs, periodStart) : NaN
    const opWindow = Number.isFinite(opStartMs) && Date.now() > opStartMs ? dur(Date.now() - opStartMs) : null
    const profit = realized + assets.unrealized
    return { periodStart, trades, realized, gain, loss, railsTrades, realizedRails, tradeCount, railsSince, life, opStartMs, opWindow, profit, localDate }
  })()

  // Account summary. Lives in the page header, right-aligned: it is reference
  // data you glance at, not the thing you came to do — the create buttons are.
  // Full-width tiles under the buttons pushed the actual TRADING list below
  // the fold on a laptop.
  // Rendered from the first paint, before any fetch resolves: the tiles are
  // the page's masthead, and gating the whole strip on `assets` made it pop in
  // a beat after everything else. While loading, each tile keeps its label and
  // its footprint and shows an em dash where the number will land — no reflow
  // when the values arrive, and no stale money figure shown as if it were
  // current. Tiles only become clickable once there is something to open.
  const summaryStrip = (() => {
    const ready = !!(assets && win)
    // Equal-width tiles (owner ask 2026-08-09 "inside each block, arrange"):
    // content-driven widths made the four tiles ragged; a fixed width lines
    // them up. 186px keeps the typical sub-line ("in use X · cash Y") whole;
    // anything longer ellipsizes — the detail modal carries the full figure.
    const tile: any = { width: 186, overflow: 'hidden', background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 10, padding: '9px 13px', textAlign: 'left', font: 'inherit', color: 'inherit', cursor: ready ? 'pointer' : 'default' }
    const kSt: any = { fontSize: 10.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
    const vSt: any = { fontSize: 17, fontWeight: 800, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
    const sSt: any = { fontSize: 10, color: 'var(--text-muted,#a89f92)', marginTop: 2, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }
    const periods: Array<'today' | 'week' | 'month' | 'year'> = ['today', 'week', 'month', 'year']
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {periods.map(pp => (
            <button key={pp} onClick={() => setSumPeriod(pp)}
              style={{ padding: '3px 10px', borderRadius: 7, fontSize: 11, cursor: 'pointer',
                border: '1px solid var(--border-color,rgba(0,0,0,0.12))',
                background: sumPeriod === pp ? 'var(--accent-primary,#c26a45)' : 'transparent',
                color: sumPeriod === pp ? '#fff' : 'var(--text-secondary,#8a8073)',
                fontWeight: sumPeriod === pp ? 700 : 500 }}>
              {periodLabel[pp]}
            </button>
          ))}
        </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <button style={tile} title={T.dHint} onClick={ready ? () => setSumDetail('deposit') : undefined}>
          <div style={kSt}>💰 {T.sumDeposit}</div>
          <div style={vSt}>{assets ? fmtUsd(assets.total) : '—'}</div>
          <div style={sSt}>{assets ? <>{T.sumInUse} {fmtUsd(assets.inUse)} · {T.sumCash} {fmtUsd(assets.cash)}</> : '\u00a0'}</div>
        </button>
        <button style={tile} title={T.dHint} onClick={ready ? () => setSumDetail('lifetime') : undefined}>
          <div style={kSt}>📅 {T.sumLifetime}</div>
          <div style={vSt}>{win && win.opWindow ? <>{win.opWindow.d}{T.sumDay} <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary,#8a8073)' }}>{win.opWindow.h}{T.sumHour}</span></> : '—'}</div>
          <div style={sSt}>{!win ? '\u00a0' : Number.isFinite(win.opStartMs) ? `${win.localDate(win.opStartMs)} ${T.sumSince}` : T.sumNoHistory}</div>
        </button>
        <button style={tile} title={T.dHint} onClick={ready ? () => setSumDetail('profit') : undefined}>
          <div style={kSt}>📈 {T.sumProfit}</div>
          <div style={{ ...vSt, color: win ? pnlColor(win.profit) : undefined }}>{win ? `${win.profit >= 0 ? '+' : ''}${fmtUsd(win.profit)}` : '—'}</div>
          <div style={sSt}>{win ? <><span style={{ color: 'var(--success,#2e7d32)' }}>+{fmtUsd(win.gain)}</span> <span style={{ color: 'var(--danger,#c0392b)' }}>{fmtUsd(win.loss)}</span> · {T.sumNet} {win.realized >= 0 ? '+' : ''}{fmtUsd(win.realized)}</> : '\u00a0'}</div>
        </button>
        <button style={tile} title={T.dHint} onClick={ready ? () => setSumDetail('rails') : undefined}>
          <div style={kSt}>🛡️ {T.sumCurrentRails}</div>
          <div style={{ ...vSt, color: win ? pnlColor(win.realizedRails) : undefined }}>{win ? `${win.realizedRails >= 0 ? '+' : ''}${fmtUsd(win.realizedRails)}` : '—'}</div>
          <div style={sSt}>{win ? `${T.sumRailsSince} ${win.railsSince}` : '\u00a0'}</div>
        </button>
      </div>
      {/* The desk's 30-minute analysis sits under the tiles it explains: the
          tiles say what the number is, this says what the desk did to it. */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button onClick={() => setShowCycles(true)}
          style={{ padding: '7px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
            border: '1px solid var(--border-color,rgba(0,0,0,0.12))', background: 'transparent',
            color: 'var(--text-secondary,#8a8073)' }}>
          🧠 {T.aiAnalysis}
        </button>
        {/* The desk's KEPT forward plan per fleet slot (Plan 26) — what the
            analysis above decided to do NEXT, and whether it was followed. */}
        <button onClick={() => setShowOutlook(true)}
          style={{ padding: '7px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
            border: '1px solid var(--border-color,rgba(0,0,0,0.12))', background: 'transparent',
            color: 'var(--text-secondary,#8a8073)' }}>
          📋 {T.slotOutlook}
        </button>
        {/* The member's own board — rules, runs, positions, watches, alerts.
            It was the standalone /monitor page; it opens here instead. */}
        <button onClick={() => setShowMonitor(true)}
          style={{ padding: '7px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
            border: '1px solid var(--border-color,rgba(0,0,0,0.12))', background: 'transparent',
            color: 'var(--text-secondary,#8a8073)' }}>
          📡 {T.monitoring}
        </button>
      </div>
      </div>
    )
  })()

  const acctBtn = (active: boolean): any => ({
    padding: '8px 16px', borderRadius: 9, fontSize: 13, fontWeight: 700,
    cursor: acctBusy ? 'wait' : 'pointer',
    border: '1px solid ' + (active ? 'transparent' : 'var(--border-color,#d3c8b6)'),
    background: active ? 'var(--accent-primary,#c26a45)' : 'transparent',
    color: active ? '#fff' : 'var(--text-secondary,#8a8073)',
  })

  return (
    <div>
      {/* ── Simulator / real-account switch. Same pair as the app chrome:
             real without a connected gateway routes to /accounts. ── */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <button style={acctBtn(acctMode === 'simulator')}
          title={tr(language, { ko: '모의 지갑 — 페이퍼 트레이딩', en: 'Simulated wallet — paper trading', ja: '模擬ウォレット', th: 'กระเป๋าจำลอง — เทรดกระดาษ', vi: 'Ví mô phỏng', id: 'Dompet simulasi — paper trading' })}
          onClick={() => { localStorage.setItem('account_type', 'simulator'); setAcctMode('simulator') }}>
          ◐ {tr(language, { ko: '시뮬레이터', en: 'Simulator', ja: 'シミュレーター', th: 'จำลอง', vi: 'Mô phỏng', id: 'Simulator' })}
        </button>
        <button style={acctBtn(acctMode === 'real')} disabled={acctBusy}
          title={tr(language, { ko: '실계좌 — 거래소 연결', en: 'Real account — connect an exchange', ja: '実口座 — 取引所を接続', th: 'บัญชีจริง — เชื่อมต่อกระดานเทรด', vi: 'Tài khoản thật — kết nối sàn', id: 'Akun asli — hubungkan bursa' })}
          onClick={pickReal}>
          ● {tr(language, { ko: '실계좌', en: 'Real', ja: 'リアル', th: 'จริง', vi: 'Thật', id: 'Asli' })}
        </button>
        <HelpTip text={tr(language, {
          ko: '시뮬레이터는 가상 자금으로 실전과 똑같이 연습하는 모의 지갑입니다 — 실제 돈이 사용되지 않습니다. 실계좌는 Coinbase·Bybit 등 거래소를 연결해 실제 자금으로 거래하는 모드이며, 게이트웨이가 연결되어 있지 않으면 계좌 연결 페이지로 이동합니다.',
          en: 'Simulator is a paper wallet — you practice with virtual funds and no real money is used. Real connects an exchange (Coinbase, Bybit, …) and trades with actual funds; without a connected gateway it takes you to the account-connection page.',
          ja: 'シミュレーターは仮想資金で本番同様に練習できる模擬ウォレットです — 実際のお金は使われません。実口座は Coinbase・Bybit などの取引所を接続して実資金で取引するモードで、ゲートウェイ未接続の場合は口座接続ページに移動します。',
          th: 'จำลอง คือกระเป๋าเงินทดลอง — ฝึกเทรดด้วยเงินเสมือน ไม่ใช้เงินจริง ส่วน บัญชีจริง คือการเชื่อมต่อกระดานเทรด (Coinbase, Bybit ฯลฯ) เพื่อเทรดด้วยเงินจริง หากยังไม่ได้เชื่อมต่อเกตเวย์จะพาไปหน้าเชื่อมต่อบัญชี',
          vi: 'Mô phỏng là ví giấy — bạn luyện tập với vốn ảo, không dùng tiền thật. Tài khoản thật kết nối sàn giao dịch (Coinbase, Bybit, …) và giao dịch bằng tiền thật; nếu chưa kết nối gateway sẽ đưa bạn đến trang kết nối tài khoản.',
          id: 'Simulator adalah dompet simulasi — Anda berlatih dengan dana virtual tanpa uang sungguhan. Akun asli menghubungkan bursa (Coinbase, Bybit, …) dan bertransaksi dengan dana nyata; tanpa gateway yang terhubung, Anda akan dibawa ke halaman penghubungan akun.',
        })} />
        {acctMode === 'real' && gwBroker && (
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>
            {tr(language, {
              ko: `연결된 게이트웨이: ${gwBroker} — live 규칙의 주문이 이 게이트웨이로 전송됩니다`,
              en: `connected gateway: ${gwBroker} — live rules route their orders through it`,
              ja: `接続中のゲートウェイ: ${gwBroker} — live ルールの注文はここに送信されます`,
              th: `เกตเวย์ที่เชื่อมต่อ: ${gwBroker} — กฎ live ส่งคำสั่งผ่านเกตเวย์นี้`,
              vi: `cổng đã kết nối: ${gwBroker} — quy tắc live gửi lệnh qua cổng này`,
              id: `gateway terhubung: ${gwBroker} — aturan live mengirim order melaluinya`,
            })}
          </span>
        )}
      </div>

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
        {features.analyst && (
          <button style={secondaryBtn} onClick={() => setShowAnalyst(true)}>🧠 {T.makeByAnalyst}</button>
        )}
        <HelpTip style={{ alignSelf: 'center' }} text={tr(language, {
          ko: '「새 TRADING으로 만들기」는 종목·주기·예산 등을 직접 설정하는 생성 폼을 엽니다.\n「AI 애널리스트로 만들기」는 네 명의 AI 애널리스트가 지금 바로 일회성 분석을 실행합니다 — 주문은 나가지 않으며, 결과가 마음에 들면 그 설정으로 자동매매를 시작할 수 있습니다.',
          en: '"Make by New Trading" opens the create form where you set the symbol, interval and budget yourself.\n"Make by AI Analyst" runs a one-off analysis by four AI analysts right now — no order is placed, and if you like the result you can start auto-trading with those settings.',
          ja: '「新しい TRADING で作成」はシンボル・周期・予算などを自分で設定する作成フォームを開きます。\n「AIアナリストで作成」は4人のAIアナリストが今すぐ1回限りの分析を実行します — 注文は出されず、結果が気に入ればその設定で自動売買を開始できます。',
          th: '"สร้างด้วย TRADING ใหม่" เปิดฟอร์มสร้างที่คุณตั้งค่าสัญลักษณ์ รอบเวลา และงบเอง\n"สร้างด้วยนักวิเคราะห์ AI" ให้นักวิเคราะห์ AI สี่คนวิเคราะห์ครั้งเดียวทันที — ไม่ส่งคำสั่งซื้อขาย และถ้าพอใจผลลัพธ์ก็เริ่มเทรดอัตโนมัติด้วยค่านั้นได้',
          vi: '"Tạo bằng TRADING mới" mở biểu mẫu để bạn tự đặt mã, chu kỳ và ngân sách.\n"Tạo bằng nhà phân tích AI" chạy ngay một phân tích một lần bởi bốn nhà phân tích AI — không đặt lệnh, và nếu ưng kết quả bạn có thể bắt đầu giao dịch tự động với thiết lập đó.',
          id: '"Buat lewat TRADING baru" membuka formulir pembuatan tempat Anda sendiri mengatur simbol, interval, dan anggaran.\n"Buat lewat Analis AI" langsung menjalankan analisis sekali jalan oleh empat analis AI — tidak ada order yang dipasang, dan jika hasilnya Anda sukai, Anda bisa memulai trading otomatis dengan pengaturan itu.',
        })} />
      </div>


      {/* ── Full Auto fleet monitor — always visible once a fleet is live,
             so monitoring never requires reopening the create modal ── */}
      <FleetPanel token={token!} monitorOnly
        onSelectRun={(id) => setOpenRunReq(p => ({ id, nonce: (p?.nonce || 0) + 1 }))} />

      {/* ── The one block on this page ── */}
      <RunsLiveSection token={token} embedded reloadKey={runsReload}
        hideCreateButton hideCreateForm openCreateSignal={openCreate} extraPanel={rulePanel}
        openRunRequest={openRunReq} />

      {/* ── ② Make by AI Analyst ── */}
      {/* ── Summary-tile detail modal: the numbers behind whichever tile was
             clicked, scoped to the same period chip as the strip ── */}
      {sumDetail && assets && win && (() => {
        const titles: Record<string, string> = {
          deposit: `💰 ${T.sumDeposit}`, lifetime: `📅 ${T.sumLifetime}`,
          profit: `📈 ${T.sumProfit}`, rails: `🛡️ ${T.sumCurrentRails}`,
        }
        const rowSt: any = { display: 'flex', justifyContent: 'space-between', gap: 16, padding: '7px 0', borderBottom: '1px solid var(--border-color,rgba(0,0,0,0.07))', fontSize: 13.5 }
        const row = (k: string, v: string, color?: string) => (
          <div key={k} style={rowSt}>
            <span style={{ color: 'var(--text-secondary,#8a8073)' }}>{k}</span>
            <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: color || 'inherit' }}>{v}</span>
          </div>
        )
        const money = (n: number) => `${n >= 0 ? '+' : ''}${fmtUsd(n)}`
        const durStr = (x: { d: number; h: number } | null) => x ? `${x.d}${T.sumDay} ${x.h}${T.sumHour}` : '—'
        const when = (c: any) => String(c || '').replace('T', ' ').slice(0, 16)
        const fills = (list: any[]) => (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-secondary,#8a8073)', marginBottom: 6 }}>{T.dFills}</div>
            {list.length === 0
              ? <div style={{ fontSize: 12.5, color: 'var(--text-muted,#a89f92)' }}>{T.dNoFills}</div>
              : <div style={{ maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                  {list.map((t: any, i: number) => (
                    <div key={t.signal_id ?? i} style={{ ...rowSt, fontSize: 12.5 }}>
                      <span style={{ color: 'var(--text-secondary,#8a8073)', fontVariantNumeric: 'tabular-nums' }}>{when(t.created_at)}</span>
                      <span style={{ fontWeight: 600 }}>{t.symbol} <span style={{ fontWeight: 500, color: 'var(--text-muted,#a89f92)' }}>{t.side}</span></span>
                      {/* pnl is null on the opening leg — there is nothing to realize yet */}
                      <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: t.pnl == null ? 'var(--text-muted,#a89f92)' : pnlColor(t.pnl) }}>{t.pnl == null ? '—' : money(t.pnl)}</span>
                    </div>
                  ))}
                </div>}
          </div>
        )
        // The tile's profit graph. Buckets arrive as UTC hours (server emits
        // only hours that traded); re-bucket to LOCAL hours (오늘) or local
        // days (longer chips) so the axis matches the user's calendar, then
        // accumulate. Deposit re-anchors the same curve so its last point
        // equals the current balance.
        const chartRows = (() => {
          if (!seriesPts) return null
          const useHours = sumPeriod === 'today'
          const key = sumDetail === 'rails' ? 'split_pnl' : 'pnl'
          const acc = new Map<string, number>()
          for (const p of seriesPts) {
            const d = new Date(`${p.t}:00:00Z`)
            if (isNaN(d.getTime())) continue
            const label = useHours
              ? `${String(d.getHours()).padStart(2, '0')}:00`
              : win.localDate(d.getTime())
            acc.set(label, (acc.get(label) || 0) + (Number((p as any)[key]) || 0))
          }
          let cum = 0
          const rows = [...acc.entries()].map(([t, v]) => { cum += v; return { t, v: cum } })
          if (sumDetail === 'deposit' && rows.length) {
            const total = rows[rows.length - 1].v
            for (const r of rows) r.v = assets.total - total + r.v
          }
          return rows
        })()
        const gTitle: Record<string, string> = { deposit: T.gDeposit, lifetime: T.gProfit, profit: T.gProfit, rails: T.gRails }
        const lineColor = sumDetail === 'deposit' ? 'var(--accent-primary,#c26a45)'
          : pnlColor(chartRows?.length ? chartRows[chartRows.length - 1].v : 0)
        const chart = (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-secondary,#8a8073)', marginBottom: 6 }}>
              📈 {gTitle[sumDetail]} · {periodLabel[sumPeriod]}
            </div>
            {!chartRows || chartRows.length < 2
              ? <div style={{ height: 90, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12.5, color: 'var(--text-muted,#a89f92)' }}>{T.gNoData}</div>
              : <ResponsiveContainer width="100%" height={150}>
                  <LineChart data={chartRows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" strokeOpacity={0.4} />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} width={58}
                      domain={['auto', 'auto']} tickFormatter={(v: number) => fmtUsd(v, 0)} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, fontSize: 12 }}
                      formatter={(v: any) => [typeof v === 'number' ? `$${fmtUsd(v)}` : '—', gTitle[sumDetail]] as [string, string]} />
                    {sumDetail !== 'deposit' && (
                      <ReferenceLine y={0} stroke="var(--text-muted)" strokeDasharray="4 4" strokeOpacity={0.5} />
                    )}
                    <Line type="monotone" dataKey="v" stroke={lineColor} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>}
            {sumDetail === 'deposit' && chartRows && chartRows.length >= 2 && (
              <div style={{ fontSize: 11, color: 'var(--text-muted,#a89f92)', marginTop: 4, lineHeight: 1.45 }}>{T.gDepositNote}</div>
            )}
          </div>
        )
        return (
          <div role="dialog" aria-modal="true" aria-label={titles[sumDetail]}
            onClick={() => setSumDetail(null)}
            style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 24px 24px', overflowY: 'auto' }}>
            <div onClick={e => e.stopPropagation()}
              style={{ width: '100%', maxWidth: 560, margin: 'auto', background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{ fontSize: 16, fontWeight: 800 }}>{titles[sumDetail]}</div>
                {sumDetail !== 'deposit' && (
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 7, background: 'rgba(194,106,69,0.14)', color: 'var(--accent-primary,#c26a45)' }}>{periodLabel[sumPeriod]}</span>
                )}
                <button onClick={() => setSumDetail(null)} aria-label="close"
                  style={{ marginLeft: 'auto', border: 'none', background: 'transparent', color: 'var(--text-secondary,#8a8073)', fontSize: 18, cursor: 'pointer', lineHeight: 1 }}>✕</button>
              </div>

              {sumDetail === 'deposit' && <>
                {row(T.sumDeposit, fmtUsd(assets.total))}
                {row(T.sumCash, fmtUsd(assets.cash))}
                {row(T.sumInUse, fmtUsd(assets.inUse))}
                {chart}
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-secondary,#8a8073)', marginBottom: 6 }}>{T.dOpenPositions}</div>
                  {assets.positions.length === 0
                    ? <div style={{ fontSize: 12.5, color: 'var(--text-muted,#a89f92)' }}>{T.dNoPositions}</div>
                    : <div style={{ maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                        {assets.positions.map((p: any, i: number) => (
                          <div key={p.id ?? i} style={{ ...rowSt, fontSize: 12.5 }}>
                            <span style={{ fontWeight: 600 }}>{p.symbol} <span style={{ fontWeight: 500, color: 'var(--text-muted,#a89f92)' }}>{p.side}</span></span>
                            <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary,#8a8073)' }}>{fmtUsd(positionEquity(p))}</span>
                            <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: pnlColor(p.pnl ?? 0) }}>{money(p.pnl ?? 0)}</span>
                          </div>
                        ))}
                      </div>}
                </div>
                <div style={{ marginTop: 14 }}>
                  <Link to="/assets" style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-primary,#c26a45)', textDecoration: 'none' }}>{T.dGoAssets}</Link>
                </div>
              </>}

              {sumDetail === 'lifetime' && <>
                {row(T.dFirstTrade, assets.since ? when(assets.since) : T.sumNoHistory)}
                {row(T.dTotalSpan, durStr(win.life))}
                {row(`${T.dWindowSpan} · ${periodLabel[sumPeriod]}`, durStr(win.opWindow))}
                {row(T.dTradeCount, String(win.tradeCount))}
                {row(T.dLastTrade, win.trades.length ? when(win.trades[0].created_at) : '—')}
                {chart}
              </>}

              {sumDetail === 'profit' && <>
                {row(`${T.sumProfit} · ${periodLabel[sumPeriod]}`, money(win.profit), pnlColor(win.profit))}
                {row(T.dGain, `+${fmtUsd(win.gain)}`, 'var(--success,#2e7d32)')}
                {row(T.dLoss, fmtUsd(win.loss), 'var(--danger,#c0392b)')}
                {row(T.dRealizedPeriod, money(win.realized), pnlColor(win.realized))}
                {row(T.dUnrealizedNow, money(assets.unrealized), pnlColor(assets.unrealized))}
                {row(T.dRealizedLife, money(assets.realized), pnlColor(assets.realized))}
                <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 8, lineHeight: 1.5 }}>{T.dUnrealNote}</div>
                {chart}
                {fills(win.trades)}
              </>}

              {sumDetail === 'rails' && <>
                {row(`${T.dRailsWin} · ${periodLabel[sumPeriod]}`, money(win.realizedRails), pnlColor(win.realizedRails))}
                {row(T.dRailsCur, money(assets.realizedCurrent), pnlColor(assets.realizedCurrent))}
                {row(T.dRailsOld, money(assets.realized - assets.realizedCurrent), pnlColor(assets.realized - assets.realizedCurrent))}
                {row(T.sumRailsSince, win.railsSince)}
                <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 8, lineHeight: 1.5 }}>{T.dRailsWhat}</div>
                {chart}
                {fills(win.railsTrades)}
              </>}
            </div>
          </div>
        )
      })()}

      {showCycles && <DeskCyclesPanel token={token} onClose={() => setShowCycles(false)} />}

      {showOutlook && <SlotOutlookPanel token={token} onClose={() => setShowOutlook(false)} />}

      {showMonitor && <MonitorPanel token={token} onClose={() => setShowMonitor(false)} />}

      {showAnalyst && (
        <div role="dialog" aria-modal="true" aria-label={T.makeByAnalyst}
          // z 600 + 32px top padding: the sticky top nav is z-index 500 and
          // covered this modal's first rows (the Close button) at z 60 —
          // same fix as the create modal in RunsLivePage.
          onClick={() => setShowAnalyst(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 24px 24px', overflowY: 'auto' }}>
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
                {(() => {
                  // Decision detail: the component scores, the verifier's
                  // verdict, and the desk's order intent — the parts of the
                  // final pipeline that the action/confidence header hides.
                  const d = analyze.result.decision || {}
                  const scores = d.scores || {}
                  const scoreRows: Array<[string, number]> = ([
                    [T.scoreThesis, scores.thesis_alignment], [T.scoreMomentum, scores.momentum_quality],
                    [T.scoreEntry, scores.entry_quality], [T.scoreRisk, scores.risk_context],
                  ] as Array<[string, any]>).filter((r): r is [string, number] => typeof r[1] === 'number')
                  const ver = d.verification
                  const oi = d.order_intent
                  const levels: string[] = []
                  if (d.suggested_entry != null) levels.push(`${T.suggestedEntryLabel} ${d.suggested_entry}`)
                  if (d.target != null) levels.push(`${T.targetLabel} ${d.target}`)
                  if (d.stop != null) levels.push(`${T.stopLabel} ${d.stop}`)
                  const isRule = d.decided_by === 'rule'
                  if (!scoreRows.length && !ver && !oi?.intent && !levels.length && !isRule) return null
                  const verColor = ver?.verdict === 'rejected' ? '#f0663f' : ver?.verdict === 'weakened' ? '#e3a008' : '#3987e5'
                  return (
                    <div style={{ marginTop: 14 }}>
                      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', marginBottom: 8 }}>{T.decisionDetail}</div>
                      {scoreRows.length > 0 && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 10, marginBottom: 10 }}>
                          {scoreRows.map(([label, v]) => (
                            <div key={label}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, marginBottom: 3 }}>
                                <span style={{ color: 'var(--text-secondary,#8a8073)' }}>{label}</span>
                                <b style={{ fontVariantNumeric: 'tabular-nums' }}>{Math.round(v * 100)}%</b>
                              </div>
                              <div style={{ height: 4, borderRadius: 2, background: 'var(--border-color,rgba(0,0,0,0.12))' }}>
                                <div style={{ height: 4, borderRadius: 2, width: `${Math.round(v * 100)}%`, background: '#3987e5' }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12.5 }}>
                        {ver?.verdict && (
                          <div>
                            <b style={{ color: verColor }}>{T.verifyLabel}: {stepLabels[`__verdict_${ver.verdict}`] || ver.verdict}</b>
                            {typeof ver.adjusted_confidence === 'number' && <span style={{ color: 'var(--text-secondary,#8a8073)' }}> · {T.confidence} {Math.round(ver.adjusted_confidence * 100)}%</span>}
                            {ver.reason && <span style={{ color: 'var(--text-secondary,#8a8073)' }}> — {ver.reason}</span>}
                          </div>
                        )}
                        {oi?.intent && (
                          <div>
                            <b>{T.orderIntentLabel}: {String(oi.intent).toUpperCase()}</b>
                            {typeof oi.size_frac === 'number' && oi.size_frac > 0 && <span style={{ color: 'var(--text-secondary,#8a8073)' }}> · {Math.round(oi.size_frac * 100)}%</span>}
                            {oi.why && <span style={{ color: 'var(--text-secondary,#8a8073)' }}> — {oi.why}</span>}
                          </div>
                        )}
                        {levels.length > 0 && (
                          <div style={{ color: 'var(--text-secondary,#8a8073)', fontVariantNumeric: 'tabular-nums' }}>{levels.join(' · ')}</div>
                        )}
                        {isRule && <div style={{ color: '#e3a008' }}>⚠️ {T.ruleFallback}</div>}
                      </div>
                    </div>
                  )
                })()}
                {analyze.result.analysts && (
                  <>
                    <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)', margin: '14px 0 10px' }}>{T.analystBriefs}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 14 }}>
                      {Object.entries(analyze.result.analysts).map(([role, v]: any) => {
                        const chips = briefChips(role, v?.data)
                        return (
                          <div key={role} style={{ border: '1px solid var(--border-color,#d3c8b6)', borderRadius: 10, padding: 14 }}>
                            <div style={{ fontWeight: 700 }}>{roleLabels[role] || role}</div>
                            {stepLabels[`__desc:brief:${role}`] && (
                              <div style={{ fontSize: 11, color: 'var(--text-muted,#a89f92)', marginTop: 2 }}>{stepLabels[`__desc:brief:${role}`]}</div>
                            )}
                            {chips.length > 0 && (
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0 2px' }}>
                                {chips.map((c, i) => (
                                  <span key={i} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, border: '1px solid var(--border-color,#d3c8b6)', color: 'var(--text-secondary,#8a8073)', fontVariantNumeric: 'tabular-nums' }}>{c}</span>
                                ))}
                              </div>
                            )}
                            <div style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--text-secondary,#5f574c)', whiteSpace: 'pre-wrap', marginTop: 6 }}>{v.brief}</div>
                          </div>
                        )
                      })}
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
