import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { GuideBadge, HelpTip } from '../components/HelpTip'
import { RunSparkline } from '../components/RunSparkline'
import { SymbolSelect } from '../components/SymbolSelect'
import { useRunStream } from '../hooks/useRunStream'
import { Language, tr } from '../i18n'

// Live trading-run dashboard (Plan 10, Phase 8). Route /runs/live.
//   * multi-run grid of small multiples (equity WebGL2 sparkline + status +
//     last-update AGE BADGE — honest staleness for poll-bound markets)
//   * click-through to run detail (price/equity chart + event log)
//   * create form (settings + reporting) and lifecycle controls
// Streaming is via useRunStream (ticketed /ws/runs); the grid equity series
// come from each run's snapshot + live equity events.

interface Props { token?: string | null }

// `capability` is what `status` cannot tell you: a run reads "running"
// whether it is hunting, parked on a closed market, or arithmetically unable
// to ever open a position. Prod 2026-07-27: three of seven running runs held
// $3,399 behind a permanent fee block and this page showed all seven green.
// Computed server-side from the frozen config snapshot (routes_runs._capability).
type Capability = {
  state: 'hunting' | 'waiting' | 'cannot_trade' | 'inactive'
  permanent: boolean
  reason_code?: string | null
  reason?: string | null
  capital_usd?: number | null
}

type Run = {
  id: number; symbol: string; market: string; market_type: string
  status: string; status_reason?: string
  config?: any; realized_pnl_usd?: number
  last_cycle_at?: string; last_event_seq?: number
  capability?: Capability
}

// Only two of these need to shout. `hunting` is the healthy default and gets
// no chip at all — a badge on every card is a badge on none.
const CAPABILITY_TEXT: Record<string, Record<Language, string>> = {
  cannot_trade: {
    ko: '거래 불가', en: 'Cannot trade', ja: '取引不可',
    th: 'เทรดไม่ได้', vi: 'Không thể giao dịch', id: 'Tidak dapat bertransaksi' },
  waiting: {
    ko: '장 마감 대기', en: 'Market closed', ja: '市場クローズ',
    th: 'ตลาดปิด', vi: 'Thị trường đóng', id: 'Pasar tutup' },
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'var(--text-muted, #898781)',
  armed: '#eda100',
  running: '#0ca30c',
  paused: '#7a68d8',
  stopping: '#eb6834',
  stopped: '#898781',
}

// The (?) field guide on every TRADING card. The card speaks trader shorthand
// (45m, ≥50%, 마크가, 격리, TP/SL) — each row below explains one thing the
// card actually shows, in the order the card shows it. Terms mirror the
// card's own localized labels so the guide and the card read as one.
const CARD_GUIDE = {
  open: { ko: '카드 항목 설명 보기', en: 'What do these fields mean?', ja: 'カード項目の説明', th: 'ช่องเหล่านี้คืออะไร', vi: 'Các trường này nghĩa là gì?', id: 'Apa arti kolom-kolom ini?' },
  title: { ko: 'TRADING 카드 읽는 법', en: 'How to read a TRADING card', ja: 'TRADING カードの読み方', th: 'วิธีอ่านการ์ด TRADING', vi: 'Cách đọc thẻ TRADING', id: 'Cara membaca kartu TRADING' },
  rows: [
    { term: { ko: '종목 · 시장 · 🚀#N', en: 'Symbol · market · 🚀#N', ja: '銘柄 · 市場 · 🚀#N', th: 'เหรียญ · ตลาด · 🚀#N', vi: 'Mã · thị trường · 🚀#N', id: 'Simbol · pasar · 🚀#N' },
      desc: { ko: '거래하는 종목과 시장입니다. "fut"는 선물 장부라는 뜻이고, 🚀#N 배지는 이 TRADING이 N번 자동 편성 플릿의 일원이라는 표시입니다. "실행 중"이면 AI가 주기마다 판단하고 있습니다.',
        en: 'What this TRADING trades and where. "fut" means a futures book; the 🚀#N badge means it belongs to Full-Auto fleet #N. "Running" means the AI is deciding on schedule.',
        ja: '取引する銘柄と市場。「fut」は先物ブック、🚀#N はフリート#N の一員という意味。「実行中」ならAIが周期ごとに判断しています。',
        th: 'สิ่งที่ TRADING นี้เทรดและตลาดที่เทรด "fut" คือบัญชีฟิวเจอร์ส ป้าย 🚀#N หมายถึงเป็นสมาชิกฟลีต #N "กำลังทำงาน" คือ AI กำลังตัดสินใจตามรอบ',
        vi: 'Mã và thị trường mà TRADING này giao dịch. "fut" là sổ hợp đồng tương lai; huy hiệu 🚀#N nghĩa là thuộc nhóm tự động #N. "Đang chạy" nghĩa là AI đang quyết định theo chu kỳ.',
        id: 'Apa yang diperdagangkan TRADING ini dan di mana. "fut" berarti buku futures; lencana 🚀#N berarti anggota fleet Full-Auto #N. "Berjalan" berarti AI memutuskan sesuai jadwal.' } },
    { term: { ko: '최대 베팅 · 주기 · 유형 · AI', en: 'Max bet · Interval · Type · AI', ja: '最大 · 間隔 · タイプ · AI', th: 'สูงสุด · ช่วง · ชนิด · AI', vi: 'Cược tối đa · Chu kỳ · Loại · AI', id: 'Taruhan maks · Interval · Jenis · AI' },
      desc: { ko: '전략 요약 칸입니다. 최대 베팅은 한 포지션에 걸 수 있는 상한, 주기 45m·≥50%는 AI가 45분마다 판단하고 확신이 50% 미만이면 진입하지 않는다는 뜻, 유형은 spot(현물)/futures(선물)와 레버리지, AI는 판단에 쓰는 모델입니다.',
        en: 'The strategy facts. Max bet is the cap per position; Interval 45m · ≥50% means the AI decides every 45 minutes and does not enter below 50% conviction; Type is the book (spot/futures) and leverage; AI is the model making the calls.',
        ja: '戦略欄。最大はポジションあたりの上限、間隔 45m·≥50% はAIが45分ごとに判断し確信50%未満では入らない意味、タイプはブック種別（spot/futures）とレバレッジ、AI は判断に使うモデルです。',
        th: 'ข้อมูลกลยุทธ์: สูงสุดคือเพดานต่อสถานะ, ช่วง 45m·≥50% คือ AI ตัดสินใจทุก 45 นาทีและไม่เข้าเมื่อความมั่นใจต่ำกว่า 50%, ชนิดคือบัญชี (spot/futures) กับเลเวอเรจ, AI คือโมเดลที่ใช้ตัดสินใจ',
        vi: 'Các thông số chiến lược: Cược tối đa là trần mỗi vị thế; Chu kỳ 45m·≥50% nghĩa là AI quyết định mỗi 45 phút và không vào lệnh dưới 50% độ tin cậy; Loại là sổ (spot/futures) và đòn bẩy; AI là mô hình ra quyết định.',
        id: 'Fakta strategi: Taruhan maks adalah batas per posisi; Interval 45m·≥50% berarti AI memutuskan tiap 45 menit dan tidak masuk di bawah keyakinan 50%; Jenis adalah buku (spot/futures) dan leverage; AI adalah model yang mengambil keputusan.' } },
    { term: { ko: '📋 메모 줄', en: '📋 note line', ja: '📋 メモ行', th: 'บรรทัด 📋', vi: 'Dòng 📋', id: 'Baris 📋' },
      desc: { ko: 'AI의 최근 판단 메모입니다 — 왜 진입/보류했는지, 어떤 리스크 조정이 걸려 있는지를 그대로 보여줍니다 (예: "risk: confidence 0.42 below threshold 0.5" = 확신 부족으로 보류).',
        en: 'The AI\'s latest decision note — why it entered or held, or which risk adjustment is active (e.g. "risk: confidence 0.42 below threshold 0.5" = held for lack of conviction).',
        ja: 'AIの直近の判断メモ — なぜ入った/見送ったか、どのリスク調整が効いているか（例: "risk: confidence 0.42 below threshold 0.5" = 確信不足で見送り）。',
        th: 'บันทึกการตัดสินใจล่าสุดของ AI — ทำไมเข้า/รอ หรือมีการปรับความเสี่ยงใด (เช่น "risk: confidence 0.42 below threshold 0.5" = รอเพราะความมั่นใจไม่พอ)',
        vi: 'Ghi chú quyết định mới nhất của AI — vì sao vào/chờ, hay điều chỉnh rủi ro nào đang bật (vd. "risk: confidence 0.42 below threshold 0.5" = chờ vì thiếu tự tin).',
        id: 'Catatan keputusan terbaru AI — mengapa masuk atau menahan, atau penyesuaian risiko yang aktif (mis. "risk: confidence 0.42 below threshold 0.5" = ditahan karena kurang yakin).' } },
    { term: { ko: '포지션 없음 — 현금 대기', en: 'No position — holding cash', ja: 'ポジションなし — 現金待機', th: 'ไม่มีสถานะ — ถือเงินสด', vi: 'Không vị thế — giữ tiền mặt', id: 'Tidak ada posisi — memegang kas' },
      desc: { ko: '지금은 열린 포지션이 없고 예산이 현금으로 대기 중이라는 뜻입니다. AI가 조건이 맞는 순간을 기다리고 있는 정상 상태입니다.',
        en: 'No position is open right now; the budget waits in cash. This is a normal state — the AI is waiting for a setup that clears its rules.',
        ja: '現在ポジションはなく、予算は現金で待機中。AIが条件の揃う瞬間を待っている正常な状態です。',
        th: 'ยังไม่มีสถานะเปิด งบรออยู่เป็นเงินสด เป็นสภาวะปกติ — AI กำลังรอจังหวะที่ผ่านกติกา',
        vi: 'Hiện không có vị thế mở; ngân sách chờ bằng tiền mặt. Đây là trạng thái bình thường — AI đang đợi cơ hội đạt điều kiện.',
        id: 'Tidak ada posisi terbuka saat ini; anggaran menunggu dalam bentuk kas. Ini normal — AI menunggu peluang yang lolos aturannya.' } },
    { term: { ko: '롱/숏 · 수량 · 진입가 · 마크가 · 평가액', en: 'LONG/SHORT · qty · entry · mark · value', ja: 'ロング/ショート · 数量 · 進入価格 · マーク価格 · 評価額', th: 'ลอง/ชอร์ต · จำนวน · ราคาเข้า · ราคามาร์ก · มูลค่า', vi: 'LONG/SHORT · KL · giá vào · giá mark · giá trị', id: 'LONG/SHORT · jml · harga masuk · harga pasar · nilai' },
      desc: { ko: '열린 포지션의 기본 정보입니다. 롱은 상승, 숏은 하락에 베팅. 진입가는 살(팔) 때 가격, 마크가는 지금 가격, 평가액은 포지션의 현재 가치입니다.',
        en: 'The open position\'s basics. LONG bets on a rise, SHORT on a fall. Entry is the price it opened at, mark is the price now, value is what the position is worth at the mark.',
        ja: '保有ポジションの基本。ロングは上昇、ショートは下落に賭けます。進入価格は建てた価格、マーク価格は現在価格、評価額は現在価値。',
        th: 'ข้อมูลพื้นฐานของสถานะ: ลองเดิมพันขาขึ้น ชอร์ตขาลง ราคาเข้าคือราคาที่เปิด ราคามาร์กคือราคาตอนนี้ มูลค่าคือมูลค่าปัจจุบันของสถานะ',
        vi: 'Thông tin cơ bản của vị thế: LONG đặt cược giá lên, SHORT giá xuống. Giá vào là giá mở, giá mark là giá hiện tại, giá trị là giá trị vị thế theo giá mark.',
        id: 'Dasar-dasar posisi terbuka. LONG bertaruh naik, SHORT turun. Harga masuk adalah harga saat dibuka, harga pasar adalah harga sekarang, nilai adalah nilai posisi pada harga pasar.' } },
    { term: { ko: '미실현 vs 실현', en: 'Unrealized vs realized', ja: '含み損益と実現損益', th: 'ยังไม่รับรู้ vs รับรู้แล้ว', vi: 'Chưa chốt vs đã chốt', id: 'Belum vs sudah direalisasi' },
      desc: { ko: '미실현은 지금 닫으면 생길 손익(가격 따라 계속 변함), 실현은 이미 닫은 거래로 확정된 손익입니다.',
        en: 'Unrealized is what you would make or lose if the position closed right now (it moves with price). Realized is banked P&L from trades already closed.',
        ja: '含みは今閉じた場合の損益（価格で変動）、実現は既に閉じた取引で確定した損益。',
        th: 'ยังไม่รับรู้คือกำไร/ขาดทุนถ้าปิดตอนนี้ (ขยับตามราคา) รับรู้แล้วคือผลที่ล็อกจากดีลที่ปิดไปแล้ว',
        vi: 'Chưa chốt là lãi/lỗ nếu đóng ngay bây giờ (thay đổi theo giá). Đã chốt là lãi/lỗ cố định từ các lệnh đã đóng.',
        id: 'Belum direalisasi adalah untung/rugi jika posisi ditutup sekarang (bergerak mengikuti harga). Direalisasi adalah laba rugi yang sudah dikunci dari transaksi yang ditutup.' } },
    { term: { ko: '격리 N배 · 담보 · 청산가', en: 'Isolated Nx · collateral · liq. price', ja: '分離N倍 · 担保 · 清算価格', th: 'แยก Nx · หลักประกัน · ราคาล้าง', vi: 'Cô lập Nx · ký quỹ · giá thanh lý', id: 'Terisolasi Nx · jaminan · harga likuidasi' },
      desc: { ko: '선물 포지션에만 나옵니다. N배는 레버리지, 담보는 이 포지션에 잠긴 증거금, 청산가는 가격이 여기까지 역행하면 포지션이 강제 종료되는 지점입니다. 격리라서 최대 손실은 담보까지입니다.',
        en: 'Futures only. Nx is the leverage, collateral is the margin locked to this position, and the liquidation price is where an adverse move force-closes it. Isolated margin caps the worst case at the collateral.',
        ja: '先物のみ。N倍はレバレッジ、担保はこのポジションの証拠金、清算価格は逆行で強制終了される価格。分離マージンなので最大損失は担保まで。',
        th: 'เฉพาะฟิวเจอร์ส: Nx คือเลเวอเรจ หลักประกันคือมาร์จิ้นที่ล็อกไว้ ราคาล้างคือจุดที่ราคาสวนจนถูกบังคับปิด มาร์จิ้นแบบแยกจำกัดขาดทุนสูงสุดที่หลักประกัน',
        vi: 'Chỉ với futures: Nx là đòn bẩy, ký quỹ là số tiền khóa cho vị thế này, giá thanh lý là mức giá ngược chiều khiến vị thế bị đóng bắt buộc. Ký quỹ cô lập giới hạn lỗ tối đa ở mức ký quỹ.',
        id: 'Hanya futures. Nx adalah leverage, jaminan adalah margin yang terkunci untuk posisi ini, harga likuidasi adalah titik di mana pergerakan berlawanan menutup paksa posisi. Margin terisolasi membatasi kerugian maksimum sebesar jaminan.' } },
    { term: { ko: 'TP / SL', en: 'TP / SL', ja: 'TP / SL', th: 'TP / SL', vi: 'TP / SL', id: 'TP / SL' },
      desc: { ko: '자동 청산 브래킷입니다. TP(익절)는 이익이 그 금액에 닿으면, SL(손절)은 손실이 그 금액에 닿으면 포지션을 자동으로 닫습니다.',
        en: 'The automatic exit bracket. TP (take-profit) closes the position when profit reaches that amount; SL (stop-loss) closes it when the loss reaches that amount.',
        ja: '自動決済ブラケット。TP（利確）は利益が到達したら、SL（損切り）は損失が到達したら自動で閉じます。',
        th: 'กรอบปิดอัตโนมัติ: TP ปิดเมื่อกำไรถึงจำนวนนั้น SL ปิดเมื่อขาดทุนถึงจำนวนนั้น',
        vi: 'Khung thoát tự động: TP (chốt lời) đóng vị thế khi lãi chạm mức đó; SL (cắt lỗ) đóng khi lỗ chạm mức đó.',
        id: 'Braket keluar otomatis. TP (ambil untung) menutup posisi saat profit mencapai jumlah itu; SL (stop rugi) menutupnya saat kerugian mencapai jumlah itu.' } },
    { term: { ko: '🛡 청산 방어', en: '🛡 Liq. defense', ja: '🛡 清算防御', th: '🛡 ป้องกันการล้าง', vi: '🛡 Phòng vệ thanh lý', id: '🛡 Pertahanan likuidasi' },
      desc: { ko: '레버리지 포지션이 청산가에 다가가면 단계별(T1/T2/T3)로 개입하는 방어 데몬의 상태입니다. 건전도·청산까지 남은 거리를 보여주며, 레버리지가 없으면 "방어 불필요"로 표시됩니다.',
        en: 'The defense daemon that steps in (tiers T1/T2/T3) as a leveraged position approaches liquidation. It shows health and distance to liquidation; with no leverage it reads "no defense needed".',
        ja: 'レバレッジポジションが清算に近づくと段階的（T1/T2/T3）に介入する防御デーモンの状態。健全度と清算までの距離を表示し、レバレッジ無しなら「防御不要」。',
        th: 'ดีมอนป้องกันที่เข้าแทรกเป็นขั้น (T1/T2/T3) เมื่อสถานะเลเวอเรจใกล้ถูกล้าง แสดงสุขภาพและระยะถึงจุดล้าง ถ้าไม่มีเลเวอเรจจะขึ้นว่าไม่จำเป็น',
        vi: 'Daemon phòng vệ can thiệp theo bậc (T1/T2/T3) khi vị thế đòn bẩy tiến gần thanh lý. Hiển thị sức khỏe và khoảng cách đến thanh lý; không có đòn bẩy thì ghi "không cần phòng vệ".',
        id: 'Daemon pertahanan yang turun tangan bertahap (T1/T2/T3) saat posisi ber-leverage mendekati likuidasi. Menampilkan kesehatan dan jarak ke likuidasi; tanpa leverage tertulis "tidak perlu pertahanan".' } },
    { term: { ko: '그래프 · ±$ · ⧗', en: 'Sparkline · ±$ · ⧗', ja: 'グラフ · ±$ · ⧗', th: 'กราฟ · ±$ · ⧗', vi: 'Biểu đồ · ±$ · ⧗', id: 'Grafik · ±$ · ⧗' },
      desc: { ko: '작은 그래프는 이 TRADING의 최근 손익 곡선, 왼쪽 아래 ±$는 이 TRADING의 누적 실현 손익입니다. ⧗는 가격 데이터의 나이 — 가격 갱신 주기 때문에 몇 분 전 값일 수 있습니다.',
        en: 'The small chart is this TRADING\'s recent P&L curve; the ±$ at the bottom left is its cumulative realized P&L. ⧗ is the age of the price data — refresh cycles mean it can be a few minutes old.',
        ja: '小さなグラフは直近の損益曲線、左下の±$は累積実現損益。⧗は価格データの経過時間 — 更新周期の都合で数分前の値のことがあります。',
        th: 'กราฟเล็กคือเส้นกำไร/ขาดทุนล่าสุดของ TRADING นี้ ±$ ซ้ายล่างคือกำไรรับรู้สะสม ⧗ คืออายุของข้อมูลราคา — อาจเก่าไม่กี่นาทีตามรอบรีเฟรช',
        vi: 'Biểu đồ nhỏ là đường lãi/lỗ gần đây của TRADING này; ±$ góc dưới trái là lãi/lỗ đã chốt lũy kế. ⧗ là tuổi của dữ liệu giá — có thể cũ vài phút theo chu kỳ cập nhật.',
        id: 'Grafik kecil adalah kurva laba rugi terkini TRADING ini; ±$ di kiri bawah adalah laba rugi direalisasi kumulatifnya. ⧗ adalah umur data harga — bisa beberapa menit karena siklus pembaruan.' } },
  ],
} as const

