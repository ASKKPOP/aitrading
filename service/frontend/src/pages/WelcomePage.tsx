import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { PLAN_NAMES } from '../entitlements'
import PhoneVerifyCard from '../components/PhoneVerifyCard'

// First-run welcome page (owner request 2026-08-05): four icon+numbered cards
// — service intro, how to use, subscription info, step-by-step — each with its
// own links, a LIVE phone-verify control, and a "do not show next time"
// checkbox. Signup lands here (authV2) and App.tsx redirects here once per
// session until the member dismisses it; it stays reachable from the profile
// menu forever. /getting-started survives unchanged as the deep reference.

const V = {
  bg: 'var(--bg-primary, #f9f9f7)',
  card: 'var(--bg-card, #ffffff)',
  ink: 'var(--text-primary, #0b0b0b)',
  mut: 'var(--text-secondary, #52514e)',
  faint: 'var(--text-muted, #898781)',
  line: 'var(--border-color, rgba(11,11,11,0.10))',
  accent: 'var(--accent-primary, #2a78d6)',
  accentOn: 'var(--accent-contrast, #ffffff)',
  display: 'var(--font-display, system-ui, sans-serif)',
  mono: 'var(--font-mono, ui-monospace, monospace)',
}
const wrap: any = { maxWidth: 940, margin: '0 auto', padding: '0 20px' }
const cardS: any = { background: V.card, border: `1px solid ${V.line}`, borderRadius: 14, padding: '18px 20px' }
const kicker: any = { fontFamily: V.mono, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: V.accent, fontWeight: 600 }
const numS: any = { flexShrink: 0, width: 30, height: 30, borderRadius: 999, background: V.accent, color: V.accentOn, fontFamily: V.mono, fontWeight: 700, fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const pillS: any = { display: 'inline-block', fontSize: 12.5, fontWeight: 600, color: V.accent, border: `1px solid ${V.line}`, borderRadius: 999, padding: '4px 12px', textDecoration: 'none' }

export default function WelcomePage({ userToken }: { userToken: string }) {
  const { language } = useLanguage()
  const [dismissed, setDismissed] = useState(false)
  const [plans, setPlans] = useState<any[]>([])

  useEffect(() => {
    fetch(`${API_BASE}/users/me`, { headers: { 'Authorization': `Bearer ${userToken}` } })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) setDismissed(!!d.welcome_dismissed) })
      .catch(() => {})
    fetch(`${API_BASE}/subscriptions/plans`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d?.plans) setPlans(d.plans) })
      .catch(() => {})
  }, [userToken])

  const toggleDismiss = (next: boolean) => {
    setDismissed(next)
    fetch(`${API_BASE}/users/welcome/dismiss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${userToken}` },
      body: JSON.stringify({ dismissed: next }),
    }).catch(() => {})
  }

  const linkRow = (links: { to: string; label: string }[]) => (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
      {links.map(l => <Link key={l.to} to={l.to} style={pillS}>{l.label} →</Link>)}
    </div>
  )

  const perMonth = tr(language, { ko: '/월', en: '/month', ja: '/月', th: '/เดือน', vi: '/tháng', id: '/bulan' })

  const stepLine = (n: number, text: string) => (
    <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginTop: 6 }}>
      <span style={{ fontFamily: V.mono, fontWeight: 700, fontSize: 12.5, color: V.accent }}>{n}.</span>
      <span style={{ fontSize: 14, color: V.mut }}>{text}</span>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: V.bg, color: V.ink, lineHeight: 1.55 }}>
      <div style={{ ...wrap, paddingTop: 28, paddingBottom: 56 }}>
        <div style={kicker}>{tr(language, { ko: '환영합니다', en: 'WELCOME', ja: 'ようこそ', th: 'ยินดีต้อนรับ', vi: 'CHÀO MỪNG', id: 'SELAMAT DATANG' })}</div>
        <h1 style={{ fontFamily: V.display, fontWeight: 800, fontSize: 'clamp(28px,4.4vw,44px)', lineHeight: 1.08, letterSpacing: '-0.02em', margin: '10px 0 8px' }}>
          {tr(language, { ko: 'Sooppiy에 오신 것을 환영합니다', en: 'Welcome to Sooppiy', ja: 'Sooppiyへようこそ', th: 'ยินดีต้อนรับสู่ Sooppiy', vi: 'Chào mừng đến với Sooppiy', id: 'Selamat datang di Sooppiy' })}
        </h1>
        <p style={{ fontSize: 15.5, color: V.mut, maxWidth: '64ch', margin: '0 0 20px' }}>
          {tr(language, {
            ko: '네 장의 카드로 시작에 필요한 모든 것을 안내합니다. 각 카드의 링크로 바로 이동할 수 있습니다.',
            en: 'Four cards cover everything you need to get going — each one links straight to the real pages.',
            ja: '4枚のカードで始めに必要なすべてを案内します。各カードのリンクからそのままページへ移動できます。',
            th: 'การ์ดสี่ใบครอบคลุมทุกอย่างที่คุณต้องรู้ — แต่ละใบลิงก์ตรงไปยังหน้าจริง',
            vi: 'Bốn thẻ bao quát mọi thứ bạn cần để bắt đầu — mỗi thẻ liên kết thẳng đến trang thật.',
            id: 'Empat kartu mencakup semua yang Anda butuhkan untuk memulai — setiap kartu menaut langsung ke halaman sebenarnya.',
          })}
        </p>

        <div style={{ display: 'grid', gap: 14 }}>
          {/* 1 — service introduction */}
          <div style={{ ...cardS, display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div style={numS}>1</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 16.5, marginBottom: 4 }}>
                <span aria-hidden style={{ marginRight: 8 }}>📡</span>
                {tr(language, { ko: 'Sooppiy는 이런 서비스입니다', en: 'What Sooppiy is', ja: 'Sooppiyとは', th: 'Sooppiy คืออะไร', vi: 'Sooppiy là gì', id: 'Apa itu Sooppiy' })}
              </div>
              <div style={{ fontSize: 14, color: V.mut }}>
                {tr(language, {
                  ko: 'AI 에이전트가 시장 신호를 발행하고, 팔로워는 그 매매를 자기 원장에 미러링하는 시그널 · 카피 트레이딩 플랫폼입니다. 모든 계정은 실제 리스크가 없는 $100,000 모의 원장으로 시작합니다.',
                  en: 'A signal and copy-trading platform: AI agents publish signals and followers mirror the trades onto their own ledger. Every account starts on a $100,000 simulated ledger with no real risk.',
                  ja: 'AIエージェントがシグナルを発行し、フォロワーがその売買を自分の台帳にミラーするシグナル・コピートレードのプラットフォームです。全アカウントは実リスクのない10万ドルの模擬台帳から始まります。',
                  th: 'แพลตฟอร์มสัญญาณและก๊อปปี้เทรด: เอเจนต์ AI เผยแพร่สัญญาณ และผู้ติดตามมิเรอร์การเทรดมายังบัญชีของตัวเอง ทุกบัญชีเริ่มด้วยบัญชีจำลอง $100,000 ไม่มีความเสี่ยงจริง',
                  vi: 'Nền tảng tín hiệu và copy-trading: agent AI phát tín hiệu, người theo dõi sao chép giao dịch vào sổ của mình. Mọi tài khoản bắt đầu với sổ mô phỏng $100.000, không rủi ro thật.',
                  id: 'Platform sinyal dan copy-trading: agen AI menerbitkan sinyal dan pengikut menyalin transaksinya ke buku mereka sendiri. Setiap akun dimulai dengan buku simulasi $100.000 tanpa risiko nyata.',
                })}
              </div>
              {linkRow([
                { to: '/about', label: tr(language, { ko: '서비스 소개', en: 'About', ja: 'サービス紹介', th: 'เกี่ยวกับ', vi: 'Giới thiệu', id: 'Tentang' }) },
                { to: '/signals-board', label: tr(language, { ko: '시그널 보드', en: 'Signals board', ja: 'シグナルボード', th: 'บอร์ดสัญญาณ', vi: 'Bảng tín hiệu', id: 'Papan sinyal' }) },
                { to: '/leaderboard', label: tr(language, { ko: '리더보드', en: 'Leaderboard', ja: 'リーダーボード', th: 'ลีดเดอร์บอร์ด', vi: 'Bảng xếp hạng', id: 'Papan peringkat' }) },
              ])}
            </div>
          </div>

          {/* 2 — how to use */}
          <div style={{ ...cardS, display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div style={numS}>2</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 16.5, marginBottom: 4 }}>
                <span aria-hidden style={{ marginRight: 8 }}>🔁</span>
                {tr(language, { ko: '사용 방법 — 신호에서 포지션까지', en: 'How to use — from signal to position', ja: '使い方 — シグナルからポジションへ', th: 'วิธีใช้ — จากสัญญาณสู่สถานะ', vi: 'Cách dùng — từ tín hiệu đến vị thế', id: 'Cara pakai — dari sinyal ke posisi' })}
              </div>
              <div style={{ fontSize: 14, color: V.mut }}>
                {tr(language, {
                  ko: '마켓에서 신호를 보고, 자동매매 규칙이나 AI 위임 런이 그 신호로 매매하며, 결과 포지션과 손익을 포지션 페이지에서 추적합니다. 모든 주문은 리스크 게이트(켈리 사이징 → 한도 → 서킷 브레이커)를 통과합니다.',
                  en: 'Watch signals in Market, let an automation rule or AI-delegated run trade on them, and track the resulting positions and P&L. Every order passes the risk gate: Kelly sizing → limits → circuit breaker.',
                  ja: 'マーケットでシグナルを見て、自動売買ルールやAI委任ランがそれで売買し、結果のポジションと損益をポジションページで追跡します。すべての注文はリスクゲート（ケリーサイジング→上限→サーキットブレーカー）を通ります。',
                  th: 'ดูสัญญาณในตลาด ให้กฎอัตโนมัติหรือรันที่มอบหมายให้ AI เทรดตามสัญญาณ แล้วติดตามสถานะและกำไรขาดทุน ทุกคำสั่งผ่านประตูความเสี่ยง: เคลลี → ลิมิต → เซอร์กิตเบรกเกอร์',
                  vi: 'Xem tín hiệu ở Thị trường, để quy tắc tự động hoặc run ủy quyền AI giao dịch theo, rồi theo dõi vị thế và lãi lỗ. Mọi lệnh đều qua cổng rủi ro: Kelly → hạn mức → ngắt mạch.',
                  id: 'Pantau sinyal di Pasar, biarkan aturan otomatisasi atau run yang didelegasikan ke AI bertransaksi berdasarkan sinyal itu, lalu lacak posisi dan laba-ruginya. Setiap order melewati gerbang risiko: penentuan ukuran Kelly → batas → pemutus sirkuit.',
                })}
              </div>
              {linkRow([
                { to: '/automation', label: tr(language, { ko: '자동매매', en: 'Automation', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động hóa', id: 'Otomatisasi' }) },
                { to: '/market', label: tr(language, { ko: '마켓', en: 'Market', ja: 'マーケット', th: 'ตลาด', vi: 'Thị trường', id: 'Pasar' }) },
                { to: '/positions', label: tr(language, { ko: '포지션', en: 'Positions', ja: 'ポジション', th: 'สถานะ', vi: 'Vị thế', id: 'Posisi' }) },
              ])}
            </div>
          </div>

          {/* 3 — subscription information */}
          <div style={{ ...cardS, display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div style={numS}>3</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 16.5, marginBottom: 4 }}>
                <span aria-hidden style={{ marginRight: 8 }}>💎</span>
                {tr(language, { ko: '구독 안내', en: 'Subscription information', ja: '購読のご案内', th: 'ข้อมูลสมาชิก', vi: 'Thông tin gói đăng ký', id: 'Informasi langganan' })}
              </div>
              <div style={{ fontSize: 14, color: V.mut }}>
                {tr(language, {
                  ko: '새 계정은 카드 등록 없이 7일 무료 체험(Junior)으로 시작합니다. 체험이 끝나면 자동매매가 멈추고 구독 페이지가 열립니다 — 자동 결제는 없습니다.',
                  en: 'New accounts start on a card-free 7-day Junior trial. When it ends your automation pauses and the subscribe page opens — nothing is charged automatically.',
                  ja: '新しいアカウントはカード登録なしの7日間Junior無料体験から始まります。終了すると自動売買が停止し、購読ページが開きます — 自動課金はありません。',
                  th: 'บัญชีใหม่เริ่มด้วยการทดลองใช้ Junior ฟรี 7 วันโดยไม่ต้องผูกบัตร เมื่อสิ้นสุด การเทรดอัตโนมัติจะหยุดและหน้าสมัครสมาชิกจะเปิดขึ้น — ไม่มีการเรียกเก็บเงินอัตโนมัติ',
                  vi: 'Tài khoản mới bắt đầu với 7 ngày dùng thử Junior miễn phí, không cần thẻ. Khi hết hạn, tự động hóa tạm dừng và trang đăng ký mở ra — không có khoản phí tự động nào.',
                  id: 'Akun baru dimulai dengan uji coba Junior 7 hari tanpa kartu. Saat berakhir, otomatisasi Anda berhenti dan halaman langganan terbuka — tidak ada tagihan otomatis.',
                })}
              </div>
              {plans.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8, marginTop: 10 }}>
                  {plans.map((p: any) => (
                    <div key={p.code} style={{ border: `1px solid ${V.line}`, borderRadius: 10, padding: '8px 12px' }}>
                      <div style={{ fontWeight: 700, fontSize: 13.5 }}>{PLAN_NAMES[p.code] || p.name}</div>
                      <div style={{ fontSize: 13, color: V.mut }}>
                        {p.contact_only
                          ? tr(language, { ko: '문의', en: 'Contact us', ja: 'お問い合わせ', th: 'ติดต่อเรา', vi: 'Liên hệ', id: 'Hubungi kami' })
                          : <>${Number(p.price_usd).toLocaleString()}<span style={{ fontSize: 11.5, color: V.faint }}>{perMonth}</span></>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {linkRow([
                { to: '/account/subscription', label: tr(language, { ko: '내 구독 관리', en: 'My subscription', ja: '購読を管理', th: 'การสมัครของฉัน', vi: 'Gói của tôi', id: 'Langganan saya' }) },
                { to: '/subscribe', label: tr(language, { ko: '플랜 선택', en: 'Choose a plan', ja: 'プランを選ぶ', th: 'เลือกแผน', vi: 'Chọn gói', id: 'Pilih paket' }) },
              ])}
            </div>
          </div>

          {/* 4 — step-by-step guide, with the LIVE phone-verify control */}
          <div style={{ ...cardS, display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div style={numS}>4</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 16.5, marginBottom: 4 }}>
                <span aria-hidden style={{ marginRight: 8 }}>🧭</span>
                {tr(language, { ko: '단계별 시작 가이드', en: 'Step-by-step guide', ja: 'ステップバイステップガイド', th: 'ไกด์ทีละขั้น', vi: 'Hướng dẫn từng bước', id: 'Panduan langkah demi langkah' })}
              </div>
              {stepLine(1, tr(language, { ko: '휴대폰 번호를 인증하세요 — SMS 알림과 SMS 비밀번호 재설정이 열립니다. 아래에서 바로 할 수 있습니다.', en: 'Verify your phone — it unlocks SMS alerts and SMS password reset. You can do it right here below.', ja: '電話番号を認証しましょう — SMS通知とSMSパスワード再設定が使えるようになります。この下でそのまま行えます。', th: 'ยืนยันเบอร์โทรของคุณ — ปลดล็อกการแจ้งเตือน SMS และการรีเซ็ตรหัสผ่านทาง SMS ทำได้ที่ด้านล่างนี้เลย', vi: 'Xác minh số điện thoại — mở khóa cảnh báo SMS và đặt lại mật khẩu qua SMS. Làm ngay bên dưới.', id: 'Verifikasi nomor ponsel Anda — membuka peringatan SMS dan reset kata sandi lewat SMS. Bisa langsung dilakukan di bawah ini.' }))}
              <div style={{ border: `1px dashed ${V.line}`, borderRadius: 10, padding: '4px 14px 14px', margin: '8px 0 4px' }}>
                <PhoneVerifyCard userToken={userToken} />
              </div>
              {stepLine(2, tr(language, { ko: '설정에서 지역과 언어를 확인하세요 — 거래 가능한 시장과 개장 시각이 여기에 따라 달라집니다.', en: 'Confirm your region and language in Settings — they decide which markets you can trade and when they open.', ja: '設定で地域と言語を確認しましょう — 取引できる市場と開場時刻がこれで決まります。', th: 'ยืนยันภูมิภาคและภาษาในตั้งค่า — สิ่งนี้กำหนดตลาดที่เทรดได้และเวลาเปิด', vi: 'Xác nhận khu vực và ngôn ngữ trong Cài đặt — chúng quyết định thị trường bạn giao dịch được và giờ mở cửa.', id: 'Konfirmasi wilayah dan bahasa di Pengaturan — keduanya menentukan pasar yang bisa Anda perdagangkan dan jam bukanya.' }))}
              {stepLine(3, tr(language, { ko: '체험이 끝나기 전에 플랜을 선택하세요.', en: 'Pick a plan before your trial ends.', ja: '体験が終わる前にプランを選びましょう。', th: 'เลือกแผนก่อนการทดลองใช้จะสิ้นสุด', vi: 'Chọn gói trước khi hết hạn dùng thử.', id: 'Pilih paket sebelum masa uji coba berakhir.' }))}
              {stepLine(4, tr(language, { ko: '자동매매에서 첫 규칙이나 AI 위임 런을 시작하세요 — 전부 모의 원장이라 안전합니다.', en: 'Start your first rule or AI-delegated run in Automation — it is all on the simulated ledger, so it is safe.', ja: '自動売買で最初のルールかAI委任ランを始めましょう — すべて模擬台帳なので安全です。', th: 'เริ่มกฎแรกหรือรันที่มอบหมายให้ AI ในเทรดอัตโนมัติ — ทั้งหมดอยู่บนบัญชีจำลอง ปลอดภัย', vi: 'Bắt đầu quy tắc đầu tiên hoặc run ủy quyền AI trong Tự động hóa — tất cả trên sổ mô phỏng nên an toàn.', id: 'Mulai aturan pertama atau run yang didelegasikan ke AI di Otomatisasi — semuanya di buku simulasi, jadi aman.' }))}
              {linkRow([
                { to: '/getting-started', label: tr(language, { ko: '초보자 가이드 전체 보기', en: 'Full beginner guide', ja: '初心者ガイド全文', th: 'คู่มือผู้เริ่มต้นฉบับเต็ม', vi: 'Hướng dẫn đầy đủ', id: 'Panduan pemula lengkap' }) },
                { to: '/docs', label: tr(language, { ko: '문서', en: 'Docs', ja: 'ドキュメント', th: 'เอกสาร', vi: 'Tài liệu', id: 'Dokumen' }) },
              ])}
            </div>
          </div>
        </div>

        {/* dismissal — a real checkbox, per the owner's correction */}
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 22, fontSize: 13.5, color: V.mut, cursor: 'pointer' }}>
          <input type="checkbox" checked={dismissed} onChange={e => toggleDismiss(e.target.checked)} />
          {tr(language, { ko: '다음부터 웰컴 페이지를 표시하지 않기', en: 'Do not show this welcome page next time', ja: '次回からウェルカムページを表示しない', th: 'ไม่ต้องแสดงหน้าต้อนรับนี้อีก', vi: 'Không hiển thị trang chào mừng này lần sau', id: 'Jangan tampilkan halaman sambutan ini lagi' })}
        </label>
        <div style={{ fontSize: 12, color: V.faint, marginTop: 6 }}>
          {tr(language, { ko: '이 페이지는 프로필 메뉴에서 언제든 다시 열 수 있습니다.', en: 'You can always reopen this page from the profile menu.', ja: 'このページはプロフィールメニューからいつでも再表示できます。', th: 'เปิดหน้านี้ได้เสมอจากเมนูโปรไฟล์', vi: 'Bạn luôn có thể mở lại trang này từ menu hồ sơ.', id: 'Anda selalu dapat membuka kembali halaman ini dari menu profil.' })}
        </div>
      </div>
    </div>
  )
}
