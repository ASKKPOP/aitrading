import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react'
import { createPortal } from 'react-dom'
import { API_BASE, marketLabel, useLanguage } from '../appShared'
import { statusLabel } from '../pages/RunsLivePage'
import { GuideBadge, HelpTip } from './HelpTip'
import { FleetAiFeed } from './FleetAiFeed'
import { tr } from '../i18n'

// Plan 14 — Full Auto (fleet mode). The user sets only N and presses go; the
// AI researches every automatable market, composes N TRADINGs with
// expected-profit theses, keeps the fleet at N until the user stops it, and
// pauses everything at −30% (SMS) / stops everything at −40% (SMS).
//
// Async failure states (build_failed, partial:k/N, replenishing:k/N,
// drawdown_warning) arrive via fleet status_reason — localized here through
// the reasonLabel map, never through the API error boundary (no request is
// in flight when the worker discovers them).

type Fleet = {
  id: number; status: string; status_reason: string | null
  n_runs: number; total_budget_usd: number; risk_appetite: string
  archetype?: string
  recommended_max_n_runs?: number | null
  profit_target_frac?: number | null; successor_fleet_id?: number | null
  warn_loss_frac: number; stop_loss_frac: number
  warn_latched_at: string | null; warn_acked_at: string | null
  entry_paused_reason: string | null; held_by_master: number
  market_scope?: string[] | null
  stopped_at?: string | null
}
// Rebased to 100 at launch, so an N-symbol sleeve is readable on its own
// terms instead of being lost inside the account total. Server-computed from
// marked_equity (routes_fleets.fleet_index); null when equity is unreadable —
// never render a fabricated number.
type FleetIndex = {
  base: number; value: number; pnl_usd: number; pnl_pct: number
  budget_usd: number; equity_usd: number; since: string | null
}
type Member = {
  run_id: number; symbol: string; market: string; status: string
  status_reason: string | null; paused_reason: string | null
  run_budget_usd: number | null; realized_pnl_usd: number | null
  unrealized_pnl_usd?: number | null; total_pnl_usd?: number | null
  thesis: { direction?: string; rationale?: string; confidence?: number } | null
}
type Entitlements = {
  plan: string | null; max_fleet_size: number; default_budget_usd: number
}

// Owner (2026-08-31): the risk tier, strategy archetype, and leverage
// choosers were removed from the form — those are the Desk's decisions.
// The create request omits them; the server applies its desk-managed
// defaults (standard tier, short archetype, tier-auto leverage).

// Markets a fleet may be scoped to. Mirrors markets.automatable_markets() on
// the server, which validates the request — an empty selection sends null and
// means "every market", exactly as before this picker existed.
const FLEET_MARKETS = ['crypto', 'us-stock', 'futures', 'forex']

