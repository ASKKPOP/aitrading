"""Generate per-broker "connect this gateway" guides in all 6 languages.

Run from the repo root:
    .venv/bin/python docs/design/_gen_gateway_setup_guides.py

Writes docs/design/gateway-setup-{broker}-{lang}.html (9 brokers x 6 langs),
which build_guide_content.py copies into service/server/guide_content/. The
Accounts page opens these inline when a member picks a broker — they are the
"how do I actually get an API key and what will Sooppiy do with it" companion
to the conceptual Live Trading Gateway guide (group `gateway`).

Why generated: the shared skeleton (connect steps, the three modes, the safety
rails) must agree across 54 files and with the actual gateway behaviour
(BROKER_SPECS in execution/base.py). Hand-maintaining 54 copies guarantees
drift the first time a rail changes. Broker facts (key-creation path, venue
quirks, error codes) live in one table below.

The per-venue shadow wording mirrors execution/base.py BROKER_SPECS exactly:
sandbox venues really trade in the venue's test environment, dry-run venues
send the venue's own validate/test call (unfillable by construction), and
journal venues (Upbit) get NO network call in shadow. If BROKER_SPECS
changes, regenerate.

Non-English prose is machine-drafted; English is the runtime fallback.
Have ko/ja/th/vi/id proofread by a native reader before relying on them.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "service" / "server"))
from execution.base import BROKER_SPECS  # noqa: E402

OUT = Path(__file__).resolve().parent
LANGS = ["en", "ko", "ja", "th", "vi", "id"]

# Brokers already allowed to route live money (gateway._LEGACY_LIVE_BROKERS).
LIVE_TODAY = {"alpaca", "binance", "ibkr"}

BROKER_NAMES = {
    "binance": "Binance", "alpaca": "Alpaca", "ibkr": "Interactive Brokers",
    "bybit": "Bybit", "okx": "OKX", "kraken": "Kraken",
    "cryptocom": "Crypto.com Exchange", "upbit": "Upbit", "kucoin": "KuCoin",
}

# ── shared strings ───────────────────────────────────────────────────────────

S = {
"en": dict(
    kicker="SOOPPIY DOCS — TRADING GATEWAY SETUP",
    subtitle="How to create the API credentials at {name} and connect them on the Accounts page.",
    badge_live="live trading available",
    badge_gated="shadow first — live rollout in progress",
    h_need="What you need",
    h_create="Create your credentials at {name}",
    h_connect="Connect it on the Accounts page",
    h_modes="What each mode does with {name}",
    h_notes="Venue notes",
    h_trouble="Troubleshooting",
    f_key="API key", f_secret="API secret", f_pass="API passphrase (chosen when the key is created)",
    f_gwurl="Client Portal Gateway URL", f_acct="IBKR account id",
    warn_keys="Grant TRADE permission only — never withdrawal. Use the venue's IP allowlist when it offers one. Start small. Your keys are encrypted at rest (AES-GCM) on Sooppiy's server and are never shown again after you save them.",
    connect_steps=[
        "Open <b>Accounts</b> → <b>Trading gateway</b>.",
        "Pick your region (ordering only — every broker stays available) and choose <b>{name}</b>.",
        "Paste the credentials from step 2.",
        "Read and accept the live-trading terms — required even if you only plan to use shadow.",
        "Press <b>Connect gateway</b>. The account starts in <b>paper</b> mode: nothing is sent to {name} yet.",
        "Switch the account to <b>shadow</b> (recommended first) or <b>live</b> on the account card.",
    ],
    mode_th=["Mode", "What happens"],
    mode_sim="<b>paper / simulator</b> — every trade stays on Sooppiy's internal ledger. {name} is never contacted.",
    mode_live_live="<b>live</b> — real orders go to your {name} account. The broker is authoritative: a rejected order never creates a platform position. Requires accepted terms and usable credentials; refusals are always explicit, never a silent simulation.",
    mode_live_gated="<b>live</b> — not yet open for {name}: the venue is in its shadow rollout soak, and live routing is refused with an explicit message until Sooppiy enables it platform-wide. Your rules can run in shadow meanwhile. Newly enabled venues also carry a $1,000 per-order limit at first (over-limit orders are refused, never resized).",
    trouble_th=["Symptom", "What it means / what to do"],
    t_creds=("“credentials are missing or cannot be decrypted”",
             "The stored key can no longer be read (for example after a server key rotation). Reconnect the broker with fresh credentials."),
    t_tcs=("“live-trading terms have not been accepted”",
           "Accept the terms for this broker on the Accounts page — consent is recorded per broker."),
    t_allow=("“not yet enabled for live orders on this platform”",
             "The venue is still in its shadow rollout. Shadow works today; live opens when the soak completes."),
    drift_note="Whatever mode you use, the <b>Broker orders</b> and <b>Drift records</b> panels at the bottom of the Accounts page show what {name} actually confirmed next to what the ledger assumed — differences are surfaced loudly, never auto-corrected.",
),
"ko": dict(
    kicker="SOOPPIY 문서 — 거래 게이트웨이 연결",
    subtitle="{name}에서 API 자격 증명을 만들고 계정 페이지에서 연결하는 방법.",
    badge_live="실거래 가능",
    badge_gated="섀도 우선 — 실거래는 단계적 오픈 중",
    h_need="준비물",
    h_create="{name}에서 자격 증명 만들기",
    h_connect="계정 페이지에서 연결하기",
    h_modes="각 모드에서 {name}에 일어나는 일",
    h_notes="거래소 특이사항",
    h_trouble="문제 해결",
    f_key="API 키", f_secret="API 시크릿", f_pass="API 패스프레이즈 (키 생성 시 직접 설정)",
    f_gwurl="Client Portal Gateway URL", f_acct="IBKR 계좌 번호",
    warn_keys="반드시 거래(TRADE) 권한만 부여하세요 — 출금 권한은 절대 안 됩니다. 거래소가 IP 허용목록을 제공하면 사용하세요. 소액으로 시작하세요. 키는 Sooppiy 서버에 암호화(AES-GCM)되어 저장되며 저장 후 다시 표시되지 않습니다.",
    connect_steps=[
        "<b>계정</b> → <b>거래 게이트웨이</b>를 엽니다.",
        "지역을 선택하고(추천 정렬일 뿐, 모든 브로커 연결 가능) <b>{name}</b>을(를) 선택합니다.",
        "2단계에서 만든 자격 증명을 붙여넣습니다.",
        "실거래 약관을 읽고 동의합니다 — 섀도만 쓸 계획이어도 필요합니다.",
        "<b>게이트웨이 연결</b>을 누릅니다. 계정은 <b>paper</b> 모드로 시작하며 아직 {name}에는 아무것도 전송되지 않습니다.",
        "계정 카드에서 <b>shadow</b>(먼저 권장) 또는 <b>live</b>로 전환합니다.",
    ],
    mode_th=["모드", "동작"],
    mode_sim="<b>paper / 시뮬레이터</b> — 모든 거래가 Sooppiy 내부 원장에만 기록됩니다. {name}에는 접속하지 않습니다.",
    mode_live_live="<b>live</b> — 실제 주문이 {name} 계좌로 전송됩니다. 브로커가 기준이며, 거부된 주문은 플랫폼 포지션을 만들지 않습니다. 약관 동의와 유효한 자격 증명이 필요하며, 거부는 항상 명시적으로 표시됩니다 — 몰래 시뮬레이션으로 바뀌지 않습니다.",
    mode_live_gated="<b>live</b> — {name}은(는) 아직 실거래가 열리지 않았습니다. 섀도 검증 기간(소크)이 끝나고 플랫폼에서 활성화될 때까지 실거래 주문은 명시적 메시지와 함께 거부됩니다. 그동안 규칙은 섀도로 운영할 수 있습니다. 새로 열린 거래소는 초기에 주문당 $1,000 한도가 적용됩니다(초과 주문은 축소가 아니라 거부).",
    trouble_th=["증상", "의미 / 조치"],
    t_creds=("“credentials are missing or cannot be decrypted”",
             "저장된 키를 더 이상 읽을 수 없는 상태입니다(예: 서버 키 교체 후). 새 자격 증명으로 브로커를 다시 연결하세요."),
    t_tcs=("“live-trading terms have not been accepted”",
           "계정 페이지에서 이 브로커의 실거래 약관에 동의하세요 — 동의는 브로커별로 기록됩니다."),
    t_allow=("“not yet enabled for live orders on this platform”",
             "이 거래소는 아직 섀도 검증 중입니다. 섀도는 지금도 동작하며, 검증이 끝나면 실거래가 열립니다."),
    drift_note="어떤 모드든 계정 페이지 하단의 <b>브로커 주문 내역</b>과 <b>드리프트 기록</b>에서 {name}이(가) 실제로 확인한 값과 원장의 가정을 나란히 볼 수 있습니다 — 차이는 크게 표시될 뿐, 자동으로 수정되지 않습니다.",
),
"ja": dict(
    kicker="SOOPPIY ドキュメント — 取引ゲートウェイ接続",
    subtitle="{name}でAPI資格情報を作成し、アカウントページで接続する方法。",
    badge_live="実取引可能",
    badge_gated="シャドー優先 — 実取引は段階的に開放中",
    h_need="必要なもの",
    h_create="{name}で資格情報を作成する",
    h_connect="アカウントページで接続する",
    h_modes="各モードで{name}に起きること",
    h_notes="取引所の注意点",
    h_trouble="トラブルシューティング",
    f_key="APIキー", f_secret="APIシークレット", f_pass="APIパスフレーズ (キー作成時に自分で設定)",
    f_gwurl="Client Portal Gateway URL", f_acct="IBKR口座番号",
    warn_keys="必ず取引(TRADE)権限のみを付与してください — 出金権限は絶対に不可。取引所がIP許可リストを提供する場合は使用してください。少額から始めましょう。キーはSooppiyのサーバーで暗号化(AES-GCM)保存され、保存後は再表示されません。",
    connect_steps=[
        "<b>アカウント</b> → <b>取引ゲートウェイ</b>を開きます。",
        "地域を選び(おすすめ順になるだけで、全ブローカー接続可能)、<b>{name}</b>を選択します。",
        "手順2で作成した資格情報を貼り付けます。",
        "実取引規約を読んで同意します — シャドーのみ使う場合でも必要です。",
        "<b>ゲートウェイを接続</b>を押します。アカウントは<b>paper</b>モードで始まり、まだ{name}には何も送信されません。",
        "アカウントカードで<b>shadow</b>(まず推奨)か<b>live</b>に切り替えます。",
    ],
    mode_th=["モード", "動作"],
    mode_sim="<b>paper / シミュレーター</b> — すべての取引はSooppiy内部台帳のみに記録されます。{name}には接続しません。",
    mode_live_live="<b>live</b> — 実際の注文が{name}口座に送信されます。ブローカーが正であり、拒否された注文はプラットフォームのポジションを作りません。規約同意と有効な資格情報が必要で、拒否は常に明示されます — 無断でシミュレーションに切り替わることはありません。",
    mode_live_gated="<b>live</b> — {name}はまだ実取引が開放されていません。シャドー検証期間が完了しプラットフォームで有効化されるまで、実注文は明示的なメッセージとともに拒否されます。その間もルールはシャドーで運用できます。新規開放された取引所には当初、注文あたり$1,000の上限があります(超過注文は縮小ではなく拒否)。",
    trouble_th=["症状", "意味 / 対処"],
    t_creds=("“credentials are missing or cannot be decrypted”",
             "保存済みキーが読み取れない状態です(例: サーバーキー交換後)。新しい資格情報でブローカーを再接続してください。"),
    t_tcs=("“live-trading terms have not been accepted”",
           "アカウントページでこのブローカーの実取引規約に同意してください — 同意はブローカーごとに記録されます。"),
    t_allow=("“not yet enabled for live orders on this platform”",
             "この取引所はまだシャドー検証中です。シャドーは現在も動作し、検証完了後に実取引が開放されます。"),
    drift_note="どのモードでも、アカウントページ下部の<b>ブローカー注文履歴</b>と<b>ドリフト記録</b>で、{name}が実際に確認した値と台帳の想定を並べて確認できます — 差異は大きく表示されるだけで、自動修正はされません。",
),
"th": dict(
    kicker="เอกสาร SOOPPIY — การเชื่อมต่อเกตเวย์เทรด",
    subtitle="วิธีสร้างข้อมูลรับรอง API ที่ {name} และเชื่อมต่อในหน้าบัญชี",
    badge_live="เทรดจริงได้",
    badge_gated="เริ่มที่ shadow — การเทรดจริงกำลังทยอยเปิด",
    h_need="สิ่งที่ต้องมี",
    h_create="สร้างข้อมูลรับรองที่ {name}",
    h_connect="เชื่อมต่อในหน้าบัญชี",
    h_modes="แต่ละโหมดทำอะไรกับ {name}",
    h_notes="ข้อควรรู้ของกระดานเทรดนี้",
    h_trouble="การแก้ปัญหา",
    f_key="คีย์ API", f_secret="ความลับ API", f_pass="พาสเฟรส API (ตั้งเองตอนสร้างคีย์)",
    f_gwurl="URL ของ Client Portal Gateway", f_acct="รหัสบัญชี IBKR",
    warn_keys="ให้สิทธิ์เฉพาะการเทรด (TRADE) เท่านั้น — ห้ามให้สิทธิ์ถอนเงินเด็ดขาด ใช้รายการอนุญาต IP หากกระดานมีให้ เริ่มจากเงินจำนวนน้อย คีย์ของคุณถูกเข้ารหัส (AES-GCM) บนเซิร์ฟเวอร์ Sooppiy และจะไม่แสดงอีกหลังบันทึก",
    connect_steps=[
        "เปิด <b>บัญชี</b> → <b>เกตเวย์การเทรด</b>",
        "เลือกภูมิภาค (มีผลแค่การจัดเรียงแนะนำ — ทุกโบรกเกอร์ยังเชื่อมต่อได้) แล้วเลือก <b>{name}</b>",
        "วางข้อมูลรับรองจากขั้นตอนที่ 2",
        "อ่านและยอมรับข้อกำหนดการเทรดจริง — จำเป็นแม้ตั้งใจใช้แค่ shadow",
        "กด <b>เชื่อมต่อเกตเวย์</b> บัญชีจะเริ่มในโหมด <b>paper</b> — ยังไม่ส่งอะไรไปที่ {name}",
        "สลับบัญชีเป็น <b>shadow</b> (แนะนำให้ทำก่อน) หรือ <b>live</b> ที่การ์ดบัญชี",
    ],
    mode_th=["โหมด", "สิ่งที่เกิดขึ้น"],
    mode_sim="<b>paper / จำลอง</b> — ทุกการเทรดอยู่ในบัญชีภายในของ Sooppiy เท่านั้น ไม่ติดต่อ {name} เลย",
    mode_live_live="<b>live</b> — คำสั่งจริงถูกส่งไปยังบัญชี {name} ของคุณ โบรกเกอร์คือแหล่งความจริง: คำสั่งที่ถูกปฏิเสธจะไม่สร้างสถานะบนแพลตฟอร์ม ต้องยอมรับข้อกำหนดและมีข้อมูลรับรองที่ใช้ได้ การปฏิเสธจะแสดงชัดเจนเสมอ ไม่มีการแอบเปลี่ยนเป็นการจำลอง",
    mode_live_gated="<b>live</b> — {name} ยังไม่เปิดเทรดจริง: กระดานนี้อยู่ระหว่างช่วงทดสอบ shadow และคำสั่งจริงจะถูกปฏิเสธพร้อมข้อความชัดเจนจนกว่า Sooppiy จะเปิดใช้งาน ระหว่างนี้กฎของคุณรันแบบ shadow ได้ กระดานที่เพิ่งเปิดใหม่มีเพดานคำสั่งละ $1,000 ในช่วงแรก (คำสั่งเกินเพดานถูกปฏิเสธ ไม่ถูกลดขนาด)",
    trouble_th=["อาการ", "ความหมาย / วิธีแก้"],
    t_creds=("“credentials are missing or cannot be decrypted”",
             "คีย์ที่บันทึกไว้อ่านไม่ได้แล้ว (เช่นหลังการหมุนเวียนคีย์เซิร์ฟเวอร์) — เชื่อมต่อโบรกเกอร์ใหม่ด้วยข้อมูลรับรองใหม่"),
    t_tcs=("“live-trading terms have not been accepted”",
           "ยอมรับข้อกำหนดของโบรกเกอร์นี้ในหน้าบัญชี — การยินยอมบันทึกแยกต่อโบรกเกอร์"),
    t_allow=("“not yet enabled for live orders on this platform”",
             "กระดานนี้ยังอยู่ในช่วงทดสอบ shadow ตอนนี้ shadow ใช้ได้ และเทรดจริงจะเปิดเมื่อการทดสอบเสร็จ"),
    drift_note="ไม่ว่าโหมดใด แผง <b>คำสั่งโบรกเกอร์</b> และ <b>บันทึกดริฟต์</b> ด้านล่างหน้าบัญชีจะแสดงสิ่งที่ {name} ยืนยันจริงคู่กับสิ่งที่บัญชีภายในสันนิษฐาน — ความต่างจะถูกแสดงชัดเจน ไม่ถูกแก้อัตโนมัติ",
),
"vi": dict(
    kicker="TÀI LIỆU SOOPPIY — KẾT NỐI CỔNG GIAO DỊCH",
    subtitle="Cách tạo thông tin xác thực API tại {name} và kết nối trên trang Tài khoản.",
    badge_live="đã mở giao dịch thật",
    badge_gated="shadow trước — giao dịch thật đang mở dần",
    h_need="Bạn cần gì",
    h_create="Tạo thông tin xác thực tại {name}",
    h_connect="Kết nối trên trang Tài khoản",
    h_modes="Mỗi chế độ làm gì với {name}",
    h_notes="Lưu ý riêng của sàn",
    h_trouble="Xử lý sự cố",
    f_key="Khóa API", f_secret="Bí mật API", f_pass="Passphrase API (tự đặt khi tạo khóa)",
    f_gwurl="URL Client Portal Gateway", f_acct="Mã tài khoản IBKR",
    warn_keys="Chỉ cấp quyền GIAO DỊCH (TRADE) — tuyệt đối không cấp quyền rút tiền. Dùng danh sách IP cho phép nếu sàn hỗ trợ. Bắt đầu với số tiền nhỏ. Khóa của bạn được mã hóa (AES-GCM) trên máy chủ Sooppiy và không hiển thị lại sau khi lưu.",
    connect_steps=[
        "Mở <b>Tài khoản</b> → <b>Cổng giao dịch</b>.",
        "Chọn khu vực (chỉ ảnh hưởng thứ tự đề xuất — mọi broker vẫn kết nối được) rồi chọn <b>{name}</b>.",
        "Dán thông tin xác thực từ bước 2.",
        "Đọc và chấp nhận điều khoản giao dịch thật — bắt buộc kể cả khi chỉ định dùng shadow.",
        "Nhấn <b>Kết nối cổng</b>. Tài khoản bắt đầu ở chế độ <b>paper</b>: chưa có gì gửi tới {name}.",
        "Chuyển tài khoản sang <b>shadow</b> (nên làm trước) hoặc <b>live</b> trên thẻ tài khoản.",
    ],
    mode_th=["Chế độ", "Điều gì xảy ra"],
    mode_sim="<b>paper / mô phỏng</b> — mọi giao dịch chỉ nằm trong sổ nội bộ của Sooppiy. Không hề liên hệ {name}.",
    mode_live_live="<b>live</b> — lệnh thật được gửi tới tài khoản {name} của bạn. Broker là nguồn chân lý: lệnh bị từ chối không tạo vị thế trên nền tảng. Cần chấp nhận điều khoản và thông tin xác thực hợp lệ; mọi từ chối đều hiển thị rõ, không bao giờ âm thầm chuyển thành mô phỏng.",
    mode_live_gated="<b>live</b> — {name} chưa mở giao dịch thật: sàn đang trong giai đoạn kiểm chứng shadow, lệnh thật bị từ chối kèm thông báo rõ ràng cho tới khi Sooppiy kích hoạt. Trong lúc đó quy tắc của bạn vẫn chạy shadow được. Sàn mới mở ban đầu có giới hạn $1,000 mỗi lệnh (lệnh vượt hạn bị từ chối, không bị thu nhỏ).",
    trouble_th=["Triệu chứng", "Ý nghĩa / cách xử lý"],
    t_creds=("“credentials are missing or cannot be decrypted”",
             "Khóa đã lưu không còn đọc được (ví dụ sau khi xoay khóa máy chủ). Kết nối lại broker với thông tin mới."),
    t_tcs=("“live-trading terms have not been accepted”",
           "Chấp nhận điều khoản của broker này trên trang Tài khoản — sự đồng ý được ghi riêng từng broker."),
    t_allow=("“not yet enabled for live orders on this platform”",
             "Sàn vẫn đang kiểm chứng shadow. Shadow dùng được ngay; giao dịch thật mở khi kiểm chứng xong."),
    drift_note="Dù ở chế độ nào, hai bảng <b>Lệnh tại broker</b> và <b>Bản ghi lệch</b> cuối trang Tài khoản luôn đặt số liệu {name} xác nhận cạnh giả định của sổ nội bộ — khác biệt được phơi bày rõ, không bao giờ tự sửa.",
),
"id": dict(
    kicker="DOKUMEN SOOPPIY — MENGHUBUNGKAN GATEWAY TRADING",
    subtitle="Cara membuat kredensial API di {name} dan menghubungkannya di halaman Akun.",
    badge_live="trading live tersedia",
    badge_gated="shadow dulu — trading live dibuka bertahap",
    h_need="Yang Anda butuhkan",
    h_create="Buat kredensial di {name}",
    h_connect="Hubungkan di halaman Akun",
    h_modes="Apa yang dilakukan tiap mode dengan {name}",
    h_notes="Catatan khusus bursa",
    h_trouble="Pemecahan masalah",
    f_key="Kunci API", f_secret="Secret API", f_pass="Passphrase API (Anda tetapkan saat membuat kunci)",
    f_gwurl="URL Client Portal Gateway", f_acct="ID akun IBKR",
    warn_keys="Berikan izin TRADE saja — jangan pernah izin penarikan dana. Gunakan daftar IP yang diizinkan bila bursa menyediakannya. Mulailah dari nominal kecil. Kunci Anda dienkripsi (AES-GCM) di server Sooppiy dan tidak akan ditampilkan lagi setelah disimpan.",
    connect_steps=[
        "Buka <b>Akun</b> → <b>Gateway trading</b>.",
        "Pilih wilayah (hanya memengaruhi urutan rekomendasi — semua broker tetap bisa dihubungkan) lalu pilih <b>{name}</b>.",
        "Tempel kredensial dari langkah 2.",
        "Baca dan terima ketentuan trading live — wajib meskipun Anda hanya berencana memakai shadow.",
        "Tekan <b>Hubungkan gateway</b>. Akun dimulai dalam mode <b>paper</b>: belum ada yang dikirim ke {name}.",
        "Alihkan akun ke <b>shadow</b> (disarankan lebih dulu) atau <b>live</b> pada kartu akun.",
    ],
    mode_th=["Mode", "Yang terjadi"],
    mode_sim="<b>paper / simulator</b> — semua transaksi hanya tercatat di buku internal Sooppiy. {name} tidak pernah dihubungi.",
    mode_live_live="<b>live</b> — order sungguhan dikirim ke akun {name} Anda. Broker adalah sumber kebenaran: order yang ditolak tidak pernah membuat posisi di platform. Perlu ketentuan yang sudah diterima dan kredensial yang valid; penolakan selalu eksplisit, tidak pernah diam-diam menjadi simulasi.",
    mode_live_gated="<b>live</b> — belum dibuka untuk {name}: bursa ini masih dalam masa uji shadow, dan order live ditolak dengan pesan eksplisit sampai Sooppiy mengaktifkannya. Sementara itu aturan Anda tetap bisa berjalan di shadow. Bursa yang baru diaktifkan juga membawa batas $1.000 per order pada awalnya (order yang melebihi batas ditolak, bukan diperkecil).",
    trouble_th=["Gejala", "Arti / tindakan"],
    t_creds=("“credentials are missing or cannot be decrypted”",
             "Kunci tersimpan tidak lagi bisa dibaca (mis. setelah rotasi kunci server). Hubungkan ulang broker dengan kredensial baru."),
    t_tcs=("“live-trading terms have not been accepted”",
           "Terima ketentuan untuk broker ini di halaman Akun — persetujuan dicatat per broker."),
    t_allow=("“not yet enabled for live orders on this platform”",
             "Bursa masih dalam masa uji shadow. Shadow sudah berfungsi; live dibuka setelah masa uji selesai."),
    drift_note="Apa pun modenya, panel <b>Order broker</b> dan <b>Catatan penyimpangan</b> di bagian bawah halaman Akun menampilkan apa yang benar-benar dikonfirmasi {name} di samping asumsi buku internal — perbedaan ditampilkan mencolok, tidak pernah dikoreksi otomatis.",
),
}

# ── per-broker content ───────────────────────────────────────────────────────
# fields: which credential rows to show (key/secret/pass/gwurl/acct)
# steps:  where and how to create the key at the venue
# shadow: what shadow mode really does on THIS venue (must match BROKER_SPECS)
# notes:  venue quirks worth knowing
# trouble: extra venue-specific troubleshooting rows (symptom stays verbatim)

B = {
"binance": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at binance.com → profile icon → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (system-generated).",
               "Enable <b>Reading</b> and <b>Spot &amp; Margin Trading</b>. Leave withdrawals disabled.",
               "Add Sooppiy's server IP to the key's IP access restriction if you use one (recommended)."],
        "ko": ["binance.com 로그인 → 프로필 아이콘 → <b>Account</b> → <b>API Management</b> → <b>Create API</b>(시스템 생성).",
               "<b>Reading</b>과 <b>Spot &amp; Margin Trading</b>을 활성화하세요. 출금은 비활성 상태로 두세요.",
               "IP 접근 제한을 쓴다면 Sooppiy 서버 IP를 등록하세요(권장)."],
        "ja": ["binance.comにログイン → プロフィール → <b>Account</b> → <b>API Management</b> → <b>Create API</b>(システム生成)。",
               "<b>Reading</b>と<b>Spot &amp; Margin Trading</b>を有効化。出金は無効のままにします。",
               "IPアクセス制限を使う場合はSooppiyサーバーのIPを登録してください(推奨)。"],
        "th": ["เข้าสู่ระบบ binance.com → ไอคอนโปรไฟล์ → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (แบบ system-generated)",
               "เปิดใช้ <b>Reading</b> และ <b>Spot &amp; Margin Trading</b> ปล่อยการถอนเงินให้ปิดไว้",
               "หากใช้การจำกัด IP ให้เพิ่ม IP เซิร์ฟเวอร์ของ Sooppiy (แนะนำ)"],
        "vi": ["Đăng nhập binance.com → biểu tượng hồ sơ → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (system-generated).",
               "Bật <b>Reading</b> và <b>Spot &amp; Margin Trading</b>. Giữ quyền rút tiền ở trạng thái tắt.",
               "Nếu dùng giới hạn IP, thêm IP máy chủ của Sooppiy (khuyến nghị)."],
        "id": ["Masuk ke binance.com → ikon profil → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (system-generated).",
               "Aktifkan <b>Reading</b> dan <b>Spot &amp; Margin Trading</b>. Biarkan penarikan dana nonaktif.",
               "Jika memakai pembatasan IP, tambahkan IP server Sooppiy (disarankan)."],
    },
    "shadow": {
        "en": "<b>shadow</b> — your rule's fills stay simulated, and the same order is ALSO sent to the Binance Spot <b>Testnet</b> (testnet.binance.vision) for comparison; the drift is journalled. Note: the testnet has its own separate keys — create a testnet key there if you want shadow comparison fills, and switch to your real keys before going live.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고, 같은 주문이 비교용으로 바이낸스 스팟 <b>테스트넷</b>(testnet.binance.vision)에도 전송되며 차이가 기록됩니다. 참고: 테스트넷 키는 별도입니다 — 섀도 비교 체결을 원하면 테스트넷에서 키를 만들고, 실거래 전환 전에 실계정 키로 바꾸세요.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文が比較用にBinance Spot<b>テストネット</b>(testnet.binance.vision)にも送信され、差異が記録されます。注意: テストネットのキーは別物です — シャドー比較をしたい場合はテストネットでキーを作成し、実取引前に本番キーへ切り替えてください。",
        "th": "<b>shadow</b> — การจับคู่ของกฎยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยัง Binance Spot <b>Testnet</b> (testnet.binance.vision) เพื่อเปรียบเทียบ พร้อมบันทึกความต่าง หมายเหตุ: testnet ใช้คีย์แยกต่างหาก — สร้างคีย์ testnet หากต้องการการเปรียบเทียบ และสลับเป็นคีย์จริงก่อนเปิด live",
        "vi": "<b>shadow</b> — khớp lệnh của quy tắc vẫn là mô phỏng, đồng thời lệnh đó được gửi tới Binance Spot <b>Testnet</b> (testnet.binance.vision) để so sánh; chênh lệch được ghi lại. Lưu ý: testnet có khóa riêng — hãy tạo khóa testnet nếu muốn so khớp shadow, và chuyển sang khóa thật trước khi lên live.",
        "id": "<b>shadow</b> — eksekusi aturan tetap simulasi, dan order yang sama JUGA dikirim ke Binance Spot <b>Testnet</b> (testnet.binance.vision) untuk perbandingan; selisihnya dicatat. Catatan: testnet memakai kunci terpisah — buat kunci testnet bila ingin perbandingan shadow, lalu ganti ke kunci asli sebelum live.",
    },
    "notes": {
        "en": ["Spot only, USDT-quoted pairs (BTCUSDT and friends).",
               "Regional Binance entities (e.g. Binance TH) have separate accounts and API domains — support for their endpoints is planned."],
        "ko": ["스팟 전용, USDT 호가 페어(BTCUSDT 등).",
               "지역 바이낸스 법인(예: Binance TH)은 계정과 API 도메인이 별도입니다 — 해당 엔드포인트 지원은 예정되어 있습니다."],
        "ja": ["スポットのみ、USDT建てペア(BTCUSDTなど)。",
               "地域法人(Binance THなど)は口座とAPIドメインが別です — 対応は計画中です。"],
        "th": ["เฉพาะ Spot คู่ที่อ้างอิง USDT (เช่น BTCUSDT)",
               "Binance ประจำภูมิภาค (เช่น Binance TH) มีบัญชีและโดเมน API แยก — การรองรับ endpoint เหล่านั้นอยู่ในแผน"],
        "vi": ["Chỉ Spot, các cặp định giá USDT (BTCUSDT, v.v.).",
               "Các pháp nhân Binance khu vực (như Binance TH) có tài khoản và tên miền API riêng — hỗ trợ các endpoint đó đã nằm trong kế hoạch."],
        "id": ["Spot saja, pasangan berbasis USDT (BTCUSDT dkk.).",
               "Entitas Binance regional (mis. Binance TH) punya akun dan domain API terpisah — dukungan endpoint tersebut sudah direncanakan."],
    },
    "trouble": {
        "en": [("“Invalid API-key, IP, or permissions for action” (-2015)",
                "The key's IP restriction does not include the calling server, or Spot trading permission is missing. Re-check both on Binance's API Management page.")],
        "ko": [("“Invalid API-key, IP, or permissions for action” (-2015)",
                "키의 IP 제한에 호출 서버가 없거나 스팟 거래 권한이 빠져 있습니다. 바이낸스 API Management에서 둘 다 다시 확인하세요.")],
        "ja": [("“Invalid API-key, IP, or permissions for action” (-2015)",
                "キーのIP制限に呼び出し元サーバーが含まれていないか、スポット取引権限がありません。BinanceのAPI Managementで両方を再確認してください。")],
        "th": [("“Invalid API-key, IP, or permissions for action” (-2015)",
                "การจำกัด IP ของคีย์ไม่ครอบคลุมเซิร์ฟเวอร์ที่เรียก หรือขาดสิทธิ์เทรด Spot — ตรวจทั้งสองอย่างในหน้า API Management ของ Binance")],
        "vi": [("“Invalid API-key, IP, or permissions for action” (-2015)",
                "Giới hạn IP của khóa không bao gồm máy chủ gọi, hoặc thiếu quyền giao dịch Spot. Kiểm tra lại cả hai trong API Management của Binance.")],
        "id": [("“Invalid API-key, IP, or permissions for action” (-2015)",
                "Pembatasan IP kunci tidak mencakup server pemanggil, atau izin trading Spot belum ada. Periksa keduanya di halaman API Management Binance.")],
    },
},
"alpaca": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at app.alpaca.markets and open the dashboard for the account you want to connect.",
               "Generate the key pair from <b>API Keys</b> on the right-hand panel. The secret is shown once.",
               "Paper and live are separate accounts with separate keys: paper keys only work against the paper environment, live keys only against live. Use paper keys while you run shadow; replace them with live keys when you go live."],
        "ko": ["app.alpaca.markets에 로그인해 연결할 계정의 대시보드를 엽니다.",
               "우측 패널의 <b>API Keys</b>에서 키 쌍을 생성합니다. 시크릿은 한 번만 표시됩니다.",
               "페이퍼와 라이브는 계정도 키도 별개입니다: 페이퍼 키는 페이퍼 환경에서만, 라이브 키는 라이브에서만 동작합니다. 섀도 운용 중에는 페이퍼 키를 쓰고, 실거래 전환 시 라이브 키로 교체하세요."],
        "ja": ["app.alpaca.marketsにログインし、接続したい口座のダッシュボードを開きます。",
               "右パネルの<b>API Keys</b>でキーペアを生成します。シークレットは一度だけ表示されます。",
               "ペーパーとライブは口座もキーも別です: ペーパーキーはペーパー環境のみ、ライブキーはライブのみで動作します。シャドー運用中はペーパーキー、実取引時にライブキーへ差し替えてください。"],
        "th": ["เข้าสู่ระบบ app.alpaca.markets แล้วเปิดแดชบอร์ดของบัญชีที่ต้องการเชื่อมต่อ",
               "สร้างคู่คีย์จาก <b>API Keys</b> ที่แผงด้านขวา ความลับจะแสดงเพียงครั้งเดียว",
               "Paper กับ Live เป็นคนละบัญชีและคนละคีย์: คีย์ paper ใช้ได้กับสภาพแวดล้อม paper เท่านั้น ใช้คีย์ paper ระหว่างรัน shadow และเปลี่ยนเป็นคีย์ live เมื่อจะเทรดจริง"],
        "vi": ["Đăng nhập app.alpaca.markets và mở bảng điều khiển của tài khoản muốn kết nối.",
               "Tạo cặp khóa từ <b>API Keys</b> ở bảng bên phải. Bí mật chỉ hiển thị một lần.",
               "Paper và live là hai tài khoản với khóa riêng: khóa paper chỉ chạy với môi trường paper, khóa live chỉ với live. Dùng khóa paper khi chạy shadow; thay bằng khóa live khi lên live."],
        "id": ["Masuk ke app.alpaca.markets dan buka dasbor akun yang ingin dihubungkan.",
               "Buat pasangan kunci dari <b>API Keys</b> di panel kanan. Secret hanya ditampilkan sekali.",
               "Paper dan live adalah akun terpisah dengan kunci terpisah: kunci paper hanya bekerja di lingkungan paper, kunci live hanya di live. Pakai kunci paper selama shadow; ganti ke kunci live saat akan live."],
    },
    "shadow": {
        "en": "<b>shadow</b> — fills stay simulated and the same order is ALSO sent to Alpaca's <b>paper trading</b> environment for comparison; the drift is journalled. This needs paper-account keys.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고 같은 주문이 비교용으로 알파카 <b>페이퍼 트레이딩</b> 환경에도 전송되며 차이가 기록됩니다. 페이퍼 계정 키가 필요합니다.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文が比較用にAlpacaの<b>ペーパートレーディング</b>環境にも送信され、差異が記録されます。ペーパー口座のキーが必要です。",
        "th": "<b>shadow</b> — การจับคู่ยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยังสภาพแวดล้อม <b>paper trading</b> ของ Alpaca เพื่อเปรียบเทียบ พร้อมบันทึกความต่าง ต้องใช้คีย์ของบัญชี paper",
        "vi": "<b>shadow</b> — khớp lệnh vẫn là mô phỏng và lệnh đó được gửi tới môi trường <b>paper trading</b> của Alpaca để so sánh; chênh lệch được ghi lại. Cần khóa tài khoản paper.",
        "id": "<b>shadow</b> — eksekusi tetap simulasi dan order yang sama dikirim ke lingkungan <b>paper trading</b> Alpaca untuk perbandingan; selisihnya dicatat. Ini membutuhkan kunci akun paper.",
    },
    "notes": {
        "en": ["US stocks and ETFs; orders route during US market sessions.",
               "Alpaca availability depends on your country of residence — check Alpaca's own supported-country list when opening the account."],
        "ko": ["미국 주식·ETF 전용이며 주문은 미국장 시간에 처리됩니다.",
               "알파카 가입 가능 여부는 거주 국가에 따라 다릅니다 — 계좌 개설 시 알파카의 지원 국가 목록을 확인하세요."],
        "ja": ["米国株・ETF専用で、注文は米国市場の時間帯に処理されます。",
               "Alpacaの利用可否は居住国によります — 口座開設時にAlpacaの対応国リストを確認してください。"],
        "th": ["เฉพาะหุ้นและ ETF สหรัฐฯ คำสั่งดำเนินการช่วงตลาดสหรัฐฯ เปิด",
               "การเปิดบัญชี Alpaca ขึ้นกับประเทศที่พำนัก — ตรวจรายชื่อประเทศที่รองรับของ Alpaca ตอนสมัคร"],
        "vi": ["Chỉ cổ phiếu và ETF Mỹ; lệnh xử lý trong phiên thị trường Mỹ.",
               "Khả năng mở Alpaca phụ thuộc quốc gia cư trú — xem danh sách quốc gia được hỗ trợ của Alpaca khi mở tài khoản."],
        "id": ["Saham dan ETF AS; order diproses selama sesi pasar AS.",
               "Ketersediaan Alpaca bergantung negara domisili — cek daftar negara yang didukung Alpaca saat membuka akun."],
    },
    "trouble": {
        "en": [("“forbidden” / 403 on every order",
                "Almost always paper keys against the live environment or the reverse. Match the key pair to the mode you are in.")],
        "ko": [("모든 주문에서 “forbidden” / 403",
                "대부분 페이퍼 키를 라이브 환경에(또는 그 반대로) 쓴 경우입니다. 현재 모드에 맞는 키 쌍인지 확인하세요.")],
        "ja": [("すべての注文で “forbidden” / 403",
                "ほぼ確実にペーパーキーをライブ環境で(またはその逆で)使っています。モードに合ったキーペアか確認してください。")],
        "th": [("“forbidden” / 403 กับทุกคำสั่ง",
                "แทบทุกครั้งคือใช้คีย์ paper กับสภาพแวดล้อม live หรือกลับกัน — จับคู่คีย์ให้ตรงกับโหมดที่ใช้อยู่")],
        "vi": [("“forbidden” / 403 với mọi lệnh",
                "Hầu như luôn là khóa paper dùng cho môi trường live hoặc ngược lại. Khớp cặp khóa với chế độ đang dùng.")],
        "id": [("“forbidden” / 403 pada semua order",
                "Hampir selalu kunci paper dipakai di lingkungan live atau sebaliknya. Cocokkan pasangan kunci dengan mode yang dipakai.")],
    },
},
"ibkr": {
    "fields": ["gwurl", "acct"],
    "steps": {
        "en": ["IBKR has no API key/secret here — the <b>Client Portal Gateway</b> session IS the credential. Download it from IBKR's website and run it on a machine Sooppiy's server can reach.",
               "Log in to the gateway in your browser (usually https://localhost:5000) with your IBKR username.",
               "Note your account id (e.g. <code>DU1234567</code>). Ids starting with <b>D</b> are paper accounts — shadow only works on a paper account."],
        "ko": ["IBKR은 API 키/시크릿을 쓰지 않습니다 — <b>Client Portal Gateway</b> 세션 자체가 자격 증명입니다. IBKR 웹사이트에서 내려받아 Sooppiy 서버가 접근 가능한 곳에서 실행하세요.",
               "브라우저에서 게이트웨이(보통 https://localhost:5000)에 IBKR 계정으로 로그인합니다.",
               "계좌 번호(예: <code>DU1234567</code>)를 확인하세요. <b>D</b>로 시작하면 모의 계좌이며, 섀도는 모의 계좌에서만 동작합니다."],
        "ja": ["IBKRはAPIキー/シークレットを使いません — <b>Client Portal Gateway</b>のセッションそのものが資格情報です。IBKRサイトからダウンロードし、Sooppiyサーバーから到達できる場所で実行してください。",
               "ブラウザでゲートウェイ(通常 https://localhost:5000)にIBKRアカウントでログインします。",
               "口座番号(例: <code>DU1234567</code>)を控えてください。<b>D</b>で始まる口座はペーパー口座で、シャドーはペーパー口座でのみ動作します。"],
        "th": ["IBKR ไม่ใช้คีย์/ความลับ API — เซสชันของ <b>Client Portal Gateway</b> คือข้อมูลรับรอง ดาวน์โหลดจากเว็บ IBKR แล้วรันบนเครื่องที่เซิร์ฟเวอร์ Sooppiy เข้าถึงได้",
               "ล็อกอินเข้าเกตเวย์ในเบราว์เซอร์ (ปกติ https://localhost:5000) ด้วยบัญชี IBKR",
               "จดรหัสบัญชี (เช่น <code>DU1234567</code>) รหัสที่ขึ้นต้นด้วย <b>D</b> คือบัญชี paper — shadow ทำงานกับบัญชี paper เท่านั้น"],
        "vi": ["IBKR không dùng khóa/bí mật API ở đây — phiên của <b>Client Portal Gateway</b> chính là thông tin xác thực. Tải từ trang IBKR và chạy trên máy mà máy chủ Sooppiy truy cập được.",
               "Đăng nhập gateway trong trình duyệt (thường là https://localhost:5000) bằng tài khoản IBKR.",
               "Ghi lại mã tài khoản (vd: <code>DU1234567</code>). Mã bắt đầu bằng <b>D</b> là tài khoản paper — shadow chỉ hoạt động trên tài khoản paper."],
        "id": ["IBKR tidak memakai kunci/secret API di sini — sesi <b>Client Portal Gateway</b> itulah kredensialnya. Unduh dari situs IBKR dan jalankan di mesin yang bisa dijangkau server Sooppiy.",
               "Masuk ke gateway lewat browser (biasanya https://localhost:5000) dengan akun IBKR Anda.",
               "Catat ID akun (mis. <code>DU1234567</code>). ID berawalan <b>D</b> adalah akun paper — shadow hanya bekerja pada akun paper."],
    },
    "shadow": {
        "en": "<b>shadow</b> — fills stay simulated and the same order is ALSO sent to your IBKR <b>paper account</b> through the gateway; the drift is journalled.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고 같은 주문이 게이트웨이를 통해 IBKR <b>모의 계좌</b>에도 전송되며 차이가 기록됩니다.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文がゲートウェイ経由でIBKRの<b>ペーパー口座</b>にも送信され、差異が記録されます。",
        "th": "<b>shadow</b> — การจับคู่ยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยัง<b>บัญชี paper</b> ของ IBKR ผ่านเกตเวย์ พร้อมบันทึกความต่าง",
        "vi": "<b>shadow</b> — khớp lệnh vẫn là mô phỏng và lệnh đó được gửi tới <b>tài khoản paper</b> IBKR của bạn qua gateway; chênh lệch được ghi lại.",
        "id": "<b>shadow</b> — eksekusi tetap simulasi dan order yang sama dikirim ke <b>akun paper</b> IBKR Anda melalui gateway; selisihnya dicatat.",
    },
    "notes": {
        "en": ["The gateway session expires after idle minutes. Sooppiy tickles it automatically and alerts you when it lapses — the health banner on the Accounts page shows the current state.",
               "Only tick “self-signed certificate” for a gateway on your own machine or private network."],
        "ko": ["게이트웨이 세션은 몇 분만 유휴 상태여도 만료됩니다. Sooppiy가 자동으로 세션을 유지하고 끊기면 알림을 보내며, 계정 페이지 상단 배너에서 현재 상태를 볼 수 있습니다.",
               "“자체 서명 인증서” 체크는 본인 기기나 사설망의 게이트웨이에만 사용하세요."],
        "ja": ["ゲートウェイのセッションは数分のアイドルで失効します。Sooppiyが自動で維持し、切れたら通知します — アカウントページのバナーで現在の状態を確認できます。",
               "「自己署名証明書」は自分のマシンやプライベートネットワーク上のゲートウェイにのみ使用してください。"],
        "th": ["เซสชันเกตเวย์หมดอายุหลังว่างไม่กี่นาที Sooppiy ต่ออายุให้อัตโนมัติและแจ้งเตือนเมื่อหลุด — แบนเนอร์สุขภาพในหน้าบัญชีแสดงสถานะปัจจุบัน",
               "ติ๊ก “ใบรับรอง self-signed” เฉพาะเกตเวย์บนเครื่องของคุณเองหรือเครือข่ายส่วนตัวเท่านั้น"],
        "vi": ["Phiên gateway hết hạn sau vài phút không hoạt động. Sooppiy tự duy trì và cảnh báo khi phiên rớt — banner sức khỏe trên trang Tài khoản cho biết trạng thái hiện tại.",
               "Chỉ tích “chứng chỉ tự ký” cho gateway trên máy của bạn hoặc mạng riêng."],
        "id": ["Sesi gateway kedaluwarsa setelah beberapa menit idle. Sooppiy menjaganya otomatis dan memberi tahu saat terputus — banner kesehatan di halaman Akun menunjukkan status terkini.",
               "Centang “sertifikat self-signed” hanya untuk gateway di mesin sendiri atau jaringan privat."],
    },
    "trouble": {
        "en": [("“gateway session is not authenticated”",
                "Open the Client Portal Gateway in your browser and log in again — the session lapsed beyond what the keepalive could revive.")],
        "ko": [("“gateway session is not authenticated”",
                "브라우저에서 Client Portal Gateway를 열어 다시 로그인하세요 — 자동 유지로 살릴 수 없을 만큼 세션이 만료된 상태입니다.")],
        "ja": [("“gateway session is not authenticated”",
                "ブラウザでClient Portal Gatewayを開き再ログインしてください — キープアライブで復旧できないほどセッションが失効しています。")],
        "th": [("“gateway session is not authenticated”",
                "เปิด Client Portal Gateway ในเบราว์เซอร์แล้วล็อกอินใหม่ — เซสชันหลุดเกินกว่าระบบต่ออายุจะกู้ได้")],
        "vi": [("“gateway session is not authenticated”",
                "Mở Client Portal Gateway trong trình duyệt và đăng nhập lại — phiên đã rớt quá mức keepalive có thể khôi phục.")],
        "id": [("“gateway session is not authenticated”",
                "Buka Client Portal Gateway di browser dan masuk lagi — sesi terputus melebihi yang bisa dipulihkan keepalive.")],
    },
},
"bybit": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at bybit.com → profile icon → <b>API</b> → <b>Create New Key</b> → System-generated API Keys.",
               "Permissions: <b>Read-Write</b> with <b>Unified Trading — Trade</b>. Leave withdrawals off.",
               "For shadow comparison, Bybit's <b>demo trading</b> environment has its own keys — create one while switched into demo trading mode."],
        "ko": ["bybit.com 로그인 → 프로필 아이콘 → <b>API</b> → <b>Create New Key</b> → 시스템 생성 키.",
               "권한: <b>Read-Write</b> + <b>Unified Trading — Trade</b>. 출금은 끄세요.",
               "섀도 비교용으로 바이비트 <b>데모 트레이딩</b> 환경은 키가 별도입니다 — 데모 모드로 전환한 상태에서 만드세요."],
        "ja": ["bybit.comにログイン → プロフィール → <b>API</b> → <b>Create New Key</b> → システム生成キー。",
               "権限: <b>Read-Write</b> + <b>Unified Trading — Trade</b>。出金はオフのまま。",
               "シャドー比較用のBybit<b>デモトレード</b>環境はキーが別です — デモモードに切り替えた状態で作成してください。"],
        "th": ["เข้าสู่ระบบ bybit.com → ไอคอนโปรไฟล์ → <b>API</b> → <b>Create New Key</b> → คีย์แบบ system-generated",
               "สิทธิ์: <b>Read-Write</b> พร้อม <b>Unified Trading — Trade</b> ปิดการถอนเงินไว้",
               "สำหรับเปรียบเทียบ shadow สภาพแวดล้อม <b>demo trading</b> ของ Bybit ใช้คีย์แยก — สร้างขณะสลับอยู่ในโหมดเดโม"],
        "vi": ["Đăng nhập bybit.com → biểu tượng hồ sơ → <b>API</b> → <b>Create New Key</b> → khóa system-generated.",
               "Quyền: <b>Read-Write</b> với <b>Unified Trading — Trade</b>. Tắt quyền rút tiền.",
               "Để so khớp shadow, môi trường <b>demo trading</b> của Bybit có khóa riêng — tạo khi đang chuyển sang chế độ demo."],
        "id": ["Masuk ke bybit.com → ikon profil → <b>API</b> → <b>Create New Key</b> → kunci system-generated.",
               "Izin: <b>Read-Write</b> dengan <b>Unified Trading — Trade</b>. Biarkan penarikan nonaktif.",
               "Untuk perbandingan shadow, lingkungan <b>demo trading</b> Bybit punya kunci sendiri — buat saat berada dalam mode demo."],
    },
    "shadow": {
        "en": "<b>shadow</b> — fills stay simulated and the same order is ALSO sent to Bybit's <b>demo trading</b> environment for comparison; the drift is journalled. Demo keys are separate from real ones.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고 같은 주문이 바이비트 <b>데모 트레이딩</b> 환경에도 전송되며 차이가 기록됩니다. 데모 키는 실계정 키와 별개입니다.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文がBybitの<b>デモトレード</b>環境にも送信され、差異が記録されます。デモキーは本番キーと別物です。",
        "th": "<b>shadow</b> — การจับคู่ยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยังสภาพแวดล้อม <b>demo trading</b> ของ Bybit เพื่อเปรียบเทียบ พร้อมบันทึกความต่าง คีย์เดโมแยกจากคีย์จริง",
        "vi": "<b>shadow</b> — khớp lệnh vẫn là mô phỏng và lệnh đó được gửi tới môi trường <b>demo trading</b> của Bybit để so sánh; chênh lệch được ghi lại. Khóa demo tách biệt khóa thật.",
        "id": "<b>shadow</b> — eksekusi tetap simulasi dan order yang sama dikirim ke lingkungan <b>demo trading</b> Bybit untuk perbandingan; selisihnya dicatat. Kunci demo terpisah dari kunci asli.",
    },
    "notes": {
        "en": ["Spot only for now, USDT pairs, under Bybit's Unified Trading Account.",
               "Sooppiy pins market buys to base-coin sizing — the amount you configure is coins, never a USDT spend."],
        "ko": ["현재는 스팟 전용, USDT 페어, 바이비트 통합거래계좌(UTA) 기준입니다.",
               "Sooppiy는 시장가 매수를 기초자산 수량 기준으로 고정합니다 — 설정한 수량은 코인 개수이며 USDT 지출액이 아닙니다."],
        "ja": ["現在はスポットのみ、USDTペア、Bybit統合取引口座(UTA)が対象です。",
               "Sooppiyは成行買いを基軸通貨数量に固定します — 設定する数量はコイン数であり、USDT支出額ではありません。"],
        "th": ["ตอนนี้เฉพาะ Spot คู่ USDT ภายใต้บัญชี Unified Trading ของ Bybit",
               "Sooppiy ตรึงการซื้อแบบ market เป็นจำนวนเหรียญฐานเสมอ — จำนวนที่ตั้งคือจำนวนเหรียญ ไม่ใช่ยอดใช้จ่าย USDT"],
        "vi": ["Hiện chỉ Spot, cặp USDT, trong Tài khoản Giao dịch Hợp nhất của Bybit.",
               "Sooppiy cố định lệnh mua market theo số lượng coin gốc — con số bạn đặt là coin, không phải số USDT chi ra."],
        "id": ["Saat ini Spot saja, pasangan USDT, di bawah Unified Trading Account Bybit.",
               "Sooppiy mengunci market buy pada ukuran koin dasar — jumlah yang Anda atur adalah koin, bukan belanja USDT."],
    },
    "trouble": {
        "en": [("retCode 10003 / “API key is invalid”",
                "The key was made in the other environment (demo vs real) than the mode you are running, or it expired. Bybit keys without IP restriction expire after 3 months — recreate or bind an IP.")],
        "ko": [("retCode 10003 / “API key is invalid”",
                "실행 중인 모드와 다른 환경(데모 vs 실계정)에서 만든 키이거나 만료된 키입니다. IP 제한 없는 바이비트 키는 3개월 뒤 만료됩니다 — 재발급하거나 IP를 바인딩하세요.")],
        "ja": [("retCode 10003 / “API key is invalid”",
                "実行中のモードと異なる環境(デモvs本番)で作成したキーか、期限切れです。IP制限のないBybitキーは3か月で失効します — 再発行するかIPをバインドしてください。")],
        "th": [("retCode 10003 / “API key is invalid”",
                "คีย์ถูกสร้างในสภาพแวดล้อมตรงข้ามกับโหมดที่รัน (เดโม vs จริง) หรือหมดอายุ — คีย์ Bybit ที่ไม่จำกัด IP หมดอายุใน 3 เดือน สร้างใหม่หรือผูก IP")],
        "vi": [("retCode 10003 / “API key is invalid”",
                "Khóa được tạo ở môi trường khác (demo vs thật) so với chế độ đang chạy, hoặc đã hết hạn. Khóa Bybit không giới hạn IP hết hạn sau 3 tháng — tạo lại hoặc gắn IP.")],
        "id": [("retCode 10003 / “API key is invalid”",
                "Kunci dibuat di lingkungan yang berbeda (demo vs asli) dari mode yang dijalankan, atau kedaluwarsa. Kunci Bybit tanpa pembatasan IP kedaluwarsa setelah 3 bulan — buat ulang atau ikat IP.")],
    },
},
"okx": {
    "fields": ["key", "secret", "pass"],
    "steps": {
        "en": ["Log in at okx.com → profile icon → <b>API keys</b> → <b>Create API key</b>.",
               "You choose the <b>passphrase</b> yourself at creation — OKX signs every request with it, so Sooppiy needs all three values.",
               "Permissions: <b>Trade</b> (plus Read). Never Withdraw.",
               "For shadow comparison, switch OKX into <b>Demo trading</b> mode first and create a demo API key there — demo and real keys are separate."],
        "ko": ["okx.com 로그인 → 프로필 아이콘 → <b>API keys</b> → <b>Create API key</b>.",
               "<b>패스프레이즈</b>는 생성 시 직접 정합니다 — 모든 요청 서명에 쓰이므로 Sooppiy에는 세 값이 모두 필요합니다.",
               "권한: <b>Trade</b>(+ Read). 출금 권한은 절대 부여하지 마세요.",
               "섀도 비교용은 OKX를 <b>데모 트레이딩</b> 모드로 전환한 뒤 데모 API 키를 따로 만드세요 — 데모와 실계정 키는 별개입니다."],
        "ja": ["okx.comにログイン → プロフィール → <b>API keys</b> → <b>Create API key</b>。",
               "<b>パスフレーズ</b>は作成時に自分で決めます — 全リクエストの署名に使うため、Sooppiyには3つの値すべてが必要です。",
               "権限: <b>Trade</b>(+ Read)。出金権限は絶対に付与しないでください。",
               "シャドー比較用はOKXを<b>デモトレード</b>モードに切り替えてからデモAPIキーを作成してください — デモと本番のキーは別物です。"],
        "th": ["เข้าสู่ระบบ okx.com → ไอคอนโปรไฟล์ → <b>API keys</b> → <b>Create API key</b>",
               "คุณตั้ง<b>พาสเฟรส</b>เองตอนสร้าง — OKX ใช้ลงนามทุกคำขอ Sooppiy จึงต้องมีครบทั้งสามค่า",
               "สิทธิ์: <b>Trade</b> (พร้อม Read) ห้าม Withdraw เด็ดขาด",
               "สำหรับเปรียบเทียบ shadow สลับ OKX เป็นโหมด <b>Demo trading</b> ก่อนแล้วสร้างคีย์เดโมแยก — คีย์เดโมกับจริงคนละชุด"],
        "vi": ["Đăng nhập okx.com → biểu tượng hồ sơ → <b>API keys</b> → <b>Create API key</b>.",
               "Bạn tự đặt <b>passphrase</b> khi tạo — OKX ký mọi yêu cầu bằng nó, nên Sooppiy cần đủ cả ba giá trị.",
               "Quyền: <b>Trade</b> (kèm Read). Tuyệt đối không Withdraw.",
               "Để so khớp shadow, chuyển OKX sang chế độ <b>Demo trading</b> trước rồi tạo khóa API demo — khóa demo và thật tách biệt."],
        "id": ["Masuk ke okx.com → ikon profil → <b>API keys</b> → <b>Create API key</b>.",
               "Anda menetapkan <b>passphrase</b> sendiri saat pembuatan — OKX menandatangani setiap permintaan dengannya, jadi Sooppiy butuh ketiga nilai.",
               "Izin: <b>Trade</b> (plus Read). Jangan pernah Withdraw.",
               "Untuk perbandingan shadow, alihkan OKX ke mode <b>Demo trading</b> dulu dan buat kunci API demo — kunci demo dan asli terpisah."],
    },
    "shadow": {
        "en": "<b>shadow</b> — fills stay simulated and the same order is ALSO sent to OKX's <b>demo trading</b> environment (the simulated-trading channel) for comparison; the drift is journalled. Demo keys are separate from real ones.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고 같은 주문이 OKX <b>데모 트레이딩</b>(모의거래 채널)에도 전송되며 차이가 기록됩니다. 데모 키는 실계정 키와 별개입니다.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文がOKXの<b>デモトレード</b>(模擬取引チャネル)にも送信され、差異が記録されます。デモキーは本番キーと別物です。",
        "th": "<b>shadow</b> — การจับคู่ยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยัง <b>demo trading</b> ของ OKX (ช่องทางเทรดจำลอง) เพื่อเปรียบเทียบ พร้อมบันทึกความต่าง คีย์เดโมแยกจากคีย์จริง",
        "vi": "<b>shadow</b> — khớp lệnh vẫn là mô phỏng và lệnh đó được gửi tới môi trường <b>demo trading</b> của OKX (kênh giao dịch mô phỏng) để so sánh; chênh lệch được ghi lại. Khóa demo tách biệt khóa thật.",
        "id": "<b>shadow</b> — eksekusi tetap simulasi dan order yang sama dikirim ke lingkungan <b>demo trading</b> OKX (kanal simulated trading) untuk perbandingan; selisihnya dicatat. Kunci demo terpisah dari kunci asli.",
    },
    "notes": {
        "en": ["Spot only for now, USDT pairs (BTC-USDT style).",
               "Sooppiy pins market buys to base-currency sizing — the configured amount is coins, never a USDT spend."],
        "ko": ["현재는 스팟 전용, USDT 페어(BTC-USDT 형식)입니다.",
               "Sooppiy는 시장가 매수를 기초통화 수량으로 고정합니다 — 설정 수량은 코인 개수이며 USDT 지출액이 아닙니다."],
        "ja": ["現在はスポットのみ、USDTペア(BTC-USDT形式)です。",
               "Sooppiyは成行買いを基軸通貨数量に固定します — 設定数量はコイン数で、USDT支出額ではありません。"],
        "th": ["ตอนนี้เฉพาะ Spot คู่ USDT (รูปแบบ BTC-USDT)",
               "Sooppiy ตรึงการซื้อ market เป็นจำนวนสกุลฐาน — จำนวนที่ตั้งคือเหรียญ ไม่ใช่ยอด USDT"],
        "vi": ["Hiện chỉ Spot, cặp USDT (dạng BTC-USDT).",
               "Sooppiy cố định mua market theo số lượng tiền gốc — số đã đặt là coin, không phải USDT chi ra."],
        "id": ["Saat ini Spot saja, pasangan USDT (format BTC-USDT).",
               "Sooppiy mengunci market buy pada ukuran mata uang dasar — jumlah yang diatur adalah koin, bukan belanja USDT."],
    },
    "trouble": {
        "en": [("code 50105 / “Passphrase incorrect”",
                "The passphrase Sooppiy stored differs from the one set at key creation. Reconnect the broker and re-enter all three values."),
               ("code 50111 / “Invalid OK-ACCESS-KEY”",
                "Usually a real key while the venue expects a demo key (or the reverse) — the two environments have separate keys.")],
        "ko": [("code 50105 / “Passphrase incorrect”",
                "저장된 패스프레이즈가 키 생성 시 설정한 값과 다릅니다. 브로커를 다시 연결해 세 값을 다시 입력하세요."),
               ("code 50111 / “Invalid OK-ACCESS-KEY”",
                "대개 데모 환경에 실계정 키(또는 그 반대)를 쓴 경우입니다 — 두 환경의 키는 별개입니다.")],
        "ja": [("code 50105 / “Passphrase incorrect”",
                "保存されたパスフレーズがキー作成時の設定と異なります。ブローカーを再接続し3つの値を再入力してください。"),
               ("code 50111 / “Invalid OK-ACCESS-KEY”",
                "多くはデモ環境に本番キー(またはその逆)を使っています — 2つの環境のキーは別物です。")],
        "th": [("code 50105 / “Passphrase incorrect”",
                "พาสเฟรสที่บันทึกไว้ต่างจากที่ตั้งตอนสร้างคีย์ — เชื่อมต่อโบรกเกอร์ใหม่และกรอกทั้งสามค่าอีกครั้ง"),
               ("code 50111 / “Invalid OK-ACCESS-KEY”",
                "มักเป็นการใช้คีย์จริงกับสภาพแวดล้อมเดโม (หรือกลับกัน) — สองสภาพแวดล้อมใช้คีย์คนละชุด")],
        "vi": [("code 50105 / “Passphrase incorrect”",
                "Passphrase đã lưu khác với giá trị đặt khi tạo khóa. Kết nối lại broker và nhập lại cả ba giá trị."),
               ("code 50111 / “Invalid OK-ACCESS-KEY”",
                "Thường là khóa thật dùng cho môi trường demo (hoặc ngược lại) — hai môi trường có khóa riêng.")],
        "id": [("code 50105 / “Passphrase incorrect”",
                "Passphrase yang tersimpan berbeda dari yang ditetapkan saat kunci dibuat. Hubungkan ulang broker dan masukkan lagi ketiga nilai."),
               ("code 50111 / “Invalid OK-ACCESS-KEY”",
                "Biasanya kunci asli dipakai di lingkungan demo (atau sebaliknya) — kedua lingkungan memakai kunci terpisah.")],
    },
},
"kraken": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at kraken.com (or pro.kraken.com) → profile → <b>Settings</b> → <b>API</b> → <b>Create API key</b>.",
               "Permissions: <b>Query funds</b> and <b>Create &amp; modify orders</b>. Never Withdraw.",
               "Create a key that is <b>dedicated to Sooppiy</b> — do not reuse it in any other bot or tool (see venue notes on nonces)."],
        "ko": ["kraken.com(또는 pro.kraken.com) 로그인 → 프로필 → <b>Settings</b> → <b>API</b> → <b>Create API key</b>.",
               "권한: <b>Query funds</b> + <b>Create &amp; modify orders</b>. 출금 권한은 절대 안 됩니다.",
               "<b>Sooppiy 전용 키</b>를 만드세요 — 다른 봇·도구에서 같은 키를 재사용하면 안 됩니다(아래 논스 항목 참고)."],
        "ja": ["kraken.com(またはpro.kraken.com)にログイン → プロフィール → <b>Settings</b> → <b>API</b> → <b>Create API key</b>。",
               "権限: <b>Query funds</b> + <b>Create &amp; modify orders</b>。出金権限は絶対に不可。",
               "<b>Sooppiy専用のキー</b>を作成してください — 他のボットやツールで同じキーを再利用しないこと(下のノンスの注意参照)。"],
        "th": ["เข้าสู่ระบบ kraken.com (หรือ pro.kraken.com) → โปรไฟล์ → <b>Settings</b> → <b>API</b> → <b>Create API key</b>",
               "สิทธิ์: <b>Query funds</b> และ <b>Create &amp; modify orders</b> ห้าม Withdraw เด็ดขาด",
               "สร้างคีย์<b>เฉพาะสำหรับ Sooppiy</b> — อย่านำไปใช้ซ้ำในบอทหรือเครื่องมืออื่น (ดูหมายเหตุเรื่อง nonce ด้านล่าง)"],
        "vi": ["Đăng nhập kraken.com (hoặc pro.kraken.com) → hồ sơ → <b>Settings</b> → <b>API</b> → <b>Create API key</b>.",
               "Quyền: <b>Query funds</b> và <b>Create &amp; modify orders</b>. Tuyệt đối không Withdraw.",
               "Tạo khóa <b>dành riêng cho Sooppiy</b> — không dùng lại trong bot hay công cụ khác (xem ghi chú nonce bên dưới)."],
        "id": ["Masuk ke kraken.com (atau pro.kraken.com) → profil → <b>Settings</b> → <b>API</b> → <b>Create API key</b>.",
               "Izin: <b>Query funds</b> dan <b>Create &amp; modify orders</b>. Jangan pernah Withdraw.",
               "Buat kunci yang <b>khusus untuk Sooppiy</b> — jangan dipakai ulang di bot atau alat lain (lihat catatan nonce di bawah)."],
    },
    "shadow": {
        "en": "<b>shadow</b> — Kraken has no test environment, so shadow uses Kraken's own <b>validate-only</b> order call against your real account: authentication, pair, size and balance are checked, but the order can never fill and no money moves. The venue's accept/reject answer is journalled.",
        "ko": "<b>shadow</b> — 크라켄에는 테스트 환경이 없어서, 섀도는 실계정에 크라켄 자체의 <b>검증 전용(validate-only)</b> 주문 호출을 보냅니다. 인증·페어·수량·잔고는 검사되지만 주문은 절대 체결될 수 없고 돈도 움직이지 않습니다. 거래소의 승인/거부 응답이 기록됩니다.",
        "ja": "<b>shadow</b> — Krakenにはテスト環境がないため、シャドーは実口座に対しKraken自身の<b>検証専用(validate-only)</b>注文コールを送ります。認証・ペア・数量・残高は検査されますが、注文は決して約定せず資金も動きません。取引所の承認/拒否の応答が記録されます。",
        "th": "<b>shadow</b> — Kraken ไม่มีสภาพแวดล้อมทดสอบ shadow จึงใช้คำสั่งแบบ <b>validate-only</b> ของ Kraken เองกับบัญชีจริงของคุณ: ตรวจการยืนยันตัวตน คู่เทรด ขนาด และยอดเงิน แต่คำสั่งไม่มีทางจับคู่และเงินไม่เคลื่อนไหว คำตอบรับ/ปฏิเสธของกระดานถูกบันทึกไว้",
        "vi": "<b>shadow</b> — Kraken không có môi trường thử nghiệm, nên shadow dùng lệnh <b>chỉ-kiểm-tra (validate-only)</b> của chính Kraken trên tài khoản thật: xác thực, cặp, khối lượng và số dư được kiểm, nhưng lệnh không bao giờ khớp và tiền không di chuyển. Câu trả lời chấp nhận/từ chối của sàn được ghi lại.",
        "id": "<b>shadow</b> — Kraken tidak punya lingkungan uji, jadi shadow memakai panggilan order <b>validate-only</b> milik Kraken pada akun asli Anda: autentikasi, pasangan, ukuran, dan saldo diperiksa, tetapi order tidak mungkin tereksekusi dan tidak ada dana bergerak. Jawaban terima/tolak bursa dicatat.",
    },
    "notes": {
        "en": ["Kraken permanently invalidates a key when it sees a nonce go backwards. Sooppiy manages nonces safely on its side, but a SECOND app using the same key will race it and can kill the key — one key, one app.",
               "Bitcoin is called <b>XBT</b> on Kraken; Sooppiy translates symbols automatically.",
               "USD- and EUR-quoted pairs (USDT pairs also exist)."],
        "ko": ["크라켄은 논스(nonce)가 되돌아간 것을 감지하면 키를 영구 무효화합니다. Sooppiy는 자체적으로 논스를 안전하게 관리하지만, 같은 키를 쓰는 두 번째 앱이 있으면 경합으로 키가 죽을 수 있습니다 — 키 하나, 앱 하나.",
               "크라켄에서 비트코인은 <b>XBT</b>로 표기됩니다. 심볼은 Sooppiy가 자동 변환합니다.",
               "USD·EUR 호가 페어가 기본입니다(USDT 페어도 있음)."],
        "ja": ["Krakenはノンス(nonce)の逆行を検知するとキーを永久に無効化します。Sooppiy側では安全に管理しますが、同じキーを使う別のアプリがあると競合してキーが死ぬ可能性があります — 1キー1アプリ。",
               "KrakenではビットコインはXBT表記です。シンボルはSooppiyが自動変換します。",
               "USD・EUR建てペアが基本です(USDTペアもあります)。"],
        "th": ["Kraken จะทำให้คีย์ใช้ไม่ได้ถาวรเมื่อพบ nonce ย้อนกลับ Sooppiy จัดการ nonce อย่างปลอดภัยฝั่งตัวเอง แต่แอปที่สองที่ใช้คีย์เดียวกันจะแข่ง nonce และอาจทำให้คีย์ตายได้ — หนึ่งคีย์ หนึ่งแอป",
               "บน Kraken บิตคอยน์ใช้ชื่อ <b>XBT</b> — Sooppiy แปลงสัญลักษณ์ให้อัตโนมัติ",
               "คู่ที่อ้างอิง USD และ EUR เป็นหลัก (มีคู่ USDT ด้วย)"],
        "vi": ["Kraken vô hiệu hóa khóa vĩnh viễn khi thấy nonce đi lùi. Sooppiy quản lý nonce an toàn ở phía mình, nhưng một ứng dụng THỨ HAI dùng cùng khóa sẽ tranh chấp và có thể làm chết khóa — một khóa, một ứng dụng.",
               "Trên Kraken, Bitcoin gọi là <b>XBT</b>; Sooppiy tự động chuyển đổi ký hiệu.",
               "Cặp định giá USD và EUR là chính (cũng có cặp USDT)."],
        "id": ["Kraken menonaktifkan kunci secara permanen bila melihat nonce mundur. Sooppiy mengelola nonce dengan aman di sisinya, tetapi aplikasi KEDUA yang memakai kunci sama akan berebut dan bisa mematikan kunci — satu kunci, satu aplikasi.",
               "Di Kraken, Bitcoin disebut <b>XBT</b>; Sooppiy menerjemahkan simbol otomatis.",
               "Pasangan berbasis USD dan EUR (pasangan USDT juga ada)."],
    },
    "trouble": {
        "en": [("“EAPI:Invalid nonce”",
                "Another application is using the same key. Create a Sooppiy-only key — a key that keeps racing will eventually be invalidated by Kraken."),
               ("“EGeneral:Permission denied”",
                "The key lacks Create &amp; modify orders (or Query funds). Edit the key's permissions on Kraken.")],
        "ko": [("“EAPI:Invalid nonce”",
                "다른 애플리케이션이 같은 키를 쓰고 있습니다. Sooppiy 전용 키를 만드세요 — 경합이 계속되면 크라켄이 결국 키를 무효화합니다."),
               ("“EGeneral:Permission denied”",
                "키에 Create &amp; modify orders(또는 Query funds) 권한이 없습니다. 크라켄에서 키 권한을 수정하세요.")],
        "ja": [("“EAPI:Invalid nonce”",
                "別のアプリケーションが同じキーを使っています。Sooppiy専用キーを作成してください — 競合が続くとKrakenが最終的にキーを無効化します。"),
               ("“EGeneral:Permission denied”",
                "キーにCreate &amp; modify orders(またはQuery funds)権限がありません。Krakenでキーの権限を修正してください。")],
        "th": [("“EAPI:Invalid nonce”",
                "มีแอปอื่นใช้คีย์เดียวกันอยู่ — สร้างคีย์เฉพาะ Sooppiy หากแข่งกันต่อไป Kraken จะทำให้คีย์ใช้ไม่ได้ในที่สุด"),
               ("“EGeneral:Permission denied”",
                "คีย์ขาดสิทธิ์ Create &amp; modify orders (หรือ Query funds) — แก้สิทธิ์คีย์บน Kraken")],
        "vi": [("“EAPI:Invalid nonce”",
                "Một ứng dụng khác đang dùng cùng khóa. Tạo khóa chỉ dành cho Sooppiy — tranh chấp kéo dài sẽ khiến Kraken vô hiệu hóa khóa."),
               ("“EGeneral:Permission denied”",
                "Khóa thiếu quyền Create &amp; modify orders (hoặc Query funds). Sửa quyền của khóa trên Kraken.")],
        "id": [("“EAPI:Invalid nonce”",
                "Aplikasi lain memakai kunci yang sama. Buat kunci khusus Sooppiy — perebutan berkelanjutan akhirnya membuat Kraken menonaktifkan kunci."),
               ("“EGeneral:Permission denied”",
                "Kunci tidak punya izin Create &amp; modify orders (atau Query funds). Ubah izin kunci di Kraken.")],
    },
},
"cryptocom": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["This is the <b>Exchange</b> (exchange.crypto.com), not the mobile app. Log in → <b>Settings</b> → <b>API Keys</b> → create a key.",
               "Permission: trading enabled, withdrawals disabled. Add an IP allowlist if offered.",
               "For shadow comparison, the Exchange's <b>UAT sandbox</b> is a separate environment with its own keys."],
        "ko": ["모바일 앱이 아니라 <b>거래소</b>(exchange.crypto.com)입니다. 로그인 → <b>Settings</b> → <b>API Keys</b>에서 키를 생성하세요.",
               "권한: 거래 활성, 출금 비활성. IP 허용목록이 있으면 등록하세요.",
               "섀도 비교용 <b>UAT 샌드박스</b>는 별도 환경이며 키도 별도입니다."],
        "ja": ["モバイルアプリではなく<b>取引所</b>(exchange.crypto.com)です。ログイン → <b>Settings</b> → <b>API Keys</b>でキーを作成。",
               "権限: 取引は有効、出金は無効。IP許可リストがあれば登録してください。",
               "シャドー比較用の<b>UATサンドボックス</b>は別環境で、キーも別です。"],
        "th": ["นี่คือ<b>กระดานเทรด</b> (exchange.crypto.com) ไม่ใช่แอปมือถือ ล็อกอิน → <b>Settings</b> → <b>API Keys</b> → สร้างคีย์",
               "สิทธิ์: เปิดเทรด ปิดถอนเงิน เพิ่มรายการอนุญาต IP หากมี",
               "สำหรับเปรียบเทียบ shadow แซนด์บ็อกซ์ <b>UAT</b> เป็นสภาพแวดล้อมแยกและคีย์แยก"],
        "vi": ["Đây là <b>Sàn giao dịch</b> (exchange.crypto.com), không phải ứng dụng di động. Đăng nhập → <b>Settings</b> → <b>API Keys</b> → tạo khóa.",
               "Quyền: bật giao dịch, tắt rút tiền. Thêm danh sách IP cho phép nếu có.",
               "Để so khớp shadow, sandbox <b>UAT</b> của Sàn là môi trường riêng với khóa riêng."],
        "id": ["Ini adalah <b>Exchange</b> (exchange.crypto.com), bukan aplikasi seluler. Masuk → <b>Settings</b> → <b>API Keys</b> → buat kunci.",
               "Izin: trading aktif, penarikan nonaktif. Tambahkan daftar IP yang diizinkan bila tersedia.",
               "Untuk perbandingan shadow, <b>sandbox UAT</b> Exchange adalah lingkungan terpisah dengan kunci terpisah."],
    },
    "shadow": {
        "en": "<b>shadow</b> — fills stay simulated and the same order is ALSO sent to the Exchange's <b>UAT sandbox</b> for comparison; the drift is journalled. Sandbox keys are separate from real ones.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고 같은 주문이 거래소 <b>UAT 샌드박스</b>에도 전송되며 차이가 기록됩니다. 샌드박스 키는 실계정 키와 별개입니다.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文が取引所の<b>UATサンドボックス</b>にも送信され、差異が記録されます。サンドボックスキーは本番キーと別物です。",
        "th": "<b>shadow</b> — การจับคู่ยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยังแซนด์บ็อกซ์ <b>UAT</b> ของกระดานเพื่อเปรียบเทียบ พร้อมบันทึกความต่าง คีย์แซนด์บ็อกซ์แยกจากคีย์จริง",
        "vi": "<b>shadow</b> — khớp lệnh vẫn là mô phỏng và lệnh đó được gửi tới sandbox <b>UAT</b> của Sàn để so sánh; chênh lệch được ghi lại. Khóa sandbox tách biệt khóa thật.",
        "id": "<b>shadow</b> — eksekusi tetap simulasi dan order yang sama dikirim ke <b>sandbox UAT</b> Exchange untuk perbandingan; selisihnya dicatat. Kunci sandbox terpisah dari kunci asli.",
    },
    "notes": {
        "en": ["Spot only for now, USDT pairs (BTC_USDT style).",
               "Market buys on this venue are quoted in spend amount; Sooppiy converts your coin quantity at the decision price and the drift journal records the actual fill."],
        "ko": ["현재는 스팟 전용, USDT 페어(BTC_USDT 형식)입니다.",
               "이 거래소의 시장가 매수는 지출 금액 기준입니다. Sooppiy가 코인 수량을 판단 시점 가격으로 환산해 주문하며, 실제 체결량은 드리프트 기록에 남습니다."],
        "ja": ["現在はスポットのみ、USDTペア(BTC_USDT形式)です。",
               "この取引所の成行買いは支出額基準です。Sooppiyがコイン数量を判断時の価格で換算して発注し、実際の約定量はドリフト記録に残ります。"],
        "th": ["ตอนนี้เฉพาะ Spot คู่ USDT (รูปแบบ BTC_USDT)",
               "การซื้อ market บนกระดานนี้ระบุเป็นยอดใช้จ่าย — Sooppiy แปลงจำนวนเหรียญด้วยราคาตอนตัดสินใจ และปริมาณจับคู่จริงถูกบันทึกในบันทึกดริฟต์"],
        "vi": ["Hiện chỉ Spot, cặp USDT (dạng BTC_USDT).",
               "Mua market trên sàn này tính theo số tiền chi; Sooppiy quy đổi số coin theo giá lúc quyết định và nhật ký lệch ghi lại khớp thực tế."],
        "id": ["Saat ini Spot saja, pasangan USDT (format BTC_USDT).",
               "Market buy di bursa ini dihitung dari jumlah belanja; Sooppiy mengonversi jumlah koin Anda pada harga keputusan dan jurnal penyimpangan mencatat eksekusi sebenarnya."],
    },
    "trouble": {
        "en": [("code 10002 / “UNAUTHORIZED”",
                "Usually keys from the other environment (UAT vs live). Each environment only accepts its own keys.")],
        "ko": [("code 10002 / “UNAUTHORIZED”",
                "대개 다른 환경(UAT vs 실계정)의 키입니다. 각 환경은 자기 키만 받습니다.")],
        "ja": [("code 10002 / “UNAUTHORIZED”",
                "多くは別環境(UAT vs 本番)のキーです。各環境は自身のキーのみ受け付けます。")],
        "th": [("code 10002 / “UNAUTHORIZED”",
                "มักเป็นคีย์จากสภาพแวดล้อมตรงข้าม (UAT vs จริง) — แต่ละสภาพแวดล้อมรับเฉพาะคีย์ของตัวเอง")],
        "vi": [("code 10002 / “UNAUTHORIZED”",
                "Thường là khóa của môi trường kia (UAT vs live). Mỗi môi trường chỉ nhận khóa của chính nó.")],
        "id": [("code 10002 / “UNAUTHORIZED”",
                "Biasanya kunci dari lingkungan lain (UAT vs live). Tiap lingkungan hanya menerima kuncinya sendiri.")],
    },
},
"upbit": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at upbit.com → <b>마이페이지</b> (My Page) → <b>Open API 관리</b> (Open API Management).",
               "Tick <b>자산조회</b> (asset inquiry) and <b>주문</b> (orders). Never the withdrawal permission.",
               "Upbit REQUIRES registering the calling server's IP address on the key — without it every request is refused."],
        "ko": ["upbit.com 로그인 → <b>마이페이지</b> → <b>Open API 관리</b>.",
               "<b>자산조회</b>와 <b>주문</b>에 체크하세요. 출금 권한은 절대 체크하지 마세요.",
               "업비트는 키에 호출 서버의 IP 주소 등록을 필수로 요구합니다 — 등록이 없으면 모든 요청이 거부됩니다."],
        "ja": ["upbit.comにログイン → <b>マイページ</b> → <b>Open API管理</b>。",
               "<b>資産照会</b>と<b>注文</b>にチェック。出金権限は絶対にチェックしないでください。",
               "Upbitはキーに呼び出しサーバーのIPアドレス登録を必須としています — 未登録だとすべてのリクエストが拒否されます。"],
        "th": ["เข้าสู่ระบบ upbit.com → <b>마이페이지</b> (หน้าของฉัน) → <b>Open API 관리</b> (จัดการ Open API)",
               "ติ๊ก <b>자산조회</b> (ดูสินทรัพย์) และ <b>주문</b> (คำสั่งซื้อขาย) ห้ามติ๊กสิทธิ์ถอนเงินเด็ดขาด",
               "Upbit บังคับให้ลงทะเบียน IP ของเซิร์ฟเวอร์ที่เรียกบนคีย์ — หากไม่ลงทะเบียน ทุกคำขอจะถูกปฏิเสธ"],
        "vi": ["Đăng nhập upbit.com → <b>마이페이지</b> (Trang của tôi) → <b>Open API 관리</b> (Quản lý Open API).",
               "Tích <b>자산조회</b> (tra cứu tài sản) và <b>주문</b> (đặt lệnh). Tuyệt đối không tích quyền rút tiền.",
               "Upbit BẮT BUỘC đăng ký địa chỉ IP của máy chủ gọi trên khóa — thiếu nó mọi yêu cầu đều bị từ chối."],
        "id": ["Masuk ke upbit.com → <b>마이페이지</b> (Halaman Saya) → <b>Open API 관리</b> (Manajemen Open API).",
               "Centang <b>자산조회</b> (lihat aset) dan <b>주문</b> (order). Jangan pernah centang izin penarikan.",
               "Upbit MEWAJIBKAN pendaftaran alamat IP server pemanggil pada kunci — tanpanya semua permintaan ditolak."],
    },
    "shadow": {
        "en": "<b>shadow</b> — Upbit has no sandbox and no dry-run call, so shadow makes <b>no network call at all</b>: your rule's intended orders are journalled against live book prices for the rollout soak, and nothing ever reaches Upbit. The journal rows appear in the drift panel with status “journal”.",
        "ko": "<b>shadow</b> — 업비트에는 샌드박스도 검증 호출도 없어서, 섀도는 <b>네트워크 호출을 전혀 하지 않습니다</b>. 규칙이 의도한 주문이 실시간 호가와 함께 검증 기간용으로 기록될 뿐, 업비트에는 아무것도 전송되지 않습니다. 기록은 드리프트 패널에 “journal” 상태로 표시됩니다.",
        "ja": "<b>shadow</b> — Upbitにはサンドボックスも検証コールもないため、シャドーは<b>ネットワーク呼び出しを一切行いません</b>。ルールが意図した注文がライブ気配とともに検証期間用に記録されるだけで、Upbitには何も送信されません。記録はドリフトパネルに「journal」状態で表示されます。",
        "th": "<b>shadow</b> — Upbit ไม่มีแซนด์บ็อกซ์และไม่มีคำสั่งตรวจสอบ shadow จึง<b>ไม่เรียกเครือข่ายเลย</b>: คำสั่งที่กฎตั้งใจส่งถูกบันทึกคู่กับราคาจริงเพื่อช่วงทดสอบ และไม่มีอะไรไปถึง Upbit บันทึกจะแสดงในแผงดริฟต์ด้วยสถานะ “journal”",
        "vi": "<b>shadow</b> — Upbit không có sandbox lẫn lệnh kiểm tra, nên shadow <b>không gọi mạng chút nào</b>: các lệnh dự định của quy tắc được ghi lại cùng giá sổ trực tiếp cho giai đoạn kiểm chứng, và không gì tới Upbit cả. Các dòng ghi hiện trong bảng lệch với trạng thái “journal”.",
        "id": "<b>shadow</b> — Upbit tidak punya sandbox maupun panggilan uji, jadi shadow <b>tidak melakukan panggilan jaringan sama sekali</b>: order yang dimaksud aturan Anda dicatat terhadap harga buku langsung untuk masa uji, dan tidak ada yang sampai ke Upbit. Baris jurnal muncul di panel penyimpangan dengan status “journal”.",
    },
    "notes": {
        "en": ["KRW markets (KRW-BTC style). Your ledger stays in USD: Sooppiy records the KRW/USD rate it used on every order, taken from Upbit's own KRW-USDT book at that moment — and refuses to trade if no rate is available.",
               "Upbit market <b>buys</b> are placed as a KRW amount (not a coin quantity); the coin volume actually bought is read back from the venue and any difference shows in the drift records."],
        "ko": ["KRW 마켓(KRW-BTC 형식)입니다. 원장은 USD 기준으로 유지됩니다: Sooppiy는 매 주문에 사용한 KRW/USD 환율(그 시점 업비트 KRW-USDT 호가)을 기록하며, 환율을 구할 수 없으면 거래를 거부합니다.",
               "업비트 시장가 <b>매수</b>는 코인 수량이 아니라 KRW 금액으로 주문됩니다. 실제 매수된 수량은 거래소에서 다시 읽어오며 차이는 드리프트 기록에 표시됩니다."],
        "ja": ["KRWマーケット(KRW-BTC形式)です。台帳はUSD基準のまま: Sooppiyは各注文に使ったKRW/USDレート(その時点のUpbit KRW-USDT気配)を記録し、レートが取得できない場合は取引を拒否します。",
               "Upbitの成行<b>買い</b>はコイン数量ではなくKRW金額で発注されます。実際に買えた数量は取引所から読み戻し、差異はドリフト記録に表示されます。"],
        "th": ["ตลาด KRW (รูปแบบ KRW-BTC) บัญชีของคุณยังเป็น USD: Sooppiy บันทึกอัตรา KRW/USD ที่ใช้ในทุกคำสั่ง (จากกระดาน KRW-USDT ของ Upbit ณ ขณะนั้น) และปฏิเสธการเทรดหากไม่มีอัตราให้ใช้",
               "การซื้อ market ของ Upbit ระบุเป็นจำนวนเงิน KRW (ไม่ใช่จำนวนเหรียญ) ปริมาณเหรียญที่ซื้อได้จริงถูกอ่านกลับจากกระดาน และความต่างแสดงในบันทึกดริฟต์"],
        "vi": ["Thị trường KRW (dạng KRW-BTC). Sổ của bạn vẫn tính bằng USD: Sooppiy ghi lại tỷ giá KRW/USD dùng cho từng lệnh (lấy từ chính sổ KRW-USDT của Upbit lúc đó) — và từ chối giao dịch nếu không có tỷ giá.",
               "Lệnh <b>mua</b> market trên Upbit đặt theo số tiền KRW (không phải số coin); lượng coin thực mua được đọc lại từ sàn và mọi chênh lệch hiện trong bản ghi lệch."],
        "id": ["Pasar KRW (format KRW-BTC). Buku Anda tetap dalam USD: Sooppiy mencatat kurs KRW/USD yang dipakai pada setiap order (diambil dari buku KRW-USDT milik Upbit saat itu) — dan menolak bertransaksi bila kurs tidak tersedia.",
               "Market <b>buy</b> Upbit dipasang sebagai jumlah KRW (bukan jumlah koin); volume koin yang benar-benar terbeli dibaca kembali dari bursa dan selisihnya tampil di catatan penyimpangan."],
    },
    "trouble": {
        "en": [("“no_authorization_ip” / every request 401",
                "The calling server's IP is not registered on the key. Add it in Upbit's Open API management."),
               ("“could not fetch KRW/USD rate — order refused”",
                "Upbit's KRW-USDT ticker was unreachable at that moment. The order is refused rather than guessed; it will be retried on the rule's next cycle.")],
        "ko": [("“no_authorization_ip” / 모든 요청 401",
                "호출 서버 IP가 키에 등록되어 있지 않습니다. 업비트 Open API 관리에서 추가하세요."),
               ("“could not fetch KRW/USD rate — order refused”",
                "그 순간 업비트 KRW-USDT 시세를 가져올 수 없었습니다. 추정 대신 주문을 거부하며, 규칙의 다음 사이클에서 다시 시도됩니다.")],
        "ja": [("“no_authorization_ip” / すべてのリクエストが401",
                "呼び出しサーバーのIPがキーに登録されていません。UpbitのOpen API管理で追加してください。"),
               ("“could not fetch KRW/USD rate — order refused”",
                "その瞬間UpbitのKRW-USDT気配を取得できませんでした。推定はせず注文を拒否し、ルールの次サイクルで再試行されます。")],
        "th": [("“no_authorization_ip” / ทุกคำขอ 401",
                "IP ของเซิร์ฟเวอร์ที่เรียกไม่ได้ลงทะเบียนบนคีย์ — เพิ่มในหน้าจัดการ Open API ของ Upbit"),
               ("“could not fetch KRW/USD rate — order refused”",
                "ดึงราคา KRW-USDT ของ Upbit ไม่ได้ในขณะนั้น ระบบปฏิเสธคำสั่งแทนการเดา และจะลองใหม่ในรอบถัดไปของกฎ")],
        "vi": [("“no_authorization_ip” / mọi yêu cầu 401",
                "IP máy chủ gọi chưa đăng ký trên khóa. Thêm trong phần quản lý Open API của Upbit."),
               ("“could not fetch KRW/USD rate — order refused”",
                "Không lấy được giá KRW-USDT của Upbit lúc đó. Lệnh bị từ chối thay vì đoán; sẽ thử lại ở chu kỳ kế tiếp của quy tắc.")],
        "id": [("“no_authorization_ip” / semua permintaan 401",
                "IP server pemanggil belum terdaftar pada kunci. Tambahkan di manajemen Open API Upbit."),
               ("“could not fetch KRW/USD rate — order refused”",
                "Ticker KRW-USDT Upbit tidak terjangkau saat itu. Order ditolak alih-alih menebak; akan dicoba lagi pada siklus aturan berikutnya.")],
    },
},
"kucoin": {
    "fields": ["key", "secret", "pass"],
    "steps": {
        "en": ["Log in at kucoin.com → profile icon → <b>API Management</b> → <b>Create API</b>.",
               "You choose the <b>API passphrase</b> yourself at creation — Sooppiy needs it alongside the key and secret.",
               "Permissions: <b>General</b> + <b>Spot Trading</b>. Never Withdrawal. Use API key version 2 (the default for new keys)."],
        "ko": ["kucoin.com 로그인 → 프로필 아이콘 → <b>API Management</b> → <b>Create API</b>.",
               "<b>API 패스프레이즈</b>는 생성 시 직접 정합니다 — 키·시크릿과 함께 Sooppiy에 필요합니다.",
               "권한: <b>General</b> + <b>Spot Trading</b>. 출금은 절대 안 됩니다. API 키 버전 2(신규 키 기본값)를 사용하세요."],
        "ja": ["kucoin.comにログイン → プロフィール → <b>API Management</b> → <b>Create API</b>。",
               "<b>APIパスフレーズ</b>は作成時に自分で決めます — キー・シークレットとともにSooppiyに必要です。",
               "権限: <b>General</b> + <b>Spot Trading</b>。出金は絶対不可。APIキーはバージョン2(新規キーの既定)を使用してください。"],
        "th": ["เข้าสู่ระบบ kucoin.com → ไอคอนโปรไฟล์ → <b>API Management</b> → <b>Create API</b>",
               "คุณตั้ง<b>พาสเฟรส API</b> เองตอนสร้าง — Sooppiy ต้องใช้คู่กับคีย์และความลับ",
               "สิทธิ์: <b>General</b> + <b>Spot Trading</b> ห้ามถอนเงินเด็ดขาด ใช้คีย์เวอร์ชัน 2 (ค่าเริ่มต้นของคีย์ใหม่)"],
        "vi": ["Đăng nhập kucoin.com → biểu tượng hồ sơ → <b>API Management</b> → <b>Create API</b>.",
               "Bạn tự đặt <b>passphrase API</b> khi tạo — Sooppiy cần nó cùng khóa và bí mật.",
               "Quyền: <b>General</b> + <b>Spot Trading</b>. Tuyệt đối không Withdrawal. Dùng khóa phiên bản 2 (mặc định với khóa mới)."],
        "id": ["Masuk ke kucoin.com → ikon profil → <b>API Management</b> → <b>Create API</b>.",
               "Anda menetapkan <b>passphrase API</b> sendiri saat pembuatan — Sooppiy membutuhkannya bersama kunci dan secret.",
               "Izin: <b>General</b> + <b>Spot Trading</b>. Jangan pernah Withdrawal. Gunakan kunci versi 2 (bawaan untuk kunci baru)."],
    },
    "shadow": {
        "en": "<b>shadow</b> — KuCoin's public sandbox was discontinued, so shadow uses KuCoin's own <b>order test</b> endpoint against your real account: the order is fully checked (auth, symbol, size) but can never fill and no money moves. The venue's accept/reject answer is journalled.",
        "ko": "<b>shadow</b> — 쿠코인 공개 샌드박스는 중단되어, 섀도는 실계정에 쿠코인 자체의 <b>주문 테스트</b> 엔드포인트를 사용합니다. 주문은 인증·심볼·수량까지 전부 검사되지만 절대 체결될 수 없고 돈도 움직이지 않습니다. 거래소의 승인/거부 응답이 기록됩니다.",
        "ja": "<b>shadow</b> — KuCoinの公開サンドボックスは廃止されたため、シャドーは実口座に対しKuCoin自身の<b>注文テスト</b>エンドポイントを使います。注文は認証・シンボル・数量まで検査されますが、決して約定せず資金も動きません。取引所の承認/拒否の応答が記録されます。",
        "th": "<b>shadow</b> — แซนด์บ็อกซ์สาธารณะของ KuCoin ถูกยกเลิกแล้ว shadow จึงใช้ endpoint <b>ทดสอบคำสั่ง</b> ของ KuCoin เองกับบัญชีจริง: คำสั่งถูกตรวจครบ (ยืนยันตัวตน สัญลักษณ์ ขนาด) แต่ไม่มีทางจับคู่และเงินไม่เคลื่อนไหว คำตอบรับ/ปฏิเสธของกระดานถูกบันทึก",
        "vi": "<b>shadow</b> — sandbox công khai của KuCoin đã ngừng, nên shadow dùng endpoint <b>kiểm tra lệnh</b> của chính KuCoin trên tài khoản thật: lệnh được kiểm đầy đủ (xác thực, ký hiệu, khối lượng) nhưng không bao giờ khớp và tiền không di chuyển. Câu trả lời chấp nhận/từ chối của sàn được ghi lại.",
        "id": "<b>shadow</b> — sandbox publik KuCoin telah dihentikan, jadi shadow memakai endpoint <b>uji order</b> milik KuCoin pada akun asli Anda: order diperiksa penuh (autentikasi, simbol, ukuran) tetapi tidak mungkin tereksekusi dan tidak ada dana bergerak. Jawaban terima/tolak bursa dicatat.",
    },
    "notes": {
        "en": ["Spot only for now, USDT pairs (BTC-USDT style).",
               "The passphrase is transmitted encrypted (v2 signing) — Sooppiy never sends it raw."],
        "ko": ["현재는 스팟 전용, USDT 페어(BTC-USDT 형식)입니다.",
               "패스프레이즈는 암호화되어 전송됩니다(v2 서명) — Sooppiy는 원문을 그대로 보내지 않습니다."],
        "ja": ["現在はスポットのみ、USDTペア(BTC-USDT形式)です。",
               "パスフレーズは暗号化して送信されます(v2署名) — Sooppiyが平文のまま送ることはありません。"],
        "th": ["ตอนนี้เฉพาะ Spot คู่ USDT (รูปแบบ BTC-USDT)",
               "พาสเฟรสถูกส่งแบบเข้ารหัส (ลายเซ็น v2) — Sooppiy ไม่เคยส่งแบบดิบ"],
        "vi": ["Hiện chỉ Spot, cặp USDT (dạng BTC-USDT).",
               "Passphrase được truyền đã mã hóa (ký v2) — Sooppiy không bao giờ gửi dạng thô."],
        "id": ["Saat ini Spot saja, pasangan USDT (format BTC-USDT).",
               "Passphrase dikirim terenkripsi (penandatanganan v2) — Sooppiy tidak pernah mengirimnya mentah."],
    },
    "trouble": {
        "en": [("code 400004 / “KC-API-PASSPHRASE error”",
                "The stored passphrase differs from the one chosen at key creation, or the key is an old version-1 key. Reconnect with the correct passphrase on a v2 key.")],
        "ko": [("code 400004 / “KC-API-PASSPHRASE error”",
                "저장된 패스프레이즈가 키 생성 시 정한 값과 다르거나, 구버전(v1) 키입니다. v2 키에 올바른 패스프레이즈로 다시 연결하세요.")],
        "ja": [("code 400004 / “KC-API-PASSPHRASE error”",
                "保存されたパスフレーズがキー作成時の設定と異なるか、旧バージョン(v1)のキーです。v2キーに正しいパスフレーズで再接続してください。")],
        "th": [("code 400004 / “KC-API-PASSPHRASE error”",
                "พาสเฟรสที่บันทึกต่างจากที่ตั้งตอนสร้างคีย์ หรือเป็นคีย์รุ่นเก่า (v1) — เชื่อมต่อใหม่ด้วยพาสเฟรสที่ถูกต้องบนคีย์ v2")],
        "vi": [("code 400004 / “KC-API-PASSPHRASE error”",
                "Passphrase đã lưu khác với giá trị chọn khi tạo khóa, hoặc khóa là bản v1 cũ. Kết nối lại với passphrase đúng trên khóa v2.")],
        "id": [("code 400004 / “KC-API-PASSPHRASE error”",
                "Passphrase tersimpan berbeda dari yang dipilih saat kunci dibuat, atau kuncinya versi 1 lama. Hubungkan ulang dengan passphrase benar pada kunci v2.")],
    },
},
}

TITLES = {
    "binance":  {"en": "Connect Binance", "ko": "바이낸스 연결 가이드", "ja": "Binance接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Binance", "vi": "Hướng dẫn kết nối Binance", "id": "Panduan Menghubungkan Binance"},
    "alpaca":   {"en": "Connect Alpaca", "ko": "알파카 연결 가이드", "ja": "Alpaca接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Alpaca", "vi": "Hướng dẫn kết nối Alpaca", "id": "Panduan Menghubungkan Alpaca"},
    "ibkr":     {"en": "Connect Interactive Brokers", "ko": "IBKR 연결 가이드", "ja": "IBKR接続ガイド",
                 "th": "คู่มือเชื่อมต่อ IBKR", "vi": "Hướng dẫn kết nối IBKR", "id": "Panduan Menghubungkan IBKR"},
    "bybit":    {"en": "Connect Bybit", "ko": "바이비트 연결 가이드", "ja": "Bybit接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Bybit", "vi": "Hướng dẫn kết nối Bybit", "id": "Panduan Menghubungkan Bybit"},
    "okx":      {"en": "Connect OKX", "ko": "OKX 연결 가이드", "ja": "OKX接続ガイド",
                 "th": "คู่มือเชื่อมต่อ OKX", "vi": "Hướng dẫn kết nối OKX", "id": "Panduan Menghubungkan OKX"},
    "kraken":   {"en": "Connect Kraken", "ko": "크라켄 연결 가이드", "ja": "Kraken接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Kraken", "vi": "Hướng dẫn kết nối Kraken", "id": "Panduan Menghubungkan Kraken"},
    "cryptocom": {"en": "Connect Crypto.com Exchange", "ko": "Crypto.com 거래소 연결 가이드", "ja": "Crypto.com Exchange接続ガイド",
                  "th": "คู่มือเชื่อมต่อ Crypto.com Exchange", "vi": "Hướng dẫn kết nối Crypto.com Exchange", "id": "Panduan Menghubungkan Crypto.com Exchange"},
    "upbit":    {"en": "Connect Upbit", "ko": "업비트 연결 가이드", "ja": "Upbit接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Upbit", "vi": "Hướng dẫn kết nối Upbit", "id": "Panduan Menghubungkan Upbit"},
    "kucoin":   {"en": "Connect KuCoin", "ko": "쿠코인 연결 가이드", "ja": "KuCoin接続ガイド",
                 "th": "คู่มือเชื่อมต่อ KuCoin", "vi": "Hướng dẫn kết nối KuCoin", "id": "Panduan Menghubungkan KuCoin"},
}

CSS = """
:root{
  --page:#f9f9f7; --surface:#f1f0ec; --grid:#e1e0d9; --card:#ffffff;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --border:rgba(11,11,11,0.10);
  --accent:#2a78d6; --good:#0ca30c; --good-ink:#006300; --critical:#d03b3b; --yellow:#eda100;
}
@media (prefers-color-scheme: dark){
  :root{ --page:#0d0d0d; --surface:#1a1a19; --grid:#2c2c2a; --card:#202020;
    --ink:#fff; --ink-2:#c3c2b7; --border:rgba(255,255,255,0.10);
    --accent:#3987e5; --good-ink:#0ca30c; --yellow:#c98500; }
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--page);color:var(--ink);line-height:1.6;font-size:14.5px;
  font-family:system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:0 22px 46px}
