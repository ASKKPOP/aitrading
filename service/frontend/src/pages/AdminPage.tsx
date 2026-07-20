import { Fragment, useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Manager console — served on administr.sooppiy.com (App.tsx hostname gate).
// Admins sign in with email + password (admin_users, routes_admin_auth.py);
// the 12h session token lives in localStorage. Tabs cover the full operator
// surface: analytics dashboard, members, paid subscriptions, asset/position/
// automation statistics, discussion moderation, leaderboard management,
// admin accounts (superadmin only) and the audit trail.
const ADMIN_TOKEN_KEY = 'sooppiy_admin_token'

type Tab =
  | 'dashboard' | 'members' | 'subscriptions' | 'assets' | 'positions'
  | 'automation' | 'support' | 'discussions' | 'leaderboard' | 'admins' | 'audit'

const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 12, padding: '16px 18px' }
const tableCard: any = { ...card, padding: 0, overflowX: 'auto' }
const th: any = { textAlign: 'left', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted,#8a8073)', padding: '8px 10px', borderBottom: '1px solid var(--border-color,#2a2a28)', whiteSpace: 'nowrap' }
const td: any = { padding: '8px 10px', fontSize: 13, borderBottom: '1px solid var(--border-color,#2a2a28)' }
const chip = (active: boolean): any => ({ padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 13, fontWeight: active ? 700 : 500, border: active ? '1.5px solid var(--accent-primary,#c26a45)' : '1px solid var(--border-color,#2a2a28)', background: active ? 'rgba(194,106,69,0.12)' : 'transparent', color: active ? 'var(--accent-primary,#c26a45)' : 'inherit' })
const dangerBtn: any = { padding: '4px 10px', borderRadius: 6, border: '1px solid #7f1d1d', background: 'transparent', color: '#ef4444', cursor: 'pointer', fontSize: 12 }
const actionBtn: any = { padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border-color,#2a2a28)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }
const primaryBtn: any = { padding: '8px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 13 }
const inputStyle: any = { padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-secondary,#161615)', color: 'var(--text-primary,#fff)', fontSize: 13 }
const sectionTitle: any = { fontSize: 14, fontWeight: 700, margin: '18px 0 10px' }

const fmtMoney = (v: any) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
const fmtTime = (v: any) => String(v || '—').replace('T', ' ').slice(0, 16)
const fmtDate = (v: any) => String(v || '—').slice(0, 10)

// Block explorer for a USDT payment's tx hash, so verifying a pending payment
// is one click from the row instead of a copy-paste into a search box.
// The network comes from the CURRENT usdt_network setting — rows are not
// stamped with the network they were paid on, so if the receiving network is
// ever rotated, links on older rows point at the wrong chain and will simply
// not resolve. That fails safe (a missing tx, never a false match), but verify
// by hand if you have rotated networks since the payment.
const EXPLORER_TX: Record<string, string> = {
  ERC20: 'https://etherscan.io/tx/',
  TRC20: 'https://tronscan.org/#/transaction/',
  BEP20: 'https://bscscan.com/tx/',
  SOL: 'https://solscan.io/tx/',
  POLYGON: 'https://polygonscan.com/tx/',
}
const explorerUrl = (method: string, network: string, reference: string) =>
  method === 'usdt' && EXPLORER_TX[network] && reference
    ? EXPLORER_TX[network] + encodeURIComponent(reference.trim())
    : ''

function StatCards({ items }: { items: [string, any][] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 12, marginBottom: 16 }}>
      {items.map(([label, value]) => (
        <div key={label} style={card}>
          <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{String(value)}</div>
        </div>
      ))}
    </div>
  )
}

function TrendChart({ data, xKey, series, kind }: { data: any[]; xKey: string; series: [string, string][]; kind?: 'line' | 'bar' }) {
  if (!data?.length) return <div style={{ ...card, color: 'var(--text-muted,#8a8073)', fontSize: 13 }}>—</div>
  return (
    <div style={{ ...card, height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        {kind === 'bar' ? (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color,#2a2a28)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={54} />
            <Tooltip contentStyle={{ background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', fontSize: 12 }} />
            {series.map(([key, color]) => <Bar key={key} dataKey={key} fill={color} />)}
          </BarChart>
        ) : (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color,#2a2a28)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={54} />
            <Tooltip contentStyle={{ background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', fontSize: 12 }} />
            {series.map(([key, color]) => <Line key={key} type="monotone" dataKey={key} stroke={color} dot={false} strokeWidth={2} />)}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

export function AdminPage() {
  const { language } = useLanguage()
  const [token, setToken] = useState<string>(() => localStorage.getItem(ADMIN_TOKEN_KEY) || '')
  const [me, setMe] = useState<any | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tab, setTab] = useState<Tab>('dashboard')
  const [error, setError] = useState('')

  const [analytics, setAnalytics] = useState<any | null>(null)
  const [overview, setOverview] = useState<any | null>(null)
  const [users, setUsers] = useState<any | null>(null)
  const [agents, setAgents] = useState<any | null>(null)
  const [memberDetail, setMemberDetail] = useState<any | null>(null)
  const [subs, setSubs] = useState<any | null>(null)
  const [subFilter, setSubFilter] = useState('')
  const [copiedRef, setCopiedRef] = useState<number | null>(null)
  const [paySettings, setPaySettings] = useState<any>(null)
  const [usdtAddr, setUsdtAddr] = useState('')
  const [usdtNet, setUsdtNet] = useState('TRC20')
  const [bankInfo, setBankInfo] = useState('')
  const [contracts, setContracts] = useState<any | null>(null)
  const [planList, setPlanList] = useState<any[]>([])
  const [adminPlans, setAdminPlans] = useState<any[]>([])
  const [grant, setGrant] = useState({ email: '', plan_code: 'junior', days: '30', note: '' })
  const [newPlan, setNewPlan] = useState({ code: '', name: '', price: '', sort: '10' })
  const [assets, setAssets] = useState<any | null>(null)
  const [positions, setPositions] = useState<any | null>(null)
  const [autoStats, setAutoStats] = useState<any | null>(null)
  const [autoRules, setAutoRules] = useState<any | null>(null)
  const [threads, setThreads] = useState<any | null>(null)
  const [activeThread, setActiveThread] = useState<any | null>(null)
  const [reply, setReply] = useState('')
  const [broadcast, setBroadcast] = useState({ title: '', body: '' })
  const [discussions, setDiscussions] = useState<any | null>(null)
  const [replies, setReplies] = useState<Record<number, any[]>>({})
  const [leaderboard, setLeaderboard] = useState<any | null>(null)
  const [lbMetric, setLbMetric] = useState('return')
  const [admins, setAdmins] = useState<any | null>(null)
  const [audit, setAudit] = useState<any | null>(null)
  const [q, setQ] = useState('')
  const [dq, setDq] = useState('')
  const [newAdmin, setNewAdmin] = useState({ email: '', password: '', role: 'operator' })
  const [exclusion, setExclusion] = useState({ agent_id: '', reason: '' })

  const T = {
    title: tr(language, { ko: '관리자 콘솔', en: 'Manager Console', ja: '管理コンソール', th: 'คอนโซลผู้ดูแล', vi: 'Bảng quản trị' }),
    email: tr(language, { ko: '이메일', en: 'Email', ja: 'メール', th: 'อีเมล', vi: 'Email' }),
    password: tr(language, { ko: '비밀번호', en: 'Password', ja: 'パスワード', th: 'รหัสผ่าน', vi: 'Mật khẩu' }),
    signIn: tr(language, { ko: '로그인', en: 'Sign in', ja: 'ログイン', th: 'เข้าสู่ระบบ', vi: 'Đăng nhập' }),
    signOut: tr(language, { ko: '로그아웃', en: 'Sign out', ja: 'ログアウト', th: 'ออกจากระบบ', vi: 'Đăng xuất' }),
    loginHint: tr(language, { ko: '관리자 계정으로 로그인하세요. 첫 계정은 서버에서 scripts/create_admin.py로 생성합니다.', en: 'Sign in with an admin account. Bootstrap the first one with scripts/create_admin.py on the server.', ja: '管理者アカウントでログインしてください。最初のアカウントはサーバー上で scripts/create_admin.py を実行して作成します。', th: 'เข้าสู่ระบบด้วยบัญชีผู้ดูแล บัญชีแรกสร้างด้วย scripts/create_admin.py บนเซิร์ฟเวอร์', vi: 'Đăng nhập bằng tài khoản quản trị. Tạo tài khoản đầu tiên bằng scripts/create_admin.py trên máy chủ.' }),
    invalid: tr(language, { ko: '이메일 또는 비밀번호가 올바르지 않습니다', en: 'Invalid email or password', ja: 'メールアドレスまたはパスワードが正しくありません', th: 'อีเมลหรือรหัสผ่านไม่ถูกต้อง', vi: 'Email hoặc mật khẩu không đúng' }),
    sessionExpired: tr(language, { ko: '세션이 만료되었습니다 — 다시 로그인하세요', en: 'Session expired — sign in again', ja: 'セッションが期限切れです — 再度ログインしてください', th: 'เซสชันหมดอายุ — เข้าสู่ระบบใหม่', vi: 'Phiên đã hết hạn — đăng nhập lại' }),
    tabDashboard: tr(language, { ko: '대시보드', en: 'Dashboard', ja: 'ダッシュボード', th: 'แดชบอร์ด', vi: 'Bảng điều khiển' }),
    tabMembers: tr(language, { ko: '회원 관리', en: 'Members', ja: '会員管理', th: 'จัดการสมาชิก', vi: 'Thành viên' }),
    tabSubs: tr(language, { ko: '구독 관리', en: 'Subscriptions', ja: '購読管理', th: 'จัดการการสมัคร', vi: 'Đăng ký' }),
    tabAssets: tr(language, { ko: '자산 통계', en: 'Assets', ja: '資産統計', th: 'สถิติสินทรัพย์', vi: 'Tài sản' }),
    tabPositions: tr(language, { ko: '포지션 통계', en: 'Positions', ja: 'ポジション統計', th: 'สถิติสถานะ', vi: 'Vị thế' }),
    tabAutomation: tr(language, { ko: '자동화 통계', en: 'Automation', ja: '自動化統計', th: 'สถิติระบบอัตโนมัติ', vi: 'Tự động hóa' }),
    tabSupport: tr(language, { ko: '문의 · 알림', en: 'Support & alerts', ja: '問い合わせ・通知', th: 'ซัพพอร์ต · การแจ้งเตือน', vi: 'Hỗ trợ · Thông báo' }),
    tabDiscussions: tr(language, { ko: '토론 관리', en: 'Discussions', ja: '議論管理', th: 'จัดการกระทู้', vi: 'Thảo luận' }),
    tabLeaderboard: tr(language, { ko: '리더보드 관리', en: 'Leaderboard', ja: 'リーダーボード管理', th: 'จัดการลีดเดอร์บอร์ด', vi: 'Bảng xếp hạng' }),
    tabAdmins: tr(language, { ko: '관리자 계정', en: 'Admins', ja: '管理者アカウント', th: 'บัญชีผู้ดูแล', vi: 'Quản trị viên' }),
    tabAudit: tr(language, { ko: '감사 로그', en: 'Audit', ja: '監査ログ', th: 'บันทึกตรวจสอบ', vi: 'Nhật ký kiểm toán' }),
    noData: tr(language, { ko: '데이터 없음', en: 'No data', ja: 'データなし', th: 'ไม่มีข้อมูล', vi: 'Không có dữ liệu' }),
    search: tr(language, { ko: '검색', en: 'Search', ja: '検索', th: 'ค้นหา', vi: 'Tìm kiếm' }),
    del: tr(language, { ko: '삭제', en: 'Delete', ja: '削除', th: 'ลบ', vi: 'Xóa' }),
    delConfirm: tr(language, { ko: '정말 삭제할까요? 이 계정의 모든 데이터가 함께 삭제됩니다.', en: 'Really delete? All of this account\'s data is deleted with it.', ja: '本当に削除しますか？このアカウントの全データも一緒に削除されます。', th: 'ลบจริงหรือไม่ ข้อมูลทั้งหมดของบัญชีนี้จะถูกลบไปด้วย', vi: 'Xóa thật chứ? Toàn bộ dữ liệu của tài khoản này sẽ bị xóa theo.' }),
    suspend: tr(language, { ko: '정지', en: 'Suspend', ja: '停止', th: 'ระงับ', vi: 'Tạm ngưng' }),
    activate: tr(language, { ko: '해제', en: 'Activate', ja: '解除', th: 'ปลดระงับ', vi: 'Kích hoạt' }),
    detail: tr(language, { ko: '상세', en: 'Detail', ja: '詳細', th: 'รายละเอียด', vi: 'Chi tiết' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng' }),
    approve: tr(language, { ko: '승인', en: 'Approve', ja: '承認', th: 'อนุมัติ', vi: 'Duyệt' }),
    reject: tr(language, { ko: '거절', en: 'Reject', ja: '却下', th: 'ปฏิเสธ', vi: 'Từ chối' }),
    extend30: tr(language, { ko: '+30일', en: '+30 days', ja: '+30日', th: '+30 วัน', vi: '+30 ngày' }),
    cancelSub: tr(language, { ko: '해지', en: 'Cancel', ja: '解約', th: 'ยกเลิก', vi: 'Hủy' }),
    cancelConfirm: tr(language, { ko: '이 구독을 해지할까요? 회원은 즉시 구독 페이지로 이동됩니다.', en: 'Cancel this subscription? The member is gated to the subscribe page immediately.', ja: 'この購読を解約しますか？会員は直ちに購読ページへ誘導されます。', th: 'ยกเลิกการสมัครนี้หรือไม่ สมาชิกจะถูกพาไปหน้าสมัครทันที', vi: 'Hủy đăng ký này? Thành viên sẽ bị chuyển ngay tới trang đăng ký.' }),
    grantTitle: tr(language, { ko: '수동 부여 — 결제 없이 플랜 지급 (무료 제공·기존회원·엔터프라이즈 계약)', en: 'Manual grant — assign a plan without payment (comps, grandfathered members, enterprise contracts)', ja: '手動付与 — 決済なしでプランを割り当て（無償提供・既存会員・エンタープライズ契約）', th: 'ให้สิทธิ์เอง — กำหนดแพลนโดยไม่ต้องชำระเงิน (ให้ฟรี, สมาชิกเดิม, สัญญาองค์กร)', vi: 'Cấp thủ công — gán gói không cần thanh toán (tặng, thành viên cũ, hợp đồng doanh nghiệp)' }),
    grantBtn: tr(language, { ko: '부여', en: 'Grant', ja: '付与', th: 'ให้สิทธิ์', vi: 'Cấp' }),
    usdtTitle: tr(language, { ko: 'USDT 입금 주소 등록', en: 'USDT receiving address', ja: 'USDT入金アドレス', th: 'ที่อยู่รับ USDT', vi: 'Địa chỉ nhận USDT' }),
    usdtHint: tr(language, {
      ko: '구독자에게 이 주소로 송금하라고 안내합니다. 여기 저장한 값이 곧바로 결제 페이지에 표시되므로, 지갑에서 복사해 붙여넣고 저장 전에 반드시 확인하세요. 비워두면 결제 페이지에서 USDT 항목이 사라집니다.',
      en: 'Subscribers are told to send real money to whatever is saved here, and it appears on the payment page immediately. Paste it straight from your wallet and check it before saving. Leaving it empty removes USDT from the payment page.',
      ja: 'ここに保存したアドレスへ送金するよう購読者に案内され、決済ページに即座に表示されます。ウォレットから直接コピーして貼り付け、保存前に必ず確認してください。空欄にすると決済ページからUSDTが消えます。',
      th: 'ผู้สมัครจะถูกแจ้งให้โอนเงินจริงมายังที่อยู่ที่บันทึกไว้ที่นี่ และจะแสดงบนหน้าชำระเงินทันที คัดลอกจากกระเป๋าเงินโดยตรงและตรวจสอบก่อนบันทึก ถ้าเว้นว่างไว้ USDT จะหายไปจากหน้าชำระเงิน',
      vi: 'Người đăng ký được hướng dẫn gửi tiền thật tới địa chỉ lưu ở đây, và nó hiện ngay trên trang thanh toán. Dán trực tiếp từ ví và kiểm tra trước khi lưu. Để trống sẽ gỡ USDT khỏi trang thanh toán.' }),
    usdtAddrPlaceholder: tr(language, { ko: '지갑에서 복사한 USDT 주소', en: 'USDT address, pasted from your wallet', ja: 'ウォレットからコピーしたUSDTアドレス', th: 'ที่อยู่ USDT ที่คัดลอกจากกระเป๋าเงิน', vi: 'Địa chỉ USDT dán từ ví của bạn' }),
    usdtSave: tr(language, { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu' }),
    usdtConfirm: tr(language, {
      ko: '이 주소로 구독자의 실제 자금이 입금됩니다. 지갑의 주소와 정확히 일치하는지 확인하셨습니까?',
      en: 'Subscribers will send real funds to this address. Have you checked it character-for-character against your wallet?',
      ja: 'このアドレスに購読者の実際の資金が入金されます。ウォレットのアドレスと一字一句一致することを確認しましたか？',
      th: 'เงินจริงของผู้สมัครจะถูกส่งไปยังที่อยู่นี้ คุณตรวจสอบตรงกันทุกตัวอักษรกับกระเป๋าเงินแล้วหรือยัง',
      vi: 'Người đăng ký sẽ gửi tiền thật tới địa chỉ này. Bạn đã đối chiếu từng ký tự với ví chưa?' }),
    usdtLive: tr(language, { ko: '결제 페이지에 표시 중', en: 'Live on the payment page', ja: '決済ページに表示中', th: 'แสดงอยู่บนหน้าชำระเงิน', vi: 'Đang hiển thị trên trang thanh toán' }),
    refCopy: tr(language, { ko: '복사', en: 'Copy', ja: 'コピー', th: 'คัดลอก', vi: 'Sao chép' }),
    refCopied: tr(language, { ko: '복사됨', en: 'Copied', ja: 'コピー済み', th: 'คัดลอกแล้ว', vi: 'Đã sao chép' }),
    refVerify: tr(language, { ko: '체인에서 확인', en: 'Verify on chain', ja: 'チェーンで確認', th: 'ตรวจสอบบนเชน', vi: 'Kiểm tra trên chuỗi' }),
    bankTitle: tr(language, { ko: '계좌이체 정보 등록', en: 'Bank transfer details', ja: '銀行振込先の登録', th: 'ข้อมูลโอนเงินธนาคาร', vi: 'Thông tin chuyển khoản' }),
    bankHint: tr(language, { ko: '구독 페이지에 그대로 표시됩니다. 은행명·계좌번호·예금주를 줄바꿈으로 적어주세요.', en: 'Shown verbatim on the Subscribe page. Bank, account number and holder name, one per line.', ja: '購読ページにそのまま表示されます。銀行名・口座番号・名義を改行で入力してください。', th: 'แสดงตามที่กรอกบนหน้าสมัคร ใส่ธนาคาร เลขบัญชี และชื่อบัญชี บรรทัดละรายการ', vi: 'Hiển thị nguyên văn trên trang đăng ký. Ngân hàng, số tài khoản và chủ tài khoản, mỗi dòng một mục.' }),
    bankPlaceholder: tr(language, { ko: '국민은행 123456-78-901234\n예금주: (주)수피', en: 'Bank of America 123456789\nAccount holder: Sooppiy Inc.', ja: '三菱UFJ銀行 123-4567890\n名義: Sooppiy', th: 'ธนาคารกสิกรไทย 123-4-56789-0\nชื่อบัญชี: Sooppiy', vi: 'Vietcombank 0123456789\nChủ tài khoản: Sooppiy' }),
    bankUnset: tr(language, { ko: '미등록 — 계좌이체를 선택한 회원에게 보낼 곳이 표시되지 않습니다', en: 'Not set — members choosing bank transfer are shown no destination', ja: '未登録 — 銀行振込を選んだ会員に送金先が表示されません', th: 'ยังไม่ตั้งค่า — สมาชิกที่เลือกโอนธนาคารจะไม่เห็นปลายทาง', vi: 'Chưa đặt — thành viên chọn chuyển khoản không thấy nơi nhận' }),
    usdtFromEnv: tr(language, { ko: '.env 값 사용 중 (저장하면 대체됨)', en: 'currently from .env (saving replaces it)', ja: '.env の値を使用中（保存すると置き換わります）', th: 'ใช้ค่าจาก .env อยู่ (บันทึกแล้วจะแทนที่)', vi: 'Đang dùng giá trị .env (lưu sẽ thay thế)' }),
    usdtUnset: tr(language, { ko: '주소 미등록 — 결제 페이지에 USDT가 표시되지 않습니다', en: 'No address set — USDT is not offered on the payment page', ja: 'アドレス未登録 — 決済ページにUSDTは表示されません', th: 'ยังไม่ตั้งที่อยู่ — ไม่มี USDT บนหน้าชำระเงิน', vi: 'Chưa đặt địa chỉ — không hiển thị USDT trên trang thanh toán' }),
    grantDays: tr(language, { ko: '일수', en: 'Days', ja: '日数', th: 'จำนวนวัน', vi: 'Số ngày' }),
    grantNote: tr(language, { ko: '메모 (선택)', en: 'Note (optional)', ja: 'メモ（任意）', th: 'หมายเหตุ (ไม่บังคับ)', vi: 'Ghi chú (tùy chọn)' }),
    grantReplaces: tr(language, { ko: '기존 활성/대기 구독은 자동으로 대체됩니다.', en: 'Replaces any existing active/pending subscription.', ja: '既存の有効・保留中の購読は自動的に置き換えられます。', th: 'จะแทนที่การสมัครที่ใช้งานอยู่หรือรออยู่เดิม', vi: 'Thay thế mọi đăng ký đang hoạt động/chờ xử lý.' }),
    planMgmt: tr(language, { ko: '플랜 관리', en: 'Plan management', ja: 'プラン管理', th: 'จัดการแพลน', vi: 'Quản lý gói' }),
    planMgmtHint: tr(language, { ko: '가격·이름 변경은 신규 결제부터 적용됩니다. 구독 이력이 있는 플랜은 삭제 대신 비활성화하세요.', en: 'Price/name changes apply to new payments. Plans with history deactivate instead of delete.', ja: '価格・名称の変更は新規決済から適用されます。購読履歴のあるプランは削除せず無効化してください。', th: 'การเปลี่ยนราคา/ชื่อมีผลกับการชำระเงินใหม่ แพลนที่มีประวัติให้ปิดใช้งานแทนการลบ', vi: 'Đổi giá/tên áp dụng cho thanh toán mới. Gói đã có lịch sử thì vô hiệu hóa thay vì xóa.' }),
    planAdd: tr(language, { ko: '플랜 추가', en: 'Add plan', ja: 'プラン追加', th: 'เพิ่มแพลน', vi: 'Thêm gói' }),
    planCode: tr(language, { ko: '코드 (예: gold)', en: 'Code (e.g. gold)', ja: 'コード（例: gold）', th: 'โค้ด (เช่น gold)', vi: 'Mã (vd: gold)' }),
    planName: tr(language, { ko: '이름', en: 'Name', ja: '名称', th: 'ชื่อ', vi: 'Tên' }),
    planPrice: tr(language, { ko: '월 $', en: '$/month', ja: '月額 $', th: '$ / เดือน', vi: '$ / tháng' }),
    planSort: tr(language, { ko: '순서', en: 'Sort', ja: '順序', th: 'ลำดับ', vi: 'Thứ tự' }),
    editName: tr(language, { ko: '이름 변경', en: 'Rename', ja: '名称変更', th: 'เปลี่ยนชื่อ', vi: 'Đổi tên' }),
    editPrice: tr(language, { ko: '가격 변경', en: 'Set price', ja: '価格変更', th: 'ตั้งราคา', vi: 'Đặt giá' }),
    planOff: tr(language, { ko: '비활성', en: 'Deactivate', ja: '無効', th: 'ปิดใช้งาน', vi: 'Vô hiệu' }),
    planOn: tr(language, { ko: '활성', en: 'Activate', ja: '有効', th: 'เปิดใช้งาน', vi: 'Kích hoạt' }),
    subscriberRows: tr(language, { ko: '구독 이력', en: 'History', ja: '履歴', th: 'ประวัติ', vi: 'Lịch sử' }),
    status: tr(language, { ko: '상태', en: 'Status', ja: '状態', th: 'สถานะ', vi: 'Trạng thái' }),
    plan: tr(language, { ko: '플랜', en: 'Plan', ja: 'プラン', th: 'แพลน', vi: 'Gói' }),
    method: tr(language, { ko: '결제수단', en: 'Method', ja: '決済手段', th: 'ช่องทางชำระ', vi: 'Phương thức' }),
    reference: tr(language, { ko: '참조', en: 'Reference', ja: '参照', th: 'อ้างอิง', vi: 'Tham chiếu' }),
    amount: tr(language, { ko: '금액', en: 'Amount', ja: '金額', th: 'จำนวนเงิน', vi: 'Số tiền' }),
    created: tr(language, { ko: '생성일', en: 'Created', ja: '作成日', th: 'วันที่สร้าง', vi: 'Ngày tạo' }),
    expires: tr(language, { ko: '만료일', en: 'Expires', ja: '有効期限', th: 'วันหมดอายุ', vi: 'Ngày hết hạn' }),
    member: tr(language, { ko: '회원', en: 'Member', ja: '会員', th: 'สมาชิก', vi: 'Thành viên' }),
    agent: tr(language, { ko: '에이전트', en: 'Agent', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' }),
    contracts: tr(language, { ko: '엔터프라이즈 상담 요청', en: 'Enterprise contract requests', ja: 'エンタープライズ相談リクエスト', th: 'คำขอสัญญาองค์กร', vi: 'Yêu cầu hợp đồng doanh nghiệp' }),
    contacted: tr(language, { ko: '연락함', en: 'Contacted', ja: '連絡済み', th: 'ติดต่อแล้ว', vi: 'Đã liên hệ' }),
    closed: tr(language, { ko: '종료', en: 'Closed', ja: '終了', th: 'ปิดแล้ว', vi: 'Đã đóng' }),
    signups: tr(language, { ko: '일별 가입', en: 'Signups per day', ja: '日別登録', th: 'สมัครต่อวัน', vi: 'Đăng ký mỗi ngày' }),
    trades: tr(language, { ko: '일별 거래', en: 'Trades per day', ja: '日別取引', th: 'เทรดต่อวัน', vi: 'Giao dịch mỗi ngày' }),
    revenue: tr(language, { ko: '월별 매출', en: 'Revenue per month', ja: '月別売上', th: 'รายได้ต่อเดือน', vi: 'Doanh thu mỗi tháng' }),
    equityCurve: tr(language, { ko: '플랫폼 자산 추이 (30일)', en: 'Platform equity (30 days)', ja: 'プラットフォーム資産推移（30日）', th: 'มูลค่าสินทรัพย์แพลตฟอร์ม (30 วัน)', vi: 'Tài sản nền tảng (30 ngày)' }),
    topMembers: tr(language, { ko: '자산 상위 회원', en: 'Top members by equity', ja: '資産上位会員', th: 'สมาชิกสินทรัพย์สูงสุด', vi: 'Thành viên tài sản cao nhất' }),
    runsPerDay: tr(language, { ko: '일별 자동화 실행 (14일)', en: 'Automation runs per day (14d)', ja: '日別自動化実行（14日）', th: 'การรันอัตโนมัติต่อวัน (14 วัน)', vi: 'Lượt chạy tự động mỗi ngày (14 ngày)' }),
    byAgent: tr(language, { ko: '에이전트별 실행 (30일)', en: 'Runs by agent (30d)', ja: 'エージェント別実行（30日）', th: 'การรันตามเอเจนต์ (30 วัน)', vi: 'Lượt chạy theo agent (30 ngày)' }),
    skipReasons: tr(language, { ko: '결과 분포 (30일)', en: 'Outcome breakdown (30d)', ja: '結果分布（30日）', th: 'สัดส่วนผลลัพธ์ (30 วัน)', vi: 'Phân bố kết quả (30 ngày)' }),
    rules: tr(language, { ko: '자동화 규칙', en: 'Automation rules', ja: '自動化ルール', th: 'กฎอัตโนมัติ', vi: 'Quy tắc tự động' }),
    replies: tr(language, { ko: '답글', en: 'Replies', ja: '返信', th: 'การตอบกลับ', vi: 'Trả lời' }),
    exclude: tr(language, { ko: '리더보드 제외', en: 'Exclude', ja: 'リーダーボード除外', th: 'ยกเว้นจากลีดเดอร์บอร์ด', vi: 'Loại khỏi bảng xếp hạng' }),
    include: tr(language, { ko: '제외 해제', en: 'Include', ja: '除外解除', th: 'ยกเลิกการยกเว้น', vi: 'Đưa lại vào' }),
    refreshNow: tr(language, { ko: '지금 갱신', en: 'Refresh now', ja: '今すぐ更新', th: 'รีเฟรชตอนนี้', vi: 'Làm mới ngay' }),
    exclusions: tr(language, { ko: '제외 목록', en: 'Exclusions', ja: '除外リスト', th: 'รายการที่ยกเว้น', vi: 'Danh sách loại trừ' }),
    reason: tr(language, { ko: '사유', en: 'Reason', ja: '理由', th: 'เหตุผล', vi: 'Lý do' }),
    addAdmin: tr(language, { ko: '관리자 추가', en: 'Add admin', ja: '管理者追加', th: 'เพิ่มผู้ดูแล', vi: 'Thêm quản trị viên' }),
    role: tr(language, { ko: '역할', en: 'Role', ja: '役割', th: 'บทบาท', vi: 'Vai trò' }),
    disable: tr(language, { ko: '비활성화', en: 'Disable', ja: '無効化', th: 'ปิดใช้งาน', vi: 'Vô hiệu hóa' }),
    enable: tr(language, { ko: '활성화', en: 'Enable', ja: '有効化', th: 'เปิดใช้งาน', vi: 'Bật' }),
    resetPw: tr(language, { ko: '비밀번호 재설정', en: 'Reset password', ja: 'パスワード再設定', th: 'รีเซ็ตรหัสผ่าน', vi: 'Đặt lại mật khẩu' }),
    lastLogin: tr(language, { ko: '마지막 로그인', en: 'Last login', ja: '最終ログイン', th: 'เข้าสู่ระบบล่าสุด', vi: 'Đăng nhập cuối' }),
    action: tr(language, { ko: '작업', en: 'Action', ja: '操作', th: 'การกระทำ', vi: 'Hành động' }),
    target: tr(language, { ko: '대상', en: 'Target', ja: '対象', th: 'เป้าหมาย', vi: 'Đối tượng' }),
    time: tr(language, { ko: '시각', en: 'Time', ja: '時刻', th: 'เวลา', vi: 'Thời gian' }),
  }

  const hdr = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }

  async function call(path: string, opts: RequestInit = {}) {
    const used = token
    const r = await fetch(`${API_BASE}/admin/${path}`, { headers: hdr, ...opts })
    if (r.status === 401) {
      // Only kill the session when the 401 belongs to the CURRENT token — a
      // stale in-flight request resolving late must not log out a fresh login.
      if (localStorage.getItem(ADMIN_TOKEN_KEY) === used) {
        localStorage.removeItem(ADMIN_TOKEN_KEY)
        setToken(''); setMe(null); setError(T.sessionExpired)
      }
      throw new Error('401')
    }
    if (!r.ok) {
      const body = await r.json().catch(() => null)
      throw new Error(body?.detail || String(r.status))
    }
    return r.json()
  }

  async function login() {
    setError('')
    const r = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!r.ok) { setError(T.invalid); return }
    const body = await r.json()
    localStorage.setItem(ADMIN_TOKEN_KEY, body.token)
    setToken(body.token)
    setMe({ id: body.admin_id, email: body.email, role: body.role })
    setPassword('')
  }

  async function logout() {
    try { await fetch(`${API_BASE}/admin/logout`, { method: 'POST', headers: hdr }) } catch { /* ignore */ }
    localStorage.removeItem(ADMIN_TOKEN_KEY)
    setToken(''); setMe(null)
  }

  useEffect(() => {
    if (!token) return
    call('me').then(setMe).catch(() => { /* handled in call */ })
  }, [token])

  async function refresh(which: Tab = tab) {
    if (!token) return
    setError('')
    try {
      if (which === 'dashboard') {
        setAnalytics(await call('analytics'))
        setOverview(await call('overview'))
      }
      if (which === 'members') {
        setUsers(await call('users?limit=200'))
        setAgents(await call(`agents?q=${encodeURIComponent(q)}&limit=100`))
      }
      if (which === 'subscriptions') {
        setSubs(await call(`subscriptions?status=${encodeURIComponent(subFilter)}&limit=100`))
        setContracts(await call('contracts?limit=100'))
        setAdminPlans((await call('plans')).plans || [])
        const p = await fetch(`${API_BASE}/subscriptions/plans`).then(r => r.json())
        setPlanList(p.plans || [])
        const pay = await call('settings/payment')
        setPaySettings(pay)
        setUsdtAddr(pay?.usdt_address?.value || '')
        setUsdtNet(pay?.usdt_network?.value || 'TRC20')
        setBankInfo(pay?.bank_transfer_info?.value || '')
      }
      if (which === 'assets') setAssets(await call('stats/assets'))
      if (which === 'positions') setPositions(await call('stats/positions'))
      if (which === 'automation') {
        setAutoStats(await call('stats/automation'))
        setAutoRules(await call('automation?limit=100'))
      }
      if (which === 'support') setThreads(await call('support/threads?limit=200'))
      if (which === 'discussions') setDiscussions(await call(`discussions?q=${encodeURIComponent(dq)}&limit=100`))
      if (which === 'leaderboard') setLeaderboard(await call(`leaderboard?metric=${lbMetric}&limit=100`))
      if (which === 'admins') setAdmins(await call('admins'))
      if (which === 'audit') setAudit(await call('audit?limit=200'))
    } catch (e: any) {
      if (e?.message !== '401') setError(String(e?.message || e))
    }
  }

  useEffect(() => { refresh(tab) }, [tab, token, subFilter, lbMetric])

  // Returns true only when the write succeeded — callers must not clear a typed
  // reply/broadcast composer on failure, or the admin loses what they wrote.
  async function act(path: string, opts: RequestInit, then: Tab): Promise<boolean> {
    setError('')
    try { await call(path, opts); await refresh(then); return true }
    catch (e: any) { if (e?.message !== '401') setError(String(e?.message || e)); return false }
  }

  // ── Login screen ──
  if (!token) {
    return (
      <div style={{ maxWidth: 420, margin: '80px auto', padding: 24 }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>🔐 {T.title}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary,#8a8073)', marginBottom: 16 }}>{T.loginHint}</p>
        <input placeholder={T.email} value={email} onChange={e => setEmail(e.target.value)}
          style={{ ...inputStyle, width: '100%', marginBottom: 10 }} autoComplete="username" />
        <input placeholder={T.password} type="password" value={password} onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && login()}
          style={{ ...inputStyle, width: '100%', marginBottom: 14 }} autoComplete="current-password" />
        {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>⚠️ {error}</div>}
        <button onClick={login} style={{ ...primaryBtn, width: '100%', padding: '10px 20px' }}>{T.signIn}</button>
      </div>
    )
  }

  const tabs: [Tab, string][] = [
    ['dashboard', T.tabDashboard], ['members', T.tabMembers], ['subscriptions', T.tabSubs],
    ['assets', T.tabAssets], ['positions', T.tabPositions], ['automation', T.tabAutomation],
    ['support', T.tabSupport],
    ['discussions', T.tabDiscussions], ['leaderboard', T.tabLeaderboard],
    ...(me?.role === 'superadmin' ? [['admins', T.tabAdmins] as [Tab, string]] : []),
    ['audit', T.tabAudit],
  ]

  const ov = overview?.overview
  const subStatusColor = (s: string) =>
    s === 'active' ? '#22c55e' : s === 'pending' ? '#eab308' : s === 'rejected' ? '#ef4444' : 'var(--text-muted,#8a8073)'

  return (
    // The console renders on its own domain with no top nav above it, so the
    // heading sat 24px from the viewport edge and read as clipped. Give it real
    // breathing room at the top.
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 16px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>🔐 {T.title}</h1>
        <span style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)' }}>{me?.email} · {me?.role}</span>
        <button onClick={logout} style={{ ...actionBtn, marginLeft: 'auto' }}>{T.signOut}</button>
      </div>
      <div style={{ display: 'flex', gap: 8, margin: '14px 0', flexWrap: 'wrap' }}>
        {tabs.map(([key, label]) => (
          <button key={key} style={chip(tab === key)} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>
      {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>⚠️ {error}</div>}

      {/* ── Dashboard ── */}
      {tab === 'dashboard' && analytics && ov && (
        <>
          <StatCards items={[
            [tr(language, { ko: '전체 회원', en: 'Total members', ja: '総会員数', th: 'สมาชิกทั้งหมด', vi: 'Tổng thành viên' }), analytics.total_users],
            [tr(language, { ko: '활성 구독', en: 'Active subscriptions', ja: '有効な購読', th: 'การสมัครที่ใช้งาน', vi: 'Đăng ký đang hoạt động' }), analytics.active_subscriptions],
            [tr(language, { ko: '에이전트', en: 'Agents', ja: 'エージェント', th: 'เอเจนต์', vi: 'Agent' }), ov.agents],
            [tr(language, { ko: '거래', en: 'Trades', ja: '取引', th: 'การเทรด', vi: 'Giao dịch' }), ov.trades],
            [tr(language, { ko: '미결제 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะที่เปิดอยู่', vi: 'Vị thế đang mở' }), ov.open_positions],
            [tr(language, { ko: '자동화 규칙 (활성)', en: 'Automation rules (on)', ja: '自動化ルール（有効）', th: 'กฎอัตโนมัติ (เปิด)', vi: 'Quy tắc tự động (bật)' }), `${ov.automation_rules} (${ov.automation_rules_enabled})`],
            [tr(language, { ko: '토론', en: 'Discussions', ja: '議論', th: 'กระทู้', vi: 'Thảo luận' }), ov.discussions],
            [tr(language, { ko: '모의 자금 합계', en: 'Total sim cash', ja: 'シミュレーション資金合計', th: 'เงินจำลองรวม', vi: 'Tổng tiền mô phỏng' }), fmtMoney(ov.total_sim_cash)],
          ]} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 12 }}>
            <div><div style={sectionTitle}>{T.signups}</div>
              <TrendChart data={analytics.signups_by_day} xKey="day" series={[['c', '#c26a45']]} /></div>
            <div><div style={sectionTitle}>{T.trades}</div>
              <TrendChart data={analytics.trades_by_day} xKey="day" series={[['c', '#22c55e']]} /></div>
            <div><div style={sectionTitle}>{T.revenue}</div>
              <TrendChart data={analytics.revenue_by_month} xKey="month" series={[['revenue', '#c26a45']]} kind="bar" /></div>
          </div>
          <div style={sectionTitle}>{tr(language, { ko: '플랜별 구독 현황', en: 'Subscriptions by plan', ja: 'プラン別購読状況', th: 'การสมัครตามแพลน', vi: 'Đăng ký theo gói' })}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 480 }}>
              <thead><tr><th style={th}>{T.plan}</th><th style={th}>{T.status}</th><th style={th}>#</th></tr></thead>
              <tbody>
                {(analytics.subscriptions_matrix || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.plan_code}</td>
                    <td style={{ ...td, color: subStatusColor(r.status) }}>{r.status}</td><td style={td}>{r.c}</td></tr>
                ))}
                {!(analytics.subscriptions_matrix || []).length && <tr><td style={td} colSpan={3}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Members ── */}
      {tab === 'members' && (
        <>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.email}</th><th style={th}>{T.status}</th><th style={th}>{T.plan}</th><th style={th}>MFA</th><th style={th}>{T.agent}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(users?.users || []).map((u: any) => (
                  <tr key={u.id}>
                    <td style={td}>{u.id}</td><td style={{ ...td, fontWeight: 600 }}>{u.email}</td>
                    <td style={{ ...td, color: u.status === 'suspended' ? '#ef4444' : '#22c55e' }}>{u.status}</td>
                    <td style={td}>{u.plan_code || '—'}</td>
                    <td style={td}>{u.mfa_enabled ? '✓' : '—'}</td>
                    <td style={td}>{u.agent_name || '—'}</td>
                    <td style={td}>{fmtDate(u.created_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      <button style={actionBtn} onClick={async () => {
                        setMemberDetail(null)
                        try { setMemberDetail(await call(`members/${u.id}`)) } catch { /* handled */ }
                      }}>{T.detail}</button>{' '}
                      {u.status === 'suspended'
                        ? <button style={actionBtn} onClick={() => act(`members/${u.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'active' }) }, 'members')}>{T.activate}</button>
                        : <button style={dangerBtn} onClick={() => act(`members/${u.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'suspended' }) }, 'members')}>{T.suspend}</button>}{' '}
                      <button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`users/${u.id}`, { method: 'DELETE' }, 'members')}>{T.del}</button>
                    </td>
                  </tr>
                ))}
                {!(users?.users || []).length && <tr><td style={td} colSpan={8}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>

          {memberDetail && (
            <div style={{ ...card, marginTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <strong style={{ fontSize: 14 }}>{memberDetail.user.email}</strong>
                <span style={{ fontSize: 12, color: subStatusColor(memberDetail.user.status === 'active' ? 'active' : 'rejected') }}>{memberDetail.user.status}</span>
                <button style={{ ...actionBtn, marginLeft: 'auto' }} onClick={() => setMemberDetail(null)}>{T.close}</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 12, marginTop: 12 }}>
                <div>
                  <div style={sectionTitle}>{tr(language, { ko: '구독 이력', en: 'Subscription history', ja: '購読履歴', th: 'ประวัติการสมัคร', vi: 'Lịch sử đăng ký' })}</div>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead><tr><th style={th}>{T.plan}</th><th style={th}>{T.status}</th><th style={th}>{T.method}</th><th style={th}>{T.expires}</th></tr></thead>
                    <tbody>
                      {(memberDetail.subscriptions || []).map((s: any) => (
                        <tr key={s.id}><td style={td}>{s.plan_code}</td>
                          <td style={{ ...td, color: subStatusColor(s.status) }}>{s.status}</td>
                          <td style={td}>{s.method}</td><td style={td}>{fmtDate(s.expires_at)}</td></tr>
                      ))}
                      {!(memberDetail.subscriptions || []).length && <tr><td style={td} colSpan={4}>{T.noData}</td></tr>}
                    </tbody>
                  </table>
                </div>
                <div>
                  <div style={sectionTitle}>{tr(language, { ko: '자산 추이', en: 'Equity history', ja: '資産推移', th: 'ประวัติสินทรัพย์', vi: 'Lịch sử tài sản' })}</div>
                  <TrendChart data={memberDetail.equity_history || []} xKey="recorded_at" series={[['total_value', '#c26a45']]} />
                </div>
              </div>
              <div style={sectionTitle}>{tr(language, { ko: '보유 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะที่เปิดอยู่', vi: 'Vị thế đang mở' })} ({(memberDetail.positions || []).length})</div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Symbol</th><th style={th}>Side</th><th style={th}>Qty</th><th style={th}>Entry</th><th style={th}>Now</th></tr></thead>
                <tbody>
                  {(memberDetail.positions || []).slice(0, 10).map((p: any, i: number) => (
                    <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{p.symbol}</td><td style={td}>{p.side}</td>
                      <td style={td}>{p.quantity}</td><td style={td}>{p.entry_price}</td><td style={td}>{p.current_price ?? '—'}</td></tr>
                  ))}
                  {!(memberDetail.positions || []).length && <tr><td style={td} colSpan={5}>{T.noData}</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          <div style={sectionTitle}>{tr(language, { ko: '에이전트 계정', en: 'Agent accounts', ja: 'エージェントアカウント', th: 'บัญชีเอเจนต์', vi: 'Tài khoản agent' })}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder={T.search} value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && refresh('members')} style={{ ...inputStyle, width: 260 }} />
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.agent}</th><th style={th}>Cash</th><th style={th}>Points</th><th style={th}>Trades</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(agents?.agents || []).map((a: any) => (
                  <tr key={a.id}>
                    <td style={td}>{a.id}</td><td style={{ ...td, fontWeight: 600 }}>{a.name}</td>
                    <td style={td}>{fmtMoney(a.cash)}</td><td style={td}>{a.points}</td>
                    <td style={td}>{a.trade_count}</td><td style={td}>{fmtDate(a.created_at)}</td>
                    <td style={td}><button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`agents/${a.id}`, { method: 'DELETE' }, 'members')}>{T.del}</button></td>
                  </tr>
                ))}
                {!(agents?.agents || []).length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Subscriptions ── */}
      {tab === 'subscriptions' && (
        <>
          {/* USDT receiving address — registered here rather than in .env so it
              can be rotated without a deploy. Subscribers are told to send real
              money to whatever is saved here, so the field is deliberately
              blunt about that. */}
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>₮ {T.usdtTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>
              {T.usdtHint}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <select value={usdtNet} onChange={e => setUsdtNet(e.target.value)} style={inputStyle}>
                {(paySettings?.networks || ['TRC20']).map((n: string) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
              <input placeholder={T.usdtAddrPlaceholder} value={usdtAddr}
                onChange={e => setUsdtAddr(e.target.value)}
                style={{ ...inputStyle, width: 380, fontFamily: 'ui-monospace, monospace' }} />
              <button style={primaryBtn}
                onClick={async () => {
                  if (usdtAddr.trim() && !window.confirm(T.usdtConfirm)) return
                  await act('settings/payment', {
                    method: 'PUT',
                    body: JSON.stringify({ usdt_address: usdtAddr.trim(), usdt_network: usdtNet,
                      bank_transfer_info: bankInfo }),
                  }, 'subscriptions')
                }}>{T.usdtSave}</button>
            </div>
            {/* Bank details live in this card, not their own, because the Save
                button above writes both rails in one PUT. */}
            <div style={{ borderTop: '1px solid var(--border-color,#2a2a28)',
              marginTop: 14, paddingTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.bankTitle}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 8 }}>
                {T.bankHint}
              </div>
              <textarea value={bankInfo} onChange={e => setBankInfo(e.target.value)}
                placeholder={T.bankPlaceholder} rows={3} maxLength={2000}
                style={{ ...inputStyle, width: '100%', resize: 'vertical',
                  fontFamily: 'ui-monospace, monospace' }} />
              {!paySettings?.bank_transfer_info?.value && (
                <div style={{ fontSize: 11, color: '#eab308', marginTop: 6 }}>
                  ⚠️ {T.bankUnset}
                </div>
              )}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginTop: 8 }}>
              {paySettings?.usdt_address?.value
                ? <>✓ {T.usdtLive}
                    {paySettings.usdt_address.source === 'env' && ` · ${T.usdtFromEnv}`}
                    {paySettings.usdt_address.updated_by
                      && ` · ${paySettings.usdt_address.updated_by}`}
                    {paySettings.usdt_address.updated_at
                      && ` · ${fmtDate(paySettings.usdt_address.updated_at)}`}
                  </>
                : <span style={{ color: '#eab308' }}>⚠️ {T.usdtUnset}</span>}
            </div>
          </div>

          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{T.grantTitle}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>{T.grantReplaces}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input placeholder={T.email} value={grant.email}
                onChange={e => setGrant(p => ({ ...p, email: e.target.value }))} style={{ ...inputStyle, width: 220 }} />
              <select value={grant.plan_code} onChange={e => setGrant(p => ({ ...p, plan_code: e.target.value }))} style={inputStyle}>
                {(planList.length ? planList : [{ code: 'junior' }, { code: 'pro' }, { code: 'professional' }, { code: 'enterprise' }]).map((p: any) => (
                  <option key={p.code} value={p.code}>{p.name || p.code}{p.price_usd ? ` ($${p.price_usd})` : ''}</option>
                ))}
              </select>
              <input placeholder={T.grantDays} value={grant.days} inputMode="numeric"
                onChange={e => setGrant(p => ({ ...p, days: e.target.value }))} style={{ ...inputStyle, width: 80 }} />
              <input placeholder={T.grantNote} value={grant.note}
                onChange={e => setGrant(p => ({ ...p, note: e.target.value }))} style={{ ...inputStyle, width: 200 }} />
              <button style={primaryBtn} disabled={!grant.email.trim() || !(parseInt(grant.days, 10) > 0)}
                onClick={() => {
                  act('subscriptions/grant', {
                    method: 'POST',
                    body: JSON.stringify({ email: grant.email.trim(), plan_code: grant.plan_code, days: parseInt(grant.days, 10) || 30, note: grant.note }),
                  }, 'subscriptions')
                  setGrant(p => ({ ...p, email: '', note: '' }))
                }}>{T.grantBtn}</button>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            {['', 'pending', 'active', 'rejected', 'expired'].map(s => (
              <button key={s || 'all'} style={chip(subFilter === s)} onClick={() => setSubFilter(s)}>
                {s || tr(language, { ko: '전체', en: 'All', ja: 'すべて', th: 'ทั้งหมด', vi: 'Tất cả' })}
                {subs?.by_status && s ? ` (${subs.by_status[s] || 0})` : ''}
              </button>
            ))}
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.member}</th><th style={th}>{T.plan}</th><th style={th}>{T.method}</th><th style={th}>{T.reference}</th><th style={th}>{T.amount}</th><th style={th}>{T.status}</th><th style={th}>{T.expires}</th><th style={th}></th></tr></thead>
              <tbody>
                {(subs?.subscriptions || []).map((s: any) => (
                  <tr key={s.id}>
                    <td style={td}>{s.id}</td><td style={{ ...td, fontWeight: 600 }}>{s.email || s.user_id}</td>
                    <td style={td}>{s.plan_code}</td><td style={td}>{s.method}</td>
                    {/* The proof of payment. Shown in full and copyable — a
                        truncated tx hash cannot be checked against a chain. */}
                    <td style={{ ...td, maxWidth: 300 }}>
                      {s.reference ? (
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
                          <code style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11,
                            wordBreak: 'break-all', lineHeight: 1.45 }}>{s.reference}</code>
                          <button style={{ ...actionBtn, padding: '2px 8px', fontSize: 11 }}
                            onClick={() => {
                              navigator.clipboard?.writeText(s.reference)
                              setCopiedRef(s.id)
                              setTimeout(() => setCopiedRef(c => (c === s.id ? null : c)), 1500)
                            }}>{copiedRef === s.id ? `✓ ${T.refCopied}` : T.refCopy}</button>
                          {explorerUrl(s.method, paySettings?.usdt_network?.value || '', s.reference) && (
                            <a href={explorerUrl(s.method, paySettings?.usdt_network?.value || '', s.reference)}
                              target="_blank" rel="noopener noreferrer"
                              style={{ fontSize: 11, color: 'var(--accent-primary,#c26a45)' }}>
                              {T.refVerify} ↗
                            </a>
                          )}
                        </div>
                      ) : '—'}
                    </td>
                    <td style={td}>{fmtMoney(s.amount_usd)}</td>
                    <td style={{ ...td, color: subStatusColor(s.status), fontWeight: 600 }}>{s.status}</td>
                    <td style={td}>{fmtDate(s.expires_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {s.status === 'pending' && <>
                        <button style={actionBtn} onClick={() => act(`subscriptions/${s.id}/approve`, { method: 'POST', body: JSON.stringify({ note: '' }) }, 'subscriptions')}>{T.approve}</button>{' '}
                        <button style={dangerBtn} onClick={() => {
                          const note = window.prompt(T.reason) || ''
                          act(`subscriptions/${s.id}/reject`, { method: 'POST', body: JSON.stringify({ note }) }, 'subscriptions')
                        }}>{T.reject}</button>
                      </>}
                      {(s.status === 'active' || s.status === 'expired') &&
                        <button style={actionBtn} onClick={() => act(`subscriptions/${s.id}/extend`, { method: 'POST', body: JSON.stringify({ days: 30 }) }, 'subscriptions')}>{T.extend30}</button>}{' '}
                      {s.status === 'active' &&
                        <button style={dangerBtn} onClick={() => {
                          if (!window.confirm(T.cancelConfirm)) return
                          const note = window.prompt(T.grantNote) || ''
                          act(`subscriptions/${s.id}/cancel`, { method: 'POST', body: JSON.stringify({ note }) }, 'subscriptions')
                        }}>{T.cancelSub}</button>}
                    </td>
                  </tr>
                ))}
                {!(subs?.subscriptions || []).length && <tr><td style={td} colSpan={9}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>

          <div style={sectionTitle}>{T.planMgmt}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>{T.planMgmtHint}</div>
          <div style={{ ...tableCard, marginBottom: 12 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
              <thead><tr><th style={th}>{T.planCode}</th><th style={th}>{T.planName}</th><th style={th}>{T.planPrice}</th><th style={th}>{T.planSort}</th><th style={th}>{T.subscriberRows}</th><th style={th}>{T.status}</th><th style={th}></th></tr></thead>
              <tbody>
                {adminPlans.map((p: any) => (
                  <tr key={p.code}>
                    <td style={{ ...td, fontWeight: 600 }}>{p.code}{p.contact_only ? ' 📞' : ''}</td>
                    <td style={td}>{p.name}</td>
                    <td style={td}>{p.contact_only ? '—' : fmtMoney(p.price_usd)}</td>
                    <td style={td}>{p.sort_order}</td>
                    <td style={td}>{p.subscriber_rows}</td>
                    <td style={{ ...td, color: p.active ? '#22c55e' : 'var(--text-muted,#8a8073)' }}>{p.active ? 'active' : 'off'}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      <button style={actionBtn} onClick={() => {
                        const name = window.prompt(T.editName, p.name)
                        if (name) act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ name }) }, 'subscriptions')
                      }}>{T.editName}</button>{' '}
                      {!p.contact_only && <><button style={actionBtn} onClick={() => {
                        const price = window.prompt(T.editPrice, String(p.price_usd))
                        if (price !== null && !isNaN(parseFloat(price))) act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ price_usd: parseFloat(price) }) }, 'subscriptions')
                      }}>{T.editPrice}</button>{' '}</>}
                      {p.active
                        ? <button style={actionBtn} onClick={() => act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ active: 0 }) }, 'subscriptions')}>{T.planOff}</button>
                        : <button style={actionBtn} onClick={() => act(`plans/${p.code}`, { method: 'PATCH', body: JSON.stringify({ active: 1 }) }, 'subscriptions')}>{T.planOn}</button>}{' '}
                      {!p.subscriber_rows && <button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`plans/${p.code}`, { method: 'DELETE' }, 'subscriptions')}>{T.del}</button>}
                    </td>
                  </tr>
                ))}
                {!adminPlans.length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
            <input placeholder={T.planCode} value={newPlan.code}
              onChange={e => setNewPlan(p => ({ ...p, code: e.target.value }))} style={{ ...inputStyle, width: 140 }} />
            <input placeholder={T.planName} value={newPlan.name}
              onChange={e => setNewPlan(p => ({ ...p, name: e.target.value }))} style={{ ...inputStyle, width: 160 }} />
            <input placeholder={T.planPrice} value={newPlan.price} inputMode="decimal"
              onChange={e => setNewPlan(p => ({ ...p, price: e.target.value }))} style={{ ...inputStyle, width: 90 }} />
            <input placeholder={T.planSort} value={newPlan.sort} inputMode="numeric"
              onChange={e => setNewPlan(p => ({ ...p, sort: e.target.value }))} style={{ ...inputStyle, width: 70 }} />
            <button style={primaryBtn}
              disabled={!newPlan.code.trim() || !newPlan.name.trim() || isNaN(parseFloat(newPlan.price))}
              onClick={() => {
                act('plans', {
                  method: 'POST',
                  body: JSON.stringify({ code: newPlan.code.trim(), name: newPlan.name.trim(), price_usd: parseFloat(newPlan.price) || 0, sort_order: parseInt(newPlan.sort, 10) || 0 }),
                }, 'subscriptions')
                setNewPlan({ code: '', name: '', price: '', sort: '10' })
              }}>{T.planAdd}</button>
          </div>

          <div style={sectionTitle}>{T.contracts}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.email}</th><th style={th}>Company</th><th style={th}>Phone</th><th style={th}>Message</th><th style={th}>{T.status}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(contracts?.contracts || []).map((c: any) => (
                  <tr key={c.id}>
                    <td style={td}>{c.id}</td><td style={{ ...td, fontWeight: 600 }}>{c.email}</td>
                    <td style={td}>{c.company || '—'}</td><td style={td}>{c.phone || '—'}</td>
                    <td style={{ ...td, maxWidth: 260 }}>{c.message}</td>
                    <td style={{ ...td, color: c.status === 'new' ? '#eab308' : c.status === 'contacted' ? '#22c55e' : 'var(--text-muted,#8a8073)' }}>{c.status}</td>
                    <td style={td}>{fmtDate(c.created_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {c.status !== 'contacted' && <button style={actionBtn} onClick={() => act(`contracts/${c.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'contacted' }) }, 'subscriptions')}>{T.contacted}</button>}{' '}
                      {c.status !== 'closed' && <button style={actionBtn} onClick={() => act(`contracts/${c.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'closed' }) }, 'subscriptions')}>{T.closed}</button>}
                    </td>
                  </tr>
                ))}
                {!(contracts?.contracts || []).length && <tr><td style={td} colSpan={8}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Assets ── */}
      {tab === 'assets' && assets && (
        <>
          <StatCards items={[
            [tr(language, { ko: '현금 합계', en: 'Total cash', ja: '現金合計', th: 'เงินสดรวม', vi: 'Tổng tiền mặt' }), fmtMoney(assets.totals.cash)],
            [tr(language, { ko: '입금 합계', en: 'Total deposited', ja: '入金合計', th: 'ยอดฝากรวม', vi: 'Tổng đã nạp' }), fmtMoney(assets.totals.deposited)],
            [tr(language, { ko: '포지션 가치', en: 'Position value', ja: 'ポジション評価額', th: 'มูลค่าสถานะ', vi: 'Giá trị vị thế' }), fmtMoney(assets.totals.position_value)],
            [tr(language, { ko: '에이전트 수', en: 'Agents', ja: 'エージェント数', th: 'จำนวนเอเจนต์', vi: 'Số agent' }), assets.totals.agents],
          ]} />
          <div style={sectionTitle}>{T.equityCurve}</div>
          <TrendChart data={assets.equity_curve} xKey="day" series={[['total_value', '#c26a45'], ['profit', '#22c55e']]} />
          <div style={sectionTitle}>{T.topMembers}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>{T.agent}</th><th style={th}>{T.email}</th><th style={th}>Equity</th><th style={th}>Cash</th><th style={th}>Positions</th><th style={th}>Profit</th></tr></thead>
              <tbody>
                {(assets.top_members || []).map((m: any) => (
                  <tr key={m.agent_id}>
                    <td style={{ ...td, fontWeight: 600 }}>{m.name}</td><td style={td}>{m.email || '—'}</td>
                    <td style={td}>{fmtMoney(m.total_value)}</td><td style={td}>{fmtMoney(m.cash)}</td>
                    <td style={td}>{fmtMoney(m.position_value)}</td>
                    <td style={{ ...td, color: (m.profit || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{fmtMoney(m.profit)}</td>
                  </tr>
                ))}
                {!(assets.top_members || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Positions ── */}
      {tab === 'positions' && positions && (
        <>
          <StatCards items={[
            [tr(language, { ko: '미결제 포지션', en: 'Open positions', ja: '未決済ポジション', th: 'สถานะที่เปิดอยู่', vi: 'Vị thế đang mở' }), positions.totals.open_positions],
            [tr(language, { ko: '총 가치', en: 'Total value', ja: '総額', th: 'มูลค่ารวม', vi: 'Tổng giá trị' }), fmtMoney(positions.totals.total_value)],
            [tr(language, { ko: '미실현 손익', en: 'Unrealized PnL', ja: '未実現損益', th: 'กำไรขาดทุนที่ยังไม่รับรู้', vi: 'Lãi/lỗ chưa thực hiện' }), fmtMoney(positions.totals.unrealized_pnl)],
          ]} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 12 }}>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Market</th><th style={th}>#</th><th style={th}>Value</th></tr></thead>
                <tbody>{(positions.by_market || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.market}</td><td style={td}>{r.c}</td><td style={td}>{fmtMoney(r.value)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Side</th><th style={th}>#</th></tr></thead>
                <tbody>{(positions.by_side || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.side}</td><td style={td}>{r.c}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr><th style={th}>Symbol</th><th style={th}>#</th><th style={th}>Value</th></tr></thead>
                <tbody>{(positions.top_symbols || []).map((r: any, i: number) => (
                  <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.symbol}</td><td style={td}>{r.c}</td><td style={td}>{fmtMoney(r.value)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
          <div style={sectionTitle}>{tr(language, { ko: '대형 포지션', en: 'Largest positions', ja: '大口ポジション', th: 'สถานะขนาดใหญ่สุด', vi: 'Vị thế lớn nhất' })}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
              <thead><tr><th style={th}>Symbol</th><th style={th}>{T.agent}</th><th style={th}>{T.email}</th><th style={th}>Side</th><th style={th}>Qty</th><th style={th}>Entry</th><th style={th}>Now</th><th style={th}>PnL</th></tr></thead>
              <tbody>
                {(positions.largest || []).map((p: any) => (
                  <tr key={p.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{p.symbol} <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{p.market}</span></td>
                    <td style={td}>{p.agent_name || '—'}</td><td style={td}>{p.email || '—'}</td>
                    <td style={{ ...td, color: ['buy', 'long', 'yes'].includes(p.side) ? '#22c55e' : '#ef4444' }}>{p.side}</td>
                    <td style={td}>{p.quantity}</td><td style={td}>{p.entry_price}</td><td style={td}>{p.current_price ?? '—'}</td>
                    <td style={{ ...td, color: (p.unrealized_pnl || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{fmtMoney(p.unrealized_pnl)}</td>
                  </tr>
                ))}
                {!(positions.largest || []).length && <tr><td style={td} colSpan={8}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Automation ── */}
      {tab === 'automation' && autoStats && (
        <>
          <StatCards items={[
            [tr(language, { ko: '규칙 (활성)', en: 'Rules (on)', ja: 'ルール（有効）', th: 'กฎ (เปิด)', vi: 'Quy tắc (bật)' }), `${autoStats.totals.rules} (${autoStats.totals.enabled})`],
            [tr(language, { ko: '자동 실행 규칙', en: 'Auto-execute rules', ja: '自動実行ルール', th: 'กฎรันอัตโนมัติ', vi: 'Quy tắc tự thực thi' }), autoStats.totals.auto_execute],
            [tr(language, { ko: '실행 (30일)', en: 'Runs (30d)', ja: '実行（30日）', th: 'การรัน (30 วัน)', vi: 'Lượt chạy (30 ngày)' }), autoStats.totals.runs_30d],
            [tr(language, { ko: '실행률 (30일)', en: 'Execute rate (30d)', ja: '実行率（30日）', th: 'อัตราการรัน (30 วัน)', vi: 'Tỷ lệ thực thi (30 ngày)' }), `${Math.round((autoStats.totals.execute_rate_30d || 0) * 100)}%`],
          ]} />
          <div style={sectionTitle}>{T.runsPerDay}</div>
          <TrendChart data={autoStats.runs_by_day} xKey="day" series={[['runs', '#c26a45'], ['executed', '#22c55e']]} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 12, marginTop: 16 }}>
            <div>
              <div style={sectionTitle}>{T.byAgent}</div>
              <div style={tableCard}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr><th style={th}>{T.agent}</th><th style={th}>Runs</th><th style={th}>Executed</th></tr></thead>
                  <tbody>{(autoStats.by_agent || []).map((r: any, i: number) => (
                    <tr key={i}><td style={{ ...td, fontWeight: 600 }}>{r.agent_name || r.agent_id}</td><td style={td}>{r.runs}</td><td style={td}>{r.executed}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
            <div>
              <div style={sectionTitle}>{T.skipReasons}</div>
              <div style={tableCard}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr><th style={th}>{T.reason}</th><th style={th}>#</th></tr></thead>
                  <tbody>{(autoStats.skip_reasons || []).map((r: any, i: number) => (
                    <tr key={i}><td style={td}>{r.reason}</td><td style={td}>{r.c}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          </div>
          <div style={sectionTitle}>{T.rules}</div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>Rule</th><th style={th}>{T.agent}</th><th style={th}>Interval</th><th style={th}>Conf.</th><th style={th}>$</th><th style={th}>{T.status}</th><th style={th}>Last run</th></tr></thead>
              <tbody>
                {(autoRules?.rules || []).map((r: any) => (
                  <tr key={r.id}>
                    <td style={{ ...td, fontWeight: 600 }}>{r.symbol} <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{r.market} · {r.provider || 'default'}</span></td>
                    <td style={td}>{r.agent_name || r.agent_id}</td>
                    <td style={td}>{r.interval_minutes}m</td>
                    <td style={td}>≥{Math.round((r.min_confidence || 0) * 100)}%</td>
                    <td style={td}>${r.size_usd}</td>
                    <td style={td}>{r.enabled ? (r.auto_execute ? '🟢 auto' : '🟡 analysis') : '⚪ off'} · {r.account_type}</td>
                    <td style={td}>{fmtTime(r.last_run_at)}</td>
                  </tr>
                ))}
                {!(autoRules?.rules || []).length && <tr><td style={td} colSpan={7}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Support conversations + announcements ── */}
      {tab === 'support' && (
        <>
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={sectionTitle}>
              {tr(language, { ko: '공지 발송 — 전체 회원 알림', en: 'Broadcast — announcement to every member', ja: '一斉配信 — 全会員へのお知らせ', th: 'ประกาศ — แจ้งสมาชิกทุกคน', vi: 'Phát thông báo — gửi tới mọi thành viên' })}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', marginBottom: 10 }}>
              {tr(language, {
                ko: '회원의 알림함에 공지가 표시됩니다. 공지 알림을 끈 회원은 자동으로 제외됩니다.',
                en: "Lands in each member's notification centre. Members who switched announcements off are skipped automatically.",
                ja: '会員の通知センターに表示されます。お知らせ通知をオフにした会員は自動的に除外されます。',
                th: 'จะแสดงในศูนย์แจ้งเตือนของสมาชิกแต่ละคน สมาชิกที่ปิดการแจ้งเตือนประกาศจะถูกข้ามอัตโนมัติ',
                vi: 'Hiển thị trong trung tâm thông báo của từng thành viên. Thành viên đã tắt thông báo sẽ tự động bị bỏ qua.',
              })}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <input placeholder={tr(language, { ko: '제목', en: 'Title', ja: 'タイトル', th: 'หัวข้อ', vi: 'Tiêu đề' })} value={broadcast.title}
                onChange={e => setBroadcast(b => ({ ...b, title: e.target.value }))}
                style={{ ...inputStyle, width: 240 }} />
              <input placeholder={tr(language, { ko: '내용 (선택)', en: 'Body (optional)', ja: '本文（任意）', th: 'เนื้อหา (ไม่บังคับ)', vi: 'Nội dung (tùy chọn)' })} value={broadcast.body}
                onChange={e => setBroadcast(b => ({ ...b, body: e.target.value }))}
                style={{ ...inputStyle, flex: 1, minWidth: 240 }} />
              <button style={primaryBtn} disabled={!broadcast.title.trim()}
                onClick={async () => {
                  if (!confirm(tr(language, {
                    ko: '모든 회원에게 이 공지를 보낼까요?',
                    en: 'Send this announcement to every member?',
                    ja: 'このお知らせを全会員に送信しますか？',
                    th: 'ส่งประกาศนี้ให้สมาชิกทุกคนหรือไม่',
                    vi: 'Gửi thông báo này tới mọi thành viên?',
                  }))) return
                  const ok = await act('notifications/broadcast',
                    { method: 'POST', body: JSON.stringify(broadcast) }, 'support')
                  if (ok) setBroadcast({ title: '', body: '' })
                }}>
                {tr(language, { ko: '발송', en: 'Send', ja: '送信', th: 'ส่ง', vi: 'Gửi' })}
              </button>
            </div>
          </div>

          <div style={sectionTitle}>
            {tr(language, { ko: '회원 문의', en: 'Member conversations', ja: '会員問い合わせ', th: 'บทสนทนากับสมาชิก', vi: 'Hội thoại thành viên' })}
            {threads?.unread_total > 0 && (
              <span style={{ marginLeft: 8, color: '#c26a45' }}>
                · {threads.unread_total} {tr(language, { ko: '건 대기', en: 'waiting', ja: '件 待機中', th: 'รออยู่', vi: 'đang chờ' })}
              </span>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px,1fr) minmax(320px,1.4fr)', gap: 12, alignItems: 'start' }}>
            <div style={tableCard}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead><tr>
                  <th style={th}>{T.member}</th>
                  <th style={th}>{T.status}</th>
                  <th style={th}>{tr(language, { ko: '최근', en: 'Last', ja: '最終', th: 'ล่าสุด', vi: 'Gần nhất' })}</th>
                </tr></thead>
                <tbody>
                  {(threads?.threads || []).map((t: any) => (
                    <tr key={t.id} onClick={async () => {
                      setReply('')
                      setActiveThread(await call(`support/threads/${t.id}`))
                      await refresh('support')
                    }} style={{ cursor: 'pointer', background: activeThread?.thread?.id === t.id ? 'rgba(194,106,69,0.10)' : undefined }}>
                      <td style={td}>
                        {t.user_email}
                        {t.admin_unread > 0 && (
                          <span style={{ marginLeft: 6, background: '#c26a45', color: '#fff', borderRadius: 999, padding: '1px 7px', fontSize: 10, fontWeight: 700 }}>
                            {t.admin_unread}
                          </span>
                        )}
                        <div style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{t.subject || '—'}</div>
                      </td>
                      <td style={{ ...td, color: t.status === 'open' ? '#22c55e' : 'var(--text-muted,#8a8073)' }}>{t.status}</td>
                      <td style={{ ...td, fontSize: 11 }}>{fmtTime(t.last_message_at)}</td>
                    </tr>
                  ))}
                  {!(threads?.threads || []).length && (
                    <tr><td style={td} colSpan={3}>{T.noData}</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={card}>
              {!activeThread && (
                <div style={{ color: 'var(--text-muted,#8a8073)', fontSize: 13 }}>
                  {tr(language, { ko: '왼쪽에서 대화를 선택하세요.', en: 'Pick a conversation on the left.', ja: '左側から会話を選択してください。', th: 'เลือกบทสนทนาทางซ้าย', vi: 'Chọn một hội thoại ở bên trái.' })}
                </div>
              )}
              {activeThread && (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 14 }}>{activeThread.thread.user_email}</strong>
                    <button style={actionBtn} onClick={async () => {
                      const next = activeThread.thread.status === 'open' ? 'closed' : 'open'
                      await act(`support/threads/${activeThread.thread.id}/status`,
                        { method: 'POST', body: JSON.stringify({ status: next }) }, 'support')
                      setActiveThread(await call(`support/threads/${activeThread.thread.id}`))
                    }}>
                      {activeThread.thread.status === 'open'
                        ? tr(language, { ko: '문의 종료', en: 'Close thread', ja: '問い合わせ終了', th: 'ปิดเธรด', vi: 'Đóng chủ đề' })
                        : tr(language, { ko: '다시 열기', en: 'Reopen', ja: '再開', th: 'เปิดใหม่', vi: 'Mở lại' })}
                    </button>
                  </div>
                  <div style={{ maxHeight: 340, overflowY: 'auto', marginBottom: 10 }}>
                    {activeThread.messages.map((m: any) => (
                      <div key={m.id} style={{ display: 'flex', justifyContent: m.sender === 'admin' ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
                        <div style={{ maxWidth: '80%' }}>
                          <div style={{
                            padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
                            background: m.sender === 'admin' ? 'var(--accent-primary,#c26a45)' : 'var(--bg-primary,#0f0f0e)',
                            color: m.sender === 'admin' ? '#fff' : 'inherit',
                            border: m.sender === 'admin' ? 'none' : '1px solid var(--border-color,#2a2a28)',
                          }}>{m.body}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted,#8a8073)', marginTop: 2, textAlign: m.sender === 'admin' ? 'right' : 'left' }}>
                            {m.sender === 'admin' ? (m.admin_email || 'admin') : activeThread.thread.user_email} · {fmtTime(m.created_at)}
                          </div>
                        </div>
                      </div>
                    ))}
                    {!activeThread.messages.length && (
                      <div style={{ color: 'var(--text-muted,#8a8073)', fontSize: 13 }}>{T.noData}</div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                    <textarea value={reply} onChange={e => setReply(e.target.value.slice(0, 4000))} rows={3}
                      placeholder={tr(language, { ko: '답변을 입력하세요…', en: 'Write a reply…', ja: '返信を入力…', th: 'เขียนคำตอบ…', vi: 'Viết trả lời…' })}
                      style={{ ...inputStyle, flex: 1, resize: 'vertical', fontFamily: 'inherit' }} />
                    <button style={primaryBtn} disabled={!reply.trim()} onClick={async () => {
                      const id = activeThread.thread.id
                      const ok = await act(`support/threads/${id}/reply`,
                        { method: 'POST', body: JSON.stringify({ body: reply }) }, 'support')
                      if (!ok) return  // keep the typed reply so the admin can retry
                      setReply('')
                      try { setActiveThread(await call(`support/threads/${id}`)) }
                      catch { /* refresh() already re-rendered the list; thread reload is best-effort */ }
                    }}>
                      {tr(language, { ko: '답변 전송', en: 'Send reply', ja: '返信送信', th: 'ส่งคำตอบ', vi: 'Gửi trả lời' })}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Discussions ── */}
      {tab === 'discussions' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder={T.search} value={dq} onChange={e => setDq(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && refresh('discussions')} style={{ ...inputStyle, width: 280 }} />
            <button style={actionBtn} onClick={() => refresh('discussions')}>{T.search}</button>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>Title</th><th style={th}>{T.agent}</th><th style={th}>{T.replies}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(discussions?.discussions || []).map((d: any) => (
                  <Fragment key={d.signal_id}>
                    <tr>
                      <td style={td}>{d.signal_id}</td>
                      <td style={{ ...td, maxWidth: 340 }}>
                        <div style={{ fontWeight: 600 }}>{d.title || '(untitled)'}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted,#8a8073)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.content}</div>
                      </td>
                      <td style={td}>{d.agent_name || d.agent_id}</td>
                      <td style={td}>
                        <button style={actionBtn} onClick={async () => {
                          if (replies[d.signal_id]) { setReplies(p => { const n = { ...p }; delete n[d.signal_id]; return n }); return }
                          try {
                            const body = await call(`discussions/${d.signal_id}/replies`)
                            setReplies(p => ({ ...p, [d.signal_id]: body.replies }))
                          } catch { /* handled */ }
                        }}>{d.reply_count} ▾</button>
                      </td>
                      <td style={td}>{fmtTime(d.created_at)}</td>
                      <td style={td}><button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`discussions/${d.signal_id}`, { method: 'DELETE' }, 'discussions')}>{T.del}</button></td>
                    </tr>
                    {replies[d.signal_id] && (
                      <tr>
                        <td style={td} colSpan={6}>
                          {(replies[d.signal_id] || []).map((r: any) => (
                            <div key={r.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 0 4px 24px', fontSize: 13 }}>
                              <strong>{r.agent_name || r.agent_id}</strong>
                              <span style={{ flex: 1 }}>{r.content}</span>
                              <span style={{ fontSize: 11, color: 'var(--text-muted,#8a8073)' }}>{fmtTime(r.created_at)}</span>
                              <button style={dangerBtn} onClick={() => act(`replies/${r.id}`, { method: 'DELETE' }, 'discussions').then(() => setReplies(p => { const n = { ...p }; delete n[d.signal_id]; return n }))}>{T.del}</button>
                            </div>
                          ))}
                          {!(replies[d.signal_id] || []).length && <div style={{ paddingLeft: 24, fontSize: 13, color: 'var(--text-muted,#8a8073)' }}>{T.noData}</div>}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!(discussions?.discussions || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Leaderboard ── */}
      {tab === 'leaderboard' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            {['return', 'risk', 'collaboration', 'quality'].map(m => (
              <button key={m} style={chip(lbMetric === m)} onClick={() => setLbMetric(m)}>{m}</button>
            ))}
            <button style={{ ...actionBtn, marginLeft: 'auto' }} onClick={() => act('leaderboard/refresh', { method: 'POST' }, 'leaderboard')}>{T.refreshNow}</button>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead><tr><th style={th}>#</th><th style={th}>{T.agent}</th><th style={th}>Profit</th><th style={th}>Profit %</th><th style={th}>Trades</th><th style={th}></th></tr></thead>
              <tbody>
                {(leaderboard?.snapshot || []).map((r: any, i: number) => (
                  <tr key={r.agent_id ?? i}>
                    <td style={td}>{i + 1}</td>
                    <td style={{ ...td, fontWeight: 600 }}>{r.name || r.agent_id}</td>
                    <td style={{ ...td, color: (r.profit || 0) >= 0 ? '#22c55e' : '#ef4444' }}>{fmtMoney(r.profit)}</td>
                    <td style={td}>{Number(r.profit_percent || 0).toFixed(2)}%</td>
                    <td style={td}>{r.trade_count ?? '—'}</td>
                    <td style={td}><button style={dangerBtn} onClick={() => {
                      const reason = window.prompt(T.reason) || ''
                      act('leaderboard/exclusions', { method: 'POST', body: JSON.stringify({ agent_id: r.agent_id, reason }) }, 'leaderboard')
                    }}>{T.exclude}</button></td>
                  </tr>
                ))}
                {!(leaderboard?.snapshot || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={sectionTitle}>{T.exclusions}</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input placeholder="agent_id" value={exclusion.agent_id}
              onChange={e => setExclusion(p => ({ ...p, agent_id: e.target.value }))} style={{ ...inputStyle, width: 110 }} />
            <input placeholder={T.reason} value={exclusion.reason}
              onChange={e => setExclusion(p => ({ ...p, reason: e.target.value }))} style={{ ...inputStyle, width: 240 }} />
            <button style={actionBtn} onClick={() => {
              const id = parseInt(exclusion.agent_id, 10)
              if (!id) return
              act('leaderboard/exclusions', { method: 'POST', body: JSON.stringify({ agent_id: id, reason: exclusion.reason }) }, 'leaderboard')
              setExclusion({ agent_id: '', reason: '' })
            }}>{T.exclude}</button>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
              <thead><tr><th style={th}>{T.agent}</th><th style={th}>{T.reason}</th><th style={th}>{T.status}</th><th style={th}>{T.created}</th><th style={th}></th></tr></thead>
              <tbody>
                {(leaderboard?.exclusions || []).map((e: any, i: number) => (
                  <tr key={i}>
                    <td style={{ ...td, fontWeight: 600 }}>{e.agent_name || e.agent_id}</td>
                    <td style={td}>{e.reason || '—'}</td>
                    <td style={{ ...td, color: e.active ? '#ef4444' : 'var(--text-muted,#8a8073)' }}>{e.active ? tr(language, { ko: '제외됨', en: 'excluded', ja: '除外済み', th: 'ถูกยกเว้น', vi: 'đã loại trừ' }) : tr(language, { ko: '해제됨', en: 'included', ja: '解除済み', th: 'ยกเลิกยกเว้นแล้ว', vi: 'đã đưa lại' })}</td>
                    <td style={td}>{fmtDate(e.created_at)}</td>
                    <td style={td}>{!!e.active && <button style={actionBtn} onClick={() => act(`leaderboard/exclusions/${e.agent_id}`, { method: 'DELETE' }, 'leaderboard')}>{T.include}</button>}</td>
                  </tr>
                ))}
                {!(leaderboard?.exclusions || []).length && <tr><td style={td} colSpan={5}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Admins (superadmin only) ── */}
      {tab === 'admins' && me?.role === 'superadmin' && (
        <>
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>{T.addAdmin}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input placeholder={T.email} value={newAdmin.email}
                onChange={e => setNewAdmin(p => ({ ...p, email: e.target.value }))} style={{ ...inputStyle, width: 220 }} />
              <input placeholder={T.password} type="password" value={newAdmin.password}
                onChange={e => setNewAdmin(p => ({ ...p, password: e.target.value }))} style={{ ...inputStyle, width: 180 }} />
              <select value={newAdmin.role} onChange={e => setNewAdmin(p => ({ ...p, role: e.target.value }))} style={inputStyle}>
                <option value="operator">operator</option>
                <option value="superadmin">superadmin</option>
              </select>
              <button style={primaryBtn} onClick={() => {
                act('admins', { method: 'POST', body: JSON.stringify(newAdmin) }, 'admins')
                setNewAdmin({ email: '', password: '', role: 'operator' })
              }}>{T.addAdmin}</button>
            </div>
          </div>
          <div style={tableCard}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr><th style={th}>ID</th><th style={th}>{T.email}</th><th style={th}>{T.role}</th><th style={th}>{T.status}</th><th style={th}>{T.lastLogin}</th><th style={th}></th></tr></thead>
              <tbody>
                {(admins?.admins || []).map((a: any) => (
                  <tr key={a.id}>
                    <td style={td}>{a.id}</td><td style={{ ...td, fontWeight: 600 }}>{a.email}</td>
                    <td style={td}>{a.role}</td>
                    <td style={{ ...td, color: a.status === 'active' ? '#22c55e' : '#ef4444' }}>{a.status}</td>
                    <td style={td}>{fmtTime(a.last_login_at)}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {/* Password reset is allowed on your own row (backend only
                          blocks self-disable/demote/delete). Resetting your own
                          password revokes the session — you log back in. */}
                      <button style={actionBtn} onClick={() => {
                        const pw = window.prompt(T.resetPw)
                        if (pw) act(`admins/${a.id}`, { method: 'PATCH', body: JSON.stringify({ password: pw }) }, 'admins')
                      }}>{T.resetPw}</button>{' '}
                      {a.id !== me.id && <>
                        {a.status === 'active'
                          ? <button style={dangerBtn} onClick={() => act(`admins/${a.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'disabled' }) }, 'admins')}>{T.disable}</button>
                          : <button style={actionBtn} onClick={() => act(`admins/${a.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'active' }) }, 'admins')}>{T.enable}</button>}{' '}
                        <button style={dangerBtn} onClick={() => window.confirm(T.delConfirm) && act(`admins/${a.id}`, { method: 'DELETE' }, 'admins')}>{T.del}</button>
                      </>}
                    </td>
                  </tr>
                ))}
                {!(admins?.admins || []).length && <tr><td style={td} colSpan={6}>{T.noData}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Audit ── */}
      {tab === 'audit' && (
        <div style={tableCard}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
            <thead><tr><th style={th}>{T.time}</th><th style={th}>{T.email}</th><th style={th}>{T.action}</th><th style={th}>{T.target}</th><th style={th}>{tr(language, { ko: '내용', en: 'Detail', ja: '内容', th: 'รายละเอียด', vi: 'Chi tiết' })}</th></tr></thead>
            <tbody>
              {(audit?.entries || []).map((e: any) => (
                <tr key={e.id}>
                  <td style={td}>{fmtTime(e.created_at)}</td>
                  <td style={{ ...td, fontWeight: 600 }}>{e.admin_email || '—'}</td>
                  <td style={td}>{e.action}</td>
                  <td style={td}>{e.target || '—'}</td>
                  <td style={{ ...td, maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.detail || '—'}</td>
                </tr>
              ))}
              {!(audit?.entries || []).length && <tr><td style={td} colSpan={5}>{T.noData}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default AdminPage