// A raw status ("stopped") and a raw reason ("stop_event:max_loss") tell the
// user nothing — the reason in particular is the only thing that explains WHY
// a TRADING ended. Both are rendered through these maps in the active locale.
const STATUS_TEXT: Record<string, Record<Language, string>> = {
  draft: { ko: '준비됨', en: 'Ready', ja: '準備完了', th: 'พร้อม', vi: 'Sẵn sàng', id: 'Siap' },
  armed: { ko: '대기 중', en: 'Waiting', ja: '待機中', th: 'รออยู่', vi: 'Đang chờ', id: 'Menunggu' },
  running: { ko: '실행 중', en: 'Running', ja: '実行中', th: 'กำลังทำงาน', vi: 'Đang chạy', id: 'Berjalan' },
  paused: { ko: '일시정지', en: 'Paused', ja: '一時停止', th: 'หยุดชั่วคราว', vi: 'Tạm dừng', id: 'Dijeda' },
  stopping: { ko: '정지하는 중', en: 'Stopping', ja: '停止処理中', th: 'กำลังหยุด', vi: 'Đang dừng', id: 'Sedang berhenti' },
  stopped: { ko: '정지됨', en: 'Stopped', ja: '停止済み', th: 'หยุดแล้ว', vi: 'Đã dừng', id: 'Berhenti' },
}

const REASON_TEXT: Record<string, Record<Language, string>> = {
  // NOT "you pressed Stop" — this reason only means a stop request arrived on
  // the agent token, which is just as often a QA session or a script as it is
  // the owner clicking the button. Say what actually happened, not who did it.
  user_stop: {
    ko: '수동 정지 — 이 TRADING에 정지 요청이 들어왔습니다 (정지 버튼 또는 API)',
    en: 'Stopped by hand — a Stop request arrived for this TRADING (button or API)',
    ja: '手動停止 — この TRADING に停止リクエストが届きました（ボタンまたは API）',
    th: 'หยุดด้วยมือ — มีคำขอหยุดส่งมาที่ TRADING นี้ (ปุ่มหรือ API)',
    vi: 'Dừng thủ công — có yêu cầu Dừng gửi tới TRADING này (nút hoặc API)',
    id: 'Dihentikan manual — ada permintaan Stop untuk TRADING ini (tombol atau API)' },
  // NOT a person either — the fleet stopped its whole sleeve. 59 of the 61
  // runs that read "user_stop" on prod were this, arriving in batches of four.
  fleet_stop_all: {
    ko: '전체 정지 — 이 TRADING이 속한 N종목 전체가 함께 정지되었습니다',
    en: 'Stop all — the whole sleeve this TRADING belongs to was stopped together',
    ja: '全体停止 — この TRADING が属するスリーブ全体が停止されました',
    th: 'หยุดทั้งหมด — สลีฟที่ TRADING นี้อยู่ถูกหยุดพร้อมกันทั้งชุด',
    vi: 'Dừng tất cả — toàn bộ sleeve chứa TRADING này đã bị dừng cùng lúc',
    id: 'Stop semua — seluruh sleeve tempat TRADING ini berada dihentikan bersamaan' },
  fleet_profit_target: {
    ko: '플릿 목표 수익 달성 — N종목 전체가 이익을 확정하고 정지했습니다',
    en: 'Fleet profit target — the sleeve banked its gain and stopped',
    ja: 'フリート利益目標達成 — スリーブ全体が利益を確定して停止しました',
    th: 'ฟลีทถึงเป้าหมายกำไร — สลีฟล็อกกำไรและหยุด',
    vi: 'Fleet đạt mục tiêu lợi nhuận — sleeve chốt lãi và dừng',
    id: 'Target profit fleet — sleeve membukukan keuntungannya lalu berhenti' },
  fleet_breaker: {
    ko: '플릿 서킷 브레이커 — 손실 한도에 도달해 N종목 전체가 청산되었습니다',
    en: 'Fleet circuit breaker — the loss rail fired and the sleeve was closed',
    ja: 'フリートのサーキットブレーカー — 損失ラインに達しスリーブ全体を決済しました',
    th: 'เซอร์กิตเบรกเกอร์ของฟลีท — ถึงขีดขาดทุนและปิดสลีฟทั้งชุด',
    vi: 'Ngắt mạch fleet — chạm ngưỡng lỗ và toàn bộ sleeve đã bị đóng',
    id: 'Pemutus sirkuit fleet — batas kerugian terpicu dan sleeve ditutup' },
  user_pause: {
    ko: '수동 일시정지 — 일시정지 요청이 들어왔습니다',
    en: 'Paused by hand — a Pause request arrived',
    ja: '手動一時停止 — 一時停止リクエストが届きました',
    th: 'หยุดชั่วคราวด้วยมือ — มีคำขอหยุดชั่วคราวส่งมา',
    vi: 'Tạm dừng thủ công — có yêu cầu Tạm dừng',
    id: 'Dijeda manual — ada permintaan Pause' },
  'stop_event:profit_target': {
    ko: '목표 수익에 도달했습니다 — 같은 설정으로 새 TRADING이 자동 시작됩니다',
    en: 'Profit target reached — a new TRADING with the same settings starts automatically',
    ja: '目標利益に到達しました — 同じ設定で新しい TRADING が自動開始されます',
    th: 'ถึงเป้ากำไรแล้ว — TRADING ใหม่ด้วยการตั้งค่าเดิมจะเริ่มอัตโนมัติ',
    vi: 'Đã đạt mục tiêu lợi nhuận — một TRADING mới với cùng thiết lập sẽ tự khởi động',
    id: 'Target profit tercapai — TRADING baru dengan pengaturan yang sama dimulai otomatis' },
  'stop_event:max_trades': {
    ko: '설정한 최대 거래 횟수를 채웠습니다 — 같은 설정으로 새 TRADING이 자동 시작됩니다',
    en: 'Trade limit reached — a new TRADING with the same settings starts automatically',
    ja: '最大取引回数に達しました — 同じ設定で新しい TRADING が自動開始されます',
    th: 'ครบจำนวนเทรดสูงสุด — TRADING ใหม่ด้วยการตั้งค่าเดิมจะเริ่มอัตโนมัติ',
    vi: 'Đã đạt giới hạn số lệnh — một TRADING mới với cùng thiết lập sẽ tự khởi động',
    id: 'Batas jumlah transaksi tercapai — TRADING baru dengan pengaturan yang sama dimulai otomatis' },
  'stop_event:max_loss': {
    ko: '손실 한도에 도달해 잔고 보호를 위해 멈췄습니다 — 자동 재시작하지 않습니다',
    en: 'Loss limit hit — stopped to protect your balance, and it does NOT auto-restart',
    ja: '損失上限に達したため停止しました — 自動再開はしません',
    th: 'ถึงขีดจำกัดขาดทุน — หยุดเพื่อป้องกันยอดเงิน และจะไม่เริ่มใหม่อัตโนมัติ',
    vi: 'Chạm giới hạn lỗ — dừng để bảo vệ số dư, và KHÔNG tự khởi động lại',
    id: 'Batas kerugian tersentuh — dihentikan untuk melindungi saldo Anda, dan TIDAK dimulai ulang otomatis' },
  'stop_event:at_time': {
    ko: '예약한 종료 시각이 되었습니다', en: 'The scheduled end time arrived',
    ja: '予約した終了時刻になりました', th: 'ถึงเวลาสิ้นสุดที่ตั้งไว้',
    vi: 'Đã đến thời điểm kết thúc đã đặt',
    id: 'Waktu berakhir yang dijadwalkan telah tiba' },
  'stop_event:price_cross': {
    ko: '설정한 가격선을 통과했습니다', en: 'Price crossed the line you set',
    ja: '設定した価格ラインを超えました', th: 'ราคาข้ามเส้นที่คุณตั้งไว้',
    vi: 'Giá đã vượt mức bạn đặt',
    id: 'Harga melewati garis yang Anda tetapkan' },
  synthetic_liquidation: {
    ko: '숏 손실이 담보 전액에 도달해 강제 청산했습니다',
    en: 'Force-closed — the short’s loss reached your full collateral',
    ja: 'ショートの損失が担保全額に達し強制決済しました',
    th: 'ปิดบังคับ — ขาดทุนของ short ถึงหลักประกันทั้งหมด',
    vi: 'Đóng bắt buộc — lỗ của lệnh short đã chạm toàn bộ ký quỹ',
    id: 'Ditutup paksa — kerugian posisi short mencapai seluruh jaminan Anda' },
  stop_eval_failed: {
    ko: '가격이 오래되어 정지 조건을 확인할 수 없어 안전하게 멈췄습니다',
    en: 'Stopped for safety — prices went stale, so stop conditions could not be checked',
    ja: '価格が古く停止条件を確認できないため安全のため停止しました',
    th: 'หยุดเพื่อความปลอดภัย — ราคาเก่าเกินไปจึงตรวจเงื่อนไขหยุดไม่ได้',
    vi: 'Dừng để an toàn — giá quá cũ nên không kiểm tra được điều kiện dừng',
    id: 'Dihentikan demi keamanan — harga tidak diperbarui sehingga kondisi stop tidak dapat diperiksa' },
  stop_eval_recovered: {
    ko: '가격 수신이 회복되어 다시 실행합니다', en: 'The price feed recovered — running again',
    ja: '価格配信が回復し再開しました', th: 'ราคากลับมาปกติ — ทำงานต่อ',
    vi: 'Nguồn giá đã hồi phục — chạy lại',
    id: 'Umpan harga pulih — berjalan kembali' },
  positions_held: {
    ko: '정지했지만 포지션은 손절·익절 감시 아래 그대로 유지됩니다',
    en: 'Stopped, but the position is kept open under the stop-loss / take-profit watcher',
    ja: '停止しましたがポジションは損切り・利確監視下で保持されます',
    th: 'หยุดแล้ว แต่สถานะยังเปิดอยู่ภายใต้ตัวเฝ้า SL/TP',
    vi: 'Đã dừng, nhưng vị thế vẫn mở dưới bộ theo dõi cắt lỗ / chốt lời',
    id: 'Berhenti, tetapi posisi tetap terbuka di bawah pengawas stop loss / take profit' },
  stop_complete: {
    ko: '정상적으로 종료했습니다', en: 'Finished normally', ja: '正常に終了しました',
    th: 'จบการทำงานตามปกติ', vi: 'Đã kết thúc bình thường', id: 'Selesai dengan normal' },
  armed_timeout: {
    ko: '대기 시간 안에 시작 조건이 발생하지 않았습니다',
    en: 'The start condition never fired within the waiting window',
    ja: '待機時間内に開始条件が発生しませんでした',
    th: 'เงื่อนไขเริ่มไม่เกิดขึ้นภายในเวลารอ',
    vi: 'Điều kiện khởi động không xảy ra trong thời gian chờ',
    id: 'Kondisi mulai tidak pernah terpicu dalam jendela tunggu' },
  start_condition_fired: {
    ko: '시작 조건이 충족되어 실행에 들어갔습니다', en: 'The start condition fired',
    ja: '開始条件が成立しました', th: 'เงื่อนไขเริ่มทำงานแล้ว', vi: 'Điều kiện khởi động đã kích hoạt', id: 'Kondisi mulai terpicu' },
  stop_conditions_tightened: {
    ko: '정지 조건을 더 엄격하게 변경했습니다', en: 'Stop conditions were tightened',
    ja: '停止条件を厳しくしました', th: 'ปรับเงื่อนไขหยุดให้เข้มขึ้น',
    vi: 'Điều kiện dừng đã được siết chặt',
    id: 'Kondisi stop diperketat' },
  created: {
    ko: '생성되었습니다', en: 'Created', ja: '作成しました', th: 'สร้างแล้ว', vi: 'Đã tạo', id: 'Dibuat' },
  // The four below were never rendered until the AI Analysis panel started
  // showing transitions; prod's journal has all of them (2026-08-07).
  start: {
    ko: '실행을 시작했습니다', en: 'Started running', ja: '実行を開始しました',
    th: 'เริ่มทำงานแล้ว', vi: 'Đã bắt đầu chạy', id: 'Mulai berjalan' },
  desk_retired: {
    ko: '데스크가 이 TRADING을 종료하고 슬롯을 반납했습니다',
    en: 'The desk retired this TRADING and handed the slot back',
    ja: 'デスクがこの TRADING を終了しスロットを返却しました',
    th: 'เดสก์ปิด TRADING นี้และคืนสล็อต',
    vi: 'Bàn giao dịch đã kết thúc TRADING này và trả lại suất',
    id: 'Meja menutup TRADING ini dan mengembalikan slotnya' },
  'stop_event:trailing_lock': {
    ko: '추적 손절선이 이익을 잠갔습니다',
    en: 'The trailing stop locked the gain in',
    ja: 'トレーリングストップが利益を確定しました',
    th: 'เทรลลิงสต็อปล็อกกำไรไว้แล้ว',
    vi: 'Lệnh dừng lỗ động đã khóa lợi nhuận',
    id: 'Trailing stop mengunci keuntungan' },
  'stop_event:conviction_collapse': {
    ko: '확신이 무너져 정지했습니다',
    en: 'Conviction collapsed — stopped',
    ja: '確信が崩れたため停止しました',
    th: 'ความมั่นใจพังลง — จึงหยุด',
    vi: 'Niềm tin sụp đổ — đã dừng',
    id: 'Keyakinan runtuh — dihentikan' },
}