header.doc{border-bottom:1px solid var(--grid);padding:34px 0 22px}
.kicker{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:clamp(26px,4.2vw,36px);font-weight:800;letter-spacing:-.01em;line-height:1.12;margin:8px 0 6px}
.sub{color:var(--ink-2);font-size:14px;margin:2px 0 10px}
.tag{font-size:11px;font-weight:700;border-radius:999px;padding:3px 10px;white-space:nowrap;display:inline-block}
.tag.ok{background:color-mix(in srgb,var(--good) 15%,transparent);color:var(--good-ink)}
.tag.warn{background:color-mix(in srgb,var(--yellow) 18%,transparent);color:#a16800}
section{border-bottom:1px solid var(--grid);padding:24px 0}
h2{font-size:19px;font-weight:700;margin-bottom:10px}
h2 .no{color:var(--accent);font-size:13px;font-variant-numeric:tabular-nums;margin-right:8px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);text-align:left;font-weight:700;padding:9px 11px;border-bottom:1px solid var(--grid);background:var(--surface)}
td{padding:9px 11px;border-bottom:1px solid var(--grid);vertical-align:top}
tr:last-child td{border-bottom:none}
code{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:.9em;background:var(--surface);border-radius:4px;padding:1px 5px}
ul,ol{padding-left:20px;margin:6px 0} li{margin:5px 0}
.note{border-left:3px solid var(--accent);background:var(--card);padding:11px 14px;border-radius:0 10px 10px 0;font-size:13px;color:var(--ink-2);margin-top:12px}
.note.red{border-left-color:var(--critical)}
"""


def render(broker: str, lang: str) -> str:
    s = S[lang]
    b = B[broker]
    name = BROKER_NAMES[broker]
    live = broker in LIVE_TODAY
    field_rows = {"key": s["f_key"], "secret": s["f_secret"], "pass": s["f_pass"],
                  "gwurl": s["f_gwurl"], "acct": s["f_acct"]}
    fields_html = "".join(f"<li>{field_rows[f]}</li>" for f in b["fields"])
    steps_html = "".join(f"<li>{x}</li>" for x in b["steps"][lang])
    connect_html = "".join(f"<li>{x.format(name=name)}</li>" for x in s["connect_steps"])
    notes_html = "".join(f"<li>{x}</li>" for x in b["notes"][lang])
    badge = (f'<span class="tag ok">{s["badge_live"]}</span>' if live
             else f'<span class="tag warn">{s["badge_gated"]}</span>')
    mode_live = (s["mode_live_live"] if live else s["mode_live_gated"]).format(name=name)
    trouble_rows = "".join(
        f"<tr><td>{sym}</td><td>{fix}</td></tr>"
        for sym, fix in [s["t_creds"], s["t_tcs"], *([] if live else [s["t_allow"]]),
                         *b["trouble"][lang]])
    mode_h = s["mode_th"]
    trouble_h = s["trouble_th"]
    return f"""<!-- generated by docs/design/_gen_gateway_setup_guides.py — do not hand-edit; non-English machine-drafted pending native review -->
