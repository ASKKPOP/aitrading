import { useCallback, useEffect, useState } from 'react'
import { API_BASE, formatLocalDateTime, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Accounts — connect the trading gateway that automation rules route through.
//
// The API key and secret are POSTed to /api/execution/accounts, which encrypts
// them at rest (AES-GCM, EXECUTION_ENCRYPTION_KEY). They are never written to
// localStorage and never read back to the client — the list endpoint returns
// only broker, mode and timestamps.
//
// Where a fill lands is decided per rule on the Automation page
// (simulator | shadow | live); this page decides WHICH gateway live routes to
// and records the live-trading consent that automation requires.

type BrokerAccount = {
  id: number
  broker: string
  execution_mode: string
  is_active: number | boolean
  created_at?: string
  updated_at?: string
}

export function AccountsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const { language } = useLanguage()
  const [me, setMe] = useState<any>(null)
  const [brokers, setBrokers] = useState<string[]>([])
  // Per-broker connect-form spec + regional recommendations (Plan 19).
  const [specs, setSpecs] = useState<Record<string, { fields: string[] }>>({})
  const [regions, setRegions] = useState<Record<string, string[]>>({})
  const [region, setRegion] = useState('GLOBAL')
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [broker, setBroker] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  // OKX and KuCoin key pairs carry a third secret set at key creation.
  const [passphrase, setPassphrase] = useState('')
  // IBKR authenticates through its Client Portal Gateway, not a key/secret.
  const [gatewayUrl, setGatewayUrl] = useState('')
  const [accountId, setAccountId] = useState('')
  const [allowSelfSigned, setAllowSelfSigned] = useState(false)
  const [acceptedTcs, setAcceptedTcs] = useState(false)
  const [health, setHealth] = useState<any>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [drift, setDrift] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  // Per-broker connection guide (guide_content gwsetup-* docs), shown inline.
  const [guideHtml, setGuideHtml] = useState<string | null>(null)
  const [guideOpen, setGuideOpen] = useState(false)
  const [guideBusy, setGuideBusy] = useState(false)

  const authHeaders: any = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

  const T = {
    title: tr(language, { ko: '계정', en: 'Accounts', ja: 'アカウント', th: 'บัญชี', vi: 'Tài khoản', id: 'Akun' }),
    subtitle: tr(language, { ko: '거래 실행 방식을 선택하세요', en: 'Choose how trades are executed', ja: '取引の実行方法を選択', th: 'เลือกวิธีดำเนินการเทรด', vi: 'Chọn cách thực hiện giao dịch', id: 'Pilih bagaimana transaksi dieksekusi' }),
    simTitle: tr(language, { ko: '시뮬레이터 계정', en: 'Simulator account', ja: 'シミュレーター口座', th: 'บัญชีจำลอง', vi: 'Tài khoản mô phỏng', id: 'Akun simulator' }),
    simDesc: tr(language, { ko: '모의 지갑입니다. 매수와 매도는 실시간 시장 가격에 대해 모의 거래됩니다 — 실제 자금은 사용되지 않습니다.', en: 'Simulated wallet. Buys and sells are paper-traded against live market prices — no real money.', ja: '模擬ウォレット。実際の資金は動きません。', th: 'กระเป๋าจำลอง ซื้อขายแบบกระดาษกับราคาตลาดจริง — ไม่มีเงินจริง', vi: 'Ví mô phỏng. Không có tiền thật.', id: 'Dompet simulasi. Pembelian dan penjualan dijalankan sebagai paper trading terhadap harga pasar langsung — tanpa uang sungguhan.' }),
    balance: tr(language, { ko: '모의 잔고', en: 'Simulated balance', ja: '模擬残高', th: 'ยอดจำลอง', vi: 'Số dư mô phỏng', id: 'Saldo simulasi' }),
    realTitle: tr(language, { ko: '거래 게이트웨이', en: 'Trading gateway', ja: '取引ゲートウェイ', th: 'เกตเวย์การเทรด', vi: 'Cổng giao dịch', id: 'Gateway trading' }),
    realDesc: tr(language, { ko: '실제 자금으로 거래하려면 브로커를 연결하세요. 자동매매 규칙을 live로 설정하면 이 게이트웨이로 주문이 전송됩니다.', en: 'Connect a broker to trade with real funds. Automation rules set to live route their orders through this gateway.', ja: 'ブローカーを接続すると、live のルールがこのゲートウェイに発注します。', th: 'เชื่อมต่อโบรกเกอร์เพื่อเทรดด้วยเงินจริง กฎที่ตั้งเป็น live จะส่งคำสั่งผ่านเกตเวย์นี้', vi: 'Kết nối broker để giao dịch tiền thật. Quy tắc đặt live sẽ gửi lệnh qua cổng này.', id: 'Hubungkan broker untuk bertransaksi dengan dana sungguhan. Aturan otomatisasi yang disetel ke live mengirim ordernya melalui gateway ini.' }),
    exchange: tr(language, { ko: '브로커', en: 'Broker', ja: 'ブローカー', th: 'โบรกเกอร์', vi: 'Broker', id: 'Broker' }),
    apiKey: tr(language, { ko: 'API 키', en: 'API key', ja: 'APIキー', th: 'คีย์ API', vi: 'Khóa API', id: 'Kunci API' }),
    apiSecret: tr(language, { ko: 'API 시크릿', en: 'API secret', ja: 'APIシークレット', th: 'ความลับ API', vi: 'Bí mật API', id: 'Secret API' }),
    pemSecret: tr(language, { ko: '개인 키 (PEM 전체를 줄바꿈 그대로 붙여넣기) — 키는 반드시 ECDSA로 생성하세요. Ed25519는 지원되지 않습니다', en: 'Private key (paste the whole PEM, line breaks and all) — the key must be created with ECDSA; Ed25519 is not supported', ja: '秘密鍵 (PEM 全体を改行ごと貼り付け) — キーは ECDSA で作成してください。Ed25519 は非対応です', th: 'คีย์ส่วนตัว (วาง PEM ทั้งหมดพร้อมการขึ้นบรรทัดใหม่) — ต้องสร้างคีย์ด้วย ECDSA ไม่รองรับ Ed25519', vi: 'Khóa riêng tư (dán toàn bộ PEM, giữ nguyên xuống dòng) — khóa phải được tạo bằng ECDSA; Ed25519 không được hỗ trợ', id: 'Kunci privat (tempel seluruh PEM beserta baris barunya) — kunci harus dibuat dengan ECDSA; Ed25519 tidak didukung' }),
    passphrase: tr(language, { ko: 'API 패스프레이즈 (키 생성 시 설정)', en: 'API passphrase (set when the key was created)', ja: 'APIパスフレーズ (キー作成時に設定)', th: 'พาสเฟรส API (ตั้งตอนสร้างคีย์)', vi: 'Passphrase API (đặt khi tạo khóa)', id: 'Passphrase API (dibuat saat kunci dibuat)' }),
    needPassphrase: tr(language, { ko: '이 브로커는 API 키·시크릿과 함께 패스프레이즈도 필요합니다.', en: 'This broker also needs the API passphrase alongside the key and secret.', ja: 'このブローカーはキーとシークレットに加えパスフレーズが必要です。', th: 'โบรกเกอร์นี้ต้องใช้พาสเฟรสร่วมกับคีย์และความลับ', vi: 'Broker này cần cả passphrase cùng khóa và bí mật.', id: 'Broker ini juga memerlukan passphrase selain kunci dan secret.' }),
    regionLabel: tr(language, { ko: '지역', en: 'Region', ja: '地域', th: 'ภูมิภาค', vi: 'Khu vực', id: 'Wilayah' }),
    regionGlobal: tr(language, { ko: '글로벌', en: 'Global', ja: 'グローバル', th: 'ทั่วโลก', vi: 'Toàn cầu', id: 'Global' }),
    recommended: tr(language, { ko: '이 지역 추천', en: 'Recommended for this region', ja: 'この地域のおすすめ', th: 'แนะนำสำหรับภูมิภาคนี้', vi: 'Được đề xuất cho khu vực này', id: 'Direkomendasikan untuk wilayah ini' }),
    guideBtn: tr(language, { ko: '연결 가이드 보기', en: 'Connection guide', ja: '接続ガイドを見る', th: 'ดูคู่มือการเชื่อมต่อ', vi: 'Xem hướng dẫn kết nối', id: 'Lihat panduan koneksi' }),
    guideErr: tr(language, { ko: '가이드를 불러오지 못했습니다.', en: 'Could not load the guide.', ja: 'ガイドを読み込めませんでした。', th: 'โหลดคู่มือไม่สำเร็จ', vi: 'Không tải được hướng dẫn.', id: 'Tidak dapat memuat panduan.' }),
    guideClose: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    otherBrokers: tr(language, { ko: '기타 브로커', en: 'Other brokers', ja: 'その他のブローカー', th: 'โบรกเกอร์อื่น', vi: 'Broker khác', id: 'Broker lainnya' }),
    connect: tr(language, { ko: '게이트웨이 연결', en: 'Connect gateway', ja: 'ゲートウェイを接続', th: 'เชื่อมต่อเกตเวย์', vi: 'Kết nối cổng', id: 'Hubungkan gateway' }),
    warn: tr(language, { ko: '실거래는 실제 자금을 위험에 노출시킵니다. 반드시 거래(TRADE) 권한으로 한정된 API 키만 사용하세요 — 출금 권한은 절대 안 됩니다. 소액으로 시작하세요.', en: 'Real trading risks real money. Only ever use API keys scoped to TRADE — never withdrawal. Start small.', ja: '実取引は実際の資金を失う恐れがあります。出金権限のないキーのみ使用してください。', th: 'การเทรดจริงมีความเสี่ยงต่อเงินจริง ใช้คีย์ที่จำกัดสิทธิ์เฉพาะการเทรดเท่านั้น', vi: 'Giao dịch thật có rủi ro mất tiền thật. Chỉ dùng khóa giới hạn quyền TRADE.', id: 'Trading sungguhan mempertaruhkan uang sungguhan. Selalu gunakan kunci API yang dibatasi hanya untuk TRADE — jangan pernah untuk penarikan dana. Mulailah dari nominal kecil.' }),
    tcs: tr(language, { ko: '실거래 약관에 동의합니다. 실제 자금이 사용되며 손실이 발생할 수 있음을 이해합니다.', en: 'I accept the live-trading terms and understand real money is at risk.', ja: '実取引の規約に同意し、実資金のリスクを理解します。', th: 'ฉันยอมรับข้อกำหนดการเทรดจริงและเข้าใจความเสี่ยงของเงินจริง', vi: 'Tôi chấp nhận điều khoản giao dịch thật và hiểu rủi ro mất tiền.', id: 'Saya menerima ketentuan trading live dan memahami bahwa uang sungguhan dipertaruhkan.' }),
    tcsRequired: tr(language, { ko: '실거래 약관에 먼저 동의해야 합니다.', en: 'You must accept the live-trading terms first.', ja: 'まず実取引の規約に同意してください。', th: 'ต้องยอมรับข้อกำหนดการเทรดจริงก่อน', vi: 'Bạn phải chấp nhận điều khoản trước.', id: 'Anda harus menerima ketentuan trading live terlebih dahulu.' }),
    needBoth: tr(language, { ko: 'API 키와 시크릿을 모두 입력하세요.', en: 'Enter both the API key and secret.', ja: 'APIキーとシークレットの両方を入力してください。', th: 'กรอกทั้งคีย์และความลับ API', vi: 'Nhập cả khóa và bí mật API.', id: 'Masukkan kunci API dan secret-nya.' }),
    connected: tr(language, { ko: '연결된 게이트웨이', en: 'Connected gateways', ja: '接続済みゲートウェイ', th: 'เกตเวย์ที่เชื่อมต่อ', vi: 'Cổng đã kết nối', id: 'Gateway terhubung' }),
    none: tr(language, { ko: '아직 연결된 게이트웨이가 없습니다. 자동매매 규칙의 live는 게이트웨이를 연결할 때까지 실행되지 않습니다.', en: 'No gateway connected yet. Automation rules set to live will not fill until you connect one.', ja: '未接続です。live のルールは接続するまで約定しません。', th: 'ยังไม่มีเกตเวย์ กฎ live จะยังไม่ทำงานจนกว่าจะเชื่อมต่อ', vi: 'Chưa có cổng nào. Quy tắc live sẽ không khớp lệnh cho đến khi kết nối.', id: 'Belum ada gateway yang terhubung. Aturan otomatisasi yang disetel ke live tidak akan tereksekusi sampai Anda menghubungkan satu gateway.' }),
    saved: tr(language, { ko: '게이트웨이가 연결되었습니다. 키는 서버에 암호화되어 저장되며 다시 표시되지 않습니다.', en: 'Gateway connected. Your keys are encrypted server-side and are never shown again.', ja: 'ゲートウェイを接続しました。キーは暗号化して保存され再表示されません。', th: 'เชื่อมต่อแล้ว คีย์ถูกเข้ารหัสฝั่งเซิร์ฟเวอร์และจะไม่แสดงอีก', vi: 'Đã kết nối. Khóa được mã hóa phía máy chủ và không hiển thị lại.', id: 'Gateway terhubung. Kunci Anda dienkripsi di sisi server dan tidak akan ditampilkan lagi.' }),
    liveReady: tr(language, { ko: '실거래 준비됨', en: 'live-ready', ja: '実取引可', th: 'พร้อมเทรดจริง', vi: 'sẵn sàng live', id: 'siap live' }),
    gatewayUrl: tr(language, { ko: 'Client Portal Gateway URL', en: 'Client Portal Gateway URL', ja: 'Client Portal Gateway URL', th: 'Client Portal Gateway URL', vi: 'Client Portal Gateway URL', id: 'URL Client Portal Gateway' }),
    accountId: tr(language, { ko: 'IBKR 계좌 번호 (예: DU1234567)', en: 'IBKR account id (e.g. DU1234567)', ja: 'IBKR口座番号 (例: DU1234567)', th: 'รหัสบัญชี IBKR (เช่น DU1234567)', vi: 'Mã tài khoản IBKR (vd: DU1234567)', id: 'ID akun IBKR (mis. DU1234567)' }),
    selfSigned: tr(language, { ko: '게이트웨이가 자체 서명 인증서를 사용합니다 (로컬 게이트웨이만)', en: 'Gateway uses a self-signed certificate (local gateways only)', ja: 'ゲートウェイが自己署名証明書を使用 (ローカルのみ)', th: 'เกตเวย์ใช้ใบรับรองแบบ self-signed (เฉพาะเกตเวย์ในเครื่อง)', vi: 'Cổng dùng chứng chỉ tự ký (chỉ cổng nội bộ)', id: 'Gateway memakai sertifikat yang ditandatangani sendiri (hanya untuk gateway lokal)' }),
    ibkrNote: tr(language, { ko: 'IBKR은 API 키를 쓰지 않습니다. 직접 Client Portal Gateway를 실행하고 로그인해 두면, 그 세션이 자격 증명이 됩니다. 이 서버에서 접근 가능한 주소여야 합니다. 계좌 번호가 D로 시작하면 모의 계좌이며, shadow 모드는 모의 계좌에서만 동작합니다.', en: 'IBKR does not use API keys. You run and log in to the Client Portal Gateway yourself — that session is the credential — and this server must be able to reach it. Account ids starting with D are paper accounts; shadow mode only works on a paper account.', ja: 'IBKRはAPIキーを使いません。Client Portal Gatewayをご自身で実行しログインし、このサーバーから到達可能にしてください。Dで始まる口座は模擬口座で、shadowは模擬口座でのみ動作します。', th: 'IBKR ไม่ใช้คีย์ API คุณต้องรันและล็อกอิน Client Portal Gateway เอง และเซิร์ฟเวอร์นี้ต้องเข้าถึงได้ บัญชีที่ขึ้นต้นด้วย D คือบัญชีจำลอง และ shadow ทำงานเฉพาะบัญชีจำลอง', vi: 'IBKR không dùng khóa API. Bạn tự chạy và đăng nhập Client Portal Gateway — phiên đó là thông tin xác thực — và máy chủ này phải truy cập được. Mã bắt đầu bằng D là tài khoản giấy; shadow chỉ hoạt động trên tài khoản giấy.', id: 'IBKR tidak memakai kunci API. Anda sendiri yang menjalankan dan masuk ke Client Portal Gateway — sesi itulah kredensialnya — dan server ini harus bisa menjangkaunya. ID akun yang diawali D adalah akun paper; mode shadow hanya bekerja pada akun paper.' }),
    needIbkr: tr(language, { ko: '게이트웨이 URL과 계좌 번호를 모두 입력하세요.', en: 'Enter both the gateway URL and the account id.', ja: 'ゲートウェイURLと口座番号の両方を入力してください。', th: 'กรอกทั้ง URL เกตเวย์และรหัสบัญชี', vi: 'Nhập cả URL cổng và mã tài khoản.', id: 'Masukkan URL gateway dan ID akunnya.' }),
    healthOk: tr(language, { ko: '세션 정상 — 주문을 받을 수 있습니다', en: 'session healthy — ready to accept orders', ja: 'セッション正常 — 発注可能', th: 'เซสชันปกติ — พร้อมรับคำสั่ง', vi: 'phiên bình thường — sẵn sàng nhận lệnh', id: 'sesi sehat — siap menerima order' }),
    healthBad: tr(language, { ko: '게이트웨이가 주문을 받지 못합니다 — live 규칙이 체결되지 않습니다', en: 'gateway cannot accept orders — live rules will not fill', ja: 'ゲートウェイが発注不可 — liveルールは約定しません', th: 'เกตเวย์รับคำสั่งไม่ได้ — กฎ live จะไม่ทำงาน', vi: 'cổng không nhận lệnh — quy tắc live sẽ không khớp', id: 'gateway tidak dapat menerima order — aturan live tidak akan tereksekusi' }),
    healthNeutral: tr(language, { ko: '자격 증명 저장됨 — 이 브로커는 세션 점검 대상이 아닙니다', en: 'credentials on file — this broker has no session to check', ja: '認証情報を保存済み — このブローカーはセッション点検対象外です', th: 'บันทึกข้อมูลรับรองแล้ว — โบรกเกอร์นี้ไม่มีเซสชันให้ตรวจ', vi: 'đã lưu thông tin xác thực — broker này không có phiên để kiểm tra', id: 'kredensial tersimpan — broker ini tidak punya sesi untuk diperiksa' }),
    detailAuthed: tr(language, { ko: '세션 인증됨', en: 'session authenticated', ja: 'セッション認証済み', th: 'เซสชันยืนยันแล้ว', vi: 'phiên đã xác thực', id: 'sesi terautentikasi' }),
    detailNotAuthed: tr(language, { ko: '게이트웨이 세션이 인증되지 않았습니다 — Client Portal Gateway에 다시 로그인하세요', en: 'gateway session is not authenticated — log in to the Client Portal Gateway again', ja: 'ゲートウェイセッションが未認証です — Client Portal Gateway に再ログインしてください', th: 'เซสชันเกตเวย์ยังไม่ยืนยัน — ล็อกอิน Client Portal Gateway อีกครั้ง', vi: 'phiên cổng chưa xác thực — đăng nhập lại Client Portal Gateway', id: 'sesi gateway belum terautentikasi — masuk kembali ke Client Portal Gateway' }),
    detailCompeting: tr(language, { ko: '다른 세션이 이 계좌를 점유하고 있습니다', en: 'another session is competing for this account', ja: '別のセッションがこの口座を占有しています', th: 'มีเซสชันอื่นแย่งใช้บัญชีนี้', vi: 'một phiên khác đang tranh chấp tài khoản này', id: 'ada sesi lain yang berebut akun ini' }),
    detailQuote: tr(language, { ko: '게이트웨이 응답', en: 'gateway says', ja: 'ゲートウェイ応答', th: 'เกตเวย์แจ้ง', vi: 'cổng báo', id: 'gateway menyatakan' }),
    errGatewayScheme: tr(language, { ko: '게이트웨이 URL은 http:// 또는 https:// 로 시작해야 합니다', en: 'gateway URL must start with http:// or https://', ja: 'ゲートウェイURLは http:// または https:// で始まる必要があります', th: 'URL เกตเวย์ต้องขึ้นต้นด้วย http:// หรือ https://', vi: 'URL cổng phải bắt đầu bằng http:// hoặc https://', id: 'URL gateway harus diawali http:// atau https://' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.', id: 'Silakan masuk.' }),
    ordersTitle: tr(language, { ko: '브로커 주문 내역', en: 'Broker orders', ja: 'ブローカー注文履歴', th: 'ประวัติคำสั่งโบรกเกอร์', vi: 'Lệnh tại broker', id: 'Order broker' }),
    ordersHint: tr(language, { ko: '요청 수량과 브로커가 확인한 체결 수량을 함께 표시합니다 — 두 값이 다르면 주문이 드리프트 목록에도 나타납니다.', en: 'Shows the requested size next to the broker-confirmed fill — when they differ the order also appears in the drift list.', ja: '要求数量とブローカー確認済み約定数量を並べて表示 — 差異があればドリフト一覧にも表示されます。', th: 'แสดงขนาดที่ขอเทียบกับที่โบรกเกอร์ยืนยัน — ถ้าต่างกันจะปรากฏในรายการดริฟต์ด้วย', vi: 'Hiển thị khối lượng yêu cầu cạnh khối lượng broker xác nhận — nếu khác nhau, lệnh cũng xuất hiện trong danh sách lệch.', id: 'Menampilkan ukuran yang diminta di samping eksekusi yang dikonfirmasi broker — bila berbeda, order tersebut juga muncul di daftar penyimpangan.' }),
    driftTitle: tr(language, { ko: '드리프트 기록', en: 'Drift records', ja: 'ドリフト記録', th: 'บันทึกดริฟต์', vi: 'Bản ghi lệch', id: 'Catatan penyimpangan' }),
    driftHint: tr(language, { ko: '플랫폼 원장과 브로커의 실제 결과가 달랐던 경우입니다. 원장은 자동으로 수정되지 않으니 브로커 계좌를 확인하고 직접 정정하세요.', en: 'Cases where the platform ledger and the broker’s actual outcome disagreed. The ledger is never auto-corrected — review your broker account and fix manually.', ja: 'プラットフォーム台帳とブローカーの実際の結果が食い違ったケースです。台帳は自動修正されません — ブローカー口座を確認し手動で修正してください。', th: 'กรณีที่บัญชีแพลตฟอร์มกับผลจริงของโบรกเกอร์ไม่ตรงกัน บัญชีจะไม่ถูกแก้อัตโนมัติ — ตรวจสอบและแก้ไขเอง', vi: 'Trường hợp sổ nền tảng và kết quả thực tế của broker khác nhau. Sổ không tự sửa — hãy kiểm tra tài khoản broker và tự chỉnh.', id: 'Kasus di mana buku platform dan hasil sebenarnya dari broker tidak cocok. Buku tidak pernah dikoreksi otomatis — periksa akun broker Anda dan perbaiki secara manual.' }),
    reqQty: tr(language, { ko: '요청', en: 'req', ja: '要求', th: 'ขอ', vi: 'yêu cầu', id: 'diminta' }),
    webullAccountId: tr(language, { ko: 'Webull 계좌 ID (선택 — 계좌가 여러 개일 때만)', en: 'Webull account id (optional — only if you hold more than one account)', ja: 'Webull口座ID (任意 — 複数口座がある場合のみ)', th: 'รหัสบัญชี Webull (ไม่บังคับ — เฉพาะเมื่อมีหลายบัญชี)', vi: 'Mã tài khoản Webull (tùy chọn — chỉ khi có nhiều tài khoản)', id: 'ID akun Webull (opsional — hanya bila Anda punya lebih dari satu akun)' }),
    webullNote: tr(language, { ko: 'Webull은 미국 주식 현물(롱 전용)만 지원합니다. App Key와 App Secret을 사용하세요. shadow는 Webull PaperTrade 환경으로 전송되므로 PaperTrade용 키가 필요합니다.', en: 'Webull supports US stocks only, spot and long-only. Use your App Key and App Secret. Shadow mode sends orders to Webull PaperTrade, so it needs PaperTrade app keys.', ja: 'Webullは米国株の現物(ロングのみ)に対応します。App KeyとApp Secretを使用してください。shadowはWebull PaperTrade環境に送信されるため、PaperTrade用キーが必要です。', th: 'Webull รองรับเฉพาะหุ้นสหรัฐฯ แบบ spot (ซื้ออย่างเดียว) ใช้ App Key และ App Secret โหมด shadow จะส่งคำสั่งไปที่ Webull PaperTrade จึงต้องใช้คีย์ PaperTrade', vi: 'Webull chỉ hỗ trợ cổ phiếu Mỹ giao ngay (chỉ mua). Dùng App Key và App Secret. Chế độ shadow gửi lệnh tới Webull PaperTrade nên cần khóa PaperTrade.', id: 'Webull hanya mendukung saham AS spot (long saja). Gunakan App Key dan App Secret. Mode shadow mengirim order ke Webull PaperTrade, jadi perlu kunci aplikasi PaperTrade.' }),
    fillQty: tr(language, { ko: '체결', en: 'filled', ja: '約定', th: 'สำเร็จ', vi: 'khớp', id: 'tereksekusi' }),
  }

  // Health `detail` is either one of OUR fixed strings (localize it) or
  // broker/network passthrough text we can't translate — for the latter, keep
  // the original words but frame them so a non-English reader knows it's a quote
  // rather than an untranslated label.
  function localizeDetail(detail?: string | null): string {
    if (!detail) return ''
    if (detail === 'session authenticated') return T.detailAuthed
    if (detail.startsWith('gateway session is not authenticated')) return T.detailNotAuthed
    if (detail.startsWith('another session is competing')) return T.detailCompeting
    if (detail === 'broker has no session to check; credentials are on file') return ''
    return language === 'en' ? detail : `${T.detailQuote}: ${detail}`
  }

  // Our own validation messages get localized; broker/pydantic passthrough is
  // framed as a quote so a non-English reader isn't shown a bare English string.
  function localizeConnectError(raw: string): string {
    if (raw.includes('gateway_url must start with')) return T.errGatewayScheme
    if (raw.includes('requires gateway_url and account_id')) return T.needIbkr
    if (/requires api_key, api_secret and passphrase/.test(raw)) return T.needPassphrase
    if (/requires api_key and api_secret/.test(raw)) return T.needBoth
    return language === 'en' ? raw : `${T.detailQuote}: ${raw}`
  }

  const loadAccounts = useCallback(() => {
    if (!token) return
    fetch(`${API_BASE}/execution/accounts`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : { accounts: [] })
      .then(d => setAccounts(d.accounts || []))
      .catch(() => { /* leave the list empty; the connect form still works */ })
    // Credentials on file is not the same as the venue accepting orders — an
    // IBKR session expires and a live rule then quietly stops filling.
    fetch(`${API_BASE}/execution/health`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : null)
      .then(setHealth)
      .catch(() => setHealth(null))
    // Broker order + drift history — empty for simulator-only accounts, and
    // the sections below render nothing in that case.
    fetch(`${API_BASE}/execution/orders?limit=20`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : { orders: [] })
      .then(d => setOrders(d.orders || []))
      .catch(() => {})
    fetch(`${API_BASE}/execution/reconciliations?limit=20`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : { reconciliations: [] })
      .then(d => setDrift((d.reconciliations || []).filter((r: any) => r.status !== 'ok')))
      .catch(() => {})
  }, [token])

  useEffect(() => {
    if (!token) return
    fetch(`${API_BASE}/claw/agents/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(setMe).catch(() => {})
    fetch(`${API_BASE}/execution/brokers`)
      .then(r => r.json())
      .then(d => {
        const list: string[] = d.brokers || []
        setBrokers(list)
        setSpecs(d.specs || {})
        setRegions(d.regions || {})
        setBroker(prev => prev || list[0] || '')
      })
      .catch(() => {})
    loadAccounts()
  }, [token, loadAccounts])

  // IBKR and Webull share the account-id input; an id typed for one broker
  // must never ride along into another broker's connect payload.
  function pickBroker(next: string) {
    setBroker(next)
    setAccountId('')
  }

  const isIbkr = broker === 'ibkr'
  // Webull: key/secret plus an OPTIONAL account id (the adapter refuses to
  // guess between several accounts on one login).
  const isWebull = broker === 'webull'
  const needsPassphrase = (specs[broker]?.fields || []).includes('passphrase')
  // Coinbase signs with an ES256 JWT, so its "secret" is a multi-line EC
  // private key. A single-line input eats the newlines and the PEM stops
  // parsing, so that one venue gets a textarea.
  const secretIsPem = broker === 'coinbase'

  async function openGuide() {
    if (!broker || guideBusy) return
    setGuideBusy(true)
    try {
      // Reader's language first, English as the runtime fallback — same
      // policy as the docs pages.
      for (const lang of language === 'en' ? ['en'] : [language, 'en']) {
        const res = await fetch(`${API_BASE}/guide/doc/gwsetup-${broker}-${lang}`,
          { headers: { Authorization: `Bearer ${token}` } })
        if (res.ok) {
          setGuideHtml(await res.text())
          setGuideOpen(true)
          return
        }
      }
      setError(T.guideErr)
    } catch {
      setError(T.guideErr)
    } finally {
      setGuideBusy(false)
    }
  }

  async function connect() {
    setError(''); setNotice('')
    if (isIbkr) {
      if (!gatewayUrl.trim() || !accountId.trim()) { setError(T.needIbkr); return }
    } else if (!apiKey.trim() || !apiSecret.trim()) {
      setError(T.needBoth); return
    } else if (needsPassphrase && !passphrase.trim()) {
      setError(T.needPassphrase); return
    }
    if (!acceptedTcs) { setError(T.tcsRequired); return }
    setBusy(true)
    try {
      // Create the account FIRST. Recording consent before it means a rejected
      // account (e.g. a bad gateway_url 400s) still leaves an immutable consent
      // record for a broker the user never connected. The account is created in
      // paper mode, so it is harmless if the consent step later fails.
      const payload = isIbkr
        ? { broker, gateway_url: gatewayUrl.trim(), account_id: accountId.trim(),
            allow_self_signed: allowSelfSigned }
        : { broker, api_key: apiKey.trim(), api_secret: apiSecret.trim(),
            ...(needsPassphrase ? { passphrase: passphrase.trim() } : {}),
            ...(isWebull && accountId.trim() ? { account_id: accountId.trim() } : {}) }
      const res = await fetch(`${API_BASE}/execution/accounts`, {
        method: 'POST', headers: authHeaders, body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const b = await res.json().catch(() => null)
        const d = b?.detail
        const raw = typeof d === 'string' ? d : (Array.isArray(d) ? d.map((e: any) => e?.msg).join('; ') : 'Could not connect gateway')
        setError(localizeConnectError(raw))
        return
      }
      // Then record consent — automation refuses to route live without it.
      const tcs = await fetch(`${API_BASE}/execution/tcs-accept`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify({ broker, tcs_version: 'v1' }),
      })
      if (!tcs.ok) {
        const b = await tcs.json().catch(() => null)
        setError(b?.detail || 'Could not record consent'); return
      }
      // Drop the secrets from component state the moment they are stored.
      setApiKey(''); setApiSecret(''); setPassphrase(''); setAccountId(''); setAcceptedTcs(false)
      setNotice(T.saved)
      loadAccounts()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return <div><div className="header"><div><h1 className="header-title">{T.title}</h1></div></div>
      <div className="empty-state"><div className="empty-icon">◱</div><div className="empty-title">{T.login}</div></div></div>
  }

  const card = (active: boolean): any => ({
    flex: '1 1 320px', border: '2px solid ' + (active ? 'var(--accent-primary,#c26a45)' : 'var(--border-color,#d3c8b6)'),
    borderRadius: 14, padding: 22, background: 'var(--bg-card,#fffdf9)',
  })
  const badge = (bg: string): any => ({ display: 'inline-block', fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 6, background: bg, color: '#fff' })
  const field: any = { width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', marginBottom: 8 }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{T.title}</h1>
          <div style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 14 }}>{T.subtitle}</div>
        </div>
      </div>

      {/* Per-broker connection guide — standalone doc in a modal iframe. The
          doc paints its own light/dark palette, so the frame stays unthemed. */}
      {guideOpen && guideHtml && (
        <div onClick={() => setGuideOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 60,
                   display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: 'min(920px, 100%)', height: 'min(82vh, 900px)', background: 'var(--bg-card,#fffdf9)',
                     borderRadius: 14, border: '1px solid var(--border-color,#d3c8b6)',
                     display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: '10px 14px', borderBottom: '1px solid var(--border-color,#d3c8b6)' }}>
              <b style={{ fontSize: 14 }}>📖 {broker}</b>
              <button onClick={() => setGuideOpen(false)}
                style={{ border: 'none', background: 'transparent', color: 'var(--text-secondary,#8a8073)',
                         fontSize: 13, cursor: 'pointer', fontWeight: 600 }}>
                ✕ {T.guideClose}
              </button>
            </div>
            <iframe title="gateway guide" srcDoc={guideHtml}
              sandbox=""
              style={{ flex: 1, width: '100%', border: 'none', background: '#fff' }} />
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
        {/* Simulator — always available, needs no setup */}
        <div style={card(accounts.length === 0)}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 20 }}>◐</span>
            <h2 style={{ margin: 0, fontSize: 18 }}>{T.simTitle}</h2>
          </div>
          <p style={{ color: 'var(--text-secondary,#5f574c)', fontSize: 14 }}>{T.simDesc}</p>
          <div style={{ margin: '14px 0', fontSize: 13, color: 'var(--text-secondary,#8a8073)' }}>
            {T.balance}: <b style={{ fontSize: 18, color: 'inherit' }}>${(me?.cash ?? 100000).toLocaleString()}</b>
          </div>
        </div>

        {/* Trading gateway */}
        <div style={card(accounts.length > 0)}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 20 }}>●</span>
            <h2 style={{ margin: 0, fontSize: 18 }}>{T.realTitle}</h2>
            {accounts.length > 0 && <span style={{ ...badge('#c26a45'), marginLeft: 'auto' }}>{T.liveReady}</span>}
          </div>
          <p style={{ color: 'var(--text-secondary,#5f574c)', fontSize: 14 }}>{T.realDesc}</p>

          <div style={{ background: 'rgba(240,102,63,0.1)', border: '1px solid rgba(240,102,63,0.4)', borderRadius: 8, padding: '10px 12px', fontSize: 12.5, color: '#c2410c', margin: '12px 0' }}>
            ⚠️ {T.warn}
          </div>

          {/* Region drives ordering only — every broker stays connectable. */}
          {Object.keys(regions).length > 0 && (
            <>
              <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>{T.regionLabel}</label>
              <select value={region} onChange={e => setRegion(e.target.value)} style={field}>
                {Object.keys(regions).map(code =>
                  <option key={code} value={code}>{code === 'GLOBAL' ? T.regionGlobal : code}</option>)}
              </select>
            </>
          )}
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>{T.exchange}</label>
          {(() => {
            const rec = (regions[region] || []).filter(b => brokers.includes(b))
            const rest = brokers.filter(b => !rec.includes(b))
            if (rec.length === 0) {
              return (
                <select value={broker} onChange={e => pickBroker(e.target.value)} style={field}>
                  {brokers.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
              )
            }
            return (
              <select value={broker} onChange={e => pickBroker(e.target.value)} style={field}>
                <optgroup label={`★ ${T.recommended}`}>
                  {rec.map(b => <option key={b} value={b}>{b}</option>)}
                </optgroup>
                {rest.length > 0 && (
                  <optgroup label={T.otherBrokers}>
                    {rest.map(b => <option key={b} value={b}>{b}</option>)}
                  </optgroup>
                )}
              </select>
            )
          })()}
          {broker && (
            <button onClick={openGuide} disabled={guideBusy}
              style={{ display: 'block', marginBottom: 10, padding: '5px 11px', borderRadius: 7,
                       border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)',
                       color: 'var(--accent-primary,#c26a45)', fontSize: 12.5, fontWeight: 600,
                       cursor: guideBusy ? 'wait' : 'pointer' }}>
              📖 {T.guideBtn} — {broker}
            </button>
          )}
          {isIbkr ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.5, margin: '2px 0 10px' }}>
                ⓘ {T.ibkrNote}
              </div>
              <input value={gatewayUrl} onChange={e => setGatewayUrl(e.target.value)}
                placeholder={T.gatewayUrl} autoComplete="off" spellCheck={false} style={field} />
              <input value={accountId} onChange={e => setAccountId(e.target.value)}
                placeholder={T.accountId} autoComplete="off" spellCheck={false} style={field} />
              <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12.5, margin: '0 0 10px', lineHeight: 1.45 }}>
                <input type="checkbox" checked={allowSelfSigned}
                  onChange={e => setAllowSelfSigned(e.target.checked)} style={{ marginTop: 2 }} />
                <span>{T.selfSigned}</span>
              </label>
            </>
          ) : (
            <>
              <input value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={T.apiKey}
                autoComplete="off" spellCheck={false} style={field} />
              {secretIsPem ? (
                <textarea value={apiSecret} onChange={e => setApiSecret(e.target.value)}
                  placeholder={T.pemSecret} rows={5} autoComplete="off" spellCheck={false}
                  style={{ ...field, fontFamily: 'ui-monospace, monospace', fontSize: 12, resize: 'vertical' }} />
              ) : (
                <input value={apiSecret} onChange={e => setApiSecret(e.target.value)} placeholder={T.apiSecret}
                  type="password" autoComplete="new-password" spellCheck={false} style={field} />
              )}
              {isWebull && (
                <>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)', lineHeight: 1.5, margin: '2px 0 10px' }}>
                    ⓘ {T.webullNote}
                  </div>
                  <input value={accountId} onChange={e => setAccountId(e.target.value)}
                    placeholder={T.webullAccountId} autoComplete="off" spellCheck={false} style={field} />
                </>
              )}
              {needsPassphrase && (
                <input value={passphrase} onChange={e => setPassphrase(e.target.value)} placeholder={T.passphrase}
                  type="password" autoComplete="new-password" spellCheck={false} style={field} />
              )}
            </>
          )}

          <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12.5, margin: '4px 0 12px', lineHeight: 1.45 }}>
            <input type="checkbox" checked={acceptedTcs} onChange={e => setAcceptedTcs(e.target.checked)} style={{ marginTop: 2 }} />
            <span>{T.tcs}</span>
          </label>

          {error && <div style={{ color: '#f0663f', fontSize: 12.5, marginBottom: 8 }}>⚠️ {error}</div>}
          {notice && <div style={{ color: '#3fb950', fontSize: 12.5, marginBottom: 8 }}>✓ {notice}</div>}

          <button onClick={connect} disabled={busy || !broker}
            style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer', opacity: busy ? 0.6 : 1 }}>
            {T.connect}
          </button>

          {/* A lapsed session looks exactly like a quiet market from outside,
              so say it plainly. Three states: checked+ok (green), checked+bad
              (red), and configured-but-not-checkable — key-pair brokers have no
              session to probe, so show a neutral "credentials on file" instead
              of no feedback at all. */}
          {health?.configured && (() => {
            const neutral = !health.checked           // alpaca/binance: nothing to probe
            const tone = neutral ? 'neutral' : (health.ok ? 'ok' : 'bad')
            const c = tone === 'ok' ? { bg: 'rgba(63,185,80,0.12)', br: 'rgba(63,185,80,0.4)', fg: '#3fb950', icon: '✓ ' }
              : tone === 'bad' ? { bg: 'rgba(240,102,63,0.12)', br: 'rgba(240,102,63,0.45)', fg: '#f0663f', icon: '⚠️ ' }
              : { bg: 'rgba(90,120,160,0.12)', br: 'rgba(90,120,160,0.4)', fg: 'var(--text-secondary,#8a8073)', icon: 'ⓘ ' }
            const headline = tone === 'ok' ? T.healthOk : tone === 'bad' ? T.healthBad : T.healthNeutral
            // health.detail is either our own known message (localized below) or
            // broker/network passthrough text we can't translate — keep the raw
            // words but frame them so a non-English user knows it's a quote.
            const detail = localizeDetail(health.detail)
            return (
              <div style={{ marginTop: 14, padding: '9px 11px', borderRadius: 8, fontSize: 12.5, lineHeight: 1.5,
                background: c.bg, border: `1px solid ${c.br}`, color: c.fg }}>
                {c.icon}{headline}
                {detail && <div style={{ marginTop: 4, opacity: 0.85 }}>{detail}</div>}
              </div>
            )
          })()}

          <div style={{ marginTop: 16, fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)' }}>{T.connected}</div>
          {accounts.length === 0 ? (
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)', marginTop: 6, lineHeight: 1.5 }}>{T.none}</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
              {accounts.map(a => (
                <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)' }}>
                  <b>{a.broker}</b>
                  {a.is_active ? <span style={{ ...badge('#3fb950'), fontSize: 10 }}>active</span> : null}
                  <span style={{ marginLeft: 'auto', color: 'var(--text-secondary,#8a8073)', fontSize: 11.5 }}>
                    {formatLocalDateTime(a.updated_at, language)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Broker order history — invisible until a gateway has actually been
          used, so simulator-only accounts see nothing extra here. */}
      {orders.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-secondary,#8a8073)' }}>{T.ordersTitle}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)', margin: '6px 0 10px', lineHeight: 1.5 }}>{T.ordersHint}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {orders.map(o => {
              const statusColor = o.status === 'filled' ? '#3fb950'
                : (o.status === 'rejected' || o.status === 'cancelled') ? '#f0663f'
                : o.status === 'partial_fill' ? '#e3b341' : 'var(--text-secondary,#8a8073)'
              return (
                <div key={o.id} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', flexWrap: 'wrap' }}>
                  <b>{o.symbol}</b>
                  <span style={{ color: o.side === 'buy' || o.side === 'cover' ? '#3fb950' : '#f0663f', fontWeight: 600 }}>{o.side}</span>
                  <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 5, background: 'rgba(138,128,115,0.15)', color: 'var(--text-secondary,#8a8073)' }}>{o.broker} · {o.execution_mode}</span>
                  <span style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 12 }}>
                    {T.reqQty} {Number(o.quantity)}{o.filled_qty != null && ` · ${T.fillQty} ${Number(o.filled_qty)}`}
                  </span>
                  <span style={{ color: statusColor, fontWeight: 600, fontSize: 12 }}>{o.status}</span>
                  <span style={{ marginLeft: 'auto', color: 'var(--text-secondary,#8a8073)', fontSize: 11.5 }}>
                    {formatLocalDateTime(o.created_at, language)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Drift — the ledger and the broker disagreed; deliberately loud. */}
      {drift.length > 0 && (
        <div className="card" style={{ marginTop: 14, border: '1px solid rgba(240,102,63,0.45)' }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.06em', color: '#f0663f' }}>⚠ {T.driftTitle}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary,#8a8073)', margin: '6px 0 10px', lineHeight: 1.5 }}>{T.driftHint}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {drift.map(r => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', flexWrap: 'wrap' }}>
                <b>{r.symbol}</b>
                <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 5, background: 'rgba(138,128,115,0.15)', color: 'var(--text-secondary,#8a8073)' }}>{r.broker}</span>
                <span style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 12 }}>
                  ledger {Number(r.paper_qty)} ≠ broker {r.broker_qty == null ? '—' : Number(r.broker_qty)}
                </span>
                <span style={{ color: '#f0663f', fontWeight: 600, fontSize: 12 }}>{r.status}</span>
                {r.error_message && <span style={{ color: 'var(--text-secondary,#8a8073)', fontSize: 11.5 }}>{String(r.error_message).slice(0, 60)}</span>}
                <span style={{ marginLeft: 'auto', color: 'var(--text-secondary,#8a8073)', fontSize: 11.5 }}>
                  {formatLocalDateTime(r.recorded_at, language)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default AccountsPage