// The two stop buttons share one API action — the key tells them apart so
// the in-flight spinner lands on the button that was actually pressed.
function actionKey(action: string, body?: any): string {
  if (action === 'stop') return body?.flatten ? 'stop:flatten' : 'stop:hold'
  return action
}

export function statusLabel(status: string | undefined, lang: Language): string {
  if (!status) return ''
  return STATUS_TEXT[status] ? tr(lang, STATUS_TEXT[status]) : status
}

// The desk's verb, on a decision or a fill. Same four words the AI Analysis
// panel chips use — kept here because this is where the other enum maps live
// and the panel already imports from this module.
export const ACTION_TEXT: Record<string, Record<Language, string>> = {
  buy: { ko: '매수', en: 'BUY', ja: '買い', th: 'ซื้อ', vi: 'MUA', id: 'BELI' },
  sell: { ko: '매도', en: 'SELL', ja: '売り', th: 'ขาย', vi: 'BÁN', id: 'JUAL' },
  hold: { ko: '보류', en: 'HOLD', ja: 'ホールド', th: 'ถือไว้', vi: 'GIỮ', id: 'TAHAN' },
  retire: { ko: '슬롯 반납', en: 'RETIRE', ja: 'スロット返却', th: 'คืนสล็อต', vi: 'TRẢ SUẤT', id: 'LEPAS SLOT' },
}

export function actionLabel(action: string | undefined, lang: Language): string {
  if (!action) return ''
  return ACTION_TEXT[action] ? tr(lang, ACTION_TEXT[action]) : action
}

// Which gate turned a cycle away. The reason beside it says what happened;
// the stage says where, so it has to be a word rather than a field name.
const STAGE_TEXT: Record<string, Record<Language, string>> = {
  pre: { ko: '사전 점검', en: 'pre-check', ja: '事前チェック', th: 'ตรวจก่อนเทรด', vi: 'kiểm tra trước', id: 'pra-periksa' },
  execute: { ko: '주문 실행', en: 'execution', ja: '注文執行', th: 'การส่งคำสั่ง', vi: 'khớp lệnh', id: 'eksekusi' },
  risk: { ko: '리스크', en: 'risk', ja: 'リスク', th: 'ความเสี่ยง', vi: 'rủi ro', id: 'risiko' },
  budget: { ko: '예산', en: 'budget', ja: '予算', th: 'งบประมาณ', vi: 'ngân sách', id: 'anggaran' },
  adapt: { ko: '적응', en: 'adapt', ja: 'アダプト', th: 'ปรับตัว', vi: 'thích ứng', id: 'adaptif' },
  horizon: { ko: '보유 기간', en: 'horizon', ja: '保有期間', th: 'กรอบเวลา', vi: 'khung thời gian', id: 'horizon' },
  fee_edge: { ko: '수수료 대비 기대값', en: 'fee edge', ja: '手数料エッジ', th: 'ส่วนต่างค่าธรรมเนียม', vi: 'biên phí', id: 'margin biaya' },
  rr_floor: { ko: '손익비 하한', en: 'risk/reward floor', ja: 'リスクリワード下限', th: 'ขั้นต่ำผลตอบแทนต่อความเสี่ยง', vi: 'sàn lợi nhuận/rủi ro', id: 'batas imbal/risiko' },
  add_limit: { ko: '추가 매수 제한', en: 'add limit', ja: '買い増し制限', th: 'จำกัดการเพิ่มไม้', vi: 'giới hạn gia tăng', id: 'batas penambahan' },
  confidence_rank: { ko: '신뢰도 순위', en: 'confidence rank', ja: '信頼度ランク', th: 'อันดับความเชื่อมั่น', vi: 'xếp hạng tin cậy', id: 'peringkat keyakinan' },
  desk_retire: { ko: '슬롯 반납', en: 'desk retire', ja: 'スロット返却', th: 'คืนสล็อต', vi: 'trả lại suất', id: 'lepas slot' },
  master_hold: { ko: '마스터 정지', en: 'master hold', ja: 'マスター停止', th: 'หยุดด้วยสวิตช์หลัก', vi: 'giữ bằng công tắc tổng', id: 'tahan sakelar utama' },
  flatten: { ko: '포지션 정리', en: 'flatten', ja: 'ポジション解消', th: 'ปิดสถานะทั้งหมด', vi: 'đóng hết vị thế', id: 'tutup semua posisi' },
  error: { ko: '오류', en: 'error', ja: 'エラー', th: 'ข้อผิดพลาด', vi: 'lỗi', id: 'kesalahan' },
}

function stageLabel(stage: string | undefined, lang: Language): string {
  if (!stage) return ''
  return STAGE_TEXT[stage] ? tr(lang, STAGE_TEXT[stage]) : stage
}

// The event log's type column, and the card's fallback line. A raw
// 'gate_skip' is a field name, not a word. All thirteen types prod actually
// journals are here (counted 2026-08-07) — the six diagnostic ones matter as
// much as the rest, because the card shows the newest NON-equity event and
// `order_params` alone is as frequent as `decision`.
const EVENT_TYPE_TEXT: Record<string, Record<Language, string>> = {
  decision: { ko: '판단', en: 'decision', ja: '判断', th: 'การตัดสินใจ', vi: 'quyết định', id: 'keputusan' },
  trade: { ko: '체결', en: 'trade', ja: '約定', th: 'การเทรด', vi: 'khớp lệnh', id: 'transaksi' },
  gate_skip: { ko: '보류', en: 'skipped', ja: '見送り', th: 'ข้าม', vi: 'bỏ qua', id: 'dilewati' },
  run_status: { ko: '상태 변경', en: 'status', ja: '状態変更', th: 'สถานะ', vi: 'trạng thái', id: 'status' },
  equity: { ko: '평가액', en: 'equity', ja: '評価額', th: 'มูลค่าพอร์ต', vi: 'giá trị', id: 'ekuitas' },
  alert: { ko: '알림', en: 'alert', ja: '通知', th: 'แจ้งเตือน', vi: 'cảnh báo', id: 'notifikasi' },
  margin: { ko: '증거금', en: 'margin', ja: '証拠金', th: 'มาร์จิ้น', vi: 'ký quỹ', id: 'margin' },
  order_params: { ko: '주문 설계', en: 'order design', ja: '注文設計', th: 'การออกแบบคำสั่ง', vi: 'thiết kế lệnh', id: 'desain order' },
  order_intent: { ko: '주문 의도', en: 'order intent', ja: '注文の意図', th: 'เจตนาคำสั่ง', vi: 'ý định lệnh', id: 'maksud order' },
  adapt: { ko: '전략 조정', en: 'adaptation', ja: '戦略調整', th: 'การปรับกลยุทธ์', vi: 'điều chỉnh chiến lược', id: 'penyesuaian strategi' },
  hot_issue: { ko: '긴급 이슈', en: 'hot issue', ja: '緊急イシュー', th: 'ประเด็นเร่งด่วน', vi: 'vấn đề nóng', id: 'isu mendesak' },
  thesis_review: { ko: '논지 점검', en: 'thesis review', ja: '仮説の点検', th: 'ทบทวนแนวคิด', vi: 'rà soát luận điểm', id: 'tinjauan tesis' },
  armed_exit: { ko: '예약 청산', en: 'armed exit', ja: '予約決済', th: 'ตั้งปิดสถานะไว้', vi: 'lệnh thoát đã đặt', id: 'keluar terjadwal' },
}

function eventTypeLabel(kind: string, lang: Language): string {
  return EVENT_TYPE_TEXT[kind] ? tr(lang, EVENT_TYPE_TEXT[kind]) : kind
}

const CONF_LABEL: Record<Language, string> = {
  ko: '신뢰도', en: 'conf', ja: '信頼度', th: 'ความเชื่อมั่น', vi: 'độ tin cậy', id: 'keyakinan',
}

const TOTAL_LABEL: Record<Language, string> = {
  ko: '총액', en: 'total', ja: '合計', th: 'รวม', vi: 'tổng', id: 'total',
}

// Falls back to the raw reason so a newly-added backend reason still shows
// something actionable instead of silently disappearing.
export function reasonLabel(reason: string | undefined, lang: Language): string {
  if (!reason) return ''
  return REASON_TEXT[reason] ? tr(lang, REASON_TEXT[reason]) : reason
}