<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Sooppiy — {TITLES[broker][lang]}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="doc">
  <div class="kicker">{s["kicker"]}</div>
  <h1>{TITLES[broker][lang]}</h1>
  <p class="sub">{s["subtitle"].format(name=name)} {badge}</p>
</header>

<section>
  <h2><span class="no">1</span>{s["h_need"]}</h2>
  <div class="card"><ul>{fields_html}</ul></div>
  <div class="note red">{s["warn_keys"]}</div>
</section>

<section>
  <h2><span class="no">2</span>{s["h_create"].format(name=name)}</h2>
  <ol>{steps_html}</ol>
</section>

<section>
  <h2><span class="no">3</span>{s["h_connect"]}</h2>
  <ol>{connect_html}</ol>
</section>

<section>
  <h2><span class="no">4</span>{s["h_modes"].format(name=name)}</h2>
  <table>
    <tr><th>{mode_h[0]}</th><th>{mode_h[1]}</th></tr>
    <tr><td>paper</td><td>{s["mode_sim"].format(name=name)}</td></tr>
    <tr><td>shadow</td><td>{b["shadow"][lang]}</td></tr>
    <tr><td>live</td><td>{mode_live}</td></tr>
  </table>
  <div class="note">{s["drift_note"].format(name=name)}</div>
</section>

<section>
  <h2><span class="no">5</span>{s["h_notes"]}</h2>
  <ul>{notes_html}</ul>
</section>

<section>
  <h2><span class="no">6</span>{s["h_trouble"]}</h2>
  <table>
    <tr><th>{trouble_h[0]}</th><th>{trouble_h[1]}</th></tr>
    {trouble_rows}
  </table>
</section>
</div>
</body>
</html>
"""


def main() -> None:
    assert set(B) == set(BROKER_SPECS), (
        f"broker tables out of sync with BROKER_SPECS: "
        f"{set(B) ^ set(BROKER_SPECS)}")
    # Passphrase docs must agree with the vault's required fields.
    for broker, spec in BROKER_SPECS.items():
        has_pass_doc = "pass" in B[broker]["fields"]
        has_pass_spec = "passphrase" in spec.fields
        assert has_pass_doc == has_pass_spec, f"{broker}: passphrase mismatch"
    n = 0
    for broker in B:
        for lang in LANGS:
            out = OUT / f"gateway-setup-{broker}-{lang}.html"
            out.write_text(render(broker, lang), encoding="utf-8")
            n += 1
    print(f"wrote {n} files to {OUT}")


if __name__ == "__main__":
    main()