// monitorOnly: a monitor-only box — renders nothing until an active fleet
// exists, and never shows the creation form. (/automation now uses
// `combined` at the top of the page; the create modal uses the default.) onSelectRun opens a member TRADING's full detail drawer
// (sparkline + event log + pause/stop) via RunsLiveSection.openRunRequest.
// combined (owner ask 2026-11-20): the Full Auto order form sits at the TOP
// of /automation — the creation form while no fleet is live, the live monitor
// (+ base plan + 30-minute AI analysis feed) once one is.
export function FleetPanel({ token, monitorOnly = false, combined = false, onSelectRun,
  blockCreate = false, aiFeedHost }: {
  token: string; monitorOnly?: boolean; combined?: boolean; onSelectRun?: (runId: number) => void
  // Owner 2026-11-20: while any TRADING is live, nothing new is made — the
  // top box shows no create form (a live fleet's monitor still renders).
  blockCreate?: boolean
  // Owner 2026-11-20 ("AI feed to page end"): where the 30-minute AI feed
  // renders. undefined = inline in this box (old layout); null = the page's
  // slot is not mounted yet (render nothing); an element = portal into it.
  aiFeedHost?: HTMLElement | null
}) {
  const { language } = useLanguage()
  const T = {
    title: tr(language, { ko: 'N종목 자동 편성 — AI가 전부 알아서', en: 'Full Auto — the AI does everything', ja: '完全自動 — AIがすべて実行', th: 'อัตโนมัติเต็มรูปแบบ — AI จัดการทั้งหมด', vi: 'Tự động hoàn toàn — AI làm tất cả', id: 'Full Auto — AI mengerjakan semuanya' }),
    desc: tr(language, { ko: 'TRADING 개수만 정하세요 — AI가 전 시장을 리서치해 종목을 고르고, TRADING을 만들어 등록하고, 결과를 다음 판단에 반영하며, 멈출 때까지 개수를 유지합니다. 정지 버튼은 항상 당신에게 있습니다.', en: 'Set only how many TRADINGs — the AI researches the markets, picks the symbols, registers the TRADINGs, feeds every result into the next step, and keeps the count until you stop. You always keep the stop button.', ja: 'TRADING の数だけ設定 — AIが全市場をリサーチして銘柄を選び、TRADING を登録し、結果を次の判断に反映し、停止するまで数を維持します。', th: 'ตั้งแค่จำนวน TRADING — AI รีเสิร์ชตลาด เลือกเหรียญ สร้าง TRADING และรักษาจำนวนจนกว่าคุณจะหยุด', vi: 'Chỉ đặt số lượng TRADING — AI nghiên cứu thị trường, chọn mã, đăng ký TRADING và giữ số lượng cho đến khi bạn dừng.', id: 'Cukup tentukan berapa banyak TRADING — AI meriset pasar, memilih simbol, mendaftarkan TRADING, mengalirkan setiap hasil ke langkah berikutnya, dan menjaga jumlahnya sampai Anda menghentikannya. Tombol stop selalu ada di tangan Anda.' }),
    nRuns: tr(language, { ko: 'TRADING 개수', en: 'Number of TRADINGs', ja: 'TRADING 数', th: 'จำนวน TRADING', vi: 'Số TRADING', id: 'Jumlah TRADING' }),
    budget: tr(language, { ko: '총 예산 ($) — 자동 제안됨', en: 'Total budget ($) — pre-filled', ja: '総予算 ($) — 自動提案', th: 'งบรวม ($) — เติมให้อัตโนมัติ', vi: 'Tổng ngân sách ($) — điền sẵn', id: 'Total anggaran ($) — sudah terisi' }),
    deskDecides: tr(language, { ko: '위험 수준 · 전략 유형 · 레버리지는 Sooppiy AI 데스크가 스스로 정합니다.', en: 'Risk level, strategy type, and leverage are decided by the Sooppiy AI desk.', ja: 'リスク水準・戦略タイプ・レバレッジは Sooppiy AI デスクが自ら決定します。', th: 'ระดับความเสี่ยง · ประเภทกลยุทธ์ · เลเวอเรจ ตัดสินโดยเดสก์ Sooppiy AI', vi: 'Mức rủi ro, loại chiến lược và đòn bẩy do bàn Sooppiy AI tự quyết định.', id: 'Tingkat risiko, jenis strategi, dan leverage diputuskan oleh desk Sooppiy AI.' }),
    launch: tr(language, { ko: '🚀 플릿 시작', en: '🚀 Launch fleet', ja: '🚀 フリート開始', th: '🚀 เริ่มฟลีต', vi: '🚀 Khởi chạy', id: '🚀 Luncurkan fleet' }),
    stopAll: tr(language, { ko: '⏹ 전체 정지 (청산)', en: '⏹ Stop all (flatten)', ja: '⏹ 全停止（清算）', th: '⏹ หยุดทั้งหมด (ปิดสถานะ)', vi: '⏹ Dừng tất cả (đóng lệnh)', id: '⏹ Hentikan semua (tutup posisi)' }),
    editFleet: tr(language, { ko: '플릿 수정', en: 'Edit fleet', ja: 'フリート編集', th: 'แก้ไขฟลีต', vi: 'Sửa fleet', id: 'Edit fleet' }),
    editFleetSub: tr(language, { ko: '가동 중에도 목표 수익과 슬롯 수를 바꿀 수 있습니다', en: 'Change the profit goal and slot count while the fleet is running', ja: '稼働中でも目標利益とスロット数を変更できます', th: 'เปลี่ยนเป้ากำไรและจำนวนสล็อตได้ระหว่างทำงาน', vi: 'Đổi mục tiêu lợi nhuận và số slot khi fleet đang chạy', id: 'Ubah target profit dan jumlah slot saat fleet berjalan' }),
    pause: tr(language, { ko: '일시정지', en: 'Pause', ja: '一時停止', th: 'พัก', vi: 'Tạm dừng', id: 'Jeda' }),
    resume: tr(language, { ko: '재개', en: 'Resume', ja: '再開', th: 'ดำเนินต่อ', vi: 'Tiếp tục', id: 'Lanjutkan' }),
    resumeWarning: tr(language, { ko: '경고 확인 후 거래 재개 (본인 책임)', en: 'Resume trading (your responsibility)', ja: '警告を確認して再開（自己責任）', th: 'ดำเนินการต่อ (ความรับผิดชอบของคุณ)', vi: 'Tiếp tục giao dịch (bạn tự chịu trách nhiệm)', id: 'Lanjutkan trading (tanggung jawab Anda)' }),
    // Fleets moved to Professional+ with the tier gates (PR #198) — keep this
    // wording in step with entitlements.PLAN_LIMITS max_fleet_size.
    needPlan: tr(language, { ko: '완전자동 플릿은 Professional 이상 요금제에서 사용할 수 있습니다', en: 'Full Auto fleets need a Professional plan or above', ja: '完全自動フリートは Professional 以上のプランで利用できます', th: 'ฟลีตอัตโนมัติต้องใช้แผน Professional ขึ้นไป', vi: 'Đội hình tự động cần gói Professional trở lên', id: 'Fleet Full Auto memerlukan paket Professional atau di atasnya' }),
    equity: tr(language, { ko: '평가 자산', en: 'Marked equity', ja: '評価資産', th: 'มูลค่าตามราคาตลาด', vi: 'Giá trị theo thị trường', id: 'Ekuitas berbasis harga pasar' }),
    indexLabel: tr(language, { ko: 'N종목 지수', en: 'Fleet index', ja: 'フリート指数',
      th: 'ดัชนีกองทุน', vi: 'Chỉ số nhóm', id: 'Indeks fleet' }),
    indexBase: tr(language, { ko: '기준', en: 'base', ja: '基準', th: 'ฐาน', vi: 'gốc', id: 'basis' }),
    indexBudget: tr(language, { ko: '예산', en: 'budget', ja: '予算', th: 'งบ', vi: 'ngân sách', id: 'anggaran' }),
    // ── fleet index guide ((?) on the index card) ──
    idxGuideOpen: tr(language, { ko: '지수 설명 보기', en: 'What is this index?', ja: 'この指数とは？', th: 'ดัชนีนี้คืออะไร', vi: 'Chỉ số này là gì?', id: 'Apa indeks ini?' }),
    idxGuideTitle: tr(language, { ko: 'N종목 지수란?', en: 'What is the fleet index?', ja: 'フリート指数とは？', th: 'ดัชนีฟลีตคืออะไร?', vi: 'Chỉ số nhóm là gì?', id: 'Apa itu indeks fleet?' }),
    idxGuideWhat: tr(language, {
      ko: '이 숫자는 코인 가격도, 계좌 잔고도 아닙니다. 이 플릿(자동 편성)만의 성과 지수로, 플릿을 시작한 순간을 100으로 놓고 다시 계산한 값입니다.',
      en: 'This number is not a coin price and not your account balance. It is this fleet\'s own performance index, rebased to 100 at the moment the fleet launched.',
      ja: 'この数字はコイン価格でも口座残高でもありません。このフリートだけの成果指数で、開始時点を100として再計算した値です。',
      th: 'ตัวเลขนี้ไม่ใช่ราคาเหรียญและไม่ใช่ยอดเงินในบัญชี แต่เป็นดัชนีผลงานของฟลีตนี้เอง โดยตั้งจุดเริ่มต้นไว้ที่ 100 ณ ตอนเริ่มฟลีต',
      vi: 'Con số này không phải giá coin và không phải số dư tài khoản. Nó là chỉ số hiệu quả riêng của nhóm này, quy về 100 tại thời điểm khởi chạy.',
      id: 'Angka ini bukan harga koin dan bukan saldo akun Anda. Ini adalah indeks kinerja fleet ini sendiri, ditetapkan ulang ke 100 pada saat fleet diluncurkan.' }),
    idxGuideRead: tr(language, {
      ko: '읽는 법: 100보다 크면 수익, 작으면 손실입니다. 예를 들어 99.93은 예산 대비 −0.07%라는 뜻입니다. 옆의 %와 $ 값은 같은 변화를 예산 기준 백분율과 금액으로 보여줍니다.',
      en: 'How to read it: above 100 means profit, below 100 means loss. For example 99.93 means −0.07% on the fleet budget. The % and $ beside it show that same change as a percentage and in dollars.',
      ja: '読み方: 100より上なら利益、下なら損失。例えば99.93は予算比−0.07%という意味です。隣の%と$は同じ変化を百分率と金額で示します。',
      th: 'วิธีอ่าน: สูงกว่า 100 คือกำไร ต่ำกว่า 100 คือขาดทุน เช่น 99.93 หมายถึง −0.07% ของงบฟลีต ส่วน % และ $ ข้าง ๆ แสดงการเปลี่ยนแปลงเดียวกันเป็นเปอร์เซ็นต์และจำนวนเงิน',
      vi: 'Cách đọc: trên 100 là lãi, dưới 100 là lỗ. Ví dụ 99.93 nghĩa là −0.07% trên ngân sách nhóm. Giá trị % và $ bên cạnh thể hiện cùng thay đổi đó theo phần trăm và bằng tiền.',
      id: 'Cara membacanya: di atas 100 berarti untung, di bawah 100 berarti rugi. Misalnya 99.93 berarti −0.07% dari anggaran fleet. Nilai % dan $ di sampingnya menunjukkan perubahan yang sama dalam persentase dan dolar.' }),
    idxGuideWhy: tr(language, {
      ko: '왜 지수로 보여주나요? 계좌 전체 합계에서는 작은 플릿의 성과가 보이지 않기 때문입니다. 100 기준으로 다시 계산하면 예산이 다른 플릿끼리도 성과를 바로 비교할 수 있습니다.',
      en: 'Why an index? In the account total, a small fleet\'s result is invisible. Rebasing to 100 makes fleets of different budgets directly comparable.',
      ja: 'なぜ指数？口座合計では小さなフリートの成果が見えないためです。100基準なら予算が違うフリート同士も直接比較できます。',
      th: 'ทำไมต้องเป็นดัชนี? เพราะในยอดรวมบัญชี ผลงานของฟลีตเล็ก ๆ จะมองไม่เห็น การตั้งฐานที่ 100 ทำให้เทียบฟลีตที่งบต่างกันได้ทันที',
      vi: 'Tại sao dùng chỉ số? Trong tổng tài khoản, kết quả của một nhóm nhỏ sẽ không nhìn thấy được. Quy về 100 giúp so sánh trực tiếp các nhóm có ngân sách khác nhau.',
      id: 'Mengapa indeks? Dalam total akun, hasil fleet kecil tidak terlihat. Penetapan ulang ke 100 membuat fleet dengan anggaran berbeda dapat dibandingkan langsung.' }),
    idxGuideLine: tr(language, {
      ko: '아래 작은 줄의 의미 — 기준 100: 시작점 · 예산: 이 플릿에 배정된 금액 · 날짜: 플릿 시작일.',
      en: 'The small line underneath — base 100: the starting point · budget: the amount allocated to this fleet · date: the fleet\'s launch date.',
      ja: '下の小さな行の意味 — 基準100: 開始点 · 予算: このフリートへの配分額 · 日付: 開始日。',
      th: 'บรรทัดเล็กด้านล่าง — ฐาน 100: จุดเริ่มต้น · งบ: จำนวนเงินที่จัดสรรให้ฟลีตนี้ · วันที่: วันเริ่มฟลีต',
      vi: 'Dòng nhỏ bên dưới — gốc 100: điểm xuất phát · ngân sách: số tiền phân bổ cho nhóm này · ngày: ngày khởi chạy.',
      id: 'Baris kecil di bawah — basis 100: titik awal · anggaran: jumlah yang dialokasikan ke fleet ini · tanggal: tanggal peluncuran fleet.' }),
    idxGuideAccount: tr(language, {
      ko: '내 전체 자산이 궁금하면 페이지 상단의 계좌 요약(현재 예치금 · 총 수익)을 보세요 — 이 지수는 이 플릿 하나만 답합니다.',
      en: 'For your overall money, look at the account summary at the top of the page (deposit · profit) — this index answers only for this one fleet.',
      ja: '資産全体は上部の口座サマリー（預入・総収益）を見てください — この指数はこのフリートだけの答えです。',
      th: 'หากอยากรู้เงินโดยรวม ให้ดูสรุปบัญชีด้านบนของหน้า (เงินฝาก · กำไร) — ดัชนีนี้ตอบเฉพาะฟลีตนี้เท่านั้น',
      vi: 'Về tổng tài sản, hãy xem phần tóm tắt tài khoản ở đầu trang (số dư · lợi nhuận) — chỉ số này chỉ trả lời cho riêng nhóm này.',
      id: 'Untuk keseluruhan dana Anda, lihat ringkasan akun di bagian atas halaman (setoran · keuntungan) — indeks ini hanya menjawab untuk fleet yang satu ini.' }),
    basePlan: tr(language, { ko: '기본 계획 (내 주문)', en: 'Base plan (your order)', ja: '基本計画（あなたの注文）', th: 'แผนพื้นฐาน (คำสั่งของคุณ)', vi: 'Kế hoạch gốc (lệnh của bạn)', id: 'Rencana dasar (pesanan Anda)' }),
    basePlanMarkets: tr(language, { ko: '시장:', en: 'markets:', ja: '市場:', th: 'ตลาด:', vi: 'thị trường:', id: 'pasar:' }),
    basePlanHint: tr(language, { ko: 'AI는 이 계획 안에서만 종목을 고르고 매수·매도합니다 — 개수·예산·시장을 넘지 않습니다.', en: 'The AI picks symbols and buys/sells only inside this plan — never beyond its count, budget or markets.', ja: 'AIはこの計画の範囲内でのみ銘柄を選び売買します — 数・予算・市場を超えません。', th: 'AI เลือกเหรียญและซื้อขายภายในแผนนี้เท่านั้น — ไม่เกินจำนวน งบ หรือตลาด', vi: 'AI chỉ chọn mã và mua/bán trong kế hoạch này — không vượt số lượng, ngân sách hay thị trường.', id: 'AI memilih simbol dan membeli/menjual hanya di dalam rencana ini — tidak pernah melampaui jumlah, anggaran, atau pasarnya.' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    monitorTitle: tr(language, { ko: 'N종목 자동 편성 — 실시간 모니터', en: 'Full Auto — live monitor', ja: '完全自動編成 — ライブモニター', th: 'อัตโนมัติเต็มรูปแบบ — มอนิเตอร์สด', vi: 'Tự động hoàn toàn — theo dõi trực tiếp', id: 'Full Auto — monitor langsung' }),
    buildingHint: tr(language, { ko: 'AI가 시장을 리서치해 TRADING을 구성하는 중입니다 — 완성되는 대로 여기에 하나씩 나타납니다', en: 'The AI is researching the markets and composing the TRADINGs — each one appears here as it is built', ja: 'AIが市場をリサーチして TRADING を構成中 — 完成し次第ここに表示されます', th: 'AI กำลังรีเสิร์ชตลาดและสร้าง TRADING — จะแสดงที่นี่ทีละรายการ', vi: 'AI đang nghiên cứu thị trường và tạo các TRADING — sẽ hiện ở đây khi hoàn thành', id: 'AI sedang meriset pasar dan menyusun TRADING — masing-masing muncul di sini begitu selesai dibuat' }),
    clickHint: tr(language, { ko: '카드를 누르면 개별 TRADING의 실시간 모니터링(차트·이벤트 로그·일시정지/정지)이 열립니다', en: 'Click a card to open that TRADING\'s live monitor (chart · event log · pause/stop)', ja: 'カードをクリックすると各 TRADING のライブモニター（チャート・イベントログ・一時停止/停止）が開きます', th: 'คลิกการ์ดเพื่อเปิดจอมอนิเตอร์สดของ TRADING นั้น (กราฟ · บันทึกเหตุการณ์ · พัก/หยุด)', vi: 'Nhấp vào thẻ để mở màn hình theo dõi trực tiếp của TRADING đó (biểu đồ · nhật ký · tạm dừng/dừng)', id: 'Klik sebuah kartu untuk membuka monitor langsung TRADING itu (grafik · catatan peristiwa · jeda/hentikan)' }),
    memberBudget: tr(language, { ko: '예산', en: 'Budget', ja: '予算', th: 'งบ', vi: 'Ngân sách', id: 'Anggaran' }),
    showFinished: tr(language, { ko: '종료된 TRADING 보기', en: 'Show finished TRADINGs',
      ja: '終了した TRADING を表示', th: 'แสดง TRADING ที่จบแล้ว', vi: 'Hiện TRADING đã kết thúc', id: 'Tampilkan TRADING yang selesai' }),
    hideFinished: tr(language, { ko: '종료된 TRADING 숨기기', en: 'Hide finished TRADINGs',
      ja: '終了した TRADING を隠す', th: 'ซ่อน TRADING ที่จบแล้ว', vi: 'Ẩn TRADING đã kết thúc', id: 'Sembunyikan TRADING yang selesai' }),
    tabMonitor: tr(language, { ko: '실시간 모니터', en: 'Live monitor', ja: 'ライブモニター', th: 'มอนิเตอร์สด', vi: 'Theo dõi trực tiếp', id: 'Monitor langsung' }),
    tabActivity: tr(language, { ko: '거래 활동', en: 'Trading activity', ja: '取引アクティビティ', th: 'กิจกรรมเทรด', vi: 'Hoạt động giao dịch', id: 'Aktivitas trading' }),
    actAll: tr(language, { ko: '전체', en: 'All', ja: '全て', th: 'ทั้งหมด', vi: 'Tất cả', id: 'Semua' }),
    actType: tr(language, { ko: '유형', en: 'Type', ja: 'タイプ', th: 'ประเภท', vi: 'Loại', id: 'Jenis' }),
    actQty: tr(language, { ko: '수량', en: 'Amount', ja: '数量', th: 'จำนวน', vi: 'Số lượng', id: 'Jumlah' }),
    actPrice: tr(language, { ko: '가격', en: 'Price', ja: '価格', th: 'ราคา', vi: 'Giá', id: 'Harga' }),
    actPnl: tr(language, { ko: '손익', en: 'P&L', ja: '損益', th: 'กำไร/ขาดทุน', vi: 'Lãi/lỗ', id: 'Laba rugi' }),
    actDate: tr(language, { ko: '날짜', en: 'Date', ja: '日付', th: 'วันที่', vi: 'Ngày', id: 'Tanggal' }),
    actEmpty: tr(language, { ko: '아직 거래 활동이 없습니다', en: 'No trading activity yet', ja: '取引はまだありません', th: 'ยังไม่มีกิจกรรมเทรด', vi: 'Chưa có hoạt động giao dịch', id: 'Belum ada aktivitas trading' }),
    holdBanner: tr(language, { ko: '⚠️ 마스터 스위치로 전체 보류 중 — 손절/익절 청산은 계속 작동하며, 이미 실행 중인 사이클은 신규 진입 없이 마무리됩니다', en: '⚠️ Held by the master switch — protective exits (SL/TP) stay active; any cycle already executing completes without opening new positions', ja: '⚠️ マスタースイッチで保留中 — SL/TPの保護決済は動作し続けます', th: '⚠️ ถูกพักโดยสวิตช์หลัก — SL/TP ยังทำงาน', vi: '⚠️ Đang giữ bởi công tắc chính — SL/TP vẫn hoạt động', id: '⚠️ Ditahan oleh sakelar utama — keluar proteksi (SL/TP) tetap aktif; siklus yang sudah berjalan diselesaikan tanpa membuka posisi baru' }),
  }
  // fleet status_reason → localized label (the RunsLivePage reasonLabel
  // pattern; unmapped keys render the raw string rather than nothing)
  const reasonLabel = (reason: string | null): string | null => {
    if (!reason) return null
    if (reason.startsWith('partial:')) return tr(language, { ko: `일부만 구성됨 (${reason.slice(8)})`, en: `Built ${reason.slice(8)}`, ja: `一部のみ構成 (${reason.slice(8)})`, th: `สร้างได้ ${reason.slice(8)}`, vi: `Đã tạo ${reason.slice(8)}`, id: `Terbentuk ${reason.slice(8)}` })
    if (reason.startsWith('replenishing:')) return tr(language, { ko: `보충 대기 중 (${reason.slice(13)})`, en: `Replenishing (${reason.slice(13)})`, ja: `補充待ち (${reason.slice(13)})`, th: `กำลังเติม (${reason.slice(13)})`, vi: `Đang bổ sung (${reason.slice(13)})`, id: `Menunggu pemenuhan (${reason.slice(13)})` })
    const map: Record<string, any> = {
      build_failed: { ko: '구성 실패 — 후보 종목이 없습니다. 잠시 후 다시 시도하세요', en: 'Build failed — no eligible candidates; try again later', ja: '構成失敗 — 候補がありません', th: 'สร้างไม่สำเร็จ — ไม่มีตัวเลือก', vi: 'Tạo thất bại — không có ứng viên', id: 'Pembentukan gagal — tidak ada kandidat yang memenuhi syarat; coba lagi nanti' },
      breaker: { ko: `−${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% 방어선 작동 — 전체 청산됨`, en: `−${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% stop rail fired — everything closed`, ja: `−${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% レール作動 — 全決済`, th: 'ราวหยุดทำงาน — ปิดทั้งหมด', vi: 'Ngưỡng dừng kích hoạt — đã đóng tất cả', id: `Batas stop −${Math.round((fleet?.stop_loss_frac || 0.4) * 100)}% terpicu — semuanya ditutup` },
      drawdown_warning: { ko: '손실 경고 — 신규 진입 정지됨', en: 'Drawdown warning — new entries paused', ja: 'ドローダウン警告 — 新規停止', th: 'เตือนขาดทุน — พักการเข้าใหม่', vi: 'Cảnh báo sụt giảm — tạm dừng lệnh mới', id: 'Peringatan penurunan — entri baru dijeda' },
      eval_failed: { ko: '가격 데이터 문제로 평가 불가 — 진입 정지', en: 'Equity evaluation failing on stale prices — entries paused', ja: '価格データ問題で評価不可 — 停止', th: 'ประเมินไม่ได้ — พัก', vi: 'Không đánh giá được — tạm dừng', id: 'Evaluasi ekuitas gagal karena harga usang — entri dijeda' },
      user_stop: { ko: '사용자 정지', en: 'Stopped by you', ja: 'ユーザー停止', th: 'หยุดโดยผู้ใช้', vi: 'Bạn đã dừng', id: 'Dihentikan oleh Anda' },
      fleet_stop_all: { ko: '전체 정지 — 이 N종목 전체를 정지했습니다', en: 'Stop all — this sleeve was stopped as a whole', ja: '全体停止 — このスリーブ全体を停止しました', th: 'หยุดทั้งหมด — หยุดสลีฟนี้ทั้งชุด', vi: 'Dừng tất cả — đã dừng toàn bộ sleeve này', id: 'Hentikan semua — sleeve ini dihentikan secara keseluruhan' },
      fleet_profit_target: { ko: '플릿 목표 수익 달성 — 전체 청산됨', en: 'Fleet profit target reached — everything closed', ja: 'フリート利益目標達成 — 全決済', th: 'ฟลีทถึงเป้าหมายกำไร — ปิดทั้งหมด', vi: 'Fleet đạt mục tiêu lợi nhuận — đã đóng tất cả', id: 'Target profit fleet tercapai — semuanya ditutup' },
      user_master_remove: { ko: '마스터 스위치로 제거됨', en: 'Removed via master switch', ja: 'マスタースイッチで削除', th: 'ลบผ่านสวิตช์หลัก', vi: 'Đã gỡ qua công tắc chính', id: 'Dihapus lewat sakelar utama' },
      agent_deleted: { ko: '에이전트가 삭제되어 정지됨', en: 'Stopped — agent deleted', ja: 'エージェント削除により停止', th: 'หยุด — เอเจนต์ถูกลบ', vi: 'Dừng — agent đã xóa', id: 'Dihentikan — agen dihapus' },
      adapt_retired: { ko: '연속 손실로 은퇴됨', en: 'Retired after consecutive losses', ja: '連続損失により引退', th: 'ปลดหลังขาดทุนต่อเนื่อง', vi: 'Nghỉ sau chuỗi thua lỗ', id: 'Ditarik setelah kerugian beruntun' },
    }
    return map[reason] ? tr(language, map[reason]) : reason
  }

  const authHeaders: any = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  const [ent, setEnt] = useState<Entitlements | null>(null)
  const [fleet, setFleet] = useState<Fleet | null>(null)
  const [index, setIndex] = useState<FleetIndex | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [equity, setEquity] = useState<number | null>(null)
  const [n, setN] = useState(3)
  const [budget, setBudget] = useState<number>(0)
  // Empty = every market, which is what the API means by a null market_scope.
  const [mkts, setMkts] = useState<string[]>([])
  const [sizeN, setSizeN] = useState<number>(0)       // 0 = untouched; use fleet.n_runs
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Monitor box tabs: cards (실시간 모니터) | trading activity (거래 활동)
  const [monTab, setMonTab] = useState<'monitor' | 'activity'>('monitor')
  // Finished members stay attributed to the fleet forever (list_members
  // returns every run ever rotated through it, and the index NEEDS them for
  // P&L), but a rotating sleeve accumulates stopped cards without bound —
  // fleet 22 showed 6 정지됨 cards around its 2 live ones. Hide them by
  // default behind the same toggle the TRADING grid uses (PR #42).
  const [showFinished, setShowFinished] = useState(false)
  // (?) next to the fleet index — owner report: members read 99.93 as a
  // price or a balance. The badge says INDEX; this opens the full guide.
  const [showIndexGuide, setShowIndexGuide] = useState(false)
  // 플릿 수정 popup (owner ask 2026-08-08): the goal + slots rows moved out of
  // the always-visible monitor into a popup behind one button.
  const [showEdit, setShowEdit] = useState(false)
  const [trades, setTrades] = useState<any[]>([])
  // First /fleets read finished — until then the top box cannot tell a live
  // fleet from none, so it renders nothing rather than flash the form.
  const [loaded, setLoaded] = useState(false)
  const [actMkt, setActMkt] = useState('all')

  const load = useCallback(async () => {
    try {
      const fl = await fetch(`${API_BASE}/fleets`, { headers: authHeaders }).then(r => r.json())
      const active = (fl.fleets || []).find((f: Fleet) => f.status !== 'stopped') || (fl.fleets || [])[0] || null
      if (active) {
        const detail = await fetch(`${API_BASE}/fleets/${active.id}`, { headers: authHeaders }).then(r => r.json())
        setFleet(detail.fleet); setMembers(detail.members || [])
        setEquity(detail.equity && detail.equity.ok ? detail.equity.equity : null)
        setIndex(detail.index || null)
      } else { setFleet(null); setMembers([]); setIndex(null) }
      setLoaded(true)
    } catch { /* transient */ }
  }, [token])

  const loadEnt = useCallback(() => {
    fetch(`${API_BASE}/entitlements/me`, { headers: authHeaders })
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() })
      .then((e: Entitlements) => { setEnt(e); setBudget(b => b || e.default_budget_usd || 1000) })
      .catch(() => setEnt(null))
  }, [token])

  useEffect(() => {
    loadEnt()
    load()
  }, [token])

  // The top box hides its create form until the plan is known, so a failed
  // entitlements read must not hide it for good — retry every 20 s.
  useEffect(() => {
    if (!combined || ent) return
    const id = setInterval(loadEnt, 20000)
    return () => clearInterval(id)
  }, [combined, ent, loadEnt])

  useEffect(() => {
    if (!fleet || fleet.status === 'stopped') {
      // Discovery poll (monitor box only): the always-visible panel mounts
      // before any fleet exists, so without this a fleet launched from the
      // create modal stays invisible until a full page reload.
      if (!monitorOnly && !combined) return
      const id = setInterval(load, 20000)
      return () => clearInterval(id)
    }
    const fast = fleet.status === 'researching' || fleet.status === 'building'
    // 5s while live — member P&L/status changes drive the card blink, so the
    // poll has to be tight enough for the box to visibly breathe.
    const id = setInterval(load, fast ? 2000 : 5000)
    return () => clearInterval(id)
  }, [fleet?.status, load, monitorOnly, combined])

  // 거래 활동 tab: the account's recent legs across every market (side, symbol,
  // qty, price, P&L, date). Monitor box only; light 15s poll.
  useEffect(() => {
    if (!(monitorOnly || combined) || !token) return
    let dead = false
    const loadTrades = async () => {
      try {
        const r = await fetch(`${API_BASE}/positions/trades?limit=50`, { headers: authHeaders }).then(r => r.json())
        if (!dead) setTrades(r.trades || [])
      } catch { /* transient */ }
    }
    loadTrades()
    const iv = setInterval(loadTrades, 15000)
    return () => { dead = true; clearInterval(iv) }
  }, [monitorOnly, combined, token])

  // Member-card liveness: the panel is poll-driven, so "an event" here is a
  // change in a member's polled snapshot (status / P&L / pause reason) — blink
  // that card for 2s so activity is visible without opening the drawer.
  const [memberFlash, setMemberFlash] = useState<Record<number, number | undefined>>({})
  const memberSig = useRef<Record<number, string>>({})
  const memberTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})
  useEffect(() => {
    members.forEach(m => {
      const sig = `${m.status}|${m.total_pnl_usd ?? m.realized_pnl_usd ?? ''}|${m.paused_reason ?? ''}`
      const prev = memberSig.current[m.run_id]
      memberSig.current[m.run_id] = sig
      if (prev !== undefined && prev !== sig) {
        setMemberFlash(f => ({ ...f, [m.run_id]: (f[m.run_id] || 0) + 1 }))
        clearTimeout(memberTimers.current[m.run_id])
        memberTimers.current[m.run_id] = setTimeout(
          () => setMemberFlash(f => ({ ...f, [m.run_id]: undefined })), 2000)
      }
    })
  }, [members])
  useEffect(() => () => {
    Object.values(memberTimers.current).forEach(clearTimeout)
  }, [])

  const finishedCount = members.filter(m => m.status === 'stopped').length
  const visibleMembers = showFinished ? members : members.filter(m => m.status !== 'stopped')

  const launch = async () => {
    setBusy(true); setError(null)
    try {
      const r = await fetch(`${API_BASE}/fleets`, {
        method: 'POST', headers: authHeaders,
        // risk_appetite / archetype / leverage are intentionally absent —
        // the Desk decides them (owner 2026-08-31); the server applies its
        // desk-managed defaults.
        body: JSON.stringify({ n_runs: n, total_budget_usd: budget, markets: mkts.length ? mkts : null, idempotency_key: `ui-${Date.now()}` }),
      })
      const body = await r.json()
      if (!r.ok) { setError(body.detail || 'error'); return }
      const s = await fetch(`${API_BASE}/fleets/${body.id}/start`, { method: 'POST', headers: authHeaders })
      if (!s.ok) { setError((await s.json()).detail || 'error'); return }
      await load()
    } finally { setBusy(false) }
  }


  const saveSize = async (n: number) => {
    if (!fleet || !n || n === fleet.n_runs) return
    // Confirm-with-recommendation (owner ask 2026-08-08): the change only
    // proceeds if the user agrees after seeing what it means for per-slot
    // budget, the drain/fill semantics, and the AI's recommended count.
    const perSlot = fleet.total_budget_usd / n
    const rec = fleet.recommended_max_n_runs
    const lines: string[] = [
      tr(language, { ko: `슬롯 수를 ${fleet.n_runs}개 → ${n}개로 변경합니다.`, en: `Change slots from ${fleet.n_runs} to ${n}.`, ja: `スロット数を ${fleet.n_runs} → ${n} に変更します。`, th: `เปลี่ยนสล็อตจาก ${fleet.n_runs} เป็น ${n}`, vi: `Đổi số slot từ ${fleet.n_runs} thành ${n}.`, id: `Ubah slot dari ${fleet.n_runs} menjadi ${n}.` }),
      tr(language, { ko: `슬롯당 예산은 약 $${perSlot.toFixed(0)}가 됩니다.`, en: `Each slot's budget becomes ≈ $${perSlot.toFixed(0)}.`, ja: `スロットあたりの予算は約 $${perSlot.toFixed(0)} になります。`, th: `งบต่อสล็อตจะอยู่ที่ ≈ $${perSlot.toFixed(0)}`, vi: `Ngân sách mỗi slot còn ≈ $${perSlot.toFixed(0)}.`, id: `Anggaran per slot menjadi ≈ $${perSlot.toFixed(0)}.` }),
      n > fleet.n_runs
        ? tr(language, { ko: '늘어난 슬롯은 예산 여유가 생길 때에만 채워집니다 (즉시 늘어나지 않을 수 있음).', en: 'New slots fill only as budget headroom frees up (may not appear immediately).', ja: '増えたスロットは予算に余裕ができたときにのみ埋まります（すぐには増えない場合があります）。', th: 'สล็อตใหม่จะถูกเติมเมื่องบมีที่ว่างเท่านั้น (อาจไม่ปรากฏทันที)', vi: 'Slot mới chỉ được lấp khi ngân sách có dư (có thể không xuất hiện ngay).', id: 'Slot baru terisi hanya saat anggaran memiliki ruang (mungkin tidak langsung muncul).' })
        : tr(language, { ko: '줄어드는 슬롯은 포지션이 스스로 종료될 때에만 회수됩니다 — 보유 포지션을 강제 청산하지 않습니다.', en: 'Removed slots retire only when their positions finish on their own — nothing is force-closed.', ja: '減らしたスロットはポジションが自然に終了したときにのみ回収されます — 強制清算はしません。', th: 'สล็อตที่ลดจะถูกเก็บคืนเมื่อสถานะจบเองเท่านั้น — ไม่มีการบังคับปิด', vi: 'Slot bị giảm chỉ được thu hồi khi vị thế tự kết thúc — không ép đóng lệnh.', id: 'Slot yang dikurangi ditarik hanya saat posisinya selesai sendiri — tidak ada penutupan paksa.' }),
    ]
    if (rec) {
      lines.push(tr(language, { ko: `🤖 AI 권장: 이 예산($${fleet.total_budget_usd.toFixed(0)})에는 최대 ${rec}개 (슬롯당 $100 이상 유지).`, en: `🤖 AI recommendation: at most ${rec} slots for this budget ($${fleet.total_budget_usd.toFixed(0)}) — keep each slot at $100+.`, ja: `🤖 AI推奨: この予算（$${fleet.total_budget_usd.toFixed(0)}）では最大 ${rec} スロット（各スロット $100 以上を維持）。`, th: `🤖 คำแนะนำ AI: งบนี้ ($${fleet.total_budget_usd.toFixed(0)}) ไม่ควรเกิน ${rec} สล็อต (รักษาสล็อตละ $100 ขึ้นไป)`, vi: `🤖 AI khuyến nghị: tối đa ${rec} slot cho ngân sách này ($${fleet.total_budget_usd.toFixed(0)}) — giữ mỗi slot từ $100 trở lên.`, id: `🤖 Rekomendasi AI: maksimal ${rec} slot untuk anggaran ini ($${fleet.total_budget_usd.toFixed(0)}) — jaga tiap slot $100+.` }))
      if (n > rec) {
        lines.push(tr(language, { ko: `⚠️ 권장 개수를 초과합니다. 슬롯이 작을수록 수수료 허들(왕복 비용)을 넘기 어려워 수익성이 떨어집니다.`, en: `⚠️ This exceeds the recommendation. Smaller slots struggle to clear the round-trip fee hurdle, hurting profitability.`, ja: `⚠️ 推奨数を超えています。スロットが小さいほど往復手数料のハードルを越えにくく、収益性が下がります。`, th: `⚠️ เกินจำนวนที่แนะนำ สล็อตยิ่งเล็กยิ่งข้ามต้นทุนค่าธรรมเนียมไป-กลับได้ยาก ทำให้กำไรลดลง`, vi: `⚠️ Vượt mức khuyến nghị. Slot càng nhỏ càng khó vượt rào phí khứ hồi, làm giảm lợi nhuận.`, id: `⚠️ Melebihi rekomendasi. Slot yang lebih kecil sulit melewati rintangan biaya pulang-pergi, mengurangi profitabilitas.` }))
      }
    }
    lines.push(tr(language, { ko: '계속할까요?', en: 'Proceed?', ja: '続行しますか？', th: 'ดำเนินการต่อหรือไม่?', vi: 'Tiếp tục?', id: 'Lanjutkan?' }))
    if (!window.confirm(lines.join('\n\n'))) return
    setBusy(true); setError(null)
    try {
      const r = await fetch(`${API_BASE}/fleets/${fleet.id}/size`, {
        method: 'PUT', headers: authHeaders,
        body: JSON.stringify({ n_runs: n }),
      })
      if (!r.ok) { setError((await r.json()).detail || 'error'); return }
      await load()
    } finally { setBusy(false) }
  }

  // Tracks WHICH lifecycle button is in flight so the spinner lands on the
  // pressed one. act() previously never surfaced failures either — a refused
  // stop looked exactly like a dead button.
  const [actingKey, setActingKey] = useState<string | null>(null)
  const act = async (path: string) => {
    if (!fleet) return
    setBusy(true); setError(null); setActingKey(path)
    try {
      const r = await fetch(`${API_BASE}/fleets/${fleet.id}/${path}`, { method: 'POST', headers: authHeaders, body: '{}' })
      if (!r.ok) { setError((await r.json().catch(() => ({}))).detail || `error (HTTP ${r.status})`); return }
      await load()
    } catch { setError('network error') }
    finally { setBusy(false); setActingKey(null) }
  }
  const spin = (key: string) => (busy && actingKey === key ? '⏳ ' : '')

  const chip = (active: boolean): any => ({
    padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontSize: 13,
    border: active ? '1px solid var(--accent-primary,#c26a45)' : '1px solid var(--border-color,rgba(0,0,0,0.15))',
    background: active ? 'rgba(194,106,69,0.12)' : 'transparent',
    color: active ? 'var(--accent-primary,#c26a45)' : 'inherit',
  })

  // `mon` = render as the live monitor: always for monitorOnly, and for the
  // combined top box once a fleet is live.
  const live = !!fleet && fleet.status !== 'stopped'
  const mon = monitorOnly || (combined && live)
  const card: any = { background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 16,
    ...(monitorOnly || combined ? { marginBottom: 18 } : {}) }

  // The monitor box has nothing to say until a fleet is live; the creation
  // form (and the plan-gate notice) stay in the create modal only.
  if (monitorOnly && (!fleet || fleet.status === 'stopped')) return null
  // Top-of-page box: a live fleet always renders (monitor + stop, whatever
  // the plan). With no live fleet it shows the create form only once the
  // plan is known AND allows fleets — never a form a plan cannot launch,
  // never an upsell card as the page's first element (review 2026-11-20).
  if (combined && !loaded) return null
  if (combined && !live && (!ent || ent.max_fleet_size <= 0)) return null
  if (combined && !live && blockCreate) return null

  if (!combined && ent && ent.max_fleet_size <= 0) {
    if (monitorOnly) return null
    return <div style={card}><div style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>🚀 {T.needPlan}</div></div>
  }

  // The AI feed, at the page's slot when one is given (its own card there),
  // else inline exactly as before.
  const feedAt = (feed: ReactElement) => aiFeedHost === undefined ? feed
    : aiFeedHost ? createPortal(<div style={{ ...card, marginTop: 18 }}>{feed}</div>, aiFeedHost) : null

  const warned = !!(fleet && fleet.warn_latched_at && !fleet.warn_acked_at)
  const pnl = fleet && equity !== null ? equity - fleet.total_budget_usd : null

  return (
    <div style={card}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>🚀 {mon ? T.monitorTitle : T.title}</div>
      {!mon && (
        <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 14 }}>{T.desc}</div>
      )}

      {!fleet || fleet.status === 'stopped' ? (
        <>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 10 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              {T.nRuns} {ent ? `(max ${ent.max_fleet_size})` : ''}
              <input type="number" min={1} max={ent?.max_fleet_size || 25} value={n}
                onChange={e => setN(Number(e.target.value))}
                style={{ padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', width: 120, background: 'transparent', color: 'inherit' }} />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              {T.budget}
              <input type="number" min={50} value={budget}
                onChange={e => setBudget(Number(e.target.value))}
                style={{ padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', width: 160, background: 'transparent', color: 'inherit' }} />
            </label>
            <button onClick={launch} disabled={busy || n < 1}
              style={{ padding: '11px 24px', borderRadius: 9, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: busy ? 0.6 : 1 }}>
              {T.launch}
            </button>
            {error && <span style={{ color: '#f0663f', fontSize: 12.5 }}>⚠️ {error}</span>}
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12.5, margin: '0 0 6px', fontWeight: 600 }}>
              {tr(language, { ko: '시장', en: 'Markets', ja: '市場', th: 'ตลาด', vi: 'Thị trường', id: 'Pasar' })}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button style={chip(mkts.length === 0)} onClick={() => setMkts([])}>
                {tr(language, { ko: '전체', en: 'All', ja: '全て', th: 'ทั้งหมด', vi: 'Tất cả', id: 'Semua' })}
              </button>
              {FLEET_MARKETS.map(m => (
                <button key={m} style={chip(mkts.includes(m))}
                  onClick={() => setMkts(cur => cur.includes(m) ? cur.filter(x => x !== m) : [...cur, m])}>
                  {marketLabel(m, language)}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 6, lineHeight: 1.45 }}>
              {mkts.length === 0
                ? tr(language, { ko: '전체 — AI가 지금 열려 있는 시장 중에서 고릅니다.', en: 'All — the AI picks from whichever markets are open right now.', ja: '全市場 — AIが現在開いている市場から選びます。', th: 'ทั้งหมด — AI เลือกจากตลาดที่เปิดอยู่', vi: 'Tất cả — AI chọn trong các thị trường đang mở.', id: 'Semua — AI memilih dari pasar yang sedang buka.' })
                : tr(language, { ko: '선택한 시장에서만 종목을 고릅니다. 모두 닫혀 있으면 열릴 때까지 기다립니다.', en: 'Symbols are picked only from the markets you chose. If they are all shut, the fleet waits for a session.', ja: '選択した市場からのみ選びます。全て閉場なら開くまで待機します。', th: 'เลือกเฉพาะตลาดที่คุณเลือก หากปิดทั้งหมดจะรอจนเปิด', vi: 'Chỉ chọn trong các thị trường bạn đã chọn. Nếu đều đóng cửa, hạm đội sẽ chờ.', id: 'Simbol hanya dipilih dari pasar yang Anda pilih. Jika semuanya tutup, armada menunggu sesi berikutnya.' })}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 12, lineHeight: 1.45 }}>
              🤖 {T.deskDecides}
            </div>
          </div>
          {fleet && fleet.status === 'stopped' && fleet.status_reason && (
            <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>
              ℹ️ {reasonLabel(fleet.status_reason)}
            </div>
          )}
          {combined && fleet && fleet.status === 'stopped' && fleet.stopped_at
            && Date.now() - Date.parse(fleet.stopped_at) < 24 * 3600 * 1000 && (
            // Why the last fleet ended (e.g. 20 empty research tries) — the
            // same 30-minute feed, so the reason is visible, not guessed. It
            // goes where the live feed goes (page end) so it has one place.
            feedAt(
            <div style={{ marginTop: 12 }}>
              <FleetAiFeed token={token} fleetId={fleet.id} language={language} reasonLabel={reasonLabel} live={false} />
            </div>)
          )}
        </>
      ) : (
        <>
          {!!fleet.held_by_master && (
            <div style={{ fontSize: 12.5, marginBottom: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(240,102,63,0.1)' }}>{T.holdBanner}</div>
          )}
          {combined && (
            // Owner ask 2026-11-20: what the user ordered is the base plan the
            // AI trades by — state it on the box the AI reports into.
            <div style={{ fontSize: 12.5, marginBottom: 10, padding: '8px 12px', borderRadius: 8,
              border: '1px dashed var(--border-color,rgba(0,0,0,0.18))' }}>
              📋 <b>{T.basePlan}</b>: {fleet.n_runs} TRADING · ${Number(fleet.total_budget_usd).toLocaleString()} · {T.basePlanMarkets} {
                fleet.market_scope && fleet.market_scope.length
                  ? fleet.market_scope.map(m => marketLabel(m, language)).join(', ')
                  : tr(language, { ko: '전체', en: 'All', ja: '全て', th: 'ทั้งหมด', vi: 'Tất cả', id: 'Semua' })}
              <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginTop: 3 }}>{T.basePlanHint}</div>
            </div>
          )}
          {combined && feedAt(
            <FleetAiFeed token={token} fleetId={fleet.id} language={language} reasonLabel={reasonLabel} live />
          )}
          {/* This sleeve's own scoreboard, rebased to 100 at launch. The
              account total above answers "am I up?"; only this answers "is
              THIS fleet working?" — on a six-figure account a $10k sleeve's
              result is otherwise invisible. Budget-independent, so two fleets
              of different size are directly comparable. */}
          {index && (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap',
              marginBottom: 12, padding: '12px 16px', borderRadius: 12,
              border: '1px solid var(--border-color,rgba(0,0,0,0.1))',
              background: 'var(--bg-card,rgba(0,0,0,0.02))' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)' }}>
                🎯 {T.indexLabel}
              </span>
              <span style={{ fontSize: 30, fontWeight: 800, fontVariantNumeric: 'tabular-nums',
                color: index.value >= index.base ? '#2e9e6b' : '#f0663f' }}>
                {index.value.toFixed(2)}
              </span>
              {/* Owner report: members read this as a price or balance — say
                  INDEX right on the number, and (?) opens the full guide. */}
              <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '.08em',
                padding: '2px 7px', borderRadius: 5,
                border: '1px solid var(--border-color,rgba(0,0,0,0.18))',
                color: 'var(--text-secondary,#8a8073)' }}>
                INDEX
              </span>
              <GuideBadge onClick={() => setShowIndexGuide(true)} title={T.idxGuideOpen}
                style={{ width: 20, height: 20, borderRadius: 10, padding: 0, fontSize: 12,
                  fontWeight: 700, lineHeight: 1, cursor: 'pointer',
                  border: '1px solid var(--border-color,rgba(0,0,0,0.2))',
                  background: 'transparent', color: 'var(--text-secondary,#8a8073)' }} />
              <span style={{ fontSize: 14, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                color: index.pnl_pct >= 0 ? '#2e9e6b' : '#f0663f' }}>
                {index.pnl_pct >= 0 ? '+' : ''}{index.pnl_pct.toFixed(2)}%
                <span style={{ marginLeft: 6, fontWeight: 600 }}>
                  ({index.pnl_usd >= 0 ? '+' : ''}${index.pnl_usd.toFixed(2)})
                </span>
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)',
                fontVariantNumeric: 'tabular-nums' }}>
                {T.indexBase} {index.base.toFixed(0)} · {T.indexBudget} ${index.budget_usd.toFixed(0)}
                {index.since ? ` · ${index.since.slice(0, 10)}` : ''}
              </span>
            </div>
          )}
          {/* Owner ask 2026-08-08: the status line reads as reference data,
              not an action — right-aligned so the left edge stays for the
              index and controls. */}
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'center',
            justifyContent: 'flex-end', marginBottom: 10 }}>
            <span style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 12.5 }}>
              {fleet.status}{fleet.status_reason ? ` · ${reasonLabel(fleet.status_reason)}` : ''}
            </span>
            {equity !== null && (
              <span style={{ fontSize: 13 }}>
                {T.equity}: ${equity.toFixed(2)}
                {pnl !== null && (
                  <b style={{ color: pnl >= 0 ? '#2e9e6b' : '#f0663f', marginLeft: 6 }}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                  </b>
                )}
              </span>
            )}
            <span style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)' }}>
              −{Math.round(fleet.warn_loss_frac * 100)}% ⚠︎ / −{Math.round(fleet.stop_loss_frac * 100)}% ⏹
            </span>
            <HelpTip text={(() => {
              const warn = Math.round(fleet.warn_loss_frac * 100)
              const stop = Math.round(fleet.stop_loss_frac * 100)
              return tr(language, {
                ko: `플릿의 현재 상태 표시줄입니다. ACTIVE는 운용 중이라는 뜻이고, 「보충 대기 중 (k/N)」은 목표 N개 중 k개가 준비되어 나머지를 AI가 채우는 중이라는 뜻입니다. 평가 자산은 현재 시세로 계산한 플릿 가치이며, 옆의 숫자는 예산 대비 손익입니다. 손실이 −${warn}%에 이르면 신규 진입이 정지되고(⚠︎), −${stop}%에 이르면 전체가 자동 청산됩니다(⏹).`,
                en: `The fleet's current status bar. ACTIVE means it is running; "Replenishing (k/N)" means k of the target N TRADINGs are in place and the AI is building the rest. Marked equity is the fleet's value at current prices; the figure next to it is P&L versus budget. If the loss reaches −${warn}% new entries pause (⚠︎); at −${stop}% everything is closed automatically (⏹).`,
                ja: `フリートの現在の状態バーです。ACTIVE は運用中、「補充待ち (k/N)」は目標 N 件のうち k 件が稼働し残りをAIが構築中という意味です。評価資産は現在価格で計算したフリートの価値で、隣の数字は予算比の損益です。損失が −${warn}% に達すると新規エントリーが停止し(⚠︎)、−${stop}% で全体が自動清算されます(⏹)。`,
                th: `แถบสถานะปัจจุบันของฟลีต ACTIVE คือกำลังทำงาน "กำลังเติม (k/N)" คือมี k จากเป้า N TRADING แล้วและ AI กำลังสร้างที่เหลือ มูลค่าตามราคาตลาดคือมูลค่าฟลีตที่ราคาปัจจุบัน ตัวเลขข้างๆ คือกำไรขาดทุนเทียบกับงบ ถ้าขาดทุนถึง −${warn}% จะหยุดการเข้าใหม่ (⚠︎) และถึง −${stop}% จะปิดทั้งหมดอัตโนมัติ (⏹)`,
                vi: `Thanh trạng thái hiện tại của fleet. ACTIVE nghĩa là đang chạy; "Đang bổ sung (k/N)" nghĩa là k trên N TRADING mục tiêu đã sẵn sàng và AI đang tạo phần còn lại. Giá trị theo thị trường là giá trị fleet theo giá hiện tại; con số bên cạnh là lãi/lỗ so với ngân sách. Nếu lỗ chạm −${warn}%, lệnh mới bị tạm dừng (⚠︎); chạm −${stop}%, tất cả được đóng tự động (⏹).`,
                id: `Bilah status fleet saat ini. ACTIVE berarti sedang berjalan; "Menunggu pemenuhan (k/N)" berarti k dari target N TRADING sudah terpasang dan AI sedang membangun sisanya. Ekuitas berbasis harga pasar adalah nilai fleet pada harga saat ini; angka di sebelahnya adalah laba rugi terhadap anggaran. Jika kerugian mencapai −${warn}% entri baru dijeda (⚠︎); pada −${stop}% semuanya ditutup otomatis (⏹).`,
              })
            })()} />
          </div>
          {warned && (
            <div style={{ marginBottom: 10, padding: '10px 12px', borderRadius: 8, background: 'rgba(240,102,63,0.12)', fontSize: 12.5 }}>
              ⚠️ {reasonLabel('drawdown_warning')}
              <button onClick={() => act('resume-warning')} disabled={busy}
                style={{ marginLeft: 12, padding: '5px 12px', borderRadius: 7, border: '1px solid #f0663f', background: 'transparent', color: '#f0663f', fontSize: 12, cursor: 'pointer', opacity: busy ? 0.55 : 1 }}>
                {spin('resume-warning')}{T.resumeWarning}
              </button>
            </div>
          )}
          {members.length === 0 && (fleet.status === 'researching' || fleet.status === 'building') && (
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginBottom: 12 }}>
              ⏳ {T.buildingHint}
            </div>
          )}
          {mon && (
            <div style={{ display: 'flex', gap: 20, borderBottom: '1px solid var(--border-color,rgba(0,0,0,0.12))', marginBottom: 14 }}>
              {([['monitor', T.tabMonitor], ['activity', T.tabActivity]] as const).map(([k, lbl]) => (
                <button key={k} onClick={() => setMonTab(k)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '6px 2px 10px', fontSize: 13, fontWeight: 700, marginBottom: -1,
                    color: monTab === k ? 'var(--text-primary,inherit)' : 'var(--text-secondary,#8a8073)',
                    borderBottom: monTab === k ? '2px solid var(--accent-primary,#c26a45)' : '2px solid transparent' }}>
                  {lbl}
                </button>
              ))}
              <HelpTip style={{ alignSelf: 'center', marginBottom: 4 }} text={tr(language, {
                ko: '「실시간 모니터」는 플릿의 각 TRADING을 카드로 보여줍니다 — 카드를 누르면 차트와 이벤트 로그가 있는 상세 화면이 열립니다.\n「거래 활동」은 계정의 최근 체결 내역(매수/매도·수량·가격·손익)을 표로 보여줍니다.',
                en: '"Live monitor" shows each TRADING in the fleet as a card — click one to open its detail view with chart and event log.\n"Trading activity" lists the account\'s recent fills (side, amount, price, P&L) in a table.',
                ja: '「ライブモニター」はフリートの各 TRADING をカードで表示します — カードを押すとチャートとイベントログのある詳細画面が開きます。\n「取引アクティビティ」はアカウントの最近の約定（売買・数量・価格・損益）を表で表示します。',
                th: '"มอนิเตอร์สด" แสดงแต่ละ TRADING ในฟลีตเป็นการ์ด — กดการ์ดเพื่อเปิดหน้ารายละเอียดพร้อมกราฟและบันทึกเหตุการณ์\n"กิจกรรมเทรด" แสดงรายการซื้อขายล่าสุดของบัญชี (ฝั่งซื้อ/ขาย จำนวน ราคา กำไรขาดทุน) เป็นตาราง',
                vi: '"Theo dõi trực tiếp" hiển thị mỗi TRADING trong fleet dưới dạng thẻ — nhấp vào một thẻ để mở màn hình chi tiết với biểu đồ và nhật ký sự kiện.\n"Hoạt động giao dịch" liệt kê các lệnh khớp gần đây của tài khoản (mua/bán, số lượng, giá, lãi/lỗ) trong một bảng.',
                id: '"Monitor langsung" menampilkan setiap TRADING dalam fleet sebagai kartu — klik salah satu untuk membuka tampilan detailnya dengan grafik dan catatan peristiwa.\n"Aktivitas trading" menampilkan transaksi terbaru akun (arah, jumlah, harga, laba rugi) dalam sebuah tabel.',
              })} />
            </div>
          )}
          {(!mon || monTab === 'monitor') ? (
          <>
          {visibleMembers.length > 0 && onSelectRun && (
            <div style={{ fontSize: 11.5, color: 'var(--text-muted,#a89f92)', marginBottom: 6 }}>
              💡 {T.clickHint}
            </div>
          )}
          {finishedCount > 0 && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
              <button onClick={() => setShowFinished(v => !v)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>
                {showFinished ? '▾' : '▸'} {showFinished ? T.hideFinished : T.showFinished} ({finishedCount})
              </button>
            </div>
          )}
          <style>{`
            @keyframes sp-run-flash {
              0% { box-shadow: 0 0 0 2.5px var(--sp-flash-color), 0 0 18px 2px var(--sp-flash-color); }
              70% { box-shadow: 0 0 0 2px var(--sp-flash-color), 0 0 8px 0 transparent; }
              100% { box-shadow: 0 0 0 0 transparent; }
            }
            @keyframes sp-live-pulse { 0%, 100% { opacity: 1 } 50% { opacity: .25 } }
          `}</style>
          {mon ? (
            // Merged with the runs grid below (owner: "the same trading showed
            // twice") — the monitor box keeps a one-line chip strip for
            // at-a-glance fleet state; the full per-run cards live ONLY in the
            // grid, grouped under the 🚀 fleet divider.
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {visibleMembers.map(m => {
                const total = m.total_pnl_usd ?? m.realized_pnl_usd
                const t = total != null ? Number(total) : null
                return (
                  <button key={m.run_id}
                    onClick={onSelectRun ? () => onSelectRun(m.run_id) : undefined}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 11px',
                      borderRadius: 16, border: '1px solid var(--border-color,rgba(0,0,0,0.12))',
                      background: 'transparent', color: 'inherit', fontSize: 12.5,
                      cursor: onSelectRun ? 'pointer' : undefined, position: 'relative' }}>
                    {memberFlash[m.run_id] != null && (
                      <span key={memberFlash[m.run_id]} style={{ position: 'absolute', inset: 0, borderRadius: 16,
                        pointerEvents: 'none', ['--sp-flash-color' as any]: 'rgba(12,163,12,0.85)',
                        animation: 'sp-run-flash 2s ease-out forwards' }} />
                    )}
                    {m.status === 'running' && (
                      <span style={{ width: 6, height: 6, borderRadius: 6, background: '#0ca30c',
                        display: 'inline-block', animation: 'sp-live-pulse 1.6s ease-in-out infinite' }} />
                    )}
                    <b>{m.symbol}</b>
                    {m.thesis?.direction === 'short' && (
                      <span style={{ fontSize: 10.5, color: 'var(--text-muted,#a89f92)' }}>short</span>
                    )}
                    {t != null && (
                      <span style={{ fontVariantNumeric: 'tabular-nums', color: t >= 0 ? '#2e9e6b' : '#f0663f' }}>
                        {t >= 0 ? '+' : ''}{t.toFixed(2)}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 8, marginBottom: 12 }}>
            {visibleMembers.map(m => (
              <div key={m.run_id}
                onClick={onSelectRun ? () => onSelectRun(m.run_id) : undefined}
                style={{ border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 9, padding: '9px 11px', fontSize: 12.5,
                  cursor: onSelectRun ? 'pointer' : undefined, position: 'relative' }}>
                {memberFlash[m.run_id] != null && (
                  <div key={memberFlash[m.run_id]} style={{ position: 'absolute', inset: 0, borderRadius: 9,
                    pointerEvents: 'none', ['--sp-flash-color' as any]: 'rgba(12,163,12,0.85)',
                    animation: 'sp-run-flash 2s ease-out forwards' }} />
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <b>{m.symbol}</b>
                  <span style={{ color: 'var(--text-muted,#a89f92)' }}>{m.market}{m.thesis?.direction === 'short' ? ' · short' : ''}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5,
                    color: m.status === 'running' ? '#0ca30c' : m.status === 'paused' ? '#7a68d8' : 'inherit' }}>
                    {m.status === 'running' && (
                      <span style={{ width: 6, height: 6, borderRadius: 6, background: '#0ca30c',
                        display: 'inline-block', animation: 'sp-live-pulse 1.6s ease-in-out infinite' }} />
                    )}
                    {statusLabel(m.status, language)}{m.paused_reason ? ` (${m.paused_reason})` : ''}
                  </span>
                  {(m.total_pnl_usd ?? m.realized_pnl_usd) != null && (() => {
                    // Plan 15 O2: show the marked TOTAL (realized + unrealized) —
                    // realized alone is just the fee ledger until the first
                    // close and painted every young winner red.
                    const total = Number(m.total_pnl_usd ?? m.realized_pnl_usd)
                    const tip = `${tr(language, { ko: '평가 손익', en: 'marked P&L', ja: '評価損益', th: 'P&L ตามราคาตลาด', vi: 'P&L theo giá', id: 'laba rugi berbasis harga pasar' })} ${total >= 0 ? '+' : ''}${total.toFixed(2)}` +
                      (m.realized_pnl_usd != null ? ` · ${tr(language, { ko: '실현', en: 'realized', ja: '実現', th: 'รับรู้แล้ว', vi: 'đã chốt', id: 'direalisasi' })} ${Number(m.realized_pnl_usd) >= 0 ? '+' : ''}${Number(m.realized_pnl_usd).toFixed(2)}` : '')
                    return (
                      <span title={tip} style={{ color: total >= 0 ? '#2e9e6b' : '#f0663f' }}>
                        {total >= 0 ? '+' : ''}{total.toFixed(2)}
                      </span>
                    )
                  })()}
                </div>
                {m.run_budget_usd != null && (
                  <div style={{ marginTop: 3, fontSize: 11.5, color: 'var(--text-muted,#a89f92)' }}>
                    {T.memberBudget}: ${Number(m.run_budget_usd).toFixed(0)}
                  </div>
                )}
                {m.thesis?.rationale && (
                  <div style={{ marginTop: 4, fontSize: 11.5, color: 'var(--text-muted,#a89f92)', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as any }}>
                    {m.thesis.rationale}
                  </div>
                )}
              </div>
            ))}
          </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            {fleet.status === 'active' && <button style={{ ...chip(false), opacity: busy ? 0.55 : 1 }} onClick={() => act('pause')} disabled={busy}>{spin('pause')}{T.pause}</button>}
            {fleet.status === 'paused' && <button style={{ ...chip(false), opacity: busy ? 0.55 : 1 }} onClick={() => act('resume')} disabled={busy}>{spin('resume')}{T.resume}</button>}
            <button onClick={() => act('stop')} disabled={busy}
              style={{ padding: '8px 18px', borderRadius: 8, border: 'none', background: '#c0392b', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', opacity: busy ? 0.55 : 1 }}>
              {spin('stop')}{T.stopAll}
            </button>
            <button style={chip(false)} onClick={() => setShowEdit(true)}>{T.editFleet}</button>
            <HelpTip style={{ alignSelf: 'center' }} text={tr(language, {
              ko: '「일시정지」는 신규 진입만 멈춥니다 — 보유 포지션과 손절/익절 보호는 그대로 유지되며, 「재개」로 이어서 운용합니다.\n「전체 정지 (청산)」은 플릿 전체를 정지하고 모든 포지션을 즉시 청산합니다. 정지된 플릿은 다시 시작할 수 없고 새로 만들어야 합니다.',
              en: '"Pause" only stops new entries — open positions and their SL/TP protection stay active, and Resume continues the fleet.\n"Stop all (flatten)" halts the whole fleet and closes every position immediately. A stopped fleet cannot be restarted — you launch a new one.',
              ja: '「一時停止」は新規エントリーだけを止めます — 保有ポジションと損切り/利確の保護はそのまま維持され、「再開」で続行します。\n「全停止（清算）」はフリート全体を停止し、全ポジションを即座に清算します。停止したフリートは再開できず、新しく作成します。',
              th: '"พัก" หยุดเฉพาะการเข้าใหม่ — สถานะที่ถืออยู่และการป้องกัน SL/TP ยังทำงาน และกด "ดำเนินต่อ" เพื่อทำงานต่อ\n"หยุดทั้งหมด (ปิดสถานะ)" หยุดทั้งฟลีตและปิดทุกสถานะทันที ฟลีตที่หยุดแล้วเริ่มใหม่ไม่ได้ ต้องสร้างใหม่',
              vi: '"Tạm dừng" chỉ ngừng mở lệnh mới — các vị thế đang mở và bảo vệ SL/TP vẫn hoạt động, nhấn "Tiếp tục" để chạy tiếp.\n"Dừng tất cả (đóng lệnh)" dừng toàn bộ fleet và đóng mọi vị thế ngay lập tức. Fleet đã dừng không thể chạy lại — bạn khởi chạy fleet mới.',
              id: '"Jeda" hanya menghentikan entri baru — posisi terbuka beserta proteksi SL/TP-nya tetap aktif, dan "Lanjutkan" meneruskan fleet.\n"Hentikan semua (tutup posisi)" menghentikan seluruh fleet dan segera menutup setiap posisi. Fleet yang sudah dihentikan tidak bisa dijalankan lagi — Anda meluncurkan yang baru.',
            })} />
          </div>
          {error && (
            <div style={{ color: '#f0663f', fontSize: 12.5, marginTop: 8 }}>⚠️ {error}</div>
          )}
          {/* 플릿 수정 — the goal and slots controls live in this popup so the
              always-visible monitor stays read-only at a glance (owner ask
              2026-08-08). The rows inside are unchanged. */}
          {showEdit && (
          <div role="dialog" aria-modal="true" aria-label={T.editFleet}
            onClick={() => setShowEdit(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 70, background: 'rgba(0,0,0,0.55)',
              display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: 24, overflowY: 'auto' }}>
            <div onClick={e => e.stopPropagation()}
              style={{ width: '100%', maxWidth: 720, margin: 'auto', background: 'var(--bg-card,#fff)',
                border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>{T.editFleet}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)', marginTop: 2 }}>{T.editFleetSub}</div>
                </div>
                <button onClick={() => setShowEdit(false)}
                  style={{ padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>
                  {T.close}
                </button>
              </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 10, fontSize: 12 }}>
            <span style={{ fontWeight: 600 }}>{tr(language, { ko: '슬롯 수 (목표 TRADING 수)', en: 'Slots (target TRADINGs)', ja: 'スロット数（目標TRADING数）', th: 'จำนวนสล็อต (เป้า TRADING)', vi: 'Số slot (TRADING mục tiêu)', id: 'Slot (target TRADING)' })}</span>
            <HelpTip text={tr(language, {
              ko: '가동 중에도 플릿의 목표 슬롯 수를 바꿀 수 있습니다. 늘리면 예산 여유가 생기는 대로 AI가 새 슬롯을 채우고, 줄이면 초과 슬롯은 포지션이 스스로 종료될 때에만 회수됩니다 — 보유 포지션을 강제로 청산하지 않습니다(드레인 방식). 요금제의 슬롯 상한을 넘길 수는 없습니다.',
              en: 'You can change the fleet\'s target slot count while it is running. Raising it lets the AI fill new slots as budget headroom allows; lowering it retires excess slots only when their positions finish on their own — open positions are never force-closed (drain, not dump). Your plan\'s slot cap still applies.',
              ja: '稼働中でもフリートの目標スロット数を変更できます。増やすと予算に余裕ができ次第AIが新しいスロットを埋め、減らすと超過スロットはポジションが自然に終了したときにのみ回収されます — 保有ポジションを強制清算することはありません（ドレイン方式）。プランのスロット上限は適用されます。',
              th: 'เปลี่ยนจำนวนสล็อตเป้าหมายได้แม้ฟลีตกำลังทำงาน เพิ่มแล้ว AI จะเติมสล็อตใหม่เมื่องบมีที่ว่าง ลดแล้วสล็อตส่วนเกินจะถูกเก็บคืนเมื่อสถานะจบเองเท่านั้น — ไม่บังคับปิดสถานะที่ถืออยู่ (เดรน ไม่ใช่ทิ้ง) เพดานสล็อตของแพ็กเกจยังมีผล',
              vi: 'Bạn có thể đổi số slot mục tiêu khi fleet đang chạy. Tăng lên thì AI lấp slot mới khi ngân sách cho phép; giảm xuống thì slot dư chỉ được thu hồi khi vị thế của nó tự kết thúc — không bao giờ ép đóng vị thế đang mở (drain, không dump). Giới hạn slot của gói vẫn áp dụng.',
              id: 'Anda dapat mengubah target jumlah slot saat fleet berjalan. Menaikkannya membuat AI mengisi slot baru saat anggaran memungkinkan; menurunkannya menarik slot berlebih hanya ketika posisinya selesai sendiri — posisi terbuka tidak pernah ditutup paksa (drain, bukan dump). Batas slot paket Anda tetap berlaku.',
            })} />
            <input type="number" min={1} max={25} step={1}
              defaultValue={fleet.n_runs}
              onChange={e => setSizeN(Number(e.target.value))}
              style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-color,rgba(0,0,0,0.15))', width: 80, background: 'transparent', color: 'inherit' }} />
            <button style={chip(false)} disabled={busy} onClick={() => saveSize(sizeN)}>
              {tr(language, { ko: '슬롯 저장', en: 'Save slots', ja: 'スロットを保存', th: 'บันทึกสล็อต', vi: 'Lưu slot', id: 'Simpan slot' })}
            </button>
            <span style={{ color: (sizeN || fleet.n_runs) > (fleet.recommended_max_n_runs || 25) ? '#f0663f' : 'var(--text-muted,#a89f92)' }}>
              {(() => {
                // Live calc (owner ask 2026-08-08): as N is typed, show the
                // per-slot budget it implies and the AI's recommendation for
                // this balance, warning-coloured when the typed N exceeds it.
                const liveN = sizeN || fleet.n_runs
                const perSlot = fleet.total_budget_usd / Math.max(liveN, 1)
                const rec = fleet.recommended_max_n_runs
                return tr(language, {
                  ko: `현재 목표 ${fleet.n_runs}개 · ${liveN}개면 슬롯당 ≈ $${perSlot.toFixed(0)}${rec ? ` · 🤖 권장 최대 ${rec}개` : ''}`,
                  en: `current target ${fleet.n_runs} · ${liveN} → ≈ $${perSlot.toFixed(0)}/slot${rec ? ` · 🤖 rec. max ${rec}` : ''}`,
                  ja: `現在の目標 ${fleet.n_runs} · ${liveN}なら1スロット ≈ $${perSlot.toFixed(0)}${rec ? ` · 🤖 推奨最大 ${rec}` : ''}`,
                  th: `เป้าปัจจุบัน ${fleet.n_runs} · ${liveN} → ≈ $${perSlot.toFixed(0)}/สล็อต${rec ? ` · 🤖 แนะนำสูงสุด ${rec}` : ''}`,
                  vi: `mục tiêu hiện tại ${fleet.n_runs} · ${liveN} → ≈ $${perSlot.toFixed(0)}/slot${rec ? ` · 🤖 khuyến nghị tối đa ${rec}` : ''}`,
                  id: `target saat ini ${fleet.n_runs} · ${liveN} → ≈ $${perSlot.toFixed(0)}/slot${rec ? ` · 🤖 rek. maks ${rec}` : ''}`,
                })
              })()}
            </span>
          </div>
              {error && (
                <div style={{ color: '#f0663f', fontSize: 12.5, marginTop: 10 }}>⚠️ {error}</div>
              )}
            </div>
          </div>
          )}
          </>
          ) : (
          <>
            {(() => {
              const markets = Array.from(new Set(trades.map((t: any) => t.market).filter(Boolean)))
              const rows = trades.filter((t: any) => actMkt === 'all' || t.market === actMkt)
              return (
                <>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
                    {['all', ...markets].map(mk => (
                      <button key={mk} onClick={() => setActMkt(mk)} style={chip(actMkt === mk)}>
                        {mk === 'all' ? T.actAll : marketLabel(mk, language)}
                      </button>
                    ))}
                  </div>
                  {rows.length === 0 ? (
                    <div style={{ fontSize: 12.5, color: 'var(--text-muted,#a89f92)', padding: '16px 4px' }}>{T.actEmpty}</div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                        <thead>
                          <tr style={{ color: 'var(--text-secondary,#8a8073)', textAlign: 'right', fontSize: 11.5 }}>
                            <th style={{ textAlign: 'left', padding: '8px 10px', fontWeight: 600 }}>{T.actType}</th>
                            <th style={{ textAlign: 'left', padding: '8px 10px', fontWeight: 600 }}>Symbol</th>
                            <th style={{ padding: '8px 10px', fontWeight: 600 }}>{T.actQty}</th>
                            <th style={{ padding: '8px 10px', fontWeight: 600 }}>{T.actPrice}</th>
                            <th style={{ padding: '8px 10px', fontWeight: 600 }}>{T.actPnl}</th>
                            <th style={{ padding: '8px 10px', fontWeight: 600 }}>{T.actDate}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((t: any, i: number) => {
                            const side = String(t.side || '').toLowerCase()
                            const isBuy = side === 'buy' || side === 'cover'
                            const pnl = t.pnl
                            return (
                              <tr key={t.signal_id ?? i} style={{ borderTop: '1px solid var(--border-color,rgba(0,0,0,0.08))', textAlign: 'right' }}>
                                <td style={{ textAlign: 'left', padding: '9px 10px', fontWeight: 700, color: isBuy ? '#2e9e6b' : '#f0663f' }}>
                                  {String(t.side || '').toUpperCase()}
                                </td>
                                <td style={{ textAlign: 'left', padding: '9px 10px' }}>
                                  <b>{t.symbol}</b>
                                  {t.market && <span style={{ fontSize: 10.5, color: 'var(--text-muted,#a89f92)', background: 'var(--bg-hover,rgba(0,0,0,0.05))', borderRadius: 4, padding: '1px 6px', marginLeft: 6 }}>{marketLabel(t.market, language)}</span>}
                                </td>
                                <td style={{ padding: '9px 10px', fontVariantNumeric: 'tabular-nums' }}>{Number(t.quantity).toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                                <td style={{ padding: '9px 10px', fontVariantNumeric: 'tabular-nums' }}>{Number(t.entry_price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                                <td style={{ padding: '9px 10px', fontVariantNumeric: 'tabular-nums', color: pnl == null ? 'var(--text-muted,#a89f92)' : pnl >= 0 ? '#2e9e6b' : '#f0663f' }}>
                                  {pnl == null ? '—' : (pnl >= 0 ? '+' : '') + Number(pnl).toFixed(2)}
                                </td>
                                <td style={{ padding: '9px 10px', color: 'var(--text-muted,#a89f92)' }}>{String(t.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )
            })()}
          </>
          )}
        </>
      )}
      {/* Fleet-index guide, opened by the (?) on the index card. z 600 +
          32px top padding: dialogs must outrank the z-500 sticky nav. */}
      {showIndexGuide && (
        <div role="dialog" aria-modal="true" aria-label={T.idxGuideTitle}
          onClick={() => setShowIndexGuide(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
            padding: '32px 24px 24px', overflowY: 'auto' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: '100%', maxWidth: 560, margin: 'auto', background: 'var(--bg-card,#fff)',
              border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <div style={{ fontSize: 16, fontWeight: 800 }}>🎯 {T.idxGuideTitle}</div>
              <button onClick={() => setShowIndexGuide(false)} aria-label="close"
                style={{ marginLeft: 'auto', border: 'none', background: 'transparent',
                  color: 'var(--text-secondary,#8a8073)', fontSize: 18, cursor: 'pointer', lineHeight: 1 }}>
                ✕
              </button>
            </div>
            {[T.idxGuideWhat, T.idxGuideRead, T.idxGuideWhy, T.idxGuideLine, T.idxGuideAccount].map((p, i) => (
              <p key={i} style={{ fontSize: 13.5, lineHeight: 1.6, margin: '0 0 10px',
                color: i === 0 ? 'inherit' : 'var(--text-secondary,#5f574c)' }}>
                {p}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