function ageLabel(ts: string | undefined, lang: Language): string {
  if (!ts) return tr(lang, { ko: '대기', en: 'idle', ja: '待機', th: 'ว่าง', vi: 'chờ', id: 'menganggur' })
  const secs = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000)
  if (secs < 60) return `${Math.round(secs)}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  return `${Math.round(secs / 3600)}h`
}

// The card's rotating "what am I doing right now" line (advanced every 3s by
// the section heartbeat). A running box must never read as static: it cycles
// through the next-cycle countdown, the live mark it is watching, and the
// last non-equity event — whatever this run actually has.
function activityLines(run: Run, tick: any, events: any[],
                       lang: Language): string[] {
  const lines: string[] = []
  const iv = Number((run as any).config?.interval_minutes ?? 60) * 60000
  const last = run.last_cycle_at ? new Date(run.last_cycle_at).getTime() : 0
  if (last) {
    const mins = Math.ceil(Math.max(0, last + iv - Date.now()) / 60000)
    lines.push(mins <= 0
      ? tr(lang, { ko: '🧠 AI 분석 사이클 임박', en: '🧠 AI analysis due now',
          ja: '🧠 AI分析まもなく', th: '🧠 ใกล้รอบวิเคราะห์ AI', vi: '🧠 sắp tới chu kỳ AI', id: '🧠 Analisis AI dijadwalkan sekarang' })
      : tr(lang, { ko: `🧠 다음 AI 분석까지 ${mins}분`, en: `🧠 next AI analysis in ${mins}m`,
          ja: `🧠 次のAI分析まで${mins}分`, th: `🧠 วิเคราะห์ AI ครั้งถัดไปใน ${mins} นาที`,
          vi: `🧠 phân tích AI tiếp theo sau ${mins} phút`, id: `🧠 analisis AI berikutnya dalam ${mins} menit` }))
  }
  if (tick && tick.price != null) {
    const p = `$${Number(tick.price).toFixed(2)}`
    lines.push(tr(lang, { ko: `👁 가격 감시 중 — ${p}`, en: `👁 watching price — ${p}`,
      ja: `👁 価格監視中 — ${p}`, th: `👁 เฝ้าดูราคา — ${p}`, vi: `👁 đang theo dõi giá — ${p}`, id: `👁 memantau harga — ${p}` }))
  }
  const lastEv = (events || []).filter((e) => e.event_type !== 'equity').slice(-1)[0]
  if (lastEv) {
    lines.push(`📋 ${summarize(lastEv, lang, false)}`)
  }
  if (!lines.length) {
    lines.push(tr(lang, { ko: '⚙️ 서버에서 실행 중', en: '⚙️ running on the server',
      ja: '⚙️ サーバーで実行中', th: '⚙️ กำลังทำงานบนเซิร์ฟเวอร์', vi: '⚙️ đang chạy trên máy chủ', id: '⚙️ berjalan di server' }))
  }
  return lines
}

// Flash color: the event type decides how the 2s blink reads.
function flashColor(eventType: string): string {
  if (eventType === 'trade') return '#0ca30c'
  if (eventType === 'alert' || eventType === 'gate_skip') return '#eb6834'
  if (eventType === 'decision') return '#2a78d6'
  if (eventType === 'run_status') return '#7a68d8'
  return 'rgba(12,163,12,0.85)'  // equity heartbeat and anything new
}

function fmtPx(v: number | null | undefined): string {
  if (v == null || !isFinite(Number(v))) return '—'
  const n = Number(v)
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 6 : 2 })
}

// Exchange-style live book row for one TRADING card. Position quantity/entry
// only change on trade events (snapshot refetch); the mark rides the WS tick,
// and the section's 1s clock re-renders so value / unrealized P&L move every
// second like a real terminal. Shorts run 1x on full collateral, so the
// synthetic liquidation sits at exactly 2× entry (run_engine._evaluate_stop).
function BookBlock({ run, snap, tick, lang, liqDefense }: {
  run: Run; snap: any; tick: any; lang: Language; liqDefense?: any
}) {
  const L = {
    qty: tr(lang, { ko: '수량', en: 'Qty', ja: '数量', th: 'จำนวน', vi: 'KL', id: 'Jml' }),
    entry: tr(lang, { ko: '진입가', en: 'Entry', ja: '進入価格', th: 'ราคาเข้า', vi: 'Giá vào', id: 'Harga masuk' }),
    mark: tr(lang, { ko: '마크가', en: 'Mark', ja: 'マーク価格', th: 'ราคามาร์ก', vi: 'Giá mark', id: 'Harga pasar' }),
    value: tr(lang, { ko: '평가액', en: 'Value', ja: '評価額', th: 'มูลค่า', vi: 'Giá trị', id: 'Nilai' }),
    upnl: tr(lang, { ko: '미실현', en: 'Unrealized', ja: '含み損益', th: 'ยังไม่รับรู้', vi: 'Chưa chốt', id: 'Belum direalisasi' }),
    realized: tr(lang, { ko: '실현', en: 'Realized', ja: '実現', th: 'รับรู้แล้ว', vi: 'Đã chốt', id: 'Direalisasi' }),
    liq: tr(lang, { ko: '청산가', en: 'Liq. price', ja: '清算価格', th: 'ราคาล้าง', vi: 'Giá thanh lý', id: 'Harga likuidasi' }),
    margin: tr(lang, { ko: '담보', en: 'Collateral', ja: '担保', th: 'หลักประกัน', vi: 'Ký quỹ', id: 'Jaminan' }),
    long: tr(lang, { ko: '롱', en: 'LONG', ja: 'ロング', th: 'ลอง', vi: 'LONG', id: 'LONG' }),
    short: tr(lang, { ko: '숏', en: 'SHORT', ja: 'ショート', th: 'ชอร์ต', vi: 'SHORT', id: 'SHORT' }),
    isolated: tr(lang, { ko: '격리 1배', en: 'isolated 1x', ja: '分離 1倍', th: 'แยก 1x', vi: 'cô lập 1x', id: 'terisolasi 1x' }),
    flat: tr(lang, { ko: '포지션 없음 — 현금 대기', en: 'No position — holding cash',
      ja: 'ポジションなし — 現金待機', th: 'ไม่มีสถานะ — ถือเงินสด', vi: 'Không vị thế — giữ tiền mặt', id: 'Tidak ada posisi — memegang kas' }),
    trades: tr(lang, { ko: '거래', en: 'trades', ja: '取引', th: 'ดีล', vi: 'lệnh', id: 'transaksi' }),
    defense: tr(lang, { ko: '청산 방어', en: 'Liq. defense', ja: '清算防御', th: 'ป้องกันการล้าง', vi: 'Phòng vệ thanh lý', id: 'Pertahanan likuidasi' }),
    health: tr(lang, { ko: '건전도', en: 'health', ja: '健全度', th: 'สุขภาพ', vi: 'sức khỏe', id: 'kesehatan' }),
    toLiq: tr(lang, { ko: '청산까지', en: 'to liq', ja: '清算まで', th: 'ถึงล้าง', vi: 'đến TL', id: 'ke likuidasi' }),
    noLev: tr(lang, { ko: '레버리지 노출 없음 — 방어 불필요', en: 'no leveraged exposure',
      ja: 'レバレッジ無し', th: 'ไม่มีเลเวอเรจ', vi: 'không có đòn bẩy', id: 'tanpa leverage' }),
    reflexArmed: tr(lang, { ko: '반사 무장', en: 'reflex armed', ja: 'リフレックス作動', th: 'พร้อมรีเฟล็กซ์', vi: 'phản xạ sẵn sàng', id: 'refleks siap' }),
  }
  const mono: React.CSSProperties = {
    fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace',
    fontVariantNumeric: 'tabular-nums' }
  const lbl: React.CSSProperties = { color: 'var(--text-muted,#a89f92)' }
  const realized = Number(snap?.pnl?.realized ?? 0)
  const trades = Number(snap?.pnl?.trades ?? 0)
  const stops = (run as any).stop_conditions || {}
  const pos = snap?.position
  const qtySigned = pos ? Number(pos.quantity || 0) : 0

  // Liquidation Defense Daemon (Plan 16) readout — the daemon's latest
  // margin_state for this run, streamed as `margin` events. Present only for a
  // leveraged position (spot/cash books cannot be liquidated). tier T0/T1 =
  // nominal, T2 = defend, T3 = auto-flatten (reflex).
  const def = liqDefense && typeof liqDefense === 'object' ? liqDefense : null
  const tier: string | undefined = def?.tier
  const tierColor = tier === 'T3' ? '#d03b3b' : tier === 'T2' ? '#e08a1e' : '#0ca30c'
  const dHealth = def?.health != null ? Number(def.health) : null
  const dTtl = def?.ttl_hours != null ? Number(def.ttl_hours) : null
  const dLiq = def?.liq_price != null ? Number(def.liq_price) : null
  const kv = (label: string, val: React.ReactNode) => (
    <span style={{ whiteSpace: 'nowrap' }}><span style={lbl}>{label} </span>{val}</span>
  )
  const defenseItem = (
    <div style={{ ...mono, fontSize: 10, marginTop: 4, padding: '4px 8px',
      borderRadius: 7, background: 'var(--bg-secondary,rgba(0,0,0,0.04))',
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
      border: tier === 'T2' || tier === 'T3' ? `1px solid ${tierColor}` : '1px solid transparent' }}>
      <span style={{ whiteSpace: 'nowrap' }}><span style={lbl}>🛡 </span>{L.defense}</span>
      {def ? (<>
        <b style={{ color: tierColor }}>{tier}</b>
        {dHealth != null && kv(L.health, `${(dHealth * 100).toFixed(1)}%`)}
        {dTtl != null && kv(L.toLiq, `~${dTtl < 100 ? dTtl.toFixed(1) : '99+'}h`)}
        {dLiq != null && kv(L.liq, fmtPx(dLiq))}
      </>) : (<span style={lbl}>· {L.noLev}</span>)}
    </div>
  )

  if (!pos || Math.abs(qtySigned) < 1e-12) {
    return (
      <>
      <div style={{ ...mono, fontSize: 10.5, marginTop: 6, padding: '5px 8px',
        borderRadius: 7, background: 'var(--bg-secondary,rgba(0,0,0,0.04))',
        display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span style={lbl}>{L.flat}</span>
        <span>
          <span style={lbl}>{L.realized} </span>
          <span style={{ color: realized > 0 ? '#0ca30c' : realized < 0 ? '#d03b3b' : 'inherit' }}>
            {realized >= 0 ? '+' : ''}{realized.toFixed(2)}</span>
          <span style={lbl}> · {trades} {L.trades}</span>
        </span>
      </div>
      {defenseItem}
      </>
    )
  }

  const short = qtySigned < 0
  const qty = Math.abs(qtySigned)
  const entry = Number(pos.entry_price || 0)
  const mark = tick && tick.price != null ? Number(tick.price)
    : pos.current_price != null ? Number(pos.current_price) : null
  const value = mark != null ? qty * mark : null
  const upnl = mark != null ? (short ? entry - mark : mark - entry) * qty : null
  const upnlPct = upnl != null && entry * qty > 0 ? (upnl / (entry * qty)) * 100 : null
  const upnlColor = (upnl ?? 0) > 0 ? '#0ca30c' : (upnl ?? 0) < 0 ? '#d03b3b' : 'inherit'
  const cell = (label: string, val: React.ReactNode) => (
    <span style={{ whiteSpace: 'nowrap' }}><span style={lbl}>{label} </span>{val}</span>
  )
  return (
    <>
    <div style={{ ...mono, fontSize: 10.5, marginTop: 6, padding: '6px 8px',
      borderRadius: 7, background: 'var(--bg-secondary,rgba(0,0,0,0.04))',
      display: 'flex', flexDirection: 'column', gap: 3 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span>
          <b style={{ color: short ? '#d03b3b' : '#0ca30c' }}>{short ? L.short : L.long}</b>
          {short && <span style={{ ...lbl, marginLeft: 5 }}>{L.isolated}</span>}
          <span style={{ marginLeft: 8 }}>{cell(L.qty, qty.toFixed(qty < 1 ? 6 : 4))}</span>
        </span>
        {cell(L.value, value != null ? `$${fmtPx(value)}` : '—')}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        {cell(L.entry, fmtPx(entry))}
        {cell(L.mark, <span style={{ color: upnlColor }}>{fmtPx(mark)}</span>)}
        {short ? cell(L.liq, fmtPx(entry * 2)) : null}
        {short ? cell(L.margin, `$${fmtPx(entry * qty)}`) : null}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        {cell(L.upnl, (
          <span style={{ color: upnlColor }}>
            {upnl != null ? `${upnl >= 0 ? '+' : ''}${upnl.toFixed(2)}` : '—'}
            {upnlPct != null ? ` (${upnlPct >= 0 ? '+' : ''}${upnlPct.toFixed(2)}%)` : ''}
          </span>
        ))}
        {cell(L.realized, (
          <span style={{ color: realized > 0 ? '#0ca30c' : realized < 0 ? '#d03b3b' : 'inherit' }}>
            {realized >= 0 ? '+' : ''}{realized.toFixed(2)}</span>
        ))}
        <span style={{ whiteSpace: 'nowrap' }}>
          <span style={lbl}>TP </span>
          <span style={{ color: '#0ca30c' }}>{stops.profit_target_usd != null ? `+$${Number(stops.profit_target_usd)}` : '—'}</span>
          <span style={lbl}> SL </span>
          <span style={{ color: '#d03b3b' }}>{stops.max_loss_usd != null ? `−$${Number(stops.max_loss_usd)}` : '—'}</span>
        </span>
      </div>
    </div>
    {defenseItem}
    </>
  )
}

// The whole live-runs experience (grid + create + detail drawer), embeddable:
// /automation renders it as its primary section (embedded), while the old
// /runs/live route now redirects there. `reloadKey` lets a parent force a
// reload after it creates a run out-of-band.
//
// /automation drives the create modal from its own "Make by New Trading"
// button, so it hides the section's button (`hideCreateButton`) and bumps
// `openCreateSignal` to open the modal. The modal stays here on purpose — it
// owns the structured-409 conflict flow, which the parent would otherwise have
// to reimplement. `extraPanel` hangs additional creation UI off the same modal.
export function RunsLiveSection({ token, embedded = false, reloadKey = 0,
  hideCreateButton = false, hideCreateForm = false, openCreateSignal = 0,
  extraPanel, openRunRequest }: {
  token?: string | null; embedded?: boolean; reloadKey?: number
  hideCreateButton?: boolean; openCreateSignal?: number; extraPanel?: React.ReactNode
  // Hide the manual TRADING form in CREATE mode (Henry, 2026-08-02) — the
  // modal then offers only extraPanel's delegation modes. Re-configuring an
  // existing draft still shows the form; that flow has no other editor.
  hideCreateForm?: boolean
  // Parent-driven "open this run's detail drawer" (the fleet monitor's member
  // cards use it). Nonce-keyed like openCreateSignal so the same run can be
  // reopened after the drawer is closed.
  openRunRequest?: { id: number; nonce: number } | null
}) {
  const { language } = useLanguage()
  const [runs, setRuns] = useState<Run[]>([])
  const [equityByRun, setEquityByRun] = useState<Record<number, number[]>>({})
  // Latest liquidation-defense margin_state per run (Plan 16), seeded from the
  // REST event history and appended from the live stream — same pattern as
  // equity above. Only leveraged positions emit `margin` events.
  const [liqByRun, setLiqByRun] = useState<Record<number, any>>({})
  const [selected, setSelected] = useState<number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  // Id of the draft being re-configured. It opens the same modal as create,
  // seeded from the run — null means the modal is in create mode.
  const [editRunId, setEditRunId] = useState<number | null>(null)
  const [err, setErr] = useState('')
  // Which lifecycle action is in flight, as `${runId}:${key}` — drives the
  // pressed-button spinner and disables the drawer's action row. Without it
  // a click had NO visible reaction until the next poll (and errors rendered
  // BEHIND the drawer, so failures looked like dead buttons).
  const [acting, setActing] = useState<string | null>(null)
  // Structured start conflict (409 with resolvable position/rules) — rendered
  // as a modal offering one-click "close position + disable rules, then start".
  const [conflict, setConflict] = useState<{
    runId: number; message: string
    conflicts: { position: any; rule_ids: number[] }
  } | null>(null)

  const auth = useMemo(() => ({ 'Content-Type': 'application/json',
    Authorization: `Bearer ${token}` }), [token])

  const load = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/runs`, { headers: auth })
      if (r.ok) setRuns((await r.json()).runs || [])
    } catch { /* transient */ }
  }, [token, auth])

  useEffect(() => { load() }, [load, reloadKey])
  // Parent-driven open. 0 is the "never asked" value, so it never fires on mount.
  useEffect(() => { if (openCreateSignal > 0) setShowCreate(true) }, [openCreateSignal])
  useEffect(() => {
    if (openRunRequest && openRunRequest.nonce > 0) setSelected(openRunRequest.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRunRequest?.nonce])
  useEffect(() => {
    const id = setInterval(load, 20000)  // low-frequency reconcile; WS carries live
    return () => clearInterval(id)
  }, [load])

  // Finished TRADINGs stay OFF the board (Henry 2026-07-21) — the grid is a
  // live monitor, not an archive. They remain one click away behind the
  // counter toggle, because a protective stop's reason (max_loss, liquidation)
  // must stay findable.
  const [showStopped, setShowStopped] = useState(false)
  // (?) on every TRADING card — owner report: members can't decode the card's
  // trader shorthand (45m, ≥50%, 마크가, 격리, TP/SL…). One shared field guide.
  const [showCardGuide, setShowCardGuide] = useState(false)
  const stoppedCount = useMemo(
    () => runs.filter((r) => r.status === 'stopped').length, [runs])

  // Allocated-but-inert capital. `permanent` is the only class worth a banner:
  // a closed market reopens on its own, a dead thesis never does.
  const blockedRuns = useMemo(
    () => runs.filter((r) => r.capability?.permanent), [runs])
  const blockedCapital = useMemo(
    () => blockedRuns.reduce((s, r) => s + Number(r.capability?.capital_usd || 0), 0),
    [blockedRuns])
  const [releasing, setReleasing] = useState(false)
  const releaseBlocked = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setReleasing(true)
    try {
      // Sequential, not Promise.all: each stop frees a fleet slot and the
      // supervisor rebuilds against live state — firing them together races
      // the replacement path onto stale slot bookkeeping.
      for (const r of blockedRuns) {
        // confirm_early is required while the thesis horizon is unelapsed —
        // the guard exists so a stop does not realize the current mark instead
        // of letting the thesis resolve. Neither applies here: the run never
        // opened a position and never could, so there is nothing to realize
        // and no thesis left to wait on. Clicking Release IS the acknowledgement.
        await fetch(`${API_BASE}/runs/${r.id}/stop`, {
          method: 'POST',
          headers: { ...auth, 'Content-Type': 'application/json' },
          body: JSON.stringify({ flatten: true, confirm_early: true }),
        })
      }
      await load()
    } finally { setReleasing(false) }
  }
  const visibleRuns = useMemo(
    () => (showStopped ? runs : runs.filter((r) => r.status !== 'stopped')),
    [runs, showStopped])

  // The fleet monitor box above this grid no longer re-lists its members as
  // cards (owner: "the same trading showed twice"). This grid is the single
  // per-run surface; fleet members are grouped under a 🚀 divider so the
  // fleet context survives the merge.
  type RunDivider = { dividerKey: string; dividerLabel: string }
  const displayRuns = useMemo<(Run | RunDivider)[]>(() => {
    const fleets = new Map<number, Run[]>()
    const solo: Run[] = []
    for (const r of visibleRuns) {
      const fid = (r as any).fleet_id
      if (fid) { const a = fleets.get(fid) || []; a.push(r); fleets.set(fid, a) }
      else solo.push(r)
    }
    if (fleets.size === 0) return visibleRuns
    const out: (Run | RunDivider)[] = []
    for (const [fid, rs] of fleets) {
      out.push({
        dividerKey: `fleet-${fid}`,
        dividerLabel: `🚀 #${fid} · ${tr(language, { ko: '자동 편성 멤버', en: 'Fleet members', ja: '自動編成メンバー', th: 'สมาชิกกองยาน', vi: 'Thành viên fleet', id: 'Anggota fleet' })} (${rs.length})`,
      })
      out.push(...rs)
    }
    if (solo.length > 0) {
      out.push({
        dividerKey: 'solo',
        dividerLabel: tr(language, { ko: '개별 TRADING', en: 'Standalone tradings', ja: '個別トレーディング', th: 'การเทรดเดี่ยว', vi: 'Trading riêng lẻ', id: 'Trading mandiri' }),
      })
      out.push(...solo)
    }
    return out
  }, [visibleRuns, language])

  const activeRunIds = useMemo(
    () => runs.filter((r) => ['armed', 'running', 'paused', 'stopping'].includes(r.status))
      .map((r) => r.id),
    [runs])
  const { connected, eventsByRun, tickByRun } = useRunStream(token || null, activeRunIds, language)

  // seed equity series from snapshots for the grid
  useEffect(() => {
    for (const run of runs) {
      if (equityByRun[run.id]) continue
      fetch(`${API_BASE}/runs/${run.id}/events?limit=500`, { headers: auth })
        .then((r) => (r.ok ? r.json() : { events: [] }))
        .then((d) => {
          const series = (d.events || [])
            .filter((e: any) => e.event_type === 'equity')
            .map((e: any) => Number(e.payload?.total ?? 0))
          setEquityByRun((prev) => ({ ...prev, [run.id]: series.length ? series : [0] }))
          const margins = (d.events || []).filter((e: any) => e.event_type === 'margin')
          if (margins.length) {
            const last = margins[margins.length - 1]
            setLiqByRun((prev) => ({ ...prev, [run.id]: last.payload }))
          }
        })
        .catch(() => { /* transient */ })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs])

  // append live equity events into the grid series
  useEffect(() => {
    setEquityByRun((prev) => {
      const next = { ...prev }
      for (const [ridStr, events] of Object.entries(eventsByRun)) {
        const rid = Number(ridStr)
        const eqs = events.filter((e) => e.event_type === 'equity')
        if (!eqs.length) continue
        const base = prev[rid] || [0]
        const merged = base.concat(eqs.map((e) => Number(e.payload?.total ?? 0)))
        next[rid] = merged.length > 4096 ? merged.slice(merged.length - 4096) : merged
      }
      return next
    })
  }, [eventsByRun])

  // append live margin events into the per-run liquidation-defense state
  useEffect(() => {
    setLiqByRun((prev) => {
      const next = { ...prev }
      for (const [ridStr, events] of Object.entries(eventsByRun)) {
        const margins = events.filter((e) => e.event_type === 'margin')
        if (!margins.length) continue
        next[Number(ridStr)] = margins[margins.length - 1].payload
      }
      return next
    })
  }, [eventsByRun])

  // Liveness. heartbeat advances the per-card activity line every 3s; flash
  // marks a card for 2s whenever one of its events arrives (any type — the
  // blink IS the proof the run is alive, and its color says what happened).
  const [heartbeat, setHeartbeat] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setHeartbeat((n) => n + 1), 3000)
    return () => clearInterval(id)
  }, [])
  // 1s terminal clock — the book's derived fields (value, unrealized, mark)
  // recompute against the latest tick every second, exchange-style.
  const [, setClockTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setClockTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Per-run book snapshot (position + realized). Quantity/entry only move on
  // trades, so seed once per run and refetch when a trade or status event
  // arrives; the per-second motion comes from the WS mark, not from polling.
  const [snapByRun, setSnapByRun] = useState<Record<number, any>>({})
  const fetchSnap = useCallback((rid: number) => {
    fetch(`${API_BASE}/runs/${rid}/snapshot`, { headers: auth })
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => { if (s) setSnapByRun((prev) => ({ ...prev, [rid]: s })) })
      .catch(() => { /* transient */ })
  }, [auth])
  useEffect(() => {
    for (const run of runs) {
      if (!snapByRun[run.id]) fetchSnap(run.id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs])
  const [flash, setFlash] = useState<Record<number,
    { nonce: number; text: string; color: string } | undefined>>({})
  const flashTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})
  const seenEventCount = useRef<Record<number, number>>({})
  useEffect(() => {
    for (const [ridStr, events] of Object.entries(eventsByRun)) {
      const rid = Number(ridStr)
      const prev = seenEventCount.current[rid] || 0
      if (events.length <= prev) continue
      seenEventCount.current[rid] = events.length
      const e = events[events.length - 1]
      setFlash((f) => ({ ...f, [rid]: {
        nonce: (f[rid]?.nonce || 0) + 1,
        text: summarize(e, language, false),
        color: flashColor(e.event_type) } }))
      clearTimeout(flashTimers.current[rid])
      flashTimers.current[rid] = setTimeout(
        () => setFlash((f) => ({ ...f, [rid]: undefined })), 2000)
      // trades / lifecycle changes move the book — refresh that run's snapshot
      const fresh = events.slice(prev)
      if (fresh.some((ev) => ev.event_type === 'trade' || ev.event_type === 'run_status')) {
        fetchSnap(rid)
      }
    }
  }, [eventsByRun, language])
  useEffect(() => () => {  // unmount: drop pending flash timers
    Object.values(flashTimers.current).forEach(clearTimeout)
  }, [])

  async function act(id: number, action: string, body?: any) {
    setErr('')
    setActing(`${id}:${actionKey(action, body)}`)
    try {
      const r = await fetch(`${API_BASE}/runs/${id}/${action}`, {
        method: 'POST', headers: auth,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!r.ok) {
        const detail = (await r.json()).detail
        if (r.status === 409 && detail && typeof detail === 'object' && detail.early_stop) {
          // Plan 15 E2: stopping a thesis run before its horizon realizes the
          // current mark — confirm, then re-send with confirm_early.
          const es = detail.early_stop
          const msg = tr(language, {
            ko: `이 TRADING의 AI 논지 기간이 ${es.remaining_hours}시간 남았습니다. 지금 정지하면 현재 가격으로 손익이 확정됩니다. 그래도 정지할까요?`,
            en: `This TRADING's AI thesis still has ${es.remaining_hours}h to run. Stopping now locks in P&L at the current price. Stop anyway?`,
            ja: `このTRADINGのAI論点はあと${es.remaining_hours}時間残っています。今停止すると現在価格で損益が確定します。停止しますか？`,
            th: `วิทยานิพนธ์ AI ของ TRADING นี้เหลืออีก ${es.remaining_hours} ชม. หยุดตอนนี้จะล็อกกำไร/ขาดทุนที่ราคาปัจจุบัน หยุดหรือไม่?`,
            vi: `Luận điểm AI của TRADING này còn ${es.remaining_hours} giờ. Dừng bây giờ sẽ chốt lãi/lỗ theo giá hiện tại. Vẫn dừng?`, id: `Tesis AI TRADING ini masih punya sisa ${es.remaining_hours} jam. Menghentikannya sekarang mengunci laba rugi pada harga saat ini. Tetap hentikan?`,
          })
          if (window.confirm(msg)) {
            await act(id, action, { ...(body || {}), confirm_early: true })
          }
        } else if (r.status === 409 && detail && typeof detail === 'object' && detail.conflicts
            && (detail.conflicts.position || detail.conflicts.rule_ids?.length)) {
          setConflict({ runId: id, message: detail.message, conflicts: detail.conflicts })
        } else {
          const msg = typeof detail === 'object' ? detail?.message : detail
          setErr(msg || T.actionFailed)
        }
      }
      await load()
    } catch { setErr(T.networkError) }
    finally { setActing(null) }
  }

  async function del(id: number) {
    setErr('')
    setActing(`${id}:delete`)
    try {
      const r = await fetch(`${API_BASE}/runs/${id}`, { method: 'DELETE', headers: auth })
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))).detail
        setErr((typeof detail === 'object' ? detail?.message : detail) || T.actionFailed)
        return
      }
      if (selected === id) setSelected(null)
      await load()
    } catch { setErr(T.networkError) }
    finally { setActing(null) }
  }

  // "AI Automation Master" (the section) and "TRADING" (one box) are product
  // names — they stay verbatim in every locale; the sentences around them do not.
  const T = {
    title: 'AI Automation Master',
    subtitle: tr(language, {
      ko: '각 TRADING은 서버에서 계속 실행됩니다. 목표(익절·최대 거래 횟수)를 채우고 멈추면 같은 설정의 TRADING이 자동으로 이어서 시작됩니다. 가격 갱신 주기 때문에 데이터 나이(⧗)도 함께 확인하세요.',
      en: 'Each TRADING keeps running on the server. When one stops because it reached its goal (profit target or trade limit), a new TRADING with the same settings takes over automatically. Watch the data-age badge (⧗) — polled markets update on an interval.',
      ja: '各 TRADING はサーバーで実行され続けます。目標（利確・最大取引回数）に達して停止すると、同じ設定の TRADING が自動的に引き継ぎます。ポーリング市場のためデータ経過時間（⧗）にも注意。',
      th: 'แต่ละ TRADING ทำงานต่อเนื่องบนเซิร์ฟเวอร์ เมื่อหยุดเพราะถึงเป้าหมาย (เป้ากำไรหรือจำนวนเทรด) TRADING ใหม่ที่ตั้งค่าเหมือนกันจะทำงานต่อทันที ดูอายุข้อมูล (⧗) ด้วย',
      vi: 'Mỗi TRADING chạy liên tục trên máy chủ. Khi dừng vì đạt mục tiêu (chốt lời hoặc giới hạn lệnh), một TRADING mới cùng thiết lập sẽ tiếp quản tự động. Hãy xem nhãn tuổi dữ liệu (⧗).',
      id: 'Setiap TRADING terus berjalan di server. Ketika satu berhenti karena mencapai targetnya (target profit atau batas transaksi), TRADING baru dengan pengaturan yang sama mengambil alih secara otomatis. Perhatikan lencana usia data (⧗) — pasar yang di-polling diperbarui pada interval tertentu.' }),
    newRun: tr(language, { ko: '새 TRADING', en: 'New TRADING', ja: '新しい TRADING',
      th: 'TRADING ใหม่', vi: 'TRADING mới', id: 'TRADING baru' }),
    empty: tr(language, { ko: '아직 TRADING이 없습니다.', en: 'No TRADING yet.',
      ja: 'TRADING はまだありません。', th: 'ยังไม่มี TRADING', vi: 'Chưa có TRADING nào.', id: 'Belum ada TRADING.' }),
    showStopped: tr(language, { ko: '종료된 TRADING 보기', en: 'Show finished TRADINGs',
      ja: '終了した TRADING を表示', th: 'แสดง TRADING ที่จบแล้ว', vi: 'Hiện TRADING đã kết thúc', id: 'Tampilkan TRADING yang selesai' }),
    hideStopped: tr(language, { ko: '종료된 TRADING 숨기기', en: 'Hide finished TRADINGs',
      ja: '終了した TRADING を隠す', th: 'ซ่อน TRADING ที่จบแล้ว', vi: 'Ẩn TRADING đã kết thúc', id: 'Sembunyikan TRADING yang selesai' }),
    blockedTitle: (n: number, usd: number) => tr(language, {
      ko: `TRADING ${n}개 ($${usd.toLocaleString()})가 거래할 수 없습니다`,
      en: `${n} TRADING${n > 1 ? 's' : ''} ($${usd.toLocaleString()}) cannot trade`,
      ja: `TRADING ${n} 件 ($${usd.toLocaleString()}) が取引できません`,
      th: `${n} TRADING ($${usd.toLocaleString()}) เทรดไม่ได้`,
      vi: `${n} TRADING ($${usd.toLocaleString()}) không thể giao dịch`, id: `${n} TRADING ($${usd.toLocaleString()}) tidak dapat bertransaksi` }),
    blockedWhy: tr(language, {
      ko: '목표 이동폭이 수수료를 감당하기에 너무 작아 포지션을 열 수 없습니다. 해제하면 자본이 반환됩니다.',
      en: 'their target move is too small to cover fees, so they can never open a position. Releasing returns the capital.',
      ja: '目標変動幅が手数料に対して小さすぎ、ポジションを開けません。解除すると資金が戻ります。',
      th: 'เป้าการเคลื่อนไหวเล็กเกินกว่าจะคุ้มค่าธรรมเนียม จึงเปิดสถานะไม่ได้ ปล่อยแล้วเงินทุนจะคืนมา',
      vi: 'mức biến động mục tiêu quá nhỏ so với phí nên không thể mở vị thế. Giải phóng sẽ hoàn lại vốn.',
      id: 'target pergerakannya terlalu kecil untuk menutup biaya, sehingga tidak akan pernah bisa membuka posisi. Melepaskannya akan mengembalikan modal.' }),
    releaseAll: tr(language, { ko: '전부 해제', en: 'Release all', ja: 'すべて解除',
      th: 'ปล่อยทั้งหมด', vi: 'Giải phóng tất cả', id: 'Lepaskan semua' }),
    releasing: tr(language, { ko: '해제 중…', en: 'Releasing…', ja: '解除中…',
      th: 'กำลังปล่อย…', vi: 'Đang giải phóng…', id: 'Melepaskan…' }),
    live: tr(language, { ko: '실시간', en: 'live', ja: 'ライブ', th: 'สด', vi: 'trực tiếp', id: 'live' }),
    offline: tr(language, { ko: '오프라인', en: 'offline', ja: 'オフライン', th: 'ออฟไลน์', vi: 'ngoại tuyến', id: 'offline' }),
    actionFailed: tr(language, { ko: '요청을 처리하지 못했습니다.', en: 'That action did not go through.',
      ja: '操作を実行できませんでした。', th: 'ดำเนินการไม่สำเร็จ', vi: 'Thao tác không thành công.', id: 'Tindakan tersebut tidak berhasil.' }),
    networkError: tr(language, { ko: '네트워크 오류 — 연결을 확인한 뒤 다시 시도하세요.',
      en: 'Network error — check your connection and try again.',
      ja: 'ネットワークエラー — 接続を確認して再試行してください。',
      th: 'เครือข่ายผิดพลาด — ตรวจการเชื่อมต่อแล้วลองใหม่',
      vi: 'Lỗi mạng — kiểm tra kết nối rồi thử lại.',
      id: 'Kesalahan jaringan — periksa koneksi Anda dan coba lagi.' }),
  }

  if (!token) {
    return <div className="page"><p className="muted">
      {tr(language, { ko: '에이전트 로그인이 필요합니다.', en: 'Agent login required.',
        ja: 'エージェントログインが必要です。', th: 'ต้องเข้าสู่ระบบ', vi: 'Cần đăng nhập', id: 'Perlu login agen.' })}
    </p></div>
  }

  return (
    <div className={embedded ? undefined : 'page'}
      style={embedded ? undefined : { padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 12, flexWrap: 'wrap' }}>
        <div>
          {embedded
            ? <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)' }}>📈 {T.title}</div>
            : <h1 style={{ margin: 0, fontSize: 22 }}>{T.title}</h1>}
          <p className="muted" style={{ margin: '4px 0 0', maxWidth: 680, fontSize: 13 }}>
            {T.subtitle}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: connected ? '#0ca30c' : '#898781',
            display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 8,
              background: connected ? '#0ca30c' : '#898781', display: 'inline-block' }} />
            {connected ? T.live : T.offline}
          </span>
          {!hideCreateButton && (
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
              + {T.newRun}
            </button>
          )}
        </div>
      </div>

      {err && <div style={{ color: '#d03b3b', marginTop: 10, fontSize: 13 }}>{err}</div>}

      {(showCreate || editRunId !== null) && (
        <div role="dialog" aria-modal="true" aria-label={T.newRun}
          onClick={() => { setShowCreate(false); setEditRunId(null) }}
          // The sticky top nav is z-index 500; at 60 this overlay rendered
          // UNDER it and the nav covered the modal's first ~32px, so the
          // symbol/market row was unreachable. Dialogs must outrank the nav.
          style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
            padding: '32px 24px 24px', overflowY: 'auto' }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ width: '100%', maxWidth: 900, margin: 'auto' }}>
            {(editRunId !== null || !hideCreateForm) && (
              <CreateRunForm token={token}
                // Remount on mode change so the form re-seeds from the run being
                // edited instead of keeping the previous draft's values.
                key={editRunId ?? 'create'}
                editRun={editRunId !== null
                  ? runs.find((r) => r.id === editRunId) : undefined}
                onDone={(startError, conflictInfo) => {
                  setShowCreate(false); setEditRunId(null)
                  if (conflictInfo) setConflict(conflictInfo)
                  else if (startError) setErr(startError)
                  load()
                }}
                onCancel={() => { setShowCreate(false); setEditRunId(null) }}
                language={language} />
            )}
            {extraPanel}
          </div>
        </div>
      )}

      {runs.length === 0 && !showCreate && (
        <p className="muted" style={{ marginTop: 24 }}>{T.empty}</p>
      )}

      {/* Capital that is allocated but cannot act. Silent until it exists, and
          it should normally never exist — the server retires an infeasible run
          on its first cycle. This strip is the receipt when it does. */}
      {blockedRuns.length > 0 && (
        <div style={{ marginTop: 14, padding: '11px 13px', borderRadius: 10,
          border: '1px solid rgba(208,59,59,0.28)', background: 'rgba(208,59,59,0.06)',
          display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 13 }}>⚠</span>
          <span style={{ fontSize: 12.5, lineHeight: 1.5, flex: '1 1 260px' }}>
            <strong>{T.blockedTitle(blockedRuns.length, blockedCapital)}</strong>
            <br />
            <span className="muted">{blockedRuns.map((r) => r.symbol).join(', ')} — {T.blockedWhy}</span>
          </span>
          <button onClick={releaseBlocked} disabled={releasing}
            style={{ fontSize: 12, padding: '6px 12px', borderRadius: 7, cursor: 'pointer',
              border: '1px solid rgba(208,59,59,0.4)', background: 'transparent',
              color: 'var(--text-primary,#2b2b2b)', opacity: releasing ? 0.5 : 1 }}>
            {releasing ? T.releasing : T.releaseAll}
          </button>
        </div>
      )}

      {stoppedCount > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 6, marginTop: 10 }}>
          <button onClick={() => setShowStopped((v) => !v)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              fontSize: 12, color: 'var(--text-muted,#a89f92)' }}>
            {showStopped ? '▾' : '▸'} {showStopped ? T.hideStopped : T.showStopped} ({stoppedCount})
          </button>
          <HelpTip text={tr(language, {
            ko: '목표 달성·수동 정지·손절 등으로 끝난 TRADING의 기록입니다. 펼치면 각 TRADING의 최종 손익과 종료 사유를 확인할 수 있습니다. 괄호 안 숫자는 종료된 TRADING 개수입니다.',
            en: "The record of TRADINGs that have ended — goal reached, stopped manually, or stopped out. Expand it to see each one's final P&L and why it ended. The number in parentheses is how many have finished.",
            ja: '目標達成・手動停止・損切りなどで終了した TRADING の記録です。開くと各 TRADING の最終損益と終了理由を確認できます。括弧内の数字は終了した TRADING の数です。',
            th: 'บันทึกของ TRADING ที่จบแล้ว — ถึงเป้า หยุดเอง หรือโดนตัดขาดทุน กดเปิดเพื่อดูกำไรขาดทุนสุดท้ายและเหตุผลที่จบของแต่ละรายการ ตัวเลขในวงเล็บคือจำนวน TRADING ที่จบแล้ว',
            vi: 'Lịch sử các TRADING đã kết thúc — đạt mục tiêu, dừng thủ công hoặc bị cắt lỗ. Mở ra để xem lãi/lỗ cuối cùng và lý do kết thúc của từng cái. Số trong ngoặc là số TRADING đã kết thúc.',
            id: 'Riwayat TRADING yang telah berakhir — target tercapai, dihentikan manual, atau kena stop. Bentangkan untuk melihat P&L akhir dan alasan berakhirnya masing-masing. Angka dalam kurung adalah jumlah TRADING yang sudah selesai.',
          })} />
        </div>
      )}

      {/* Liveness keyframes — the flash ring restarts per event because the
          overlay is keyed by the flash nonce. */}
      <style>{`
        @keyframes sp-run-flash {
          0% { box-shadow: 0 0 0 2.5px var(--sp-flash-color), 0 0 18px 2px var(--sp-flash-color); }
          70% { box-shadow: 0 0 0 2px var(--sp-flash-color), 0 0 8px 0 transparent; }
          100% { box-shadow: 0 0 0 0 transparent; }
        }
        @keyframes sp-live-pulse { 0%, 100% { opacity: 1 } 50% { opacity: .25 } }
      `}</style>
      <div style={{ display: 'grid', gap: 12, marginTop: 18,
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {displayRuns.map((item) => {
          if ('dividerKey' in item) {
            return (
              <div key={item.dividerKey}
                style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 10, margin: '4px 0 -4px', fontSize: 12.5, fontWeight: 700, color: 'var(--text-secondary,#8a8073)' }}>
                {item.dividerLabel}
                <span style={{ flex: 1, height: 1, background: 'var(--border-color,rgba(0,0,0,0.1))' }} />
              </div>
            )
          }
          const run = item
          const tick = tickByRun[run.id]
          const pnl = Number(run.realized_pnl_usd || 0)
          const pnlColor = pnl > 0 ? '#0ca30c' : pnl < 0 ? '#d03b3b' : 'var(--text-muted,#898781)'
          const ageTs = run.status === 'running' ? (tick?.ts || run.last_cycle_at) : run.last_cycle_at
          const fl = flash[run.id]
          const acts = run.status === 'running'
            ? activityLines(run, tick, eventsByRun[run.id] || [], language) : []
          return (
            <div key={run.id} data-help-zone
              onClick={() => setSelected(run.id)}
              style={{ background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))',
                borderRadius: 12, padding: 14, cursor: 'pointer', position: 'relative' }}>
              {fl && (
                <div key={fl.nonce} style={{ position: 'absolute', inset: 0, borderRadius: 12,
                  pointerEvents: 'none', ['--sp-flash-color' as any]: fl.color,
                  animation: 'sp-run-flash 2s ease-out forwards' }} />
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <strong style={{ fontSize: 15 }}>{run.symbol}
                  <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                    {run.market}{run.market_type === 'futures' ? ' · fut' : ''}</span>
                  {(run as any).fleet_id ? (
                    <span style={{ fontSize: 10.5, marginLeft: 6, padding: '1px 7px', borderRadius: 9,
                      background: 'rgba(194,106,69,0.14)', color: 'var(--accent-primary,#c26a45)' }}>
                      🚀 #{(run as any).fleet_id}</span>
                  ) : null}
                </strong>
                <span style={{ fontSize: 11, fontWeight: 600, display: 'inline-flex',
                  alignItems: 'center', gap: 5,
                  color: STATUS_COLOR[run.status] || '#898781' }}>
                  {run.status === 'running' && (
                    <span style={{ width: 6, height: 6, borderRadius: 6, background: '#0ca30c',
                      display: 'inline-block', animation: 'sp-live-pulse 1.6s ease-in-out infinite' }} />
                  )}
                  {statusLabel(run.status, language)}
                  <GuideBadge onClick={(e) => { e.stopPropagation(); setShowCardGuide(true) }}
                    title={tr(language, CARD_GUIDE.open)}
                    style={{ width: 18, height: 18, borderRadius: 9, padding: 0, fontSize: 11,
                      fontWeight: 700, lineHeight: 1, cursor: 'pointer',
                      border: '1px solid var(--border-color,rgba(0,0,0,0.2))',
                      background: 'transparent', color: 'var(--text-secondary,#8a8073)' }} />
                </span>
              </div>
              {/* A `running` badge on a run that cannot open a position is the
                  single most misleading thing this page can say. The chip sits
                  directly under the status so the two are read together. */}
              {run.capability && CAPABILITY_TEXT[run.capability.state] && (
                <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 10.5, fontWeight: 600, padding: '2px 8px',
                    borderRadius: 9, whiteSpace: 'nowrap',
                    background: run.capability.permanent
                      ? 'rgba(208,59,59,0.14)' : 'rgba(237,161,0,0.16)',
                    color: run.capability.permanent ? '#d03b3b' : '#8a6000' }}>
                    {run.capability.permanent ? '🔴' : '🟡'}{' '}
                    {CAPABILITY_TEXT[run.capability.state][language]}
                  </span>
                  {run.capability.permanent && run.capability.capital_usd ? (
                    <span className="muted" style={{ fontSize: 10.5, fontVariantNumeric: 'tabular-nums' }}>
                      ${Number(run.capability.capital_usd).toLocaleString()}
                    </span>
                  ) : null}
                </div>
              )}
              {/* the reason is the whole answer to "why did this stop?" —
                  never leave a stopped/paused box without it */}
              {['stopped', 'stopping', 'paused'].includes(run.status) && run.status_reason && (
                <div className="muted" style={{ fontSize: 11, marginTop: 4, lineHeight: 1.45 }}>
                  {reasonLabel(run.status_reason, language)}
                </div>
              )}
              {/* Several runs may share a symbol as long as they are different
                  strategies, so the card has to say WHICH strategy this is —
                  these are exactly the fields that tell them apart. Labeled
                  2-col grid (owner ask 2026-08-09 "inside each block,
                  arrange") instead of one run-on line. */}
              {(() => {
                const cfg = (run as any).config || {}
                const lev = Number(cfg.leverage || 1)
                const kv = (label: string, val: string) => (
                  <span style={{ display: 'flex', justifyContent: 'space-between', gap: 8, minWidth: 0 }}>
                    <span style={{ color: 'var(--text-muted,#a89f92)', whiteSpace: 'nowrap' }}>{label}</span>
                    <span style={{ color: 'var(--text-secondary,#8a8073)', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{val}</span>
                  </span>
                )
                return (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 10px',
                    marginTop: 6, fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
                    {/* label wording mirrors the create form ('최대 베팅($)',
                        '주기(분)', '유형') so the card and the form that made
                        it read as one */}
                    {kv(tr(language, { ko: '최대 베팅', en: 'Max bet', ja: '最大', th: 'สูงสุด', vi: 'Cược tối đa', id: 'Taruhan maks' }),
                      `$${cfg.max_bet_usd ?? 500}`)}
                    {kv(tr(language, { ko: '주기', en: 'Interval', ja: '間隔', th: 'ช่วง', vi: 'Chu kỳ', id: 'Interval' }),
                      `${cfg.interval_minutes ?? 60}m·≥${Math.round((cfg.min_confidence ?? 0.65) * 100)}%`)}
                    {kv(tr(language, { ko: '유형', en: 'Type', ja: 'タイプ', th: 'ชนิด', vi: 'Loại', id: 'Jenis' }),
                      `${run.market_type === 'futures' ? 'futures' : 'spot'}${lev > 1 ? `·${lev}×` : ''}`)}
                    {kv('AI', String(cfg.provider ||
                      tr(language, { ko: '서버 기본값', en: 'server default', ja: 'サーバー既定', th: 'ค่าเริ่มต้นเซิร์ฟเวอร์', vi: 'mặc định máy chủ', id: 'bawaan server' })))}
                  </div>
                )
              })()}
              {/* what it's doing RIGHT NOW — rotates every 3s; an arriving
                  event takes the line over for its 2s flash */}
              {run.status === 'running' && (
                <div style={{ fontSize: 11, marginTop: 5, minHeight: 15,
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: fl ? fl.color : 'var(--text-secondary,#8a8073)',
                  fontWeight: fl ? 600 : 400 }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {fl ? `⚡ ${fl.text}` : acts[heartbeat % acts.length]}
                  </span>
                </div>
              )}
              {/* live book — the contract/holding state of this run's tuple */}
              <BookBlock run={run} snap={snapByRun[run.id]} liqDefense={liqByRun[run.id]}
                tick={run.status === 'running' ? tick : null} lang={language} />
              <div style={{ marginTop: 8 }}>
                <RunSparkline values={equityByRun[run.id] || [0]}
                  color={pnl < 0 ? 'rgb(208,59,59)' : 'rgb(12,163,12)'} height={44} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                alignItems: 'center', marginTop: 8, fontSize: 12 }}>
                <span style={{ color: pnlColor, fontWeight: 600 }}>
                  {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>
                <span className="muted" title="last data update"
                  style={{ fontSize: 11 }}>⧗ {ageLabel(ageTs, language)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Card field guide, opened by the (?) on any card. z 600 + 32px top
          padding: dialogs must outrank the z-500 sticky nav. */}
      {showCardGuide && (
        <div role="dialog" aria-modal="true" aria-label={tr(language, CARD_GUIDE.title)}
          onClick={() => setShowCardGuide(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
            padding: '32px 24px 24px', overflowY: 'auto' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: '100%', maxWidth: 640, margin: 'auto', background: 'var(--bg-card,#fff)',
              border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ fontSize: 16, fontWeight: 800 }}>💡 {tr(language, CARD_GUIDE.title)}</div>
              <button onClick={() => setShowCardGuide(false)} aria-label="close"
                style={{ marginLeft: 'auto', border: 'none', background: 'transparent',
                  color: 'var(--text-secondary,#8a8073)', fontSize: 18, cursor: 'pointer', lineHeight: 1 }}>
                ✕
              </button>
            </div>
            {CARD_GUIDE.rows.map((r, i) => (
              <div key={i} style={{ padding: '9px 0',
                borderTop: i > 0 ? '1px solid var(--border-color,rgba(0,0,0,0.07))' : 'none' }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 3,
                  fontVariantNumeric: 'tabular-nums' }}>{tr(language, r.term)}</div>
                <div style={{ fontSize: 12.5, lineHeight: 1.55,
                  color: 'var(--text-secondary,#5f574c)' }}>{tr(language, r.desc)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selected !== null && (
        <RunDetail runId={selected} token={token}
          events={eventsByRun[selected] || []}
          tick={tickByRun[selected]}
          onClose={() => setSelected(null)}
          onAct={act} onDelete={del} language={language}
          acting={acting} err={err}
          onEdit={(id) => { setSelected(null); setEditRunId(id) }} />
      )}

      {conflict && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 600 }}>
          <div style={{ width: 'min(440px, calc(100% - 32px))', background: 'var(--bg-card,#fff)',
            border: '1px solid var(--border-color,rgba(0,0,0,0.15))', borderRadius: 12,
            padding: 20 }}>
            <strong style={{ fontSize: 15 }}>
              {tr(language, { ko: '시작 차단 — 해결 가능한 충돌', en: 'Start blocked — resolvable conflicts',
                ja: '開始ブロック — 解決可能な競合', th: 'เริ่มไม่ได้ — ความขัดแย้งที่แก้ได้',
                vi: 'Bị chặn — xung đột có thể xử lý',
                id: 'Mulai terhalang — ada konflik yang dapat diselesaikan' })}
            </strong>
            <ul style={{ margin: '12px 0', paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
              {conflict.conflicts.position && (
                <li>{tr(language, {
                  ko: `이 심볼에 열린 포지션이 있습니다 (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  en: `An open position exists on this symbol (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  ja: `このシンボルに未決済ポジションがあります (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  th: `มีสถานะเปิดอยู่ (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`,
                  vi: `Đang có vị thế mở (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})`, id: `Ada posisi terbuka pada simbol ini (${conflict.conflicts.position.side} ${conflict.conflicts.position.quantity})` })}</li>
              )}
              {conflict.conflicts.rule_ids?.length > 0 && (
                <li>{tr(language, {
                  ko: `자동실행 automation 규칙 ${conflict.conflicts.rule_ids.length}개가 같은 심볼에 켜져 있습니다`,
                  en: `${conflict.conflicts.rule_ids.length} auto-executing automation rule(s) enabled on this symbol`,
                  ja: `同一シンボルで自動実行ルールが${conflict.conflicts.rule_ids.length}件有効です`,
                  th: `กฎอัตโนมัติ ${conflict.conflicts.rule_ids.length} ข้อเปิดอยู่บนสัญลักษณ์นี้`,
                  vi: `${conflict.conflicts.rule_ids.length} quy tắc tự động đang bật trên mã này`, id: `${conflict.conflicts.rule_ids.length} aturan otomatisasi eksekusi-otomatis aktif pada simbol ini` })}</li>
              )}
            </ul>
            <p className="muted" style={{ fontSize: 12, margin: '0 0 14px' }}>
              {tr(language, {
                ko: '런의 손익 귀속을 정확히 유지하려면 런은 항상 빈 포지션에서 시작해야 합니다. 아래 버튼 하나로 포지션을 현재가에 청산하고 규칙을 끈 뒤 바로 시작합니다.',
                en: 'Runs must start flat so run P&L attribution stays honest. One click closes the position at the current mark, disables the rules, and starts the run.',
                ja: 'ランの損益帰属を正確に保つため、ランはフラットな状態から開始する必要があります。ワンクリックで現在値でクローズし、ルールを無効化して開始します。',
                th: 'รันต้องเริ่มจากสถานะว่างเพื่อให้ P&L ถูกต้อง คลิกเดียวเพื่อปิดสถานะ ปิดกฎ แล้วเริ่มรัน',
                vi: 'Phiên phải bắt đầu không vị thế để P&L chính xác. Một cú nhấp sẽ đóng vị thế theo giá hiện tại, tắt quy tắc và bắt đầu.',
                id: 'Run harus dimulai tanpa posisi terbuka agar atribusi laba rugi run tetap jujur. Satu klik akan menutup posisi pada harga pasar saat ini, menonaktifkan aturan, lalu memulai run.' })}
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => setConflict(null)}>
                {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' })}
              </button>
              <button className="btn btn-primary" onClick={() => {
                const id = conflict.runId
                setConflict(null)
                act(id, 'start', { resolve_conflicts: true })
              }}>
                {tr(language, {
                  ko: '청산·규칙 해제 후 시작', en: 'Close & disable, then start',
                  ja: 'クローズ＆無効化して開始', th: 'ปิดสถานะและกฎ แล้วเริ่ม',
                  vi: 'Đóng & tắt, rồi bắt đầu',
                  id: 'Tutup & nonaktifkan, lalu mulai' })}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function RunsLivePage({ token }: Props) {
  return (
    <div className="page" style={{ padding: '20px 24px' }}>
      <RunsLiveSection token={token} />
    </div>
  )
}

function RunDetail({ runId, token, events, tick, onClose, onAct, onDelete, onEdit, language,
  acting, err }: {
  runId: number; token: string; events: any[]; tick: any
  onClose: () => void
  onAct: (id: number, action: string, body?: any) => void
  onDelete: (id: number) => void
  onEdit?: (id: number) => void
  language: Language
  acting?: string | null
  err?: string
}) {
  const [snap, setSnap] = useState<any>(null)
  const auth = { Authorization: `Bearer ${token}` }

  useEffect(() => {
    fetch(`${API_BASE}/runs/${runId}/snapshot`, { headers: auth })
      .then((r) => (r.ok ? r.json() : null)).then(setSnap).catch(() => setSnap(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, events.length])

  const equity = useMemo(() => {
    const base = (snap?.pnl ? [Number(snap.pnl.total || 0)] : [0])
    const live = events.filter((e) => e.event_type === 'equity')
      .map((e) => Number(e.payload?.total ?? 0))
    return base.concat(live)
  }, [snap, events])

  const run = snap?.run
  const status = run?.status
  const canStop = ['armed', 'running', 'paused'].includes(status)
  const log = events.slice().reverse().slice(0, 60)
  // While any lifecycle action is in flight the whole row locks and the
  // pressed button carries the spinner — the click must visibly register.
  const busy = acting != null
  const spin = (key: string) => (acting === `${runId}:${key}` ? '⏳ ' : '')

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.45)', display: 'flex', justifyContent: 'flex-end', zIndex: 600 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(560px, 100%)',
        height: '100%', overflowY: 'auto', background: 'var(--bg-primary,#fff)',
        borderLeft: '1px solid var(--border-color,rgba(0,0,0,0.1))', padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>
            {run ? `${run.symbol} · ${run.market}` : `TRADING #${runId}`}</h2>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        {run && (
          <>
            <div style={{ marginTop: 4, fontSize: 12, color: STATUS_COLOR[status] || '#898781',
              fontWeight: 600 }}>
              {statusLabel(status, language)}
            </div>
            {run.status_reason && (
              <div className="muted" style={{ fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>
                {reasonLabel(run.status_reason, language)}
              </div>
            )}
          </>
        )}

        {snap?.pnl && (
          <div style={{ display: 'flex', gap: 18, marginTop: 12, fontSize: 13 }}>
            <div><span className="muted">P&amp;L </span>
              <strong style={{ color: snap.pnl.total >= 0 ? '#0ca30c' : '#d03b3b' }}>
                {snap.pnl.total >= 0 ? '+' : ''}${Number(snap.pnl.total).toFixed(2)}</strong></div>
            <div><span className="muted">
              {tr(language, { ko: '실현', en: 'realized', ja: '実現', th: 'รับรู้', vi: 'đã chốt', id: 'direalisasi' })} </span>
              ${Number(snap.pnl.realized).toFixed(2)}</div>
            <div><span className="muted">
              {tr(language, { ko: '거래', en: 'trades', ja: '取引', th: 'ดีล', vi: 'lệnh', id: 'transaksi' })} </span>
              {snap.pnl.trades}</div>
            {tick && <div><span className="muted">
              {tr(language, { ko: '현재가', en: 'mark', ja: '価格', th: 'ราคา', vi: 'giá', id: 'harga pasar' })} </span>
              ${Number(tick.price).toFixed(2)}</div>}
          </div>
        )}

        <div style={{ marginTop: 14, background: 'var(--bg-card,#fafafa)',
          border: '1px solid var(--border-color,rgba(0,0,0,0.08))', borderRadius: 10, padding: 8 }}>
          <RunSparkline values={equity}
            color={(snap?.pnl?.total ?? 0) < 0 ? 'rgb(208,59,59)' : 'rgb(12,163,12)'}
            height={120} />
        </div>

        {err && (
          <div style={{ color: '#d03b3b', marginTop: 14, fontSize: 13, lineHeight: 1.5 }}>
            ⚠️ {err}
          </div>
        )}
        {canStop && (
          <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
            {status === 'running' &&
              <button className="btn" disabled={busy} onClick={() => onAct(runId, 'pause')}>
                {spin('pause')}{tr(language, { ko: '일시정지', en: 'Pause', ja: '一時停止', th: 'พัก', vi: 'Tạm dừng', id: 'Jeda' })}</button>}
            {status === 'paused' &&
              <button className="btn" disabled={busy} onClick={() => onAct(runId, 'resume')}>
                {spin('resume')}{tr(language, { ko: '재개', en: 'Resume', ja: '再開', th: 'ต่อ', vi: 'Tiếp tục', id: 'Lanjutkan' })}</button>}
            <button className="btn" style={{ color: '#eb6834' }} disabled={busy}
              onClick={() => onAct(runId, 'stop', { flatten: true })}>
              {spin('stop:flatten')}{tr(language, { ko: '정지+청산', en: 'Stop & flatten', ja: '停止+清算',
                th: 'หยุด+ปิด', vi: 'Dừng + đóng', id: 'Hentikan & tutup posisi' })}</button>
            <button className="btn" disabled={busy}
              onClick={() => onAct(runId, 'stop', { flatten: false })}>
              {spin('stop:hold')}{tr(language, { ko: '정지+보유', en: 'Stop & hold', ja: '停止+保有',
                th: 'หยุด+ถือ', vi: 'Dừng + giữ', id: 'Hentikan & tahan posisi' })}</button>
          </div>
        )}
        {['draft', 'stopped'].includes(status) &&
          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            {status === 'draft' &&
              <button className="btn btn-primary" disabled={busy} onClick={() => onAct(runId, 'start')}>
                {spin('start')}{tr(language, { ko: '시작', en: 'Start', ja: '開始', th: 'เริ่ม', vi: 'Bắt đầu', id: 'Mulai' })}</button>}
            {/* Only a draft can be re-configured. It is also the way out of the
                exclusivity refusal: change the interval, type, confidence or
                provider here and this TRADING can run beside the existing one. */}
            {status === 'draft' && onEdit &&
              <button className="btn" disabled={busy} onClick={() => onEdit(runId)}>
                {tr(language, { ko: '설정 수정', en: 'Edit settings', ja: '設定を編集',
                  th: 'แก้ไขการตั้งค่า', vi: 'Sửa cài đặt', id: 'Ubah pengaturan' })}</button>}
            <button className="btn" style={{ color: '#d03b3b' }} disabled={busy}
              onClick={() => onDelete(runId)}>
              {spin('delete')}{tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa', id: 'Hapus' })}</button>
          </div>}

        <h3 style={{ fontSize: 13, marginTop: 20, marginBottom: 6 }}>
          {tr(language, { ko: '이벤트 로그', en: 'Event log', ja: 'イベントログ',
            th: 'บันทึกเหตุการณ์', vi: 'Nhật ký sự kiện', id: 'Catatan peristiwa' })}</h3>
        <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11.5, lineHeight: 1.7 }}>
          {log.length === 0 && <span className="muted">—</span>}
          {log.map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 8 }}>
              <span className="muted" style={{ minWidth: 62 }}>{e.ts?.slice(11, 19)}</span>
              <span style={{ minWidth: 74, color: e.event_type === 'trade' ? '#0ca30c'
                : e.event_type === 'run_status' ? '#2a78d6' : '#898781' }}>
                {eventTypeLabel(e.event_type, language)}</span>
              <span style={{ opacity: 0.85 }}>{summarize(e, language)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// What a journal row says on the card and in the event log. Every branch has
// to read as a sentence in the reader's language: this line was the last
// English left on the automation page, showing "pre: decision is 'hold'" and
// "buy conf 0.68" under a fully Korean or Thai screen.
//
// The gate_skip REASON is the one part that is not localized here — it is
// English prose from the run engine and arrives already translated on the
// socket (routes_run_stream._event_frame), so its catalogue stays in one
// place instead of being mirrored into TypeScript.
// `raw` is the difference between the two places this is rendered. The event
// LOG is a diagnostic view, so an unrecognised type is worth dumping verbatim
// there. The CARD is not: a JSON blob across the run tile is not a status
// line in any language, and `order_params` — which has no summary sentence
// and never will — is journaled as often as `decision`.
function summarize(e: any, lang: Language, raw = true): string {
  const p = e.payload || {}
  if (e.event_type === 'run_status') {
    const from = statusLabel(p.from, lang) || '—'
    const why = reasonLabel(p.reason, lang)
    return `${from} → ${statusLabel(p.to, lang)}${why ? ` (${why})` : ''}`
  }
  if (e.event_type === 'alert' && p.auto_restart_run_id) {
    return tr(lang, {
      ko: `같은 설정으로 새 TRADING #${p.auto_restart_run_id}을(를) 시작했습니다`,
      en: `Restarted as TRADING #${p.auto_restart_run_id} with the same settings`,
      ja: `同じ設定で TRADING #${p.auto_restart_run_id} を開始しました`,
      th: `เริ่ม TRADING #${p.auto_restart_run_id} ใหม่ด้วยการตั้งค่าเดิม`,
      vi: `Đã khởi động lại thành TRADING #${p.auto_restart_run_id} với cùng thiết lập`, id: `Dimulai ulang sebagai TRADING #${p.auto_restart_run_id} dengan pengaturan yang sama` })
  }
  if (e.event_type === 'alert' && p.stop_reason) return reasonLabel(p.stop_reason, lang)
  if (e.event_type === 'trade') {
    return `${actionLabel(String(p.side || '').toLowerCase(), lang)} ${Number(p.quantity).toFixed(4)} @ $${Number(p.price).toFixed(2)}`
  }
  if (e.event_type === 'decision') {
    const verb = p.action ? actionLabel(String(p.action).toLowerCase(), lang) : '—'
    return `${verb} ${CONF_LABEL[lang]} ${p.confidence ?? '—'}`
  }
  if (e.event_type === 'equity') {
    return `${TOTAL_LABEL[lang]} $${Number(p.total).toFixed(2)}`
  }
  if (e.event_type === 'gate_skip') return `${stageLabel(p.stage, lang)}: ${p.reason}`
  if (e.event_type === 'alert') return p.stop_reason ?? eventTypeLabel(e.event_type, lang)
  return raw ? JSON.stringify(p).slice(0, 80) : eventTypeLabel(e.event_type, lang)
}

function CreateRunForm({ token, onDone, onCancel, language, editRun }: {
  token: string
  onDone: (startError?: string, conflictInfo?: {
    runId: number; message: string
    conflicts: { position: any; rule_ids: number[] }
  }) => void
  onCancel: () => void; language: Language
  // Present when re-configuring a draft instead of creating one. Same form,
  // because an edited draft is validated exactly like a new run — the server
  // takes a full replacement, not a patch.
  editRun?: Run
}) {
  const [f, setF] = useState(() => {
    const c = editRun?.config || {}
    const s = (editRun as any)?.stop_conditions || {}
    return {
      symbol: editRun?.symbol ?? 'BTC',
      market: editRun?.market ?? 'crypto',
      market_type: editRun?.market_type ?? 'spot',
      max_bet_usd: c.max_bet_usd ?? 500,
      interval_minutes: c.interval_minutes ?? 60,
      min_confidence: c.min_confidence ?? 0.65,
      stop_loss_usd: s.max_loss_usd != null ? String(s.max_loss_usd) : '',
      profit_target_usd: s.profit_target_usd != null ? String(s.profit_target_usd) : '',
      report_frequency: 'off', notify_on_trade: false,
    }
  })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  // "AI pick": the model chooses among the ranked candidates and says why.
  // One brief-tier call (see /api/markets/suggest-symbol) — the full analyst
  // pipeline takes 30-90s, which is unusable for a picker. Falls back to the
  // ranking leader when the LLM is unconfigured or unparseable, and the reason
  // line distinguishes the two so the button never implies thinking that did
  // not happen.
  const [picking, setPicking] = useState(false)
  const [pickWhy, setPickWhy] = useState('')

  async function pickTopSymbol() {
    setPicking(true)
    try {
      const r = await fetch(`${API_BASE}/markets/suggest-symbol`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      })
      if (!r.ok) throw new Error(String(r.status))
      const d = await r.json()
      if (!d?.symbol) throw new Error('empty')
      setF((prev) => ({ ...prev, symbol: String(d.symbol) }))
      setPickWhy(d.by_ai && d.reason
        ? `🧠 ${d.reason}`
        : tr(language, {
            ko: '거래량 상위 종목입니다 (AI 응답이 없어 순위로 선택).',
            en: 'Top-ranked by volume (AI was unavailable, so the ranking chose).',
            ja: '出来高上位銘柄です（AI応答がないためランキングで選択）。',
            th: 'อันดับสูงสุดตามปริมาณ (AI ไม่ตอบ จึงใช้การจัดอันดับ)',
            vi: 'Xếp hạng đầu theo khối lượng (AI không phản hồi nên dùng xếp hạng).',
            id: 'Peringkat teratas berdasarkan volume (AI tidak tersedia, jadi peringkat yang memilih).' }))
    } catch {
      setPickWhy(tr(language, {
        ko: '추천을 가져오지 못했습니다 — 직접 선택하세요.',
        en: 'Could not get a suggestion — pick one yourself.',
        ja: '推奨を取得できませんでした — 手動で選択してください。',
        th: 'ขอคำแนะนำไม่สำเร็จ — เลือกเอง',
        vi: 'Không lấy được gợi ý — hãy tự chọn.',
        id: 'Tidak bisa mendapatkan saran — pilih sendiri.' }))
    } finally { setPicking(false) }
  }
  // Submit runs three sequential requests; stage names which one is in flight so
  // the user sees progress instead of a silently disabled button.
  const [stage, setStage] = useState(0)
  const [withReporting, setWithReporting] = useState(false)
  const auth = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  const E = {
    createFailed: editRun
      ? tr(language, { ko: 'TRADING을 수정하지 못했습니다.', en: 'Could not save the TRADING.',
          ja: 'TRADING を保存できませんでした。', th: 'บันทึก TRADING ไม่สำเร็จ',
          vi: 'Không lưu được TRADING.',
          id: 'Tidak dapat menyimpan TRADING.' })
      : tr(language, { ko: 'TRADING을 만들지 못했습니다.', en: 'Could not create the TRADING.',
          ja: 'TRADING を作成できませんでした。', th: 'สร้าง TRADING ไม่สำเร็จ', vi: 'Không tạo được TRADING.', id: 'Tidak dapat membuat TRADING.' }),
    startFailed: tr(language, { ko: 'TRADING을 시작하지 못했습니다.', en: 'Could not start the TRADING.',
      ja: 'TRADING を開始できませんでした。', th: 'เริ่ม TRADING ไม่สำเร็จ', vi: 'Không khởi động được TRADING.', id: 'Tidak dapat memulai TRADING.' }),
    network: tr(language, { ko: '네트워크 오류 — 연결을 확인한 뒤 다시 시도하세요.',
      en: 'Network error — check your connection and try again.',
      ja: 'ネットワークエラー — 接続を確認して再試行してください。',
      th: 'เครือข่ายผิดพลาด — ตรวจการเชื่อมต่อแล้วลองใหม่',
      vi: 'Lỗi mạng — kiểm tra kết nối rồi thử lại.',
      id: 'Kesalahan jaringan — periksa koneksi Anda dan coba lagi.' }),
  }

  async function submit() {
    const reporting = f.report_frequency !== 'off' || f.notify_on_trade
    setErr(''); setBusy(true); setWithReporting(reporting); setStage(1)
    const stop: any = {}
    if (f.stop_loss_usd) stop.max_loss_usd = Number(f.stop_loss_usd)
    if (f.profit_target_usd) stop.profit_target_usd = Number(f.profit_target_usd)
    try {
      // Editing replaces the draft in place; creating makes a new one. Either
      // way the same body, because the edit endpoint takes a full config.
      const r = await fetch(
        editRun ? `${API_BASE}/runs/${editRun.id}` : `${API_BASE}/runs`, {
          method: editRun ? 'PUT' : 'POST', headers: auth,
          body: JSON.stringify({
            symbol: f.symbol, market: f.market, market_type: f.market_type,
            max_bet_usd: Number(f.max_bet_usd),
            interval_minutes: Number(f.interval_minutes),
            min_confidence: Number(f.min_confidence),
            stop_conditions: stop,
          }),
        })
      const d = await r.json()
      if (!r.ok) {
        const msg = typeof d.detail === 'object' ? d.detail?.message : d.detail
        setErr(msg || E.createFailed); setBusy(false); setStage(0); return
      }
      const runId = editRun ? editRun.id : d.id
      if (reporting) {
        setStage(2)
        await fetch(`${API_BASE}/runs/${runId}/reporting`, {
          method: 'PUT', headers: auth,
          body: JSON.stringify({ report_frequency: f.report_frequency,
            notify_on_trade: f.notify_on_trade }),
        })
      }
      // One step: start immediately. A structured 409 (open position and/or a
      // conflicting auto-execute rule) bubbles up so the section can offer
      // one-click resolution; any other refusal leaves the draft in the grid
      // with the reason surfaced at section level.
      let startError: string | undefined
      let conflictInfo
      setStage(3)
      try {
        const s = await fetch(`${API_BASE}/runs/${runId}/start`, { method: 'POST', headers: auth })
        if (!s.ok) {
          const detail = (await s.json().catch(() => null))?.detail
          if (s.status === 409 && detail && typeof detail === 'object' && detail.conflicts
              && (detail.conflicts.position || detail.conflicts.rule_ids?.length)) {
            conflictInfo = { runId, message: detail.message, conflicts: detail.conflicts }
          } else if (typeof detail === 'string') {
            startError = detail
          } else {
            startError = detail?.message || E.startFailed
          }
        }
      } catch { startError = E.network }
      onDone(startError, conflictInfo)
    } catch { setErr(E.network); setBusy(false); setStage(0) }
  }

  const lbl = (o: any) => tr(language, o)
  const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }
  const input: React.CSSProperties = { padding: '6px 8px', borderRadius: 6,
    border: '1px solid var(--border-color,rgba(0,0,0,0.15))', background: 'var(--bg-card,#fff)',
    color: 'var(--text-primary,#111)' }

  return (
    <div style={{ marginTop: 16, background: 'var(--bg-card,#fff)',
      border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 16 }}>
      {/* Title row (owner ask 2026-08-09 "inside each block, arrange"): the
          modal opened straight into bare fields — say what this box is. */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 800 }}>
            {editRun
              ? lbl({ ko: '✏️ TRADING 다시 설정', en: '✏️ Reconfigure TRADING', ja: '✏️ TRADING を再設定', th: '✏️ ตั้งค่า TRADING ใหม่', vi: '✏️ Thiết lập lại TRADING', id: '✏️ Atur ulang TRADING' })
              : lbl({ ko: '➕ 새 TRADING', en: '➕ New TRADING', ja: '➕ 新しい TRADING', th: '➕ TRADING ใหม่', vi: '➕ TRADING mới', id: '➕ TRADING baru' })}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)', marginTop: 2 }}>
            {lbl({ ko: 'AI가 아래 주기·신뢰도·금액대로 스스로 매매를 반복합니다', en: 'The AI cycles on its own with the interval, confidence and size below', ja: 'AIが以下の周期・信頼度・金額で自動売買を繰り返します', th: 'AI จะเทรดซ้ำเองตามรอบ ความมั่นใจ และวงเงินด้านล่าง', vi: 'AI tự lặp lại giao dịch theo chu kỳ, độ tin cậy và mức vốn bên dưới', id: 'AI berputar sendiri dengan interval, keyakinan, dan ukuran di bawah ini' })}
          </div>
        </div>
        <button onClick={onCancel}
          style={{ padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,rgba(0,0,0,0.15))',
            background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>
          {lbl({ ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' })}
        </button>
      </div>
      <div style={{ display: 'grid', gap: 12,
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <label style={field}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'space-between' }}>
            {lbl({ ko: '심볼', en: 'Symbol', ja: 'シンボル', th: 'สัญลักษณ์', vi: 'Mã', id: 'Simbol' })}
            {f.market === 'crypto' && (
              <button type="button" onClick={pickTopSymbol} disabled={picking}
                style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer',
                  fontSize: 11, color: 'var(--accent-primary,#c26a45)', fontWeight: 600 }}>
                🔍 {lbl({ ko: 'AI 추천', en: 'AI pick', ja: 'AI 推奨',
                  th: 'AI แนะนำ', vi: 'AI chọn', id: 'Pilihan AI' })}
              </button>
            )}
          </span>
          <SymbolSelect style={input} market={f.market} value={f.symbol}
            onChange={(symbol) => { setF({ ...f, symbol }); setPickWhy('') }}
            placeholder={lbl({ ko: '종목 선택', en: 'Select symbol', ja: '銘柄を選択',
              th: 'เลือกสัญลักษณ์', vi: 'Chọn mã', id: 'Pilih simbol' })} />
          {pickWhy && <span style={{ fontSize: 10.5, color: 'var(--text-muted,#8a8073)',
            lineHeight: 1.4 }}>{pickWhy}</span>}
        </label>
        <label style={field}>{lbl({ ko: '시장', en: 'Market', ja: '市場', th: 'ตลาด', vi: 'Thị trường', id: 'Pasar' })}
          <select style={input} value={f.market}
            onChange={(e) => setF({ ...f, market: e.target.value, symbol: '',
              market_type: e.target.value === 'crypto' ? f.market_type : 'spot' })}>
            <option value="crypto">crypto</option><option value="us-stock">us-stock</option>
            <option value="forex">forex</option>
            <option value="futures">futures</option>
          </select></label>
        <label style={field}>{lbl({ ko: '유형', en: 'Type', ja: 'タイプ', th: 'ชนิด', vi: 'Loại', id: 'Jenis' })}
          <select style={input} value={f.market_type}
            onChange={(e) => setF({ ...f, market_type: e.target.value })}>
            <option value="spot">spot</option>
            <option value="futures" disabled={f.market !== 'crypto'}>futures</option>
          </select></label>
        <label style={field}>{lbl({ ko: '최대 베팅($)', en: 'Max bet ($)', ja: '最大($)', th: 'เดิมพันสูงสุด', vi: 'Cược tối đa', id: 'Taruhan maks ($)' })}
          <input style={input} type="number" value={f.max_bet_usd}
            onChange={(e) => setF({ ...f, max_bet_usd: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '주기(분)', en: 'Interval (min)', ja: '間隔(分)', th: 'ช่วง(นาที)', vi: 'Chu kỳ (phút)', id: 'Interval (menit)' })}
          <input style={input} type="number" min={5} value={f.interval_minutes}
            onChange={(e) => setF({ ...f, interval_minutes: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '최소 신뢰도', en: 'Min confidence', ja: '最小信頼度', th: 'ความมั่นใจ', vi: 'Độ tin tối thiểu', id: 'Keyakinan min' })}
          <input style={input} type="number" step={0.05} min={0} max={1} value={f.min_confidence}
            onChange={(e) => setF({ ...f, min_confidence: Number(e.target.value) })} /></label>
        <label style={field}>{lbl({ ko: '손절($)', en: 'Stop loss ($)', ja: '損切り($)', th: 'ตัดขาดทุน', vi: 'Cắt lỗ ($)', id: 'Stop loss ($)' })}
          <input style={input} type="number" value={f.stop_loss_usd}
            onChange={(e) => setF({ ...f, stop_loss_usd: e.target.value })} /></label>
        <label style={field}>{lbl({ ko: '익절($)', en: 'Profit target ($)', ja: '利確($)', th: 'เป้ากำไร', vi: 'Chốt lời ($)', id: 'Target profit ($)' })}
          <input style={input} type="number" value={f.profit_target_usd}
            onChange={(e) => setF({ ...f, profit_target_usd: e.target.value })} /></label>
        <label style={field}>{lbl({ ko: '리포트', en: 'Reports', ja: 'レポート', th: 'รายงาน', vi: 'Báo cáo', id: 'Laporan' })}
          <select style={input} value={f.report_frequency}
            onChange={(e) => setF({ ...f, report_frequency: e.target.value })}>
            <option value="off">off</option><option value="hourly">hourly</option>
            <option value="daily">daily</option><option value="weekly">weekly</option>
          </select></label>
        <label style={{ ...field, flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 18 }}>
          <input type="checkbox" checked={f.notify_on_trade}
            onChange={(e) => setF({ ...f, notify_on_trade: e.target.checked })} />
          {lbl({ ko: '체결 알림', en: 'Alert on trade', ja: '取引通知', th: 'แจ้งเมื่อเทรด', vi: 'Báo khi giao dịch', id: 'Peringatan saat transaksi' })}
        </label>
      </div>
      {err && <div style={{ color: '#d03b3b', marginTop: 10, fontSize: 12 }}>{err}</div>}
      <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
        {tr(language, {
          ko: '런은 서버에서 백그라운드로 실행되며 페이퍼(시뮬레이터) 계정으로 체결됩니다. 미국 주식은 가격 갱신 주기 특성상 정지 조건이 수 분 지연될 수 있습니다.',
          en: 'Runs execute server-side on the paper (simulator) account. US-stock stops evaluate on minutes-old marks due to the price-poll interval.',
          ja: 'ランはサーバー側でペーパー口座で執行。米国株は価格ポーリングのため停止条件が数分遅延することがあります。',
          th: 'รันทำงานฝั่งเซิร์ฟเวอร์บนบัญชีจำลอง หุ้นสหรัฐฯ เงื่อนไขหยุดอาจช้าไม่กี่นาที',
          vi: 'Phiên chạy phía máy chủ trên tài khoản mô phỏng. Cổ phiếu Mỹ có thể trễ vài phút do chu kỳ polling giá.',
          id: 'Run dieksekusi di sisi server pada akun paper (simulator). Stop untuk saham AS dievaluasi pada harga yang berusia beberapa menit karena interval polling harga.' })}
      </p>
      {stage > 0 && (
        <ol style={{ listStyle: 'none', margin: '12px 0 0', padding: 0,
          display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
          {[
            [1, editRun
              ? lbl({ ko: '설정 저장', en: 'Saving settings', ja: '設定を保存',
                  th: 'บันทึกการตั้งค่า', vi: 'Lưu cài đặt', id: 'Menyimpan pengaturan' })
              : lbl({ ko: '런 생성', en: 'Creating run', ja: 'ラン作成',
                  th: 'สร้างรัน', vi: 'Tạo phiên chạy', id: 'Membuat run' })],
            ...(withReporting ? [[2, lbl({ ko: '리포트 설정', en: 'Configuring reports',
              ja: 'レポート設定', th: 'ตั้งค่ารายงาน', vi: 'Cấu hình báo cáo', id: 'Mengatur laporan' })]] : []),
            [3, lbl({ ko: '시작', en: 'Starting', ja: '開始', th: 'เริ่ม', vi: 'Bắt đầu', id: 'Memulai' })],
          ].map(([s, label]: any, i) => (
            <li key={s} style={{ display: 'flex', alignItems: 'center', gap: 6,
              opacity: s > stage ? 0.5 : 1 }}>
              <span>{s < stage ? '✅' : s === stage ? '🔄' : '⏳'}</span>
              <span>{i + 1}. {label}</span>
            </li>
          ))}
        </ol>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary" disabled={busy} onClick={submit}>
          {editRun
            ? tr(language, { ko: '▶ 저장하고 시작', en: '▶ Save & start',
                ja: '▶ 保存して開始', th: '▶ บันทึกและเริ่ม', vi: '▶ Lưu & bắt đầu', id: '▶ Simpan & mulai' })
            : tr(language, { ko: '▶ TRADING 만들고 시작', en: '▶ Create & start TRADING',
                ja: '▶ TRADING を作成して開始', th: '▶ สร้างและเริ่ม TRADING',
                vi: '▶ Tạo & bắt đầu TRADING',
                id: '▶ Buat & mulai TRADING' })}</button>
        <button className="btn" onClick={onCancel}>
          {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' })}</button>
      </div>
    </div>
  )
}

export default RunsLivePage
