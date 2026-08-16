import { useCallback, useEffect, useState } from 'react'
import { API_BASE, marketLabel, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { fmtQty } from '../pages/tradeShared'

// Slot Strategy Outlook (Plan 26) — the desk's KEPT forward plan, per fleet
// slot, opened from beside the AI Analysis button on the automation page.
//
// Nothing here trades. The desk writes an `outlook` event beside every
// decision (buy-side, sell-side, invalidation, horizon); this panel reads
// GET /api/fleets/{id}/outlook and renders each slot's standing plan as a
// card: header badges, a plain-SVG levels strip (entry zone band, target and
// stop rules — direct labels on every level, never color alone; no WebGL,
// no canvas — the 16-context cap evicts grid canvases), the narrative, and
// a collapsible dialog of the slot's decision/outlook tail.
//
// The narrative/dialog prose arrives already localized from the endpoint
// (?lang=…, write-time-warm cache, English fallback); every static label
// localizes here through the same tr() maps sibling panels use.

type OutlookEntry = {
  kind: 'zone' | 'trigger' | 'none'
  low: number | null; high: number | null; trigger: string | null
}
type OutlookExit = {
  target_px: number | null; stop_ref_px: number | null; time_exit: string | null
}
// The desk-vs-algorithm target discussion (additive; older events lack it).
type OutlookBasisAlgo = {
  entry_low: number | null; entry_high: number | null
  target_px: number | null; stop_ref_px: number | null; time_exit: string | null
}
type OutlookBasis = {
  algo: OutlookBasisAlgo | null
  verdict: 'adopted' | 'adjusted' | 'overridden' | 'algo_fallback'
  discussion: string | null
}
type Outlook = {
  bias: 'long' | 'short' | 'flat'
  entry: OutlookEntry | null
  exit: OutlookExit | null
  invalidation: string | null
  horizon_hours: number | null
  narrative: string
  source: 'cycle' | 'sweeper'
  basis?: OutlookBasis | null
}
type DialogRow = {
  ts: string; kind: 'decision' | 'outlook'; text: string
  plan_adherence: 'followed' | 'revised' | 'deviated' | null
  source: string | null
}
type Slot = {
  slot_index: number; state: string; run_id: number | null
  symbol: string | null; market: string | null; status: string | null
  thesis: { direction: string; horizon_hours: number } | null
  outlook: Outlook | null
  outlook_ts: string | null; next_refresh_by: string | null
  dialog: DialogRow[]
}
type FleetOutlook = { fleet_id: number; slots: Slot[] }
type FleetRef = { id: number; status: string }

// Mirror of outlook_refresher.OUTLOOK_CADENCE_MIN — the freshness floor per
// market. Fast markets refresh with the 30-min cycle; everything else (and
// closed sessions, server-side) rides the hourly sweeper.
const FAST_MARKETS = new Set(['us-stock', 'crypto', 'forex'])

const hhmm = (iso: string, lang: string) =>
  new Date(iso).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit', hour12: false })
const fullStamp = (iso: string, lang: string) => new Date(iso).toLocaleString(lang)

// ── The levels strip ─────────────────────────────────────────────────────
// One horizontal price axis; entry zone as a translucent band, target and
// stop as dashed status-colored rules. Every level carries its value + name
// as text. Prices come straight from the outlook payload — there is no
// price series in the contract, so the strip is levels-only by design.
const GOOD = '#3fb950'      // app profit green (pnlColor)
const DANGER = '#f0663f'    // app danger orange-red (pnlColor)

type Level = { px: number; label: string; color: string; kind: 'target' | 'stop' }

function LevelsStrip({ outlook, algoTarget, labels }: {
  outlook: Outlook
  // The algorithm's own target when the desk adjusted/overrode it — drawn as
  // a faint secondary marker on its own label row so it never collides with
  // the primary level labels. null = don't draw.
  algoTarget?: number | null
  labels: { entryZone: string; target: string; stop: string; trigger: string; algo: string }
}) {
  const algoPx = algoTarget !== undefined && algoTarget !== null && Number.isFinite(algoTarget) ? algoTarget : null
  const entry = outlook.entry
  const exit = outlook.exit
  const zoneLow = entry && entry.kind === 'zone' && entry.low !== null && Number.isFinite(entry.low) ? entry.low : null
  const zoneHigh = entry && entry.kind === 'zone' && entry.high !== null && Number.isFinite(entry.high) ? entry.high : null
  const levels: Level[] = []
  if (exit && exit.target_px !== null && Number.isFinite(exit.target_px))
    levels.push({ px: exit.target_px, label: labels.target, color: GOOD, kind: 'target' })
  if (exit && exit.stop_ref_px !== null && Number.isFinite(exit.stop_ref_px))
    levels.push({ px: exit.stop_ref_px, label: labels.stop, color: DANGER, kind: 'stop' })

  const pts: number[] = [...levels.map(l => l.px)]
  if (zoneLow !== null) pts.push(zoneLow)
  if (zoneHigh !== null) pts.push(zoneHigh)
  if (algoPx !== null) pts.push(algoPx)
  if (pts.length === 0) {
    // Trigger-style entry with no numeric levels: state it as text.
    if (entry && entry.kind === 'trigger' && entry.trigger)
      return <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', margin: '6px 0' }}>⚡ {labels.trigger}: {entry.trigger}</div>
    return null
  }

  const W = 680, PAD = 46
  const H = algoPx !== null ? 110 : 96   // extra label row for the algo marker
  const AXIS_Y = 56
  let lo = Math.min(...pts), hi = Math.max(...pts)
  if (lo === hi) { lo -= Math.abs(lo) * 0.02 || 1; hi += Math.abs(hi) * 0.02 || 1 }
  const span = hi - lo
  lo -= span * 0.1; hi += span * 0.1
  const x = (px: number) => PAD + ((px - lo) / (hi - lo)) * (W - 2 * PAD)
  const clampX = (v: number) => Math.max(PAD - 30, Math.min(W - PAD + 30, v))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ display: 'block', width: '100%', maxWidth: 680, height: 'auto', margin: '6px 0' }}>
      {/* axis */}
      <line x1={PAD - 20} y1={AXIS_Y} x2={W - PAD + 20} y2={AXIS_Y} stroke="var(--border-color,rgba(0,0,0,0.25))" strokeWidth={1.5} />
      {/* entry zone band */}
      {zoneLow !== null && zoneHigh !== null && (
        <>
          <rect x={Math.min(x(zoneLow), x(zoneHigh))} y={AXIS_Y - 16}
            width={Math.max(2, Math.abs(x(zoneHigh) - x(zoneLow)))} height={32}
            fill="rgba(63,185,80,0.14)" stroke="rgba(63,185,80,0.45)" strokeWidth={1} rx={3} />
          <text x={clampX((x(zoneLow) + x(zoneHigh)) / 2)} y={AXIS_Y + 34} fontSize={11.5}
            textAnchor="middle" fill={GOOD}>
            {labels.entryZone} {fmtQty(Math.min(zoneLow, zoneHigh))} – {fmtQty(Math.max(zoneLow, zoneHigh))}
          </text>
        </>
      )}
      {zoneLow !== null && zoneHigh === null && (
        <>
          <line x1={x(zoneLow)} y1={AXIS_Y - 16} x2={x(zoneLow)} y2={AXIS_Y + 16} stroke={GOOD} strokeWidth={2} strokeDasharray="5 4" />
          <text x={clampX(x(zoneLow))} y={AXIS_Y + 34} fontSize={11.5} textAnchor="middle" fill={GOOD}>
            {labels.entryZone} {fmtQty(zoneLow)}
          </text>
        </>
      )}
      {/* target / stop rules — labels above the axis, stacked apart */}
      {levels.map((l, i) => (
        <g key={l.kind}>
          <line x1={x(l.px)} y1={AXIS_Y - 18} x2={x(l.px)} y2={AXIS_Y + 18}
            stroke={l.color} strokeWidth={2} strokeDasharray="6 4" />
          <text x={clampX(x(l.px))} y={i === 0 ? 16 : 32} fontSize={11.5} textAnchor="middle" fill={l.color}>
            {l.label} {fmtQty(l.px)}
          </text>
        </g>
      ))}
      {/* algo's own target — faint, its own row, direct label */}
      {algoPx !== null && (
        <g opacity={0.55}>
          <line x1={x(algoPx)} y1={AXIS_Y - 12} x2={x(algoPx)} y2={AXIS_Y + 12}
            stroke="var(--text-muted,#a89f92)" strokeWidth={1.5} strokeDasharray="3 3" />
          <text x={clampX(x(algoPx))} y={AXIS_Y + 46} fontSize={10.5} textAnchor="middle" fill="var(--text-muted,#a89f92)">
            {labels.algo} {fmtQty(algoPx)}
          </text>
        </g>
      )}
      {/* axis end labels */}
      <text x={PAD - 20} y={H - 4} fontSize={10.5} fill="var(--text-muted,#a89f92)">{fmtQty(lo)}</text>
      <text x={W - PAD + 20} y={H - 4} fontSize={10.5} textAnchor="end" fill="var(--text-muted,#a89f92)">{fmtQty(hi)}</text>
    </svg>
  )
}

