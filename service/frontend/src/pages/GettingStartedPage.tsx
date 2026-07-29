import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../appShared'
import { tr, translations } from '../i18n'
import { buildNavSections } from '../appChrome'
import { resolveGuide, type PageGuide } from '../guides'

// Beginner overview: what Sooppiy is, a first-15-minutes path, and a plain
// explanation of every menu. Menu labels come from buildNavSections and the
// one-line descriptions reuse each page's own localized guide summary, so this
// page never drifts from the real navigation or the per-page guides.

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
  sans: 'var(--font-sans, system-ui, sans-serif)',
  mono: 'var(--font-mono, ui-monospace, monospace)',
}

const wrap: any = { maxWidth: 940, margin: '0 auto', padding: '0 20px' }
const cardS: any = { background: V.card, border: `1px solid ${V.line}`, borderRadius: 14, padding: '16px 18px' }
const h2S: any = { fontFamily: V.display, fontWeight: 700, fontSize: 'clamp(22px,3vw,30px)', letterSpacing: '-0.01em', lineHeight: 1.12, color: V.ink, margin: '6px 0 6px' }
const kicker: any = { fontFamily: V.mono, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: V.accent, fontWeight: 600 }

export function GettingStartedPage() {
  const { language } = useLanguage()
  const t = translations[language]
  // Owner-only items (e.g. internal docs) are hidden from ordinary users, so
  // leave them out of the beginner overview too.
  const navSections = buildNavSections(language, t, { discussion: 0, strategy: 0, experiment: 0 })
    .map(s => ({ ...s, items: s.items.filter((i: any) => !i.ownerOnly && i.path !== '/getting-started') }))

  // An extra "Account & profile" group — these live in the profile/account menus
  // rather than the main nav, but a beginner still needs them explained.
  const accountGroup = {
    label: tr(language, { ko: '계정 · 프로필', en: 'Account & profile', ja: 'アカウント・プロフィール', th: 'บัญชี·โปรไฟล์', vi: 'Tài khoản & hồ sơ', id: 'Akun & profil' }),
    items: [
      { path: '/my-trading', icon: '◱', label: tr(language, { ko: '내 트레이딩', en: 'My Trading', ja: 'マイトレード', th: 'การเทรดของฉัน', vi: 'Giao dịch của tôi', id: 'Trading saya' }) },
      { path: '/notifications', icon: '🔔', label: tr(language, { ko: '알림', en: 'Notifications', ja: '通知', th: 'การแจ้งเตือน', vi: 'Thông báo', id: 'Notifikasi' }) },
      { path: '/support', icon: '💬', label: tr(language, { ko: '고객지원', en: 'Support', ja: 'サポート', th: 'ฝ่ายสนับสนุน', vi: 'Hỗ trợ', id: 'Dukungan' }) },
      { path: '/subscribe', icon: '★', label: tr(language, { ko: '멤버십', en: 'Membership', ja: 'メンバーシップ', th: 'สมาชิก', vi: 'Thành viên', id: 'Keanggotaan' }) },
      { path: '/settings', icon: '⚙', label: tr(language, { ko: '설정', en: 'Settings', ja: '設定', th: 'ตั้งค่า', vi: 'Cài đặt', id: 'Pengaturan' }) },
    ],
  }
  const groups = [...navSections, accountGroup]

  // Load each page's own guide summary once, keyed by path.
  const [summaries, setSummaries] = useState<Record<string, PageGuide | null>>({})
  useEffect(() => {
    let alive = true
    const paths = Array.from(new Set(groups.flatMap(g => g.items.map(i => i.path))))
    Promise.all(paths.map(p => resolveGuide(p).then(g => [p, g] as const).catch(() => [p, null] as const)))
      .then(entries => { if (alive) setSummaries(Object.fromEntries(entries)) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language])

  const steps = [
    {
      t: tr(language, { ko: '가입하고 $100,000 페이퍼 계좌 받기', en: 'Sign up and get a $100,000 paper account', ja: '登録して10万ドルの模擬口座を受け取る', th: 'สมัครและรับบัญชีเปเปอร์ $100,000', vi: 'Đăng ký và nhận tài khoản paper $100.000', id: 'Daftar dan dapatkan akun paper senilai $100.000' }),
      d: tr(language, { ko: '무료로 가입하면 실제 리스크가 없는 모의 자금 $100,000이 바로 지급됩니다. 실제 돈은 필요하지 않습니다.', en: 'Join for free and a $100,000 simulated balance is credited immediately — no real money, no real risk.', ja: '無料で登録すると、実リスクのない模擬資金10万ドルがすぐに付与されます。実際のお金は不要です。', th: 'สมัครฟรีแล้วรับเงินจำลอง $100,000 ทันที ไม่มีเงินจริง ไม่มีความเสี่ยงจริง', vi: 'Đăng ký miễn phí và được cấp ngay số dư mô phỏng $100.000 — không tiền thật, không rủi ro thật.', id: 'Bergabunglah gratis dan saldo simulasi $100.000 langsung dikreditkan — tanpa uang sungguhan, tanpa risiko nyata.' }),
    },
    {
      t: tr(language, { ko: '마켓과 리더보드 둘러보기', en: 'Explore Markets and the Leaderboard', ja: 'マーケットとリーダーボードを見る', th: 'สำรวจตลาดและลีดเดอร์บอร์ด', vi: 'Khám phá Thị trường và Bảng xếp hạng', id: 'Jelajahi Pasar dan Papan Peringkat' }),
      d: tr(language, { ko: '마켓에서 실시간 신호를 보고, 리더보드에서 어떤 에이전트가 실제로 잘하고 있는지 확인하세요.', en: 'See live signals in Markets and check the Leaderboard to see which agents are actually performing.', ja: 'マーケットでライブシグナルを見て、リーダーボードでどのエージェントが実際に好調かを確認します。', th: 'ดูสัญญาณสดในตลาด และเช็กลีดเดอร์บอร์ดว่าเอเจนต์ไหนทำได้ดีจริง', vi: 'Xem tín hiệu trực tiếp ở Thị trường và kiểm tra Bảng xếp hạng để biết agent nào thực sự hiệu quả.', id: 'Lihat sinyal langsung di Pasar dan cek Papan Peringkat untuk melihat agen mana yang benar-benar berkinerja baik.' }),
    },
    {
      t: tr(language, { ko: '첫 페이퍼 거래 또는 카피 트레이딩 해보기', en: 'Make your first paper trade — or copy a leader', ja: '最初の模擬取引、またはコピートレードを試す', th: 'ลองเทรดเปเปอร์ครั้งแรก หรือก๊อปปี้เทรด', vi: 'Thực hiện giao dịch paper đầu tiên — hoặc copy một leader', id: 'Lakukan transaksi paper pertama Anda — atau salin seorang leader' }),
      d: tr(language, { ko: '현물·선물에서 직접 매매하거나, 잘하는 트레이더를 팔로우하면 그 신호가 내 원장에 자동으로 미러링됩니다.', en: 'Trade yourself in Spot or Futures, or follow a strong trader and their signals mirror onto your ledger automatically.', ja: '現物・先物で自分で売買するか、優れたトレーダーをフォローすると、そのシグナルが自分の台帳へ自動でミラーされます。', th: 'เทรดเองในสปอต·ฟิวเจอร์ส หรือติดตามเทรดเดอร์เก่ง แล้วสัญญาณจะมิเรอร์มายังบัญชีของคุณอัตโนมัติ', vi: 'Tự giao dịch ở Spot hoặc Futures, hoặc theo dõi một trader giỏi và tín hiệu của họ tự sao chép vào sổ của bạn.', id: 'Bertransaksi sendiri di Spot atau Futures, atau ikuti trader yang kuat dan sinyal mereka otomatis tersalin ke buku Anda.' }),
    },
    {
      t: tr(language, { ko: '자동매매 켜기', en: 'Turn on Automation', ja: '自動売買をオンにする', th: 'เปิดเทรดอัตโนมัติ', vi: 'Bật Tự động hóa', id: 'Aktifkan Otomatisasi' }),
      d: tr(language, { ko: '규칙을 하나 만들거나 AI 플릿을 실행하세요. 모든 주문은 켈리 사이징 → 한도 → 서킷 브레이커의 리스크 게이트를 통과합니다.', en: 'Create a rule or launch an AI fleet. Every order passes the risk gate: Kelly sizing → limits → circuit breaker.', ja: 'ルールを1つ作るか、AIフリートを起動します。すべての注文はケリーサイジング→上限→サーキットブレーカーのリスクゲートを通ります。', th: 'สร้างกฎหนึ่งข้อหรือเปิดฟลีต AI ทุกคำสั่งจะผ่านประตูความเสี่ยง: เคลลี → ลิมิต → เซอร์กิตเบรกเกอร์', vi: 'Tạo một quy tắc hoặc khởi chạy một fleet AI. Mọi lệnh đều qua cổng rủi ro: Kelly → hạn mức → ngắt mạch.', id: 'Buat aturan atau luncurkan fleet AI. Setiap order melewati gerbang risiko: penentuan ukuran Kelly → batas → pemutus sirkuit.' }),
    },
    {
      t: tr(language, { ko: '지켜보고 복기하기', en: 'Watch and review', ja: '観察して振り返る', th: 'เฝ้าดูและทบทวน', vi: 'Theo dõi và xem lại', id: 'Pantau dan tinjau' }),
      d: tr(language, { ko: '모니터링·포지션·내 자산에서 실시간 손익과 모든 판단 기록을 확인하세요. 되는 것은 남기고, 지는 것은 잘라내세요.', en: 'Track live P&L and every decision in Monitoring, Positions, and My Assets. Keep what works, prune what loses.', ja: 'モニタリング・ポジション・資産でライブ損益とすべての判断記録を確認します。勝ちを残し、負けを削ります。', th: 'ติดตาม P&L สดและทุกการตัดสินใจในการติดตาม·สถานะ·ทรัพย์สิน เก็บที่ได้ผล ตัดที่แพ้', vi: 'Theo dõi P&L trực tiếp và mọi quyết định ở Giám sát, Vị thế và Tài sản. Giữ cái hiệu quả, cắt cái thua.', id: 'Pantau laba rugi langsung dan setiap keputusan di Pemantauan, Posisi, dan Aset Saya. Pertahankan yang berhasil, pangkas yang merugi.' }),
    },
    {
      t: tr(language, { ko: '준비되면 라이브로 (검증 먼저)', en: 'Go live only when ready (verify first)', ja: '準備できたらライブへ（まず検証）', th: 'ไปไลฟ์เมื่อพร้อม (ยืนยันก่อน)', vi: 'Chỉ live khi sẵn sàng (xác minh trước)', id: 'Beralih ke live hanya saat siap (verifikasi dulu)' }),
      d: tr(language, { ko: '계좌 메뉴에서 본인 Alpaca·Binance·IBKR 계좌를 연결하세요. 라이브는 기본 비활성이며, 검증하고 각 브로커 약관에 동의한 뒤에만 시작됩니다 — AI 자동 런은 계속 페이퍼로 유지됩니다.', en: 'Connect your own Alpaca, Binance, or IBKR account in Accounts. Live is off by default and starts only after you verify and accept each broker’s terms — AI auto-runs stay on paper.', ja: 'アカウントメニューで本人のAlpaca・Binance・IBKR口座を接続します。ライブは既定で無効、検証し各社の規約に同意した後にのみ開始します — AIの自動ランはペーパーのままです。', th: 'เชื่อมบัญชี Alpaca, Binance หรือ IBKR ของคุณเองในเมนูบัญชี ไลฟ์ปิดโดยค่าเริ่มต้น เริ่มเฉพาะหลังยืนยันและยอมรับข้อกำหนดของแต่ละโบรกเกอร์ — การรันอัตโนมัติของ AI ยังอยู่บนเปเปอร์', vi: 'Kết nối tài khoản Alpaca, Binance hoặc IBKR của bạn trong mục Tài khoản. Live tắt mặc định, chỉ bắt đầu sau khi bạn xác minh và chấp nhận điều khoản từng broker — các lần AI tự chạy vẫn ở paper.', id: 'Hubungkan akun Alpaca, Binance, atau IBKR Anda sendiri di Akun. Mode live nonaktif secara bawaan dan hanya dimulai setelah Anda memverifikasi dan menerima ketentuan masing-masing broker — run otomatis AI tetap berjalan di paper.' }),
    },
  ]

  return (
    <div style={{ minHeight: '100vh', background: V.bg, color: V.ink, fontFamily: V.sans, lineHeight: 1.55 }}>
      <div style={{ ...wrap, paddingTop: 28, paddingBottom: 56 }}>

        {/* intro */}
        <div style={kicker}>{tr(language, { ko: '시작하기', en: 'GETTING STARTED', ja: 'はじめに', th: 'เริ่มต้น', vi: 'BẮT ĐẦU', id: 'PANDUAN AWAL' })}</div>
        <h1 style={{ fontFamily: V.display, fontWeight: 800, fontSize: 'clamp(28px,4.4vw,44px)', lineHeight: 1.08, letterSpacing: '-0.02em', margin: '10px 0 12px' }}>
          {tr(language, { ko: 'Sooppiy 초보자 가이드', en: 'A beginner’s guide to Sooppiy', ja: 'Sooppiy 初心者ガイド', th: 'คู่มือผู้เริ่มต้น Sooppiy', vi: 'Hướng dẫn Sooppiy cho người mới', id: 'Panduan Sooppiy untuk pemula' })}
        </h1>
        <p style={{ fontSize: 16, color: V.mut, maxWidth: '64ch', margin: '0 0 10px' }}>
          {tr(language, {
            ko: 'Sooppiy는 시장 신호를 측정해 당신의 규칙대로 매매하는 AI 트레이딩 플랫폼입니다. 모두 페이퍼(모의)로 시작해 리스크 없이 배우고, 준비되면 본인 브로커에서 라이브로 전환합니다.',
            en: 'Sooppiy is an AI trading platform that measures market signals and trades on your rules. Everyone starts on paper (simulated) to learn risk-free, then switches to live on their own broker when ready.',
            ja: 'Sooppiyは市場シグナルを測定し、あなたのルールで売買するAIトレーディングプラットフォームです。全員がペーパー（模擬）から始めてリスクなく学び、準備ができたら本人のブローカーでライブに切り替えます。',
            th: 'Sooppiy คือแพลตฟอร์มเทรด AI ที่วัดสัญญาณตลาดและเทรดตามกฎของคุณ ทุกคนเริ่มด้วยเปเปอร์ (จำลอง) เพื่อเรียนรู้แบบไร้ความเสี่ยง แล้วเปลี่ยนไปไลฟ์บนโบรกเกอร์ของตัวเองเมื่อพร้อม',
            vi: 'Sooppiy là nền tảng giao dịch AI đo tín hiệu thị trường và giao dịch theo quy tắc của bạn. Mọi người bắt đầu bằng paper (mô phỏng) để học không rủi ro, rồi chuyển sang live trên broker của mình khi sẵn sàng.',
            id: 'Sooppiy adalah platform trading AI yang mengukur sinyal pasar dan bertransaksi sesuai aturan Anda. Semua orang memulai di paper (simulasi) untuk belajar tanpa risiko, lalu beralih ke live pada broker mereka sendiri saat sudah siap.',
          })}
        </p>

        {/* first 15 minutes */}
        <section style={{ marginTop: 30 }}>
          <div style={kicker}>{tr(language, { ko: '처음 15분', en: 'YOUR FIRST 15 MINUTES', ja: '最初の15分', th: '15 นาทีแรกของคุณ', vi: '15 phút đầu tiên', id: '15 MENIT PERTAMA ANDA' })}</div>
          <h2 style={h2S}>{tr(language, { ko: '여섯 단계로 시작', en: 'Get going in six steps', ja: '6ステップで開始', th: 'เริ่มใน 6 ขั้นตอน', vi: 'Bắt đầu trong sáu bước', id: 'Mulai dalam enam langkah' })}</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {steps.map((s, i) => (
              <div key={i} style={{ ...cardS, display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{ flexShrink: 0, width: 30, height: 30, borderRadius: 999, background: V.accent, color: V.accentOn, fontFamily: V.mono, fontWeight: 700, fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{i + 1}</div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15.5, marginBottom: 3 }}>{s.t}</div>
                  <div style={{ fontSize: 14, color: V.mut }}>{s.d}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* every menu explained */}
        <section style={{ marginTop: 34 }}>
          <div style={kicker}>{tr(language, { ko: '모든 메뉴', en: 'EVERY MENU', ja: 'すべてのメニュー', th: 'ทุกเมนู', vi: 'MỌI MENU', id: 'SETIAP MENU' })}</div>
          <h2 style={h2S}>{tr(language, { ko: '메뉴별 설명', en: 'What each menu does', ja: '各メニューの役割', th: 'แต่ละเมนูทำอะไร', vi: 'Mỗi menu làm gì', id: 'Fungsi masing-masing menu' })}</h2>
          <p style={{ fontSize: 13.5, color: V.faint, margin: '4px 0 16px' }}>
            {tr(language, { ko: '메뉴 이름을 누르면 해당 페이지로 이동합니다. 각 페이지에서 우측 상단 가이드 버튼을 누르면 더 자세한 설명을 볼 수 있습니다.', en: 'Click a menu name to open that page. On each page, the guide button (top-right) shows a more detailed walkthrough.', ja: 'メニュー名を押すとそのページへ移動します。各ページ右上のガイドボタンでより詳しい説明を見られます。', th: 'คลิกชื่อเมนูเพื่อเปิดหน้านั้น ในแต่ละหน้า ปุ่มคู่มือ (มุมขวาบน) จะแสดงคำอธิบายละเอียดขึ้น', vi: 'Nhấp tên menu để mở trang đó. Trên mỗi trang, nút hướng dẫn (góc trên phải) hiển thị hướng dẫn chi tiết hơn.', id: 'Klik nama menu untuk membuka halamannya. Di setiap halaman, tombol panduan (kanan atas) menampilkan penjelasan yang lebih rinci.' })}
          </p>

          <div style={{ display: 'grid', gap: 20 }}>
            {groups.map(group => (
              <div key={group.label}>
                <div style={{ fontFamily: V.mono, fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: V.ink, marginBottom: 10, paddingBottom: 6, borderBottom: `1px solid ${V.line}` }}>{group.label}</div>
                <div style={{ display: 'grid', gap: 8 }}>
                  {group.items.map(item => {
                    const g = summaries[item.path]
                    const summary = g?.summary?.[language]
                    return (
                      <Link key={item.path} to={item.path} style={{ ...cardS, display: 'flex', gap: 12, alignItems: 'flex-start', textDecoration: 'none', color: 'inherit' }}>
                        <span aria-hidden style={{ flexShrink: 0, fontSize: 16, width: 22, textAlign: 'center', color: V.accent }}>{(item as any).icon || '·'}</span>
                        <span>
                          <span style={{ fontWeight: 700, fontSize: 15, color: V.ink }}>{item.label}</span>
                          <span style={{ display: 'block', fontSize: 13.5, color: V.mut, marginTop: 2 }}>
                            {summary || tr(language, { ko: '이 페이지를 열어 확인하세요.', en: 'Open this page to explore it.', ja: 'このページを開いて確認してください。', th: 'เปิดหน้านี้เพื่อดู', vi: 'Mở trang này để khám phá.', id: 'Buka halaman ini untuk menjelajahinya.' })}
                          </span>
                        </span>
                      </Link>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* paper-first / live note */}
        <section style={{ marginTop: 30 }}>
          <div style={{ ...cardS, borderLeft: `3px solid ${V.accent}` }}>
            <div style={{ fontWeight: 700, fontSize: 15.5, marginBottom: 5 }}>
              {tr(language, { ko: '페이퍼 먼저, 그다음 라이브', en: 'Paper first, then live', ja: 'まず模擬、次にライブ', th: 'เปเปอร์ก่อน แล้วค่อยไลฟ์', vi: 'Paper trước, rồi live', id: 'Paper dulu, baru live' })}
            </div>
            <div style={{ fontSize: 14, color: V.mut }}>
              {tr(language, {
                ko: '기본적으로 모든 거래는 모의이며 실제 자금이 위험에 노출되지 않습니다. 라이브 브로커 거래는 선택 사항이고 기본 비활성이며, 본인이 연결한 계좌에서 각 브로커 약관에 동의한 뒤에만 실행됩니다. AI 자동 런은 계속 모의 원장에 남습니다. 이 사이트의 어떤 내용도 투자 자문이 아닙니다.',
                en: 'By default all trading is simulated and no real funds are at risk. Live brokerage trading is optional and off by default — it runs only on an account you connect yourself, after you accept each broker’s terms. AI auto-runs stay on the simulated ledger. Nothing here is investment advice.',
                ja: '既定ではすべての取引は模擬で、実資金はリスクにさらされません。ライブのブローカー取引は任意で既定は無効 — 本人が接続した口座で各社の規約に同意した後にのみ実行されます。AIの自動ランは模擬台帳に残ります。ここにある内容は投資助言ではありません。',
                th: 'โดยค่าเริ่มต้นทุกการเทรดเป็นแบบจำลองและไม่มีเงินจริงเสี่ยง การเทรดไลฟ์ผ่านโบรกเกอร์เป็นทางเลือกและปิดอยู่ — ทำงานเฉพาะบนบัญชีที่คุณเชื่อมเอง หลังยอมรับข้อกำหนดของแต่ละโบรกเกอร์ การรันอัตโนมัติของ AI ยังอยู่บนบัญชีจำลอง ไม่มีเนื้อหาใดเป็นคำแนะนำการลงทุน',
                vi: 'Mặc định mọi giao dịch đều mô phỏng và không tiền thật nào chịu rủi ro. Giao dịch live qua broker là tùy chọn và tắt mặc định — chỉ chạy trên tài khoản bạn tự kết nối, sau khi chấp nhận điều khoản từng broker. Các lần AI tự chạy vẫn ở sổ mô phỏng. Không nội dung nào ở đây là lời khuyên đầu tư.',
                id: 'Secara bawaan seluruh trading bersifat simulasi dan tidak ada dana sungguhan yang dipertaruhkan. Trading live melalui broker bersifat opsional dan nonaktif secara bawaan — hanya berjalan pada akun yang Anda hubungkan sendiri, setelah Anda menerima ketentuan masing-masing broker. Run otomatis AI tetap pada buku simulasi. Tidak ada satu pun di sini yang merupakan nasihat investasi.',
              })}
            </div>
          </div>
        </section>

      </div>
    </div>
  )
}

export default GettingStartedPage
