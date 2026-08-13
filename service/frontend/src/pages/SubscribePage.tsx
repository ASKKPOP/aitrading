import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import QRCode from 'qrcode'
import { API_BASE, useLanguage } from '../appShared'
import { PLAN_FEATURE_BULLETS } from '../entitlements'
import { tr } from '../i18n'

// Membership gate — Sooppiy is subscription-only. A signed-in user without an
// active subscription lands here (App.tsx gate). Four tiers: junior $60 /
// pro $119 / professional $199 per month, enterprise via the contract page.
// Payment: Stripe (card / Apple Pay / Google Pay), auto-renewing.
// subscriptions, activated via webhook (hence the return-state polling) —
// or USDT / bank transfer (admin approval, one-time).
const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 14, padding: '22px 20px' }
const primaryBtn: any = { padding: '10px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 14, width: '100%' }
const ghostBtn: any = { ...primaryBtn, background: 'transparent', border: '1px solid var(--border-color,#2a2a28)', color: 'inherit' }
const inputStyle: any = { padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-primary,#0e0e0d)', color: 'var(--text-primary,#fff)', fontSize: 14, width: '100%' }

export function SubscribePage({ userToken, onSignOut }: { userToken: string | null, onSignOut?: () => void }) {
  const { language } = useLanguage()
  const [params] = useSearchParams()
  const [plans, setPlans] = useState<any[]>([])
  const [stripeAvailable, setStripeAvailable] = useState(false)
  const [bankInfo, setBankInfo] = useState('')
  const [usdt, setUsdt] = useState<{ available: boolean; address: string; network: string }>(
    { available: false, address: '', network: 'TRC20' })
  const [txHash, setTxHash] = useState('')
  const [copied, setCopied] = useState(false)
  const [qr, setQr] = useState('')
  const [mine, setMine] = useState<any | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const T = {
    title: tr(language, { ko: '멤버십 구독', en: 'Choose your membership', ja: 'メンバーシップを選ぶ',
      th: 'เลือกแพ็กเกจสมาชิก', vi: 'Chọn gói thành viên', id: 'Pilih keanggotaan Anda' }),
    subtitle: tr(language, { ko: 'Sooppiy는 구독 회원 전용 서비스입니다. 플랜을 선택하면 모든 기능이 열립니다.', en: 'Sooppiy is a members-only platform. Pick a plan to unlock everything.',
      ja: 'Sooppiy は会員限定のプラットフォームです。プランを選ぶとすべての機能が使えます。',
      th: 'Sooppiy เปิดให้เฉพาะสมาชิกเท่านั้น เลือกแพ็กเกจเพื่อปลดล็อกทุกฟีเจอร์',
      vi: 'Sooppiy là nền tảng dành riêng cho thành viên. Chọn một gói để mở khóa toàn bộ tính năng.',
      id: 'Sooppiy adalah platform khusus anggota. Pilih paket untuk membuka semua fitur.' }),
    perMonth: tr(language, { ko: '/월', en: '/month', ja: '/月', th: '/เดือน', vi: '/tháng', id: '/bulan' }),
    select: tr(language, { ko: '선택', en: 'Select', ja: '選択', th: 'เลือก', vi: 'Chọn', id: 'Pilih' }),
    selectedLabel: tr(language, { ko: '선택됨', en: 'Selected', ja: '選択中', th: 'เลือกแล้ว', vi: 'Đã chọn', id: 'Terpilih' }),
    payBank: tr(language, { ko: '계좌이체로 신청', en: 'Pay by bank transfer', ja: '銀行振込で申し込む',
      th: 'ชำระด้วยการโอนเงินผ่านธนาคาร', vi: 'Thanh toán bằng chuyển khoản ngân hàng', id: 'Bayar lewat transfer bank' }),
    bankRef: tr(language, { ko: '이체 참조번호 (보낸 분 성함 등)', en: 'Transfer reference (sender name, memo…)',
      ja: '振込の参照情報 (振込人名義・メモなど)', th: 'ข้อมูลอ้างอิงการโอน (ชื่อผู้โอน, บันทึกช่วยจำ…)',
      vi: 'Thông tin tham chiếu chuyển khoản (tên người gửi, ghi chú…)',
      id: 'Referensi transfer (nama pengirim, memo…)' }),
    bankSubmit: tr(language, { ko: '이체 완료 — 승인 요청', en: 'I transferred — request approval',
      ja: '振込しました — 承認をリクエスト', th: 'โอนแล้ว — ขออนุมัติ',
      vi: 'Đã chuyển khoản — yêu cầu duyệt',
      id: 'Saya sudah transfer — ajukan persetujuan' }),
    contactUs: tr(language, { ko: '문의하기', en: 'Contact us', ja: 'お問い合わせ', th: 'ติดต่อเรา',
      vi: 'Liên hệ với chúng tôi',
      id: 'Hubungi kami' }),
    enterpriseDesc: tr(language, { ko: '맞춤 계약 · 전담 지원', en: 'Custom contract · dedicated support',
      ja: 'カスタム契約 · 専任サポート', th: 'สัญญาแบบกำหนดเอง · ทีมดูแลเฉพาะ',
      vi: 'Hợp đồng tùy chỉnh · hỗ trợ riêng',
      id: 'Kontrak khusus · dukungan khusus' }),
    pendingTitle: tr(language, { ko: '승인 대기 중', en: 'Awaiting approval', ja: '承認待ち',
      th: 'รอการอนุมัติ', vi: 'Đang chờ duyệt', id: 'Menunggu persetujuan' }),
    pendingBody: tr(language, { ko: '이체 확인 후 관리자가 구독을 활성화합니다. 잠시 후 다시 확인해 주세요.', en: 'An administrator will activate your subscription once the transfer is confirmed. Check back soon.',
      ja: '振込の確認後、管理者が購読を有効化します。しばらくしてからもう一度ご確認ください。',
      th: 'ผู้ดูแลจะเปิดใช้งานการสมัครสมาชิกหลังยืนยันการโอนแล้ว กรุณากลับมาตรวจสอบอีกครั้ง',
      vi: 'Quản trị viên sẽ kích hoạt gói đăng ký sau khi xác nhận chuyển khoản. Vui lòng kiểm tra lại sau ít phút.',
      id: 'Administrator akan mengaktifkan langganan Anda setelah transfer terkonfirmasi. Silakan cek kembali sebentar lagi.' }),
    activeTitle: tr(language, { ko: '구독 활성화됨', en: 'Subscription active', ja: '購読が有効です',
      th: 'สมาชิกใช้งานอยู่', vi: 'Gói đăng ký đang hoạt động', id: 'Langganan aktif' }),
    activeBody: tr(language, { ko: '모든 기능을 사용할 수 있습니다.', en: 'You have full access.',
      ja: 'すべての機能をご利用いただけます。', th: 'คุณเข้าถึงได้ทุกฟีเจอร์แล้ว',
      vi: 'Bạn đã có toàn quyền truy cập.',
      id: 'Anda memiliki akses penuh.' }),
    expires: tr(language, { ko: '만료일', en: 'Expires', ja: '有効期限', th: 'วันหมดอายุ',
      vi: 'Ngày hết hạn',
      id: 'Berakhir' }),
    goApp: tr(language, { ko: '앱으로 이동', en: 'Go to the app', ja: 'アプリへ移動', th: 'ไปที่แอป',
      vi: 'Đến ứng dụng',
      id: 'Buka aplikasi' }),
    signOut: tr(language, { ko: '로그아웃', en: 'Sign out', ja: 'ログアウト', th: 'ออกจากระบบ',
      vi: 'Đăng xuất',
      id: 'Keluar' }),
    subDone: tr(language, { ko: '결제가 완료되었습니다! 구독이 활성화되었습니다.', en: 'Payment complete! Your subscription is active.',
      ja: 'お支払いが完了しました！購読が有効になりました。',
      th: 'ชำระเงินสำเร็จ! เปิดใช้งานการสมัครสมาชิกแล้ว',
      vi: 'Thanh toán hoàn tất! Gói đăng ký của bạn đã được kích hoạt.',
      id: 'Pembayaran selesai! Langganan Anda aktif.' }),
    // ── USDT (the default rail) ──
    payUsdt: tr(language, { ko: 'USDT로 결제', en: 'Pay with USDT', ja: 'USDT で支払う',
      th: 'ชำระด้วย USDT', vi: 'Thanh toán bằng USDT', id: 'Bayar dengan USDT' }),
    usdtNetwork: tr(language, { ko: '네트워크', en: 'Network', ja: 'ネットワーク',
      th: 'เครือข่าย', vi: 'Mạng lưới', id: 'Jaringan' }),
    usdtScan: tr(language, { ko: '지갑 앱으로 스캔', en: 'Scan with your wallet app',
      ja: 'ウォレットアプリでスキャン', th: 'สแกนด้วยแอปกระเป๋าเงิน',
      vi: 'Quét bằng ứng dụng ví',
      id: 'Pindai dengan aplikasi dompet Anda' }),
    usdtAddress: tr(language, { ko: '입금 주소', en: 'Deposit address', ja: '入金アドレス',
      th: 'ที่อยู่สำหรับโอน', vi: 'Địa chỉ nhận', id: 'Alamat setor' }),
    usdtCopy: tr(language, { ko: '복사', en: 'Copy', ja: 'コピー', th: 'คัดลอก', vi: 'Sao chép', id: 'Salin' }),
    usdtCopied: tr(language, { ko: '복사됨', en: 'Copied', ja: 'コピーしました',
      th: 'คัดลอกแล้ว', vi: 'Đã sao chép', id: 'Tersalin' }),
    usdtHash: tr(language, { ko: '트랜잭션 해시 (TxID)', en: 'Transaction hash (TxID)',
      th: 'แฮชธุรกรรม (TxID)', ja: 'トランザクションハッシュ (TxID)', vi: 'Mã giao dịch (TxID)', id: 'Hash transaksi (TxID)' }),
    usdtSubmit: tr(language, { ko: '송금 완료 — 승인 요청', en: 'I sent it — request approval',
      ja: '送金しました — 承認をリクエスト', th: 'โอนแล้ว — ขออนุมัติ',
      vi: 'Đã chuyển — yêu cầu duyệt',
      id: 'Saya sudah mengirim — ajukan persetujuan' }),
    usdtWarn: tr(language, {
      ko: '반드시 위에 표시된 네트워크로만 보내세요. 다른 네트워크로 보내면 자금을 복구할 수 없습니다. 입금 확인 후 관리자가 구독을 활성화합니다.',
      en: 'Send only on the network shown above. Funds sent on a different network cannot be recovered. An administrator activates your subscription once the transfer is confirmed on-chain.',
      ja: '必ず上記のネットワークで送金してください。異なるネットワークに送金した資金は復元できません。入金確認後に管理者が有効化します。',
      th: 'โอนผ่านเครือข่ายที่แสดงด้านบนเท่านั้น เงินที่ส่งผิดเครือข่ายจะกู้คืนไม่ได้ ผู้ดูแลจะเปิดใช้งานหลังยืนยันบนเชน',
      vi: 'Chỉ chuyển trên mạng lưới hiển thị ở trên. Tiền gửi sai mạng lưới không thể khôi phục. Quản trị viên sẽ kích hoạt sau khi xác nhận trên chuỗi.',
      id: 'Kirim hanya melalui jaringan yang ditampilkan di atas. Dana yang dikirim lewat jaringan lain tidak dapat dipulihkan. Administrator mengaktifkan langganan Anda setelah transfer terkonfirmasi di blockchain.' }),
    usdtAmount: tr(language, { ko: '보낼 금액', en: 'Amount to send', ja: '送金額',
      th: 'จำนวนที่ต้องโอน', vi: 'Số tiền cần chuyển', id: 'Jumlah yang dikirim' }),
    orOther: tr(language, { ko: '또는 다른 방법', en: 'Or another method', ja: 'または他の方法',
      th: 'หรือวิธีอื่น', vi: 'Hoặc phương thức khác', id: 'Atau metode lain' }),
    upgradeTitle: tr(language, { ko: '플랜 업그레이드', en: 'Upgrade your plan', ja: 'プランをアップグレード',
      th: 'อัปเกรดแผนของคุณ', vi: 'Nâng cấp gói của bạn', id: 'Tingkatkan paket Anda' }),
    upgradeSubtitle: tr(language, { ko: '더 높은 플랜을 선택하면 결제 승인 후 적용됩니다.',
      en: 'Pick a higher plan — it takes effect once the payment is approved.',
      ja: '上位プランを選ぶと、支払いの承認後に適用されます。',
      th: 'เลือกแผนที่สูงขึ้น — มีผลเมื่อการชำระเงินได้รับอนุมัติ',
      vi: 'Chọn gói cao hơn — có hiệu lực sau khi thanh toán được duyệt.',
      id: 'Pilih paket yang lebih tinggi — berlaku setelah pembayaran disetujui.' }),
    currentPlan: tr(language, { ko: '현재 플랜', en: 'Current plan', ja: '現在のプラン',
      th: 'แผนปัจจุบัน', vi: 'Gói hiện tại', id: 'Paket saat ini' }),
    payCard: tr(language, { ko: '카드로 구독 — 카드 · Apple Pay · Google Pay', en: 'Subscribe with card — card · Apple Pay · Google Pay',
      ja: 'カードで購読 — カード · Apple Pay · Google Pay', th: 'สมัครด้วยบัตร — บัตร · Apple Pay · Google Pay',
      vi: 'Đăng ký bằng thẻ — thẻ · Apple Pay · Google Pay', id: 'Berlangganan dengan kartu — kartu · Apple Pay · Google Pay' }),
    autoRenewNote: tr(language, { ko: '매월 자동 갱신 · 언제든 해지 가능', en: 'Renews monthly · cancel anytime',
      ja: '毎月自動更新 · いつでも解約可能', th: 'ต่ออายุรายเดือน · ยกเลิกได้ทุกเมื่อ',
      vi: 'Gia hạn hằng tháng · hủy bất cứ lúc nào', id: 'Diperpanjang bulanan · batalkan kapan saja' }),
    activating: tr(language, { ko: '결제 확인 중 — 곧 활성화됩니다…', en: 'Payment received — activating…',
      ja: '支払いを確認中 — まもなく有効になります…', th: 'ได้รับการชำระเงินแล้ว — กำลังเปิดใช้งาน…',
      vi: 'Đã nhận thanh toán — đang kích hoạt…', id: 'Pembayaran diterima — mengaktifkan…' }),
    stripeCancelled: tr(language, { ko: '카드 결제가 취소되었습니다.', en: 'Card checkout was cancelled.',
      ja: 'カード決済がキャンセルされました。', th: 'การชำระด้วยบัตรถูกยกเลิก',
      vi: 'Thanh toán thẻ đã bị hủy.', id: 'Pembayaran kartu dibatalkan.' }),
    renewsAuto: tr(language, { ko: '자동 갱신', en: 'Renews automatically', ja: '自動更新',
      th: 'ต่ออายุอัตโนมัติ', vi: 'Tự động gia hạn', id: 'Diperpanjang otomatis' }),
    cancelsOn: tr(language, { ko: '해지 예정일', en: 'Cancels on', ja: '解約予定日',
      th: 'จะยกเลิกในวันที่', vi: 'Sẽ hủy vào', id: 'Berakhir pada' }),
    manageSub: tr(language, { ko: '구독 관리', en: 'Manage subscription', ja: '購読を管理',
      th: 'จัดการการสมัคร', vi: 'Quản lý gói đăng ký', id: 'Kelola langganan' }),
    changePlan: tr(language, { ko: '플랜 변경 (다음 결제 주기부터 적용)', en: 'Change plan (applies next billing cycle)',
      ja: 'プラン変更 (次の請求サイクルから適用)', th: 'เปลี่ยนแพ็กเกจ (มีผลรอบบิลถัดไป)',
      vi: 'Đổi gói (áp dụng từ chu kỳ sau)', id: 'Ganti paket (berlaku siklus berikutnya)' }),
    cancelAutoRenew: tr(language, { ko: '자동 갱신 해지', en: 'Cancel auto-renewal', ja: '自動更新を解約',
      th: 'ยกเลิกการต่ออายุอัตโนมัติ', vi: 'Hủy tự động gia hạn', id: 'Batalkan perpanjangan otomatis' }),
    cancelKeepsAccess: tr(language, { ko: '해지해도 현재 결제 기간이 끝날 때까지는 이용할 수 있습니다.', en: 'You keep access until the end of the current billing period.',
      ja: '解約後も現在の請求期間の終了までご利用いただけます。', th: 'คุณยังใช้งานได้จนสิ้นสุดรอบบิลปัจจุบัน',
      vi: 'Bạn vẫn dùng được đến hết chu kỳ thanh toán hiện tại.', id: 'Anda tetap punya akses hingga akhir periode tagihan saat ini.' }),
  }

  const authHdr: Record<string, string> = userToken ? { 'Authorization': `Bearer ${userToken}` } : {}

  async function loadState() {
    try {
      const p = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
      setPlans(p.plans || [])
      setStripeAvailable(!!p.stripe_available)
      setBankInfo(p.bank_transfer_info || '')
      setUsdt({ available: !!p.usdt_available, address: p.usdt_address || '',
        network: p.usdt_network || 'TRC20' })
      if (userToken) {
        const m = await fetch(`${API_BASE}/subscriptions/me`, { headers: authHdr }).then(r => r.ok ? r.json() : null)
        setMine(m)
      }
    } catch { /* network */ }
  }

  useEffect(() => { loadState() }, [userToken])

  // The QR encodes the deposit address verbatim — same `usdt.address` string the
  // <code> block below renders, so the two can never drift apart. Plain address,
  // not an EIP-681 URI: every wallet scans it, and there is no contract or
  // decimals value to get wrong. The user still types the amount by hand.
  useEffect(() => {
    if (!usdt.address) { setQr(''); return }
    let live = true
    QRCode.toDataURL(usdt.address, { errorCorrectionLevel: 'M', margin: 1, width: 320 })
      .then(url => { if (live) setQr(url) })
      .catch(() => { if (live) setQr('') })  // address text stays authoritative
    return () => { live = false }
  }, [usdt.address])

  // Stripe auto-renew return: activation lands via webhook, so poll.
  useEffect(() => {
    const stripeMode = params.get('stripe')
    if (stripeMode === 'cancel') { setError(T.stripeCancelled); return }
    if (stripeMode !== 'success' || !userToken) return
    setBusy(true); setNotice(T.activating)
    let tries = 0
    const timer = setInterval(async () => {
      tries += 1
      try {
        const m = await fetch(`${API_BASE}/subscriptions/me`, { headers: authHdr })
          .then(r => r.ok ? r.json() : null)
        if (m?.status === 'active' && Number(m?.subscription?.auto_renew)) {
          clearInterval(timer)
          setNotice(T.subDone)
          setTimeout(() => { window.location.href = '/' }, 1200)
          return
        }
      } catch { /* keep polling */ }
      if (tries >= 15) { clearInterval(timer); setBusy(false); setNotice('') }
    }, 2000)
    return () => clearInterval(timer)
  }, [params, userToken])

  async function startStripe(planCode: string) {
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/stripe/checkout`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      window.location.href = (await r.json()).url
    } catch (e: any) { setError(String(e?.message || e)); setBusy(false) }
  }

  async function submitUsdt(planCode: string) {
    if (!txHash.trim()) return
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/usdt`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode, tx_hash: txHash }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      setTxHash('')
      await loadState()
    } catch (e: any) { setError(String(e?.message || e)) }
    setBusy(false)
  }

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(usdt.address)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch { /* clipboard blocked — the address is selectable on screen anyway */ }
  }

  async function submitBank(planCode: string) {
    if (!reference.trim()) return
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/bank-transfer`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode, reference }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      await loadState()
    } catch (e: any) { setError(String(e?.message || e)) }
    setBusy(false)
  }

  const status = mine?.status || 'none'

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '48px 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, margin: 0 }}>💎 {T.title}</h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary,#8a8073)', marginTop: 8 }}>{T.subtitle}</p>
      </div>

      {notice && <div style={{ ...card, borderColor: '#22c55e', color: '#22c55e', marginBottom: 16, textAlign: 'center' }}>{notice}</div>}
      {error && <div style={{ ...card, borderColor: '#7f1d1d', color: '#ef4444', marginBottom: 16, textAlign: 'center' }}>⚠️ {error}</div>}

      {status === 'active' && (
        <div style={{ ...card, textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#22c55e' }}>✓ {T.activeTitle}</div>
          <div style={{ fontSize: 14, marginTop: 6 }}>{T.activeBody}</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted,#8a8073)', marginTop: 6 }}>
            {mine?.subscription?.plan_code} · {T.expires}: {String(mine?.subscription?.expires_at || '').slice(0, 10)}
          </div>
          {Number(mine?.subscription?.auto_renew) === 1 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, color: 'var(--text-muted,#8a8073)' }}>
                {Number(mine?.subscription?.cancel_at_period_end) === 1
                  ? `${T.cancelsOn}: ${String(mine?.subscription?.expires_at || '').slice(0, 10)}`
                  : `↻ ${T.renewsAuto}`}
              </div>
              {mine?.subscription?.method === 'stripe' && (
                <button style={{ ...ghostBtn, width: 'auto', marginTop: 10 }} disabled={busy}
                  onClick={async () => {
                    setBusy(true); setError('')
                    try {
                      const r = await fetch(`${API_BASE}/subscriptions/stripe/portal`, {
                        method: 'POST', headers: authHdr })
                      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
                      window.location.href = (await r.json()).url
                    } catch (e: any) { setError(String(e?.message || e)); setBusy(false) }
                  }}>{T.manageSub}</button>
              )}
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <Link to="/"><button style={{ ...primaryBtn, width: 'auto' }}>{T.goApp}</button></Link>
          </div>
        </div>
      )}

      {status === 'pending' && (
        <div style={{ ...card, textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#eab308' }}>⏳ {T.pendingTitle}</div>
          <div style={{ fontSize: 14, marginTop: 6 }}>{T.pendingBody}</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted,#8a8073)', marginTop: 6 }}>
            {mine?.subscription?.plan_code} · {mine?.subscription?.method}
          </div>
        </div>
      )}

      {/* An ACTIVE member keeps the plan grid — it is the upgrade path the
          account pages link to. Only a pending payment hides it. */}
      {status === 'active' && (
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 17, fontWeight: 700 }}>⬆ {T.upgradeTitle}</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)', marginTop: 4 }}>{T.upgradeSubtitle}</div>
        </div>
      )}
      {status !== 'pending' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 14 }}>
          {plans.map(p => {
            const isCurrent = status === 'active' && mine?.subscription?.plan_code === p.code
            const bullets = PLAN_FEATURE_BULLETS[p.code] || []
            return (
              <div key={p.code} style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10, borderColor: selected === p.code ? 'var(--accent-primary,#c26a45)' : isCurrent ? '#22c55e' : undefined }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>{p.name}</div>
                  {isCurrent && (
                    <span style={{ fontSize: 10.5, fontWeight: 700, borderRadius: 999, padding: '2px 8px', background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>✓ {T.currentPlan}</span>
                  )}
                </div>
                {p.contact_only ? (
                  <>
                    <div style={{ fontSize: 22, fontWeight: 800 }}>—</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)' }}>{T.enterpriseDesc}</div>
                    <ul style={{ margin: 0, padding: '0 0 0 2px', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, flex: 1, fontSize: 12.5, color: 'var(--text-secondary,#a89f92)' }}>
                      {bullets.map((b, i) => <li key={i}>✓ {tr(language, b)}</li>)}
                    </ul>
                    <Link to="/contract" style={{ textDecoration: 'none' }}><button style={ghostBtn}>{T.contactUs}</button></Link>
                  </>
                ) : (
                  <>
                    <div style={{ fontSize: 22, fontWeight: 800 }}>${Number(p.price_usd).toLocaleString()}<span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted,#8a8073)' }}>{T.perMonth}</span></div>
                    <ul style={{ margin: 0, padding: '0 0 0 2px', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, flex: 1, fontSize: 12.5, color: 'var(--text-secondary,#a89f92)' }}>
                      {bullets.map((b, i) => <li key={i}>✓ {tr(language, b)}</li>)}
                    </ul>
                    <button style={selected === p.code ? primaryBtn : ghostBtn} disabled={busy || isCurrent}
                      onClick={() => { setSelected(p.code); setError('') }}>
                      {isCurrent ? `✓ ${T.currentPlan}` : selected === p.code ? `✓ ${T.selectedLabel}` : T.select}
                    </button>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}

      {status !== 'pending' && selected && (
        <div style={{ ...card, marginTop: 20, maxWidth: 520, marginLeft: 'auto', marginRight: 'auto' }}>
          {stripeAvailable && (
            <div style={{ marginBottom: 18 }}>
              <button style={primaryBtn} disabled={busy} onClick={() => startStripe(selected)}>
                💳 {T.payCard}
              </button>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted,#8a8073)', marginTop: 6, textAlign: 'center' }}>
                {T.autoRenewNote}
              </div>
            </div>
          )}

          {/* USDT is the default rail — first, and the only one with a
              highlighted action. */}
          {usdt.available && (
            <div style={{ marginBottom: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>₮ {T.payUsdt}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
                color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>
                <span>{T.usdtNetwork}</span>
                <strong style={{ color: 'var(--text-primary,#fff)' }}>{usdt.network}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12,
                color: 'var(--text-muted,#8a8073)', marginBottom: 8 }}>
                <span>{T.usdtAmount}</span>
                <strong style={{ color: 'var(--text-primary,#fff)' }}>
                  {Number(plans.find(p => p.code === selected)?.price_usd || 0).toLocaleString()} USDT
                </strong>
              </div>
              {qr && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
                  gap: 6, margin: '4px 0 12px' }}>
                  {/* White plate is required, not decorative: scanners need the
                      light quiet zone, and the app renders on a dark ground. */}
                  <img src={qr} alt={`${T.usdtAddress} — ${usdt.network}`} width={160} height={160}
                    style={{ display: 'block', background: '#fff', padding: 8, borderRadius: 8 }} />
                  <div style={{ fontSize: 11.5, color: 'var(--text-muted,#8a8073)' }}>{T.usdtScan}</div>
                </div>
              )}
              <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 4 }}>
                {T.usdtAddress}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
                <code style={{ flex: 1, fontSize: 12, wordBreak: 'break-all', padding: '10px 12px',
                  borderRadius: 8, background: 'var(--bg-primary,#0e0e0d)',
                  border: '1px solid var(--border-color,#2a2a28)' }}>{usdt.address}</code>
                <button style={{ ...ghostBtn, width: 'auto', whiteSpace: 'nowrap' }}
                  onClick={copyAddress}>{copied ? `✓ ${T.usdtCopied}` : T.usdtCopy}</button>
              </div>
              <p style={{ fontSize: 11.5, lineHeight: 1.5, color: '#eab308', margin: '10px 0 0' }}>
                ⚠️ {T.usdtWarn}
              </p>
              <input placeholder={T.usdtHash} value={txHash} onChange={e => setTxHash(e.target.value)}
                style={{ ...inputStyle, margin: '10px 0' }} />
              <button style={primaryBtn} disabled={busy || !txHash.trim()}
                onClick={() => submitUsdt(selected)}>{T.usdtSubmit}</button>
            </div>
          )}

          {usdt.available && (
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em',
              color: 'var(--text-muted,#8a8073)', borderTop: '1px solid var(--border-color,#2a2a28)',
              paddingTop: 14, marginBottom: 10 }}>{T.orOther}</div>
          )}

          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{T.payBank}</div>
          {bankInfo && <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', background: 'var(--bg-primary,#0e0e0d)', borderRadius: 8, padding: 10, border: '1px solid var(--border-color,#2a2a28)' }}>{bankInfo}</pre>}
          <input placeholder={T.bankRef} value={reference} onChange={e => setReference(e.target.value)}
            style={{ ...inputStyle, margin: '8px 0 10px' }} />
          <button style={ghostBtn} disabled={busy || !reference.trim()}
            onClick={() => submitBank(selected)}>{T.bankSubmit}</button>
        </div>
      )}

      {onSignOut && (
        <div style={{ textAlign: 'center', marginTop: 28 }}>
          <button onClick={onSignOut} style={{ background: 'none', border: 'none', color: 'var(--text-muted,#8a8073)', cursor: 'pointer', fontSize: 13, textDecoration: 'underline' }}>{T.signOut}</button>
        </div>
      )}
    </div>
  )
}

export default SubscribePage