export function SlotOutlookPanel({ token, onClose }: { token: string | null; onClose: () => void }) {
  const { language } = useLanguage()
  const [fleets, setFleets] = useState<FleetOutlook[] | null>(null)
  const [error, setError] = useState('')
  const [openDialog, setOpenDialog] = useState<Record<string, boolean>>({})

  const T = {
    title: tr(language, { ko: '슬롯 전략 전망', en: 'Slot Strategy Outlook', ja: 'スロット戦略アウトルック', th: 'แผนกลยุทธ์ของสล็อต', vi: 'Triển vọng chiến lược từng slot', id: 'Prospek Strategi Slot' }),
    subtitle: tr(language, {
      ko: '데스크가 매 분석 주기마다 남기는 향후 계획입니다 — 진입 구간, 목표가, 무효화 기준, 그리고 그 계획을 지켰는지가 슬롯별로 기록됩니다.',
      en: "The desk's forward plan, kept per slot every analysis cycle — entry zone, target, invalidation, and whether the plan was followed.",
      ja: 'デスクが分析サイクルごとに残す先行きプランです — エントリーゾーン、目標、無効化条件、そしてプランが守られたかがスロット別に記録されます。',
      th: 'แผนล่วงหน้าที่เดสก์บันทึกไว้ทุกรอบการวิเคราะห์ — โซนเข้า เป้าหมาย เงื่อนไขยกเลิก และการปฏิบัติตามแผน แยกตามสล็อต',
      vi: 'Kế hoạch phía trước mà bàn giao dịch lưu mỗi chu kỳ phân tích — vùng vào lệnh, mục tiêu, điều kiện vô hiệu, và việc kế hoạch có được tuân thủ, theo từng slot.',
      id: 'Rencana ke depan yang disimpan desk setiap siklus analisis — zona masuk, target, pembatalan, dan apakah rencana diikuti, per slot.',
    }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    loading: tr(language, { ko: '불러오는 중…', en: 'Loading…', ja: '読み込み中…', th: 'กำลังโหลด…', vi: 'Đang tải…', id: 'Memuat…' }),
    failed: tr(language, { ko: '전망을 불러오지 못했습니다', en: 'Could not load the outlook', ja: 'アウトルックを読み込めませんでした', th: 'โหลดแผนไม่สำเร็จ', vi: 'Không tải được triển vọng', id: 'Gagal memuat prospek' }),
    noFleets: tr(language, {
      ko: '아직 플릿이 없습니다. 플릿이 시작되면 슬롯별 전략 전망이 여기에 표시됩니다.',
      en: 'No fleet yet. Once a fleet is live, each slot’s strategy outlook appears here.',
      ja: 'まだフリートがありません。フリートが稼働すると、スロットごとの戦略アウトルックがここに表示されます。',
      th: 'ยังไม่มีฟลีต เมื่อฟลีตเริ่มทำงาน แผนกลยุทธ์ของแต่ละสล็อตจะแสดงที่นี่',
      vi: 'Chưa có fleet nào. Khi fleet hoạt động, triển vọng chiến lược của từng slot sẽ hiển thị ở đây.',
      id: 'Belum ada fleet. Setelah fleet berjalan, prospek strategi tiap slot muncul di sini.',
    }),
    noSlots: tr(language, {
      ko: '이 플릿에는 아직 슬롯이 없습니다.',
      en: 'This fleet has no slots yet.',
      ja: 'このフリートにはまだスロットがありません。',
      th: 'ฟลีตนี้ยังไม่มีสล็อต',
      vi: 'Fleet này chưa có slot nào.',
      id: 'Fleet ini belum punya slot.',
    }),
    noRun: tr(language, {
      ko: '이 슬롯에는 아직 배정된 RUN이 없습니다.',
      en: 'No run is bound to this slot yet.',
      ja: 'このスロットにはまだ RUN が割り当てられていません。',
      th: 'ยังไม่มี RUN ผูกกับสล็อตนี้',
      vi: 'Chưa có run nào gắn với slot này.',
      id: 'Belum ada run yang terikat ke slot ini.',
    }),
    noOutlookYet: tr(language, {
      ko: '아직 전망이 없습니다 — 첫 계획은 30분 이내에 도착합니다.',
      en: 'No outlook yet — the first plan arrives within 30 minutes.',
      ja: 'まだアウトルックがありません — 最初のプランは30分以内に届きます。',
      th: 'ยังไม่มีแผน — แผนแรกจะมาถึงภายใน 30 นาที',
      vi: 'Chưa có triển vọng — kế hoạch đầu tiên sẽ đến trong vòng 30 phút.',
      id: 'Belum ada prospek — rencana pertama tiba dalam 30 menit.',
    }),
    fleet: tr(language, { ko: '플릿', en: 'Fleet', ja: 'フリート', th: 'ฟลีต', vi: 'Fleet', id: 'Fleet' }),
    slot: tr(language, { ko: '슬롯', en: 'Slot', ja: 'スロット', th: 'สล็อต', vi: 'Slot', id: 'Slot' }),
    every30: tr(language, { ko: '30분마다 갱신', en: 'updates every 30 min', ja: '30分ごとに更新', th: 'อัปเดตทุก 30 นาที', vi: 'cập nhật mỗi 30 phút', id: 'diperbarui tiap 30 menit' }),
    hourly: tr(language, { ko: '1시간마다 갱신', en: 'updates hourly', ja: '1時間ごとに更新', th: 'อัปเดตทุกชั่วโมง', vi: 'cập nhật mỗi giờ', id: 'diperbarui tiap jam' }),
    refreshed: tr(language, { ko: '갱신', en: 'refreshed', ja: '更新', th: 'อัปเดตเมื่อ', vi: 'làm mới', id: 'diperbarui' }),
    nextBy: tr(language, { ko: '다음', en: 'next by', ja: '次回', th: 'ครั้งถัดไป', vi: 'lần tới', id: 'berikutnya' }),
    biasLong: tr(language, { ko: '매수 편향', en: 'long', ja: 'ロング', th: 'ลอง', vi: 'long', id: 'long' }),
    biasShort: tr(language, { ko: '매도 편향', en: 'short', ja: 'ショート', th: 'ชอร์ต', vi: 'short', id: 'short' }),
    biasFlat: tr(language, { ko: '중립', en: 'flat', ja: 'フラット', th: 'เป็นกลาง', vi: 'trung lập', id: 'netral' }),
    entryZone: tr(language, { ko: '진입 구간', en: 'entry zone', ja: 'エントリーゾーン', th: 'โซนเข้า', vi: 'vùng vào lệnh', id: 'zona masuk' }),
    target: tr(language, { ko: '목표', en: 'target', ja: '目標', th: 'เป้าหมาย', vi: 'mục tiêu', id: 'target' }),
    stop: tr(language, { ko: '손절 기준', en: 'stop ref', ja: 'ストップ基準', th: 'จุดอ้างอิงตัดขาดทุน', vi: 'mốc dừng lỗ', id: 'acuan stop' }),
    trigger: tr(language, { ko: '진입 트리거', en: 'entry trigger', ja: 'エントリートリガー', th: 'ทริกเกอร์เข้า', vi: 'kích hoạt vào lệnh', id: 'pemicu masuk' }),
    timeExit: tr(language, { ko: '시간 청산', en: 'time exit', ja: '時間退出', th: 'ออกตามเวลา', vi: 'thoát theo thời gian', id: 'keluar berdasarkan waktu' }),
    invalidation: tr(language, { ko: '무효화', en: 'invalidation', ja: '無効化条件', th: 'เงื่อนไขยกเลิก', vi: 'điều kiện vô hiệu', id: 'pembatalan' }),
    horizon: tr(language, { ko: '전망 기간', en: 'horizon', ja: 'ホライズン', th: 'กรอบเวลา', vi: 'khung thời gian', id: 'horizon' }),
    hoursSuffix: tr(language, { ko: '시간', en: 'h', ja: '時間', th: ' ชม.', vi: ' giờ', id: ' jam' }),
    tgtAdopted: tr(language, { ko: '목표: 채택', en: 'targets: adopted', ja: '目標: 採用', th: 'เป้าหมาย: ใช้ตามเดิม', vi: 'mục tiêu: chấp nhận', id: 'target: diadopsi' }),
    tgtAdjusted: tr(language, { ko: '목표: 조정', en: 'targets: adjusted', ja: '目標: 調整', th: 'เป้าหมาย: ปรับแล้ว', vi: 'mục tiêu: điều chỉnh', id: 'target: disesuaikan' }),
    tgtOverridden: tr(language, { ko: '목표: 재정의', en: 'targets: overridden', ja: '目標: 上書き', th: 'เป้าหมาย: แทนที่', vi: 'mục tiêu: ghi đè', id: 'target: diganti' }),
    tgtAlgoFallback: tr(language, { ko: '목표: 알고리즘 대체', en: 'targets: algo fallback', ja: '目標: アルゴ代替', th: 'เป้าหมาย: อัลกอริทึมสำรอง', vi: 'mục tiêu: thuật toán dự phòng', id: 'target: cadangan algo' }),
    algoLabel: tr(language, { ko: '알고리즘', en: 'algo', ja: 'アルゴ', th: 'อัลกอริทึม', vi: 'thuật toán', id: 'algo' }),
    dialog: tr(language, { ko: '대화 기록', en: 'Dialog', ja: 'ダイアログ', th: 'บันทึกสนทนา', vi: 'Nhật ký hội thoại', id: 'Dialog' }),
    dialogEmpty: tr(language, { ko: '기록이 없습니다', en: 'No entries yet', ja: '記録はまだありません', th: 'ยังไม่มีบันทึก', vi: 'Chưa có mục nào', id: 'Belum ada entri' }),
    kindDecision: tr(language, { ko: '판단', en: 'decision', ja: '判断', th: 'การตัดสินใจ', vi: 'quyết định', id: 'keputusan' }),
    kindOutlook: tr(language, { ko: '향후 계획', en: 'forward plan', ja: '先行きプラン', th: 'แผนล่วงหน้า', vi: 'kế hoạch phía trước', id: 'rencana ke depan' }),
    standing: tr(language, { ko: '대기 계획', en: 'standing', ja: 'スタンディング', th: 'แผนคงค้าง', vi: 'kế hoạch chờ', id: 'rencana tetap' }),
    adhFollowed: tr(language, { ko: '계획 준수', en: 'plan: followed', ja: 'プラン遵守', th: 'ตามแผน', vi: 'theo kế hoạch', id: 'sesuai rencana' }),
    adhRevised: tr(language, { ko: '계획 수정', en: 'plan: revised', ja: 'プラン修正', th: 'แก้แผน', vi: 'sửa kế hoạch', id: 'rencana direvisi' }),
    adhDeviated: tr(language, { ko: '계획 이탈', en: 'plan: deviated', ja: 'プラン逸脱', th: 'เบี่ยงจากแผน', vi: 'lệch kế hoạch', id: 'menyimpang dari rencana' }),
  }

  const biasText: Record<string, string> = { long: T.biasLong, short: T.biasShort, flat: T.biasFlat }
  const adhText: Record<string, string> = { followed: T.adhFollowed, revised: T.adhRevised, deviated: T.adhDeviated }
  const verdictText: Record<string, string> = {
    adopted: T.tgtAdopted, adjusted: T.tgtAdjusted, overridden: T.tgtOverridden, algo_fallback: T.tgtAlgoFallback,
  }

  const load = useCallback(async () => {
    if (!token) return
    try {
      const headers = { Authorization: `Bearer ${token}` }
      const fl = await fetch(`${API_BASE}/fleets`, { headers })
      if (!fl.ok) throw new Error(`HTTP ${fl.status}`)
      const fd = await fl.json()
      // Every non-stopped fleet gets its outlook; a member with only stopped
      // fleets still sees the newest one's last plans rather than a blank.
      const all: FleetRef[] = fd.fleets || []
      const live = all.filter(f => f.status !== 'stopped')
      const targets = live.length > 0 ? live : all.slice(0, 1)
      const results = await Promise.all(targets.map(async f => {
        const r = await fetch(
          `${API_BASE}/fleets/${f.id}/outlook?lang=${encodeURIComponent(language)}&dialog_limit=12`,
          { headers })
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return (await r.json()) as FleetOutlook
      }))
      setFleets(results)
      setError('')
    } catch { setError(T.failed) }
    // T.failed changes with language only; language is already a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, language])

  useEffect(() => {
    load()
    // The fast markets refresh on the 30-min cycle; polling once a minute
    // keeps the panel current without hammering the endpoint (same cadence
    // as the desk-cycles panel).
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [load])

  const card: any = { border: '1px solid var(--border-color,rgba(0,0,0,0.12))', borderRadius: 10, marginBottom: 10, padding: '12px 14px' }
  const meta: any = { fontSize: 11.5, color: 'var(--text-secondary,#8a8073)' }
  const num: any = { fontVariantNumeric: 'tabular-nums' }
  const badge = (bg: string, color: string): any => ({
    fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 5, background: bg, color,
  })
  const biasBadge = (bias: string) =>
    bias === 'long' ? badge('rgba(63,185,80,0.16)', GOOD)
      : bias === 'short' ? badge('rgba(240,102,63,0.16)', DANGER)
        : badge('rgba(138,128,115,0.16)', 'var(--text-secondary,#8a8073)')
  const tag: any = { fontSize: 10.5, fontWeight: 600, padding: '1px 6px', borderRadius: 4, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', color: 'var(--text-secondary,#8a8073)' }

  return (
    // z 600 + 32px top padding: the sticky top nav is z-index 500 — same
    // modal shell as the desk-cycles and analyst panels.
    <div role="dialog" aria-modal="true" aria-label={T.title} onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 24px 24px', overflowY: 'auto' }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 860, margin: 'auto', background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>📋 {T.title}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.subtitle}</div>
          </div>
          <button onClick={onClose}
            style={{ padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>
            {T.close}
          </button>
        </div>

        {error && <div style={{ color: DANGER, fontSize: 13 }}>⚠️ {error}</div>}
        {!error && fleets === null && <div style={meta}>{T.loading}</div>}
        {!error && fleets !== null && fleets.length === 0 && <div style={meta}>{T.noFleets}</div>}

        {!error && (fleets || []).map(f => (
          <div key={f.fleet_id} style={{ marginBottom: 16 }}>
            {(fleets || []).length > 1 && (
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{T.fleet} #{f.fleet_id}</div>
            )}
            {f.slots.length === 0 && <div style={meta}>{T.noSlots}</div>}

            {f.slots.map(s => {
              const o = s.outlook
              const key = `${f.fleet_id}:${s.slot_index}`
              const fast = s.market !== null && FAST_MARKETS.has(s.market)
              const dialogOpen = !!openDialog[key]
              // The desk-vs-algorithm basis (additive field; older events
              // lack it). The algo's target becomes a faint strip marker only
              // when the desk changed it — same number twice is clutter.
              const basis = o && o.basis ? o.basis : null
              const algoTgt = basis
                && (basis.verdict === 'adjusted' || basis.verdict === 'overridden')
                && basis.algo && basis.algo.target_px !== null && Number.isFinite(basis.algo.target_px)
                && basis.algo.target_px !== (o && o.exit ? o.exit.target_px : null)
                ? basis.algo.target_px : null
              return (
                <div key={key} style={card}>
                  {/* ── header ── */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: 13.5 }}>
                      {T.slot} {s.slot_index}{s.symbol ? ` · ${s.symbol}` : ''}
                    </span>
                    {s.market && <span style={meta}>{marketLabel(s.market, language)}</span>}
                    {o && <span style={biasBadge(o.bias)}>{biasText[o.bias] || o.bias}</span>}
                    {s.run_id !== null && (
                      <span style={{ ...tag }}>{fast ? T.every30 : T.hourly}</span>
                    )}
                    {basis && basis.verdict && (
                      <span style={tag}>{verdictText[basis.verdict] || basis.verdict}</span>
                    )}
                    <span style={{ marginLeft: 'auto', ...meta, ...num }}>
                      {s.outlook_ts && <span title={fullStamp(s.outlook_ts, language)}>{T.refreshed} {hhmm(s.outlook_ts, language)}</span>}
                      {s.next_refresh_by && <span title={fullStamp(s.next_refresh_by, language)}> · {T.nextBy} ≤ {hhmm(s.next_refresh_by, language)}</span>}
                    </span>
                  </div>

                  {/* ── body: levels + narrative, or the empty state ── */}
                  {s.run_id === null ? (
                    <div style={{ ...meta, marginTop: 8 }}>{T.noRun}</div>
                  ) : !o ? (
                    <div style={{ ...meta, marginTop: 8 }}>{T.noOutlookYet}</div>
                  ) : (
                    <>
                      <LevelsStrip outlook={o} algoTarget={algoTgt}
                        labels={{ entryZone: T.entryZone, target: T.target, stop: T.stop, trigger: T.trigger, algo: T.algoLabel }} />
                      {o.entry && o.entry.kind === 'trigger' && o.entry.trigger &&
                        (o.exit && (o.exit.target_px !== null || o.exit.stop_ref_px !== null)) && (
                        <div style={{ ...meta, marginBottom: 4 }}>⚡ {T.trigger}: {o.entry.trigger}</div>
                      )}
                      {o.narrative && (
                        <p style={{ margin: '6px 0 0', fontSize: 13, lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
                          {o.narrative}
                        </p>
                      )}
                      {/* the desk↔algorithm discussion over which targets won */}
                      {basis && basis.discussion && (
                        <div style={{ ...meta, marginTop: 5, fontStyle: 'italic' }}>💬 {basis.discussion}</div>
                      )}
                      <div style={{ ...meta, marginTop: 6, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        {o.invalidation && <span>🚫 {T.invalidation}: {o.invalidation}</span>}
                        {o.exit && o.exit.time_exit && <span>⏱ {T.timeExit}: {o.exit.time_exit}</span>}
                        {o.horizon_hours !== null && Number.isFinite(o.horizon_hours) && (
                          <span style={num}>{T.horizon} ≈ {o.horizon_hours}{T.hoursSuffix}</span>
                        )}
                      </div>
                    </>
                  )}

                  {/* ── dialog: the desk's reasoning tail, collapsed by default ── */}
                  {s.dialog.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <button onClick={() => setOpenDialog(d => ({ ...d, [key]: !d[key] }))}
                        style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11.5, fontWeight: 600, cursor: 'pointer', border: '1px solid var(--border-color,rgba(0,0,0,0.15))', background: 'transparent', color: 'var(--text-secondary,#8a8073)' }}>
                        {dialogOpen ? '▾' : '▸'} {T.dialog} ({s.dialog.length})
                      </button>
                      {dialogOpen && (
                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {s.dialog.map((row, i) => (
                            <div key={i} style={{
                              borderRadius: 9, padding: '7px 11px', fontSize: 12.5, lineHeight: 1.5,
                              background: row.kind === 'outlook' ? 'rgba(63,185,80,0.07)' : 'var(--bg-secondary,rgba(0,0,0,0.04))',
                              borderLeft: row.kind === 'outlook' ? `3px solid ${GOOD}` : '3px solid transparent',
                            }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 3 }}>
                                <span style={{ ...meta, fontWeight: 700 }}>
                                  {row.kind === 'outlook' ? T.kindOutlook : T.kindDecision}
                                </span>
                                <span style={{ ...meta, ...num }} title={fullStamp(row.ts, language)}>{hhmm(row.ts, language)}</span>
                                {row.plan_adherence && (
                                  <span style={{ ...tag,
                                    color: row.plan_adherence === 'deviated' ? DANGER : row.plan_adherence === 'followed' ? GOOD : undefined,
                                    borderColor: row.plan_adherence === 'deviated' ? 'rgba(240,102,63,0.4)' : row.plan_adherence === 'followed' ? 'rgba(63,185,80,0.4)' : undefined }}>
                                    {adhText[row.plan_adherence] || row.plan_adherence}
                                  </span>
                                )}
                                {row.source === 'sweeper' && <span style={tag}>{T.standing}</span>}
                              </div>
                              <div style={{ whiteSpace: 'pre-wrap' }}>{row.text}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
