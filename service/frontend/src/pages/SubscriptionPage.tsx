import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { PLAN_FEATURE_BULLETS, PLAN_NAMES } from '../entitlements'
import { tr } from '../i18n'

// /account/subscription — manage the subscription you already have, on the
// rail you actually paid with (owner decisions 2026-08-05):
//   upgrade  = pay the difference now (manual rails: prorated + admin
//              approval; Stripe: portal)
//   downgrade = takes effect at renewal (manual rails: scheduled on the row)
//   trial    = never prorated — the member paid $0, so upgrades go through
//              the normal first-purchase page at full price.
// /subscribe stays the first-purchase page; this page is for members.

const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 14, padding: '20px 20px' }
const primaryBtn: any = { padding: '9px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 }
const ghostBtn: any = { ...primaryBtn, background: 'transparent', border: '1px solid var(--border-color,#2a2a28)', color: 'inherit' }
const inputStyle: any = { padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-primary,#0e0e0d)', color: 'var(--text-primary,#fff)', fontSize: 13, width: '100%' }
const th: any = { textAlign: 'left', fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted,#8a8073)', padding: '6px 10px', borderBottom: '1px solid var(--border-color,#2a2a28)' }
const td: any = { fontSize: 12.5, padding: '7px 10px', borderBottom: '1px solid var(--border-color,#2a2a28)' }

const MANUAL_METHODS = new Set(['usdt', 'bank', 'manual'])

export default function SubscriptionPage({ userToken }: { userToken: string }) {
  const { language } = useLanguage()
  const [mine, setMine] = useState<any | null>(null)
  const [plans, setPlans] = useState<any[]>([])
  const [avail, setAvail] = useState<{ usdt: boolean; address: string; network: string; bank: string }>({ usdt: false, address: '', network: 'TRC20', bank: '' })
  const [history, setHistory] = useState<{ items: any[]; total: number }>({ items: [], total: 0 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  // Inline change panel: preview result + payment inputs for one target plan.
  const [panel, setPanel] = useState<{ code: string; kind: string; prorated: number; effective: string } | null>(null)
  const [payMethod, setPayMethod] = useState<'usdt' | 'bank'>('bank')
  const [reference, setReference] = useState('')

  const authHdr = { 'Authorization': `Bearer ${userToken}` }

  const T = {
    title: tr(language, { ko: '내 구독', en: 'My subscription', ja: '購読管理', th: 'การสมัครของฉัน', vi: 'Gói của tôi', id: 'Langganan saya' }),
    subtitle: tr(language, { ko: '플랜 확인 · 업그레이드 · 다운그레이드 · 결제 이력', en: 'See your plan, upgrade or downgrade, and review history.', ja: 'プランの確認・アップグレード・ダウングレード・履歴', th: 'ดูแผน อัปเกรดหรือดาวน์เกรด และดูประวัติ', vi: 'Xem gói, nâng/hạ cấp và lịch sử.', id: 'Lihat paket Anda, tingkatkan atau turunkan, dan tinjau riwayat.' }),
    status: tr(language, { ko: '상태', en: 'Status', ja: '状態', th: 'สถานะ', vi: 'Trạng thái', id: 'Status' }),
    method: tr(language, { ko: '결제 수단', en: 'Method', ja: '支払方法', th: 'วิธีชำระ', vi: 'Phương thức', id: 'Metode' }),
    started: tr(language, { ko: '시작일', en: 'Started', ja: '開始日', th: 'เริ่ม', vi: 'Bắt đầu', id: 'Mulai' }),
    expires: tr(language, { ko: '만료일', en: 'Expires', ja: '有効期限', th: 'หมดอายุ', vi: 'Hết hạn', id: 'Berakhir' }),
    renewsAuto: tr(language, { ko: '자동 갱신', en: 'Renews automatically', ja: '自動更新', th: 'ต่ออายุอัตโนมัติ', vi: 'Tự động gia hạn', id: 'Diperpanjang otomatis' }),
    cancelsOn: tr(language, { ko: '해지 예정일', en: 'Cancels on', ja: '解約予定日', th: 'จะยกเลิกวันที่', vi: 'Sẽ hủy vào', id: 'Berakhir pada' }),
    trialNote: tr(language, { ko: '무료 체험 중입니다. 자동 결제는 없으며, 계속 이용하려면 체험 종료 전에 플랜을 구독하세요 — 정가로 새 30일이 시작됩니다.', en: 'You are on the free trial. Nothing is charged automatically — subscribe before it ends to keep going; a plan starts a fresh 30 days at full price.', ja: '無料体験中です。自動課金はありません — 継続するには体験終了前にプランを購読してください。正規価格で新しい30日が始まります。', th: 'คุณอยู่ในช่วงทดลองใช้ฟรี ไม่มีการเรียกเก็บอัตโนมัติ — สมัครก่อนสิ้นสุดเพื่อใช้ต่อ แผนจะเริ่ม 30 วันใหม่ในราคาเต็ม', vi: 'Bạn đang dùng thử miễn phí. Không có khoản phí tự động — hãy đăng ký trước khi hết hạn; gói bắt đầu 30 ngày mới với giá đầy đủ.', id: 'Anda sedang dalam uji coba gratis. Tidak ada tagihan otomatis — berlangganan sebelum berakhir untuk melanjutkan; paket dimulai 30 hari baru dengan harga penuh.' }),
    noSub: tr(language, { ko: '활성 구독이 없습니다.', en: 'No active subscription.', ja: '有効な購読はありません。', th: 'ไม่มีการสมัครที่ใช้งานอยู่', vi: 'Không có gói đang hoạt động.', id: 'Tidak ada langganan aktif.' }),
    goSubscribe: tr(language, { ko: '구독 페이지로', en: 'Go to subscribe', ja: '購読ページへ', th: 'ไปหน้าสมัคร', vi: 'Đến trang đăng ký', id: 'Ke halaman langganan' }),
    ladder: tr(language, { ko: '플랜 변경', en: 'Change plan', ja: 'プラン変更', th: 'เปลี่ยนแผน', vi: 'Đổi gói', id: 'Ganti paket' }),
    current: tr(language, { ko: '현재 플랜', en: 'Current plan', ja: '現在のプラン', th: 'แผนปัจจุบัน', vi: 'Gói hiện tại', id: 'Paket saat ini' }),
    upgrade: tr(language, { ko: '업그레이드', en: 'Upgrade', ja: 'アップグレード', th: 'อัปเกรด', vi: 'Nâng cấp', id: 'Tingkatkan' }),
    downgrade: tr(language, { ko: '다운그레이드', en: 'Downgrade', ja: 'ダウングレード', th: 'ดาวน์เกรด', vi: 'Hạ cấp', id: 'Turunkan' }),
    contactUs: tr(language, { ko: '문의하기', en: 'Contact us', ja: 'お問い合わせ', th: 'ติดต่อเรา', vi: 'Liên hệ', id: 'Hubungi kami' }),
    perMonth: tr(language, { ko: '/월', en: '/month', ja: '/月', th: '/เดือน', vi: '/tháng', id: '/bulan' }),
    payNow: tr(language, { ko: '지금 결제할 차액', en: 'Difference to pay now', ja: '今すぐ支払う差額', th: 'ส่วนต่างที่ต้องจ่ายตอนนี้', vi: 'Khoản chênh lệch trả ngay', id: 'Selisih yang dibayar sekarang' }),
    prorationNote: tr(language, { ko: '남은 기간에 대한 플랜 가격 차액만 결제합니다. 만료일은 그대로 유지됩니다.', en: 'You pay only the plan-price difference for the days left in your period. Your expiry date does not move.', ja: '残り期間分のプラン価格差額のみ支払います。有効期限は変わりません。', th: 'จ่ายเฉพาะส่วนต่างราคาแผนสำหรับวันที่เหลือ วันหมดอายุไม่เปลี่ยน', vi: 'Bạn chỉ trả chênh lệch giá gói cho số ngày còn lại. Ngày hết hạn không đổi.', id: 'Anda hanya membayar selisih harga paket untuk sisa hari periode Anda. Tanggal berakhir tidak berubah.' }),
    approvalNote: tr(language, { ko: '결제 확인 후 관리자가 승인하면 플랜이 즉시 전환됩니다.', en: 'After an administrator confirms the payment, your plan switches immediately.', ja: '管理者が支払いを確認すると、プランは即時に切り替わります。', th: 'หลังผู้ดูแลยืนยันการชำระ แผนของคุณจะเปลี่ยนทันที', vi: 'Sau khi quản trị viên xác nhận thanh toán, gói của bạn đổi ngay.', id: 'Setelah administrator mengonfirmasi pembayaran, paket Anda langsung berganti.' }),
    downgradeNote: tr(language, { ko: '다운그레이드는 결제 없이 예약되며, 현재 기간이 끝날 때 적용됩니다. 그때까지는 지금 플랜의 모든 기능을 그대로 사용합니다.', en: 'A downgrade is scheduled free of charge and takes effect when the current period ends. Until then you keep everything in your current plan.', ja: 'ダウングレードは無料で予約され、現在の期間が終わると適用されます。それまでは現在のプランの全機能を使えます。', th: 'การดาวน์เกรดถูกจองไว้ฟรีและมีผลเมื่อรอบปัจจุบันสิ้นสุด ระหว่างนี้คุณยังใช้ทุกอย่างของแผนปัจจุบันได้', vi: 'Hạ cấp được lên lịch miễn phí và có hiệu lực khi hết chu kỳ hiện tại. Đến lúc đó bạn vẫn giữ mọi thứ của gói hiện tại.', id: 'Penurunan paket dijadwalkan tanpa biaya dan berlaku saat periode berjalan berakhir. Hingga saat itu Anda tetap memakai semua fitur paket sekarang.' }),
    scheduleDowngrade: tr(language, { ko: '다운그레이드 예약', en: 'Schedule downgrade', ja: 'ダウングレードを予約', th: 'จองดาวน์เกรด', vi: 'Lên lịch hạ cấp', id: 'Jadwalkan penurunan' }),
    scheduledBanner: tr(language, { ko: '예약된 다운그레이드', en: 'Scheduled downgrade', ja: '予約済みダウングレード', th: 'ดาวน์เกรดที่จองไว้', vi: 'Hạ cấp đã lên lịch', id: 'Penurunan terjadwal' }),
    cancelSchedule: tr(language, { ko: '예약 취소', en: 'Cancel', ja: '予約取消', th: 'ยกเลิก', vi: 'Hủy lịch', id: 'Batalkan' }),
    pendingBanner: tr(language, { ko: '승인 대기 중인 결제', en: 'Payment awaiting approval', ja: '承認待ちの支払い', th: 'การชำระที่รออนุมัติ', vi: 'Thanh toán chờ duyệt', id: 'Pembayaran menunggu persetujuan' }),
    pendingBody: tr(language, { ko: '확인 후 관리자가 활성화합니다. 잠시 후 다시 확인해 주세요.', en: 'An administrator activates it once the payment is confirmed. Check back soon.', ja: '確認後、管理者が有効化します。しばらくしてからご確認ください。', th: 'ผู้ดูแลจะเปิดใช้งานหลังยืนยันการชำระ โปรดกลับมาดูอีกครั้ง', vi: 'Quản trị viên kích hoạt sau khi xác nhận thanh toán. Vui lòng kiểm tra lại sau.', id: 'Administrator mengaktifkannya setelah pembayaran terkonfirmasi. Silakan cek kembali nanti.' }),
    stripeManage: tr(language, { ko: 'Stripe 포털에서 플랜 변경 · 해지', en: 'Change or cancel in the Stripe portal', ja: 'Stripeポータルで変更・解約', th: 'เปลี่ยนหรือยกเลิกในพอร์ทัล Stripe', vi: 'Đổi hoặc hủy trong cổng Stripe', id: 'Ubah atau batalkan di portal Stripe' }),
    stripeNote: tr(language, { ko: '카드 구독은 Stripe가 차액 정산과 다음 주기 다운그레이드를 자동 처리합니다.', en: 'For card subscriptions Stripe handles proration and next-cycle downgrades automatically.', ja: 'カード購読ではStripeが差額精算と次周期のダウングレードを自動処理します。', th: 'สำหรับสมาชิกบัตร Stripe จัดการส่วนต่างและดาวน์เกรดรอบถัดไปให้อัตโนมัติ', vi: 'Với gói thẻ, Stripe tự xử lý chênh lệch và hạ cấp chu kỳ sau.', id: 'Untuk langganan kartu, Stripe menangani prorata dan penurunan siklus berikutnya secara otomatis.' }),
      changeTo: tr(language, { ko: '이 플랜으로 변경', en: 'Change to this plan', ja: 'このプランへ変更', th: 'เปลี่ยนเป็นแผนนี้', vi: 'Đổi sang gói này', id: 'Ganti ke paket ini' }),
    fullPriceAtSubscribe: tr(language, { ko: '구독 페이지에서 정가로 시작', en: 'Start at full price on the subscribe page', ja: '購読ページで正規価格で開始', th: 'เริ่มราคาเต็มที่หน้าสมัคร', vi: 'Bắt đầu giá đầy đủ ở trang đăng ký', id: 'Mulai dengan harga penuh di halaman langganan' }),
    network: tr(language, { ko: '네트워크', en: 'Network', ja: 'ネットワーク', th: 'เครือข่าย', vi: 'Mạng lưới', id: 'Jaringan' }),
    address: tr(language, { ko: '입금 주소', en: 'Deposit address', ja: '入金アドレス', th: 'ที่อยู่โอน', vi: 'Địa chỉ nhận', id: 'Alamat setor' }),
    copy: tr(language, { ko: '복사', en: 'Copy', ja: 'コピー', th: 'คัดลอก', vi: 'Sao chép', id: 'Salin' }),
    copiedLabel: tr(language, { ko: '복사됨', en: 'Copied', ja: 'コピーしました', th: 'คัดลอกแล้ว', vi: 'Đã sao chép', id: 'Tersalin' }),
    txHash: tr(language, { ko: '트랜잭션 해시 (TxID)', en: 'Transaction hash (TxID)', ja: 'トランザクションハッシュ (TxID)', th: 'แฮชธุรกรรม (TxID)', vi: 'Mã giao dịch (TxID)', id: 'Hash transaksi (TxID)' }),
    bankRef: tr(language, { ko: '이체 참조번호 (보낸 분 성함 등)', en: 'Transfer reference (sender name, memo…)', ja: '振込の参照情報', th: 'ข้อมูลอ้างอิงการโอน', vi: 'Thông tin tham chiếu chuyển khoản', id: 'Referensi transfer (nama pengirim, memo…)' }),
    submitPaid: tr(language, { ko: '결제 완료 — 승인 요청', en: 'I paid — request approval', ja: '支払いました — 承認をリクエスト', th: 'ชำระแล้ว — ขออนุมัติ', vi: 'Đã thanh toán — yêu cầu duyệt', id: 'Saya sudah bayar — ajukan persetujuan' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    payWith: tr(language, { ko: '결제 수단', en: 'Pay with', ja: '支払方法', th: 'ชำระด้วย', vi: 'Thanh toán bằng', id: 'Bayar dengan' }),
    historyTitle: tr(language, { ko: '구독 이력', en: 'History', ja: '購読履歴', th: 'ประวัติ', vi: 'Lịch sử', id: 'Riwayat' }),
    loadMore: tr(language, { ko: '더 보기', en: 'Load more', ja: 'さらに表示', th: 'ดูเพิ่ม', vi: 'Xem thêm', id: 'Muat lagi' }),
    date: tr(language, { ko: '날짜', en: 'Date', ja: '日付', th: 'วันที่', vi: 'Ngày', id: 'Tanggal' }),
    plan: tr(language, { ko: '플랜', en: 'Plan', ja: 'プラン', th: 'แผน', vi: 'Gói', id: 'Paket' }),
    amount: tr(language, { ko: '금액', en: 'Amount', ja: '金額', th: 'จำนวน', vi: 'Số tiền', id: 'Jumlah' }),
    submitted: tr(language, { ko: '요청이 접수되었습니다 — 관리자 승인을 기다립니다.', en: 'Submitted — waiting for administrator approval.', ja: '送信しました — 管理者の承認待ちです。', th: 'ส่งแล้ว — รอผู้ดูแลอนุมัติ', vi: 'Đã gửi — chờ quản trị viên duyệt.', id: 'Terkirim — menunggu persetujuan administrator.' }),
    scheduledOk: tr(language, { ko: '다운그레이드가 예약되었습니다.', en: 'Downgrade scheduled.', ja: 'ダウングレードを予約しました。', th: 'จองดาวน์เกรดแล้ว', vi: 'Đã lên lịch hạ cấp.', id: 'Penurunan terjadwal.' }),
  }

  async function loadAll() {
    try {
      const p = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
      setPlans(p.plans || [])
      setAvail({ usdt: !!p.usdt_available, address: p.usdt_address || '', network: p.usdt_network || 'TRC20', bank: p.bank_transfer_info || '' })
      setPayMethod(p.usdt_available ? 'usdt' : 'bank')
      const m = await fetch(`${API_BASE}/subscriptions/me`, { headers: authHdr }).then(r => r.ok ? r.json() : null)
      setMine(m)
      const h = await fetch(`${API_BASE}/subscriptions/history?limit=20&offset=0`, { headers: authHdr }).then(r => r.ok ? r.json() : null)
      if (h) setHistory(h)
    } catch { /* network */ }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAll() }, [userToken])

  async function loadMore() {
    try {
      const h = await fetch(`${API_BASE}/subscriptions/history?limit=20&offset=${history.items.length}`, { headers: authHdr }).then(r => r.ok ? r.json() : null)
      if (h) setHistory(prev => ({ total: h.total, items: [...prev.items, ...h.items] }))
    } catch { /* network */ }
  }

  const sub = mine?.subscription
  const method: string = sub?.method || ''
  const isTrial = method === 'trial'
  const isManual = MANUAL_METHODS.has(method)
  const currentIdx = plans.findIndex(p => p.code === sub?.plan_code)
  const pendingRow = history.items.find(i => i.status === 'pending')
  const scheduledDowngrade = sub?.change_kind === 'downgrade' && sub?.pending_plan_code

  async function post(path: string, body?: any) {
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        ...(body ? { body: JSON.stringify(body) } : {}),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : String(r.status))
      return data
    } finally { setBusy(false) }
  }

  async function openPanel(targetCode: string) {
    setNotice(''); setError(''); setReference('')
    try {
      const d = await post('/subscriptions/change/preview', { plan_code: targetCode })
      setPanel({ code: targetCode, kind: d.kind, prorated: d.prorated_usd, effective: d.effective })
    } catch (e: any) { setError(String(e?.message || e)) }
  }

  async function submitUpgrade() {
    if (!panel || !reference.trim()) return
    try {
      await post('/subscriptions/change/upgrade', { plan_code: panel.code, method: payMethod, reference })
      setPanel(null); setNotice(T.submitted)
      await loadAll()
    } catch (e: any) { setError(String(e?.message || e)) }
  }

  async function submitDowngrade() {
    if (!panel) return
    try {
      await post('/subscriptions/downgrade', { plan_code: panel.code })
      setPanel(null); setNotice(T.scheduledOk)
      await loadAll()
    } catch (e: any) { setError(String(e?.message || e)) }
  }

  async function cancelDowngrade() {
    try { await post('/subscriptions/downgrade/cancel'); await loadAll() }
    catch (e: any) { setError(String(e?.message || e)) }
  }

  async function openStripePortal() {
    try {
      const d = await post('/subscriptions/stripe/portal')
      if (d.url) window.location.href = d.url
    } catch (e: any) { setError(String(e?.message || e)) }
  }

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(avail.address)
      setCopied(true); setTimeout(() => setCopied(false), 1800)
    } catch { /* address stays selectable */ }
  }

  const fmtDate = (s: any) => String(s || '').slice(0, 10)

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 2 }}>💎 {T.title}</h1>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>{T.subtitle}</div>

      {notice && <div style={{ ...card, borderColor: '#22c55e', color: '#22c55e', marginBottom: 14, padding: '12px 16px' }}>{notice}</div>}
      {error && <div style={{ ...card, borderColor: '#7f1d1d', color: '#ef4444', marginBottom: 14, padding: '12px 16px' }}>⚠️ {error}</div>}

      {/* ── my subscription ── */}
      {mine && !sub && (
        <div style={{ ...card, marginBottom: 16 }}>
          <div style={{ fontSize: 14 }}>{T.noSub}</div>
          <Link to="/subscribe"><button style={{ ...primaryBtn, marginTop: 10 }}>{T.goSubscribe}</button></Link>
        </div>
      )}
      {sub && (
        <div style={{ ...card, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 17, fontWeight: 800 }}>{PLAN_NAMES[sub.plan_code] || sub.plan_code}</span>
            <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 9px', background: sub.status === 'active' ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)', color: sub.status === 'active' ? '#22c55e' : '#eab308' }}>{sub.status}</span>
            {isTrial && <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 9px', background: 'rgba(42,120,214,0.15)', color: 'var(--accent-primary,#2a78d6)' }}>free trial</span>}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 18px', fontSize: 13, marginTop: 10 }}>
            <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.method}</span><span>{method || '—'}</span>
            <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.started}</span><span>{fmtDate(sub.started_at) || '—'}</span>
            <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.expires}</span><span>{fmtDate(sub.expires_at) || '—'}</span>
          </div>
          {Number(sub.auto_renew) === 1 && (
            <div style={{ fontSize: 12.5, color: 'var(--text-muted,#8a8073)', marginTop: 8 }}>
              {Number(sub.cancel_at_period_end) === 1 ? `${T.cancelsOn}: ${fmtDate(sub.expires_at)}` : `↻ ${T.renewsAuto}`}
            </div>
          )}
          {isTrial && <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#a89f92)', marginTop: 10 }}>{T.trialNote}</div>}
          {scheduledDowngrade && (
            <div style={{ marginTop: 12, padding: '10px 12px', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 10, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 12.5 }}>
              <span>⤵ {T.scheduledBanner}: <b>{PLAN_NAMES[sub.pending_plan_code] || sub.pending_plan_code}</b> · {fmtDate(sub.expires_at)}</span>
              <button style={{ ...ghostBtn, padding: '5px 12px', fontSize: 12 }} disabled={busy} onClick={cancelDowngrade}>{T.cancelSchedule}</button>
            </div>
          )}
        </div>
      )}

      {pendingRow && (
        <div style={{ ...card, borderColor: '#eab308', marginBottom: 16, padding: '14px 16px' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#eab308' }}>⏳ {T.pendingBanner}</div>
          <div style={{ fontSize: 12.5, marginTop: 4 }}>
            {PLAN_NAMES[pendingRow.plan_code] || pendingRow.plan_code} · {pendingRow.method}
            {pendingRow.amount_usd != null && <> · ${Number(pendingRow.amount_usd).toFixed(2)}</>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginTop: 4 }}>{T.pendingBody}</div>
        </div>
      )}

      {/* ── plan ladder ── */}
      {sub && sub.status === 'active' && (
        <>
          <div style={{ fontSize: 15, fontWeight: 700, margin: '18px 0 8px' }}>{T.ladder}</div>
          {method === 'stripe' && (
            <div style={{ ...card, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary,#a89f92)', flex: 1, minWidth: 240 }}>{T.stripeNote}</span>
              <button style={primaryBtn} disabled={busy} onClick={openStripePortal}>{T.stripeManage}</button>
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 12 }}>
            {plans.map((p, idx) => {
              const isCurrent = p.code === sub.plan_code
              const bullets = PLAN_FEATURE_BULLETS[p.code] || []
              const dir = idx > currentIdx ? 'up' : 'down'
              return (
                <div key={p.code} style={{ ...card, padding: '16px 16px', display: 'flex', flexDirection: 'column', gap: 8, borderColor: isCurrent ? '#22c55e' : undefined }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <div style={{ fontSize: 14.5, fontWeight: 700 }}>{p.name}</div>
                    {isCurrent && <span style={{ fontSize: 10.5, fontWeight: 700, borderRadius: 999, padding: '2px 8px', background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>✓ {T.current}</span>}
                  </div>
                  <div style={{ fontSize: 19, fontWeight: 800 }}>
                    {p.contact_only ? '—' : <>${Number(p.price_usd).toLocaleString()}<span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--text-muted,#8a8073)' }}>{T.perMonth}</span></>}
                  </div>
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 5, flex: 1, fontSize: 12, color: 'var(--text-secondary,#a89f92)' }}>
                    {bullets.slice(0, 3).map((b, i) => <li key={i}>✓ {tr(language, b)}</li>)}
                  </ul>
                  {!isCurrent && (
                    p.contact_only ? (
                      <Link to="/contract" style={{ textDecoration: 'none' }}><button style={{ ...ghostBtn, width: '100%' }}>{T.contactUs}</button></Link>
                    ) : isTrial ? (
                      dir === 'up'
                        ? <Link to="/subscribe" style={{ textDecoration: 'none' }} title={T.fullPriceAtSubscribe}><button style={{ ...primaryBtn, width: '100%' }}>⬆ {T.upgrade}</button></Link>
                        : null
                    ) : method === 'stripe' ? (
                      <button style={{ ...ghostBtn, width: '100%' }} disabled={busy} onClick={openStripePortal}>{dir === 'up' ? `⬆ ${T.upgrade}` : `⤵ ${T.downgrade}`}</button>
                    ) : isManual ? (
                      <button style={{ ...(dir === 'up' ? primaryBtn : ghostBtn), width: '100%' }} disabled={busy || !!pendingRow}
                        onClick={() => openPanel(p.code)}>
                        {dir === 'up' ? `⬆ ${T.upgrade}` : `⤵ ${T.downgrade}`}
                      </button>
                    ) : null
                  )}
                </div>
              )
            })}
          </div>

          {/* inline change panel (manual rails) */}
          {panel && (
            <div style={{ ...card, marginTop: 14, maxWidth: 560 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>
                  {sub && (PLAN_NAMES[sub.plan_code] || sub.plan_code)} → {PLAN_NAMES[panel.code] || panel.code}
                </div>
                <div style={{ flex: 1 }} />
                <button style={{ background: 'none', border: 'none', color: 'var(--text-muted,#8a8073)', cursor: 'pointer', fontSize: 12.5, textDecoration: 'underline' }} onClick={() => setPanel(null)}>{T.close}</button>
              </div>
              {panel.kind === 'upgrade' ? (
                <>
                  <div style={{ fontSize: 13, marginTop: 10 }}>
                    {T.payNow}: <b style={{ fontSize: 17 }}>${panel.prorated.toFixed(2)}</b>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginTop: 4 }}>{T.prorationNote} {T.approvalNote}</div>
                  {avail.usdt && avail.bank && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, fontSize: 12.5 }}>
                      <span style={{ color: 'var(--text-muted,#8a8073)' }}>{T.payWith}</span>
                      <button style={payMethod === 'usdt' ? { ...primaryBtn, padding: '5px 12px', fontSize: 12 } : { ...ghostBtn, padding: '5px 12px', fontSize: 12 }} onClick={() => setPayMethod('usdt')}>₮ USDT</button>
                      <button style={payMethod === 'bank' ? { ...primaryBtn, padding: '5px 12px', fontSize: 12 } : { ...ghostBtn, padding: '5px 12px', fontSize: 12 }} onClick={() => setPayMethod('bank')}>🏦 Bank</button>
                    </div>
                  )}
                  {payMethod === 'usdt' && avail.usdt && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>
                        <span>{T.network}</span><strong style={{ color: 'var(--text-primary,#fff)' }}>{avail.network}</strong>
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>{T.address}</div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
                        <code style={{ flex: 1, fontSize: 12, wordBreak: 'break-all', padding: '9px 11px', borderRadius: 8, background: 'var(--bg-primary,#0e0e0d)', border: '1px solid var(--border-color,#2a2a28)' }}>{avail.address}</code>
                        <button style={{ ...ghostBtn, whiteSpace: 'nowrap' }} onClick={copyAddress}>{copied ? `✓ ${T.copiedLabel}` : T.copy}</button>
                      </div>
                      <input placeholder={T.txHash} value={reference} onChange={e => setReference(e.target.value)} style={{ ...inputStyle, margin: '10px 0 0' }} />
                    </div>
                  )}
                  {payMethod === 'bank' && (
                    <div style={{ marginTop: 10 }}>
                      {avail.bank && <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', background: 'var(--bg-primary,#0e0e0d)', borderRadius: 8, padding: 10, border: '1px solid var(--border-color,#2a2a28)', margin: 0 }}>{avail.bank}</pre>}
                      <input placeholder={T.bankRef} value={reference} onChange={e => setReference(e.target.value)} style={{ ...inputStyle, margin: '10px 0 0' }} />
                    </div>
                  )}
                  <button style={{ ...primaryBtn, width: '100%', marginTop: 12 }} disabled={busy || !reference.trim()} onClick={submitUpgrade}>{T.submitPaid}</button>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#a89f92)', marginTop: 10 }}>{T.downgradeNote}</div>
                  <button style={{ ...primaryBtn, width: '100%', marginTop: 12 }} disabled={busy} onClick={submitDowngrade}>⤵ {T.scheduleDowngrade}</button>
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* ── history ── */}
      {history.items.length > 0 && (
        <>
          <div style={{ fontSize: 15, fontWeight: 700, margin: '22px 0 8px' }}>{T.historyTitle}</div>
          <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
              <thead><tr><th style={th}>{T.date}</th><th style={th}>{T.plan}</th><th style={th}>{T.method}</th><th style={th}>{T.amount}</th><th style={th}>{T.status}</th><th style={th}>{T.expires}</th></tr></thead>
              <tbody>
                {history.items.map(i => (
                  <tr key={i.id}>
                    <td style={td}>{fmtDate(i.created_at)}</td>
                    <td style={td}>
                      {i.plan_name || i.plan_code}
                      {i.change_kind === 'upgrade' && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--accent-primary,#2a78d6)' }}>⬆</span>}
                    </td>
                    <td style={td}>{i.method || '—'}</td>
                    <td style={td}>{i.amount_usd != null ? `$${Number(i.amount_usd).toFixed(2)}` : '—'}</td>
                    <td style={td}>{i.status}</td>
                    <td style={td}>{fmtDate(i.expires_at) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {history.items.length < history.total && (
            <button style={{ ...ghostBtn, marginTop: 10 }} onClick={loadMore}>{T.loadMore} ({history.items.length}/{history.total})</button>
          )}
        </>
      )}
    </div>
  )
}
