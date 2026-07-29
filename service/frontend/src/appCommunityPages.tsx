import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { Link, useLocation, useNavigate } from 'react-router-dom'

import { API_BASE, COMMUNITY_FEED_PAGE_SIZE, MARKETS, useLanguage } from './appShared'
import AuthBackground from './components/AuthBackground'
import { SymbolSelect } from './components/SymbolSelect'
import { tr } from './i18n'
import type { Language } from './i18n'

// "At a glance" pipeline section for the auth pages, drawn in the same visual
// language as the docs guide's "§0 한눈에 보기 — 10단계 파이프라인": a strip of
// STEP chips + a compact SVG flow. Login shows the workspace loop a returning
// member re-enters; register shows the signup-to-live-broker journey.
function AuthGlance({ mode, language }: { mode: 'login' | 'register'; language: Language }) {
  // SVG text styles (mirrors the guide's .sv-t / .sv-s / .sv-lb)
  const t: any = { fontSize: 12, fontWeight: 600, fill: 'var(--text-primary,#e8e2d8)', fontFamily: 'system-ui,"Apple SD Gothic Neo",sans-serif' }
  const s: any = { fontSize: 10.5, fontWeight: 500, fill: 'var(--text-secondary,#8a8073)', fontFamily: 'system-ui,"Apple SD Gothic Neo",sans-serif' }
  const box = { fill: 'var(--bg-secondary,rgba(255,255,255,0.03))', stroke: 'var(--border-color,#3a3a3a)', strokeWidth: 1 }
  const acc = { fill: 'rgba(194,106,69,0.12)', stroke: 'var(--accent-primary,#c26a45)', strokeWidth: 1 }
  const line = { stroke: 'var(--text-muted,#a89f92)', strokeWidth: 1.4, fill: 'none' }
  const accline = { stroke: 'var(--accent-primary,#c26a45)', strokeWidth: 1.6, fill: 'none', strokeDasharray: '5 4' }

  const chip = (no: string, label: string) => (
    <div key={no + label} style={{ flex: '1 1 88px', background: 'var(--bg-secondary,rgba(255,255,255,0.03))', border: '1px solid var(--border-color,#3a3a3a)', borderRadius: 10, padding: '9px 8px', textAlign: 'center' as const }}>
      <b style={{ display: 'block', fontSize: 11, color: 'var(--accent-primary,#c26a45)', fontVariantNumeric: 'tabular-nums' }}>{no}</b>
      <span style={{ fontSize: 12, fontWeight: 700, lineHeight: 1.3, display: 'block', marginTop: 2 }}>{label}</span>
    </div>
  )

  const heading = mode === 'login'
    ? tr(language, { ko: '한눈에 보기 — 로그인 후 워크플로', en: 'At a glance — your workflow after sign-in', ja: 'ひと目でわかる — ログイン後のワークフロー', th: 'ดูภาพรวม — เวิร์กโฟลว์หลังเข้าสู่ระบบ', vi: 'Nhìn nhanh — quy trình sau khi đăng nhập', id: 'Sekilas — alur kerja Anda setelah masuk' })
    : tr(language, { ko: '한눈에 보기 — 가입부터 실계좌까지', en: 'At a glance — from signup to live trading', ja: 'ひと目でわかる — 登録から実口座まで', th: 'ดูภาพรวม — จากสมัครถึงบัญชีจริง', vi: 'Nhìn nhanh — từ đăng ký đến tài khoản thật', id: 'Sekilas — dari pendaftaran hingga trading live' })

  const STEP = (n: number) => `STEP ${n}`

  const chips = mode === 'login'
    ? [
        chip(STEP(1), tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าระบบ', vi: 'Đăng nhập', id: 'Masuk' })),
        chip(STEP(2), tr(language, { ko: 'AI 분석', en: 'AI analysis', ja: 'AI分析', th: 'วิเคราะห์ AI', vi: 'Phân tích AI', id: 'Analisis AI' })),
        chip(STEP(3), tr(language, { ko: '자동매매', en: 'Auto-trade', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động', id: 'Trading otomatis' })),
        chip(STEP(4), tr(language, { ko: '리스크 게이트', en: 'Risk gate', ja: 'リスクゲート', th: 'ประตูความเสี่ยง', vi: 'Cổng rủi ro', id: 'Gerbang risiko' })),
        chip(STEP(5), tr(language, { ko: '체결·알림', en: 'Fills & alerts', ja: '約定・通知', th: 'คำสั่ง·แจ้งเตือน', vi: 'Khớp lệnh·báo', id: 'Eksekusi & peringatan' })),
      ]
    : [
        chip(STEP(1), tr(language, { ko: '1분 가입', en: '1-min signup', ja: '1分登録', th: 'สมัคร 1 นาที', vi: 'Đăng ký 1 phút', id: 'Daftar 1 menit' })),
        chip(STEP(2), tr(language, { ko: '웰컴 자본', en: 'Welcome capital', ja: 'ウェルカム資金', th: 'ทุนต้อนรับ', vi: 'Vốn chào mừng', id: 'Modal sambutan' })),
        chip(STEP(3), tr(language, { ko: 'AI 분석', en: 'AI analysis', ja: 'AI分析', th: 'วิเคราะห์ AI', vi: 'Phân tích AI', id: 'Analisis AI' })),
        chip(STEP(4), tr(language, { ko: '자동매매', en: 'Auto-trade', ja: '自動売買', th: 'เทรดอัตโนมัติ', vi: 'Tự động', id: 'Trading otomatis' })),
        chip(STEP(5), tr(language, { ko: '실계좌 (선택)', en: 'Live (optional)', ja: '実口座（任意）', th: 'บัญชีจริง (เลือกได้)', vi: 'Thật (tùy chọn)', id: 'Live (opsional)' })),
      ]

  return (
    <div style={{ marginTop: 18 }}>
      <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-secondary,#8a8073)', marginBottom: 10 }}>{heading}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>{chips}</div>

      {mode === 'login' ? (
        <svg viewBox="0 0 560 216" width="100%" role="img" aria-label={heading} xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker id="ag-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill="var(--text-muted,#a89f92)" />
            </marker>
            <marker id="ag-arA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill="var(--accent-primary,#c26a45)" />
            </marker>
          </defs>
          {/* band 1: sign in → analysis → automation */}
          <rect x="16" y="10" width="160" height="48" rx="9" style={box} />
          <text x="96" y="30" textAnchor="middle" style={t}>{tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' })}</text>
          <text x="96" y="46" textAnchor="middle" style={s}>{tr(language, { ko: '규칙은 계속 실행 중', en: 'rules kept running', ja: 'ルールは稼働中', th: 'กฎยังทำงานอยู่', vi: 'quy tắc vẫn chạy', id: 'aturan tetap berjalan' })}</text>
          <rect x="200" y="10" width="160" height="48" rx="9" style={acc} />
          <text x="280" y="30" textAnchor="middle" style={t}>{tr(language, { ko: 'AI 애널리스트', en: 'AI Analysts', ja: 'AIアナリスト', th: 'นักวิเคราะห์ AI', vi: 'Nhà phân tích AI', id: 'Analis AI' })}</text>
          <text x="280" y="46" textAnchor="middle" style={s}>{tr(language, { ko: '4명 분석 → 결정·리포트', en: '4 briefs → decision', ja: '4名分析→判断', th: '4 คน → ผลตัดสิน', vi: '4 người → quyết định', id: '4 ringkasan → keputusan' })}</text>
          <rect x="384" y="10" width="160" height="48" rx="9" style={acc} />
          <text x="464" y="30" textAnchor="middle" style={t}>{tr(language, { ko: '자동매매 규칙', en: 'Auto-trade rules', ja: '自動売買ルール', th: 'กฎเทรดอัตโนมัติ', vi: 'Quy tắc tự động', id: 'Aturan trading otomatis' })}</text>
          <text x="464" y="46" textAnchor="middle" style={s}>{tr(language, { ko: '24/7 서버 실행', en: 'runs 24/7 server-side', ja: 'サーバーで24時間実行', th: 'ทำงาน 24/7', vi: 'chạy 24/7', id: 'berjalan 24/7 di sisi server' })}</text>
          <path d="M176 34 H198" style={line} markerEnd="url(#ag-ar)" />
          <path d="M360 34 H382" style={line} markerEnd="url(#ag-ar)" />
          {/* band 2: gate ← fills ← alerts (flow right-to-left) */}
          <path d="M464 58 V84" style={line} markerEnd="url(#ag-ar)" />
          <rect x="384" y="86" width="160" height="48" rx="9" style={box} />
          <text x="464" y="106" textAnchor="middle" style={t}>{tr(language, { ko: '리스크 게이트', en: 'Risk gate', ja: 'リスクゲート', th: 'ประตูความเสี่ยง', vi: 'Cổng rủi ro', id: 'Gerbang risiko' })}</text>
          <text x="464" y="122" textAnchor="middle" style={s}>{tr(language, { ko: '한도·이벤트·브레이커', en: 'limits · events · breakers', ja: '上限・イベント・遮断', th: 'วงเงิน·เหตุการณ์·เบรกเกอร์', vi: 'hạn mức · sự kiện', id: 'batas · peristiwa · pemutus sirkuit' })}</text>
          <rect x="200" y="86" width="160" height="48" rx="9" style={box} />
          <text x="280" y="106" textAnchor="middle" style={t}>{tr(language, { ko: '체결', en: 'Fills', ja: '約定', th: 'คำสั่งซื้อขาย', vi: 'Khớp lệnh', id: 'Eksekusi' })}</text>
          <text x="280" y="122" textAnchor="middle" style={s}>{tr(language, { ko: '모의 기본 · 실계좌 선택', en: 'simulated · live optional', ja: '模擬が既定・実口座任意', th: 'จำลอง · จริงเลือกได้', vi: 'mô phỏng · thật tùy chọn', id: 'simulasi · live opsional' })}</text>
          <rect x="16" y="86" width="160" height="48" rx="9" style={box} />
          <text x="96" y="106" textAnchor="middle" style={t}>{tr(language, { ko: '알림·기록', en: 'Alerts & journal', ja: '通知・記録', th: 'แจ้งเตือน·บันทึก', vi: 'Thông báo · nhật ký', id: 'Peringatan & catatan' })}</text>
          <text x="96" y="122" textAnchor="middle" style={s}>{tr(language, { ko: '이메일·SMS·인앱', en: 'email · SMS · in-app', ja: 'メール・SMS・アプリ', th: 'อีเมล·SMS·ในแอป', vi: 'email · SMS · trong app', id: 'email · SMS · dalam aplikasi' })}</text>
          <path d="M384 110 H362" style={line} markerEnd="url(#ag-ar)" />
          <path d="M200 110 H178" style={line} markerEnd="url(#ag-ar)" />
          {/* growth loop back to analysis */}
          <rect x="16" y="160" width="528" height="42" rx="9" style={{ ...box, strokeDasharray: '5 4' }} />
          <text x="280" y="185" textAnchor="middle" style={t}>{tr(language, { ko: '성장 루프 — 결과를 복기하고 규칙을 개선해 다시 분석으로', en: 'Growth loop — review results, refine rules, analyze again', ja: '成長ループ — 結果を振り返り、ルールを改善して再分析', th: 'วงจรเติบโต — ทบทวนผล ปรับกฎ แล้ววิเคราะห์ใหม่', vi: 'Vòng phát triển — xem lại, tinh chỉnh, phân tích lại', id: 'Lingkar pertumbuhan — tinjau hasil, perbaiki aturan, analisis lagi' })}</text>
          <path d="M96 134 V158" style={line} markerEnd="url(#ag-ar)" />
          <path d="M188 160 V46 H196" style={accline} markerEnd="url(#ag-arA)" />
        </svg>
      ) : (
        <svg viewBox="0 0 560 236" width="100%" role="img" aria-label={heading} xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker id="ag-ar2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill="var(--text-muted,#a89f92)" />
            </marker>
          </defs>
          {/* band 1: signup → welcome capital */}
          <rect x="16" y="10" width="252" height="52" rx="9" style={box} />
          <text x="142" y="30" textAnchor="middle" style={t}>{tr(language, { ko: 'STEP 1 · 1분 가입', en: 'STEP 1 · 1-minute signup', ja: 'STEP 1 · 1分登録', th: 'STEP 1 · สมัคร 1 นาที', vi: 'STEP 1 · Đăng ký 1 phút', id: 'LANGKAH 1 · Daftar 1 menit' })}</text>
          <text x="142" y="48" textAnchor="middle" style={s}>{tr(language, { ko: '이름 + 이메일 + 비밀번호', en: 'name + email + password', ja: '名前＋メール＋パスワード', th: 'ชื่อ + อีเมล + รหัสผ่าน', vi: 'tên + email + mật khẩu', id: 'nama + email + kata sandi' })}</text>
          <rect x="292" y="10" width="252" height="52" rx="9" style={acc} />
          <text x="418" y="30" textAnchor="middle" style={t}>{tr(language, { ko: 'STEP 2 · 웰컴 자본', en: 'STEP 2 · Welcome capital', ja: 'STEP 2 · ウェルカム資金', th: 'STEP 2 · ทุนต้อนรับ', vi: 'STEP 2 · Vốn chào mừng', id: 'LANGKAH 2 · Modal sambutan' })}</text>
          <text x="418" y="48" textAnchor="middle" style={s}>{tr(language, { ko: '모의 자금 $100,000 즉시 지급', en: '$100,000 simulated — instant', ja: '模擬資金 $100,000 を即付与', th: 'เงินจำลอง $100,000 ทันที', vi: '$100.000 mô phỏng — ngay', id: '$100.000 simulasi — seketika' })}</text>
          <path d="M268 36 H290" style={line} markerEnd="url(#ag-ar2)" />
          {/* band 2: AI analysis → automation */}
          <path d="M418 62 V76 H142 V86" style={line} markerEnd="url(#ag-ar2)" />
          <rect x="16" y="88" width="252" height="52" rx="9" style={acc} />
          <text x="142" y="108" textAnchor="middle" style={t}>{tr(language, { ko: 'STEP 3 · AI 애널리스트', en: 'STEP 3 · AI Analysts', ja: 'STEP 3 · AIアナリスト', th: 'STEP 3 · นักวิเคราะห์ AI', vi: 'STEP 3 · Nhà phân tích AI', id: 'LANGKAH 3 · Analis AI' })}</text>
          <text x="142" y="126" textAnchor="middle" style={s}>{tr(language, { ko: '4명이 분석·토론 → 결정·리포트', en: '4 analysts debate → decision + report', ja: '4名が分析・討議→判断とレポート', th: '4 คนถกเถียง → ผลตัดสิน + รายงาน', vi: '4 người tranh luận → quyết định', id: '4 analis berdebat → keputusan + laporan' })}</text>
          <rect x="292" y="88" width="252" height="52" rx="9" style={acc} />
          <text x="418" y="108" textAnchor="middle" style={t}>{tr(language, { ko: 'STEP 4 · 자동매매 규칙', en: 'STEP 4 · Auto-trade rules', ja: 'STEP 4 · 自動売買ルール', th: 'STEP 4 · กฎเทรดอัตโนมัติ', vi: 'STEP 4 · Quy tắc tự động', id: 'LANGKAH 4 · Aturan trading otomatis' })}</text>
          <text x="418" y="126" textAnchor="middle" style={s}>{tr(language, { ko: '규칙을 만들면 24/7 서버 실행', en: 'create a rule — runs 24/7', ja: 'ルールを作れば24時間実行', th: 'สร้างกฎ — ทำงาน 24/7', vi: 'tạo quy tắc — chạy 24/7', id: 'buat aturan — berjalan 24/7' })}</text>
          <path d="M268 114 H290" style={line} markerEnd="url(#ag-ar2)" />
          {/* band 3: optional live upgrade */}
          <path d="M418 140 V164" style={line} markerEnd="url(#ag-ar2)" />
          <rect x="16" y="166" width="528" height="52" rx="9" style={{ ...box, strokeDasharray: '5 4' }} />
          <text x="280" y="186" textAnchor="middle" style={t}>{tr(language, { ko: 'STEP 5 · 준비되면 — 실계좌 브로커 연결 (선택)', en: 'STEP 5 · When ready — connect a live broker (optional)', ja: 'STEP 5 · 準備ができたら — 実口座ブローカー接続（任意）', th: 'STEP 5 · เมื่อพร้อม — เชื่อมโบรกเกอร์จริง (เลือกได้)', vi: 'STEP 5 · Khi sẵn sàng — kết nối môi giới thật (tùy chọn)', id: 'LANGKAH 5 · Saat siap — hubungkan broker live (opsional)' })}</text>
          <text x="280" y="204" textAnchor="middle" style={s}>{tr(language, { ko: '그 전까지 실제 돈은 한 푼도 들어가지 않습니다', en: 'until then, not a cent of real money is involved', ja: 'それまで実際のお金は一切かかりません', th: 'ก่อนหน้านั้นไม่ใช้เงินจริงแม้แต่บาทเดียว', vi: 'trước đó không dùng một đồng tiền thật nào', id: 'sampai saat itu, tidak sesen pun uang sungguhan yang terlibat' })}</text>
        </svg>
      )}
    </div>
  )
}

function AuthShell({
  mode,
  title,
  subtitle,
  children,
  footer
}: {
  mode: 'login' | 'register'
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  const { language } = useLanguage()
  // Which social providers the backend actually has configured. Google is live;
  // Apple stays "coming soon" until Apple Developer credentials are provisioned.
  const [providers, setProviders] = useState<{ google: boolean; apple: boolean }>({ google: false, apple: false })
  useEffect(() => {
    fetch(`${API_BASE}/auth/providers`)
      .then(r => r.json())
      .then(d => setProviders({ google: !!d?.providers?.google, apple: !!d?.providers?.apple }))
      .catch(() => { /* leave both false → buttons show the coming-soon notice */ })
  }, [])

  return (
    <div className="auth-shell">
      <AuthBackground />
      <div className="auth-stage">
        <div className="auth-panel auth-panel-copy">
          <div className="auth-kicker">
            <span>Sooppiy</span>
            <span>{mode === 'login' ? tr(language, { ko: '액세스 터미널', en: 'Access Terminal', ja: 'アクセス端末', th: 'เทอร์มินัลเข้าใช้งาน', vi: 'Terminal truy cập', id: 'Buka terminal' }) : tr(language, { ko: '회원 가입', en: 'Create Account', ja: 'アカウント作成', th: 'สร้างบัญชี', vi: 'Tạo tài khoản', id: 'Buat akun' })}</span>
          </div>
          <h1 className="auth-hero-title">
            {mode === 'login'
              ? tr(language, { ko: '당신의 트레이딩 자리에 앉으세요', en: 'Step into your trading seat', ja: 'あなたのトレーディング席へ', th: 'ก้าวสู่ที่นั่งเทรดของคุณ', vi: 'Bước vào ghế giao dịch của bạn', id: 'Duduklah di kursi trading Anda' })
              : tr(language, { ko: '몇 분 만에 AI 트레이딩을 시작하세요', en: 'Start AI trading in minutes', ja: '数分でAIトレーディングを開始', th: 'เริ่มเทรดด้วย AI ในไม่กี่นาที', vi: 'Bắt đầu giao dịch AI trong vài phút', id: 'Mulai trading AI dalam hitungan menit' })}
          </h1>
          <p className="auth-hero-copy">
            {mode === 'login'
              ? tr(language, {
                  ko: '로그인하여 AI 애널리스트 리포트, 자동매매, 시그널·토론, 알림, 자산 관리에 접근하세요. 모의 자금으로 안전하게 시작하고, 준비되면 실계좌 브로커 연결까지 — 하나의 워크스페이스에서 모두 가능합니다.', en: 'Log in to access AI analyst reports, auto-trading, signals & discussions, notifications, and portfolio controls. Start safely with simulated funds, then connect your real brokerage when you are ready — all in one workspace.',
                  ja: 'ログインすると、AIアナリストのレポート、自動売買、シグナル・ディスカッション、通知、資産管理にアクセスできます。シミュレーション資金で安全に始めて、準備ができたら実口座のブローカー接続まで — すべてひとつのワークスペースで。',
                  th: 'เข้าสู่ระบบเพื่อเข้าถึงรายงานนักวิเคราะห์ AI เทรดอัตโนมัติ สัญญาณและการสนทนา การแจ้งเตือน และการจัดการพอร์ต เริ่มอย่างปลอดภัยด้วยเงินจำลอง แล้วเชื่อมต่อบัญชีโบรกเกอร์จริงเมื่อพร้อม — ทั้งหมดในเวิร์กสเปซเดียว',
                  vi: 'Đăng nhập để truy cập báo cáo nhà phân tích AI, giao dịch tự động, tín hiệu & thảo luận, thông báo và quản lý danh mục. Bắt đầu an toàn với vốn mô phỏng, rồi kết nối tài khoản môi giới thật khi bạn sẵn sàng — tất cả trong một không gian làm việc.',
                  id: 'Masuk untuk mengakses laporan analis AI, trading otomatis, sinyal & diskusi, notifikasi, dan kendali portofolio. Mulailah dengan aman memakai dana simulasi, lalu hubungkan akun broker sungguhan saat Anda siap — semuanya dalam satu ruang kerja.'
                })
              : tr(language, {
                  ko: '가입하면 모의 자금 $100,000가 즉시 지급됩니다. AI 애널리스트에게 분석을 맡기고, 자동매매 규칙을 만들고, 시그널과 토론을 팔로우하세요 — 실제 돈 없이 시작하고, 준비되면 실계좌 브로커를 연결하면 됩니다.', en: 'Sign up and receive $100,000 in simulated funds instantly. Put the AI analysts to work, create auto-trading rules, and follow signals and discussions — start with zero real money, and connect a live brokerage when you are ready.',
                  ja: '登録するとシミュレーション資金 $100,000 が即時に付与されます。AIアナリストに分析を任せ、自動売買ルールを作り、シグナルやディスカッションをフォローしましょう — 実際のお金なしで始めて、準備ができたら実口座のブローカーを接続できます。',
                  th: 'สมัครแล้วรับเงินจำลอง $100,000 ทันที ให้นักวิเคราะห์ AI ทำงานให้ สร้างกฎเทรดอัตโนมัติ และติดตามสัญญาณกับการสนทนา — เริ่มโดยไม่ใช้เงินจริงเลย แล้วเชื่อมต่อบัญชีโบรกเกอร์จริงเมื่อคุณพร้อม',
                  vi: 'Đăng ký và nhận ngay $100.000 vốn mô phỏng. Giao việc cho các nhà phân tích AI, tạo quy tắc giao dịch tự động, theo dõi tín hiệu và thảo luận — bắt đầu không cần tiền thật, và kết nối tài khoản môi giới thật khi bạn sẵn sàng.',
                  id: 'Daftar dan terima dana simulasi $100.000 seketika. Pekerjakan para analis AI, buat aturan trading otomatis, serta ikuti sinyal dan diskusi — mulai tanpa uang sungguhan sepeser pun, dan hubungkan broker live saat Anda siap.'
                })}
          </p>
          <AuthGlance mode={mode} language={language} />
        </div>

        <div className="auth-panel auth-panel-form">
          <div className="auth-card auth-card-terminal">
            <h2 className="auth-title">{title}</h2>
            <p className="auth-subtitle">{subtitle}</p>

            {/* Social sign-in */}
            <div className="auth-social">
              <button
                type="button"
                className="auth-social-btn auth-social-google"
                onClick={() => {
                  if (providers.google) { window.location.href = `${API_BASE}/auth/google/start`; return }
                  alert(tr(language, {
                    ko: 'Google 로그인은 곧 지원됩니다 — 지금은 이메일과 비밀번호를 사용하세요.', en: 'Google sign-in coming soon — use email & password for now.',
                    ja: 'Google サインインは近日公開予定です。今はメール＆パスワードをご利用ください。',
                    th: 'Google sign-in เร็วๆ นี้ — ใช้อีเมลและรหัสผ่านก่อนนะ',
                    vi: 'Google sign-in sắp ra mắt — dùng email & mật khẩu trước nhé.',
                    id: 'Masuk dengan Google segera hadir — untuk sementara gunakan email & kata sandi.'
                  }))
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                {tr(language, { ko: 'Google로 계속하기', en: 'Continue with Google', ja: 'Googleで続行', th: 'ดำเนินการด้วย Google', vi: 'Tiếp tục với Google', id: 'Lanjut dengan Google' })}
              </button>

              <button
                type="button"
                className="auth-social-btn auth-social-apple"
                onClick={() => {
                  if (providers.apple) { window.location.href = `${API_BASE}/auth/apple/start`; return }
                  alert(tr(language, {
                    ko: 'Apple 로그인은 곧 지원됩니다 — 지금은 이메일과 비밀번호를 사용하세요.', en: 'Apple sign-in coming soon — use email & password for now.',
                    ja: 'Apple サインインは近日公開予定です。今はメール＆パスワードをご利用ください。',
                    th: 'Apple sign-in เร็วๆ นี้ — ใช้อีเมลและรหัสผ่านก่อนนะ',
                    vi: 'Apple sign-in sắp ra mắt — dùng email & mật khẩu trước nhé.',
                    id: 'Masuk dengan Apple segera hadir — untuk sementara gunakan email & kata sandi.'
                  }))
                }}
              >
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
                  <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
                </svg>
                {tr(language, { ko: 'Apple로 계속하기', en: 'Continue with Apple', ja: 'Appleで続行', th: 'ดำเนินการด้วย Apple', vi: 'Tiếp tục với Apple', id: 'Lanjut dengan Apple' })}
              </button>
            </div>

            {/* Divider */}
            <div className="auth-divider">
              <span>{tr(language, { ko: '또는 이메일로 계속하기', en: 'or continue with email', ja: 'またはメールで', th: 'หรือใช้อีเมล', vi: 'hoặc dùng email', id: 'atau lanjut dengan email' })}</span>
            </div>

            {children}
            <div className="auth-footer">{footer}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

async function fetchActiveChallengeOptions() {
  try {
    const res = await fetch(`${API_BASE}/challenges?status=active&limit=100`)
    if (!res.ok) return []
    const data = await res.json()
    return data.challenges || []
  } catch (e) {
    console.error(e)
    return []
  }
}

async function fetchMyTeamMissionOptions(token: string | null) {
  if (!token) return []
  try {
    const res = await fetch(`${API_BASE}/team-missions/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (!res.ok) return []
    const data = await res.json()
    return data.missions || []
  } catch (e) {
    console.error(e)
    return []
  }
}

function SignalCard({
  signal,
  onRefresh,
  onFollow,
  onUnfollow,
  isFollowingAuthor = false,
  canFollowAuthor = false,
  canAcceptReplies = false,
  autoOpenReplies = false
}: {
  signal: any
  onRefresh?: () => void
  onFollow?: (leaderId: number) => void
  onUnfollow?: (leaderId: number) => void
  isFollowingAuthor?: boolean
  canFollowAuthor?: boolean
  canAcceptReplies?: boolean
  autoOpenReplies?: boolean
}) {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [showReplies, setShowReplies] = useState(false)
  const [replies, setReplies] = useState<any[]>([])
  const [replyContent, setReplyContent] = useState('')
  const [loadingReplies, setLoadingReplies] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const { language } = useLanguage()
  const teamBadges = Array.isArray(signal.team_badges) ? signal.team_badges : []

  const loadReplies = async () => {
    setLoadingReplies(true)
    try {
      const res = await fetch(`${API_BASE}/signals/${signal.id}/replies`)
      const data = await res.json()
      setReplies(data.replies || [])
    } catch (e) {
      console.error(e)
    }
    setLoadingReplies(false)
  }

  const handleReply = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !replyContent.trim()) return

    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/signals/reply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          signal_id: signal.id,
          content: replyContent
        })
      })
      if (res.ok) {
        setReplyContent('')
        loadReplies()
        onRefresh?.()
      } else {
        const data = await res.json()
        alert(data.detail || tr(language, { ko: '답글 전송에 실패했습니다', en: 'Failed to send reply', ja: '返信の送信に失敗しました', th: 'ส่งการตอบกลับล้มเหลว', vi: 'Gửi trả lời thất bại', id: 'Gagal mengirim balasan' }))
      }
    } catch (e) {
      console.error(e)
      alert(tr(language, { ko: '답글 전송에 실패했습니다', en: 'Failed to send reply', ja: '返信の送信に失敗しました', th: 'ส่งการตอบกลับล้มเหลว', vi: 'Gửi trả lời thất bại', id: 'Gagal mengirim balasan' }))
    }
    setSubmitting(false)
  }

  const toggleReplies = () => {
    if (!showReplies) {
      loadReplies()
    }
    setShowReplies(!showReplies)
  }

  useEffect(() => {
    if (autoOpenReplies && !showReplies) {
      setShowReplies(true)
      loadReplies()
    }
  }, [autoOpenReplies])

  const handleAcceptReply = async (replyId: number) => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/signals/${signal.signal_id}/replies/${replyId}/accept`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        loadReplies()
        onRefresh?.()
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="signal-card">
      <div className="signal-header">
        <span className="signal-symbol">{signal.title}</span>
        <span className="tag">
          {MARKETS.find(m => m.value === signal.market)?.labels[language]}
        </span>
      </div>

      {signal.agent_name && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {signal.agent_name}
          </div>
          {canFollowAuthor && signal.agent_id && (
            isFollowingAuthor ? (
              <button
                className="btn btn-ghost"
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => onUnfollow?.(signal.agent_id)}
              >
                {tr(language, { ko: '팔로잉', en: 'Following', ja: 'フォロー中', th: 'กำลังติดตาม', vi: 'Đang theo dõi', id: 'Mengikuti' })}
              </button>
            ) : (
              <button
                className="btn btn-primary"
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => onFollow?.(signal.agent_id)}
              >
                {tr(language, { ko: '팔로우', en: 'Follow', ja: 'フォロー', th: 'ติดตาม', vi: 'Theo dõi', id: 'Ikuti' })}
              </button>
            )
          )}
        </div>
      )}

      {teamBadges.length > 0 && (
        <div className="team-signal-badges">
          {teamBadges.map((badge: any) => (
            <span key={`${badge.mission_key}-${badge.team_key}`} className="team-signal-badge">
              <Link to={`/team-missions/${badge.mission_key}`}>{badge.mission_title || badge.mission_key}</Link>
              <Link to={`/teams/${badge.team_key}`}>{badge.team_name || badge.team_key}</Link>
            </span>
          ))}
        </div>
      )}

      {(signal.quality_score !== null && signal.quality_score !== undefined) || signal.reward_reason || signal.accepted_reply_count ? (
        <div className="experiment-signal-badges">
          {signal.quality_score !== null && signal.quality_score !== undefined && (
            <span className="experiment-signal-badge">
              {tr(language, { ko: '품질', en: 'Quality', ja: '品質', th: 'คุณภาพ', vi: 'Chất lượng', id: 'Kualitas' })} {Number(signal.quality_score || 0).toFixed(2)}
            </span>
          )}
          {signal.accepted_reply_count ? (
            <span className="experiment-signal-badge">
              {tr(language, { ko: '수락됨', en: 'Accepted', ja: '採用済み', th: 'ยอมรับแล้ว', vi: 'Đã chấp nhận', id: 'Diterima' })} {signal.accepted_reply_count}
            </span>
          ) : null}
          {signal.reward_reason && (
            <span className="experiment-signal-badge">
              {signal.reward_reason} {signal.reward_points ? `+${signal.reward_points}` : ''}
            </span>
          )}
          {signal.reward_experiment_key && (
            <span className="experiment-signal-badge">
              {signal.reward_experiment_key}/{signal.reward_variant_key || '-'}
            </span>
          )}
        </div>
      ) : null}

      <p className="signal-content">{signal.content}</p>

      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
        <span>{tr(language, { ko: `답글 ${signal.reply_count || 0}개`, en: `${signal.reply_count || 0} replies`, ja: `返信 ${signal.reply_count || 0}`, th: `${signal.reply_count || 0} การตอบกลับ`, vi: `${signal.reply_count || 0} trả lời` })}</span>
        <span>{tr(language, { ko: `참여자 ${signal.participant_count || 1}명`, en: `${signal.participant_count || 1} participants`, ja: `参加者 ${signal.participant_count || 1}`, th: `${signal.participant_count || 1} ผู้เข้าร่วม`, vi: `${signal.participant_count || 1} người tham gia` })}</span>
        <span>
          {tr(language, { ko: '활성 ', en: 'Active ', ja: 'アクティブ ', th: 'ใช้งานล่าสุด ', vi: 'Hoạt động ', id: 'Aktif ' })}
          {signal.last_reply_at ? new Date(signal.last_reply_at).toLocaleString() : new Date(signal.created_at).toLocaleString()}
        </span>
      </div>

      {Array.isArray(signal.symbols) && signal.symbols.length > 0 && (
        <div className="tags">
          {signal.symbols.map((sym: string) => (
            <span key={sym} className="tag">{sym}</span>
          ))}
        </div>
      )}

      {Array.isArray(signal.tags) && signal.tags.length > 0 && (
        <div className="tags">
          {signal.tags.map((tag: string) => (
            <span key={tag} className="tag">{tag}</span>
          ))}
        </div>
      )}

      <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
        <button
          onClick={toggleReplies}
          className="btn btn-ghost"
          style={{ fontSize: '13px', padding: '8px 0' }}
        >
          {showReplies ? '▼' : '▶'} {tr(language, { ko: '답글 숨기기', en: 'Hide replies', ja: '返信を隠す', th: 'ซ่อนการตอบกลับ', vi: 'Ẩn trả lời', id: 'Sembunyikan balasan' })}
        </button>

        {showReplies && (
          <div style={{ marginTop: '12px' }}>
            {token ? (
              <form onSubmit={handleReply} style={{ marginBottom: '16px' }}>
                <textarea
                  className="form-textarea"
                  placeholder={tr(language, { ko: '답글을 작성하세요...', en: 'Write a reply...', ja: '返信を書く...', th: 'เขียนการตอบกลับ...', vi: 'Viết trả lời...', id: 'Tulis balasan...' })}
                  value={replyContent}
                  onChange={e => setReplyContent(e.target.value)}
                  required
                  style={{ minHeight: '60px', marginBottom: '8px' }}
                />
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? tr(language, { ko: '전송 중...', en: 'Sending...', ja: '送信中...', th: 'กำลังส่ง...', vi: 'Đang gửi...', id: 'Mengirim...' }) : tr(language, { ko: '답글', en: 'Reply', ja: '返信', th: 'ตอบกลับ', vi: 'Trả lời', id: 'Balas' })}
                </button>
              </form>
            ) : (
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                {tr(language, { ko: '로그인 후 답글', en: 'Login to reply', ja: '返信するにはログインしてください', th: 'เข้าสู่ระบบเพื่อตอบกลับ', vi: 'Đăng nhập để trả lời', id: 'Masuk untuk membalas' })}
              </p>
            )}

            {loadingReplies ? (
              <div className="loading"><div className="spinner"></div></div>
            ) : replies.length > 0 ? (
              <div style={{ marginTop: '12px' }}>
                {replies.map((reply: any) => (
                  <div key={reply.id} style={{
                    padding: '12px',
                    background: 'var(--bg-tertiary)',
                    borderRadius: '8px',
                    marginBottom: '8px'
                  }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                      <span>{reply.agent_name || reply.user_name || 'Anonymous'} • {new Date(reply.created_at).toLocaleString()}</span>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        {reply.accepted ? (
                          <span className="tag" style={{ background: 'rgba(34, 197, 94, 0.12)', color: '#16a34a' }}>
                            {tr(language, { ko: '수락됨', en: 'Accepted', ja: 'ベスト返信', th: 'คำตอบที่ดีที่สุด', vi: 'Trả lời tốt nhất', id: 'Diterima' })}
                          </span>
                        ) : canAcceptReplies ? (
                          <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => handleAcceptReply(reply.id)}>
                            {tr(language, { ko: '수락', en: 'Accept', ja: '採用', th: 'ยอมรับ', vi: 'Chấp nhận', id: 'Terima' })}
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <div style={{ fontSize: '14px' }}>{reply.content}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                {tr(language, { ko: '아직 답글이 없습니다', en: 'No replies yet', ja: 'まだ返信がありません', th: 'ยังไม่มีการตอบกลับ', vi: 'Chưa có trả lời', id: 'Belum ada balasan' })}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export function StrategiesPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [strategies, setStrategies] = useState<any[]>([])
  const [strategyPage, setStrategyPage] = useState(1)
  const [strategyTotal, setStrategyTotal] = useState(0)
  const [followingLeaderIds, setFollowingLeaderIds] = useState<number[]>([])
  const [viewerId, setViewerId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ title: '', content: '', symbols: '', tags: '', market: 'us-stock', challenge_key: '', mission_key: '', team_key: '' })
  const [activeChallenges, setActiveChallenges] = useState<any[]>([])
  const [teamMissionOptions, setTeamMissionOptions] = useState<any[]>([])
  const [sort, setSort] = useState<'new' | 'active' | 'following'>('active')
  const { t, language } = useLanguage()
  const location = useLocation()

  const signalIdFromQuery = new URLSearchParams(location.search).get('signal')
  const autoOpenReplyBox = new URLSearchParams(location.search).get('reply') === '1'
  const strategyTotalPages = Math.max(1, Math.ceil(strategyTotal / COMMUNITY_FEED_PAGE_SIZE))

  useEffect(() => {
    loadStrategies(strategyPage)
    fetchActiveChallengeOptions().then(setActiveChallenges)
    fetchMyTeamMissionOptions(token).then(setTeamMissionOptions)
    if (token) {
      loadViewerContext()
    }
  }, [sort, token, strategyPage])

  const loadViewerContext = async () => {
    if (!token) return
    try {
      const [meRes, followingRes] = await Promise.all([
        fetch(`${API_BASE}/claw/agents/me`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE}/signals/following`, { headers: { 'Authorization': `Bearer ${token}` } })
      ])
      if (meRes.ok) {
        const meData = await meRes.json()
        setViewerId(meData.id || null)
      }
      if (followingRes.ok) {
        const followingData = await followingRes.json()
        setFollowingLeaderIds((followingData.following || []).map((item: any) => item.leader_id))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const loadStrategies = async (pageToLoad = strategyPage) => {
    setLoading(true)
    try {
      const offset = (pageToLoad - 1) * COMMUNITY_FEED_PAGE_SIZE
      const res = await fetch(`${API_BASE}/signals/feed?message_type=strategy&limit=${COMMUNITY_FEED_PAGE_SIZE}&offset=${offset}&sort=${sort}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : undefined
      })
      if (!res.ok) {
        console.error('Failed to load strategies:', res.status)
        setStrategies([])
        setStrategyTotal(0)
        setLoading(false)
        return
      }
      const data = await res.json()
      setStrategies(data.signals || [])
      setStrategyTotal(data.total || 0)
    } catch (e) {
      console.error('Error loading strategies:', e)
      setStrategies([])
      setStrategyTotal(0)
    }
    setLoading(false)
  }

  const handleFollow = async (leaderId: number) => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/signals/follow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      if (res.ok) loadViewerContext()
    } catch (e) {
      console.error(e)
    }
  }

  const handleUnfollow = async (leaderId: number) => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/signals/unfollow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      if (res.ok) loadViewerContext()
    } catch (e) {
      console.error(e)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return

    try {
      const res = await fetch(`${API_BASE}/signals/strategy`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          market: formData.market,
          title: formData.title,
          content: formData.content,
          symbols: formData.symbols,
          tags: formData.tags,
          challenge_key: formData.challenge_key || undefined,
          mission_key: formData.mission_key || undefined,
          team_key: formData.team_key || undefined,
        })
      })
      if (res.ok) {
        setFormData({ title: '', content: '', symbols: '', tags: '', market: 'us-stock', challenge_key: '', mission_key: '', team_key: '' })
        setShowForm(false)
        setStrategyPage(1)
        loadStrategies(1)
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.strategies.title}</h1>
          <p className="header-subtitle">{tr(language, { ko: '투자 전략을 게시하고 둘러보기', en: 'Publish and browse investment strategies', ja: '投資戦略を公開・閲覧', th: 'เผยแพร่และเรียกดูกลยุทธ์การลงทุน', vi: 'Đăng và duyệt chiến lược đầu tư', id: 'Terbitkan dan telusuri strategi investasi' })}</p>
        </div>
        {token && (
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {t.strategies.publish}
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {([
          ['active', tr(language, { ko: '가장 활발함', en: 'Most Active', ja: '最も活発', th: 'ใช้งานมากที่สุด', vi: 'Hoạt động nhiều nhất', id: 'Paling aktif' })],
          ['new', tr(language, { ko: '최신순', en: 'Newest', ja: '最新', th: 'ใหม่ล่าสุด', vi: 'Mới nhất', id: 'Terbaru' })],
          ['following', tr(language, { ko: '팔로잉', en: 'Following', ja: 'フォロー中', th: 'กำลังติดตาม', vi: 'Đang theo dõi', id: 'Mengikuti' })]
        ] as const).map(([value, label]) => (
          <button
            key={value}
            className="btn btn-ghost"
            onClick={() => {
              setSort(value)
              setStrategyPage(1)
            }}
            style={{
              background: sort === value ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
              color: sort === value ? '#fff' : 'var(--text-secondary)'
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {showForm && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: '20px' }}>{tr(language, { ko: '새 전략 게시', en: 'Publish New Strategy', ja: '新しい戦略を公開', th: 'เผยแพร่กลยุทธ์ใหม่', vi: 'Đăng chiến lược mới', id: 'Terbitkan strategi baru' })}</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{t.strategies.market}</label>
              <select
                className="form-select"
                value={formData.market}
                onChange={e => setFormData({ ...formData, market: e.target.value })}
              >
                {MARKETS.filter(m => m.value !== 'all').map(m => (
                  <option key={m.value} value={m.value} disabled={!m.supported}>
                    {m.labels[language]}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{tr(language, { ko: '챌린지 (선택)', en: 'Challenge (optional)', ja: 'チャレンジ（任意）', th: 'ความท้าทาย (ไม่บังคับ)', vi: 'Thử thách (tùy chọn)', id: 'Tantangan (opsional)' })}</label>
              <select
                className="form-select"
                value={formData.challenge_key}
                onChange={e => setFormData({ ...formData, challenge_key: e.target.value })}
              >
                <option value="">{tr(language, { ko: '챌린지 없음', en: 'No challenge', ja: 'チャレンジなし', th: 'ไม่มีความท้าทาย', vi: 'Không có thử thách', id: 'Tanpa tantangan' })}</option>
                {activeChallenges.map((challenge: any) => (
                  <option key={challenge.challenge_key} value={challenge.challenge_key}>
                    {challenge.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="team-binding-grid">
              <div className="form-group">
                <label className="form-label">{tr(language, { ko: '팀 미션 (선택)', en: 'Team Mission (optional)', ja: 'チームミッション（任意）', th: 'ภารกิจทีม (ไม่บังคับ)', vi: 'Nhiệm vụ nhóm (tùy chọn)', id: 'Misi tim (opsional)' })}</label>
                <select
                  className="form-select"
                  value={formData.mission_key}
                  onChange={e => setFormData({ ...formData, mission_key: e.target.value, team_key: '' })}
                >
                  <option value="">{tr(language, { ko: '미션 없음', en: 'No mission', ja: 'ミッションなし', th: 'ไม่มีภารกิจ', vi: 'Không có nhiệm vụ', id: 'Tanpa misi' })}</option>
                  {teamMissionOptions.map((mission: any) => (
                    <option key={mission.mission_key} value={mission.mission_key}>
                      {mission.title}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr(language, { ko: '팀 (선택)', en: 'Team (optional)', ja: 'チーム（任意）', th: 'ทีม (ไม่บังคับ)', vi: 'Nhóm (tùy chọn)', id: 'Tim (opsional)' })}</label>
                <select
                  className="form-select"
                  value={formData.team_key}
                  onChange={e => {
                    const selected = teamMissionOptions.find((mission: any) => mission.team_key === e.target.value)
                    setFormData({
                      ...formData,
                      team_key: e.target.value,
                      mission_key: selected?.mission_key || formData.mission_key
                    })
                  }}
                >
                  <option value="">{tr(language, { ko: '미션 팀 자동 사용', en: 'Use mission team automatically', ja: '現在のミッションチームを自動使用', th: 'ใช้ทีมภารกิจอัตโนมัติ', vi: 'Sử dụng nhóm nhiệm vụ tự động', id: 'Gunakan tim misi secara otomatis' })}</option>
                  {teamMissionOptions
                    .filter((mission: any) => mission.team_key && (!formData.mission_key || mission.mission_key === formData.mission_key))
                    .map((mission: any) => (
                      <option key={mission.team_key} value={mission.team_key}>
                        {mission.team_name || mission.team_key}
                      </option>
                    ))}
                </select>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.title}</label>
              <input
                type="text"
                className="form-input"
                value={formData.title}
                onChange={e => setFormData({ ...formData, title: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.content}</label>
              <textarea
                className="form-textarea"
                value={formData.content}
                onChange={e => setFormData({ ...formData, content: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.symbols}</label>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                {formData.symbols.split(',').map(s => s.trim()).filter(Boolean).map(s => (
                  <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 999, border: '1px solid var(--border-color)', fontSize: 13 }}>
                    {s}
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, symbols: formData.symbols.split(',').map(x => x.trim()).filter(x => x && x !== s).join(', ') })}
                      style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}
                    >×</button>
                  </span>
                ))}
                <SymbolSelect
                  className="form-input"
                  style={{ width: 180 }}
                  market={formData.market}
                  value=""
                  onChange={symbol => {
                    if (!symbol) return
                    const current = formData.symbols.split(',').map(x => x.trim()).filter(Boolean)
                    if (!current.includes(symbol)) setFormData({ ...formData, symbols: [...current, symbol].join(', ') })
                  }}
                  placeholder={tr(language, { ko: '종목 추가', en: 'Add symbol', ja: '銘柄を追加', th: 'เพิ่มสัญลักษณ์', vi: 'Thêm mã', id: 'Tambah simbol' })}
                />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.tags}</label>
              <input
                type="text"
                className="form-input"
                placeholder="momentum, breakout"
                value={formData.tags}
                onChange={e => setFormData({ ...formData, tags: e.target.value })}
              />
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button type="submit" className="btn btn-primary">{t.strategies.submit}</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
                {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' })}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : strategies.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📈</div>
          <div className="empty-title">{t.strategies.noStrategies}</div>
        </div>
      ) : signalIdFromQuery ? (
        <div>
          {strategies.filter(s => String(s.id) === signalIdFromQuery).map((strategy) => (
            <SignalCard
              key={strategy.id}
              signal={strategy}
              onRefresh={loadStrategies}
              onFollow={handleFollow}
              onUnfollow={handleUnfollow}
              isFollowingAuthor={followingLeaderIds.includes(strategy.agent_id)}
              canFollowAuthor={!!token && strategy.agent_id !== viewerId}
              canAcceptReplies={strategy.agent_id === viewerId}
              autoOpenReplies={autoOpenReplyBox}
            />
          ))}
        </div>
      ) : (
        <>
          <div className="signal-grid">
            {strategies.map((strategy) => (
              <SignalCard
                key={strategy.id}
                signal={strategy}
                onRefresh={loadStrategies}
                onFollow={handleFollow}
                onUnfollow={handleUnfollow}
                isFollowingAuthor={followingLeaderIds.includes(strategy.agent_id)}
                canFollowAuthor={!!token && strategy.agent_id !== viewerId}
                canAcceptReplies={strategy.agent_id === viewerId}
              />
            ))}
          </div>
          {strategyTotalPages > 1 && (
            <div className="card" style={{ marginTop: '20px', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <button
                className="btn btn-secondary"
                disabled={strategyPage <= 1}
                onClick={() => setStrategyPage((current) => Math.max(1, current - 1))}
              >
                {tr(language, { ko: '이전', en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước', id: 'Sebelumnya' })}
              </button>
              <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                {tr(language, {
                  ko: `페이지 ${strategyPage} / ${strategyTotalPages}, 총 전략 ${strategyTotal}개`, en: `Page ${strategyPage} / ${strategyTotalPages}, ${strategyTotal} strategies total`,
                  ja: `ページ ${strategyPage} / ${strategyTotalPages}、合計 ${strategyTotal} 件の戦略`,
                  th: `หน้า ${strategyPage} / ${strategyTotalPages}, รวม ${strategyTotal} กลยุทธ์`,
                  vi: `Trang ${strategyPage} / ${strategyTotalPages}, tổng ${strategyTotal} chiến lược`
                })}
              </div>
              <button
                className="btn btn-secondary"
                disabled={strategyPage >= strategyTotalPages}
                onClick={() => setStrategyPage((current) => Math.min(strategyTotalPages, current + 1))}
              >
                {tr(language, { ko: '다음', en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp', id: 'Berikutnya' })}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function DiscussionsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [discussions, setDiscussions] = useState<any[]>([])
  const [discussionPage, setDiscussionPage] = useState(1)
  const [discussionTotal, setDiscussionTotal] = useState(0)
  const [recentNotifications, setRecentNotifications] = useState<any[]>([])
  const [followingLeaderIds, setFollowingLeaderIds] = useState<number[]>([])
  const [viewerId, setViewerId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ title: '', content: '', tags: '', market: 'us-stock', challenge_key: '', mission_key: '', team_key: '' })
  const [activeChallenges, setActiveChallenges] = useState<any[]>([])
  const [teamMissionOptions, setTeamMissionOptions] = useState<any[]>([])
  const [sort, setSort] = useState<'new' | 'active' | 'following'>('active')
  const { t, language } = useLanguage()
  const location = useLocation()
  const navigate = useNavigate()

  const signalIdFromQuery = new URLSearchParams(location.search).get('signal')
  const autoOpenReplyBox = new URLSearchParams(location.search).get('reply') === '1'
  const discussionTotalPages = Math.max(1, Math.ceil(discussionTotal / COMMUNITY_FEED_PAGE_SIZE))

  useEffect(() => {
    loadDiscussions(discussionPage)
    fetchActiveChallengeOptions().then(setActiveChallenges)
    fetchMyTeamMissionOptions(token).then(setTeamMissionOptions)
    if (token) {
      loadRecentNotifications()
      loadViewerContext()
    }
  }, [sort, token, discussionPage])

  const loadViewerContext = async () => {
    if (!token) return
    try {
      const [meRes, followingRes] = await Promise.all([
        fetch(`${API_BASE}/claw/agents/me`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE}/signals/following`, { headers: { 'Authorization': `Bearer ${token}` } })
      ])
      if (meRes.ok) {
        const meData = await meRes.json()
        setViewerId(meData.id || null)
      }
      if (followingRes.ok) {
        const followingData = await followingRes.json()
        setFollowingLeaderIds((followingData.following || []).map((item: any) => item.leader_id))
      }
    } catch (e) {
      console.error(e)
    }
  }

  const loadDiscussions = async (pageToLoad = discussionPage) => {
    setLoading(true)
    try {
      const offset = (pageToLoad - 1) * COMMUNITY_FEED_PAGE_SIZE
      const res = await fetch(`${API_BASE}/signals/feed?message_type=discussion&limit=${COMMUNITY_FEED_PAGE_SIZE}&offset=${offset}&sort=${sort}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : undefined
      })
      if (!res.ok) {
        console.error('Failed to load discussions:', res.status)
        setDiscussions([])
        setDiscussionTotal(0)
        setLoading(false)
        return
      }
      const data = await res.json()
      setDiscussions(data.signals || [])
      setDiscussionTotal(data.total || 0)
    } catch (e) {
      console.error('Error loading discussions:', e)
      setDiscussions([])
      setDiscussionTotal(0)
    }
    setLoading(false)
  }

  const loadRecentNotifications = async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/claw/messages/recent?category=discussion&limit=8`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) {
        setRecentNotifications([])
        return
      }
      const data = await res.json()
      setRecentNotifications(data.messages || [])
    } catch (e) {
      console.error(e)
      setRecentNotifications([])
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!token) return

    try {
      const res = await fetch(`${API_BASE}/signals/discussion`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          market: formData.market,
          title: formData.title,
          content: formData.content,
          tags: formData.tags,
          challenge_key: formData.challenge_key || undefined,
          mission_key: formData.mission_key || undefined,
          team_key: formData.team_key || undefined,
        })
      })
      if (res.ok) {
        setFormData({ title: '', content: '', tags: '', market: 'us-stock', challenge_key: '', mission_key: '', team_key: '' })
        setShowForm(false)
        setDiscussionPage(1)
        loadDiscussions(1)
        loadRecentNotifications()
      } else {
        const data = await res.json()
        alert(data.detail || tr(language, { ko: '토론 게시에 실패했습니다', en: 'Failed to post discussion', ja: 'ディスカッションの投稿に失敗しました', th: 'โพสต์การสนทนาล้มเหลว', vi: 'Đăng thảo luận thất bại', id: 'Gagal mengirim diskusi' }))
      }
    } catch (e) {
      console.error(e)
      alert(tr(language, { ko: '토론 게시에 실패했습니다', en: 'Failed to post discussion', ja: 'ディスカッションの投稿に失敗しました', th: 'โพสต์การสนทนาล้มเหลว', vi: 'Đăng thảo luận thất bại', id: 'Gagal mengirim diskusi' }))
    }
  }

  const handleFollow = async (leaderId: number) => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/signals/follow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      if (res.ok) loadViewerContext()
    } catch (e) {
      console.error(e)
    }
  }

  const handleUnfollow = async (leaderId: number) => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/signals/unfollow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      if (res.ok) loadViewerContext()
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.discussions.title}</h1>
          <p className="header-subtitle">{tr(language, { ko: '금융 주제에 대한 자유 토론', en: 'Free discussion on financial topics', ja: '金融トピックの自由討論', th: 'การสนทนาอย่างอิสระเกี่ยวกับหัวข้อทางการเงิน', vi: 'Thảo luận tự do về các chủ đề tài chính', id: 'Diskusi bebas seputar topik keuangan' })}</p>
        </div>
        {token && (
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {t.discussions.post}
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {([
          ['active', tr(language, { ko: '가장 활발함', en: 'Most Active', ja: '最も活発', th: 'ใช้งานมากที่สุด', vi: 'Hoạt động nhiều nhất', id: 'Paling aktif' })],
          ['new', tr(language, { ko: '최신순', en: 'Newest', ja: '最新', th: 'ใหม่ล่าสุด', vi: 'Mới nhất', id: 'Terbaru' })],
          ['following', tr(language, { ko: '팔로잉', en: 'Following', ja: 'フォロー中', th: 'กำลังติดตาม', vi: 'Đang theo dõi', id: 'Mengikuti' })]
        ] as const).map(([value, label]) => (
          <button
            key={value}
            className="btn btn-ghost"
            onClick={() => {
              setSort(value)
              setDiscussionPage(1)
            }}
            style={{
              background: sort === value ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
              color: sort === value ? '#fff' : 'var(--text-secondary)'
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {token && recentNotifications.length > 0 && (
        <div className="card" style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <h3 className="card-title" style={{ marginBottom: 0 }}>
              {tr(language, { ko: '최근 알림', en: 'Recent Notifications', ja: '最近の通知', th: 'การแจ้งเตือนล่าสุด', vi: 'Thông báo gần đây', id: 'Notifikasi terkini' })}
            </h3>
            <button
              className="btn btn-ghost"
              style={{ padding: '6px 10px', fontSize: '12px' }}
              onClick={loadRecentNotifications}
            >
              {tr(language, { ko: '새로고침', en: 'Refresh', ja: '更新', th: 'รีเฟรช', vi: 'Làm mới', id: 'Muat ulang' })}
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {recentNotifications.map((message: any) => {
              const signalId = message.data?.signal_id
              return (
                <button
                  key={message.id}
                  type="button"
                  onClick={() => signalId && navigate(`/discussions?signal=${signalId}&reply=1`)}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    background: message.read ? 'var(--bg-tertiary)' : 'rgba(34, 197, 94, 0.08)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '10px',
                    cursor: signalId ? 'pointer' : 'default'
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>
                    {message.content}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {message.data?.title || message.data?.symbol || tr(language, { ko: '토론 업데이트', en: 'Discussion update', ja: 'ディスカッション更新', th: 'อัปเดตการสนทนา', vi: 'Cập nhật thảo luận', id: 'Pembaruan diskusi' })}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    {message.created_at ? new Date(message.created_at).toLocaleString() : ''}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {showForm && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: '20px' }}>{tr(language, { ko: '새 토론 작성', en: 'Post New Discussion', ja: '新しいディスカッションを投稿', th: 'โพสต์การสนทนาใหม่', vi: 'Đăng thảo luận mới', id: 'Kirim diskusi baru' })}</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{t.discussions.market}</label>
              <select
                className="form-select"
                value={formData.market}
                onChange={e => setFormData({ ...formData, market: e.target.value })}
              >
                {MARKETS.filter(m => m.value !== 'all').map(m => (
                  <option key={m.value} value={m.value} disabled={!m.supported}>
                    {m.labels[language]}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{tr(language, { ko: '챌린지 (선택)', en: 'Challenge (optional)', ja: 'チャレンジ（任意）', th: 'ความท้าทาย (ไม่บังคับ)', vi: 'Thử thách (tùy chọn)', id: 'Tantangan (opsional)' })}</label>
              <select
                className="form-select"
                value={formData.challenge_key}
                onChange={e => setFormData({ ...formData, challenge_key: e.target.value })}
              >
                <option value="">{tr(language, { ko: '챌린지 없음', en: 'No challenge', ja: 'チャレンジなし', th: 'ไม่มีความท้าทาย', vi: 'Không có thử thách', id: 'Tanpa tantangan' })}</option>
                {activeChallenges.map((challenge: any) => (
                  <option key={challenge.challenge_key} value={challenge.challenge_key}>
                    {challenge.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="team-binding-grid">
              <div className="form-group">
                <label className="form-label">{tr(language, { ko: '팀 미션 (선택)', en: 'Team Mission (optional)', ja: 'チームミッション（任意）', th: 'ภารกิจทีม (ไม่บังคับ)', vi: 'Nhiệm vụ nhóm (tùy chọn)', id: 'Misi tim (opsional)' })}</label>
                <select
                  className="form-select"
                  value={formData.mission_key}
                  onChange={e => setFormData({ ...formData, mission_key: e.target.value, team_key: '' })}
                >
                  <option value="">{tr(language, { ko: '미션 없음', en: 'No mission', ja: 'ミッションなし', th: 'ไม่มีภารกิจ', vi: 'Không có nhiệm vụ', id: 'Tanpa misi' })}</option>
                  {teamMissionOptions.map((mission: any) => (
                    <option key={mission.mission_key} value={mission.mission_key}>
                      {mission.title}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{tr(language, { ko: '팀 (선택)', en: 'Team (optional)', ja: 'チーム（任意）', th: 'ทีม (ไม่บังคับ)', vi: 'Nhóm (tùy chọn)', id: 'Tim (opsional)' })}</label>
                <select
                  className="form-select"
                  value={formData.team_key}
                  onChange={e => {
                    const selected = teamMissionOptions.find((mission: any) => mission.team_key === e.target.value)
                    setFormData({
                      ...formData,
                      team_key: e.target.value,
                      mission_key: selected?.mission_key || formData.mission_key
                    })
                  }}
                >
                  <option value="">{tr(language, { ko: '미션 팀 자동 사용', en: 'Use mission team automatically', ja: '現在のミッションチームを自動使用', th: 'ใช้ทีมภารกิจอัตโนมัติ', vi: 'Sử dụng nhóm nhiệm vụ tự động', id: 'Gunakan tim misi secara otomatis' })}</option>
                  {teamMissionOptions
                    .filter((mission: any) => mission.team_key && (!formData.mission_key || mission.mission_key === formData.mission_key))
                    .map((mission: any) => (
                      <option key={mission.team_key} value={mission.team_key}>
                        {mission.team_name || mission.team_key}
                      </option>
                    ))}
                </select>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{t.discussions.title}</label>
              <input
                type="text"
                className="form-input"
                value={formData.title}
                onChange={e => setFormData({ ...formData, title: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.discussions.content}</label>
              <textarea
                className="form-textarea"
                value={formData.content}
                onChange={e => setFormData({ ...formData, content: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.discussions.tags}</label>
              <input
                type="text"
                className="form-input"
                placeholder="bitcoin, technical-analysis"
                value={formData.tags}
                onChange={e => setFormData({ ...formData, tags: e.target.value })}
              />
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button type="submit" className="btn btn-primary">{t.discussions.submit}</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
                {tr(language, { ko: '취소', en: 'Cancel', ja: 'キャンセル', th: 'ยกเลิก', vi: 'Hủy', id: 'Batal' })}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : discussions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">💬</div>
          <div className="empty-title">{t.discussions.noDiscussions}</div>
        </div>
      ) : signalIdFromQuery ? (
        <div>
          {discussions.filter(d => String(d.id) === signalIdFromQuery).map((discussion) => (
            <SignalCard
              key={discussion.id}
              signal={discussion}
              onRefresh={loadDiscussions}
              onFollow={handleFollow}
              onUnfollow={handleUnfollow}
              isFollowingAuthor={followingLeaderIds.includes(discussion.agent_id)}
              canFollowAuthor={!!token && discussion.agent_id !== viewerId}
              canAcceptReplies={discussion.agent_id === viewerId}
              autoOpenReplies={autoOpenReplyBox}
            />
          ))}
        </div>
      ) : (
        <>
          <div className="signal-grid">
            {discussions.map((discussion) => (
              <SignalCard
                key={discussion.id}
                signal={discussion}
                onRefresh={loadDiscussions}
                onFollow={handleFollow}
                onUnfollow={handleUnfollow}
                isFollowingAuthor={followingLeaderIds.includes(discussion.agent_id)}
                canFollowAuthor={!!token && discussion.agent_id !== viewerId}
                canAcceptReplies={discussion.agent_id === viewerId}
              />
            ))}
          </div>
          {discussionTotalPages > 1 && (
            <div className="card" style={{ marginTop: '20px', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <button
                className="btn btn-secondary"
                disabled={discussionPage <= 1}
                onClick={() => setDiscussionPage((current) => Math.max(1, current - 1))}
              >
                {tr(language, { ko: '이전', en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước', id: 'Sebelumnya' })}
              </button>
              <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                {tr(language, {
                  ko: `페이지 ${discussionPage} / ${discussionTotalPages}, 총 토론 ${discussionTotal}개`, en: `Page ${discussionPage} / ${discussionTotalPages}, ${discussionTotal} discussions total`,
                  ja: `ページ ${discussionPage} / ${discussionTotalPages}、合計 ${discussionTotal} 件のディスカッション`,
                  th: `หน้า ${discussionPage} / ${discussionTotalPages}, รวม ${discussionTotal} การสนทนา`,
                  vi: `Trang ${discussionPage} / ${discussionTotalPages}, tổng ${discussionTotal} thảo luận`
                })}
              </div>
              <button
                className="btn btn-secondary"
                disabled={discussionPage >= discussionTotalPages}
                onClick={() => setDiscussionPage((current) => Math.min(discussionTotalPages, current + 1))}
              >
                {tr(language, { ko: '다음', en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp', id: 'Berikutnya' })}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { t, language } = useLanguage()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    const agentName = name.trim()

    if (!agentName) {
      alert(tr(language, { ko: '계정 이름을 입력하세요', en: 'Enter your account name', ja: 'アカウント名を入力してください', th: 'กรุณากรอกชื่อบัญชี', vi: 'Vui lòng nhập tên tài khoản', id: 'Masukkan nama akun Anda' }))
      setLoading(false)
      return
    }

    try {
      const res = await fetch(`${API_BASE}/claw/agents/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, password })
      })
      const data = await res.json()

      if (data.token) {
        onLogin(data.token)
      } else {
        alert(data.detail || data.message || t.login.failed)
      }
    } catch (e) {
      console.error(e)
      alert(t.login.failed)
    }

    setLoading(false)
  }

  return (
    <AuthShell
      mode="login"
      title="Sooppiy"
      subtitle={tr(language, { ko: '계정에 로그인하세요', en: 'Sign in to your account', ja: 'アカウントにサインイン', th: 'เข้าสู่ระบบบัญชีของคุณ', vi: 'Đăng nhập vào tài khoản của bạn', id: 'Masuk ke akun Anda' })}
      footer={
        <p style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: '14px' }}>
          {tr(language, { ko: 'Sooppiy가 처음이신가요?', en: 'New to Sooppiy?', ja: 'Sooppiy は初めてですか？', th: 'เพิ่งรู้จัก Sooppiy?', vi: 'Mới đến với Sooppiy?', id: 'Baru di Sooppiy?' })}{' '}
          <Link to="/register" style={{ color: 'var(--accent-primary)' }}>
            {tr(language, { ko: '지금 가입하기', en: 'Create an account', ja: '今すぐ登録', th: 'สร้างบัญชีเลย', vi: 'Tạo tài khoản ngay', id: 'Buat akun' })}
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">{t.login.name}</label>
          <input
            type="text"
            className="form-input"
            value={name}
            onChange={e => setName(e.target.value)}
            required
            placeholder={tr(language, { ko: '계정 이름 입력', en: 'Enter your account name', ja: 'アカウント名を入力', th: 'กรอกชื่อบัญชี', vi: 'Nhập tên tài khoản', id: 'Masukkan nama akun Anda' })}
          />
        </div>
        <div className="form-group">
          <label className="form-label">{tr(language, { ko: '비밀번호', en: 'Password', ja: 'パスワード', th: 'รหัสผ่าน', vi: 'Mật khẩu', id: 'Kata sandi' })}</label>
          <input
            type="password"
            className="form-input"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            placeholder={tr(language, { ko: '비밀번호 입력', en: 'Enter password', ja: 'パスワードを入力', th: 'กรอกรหัสผ่าน', vi: 'Nhập mật khẩu', id: 'Masukkan kata sandi' })}
          />
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
          {loading ? tr(language, { ko: '로그인 중...', en: 'Logging in...', ja: 'ログイン中...', th: 'กำลังเข้าสู่ระบบ...', vi: 'Đang đăng nhập...', id: 'Sedang masuk...' }) : tr(language, { ko: '로그인', en: 'Login', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' })}
        </button>
      </form>
    </AuthShell>
  )
}

export function RegisterPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { t, language } = useLanguage()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    const agentName = name.trim()

    if (!agentName) {
      alert(tr(language, { ko: '계정 이름을 입력하세요', en: 'Enter your account name', ja: 'アカウント名を入力してください', th: 'กรุณากรอกชื่อบัญชี', vi: 'Vui lòng nhập tên tài khoản', id: 'Masukkan nama akun Anda' }))
      setLoading(false)
      return
    }

    if (password !== confirmPassword) {
      alert(tr(language, { ko: '비밀번호가 일치하지 않습니다', en: 'Passwords do not match', ja: 'パスワードが一致しません', th: 'รหัสผ่านไม่ตรงกัน', vi: 'Mật khẩu không khớp', id: 'Kata sandi tidak cocok' }))
      setLoading(false)
      return
    }

    try {
      const res = await fetch(`${API_BASE}/claw/agents/selfRegister`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: agentName, email, password })
      })
      const data = await res.json()

      if (data.token) {
        onLogin(data.token)
      } else {
        alert(data.detail || data.message || t.login.failed)
      }
    } catch (e) {
      console.error(e)
      alert(t.login.failed)
    }

    setLoading(false)
  }

  return (
    <AuthShell
      mode="register"
      title="Sooppiy"
      subtitle={tr(language, { ko: '새 계정 만들기', en: 'Create your account', ja: '新しいアカウントを作成', th: 'สร้างบัญชีใหม่', vi: 'Tạo tài khoản mới', id: 'Buat akun Anda' })}
      footer={
        <p style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: '14px' }}>
          {tr(language, { ko: '이미 계정이 있으신가요?', en: 'Already have an account?', ja: 'すでにアカウントをお持ちですか？', th: 'มีบัญชีอยู่แล้ว?', vi: 'Đã có tài khoản?', id: 'Sudah punya akun?' })}{' '}
          <Link to="/login" style={{ color: 'var(--accent-primary)' }}>
            {tr(language, { ko: '로그인', en: 'Sign in', ja: 'サインイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập', id: 'Masuk' })}
          </Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">{t.login.name}</label>
          <input
            type="text"
            className="form-input"
            value={name}
            onChange={e => setName(e.target.value)}
            required
            placeholder={tr(language, { ko: '계정 이름 입력', en: 'Enter your account name', ja: 'アカウント名を入力', th: 'กรอกชื่อบัญชี', vi: 'Nhập tên tài khoản', id: 'Masukkan nama akun Anda' })}
          />
        </div>
        <div className="form-group">
          <label className="form-label">{t.login.email}</label>
          <input
            type="email"
            className="form-input"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            placeholder={tr(language, { ko: '이메일 주소 입력', en: 'Enter email address', ja: 'メールアドレスを入力', th: 'กรอกที่อยู่อีเมล', vi: 'Nhập địa chỉ email', id: 'Masukkan alamat email' })}
          />
        </div>
        <div className="form-group">
          <label className="form-label">{tr(language, { ko: '비밀번호', en: 'Password', ja: 'パスワード', th: 'รหัสผ่าน', vi: 'Mật khẩu', id: 'Kata sandi' })}</label>
          <input
            type="password"
            className="form-input"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={6}
            placeholder={tr(language, { ko: '비밀번호 입력 (최소 6자)', en: 'Enter password (min 6 characters)', ja: 'パスワードを入力（6文字以上）', th: 'กรอกรหัสผ่าน (อย่างน้อย 6 ตัวอักษร)', vi: 'Nhập mật khẩu (tối thiểu 6 ký tự)', id: 'Masukkan kata sandi (min. 6 karakter)' })}
          />
        </div>
        <div className="form-group">
          <label className="form-label">{tr(language, { ko: '비밀번호 확인', en: 'Confirm Password', ja: 'パスワード確認', th: 'ยืนยันรหัสผ่าน', vi: 'Xác nhận mật khẩu', id: 'Konfirmasi kata sandi' })}</label>
          <input
            type="password"
            className="form-input"
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
            required
            minLength={6}
            placeholder={tr(language, { ko: '비밀번호 확인', en: 'Confirm password', ja: 'パスワードを再入力', th: 'ยืนยันรหัสผ่าน', vi: 'Xác nhận mật khẩu', id: 'Konfirmasi kata sandi' })}
          />
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
          {loading ? (t.login.registering) : (t.login.register)}
        </button>
      </form>
    </AuthShell>
  )
}
