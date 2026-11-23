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

# Brokers already allowed to route live money (gateway._LEGACY_LIVE_BROKERS
# plus venues since added to prod's LIVE_BROKER_ALLOWLIST — kraken 2026-08-07).
LIVE_TODAY = {"alpaca", "binance", "ibkr", "kraken"}

BROKER_NAMES = {
    "binance": "Binance", "alpaca": "Alpaca", "ibkr": "Interactive Brokers",
    "bybit": "Bybit", "okx": "OKX", "kraken": "Kraken",
    "cryptocom": "Crypto.com Exchange", "upbit": "Upbit", "kucoin": "KuCoin",
    "coinbase": "Coinbase", "webull": "Webull",
}

# ── shared strings ───────────────────────────────────────────────────────────

S = {
"en": dict(
    kicker="SOOPPIY DOCS — TRADING GATEWAY SETUP",
    subtitle="How to create the API credentials at {name} and connect them on the Accounts page.",
    badge_live="live trading available",
    badge_gated="shadow first — live rollout in progress",
    h_avail="Availability and local rules",
    avail_note="Sooppiy does not decide who may use a venue — the venue's own KYC does, and your local law does. Connecting a gateway here does not make a venue available to you, and a venue you cannot legally use will simply refuse your key. This is factual guidance, not legal advice; access rules change, so confirm on the venue's own terms page for your country.",
    h_before="Before you start",
    before_steps=[
        "An account at {name} that has finished the venue's identity verification — an unverified account can create a key but cannot trade with it.",
        "Two-factor authentication switched on at {name}. Every venue asks for a 2FA code (and often an email confirmation) at the moment you create the key.",
        "This page open next to the venue's site, and somewhere safe to hold the secret for the minute between creating it and connecting it.",
    ],
    h_paste="Where each value goes",
    paste_th=["At {name} it is called", "Paste it into Sooppiy's field"],
    once_warn="The <b>secret</b> is shown exactly once, at creation. If you close that screen without copying it you cannot recover it — you have to delete the key and make a new one. Sooppiy never shows it again either, once saved.",
    ip_note="<b>IP restriction — leave it unset for now.</b> Some venues let you lock a key to one server address. Sooppiy is moving its hosting region, and a key pinned to the old address would stop working the moment it moves. One consequence worth diarising: Binance and Bybit disable an unrestricted key's trading permission after 90 days, so plan to revisit the key then.",
    h_after="After you connect",
    after_steps=[
        "The gateway appears under <b>Connected gateways</b> with a health line. Key-pair venues show “credentials on file” — normal, it means there is no session to probe.",
        "Your automation rules do not switch by themselves. A rule only reaches {name} when you set that rule's account type to shadow or live.",
        "Start in <b>shadow</b> and read the <b>Drift records</b> panel for a few days before considering live.",
        "To revoke access at any time, delete the key at {name} — that stops every order instantly, whatever Sooppiy is set to.",
    ],
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
    h_avail="이용 가능 지역과 현지 규정",
    avail_note="어느 거래소를 이용할 수 있는지는 Sooppiy가 정하지 않습니다 — 거래소의 KYC와 회원님 거주지 법률이 정합니다. 여기서 게이트웨이를 연결한다고 해서 해당 거래소를 이용할 수 있게 되는 것은 아니며, 법적으로 이용할 수 없는 거래소는 키 자체를 거부합니다. 이는 사실 안내이며 법률 자문이 아닙니다. 접근 규정은 바뀌므로 거주 국가 기준으로 거래소 약관에서 직접 확인하세요.",
    h_before="시작하기 전에",
    before_steps=[
        "{name}에서 본인 확인(KYC)을 마친 계정. 미인증 계정은 키를 만들 수는 있어도 거래에 사용할 수 없습니다.",
        "{name} 계정의 2단계 인증(2FA) 활성화. 모든 거래소가 키 생성 시점에 2FA 코드(대개 이메일 확인도)를 요구합니다.",
        "이 페이지를 거래소 사이트와 나란히 열어두고, 시크릿을 만든 뒤 연결하기까지 잠시 안전하게 보관할 곳을 준비하세요.",
    ],
    h_paste="어느 값을 어디에 입력하나",
    paste_th=["{name}에서의 이름", "Sooppiy 입력란"],
    once_warn="<b>시크릿</b>은 생성 시 <b>딱 한 번만</b> 표시됩니다. 복사하지 않고 화면을 닫으면 복구할 수 없어 키를 삭제하고 새로 만들어야 합니다. Sooppiy도 저장 후에는 다시 보여주지 않습니다.",
    ip_note="<b>IP 제한 — 지금은 설정하지 마세요.</b> 일부 거래소는 키를 특정 서버 주소로 고정할 수 있습니다. Sooppiy는 호스팅 리전을 이전할 예정이라, 이전 주소로 고정한 키는 이전하는 순간 동작을 멈춥니다. 다만 기억해 두실 점: 바이낸스와 바이비트는 IP 제한이 없는 키의 거래 권한을 90일 후 비활성화하므로, 그때 키를 다시 점검할 일정을 잡아두세요.",
    h_after="연결한 다음",
    after_steps=[
        "<b>연결된 게이트웨이</b> 목록에 상태 표시와 함께 나타납니다. 키 방식 거래소는 “자격 증명 저장됨”으로 표시되는데, 점검할 세션이 없다는 뜻이며 정상입니다.",
        "자동매매 규칙이 저절로 바뀌지는 않습니다. 규칙의 계정 유형을 shadow 또는 live로 설정해야 비로소 {name}에 주문이 전달됩니다.",
        "먼저 <b>shadow</b>로 며칠 운영하며 <b>드리프트 기록</b> 패널을 확인한 뒤 실거래를 검토하세요.",
        "언제든 {name}에서 키를 삭제하면 접근이 즉시 차단됩니다 — Sooppiy 설정과 무관하게 모든 주문이 멈춥니다.",
    ],
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
    h_avail="利用可能な地域と現地規制",
    avail_note="どの取引所を利用できるかを決めるのはSooppiyではありません — 取引所のKYCと、お住まいの地域の法律です。ここでゲートウェイを接続しても取引所が利用可能になるわけではなく、法的に利用できない取引所はキー自体を拒否します。これは事実の案内であり法的助言ではありません。アクセス規定は変わるため、居住国について取引所の規約で直接ご確認ください。",
    h_before="始める前に",
    before_steps=[
        "{name}で本人確認(KYC)を完了した口座。未認証の口座はキーを作成できても取引には使えません。",
        "{name}での二段階認証(2FA)の有効化。どの取引所もキー作成時に2FAコード(多くはメール確認も)を求めます。",
        "このページを取引所サイトと並べて開き、シークレットを作成してから接続するまでの間、安全に保管できる場所を用意してください。",
    ],
    h_paste="どの値をどこに入力するか",
    paste_th=["{name}での名称", "Sooppiyの入力欄"],
    once_warn="<b>シークレット</b>は作成時に<b>一度だけ</b>表示されます。コピーせず画面を閉じると復元できず、キーを削除して作り直す必要があります。Sooppiyも保存後は再表示しません。",
    ip_note="<b>IP制限 — 今は設定しないでください。</b> 一部の取引所ではキーを特定のサーバーアドレスに固定できます。Sooppiyはホスティングリージョンを移転する予定で、旧アドレスに固定したキーは移転した瞬間に動作しなくなります。ただし控えておく点として、BinanceとBybitはIP制限のないキーの取引権限を90日後に無効化するため、その時点でキーを見直す予定を立てておいてください。",
    h_after="接続した後",
    after_steps=[
        "<b>接続済みゲートウェイ</b>に状態表示とともに現れます。キー方式の取引所は「認証情報を保存済み」と表示されますが、点検すべきセッションがないという意味で正常です。",
        "自動売買ルールが自動的に切り替わることはありません。ルールの口座種別をshadowまたはliveにして初めて{name}に注文が届きます。",
        "まず<b>shadow</b>で数日運用し、<b>ドリフト記録</b>パネルを確認してからliveを検討してください。",
        "いつでも{name}側でキーを削除すればアクセスは即座に遮断されます — Sooppiyの設定に関係なくすべての注文が止まります。",
    ],
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
    h_avail="ความพร้อมให้บริการและกฎท้องถิ่น",
    avail_note="Sooppiy ไม่ได้เป็นผู้ตัดสินว่าใครใช้กระดานใดได้ — KYC ของกระดานและกฎหมายท้องถิ่นของคุณเป็นผู้ตัดสิน การเชื่อมต่อเกตเวย์ที่นี่ไม่ได้ทำให้กระดานนั้นใช้ได้กับคุณ และกระดานที่คุณใช้ไม่ได้ตามกฎหมายจะปฏิเสธคีย์ของคุณเอง นี่คือข้อมูลข้อเท็จจริง ไม่ใช่คำแนะนำทางกฎหมาย กฎการเข้าถึงเปลี่ยนได้ โปรดยืนยันในหน้าข้อกำหนดของกระดานสำหรับประเทศของคุณ",
    h_before="ก่อนเริ่ม",
    before_steps=[
        "บัญชีที่ {name} ซึ่งยืนยันตัวตน (KYC) เรียบร้อยแล้ว บัญชีที่ยังไม่ยืนยันสร้างคีย์ได้แต่ใช้เทรดไม่ได้",
        "เปิดใช้การยืนยันสองขั้นตอน (2FA) ที่ {name} ทุกกระดานจะขอรหัส 2FA (และมักขอยืนยันทางอีเมล) ตอนสร้างคีย์",
        "เปิดหน้านี้คู่กับเว็บของกระดาน และเตรียมที่ปลอดภัยสำหรับเก็บความลับชั่วครู่ระหว่างสร้างกับเชื่อมต่อ",
    ],
    h_paste="ค่าไหนใส่ช่องไหน",
    paste_th=["ชื่อที่ {name} ใช้", "ช่องกรอกใน Sooppiy"],
    once_warn="<b>ความลับ (secret)</b> จะแสดง<b>เพียงครั้งเดียว</b>ตอนสร้าง หากปิดหน้าจอโดยไม่คัดลอกจะกู้คืนไม่ได้ ต้องลบคีย์แล้วสร้างใหม่ และ Sooppiy ก็จะไม่แสดงอีกหลังบันทึก",
    ip_note="<b>การจำกัด IP — ยังไม่ต้องตั้งตอนนี้</b> บางกระดานให้ล็อกคีย์ไว้กับที่อยู่เซิร์ฟเวอร์เดียวได้ Sooppiy กำลังจะย้ายภูมิภาคโฮสติ้ง คีย์ที่ล็อกกับที่อยู่เดิมจะหยุดทำงานทันทีที่ย้าย สิ่งที่ควรจดไว้: Binance และ Bybit ปิดสิทธิ์เทรดของคีย์ที่ไม่จำกัด IP หลัง 90 วัน จึงควรวางแผนกลับมาตรวจคีย์ตอนนั้น",
    h_after="หลังเชื่อมต่อแล้ว",
    after_steps=[
        "เกตเวย์จะปรากฏใน <b>เกตเวย์ที่เชื่อมต่อ</b> พร้อมบรรทัดสถานะ กระดานแบบคู่คีย์จะแสดงว่า “บันทึกข้อมูลรับรองแล้ว” ซึ่งเป็นปกติ เพราะไม่มีเซสชันให้ตรวจ",
        "กฎอัตโนมัติจะไม่เปลี่ยนเอง คำสั่งจะไปถึง {name} ก็ต่อเมื่อคุณตั้งประเภทบัญชีของกฎนั้นเป็น shadow หรือ live",
        "เริ่มที่ <b>shadow</b> และดูแผง <b>บันทึกดริฟต์</b> สักสองสามวันก่อนพิจารณา live",
        "ยกเลิกสิทธิ์ได้ทุกเมื่อโดยลบคีย์ที่ {name} — คำสั่งทั้งหมดจะหยุดทันที ไม่ว่า Sooppiy จะตั้งค่าไว้อย่างไร",
    ],
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
    h_avail="Khả dụng và quy định địa phương",
    avail_note="Sooppiy không quyết định ai được dùng sàn nào — KYC của sàn và luật nơi bạn sống quyết định. Kết nối cổng ở đây không làm cho một sàn trở nên khả dụng với bạn, và sàn bạn không được phép dùng sẽ tự từ chối khóa của bạn. Đây là thông tin thực tế, không phải tư vấn pháp lý; quy định truy cập thay đổi, hãy xác nhận trên trang điều khoản của sàn cho quốc gia bạn.",
    h_before="Trước khi bắt đầu",
    before_steps=[
        "Một tài khoản tại {name} đã hoàn tất xác minh danh tính (KYC) — tài khoản chưa xác minh vẫn tạo được khóa nhưng không giao dịch được.",
        "Bật xác thực hai lớp (2FA) tại {name}. Mọi sàn đều yêu cầu mã 2FA (và thường cả xác nhận email) ngay khi bạn tạo khóa.",
        "Mở trang này cạnh website của sàn, và chuẩn bị nơi an toàn để giữ bí mật trong khoảnh khắc giữa lúc tạo và lúc kết nối.",
    ],
    h_paste="Giá trị nào điền vào đâu",
    paste_th=["Tên gọi tại {name}", "Ô nhập của Sooppiy"],
    once_warn="<b>Bí mật (secret)</b> chỉ hiển thị <b>đúng một lần</b> khi tạo. Nếu đóng màn hình mà chưa sao chép thì không thể khôi phục — bạn phải xóa khóa và tạo lại. Sooppiy cũng không hiển thị lại sau khi lưu.",
    ip_note="<b>Giới hạn IP — tạm thời đừng đặt.</b> Một số sàn cho phép khóa chỉ dùng được từ một địa chỉ máy chủ. Sooppiy sắp chuyển khu vực máy chủ, và khóa ghim theo địa chỉ cũ sẽ ngừng hoạt động ngay khi chuyển. Một điều nên ghi lại: Binance và Bybit vô hiệu hóa quyền giao dịch của khóa không giới hạn IP sau 90 ngày, hãy lên lịch xem lại khóa khi đó.",
    h_after="Sau khi kết nối",
    after_steps=[
        "Cổng xuất hiện trong <b>Cổng đã kết nối</b> kèm dòng trạng thái. Sàn dùng cặp khóa hiển thị “đã lưu thông tin xác thực” — bình thường, vì không có phiên nào để kiểm tra.",
        "Quy tắc tự động không tự chuyển. Lệnh chỉ tới {name} khi bạn đặt loại tài khoản của quy tắc đó là shadow hoặc live.",
        "Hãy bắt đầu ở <b>shadow</b> và xem bảng <b>Bản ghi lệch</b> vài ngày trước khi cân nhắc live.",
        "Thu hồi quyền bất cứ lúc nào bằng cách xóa khóa tại {name} — mọi lệnh dừng ngay, bất kể Sooppiy đang đặt gì.",
    ],
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
    h_avail="Ketersediaan dan aturan setempat",
    avail_note="Sooppiy tidak menentukan siapa yang boleh memakai suatu bursa — KYC bursa dan hukum setempat Andalah yang menentukan. Menghubungkan gateway di sini tidak membuat sebuah bursa tersedia bagi Anda, dan bursa yang tidak boleh Anda pakai secara hukum akan menolak kunci Anda. Ini panduan faktual, bukan nasihat hukum; aturan akses berubah, jadi konfirmasikan di halaman ketentuan bursa untuk negara Anda.",
    h_before="Sebelum mulai",
    before_steps=[
        "Akun di {name} yang sudah menyelesaikan verifikasi identitas (KYC) — akun belum terverifikasi bisa membuat kunci tetapi tidak bisa dipakai bertransaksi.",
        "Autentikasi dua faktor (2FA) aktif di {name}. Semua bursa meminta kode 2FA (dan sering konfirmasi email) tepat saat Anda membuat kunci.",
        "Halaman ini terbuka di samping situs bursa, dan tempat aman untuk menyimpan secret selama sesaat antara pembuatan dan penyambungan.",
    ],
    h_paste="Nilai mana masuk ke mana",
    paste_th=["Namanya di {name}", "Kolom isian Sooppiy"],
    once_warn="<b>Secret</b> hanya ditampilkan <b>satu kali</b> saat pembuatan. Jika Anda menutup layar tanpa menyalinnya, nilainya tidak bisa dipulihkan — Anda harus menghapus kunci dan membuat yang baru. Sooppiy juga tidak menampilkannya lagi setelah disimpan.",
    ip_note="<b>Pembatasan IP — biarkan kosong untuk saat ini.</b> Sebagian bursa memungkinkan mengunci kunci ke satu alamat server. Sooppiy sedang memindahkan wilayah hosting, dan kunci yang dipatok ke alamat lama akan berhenti bekerja begitu perpindahan terjadi. Satu hal untuk dicatat: Binance dan Bybit menonaktifkan izin trading kunci tanpa pembatasan IP setelah 90 hari, jadi rencanakan meninjau kunci saat itu.",
    h_after="Setelah terhubung",
    after_steps=[
        "Gateway muncul di <b>Gateway terhubung</b> dengan baris status. Bursa berbasis pasangan kunci menampilkan “kredensial tersimpan” — normal, karena tidak ada sesi untuk diperiksa.",
        "Aturan otomatisasi tidak berpindah sendiri. Order baru sampai ke {name} bila Anda menyetel jenis akun aturan tersebut ke shadow atau live.",
        "Mulailah di <b>shadow</b> dan baca panel <b>Catatan penyimpangan</b> selama beberapa hari sebelum mempertimbangkan live.",
        "Cabut akses kapan saja dengan menghapus kunci di {name} — semua order langsung berhenti, apa pun setelan Sooppiy.",
    ],
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
               "Enable <b>Reading</b> and <b>Spot &amp; Margin Trading</b>. Leave withdrawals disabled."],
        "ko": ["binance.com 로그인 → 프로필 아이콘 → <b>Account</b> → <b>API Management</b> → <b>Create API</b>(시스템 생성).",
               "<b>Reading</b>과 <b>Spot &amp; Margin Trading</b>을 활성화하세요. 출금은 비활성 상태로 두세요."],
        "ja": ["binance.comにログイン → プロフィール → <b>Account</b> → <b>API Management</b> → <b>Create API</b>(システム生成)。",
               "<b>Reading</b>と<b>Spot &amp; Margin Trading</b>を有効化。出金は無効のままにします。"],
        "th": ["เข้าสู่ระบบ binance.com → ไอคอนโปรไฟล์ → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (แบบ system-generated)",
               "เปิดใช้ <b>Reading</b> และ <b>Spot &amp; Margin Trading</b> ปล่อยการถอนเงินให้ปิดไว้"],
        "vi": ["Đăng nhập binance.com → biểu tượng hồ sơ → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (system-generated).",
               "Bật <b>Reading</b> và <b>Spot &amp; Margin Trading</b>. Giữ quyền rút tiền ở trạng thái tắt."],
        "id": ["Masuk ke binance.com → ikon profil → <b>Account</b> → <b>API Management</b> → <b>Create API</b> (system-generated).",
               "Aktifkan <b>Reading</b> dan <b>Spot &amp; Margin Trading</b>. Biarkan penarikan dana nonaktif."],
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
"coinbase": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at coinbase.com → profile → <b>Settings</b> → <b>API</b> (this opens the Coinbase Developer Platform portal) → <b>Create API key</b>.",
               "Under advanced settings choose <b>ECDSA</b> as the signature algorithm — <b>not Ed25519</b>. An Ed25519 key cannot sign for Advanced Trade and every request will fail.",
               "Permissions: <b>View</b> and <b>Trade</b>. Never Transfer.",
               "Download or copy the key file. The <b>key name</b> looks like <code>organizations/…/apiKeys/…</code> and the <b>private key</b> is a multi-line block starting with <code>BEGIN EC PRIVATE KEY</code>. Both go into Sooppiy exactly as they are — keep the private key's line breaks."],
        "ko": ["coinbase.com 로그인 → 프로필 → <b>Settings</b> → <b>API</b>(Coinbase Developer Platform 포털이 열립니다) → <b>Create API key</b>.",
               "고급 설정에서 서명 알고리즘으로 <b>ECDSA</b>를 선택하세요 — <b>Ed25519는 안 됩니다</b>. Ed25519 키는 Advanced Trade 서명에 쓸 수 없어 모든 요청이 실패합니다.",
               "권한: <b>View</b>와 <b>Trade</b>. Transfer(이체) 권한은 절대 안 됩니다.",
               "키 파일을 다운로드하거나 복사하세요. <b>키 이름</b>은 <code>organizations/…/apiKeys/…</code> 형태이고 <b>개인 키</b>는 <code>BEGIN EC PRIVATE KEY</code>로 시작하는 여러 줄 블록입니다. 두 값 모두 그대로 Sooppiy에 넣으세요 — 개인 키의 줄바꿈을 유지해야 합니다."],
        "ja": ["coinbase.comにログイン → プロフィール → <b>Settings</b> → <b>API</b>(Coinbase Developer Platformポータルが開きます) → <b>Create API key</b>。",
               "詳細設定で署名アルゴリズムに<b>ECDSA</b>を選択してください — <b>Ed25519は不可</b>。Ed25519キーはAdvanced Tradeの署名に使えず、すべてのリクエストが失敗します。",
               "権限: <b>View</b>と<b>Trade</b>。Transfer(送金)権限は絶対に不可。",
               "キーファイルをダウンロードまたはコピーします。<b>キー名</b>は<code>organizations/…/apiKeys/…</code>形式、<b>秘密鍵</b>は<code>BEGIN EC PRIVATE KEY</code>で始まる複数行のブロックです。どちらもそのままSooppiyに貼り付けてください — 秘密鍵の改行は保持すること。"],
        "th": ["เข้าสู่ระบบ coinbase.com → โปรไฟล์ → <b>Settings</b> → <b>API</b> (จะเปิดพอร์ทัล Coinbase Developer Platform) → <b>Create API key</b>",
               "ในการตั้งค่าขั้นสูง เลือกอัลกอริทึมลายเซ็นเป็น <b>ECDSA</b> — <b>ห้ามใช้ Ed25519</b> คีย์ Ed25519 เซ็นให้ Advanced Trade ไม่ได้ ทุกคำขอจะล้มเหลว",
               "สิทธิ์: <b>View</b> และ <b>Trade</b> ห้าม Transfer เด็ดขาด",
               "ดาวน์โหลดหรือคัดลอกไฟล์คีย์ <b>ชื่อคีย์</b>อยู่ในรูป <code>organizations/…/apiKeys/…</code> และ<b>คีย์ส่วนตัว</b>เป็นบล็อกหลายบรรทัดที่ขึ้นต้นด้วย <code>BEGIN EC PRIVATE KEY</code> ใส่ทั้งสองค่าใน Sooppiy ตามที่เป็น — คงการขึ้นบรรทัดใหม่ของคีย์ส่วนตัวไว้"],
        "vi": ["Đăng nhập coinbase.com → hồ sơ → <b>Settings</b> → <b>API</b> (mở cổng Coinbase Developer Platform) → <b>Create API key</b>.",
               "Trong cài đặt nâng cao, chọn thuật toán ký là <b>ECDSA</b> — <b>không phải Ed25519</b>. Khóa Ed25519 không ký được cho Advanced Trade và mọi yêu cầu sẽ thất bại.",
               "Quyền: <b>View</b> và <b>Trade</b>. Tuyệt đối không Transfer.",
               "Tải xuống hoặc sao chép tệp khóa. <b>Tên khóa</b> có dạng <code>organizations/…/apiKeys/…</code> và <b>khóa riêng tư</b> là khối nhiều dòng bắt đầu bằng <code>BEGIN EC PRIVATE KEY</code>. Dán cả hai vào Sooppiy nguyên trạng — giữ nguyên xuống dòng của khóa riêng tư."],
        "id": ["Masuk ke coinbase.com → profil → <b>Settings</b> → <b>API</b> (membuka portal Coinbase Developer Platform) → <b>Create API key</b>.",
               "Di pengaturan lanjutan pilih <b>ECDSA</b> sebagai algoritma tanda tangan — <b>bukan Ed25519</b>. Kunci Ed25519 tidak bisa menandatangani untuk Advanced Trade dan semua permintaan akan gagal.",
               "Izin: <b>View</b> dan <b>Trade</b>. Jangan pernah Transfer.",
               "Unduh atau salin berkas kunci. <b>Nama kunci</b> berbentuk <code>organizations/…/apiKeys/…</code> dan <b>kunci privat</b> adalah blok multibaris yang diawali <code>BEGIN EC PRIVATE KEY</code>. Masukkan keduanya ke Sooppiy apa adanya — pertahankan baris baru kunci privat."],
    },
    "shadow": {
        "en": "<b>shadow</b> — Coinbase has no test environment for Advanced Trade, so shadow uses Coinbase's own <b>order preview</b> call against your real account: authentication, product, size and balance are checked, but nothing is placed and no money moves. The venue's accept/reject answer is journalled.",
        "ko": "<b>shadow</b> — 코인베이스 Advanced Trade에는 테스트 환경이 없어서, 섀도는 실계정에 코인베이스 자체의 <b>주문 미리보기(preview)</b> 호출을 보냅니다. 인증·상품·수량·잔고는 검사되지만 주문은 접수되지 않고 돈도 움직이지 않습니다. 거래소의 승인/거부 응답이 기록됩니다.",
        "ja": "<b>shadow</b> — Coinbase Advanced Tradeにはテスト環境がないため、シャドーは実口座に対しCoinbase自身の<b>注文プレビュー</b>コールを送ります。認証・商品・数量・残高は検査されますが、注文は発注されず資金も動きません。取引所の承認/拒否の応答が記録されます。",
        "th": "<b>shadow</b> — Coinbase Advanced Trade ไม่มีสภาพแวดล้อมทดสอบ shadow จึงใช้คำสั่ง<b>พรีวิวออเดอร์</b>ของ Coinbase เองกับบัญชีจริงของคุณ: ตรวจการยืนยันตัวตน สินค้า ขนาด และยอดเงิน แต่ไม่มีการส่งคำสั่งจริงและเงินไม่เคลื่อนไหว คำตอบรับ/ปฏิเสธของกระดานถูกบันทึกไว้",
        "vi": "<b>shadow</b> — Coinbase không có môi trường thử nghiệm cho Advanced Trade, nên shadow dùng lệnh <b>xem trước đơn hàng (preview)</b> của chính Coinbase trên tài khoản thật: xác thực, sản phẩm, khối lượng và số dư được kiểm, nhưng không lệnh nào được đặt và tiền không di chuyển. Câu trả lời chấp nhận/từ chối của sàn được ghi lại.",
        "id": "<b>shadow</b> — Coinbase tidak punya lingkungan uji untuk Advanced Trade, jadi shadow memakai panggilan <b>pratinjau order</b> milik Coinbase pada akun asli Anda: autentikasi, produk, ukuran, dan saldo diperiksa, tetapi tidak ada order yang dipasang dan tidak ada dana bergerak. Jawaban terima/tolak bursa dicatat.",
    },
    "notes": {
        "en": ["The credential pair is unusual: the <b>API key</b> is a long resource name and the <b>secret</b> is a multi-line EC private key (PEM), not a random string. Paste the whole PEM including its BEGIN/END lines.",
               "Coinbase's main books quote in <b>USD</b>. Sooppiy translates its USDT symbols automatically (BTCUSDT → BTC-USD).",
               "Spot only — there is nothing to short on Coinbase spot.",
               "Sooppiy pins market buys to base-currency size — the quantity your rule sets is coins bought, never USD spent."],
        "ko": ["자격 증명 형태가 특이합니다: <b>API 키</b>는 긴 리소스 이름이고 <b>시크릿</b>은 임의 문자열이 아니라 여러 줄짜리 EC 개인 키(PEM)입니다. BEGIN/END 줄까지 포함해 PEM 전체를 붙여넣으세요.",
               "코인베이스 주요 마켓은 <b>USD</b> 호가입니다. Sooppiy가 USDT 심볼을 자동 변환합니다(BTCUSDT → BTC-USD).",
               "현물 전용입니다 — 코인베이스 현물에는 공매도가 없습니다.",
               "Sooppiy는 시장가 매수를 기초 통화 수량으로 고정합니다 — 규칙에 설정한 수량은 매수할 코인 수이지, 지출할 USD가 아닙니다."],
        "ja": ["資格情報の形が独特です: <b>APIキー</b>は長いリソース名で、<b>シークレット</b>はランダム文字列ではなく複数行のEC秘密鍵(PEM)です。BEGIN/END行を含むPEM全体を貼り付けてください。",
               "Coinbaseの主要マーケットは<b>USD</b>建てです。SooppiyがUSDTシンボルを自動変換します(BTCUSDT → BTC-USD)。",
               "現物のみ — Coinbase現物に空売りはありません。",
               "Sooppiyは成行買いを基軸通貨数量に固定します — ルールに設定した数量は購入するコイン数であり、支出するUSDではありません。"],
        "th": ["ข้อมูลรับรองมีรูปแบบพิเศษ: <b>คีย์ API</b> เป็นชื่อรีซอร์สยาว และ<b>ซีเคร็ต</b>คือคีย์ส่วนตัว EC หลายบรรทัด (PEM) ไม่ใช่สตริงสุ่ม วางทั้ง PEM รวมบรรทัด BEGIN/END",
               "กระดานหลักของ Coinbase อ้างอิงราคาเป็น <b>USD</b> — Sooppiy แปลงสัญลักษณ์ USDT ให้อัตโนมัติ (BTCUSDT → BTC-USD)",
               "สปอตเท่านั้น — สปอตของ Coinbase ไม่มีการชอร์ต",
               "Sooppiy ตรึงการซื้อ market ด้วยขนาดสกุลเงินฐาน — จำนวนที่กฎกำหนดคือจำนวนเหรียญที่ซื้อ ไม่ใช่จำนวน USD ที่จ่าย"],
        "vi": ["Cặp thông tin xác thực khác thường: <b>khóa API</b> là tên tài nguyên dài và <b>bí mật</b> là khóa riêng tư EC nhiều dòng (PEM), không phải chuỗi ngẫu nhiên. Dán toàn bộ PEM gồm cả dòng BEGIN/END.",
               "Các sổ lệnh chính của Coinbase định giá bằng <b>USD</b>. Sooppiy tự động chuyển ký hiệu USDT (BTCUSDT → BTC-USD).",
               "Chỉ spot — spot của Coinbase không có bán khống.",
               "Sooppiy cố định mua market theo số lượng tiền gốc — số mà quy tắc đặt là coin mua vào, không phải USD chi ra."],
        "id": ["Pasangan kredensialnya tidak biasa: <b>kunci API</b> adalah nama resource panjang dan <b>secret</b>-nya adalah kunci privat EC multibaris (PEM), bukan string acak. Tempel seluruh PEM termasuk baris BEGIN/END.",
               "Pasar utama Coinbase dikutip dalam <b>USD</b>. Sooppiy menerjemahkan simbol USDT otomatis (BTCUSDT → BTC-USD).",
               "Spot saja — spot Coinbase tidak punya short.",
               "Sooppiy mengunci market buy pada ukuran mata uang dasar — jumlah yang diatur aturan adalah koin yang dibeli, bukan USD yang dibelanjakan."],
    },
    "trouble": {
        "en": [("“credentials could not be used to sign the request”",
                "The stored private key is not a loadable ECDSA PEM — most often an Ed25519 key, or a PEM that lost its line breaks in pasting. Create an ECDSA key and paste the whole block again."),
               ("401 Unauthorized on every call",
                "The key name and private key do not belong together, or the key was revoked in the Developer Platform portal. Reconnect with a freshly created pair.")],
        "ko": [("“credentials could not be used to sign the request”",
                "저장된 개인 키를 ECDSA PEM으로 읽을 수 없습니다 — 대개 Ed25519 키이거나, 붙여넣을 때 줄바꿈이 사라진 PEM입니다. ECDSA 키를 만들어 블록 전체를 다시 붙여넣으세요."),
               ("모든 호출에서 401 Unauthorized",
                "키 이름과 개인 키가 서로 짝이 아니거나, Developer Platform 포털에서 키가 폐기되었습니다. 새로 만든 쌍으로 다시 연결하세요.")],
        "ja": [("“credentials could not be used to sign the request”",
                "保存された秘密鍵をECDSA PEMとして読み込めません — 多くはEd25519キーか、貼り付け時に改行が失われたPEMです。ECDSAキーを作成しブロック全体を貼り直してください。"),
               ("すべての呼び出しで401 Unauthorized",
                "キー名と秘密鍵が対応していないか、Developer Platformポータルでキーが失効しています。新しく作成したペアで再接続してください。")],
        "th": [("“credentials could not be used to sign the request”",
                "คีย์ส่วนตัวที่บันทึกอ่านเป็น ECDSA PEM ไม่ได้ — ส่วนใหญ่เป็นคีย์ Ed25519 หรือ PEM ที่การขึ้นบรรทัดหายตอนวาง สร้างคีย์ ECDSA แล้ววางทั้งบล็อกใหม่"),
               ("401 Unauthorized ทุกคำขอ",
                "ชื่อคีย์กับคีย์ส่วนตัวไม่ใช่คู่กัน หรือคีย์ถูกเพิกถอนในพอร์ทัล Developer Platform — เชื่อมต่อใหม่ด้วยคู่ที่สร้างใหม่")],
        "vi": [("“credentials could not be used to sign the request”",
                "Khóa riêng tư đã lưu không đọc được dưới dạng ECDSA PEM — thường là khóa Ed25519, hoặc PEM mất xuống dòng khi dán. Tạo khóa ECDSA và dán lại toàn bộ khối."),
               ("401 Unauthorized ở mọi yêu cầu",
                "Tên khóa và khóa riêng tư không thuộc về nhau, hoặc khóa đã bị thu hồi trong cổng Developer Platform. Kết nối lại bằng cặp mới tạo.")],
        "id": [("“credentials could not be used to sign the request”",
                "Kunci privat tersimpan tidak bisa dibaca sebagai ECDSA PEM — paling sering kunci Ed25519, atau PEM yang kehilangan baris barunya saat ditempel. Buat kunci ECDSA dan tempel ulang seluruh blok."),
               ("401 Unauthorized di setiap panggilan",
                "Nama kunci dan kunci privat bukan pasangan, atau kuncinya dicabut di portal Developer Platform. Hubungkan ulang dengan pasangan yang baru dibuat.")],
    },
},
"webull": {
    "fields": ["key", "secret"],
    "steps": {
        "en": ["Log in at developer.webull.com with your Webull account and open <b>Developer Console → API Keys</b>.",
               "Create an application to get an <b>App Key</b> and <b>App Secret</b>. The secret is shown once. Production approval can take 1–2 business days.",
               "For shadow mode, switch the console to <b>paperTrade</b> and apply for OpenAPI for PaperTrade — that gives a separate App Key/Secret pair for the PaperTrade environment. Use the PaperTrade pair while you run shadow; replace it with the production pair when you go live."],
        "ko": ["Webull 계정으로 developer.webull.com에 로그인해 <b>Developer Console → API Keys</b>를 엽니다.",
               "애플리케이션을 만들어 <b>App Key</b>와 <b>App Secret</b>을 받습니다. 시크릿은 한 번만 표시됩니다. 실계좌(Production) 승인은 영업일 기준 1–2일 걸릴 수 있습니다.",
               "shadow 모드용으로는 콘솔을 <b>paperTrade</b>로 전환해 PaperTrade용 OpenAPI를 신청하세요 — PaperTrade 환경 전용의 별도 App Key/Secret이 발급됩니다. shadow 동안에는 PaperTrade 키를, 실거래 전환 시 Production 키로 교체하세요."],
        "ja": ["Webullアカウントでdeveloper.webull.comにログインし、<b>Developer Console → API Keys</b>を開きます。",
               "アプリケーションを作成して<b>App Key</b>と<b>App Secret</b>を取得します。シークレットは一度だけ表示されます。本番の承認には1–2営業日かかることがあります。",
               "shadowモード用には、コンソールを<b>paperTrade</b>に切り替えてPaperTrade用OpenAPIを申請してください — PaperTrade環境専用の別のApp Key/Secretが発行されます。shadow中はPaperTradeキー、実取引時に本番キーへ差し替えてください。"],
        "th": ["เข้าสู่ระบบ developer.webull.com ด้วยบัญชี Webull แล้วเปิด <b>Developer Console → API Keys</b>",
               "สร้างแอปพลิเคชันเพื่อรับ <b>App Key</b> และ <b>App Secret</b> ความลับจะแสดงเพียงครั้งเดียว การอนุมัติ production อาจใช้เวลา 1–2 วันทำการ",
               "สำหรับโหมด shadow ให้สลับคอนโซลเป็น <b>paperTrade</b> แล้วขอ OpenAPI สำหรับ PaperTrade — จะได้ App Key/Secret แยกสำหรับสภาพแวดล้อม PaperTrade ใช้คู่ PaperTrade ระหว่างรัน shadow และเปลี่ยนเป็นคู่ production เมื่อเทรดจริง"],
        "vi": ["Đăng nhập developer.webull.com bằng tài khoản Webull và mở <b>Developer Console → API Keys</b>.",
               "Tạo ứng dụng để nhận <b>App Key</b> và <b>App Secret</b>. Bí mật chỉ hiển thị một lần. Duyệt production có thể mất 1–2 ngày làm việc.",
               "Với chế độ shadow, chuyển console sang <b>paperTrade</b> và đăng ký OpenAPI cho PaperTrade — bạn nhận cặp App Key/Secret riêng cho môi trường PaperTrade. Dùng cặp PaperTrade khi chạy shadow; thay bằng cặp production khi lên live."],
        "id": ["Masuk ke developer.webull.com dengan akun Webull Anda dan buka <b>Developer Console → API Keys</b>.",
               "Buat aplikasi untuk mendapatkan <b>App Key</b> dan <b>App Secret</b>. Secret hanya ditampilkan sekali. Persetujuan production bisa memakan 1–2 hari kerja.",
               "Untuk mode shadow, alihkan konsol ke <b>paperTrade</b> dan ajukan OpenAPI untuk PaperTrade — Anda mendapat pasangan App Key/Secret terpisah untuk lingkungan PaperTrade. Pakai pasangan PaperTrade selama shadow; ganti ke pasangan production saat live."],
    },
    "shadow": {
        "en": "<b>shadow</b> — fills stay simulated and the same order is ALSO sent to Webull's <b>PaperTrade</b> environment for comparison; the drift is journalled. This needs PaperTrade app keys.",
        "ko": "<b>shadow</b> — 체결은 시뮬레이션으로 유지되고 같은 주문이 비교용으로 Webull <b>PaperTrade</b> 환경에도 전송되며 차이가 기록됩니다. PaperTrade용 앱 키가 필요합니다.",
        "ja": "<b>shadow</b> — 約定はシミュレーションのまま、同じ注文が比較用にWebullの<b>PaperTrade</b>環境にも送信され、差異が記録されます。PaperTrade用のアプリキーが必要です。",
        "th": "<b>shadow</b> — การจับคู่ยังเป็นการจำลอง และคำสั่งเดียวกันถูกส่งไปยังสภาพแวดล้อม <b>PaperTrade</b> ของ Webull เพื่อเปรียบเทียบ และบันทึกส่วนต่าง ต้องใช้คีย์แอป PaperTrade",
        "vi": "<b>shadow</b> — khớp lệnh vẫn là mô phỏng và lệnh đó được gửi tới môi trường <b>PaperTrade</b> của Webull để so sánh; chênh lệch được ghi lại. Cần khóa ứng dụng PaperTrade.",
        "id": "<b>shadow</b> — eksekusi tetap simulasi dan order yang sama dikirim ke lingkungan <b>PaperTrade</b> Webull untuk perbandingan; selisihnya dicatat. Ini membutuhkan kunci aplikasi PaperTrade.",
    },
    "notes": {
        "en": ["US stocks only, spot and long-only: buys and sells are sent as market DAY orders in the regular session. Short and cover orders are never sent to Webull.",
               "If your Webull login holds more than one account, enter the <b>account id</b> in the optional field when you connect — Sooppiy will not guess between accounts. With one account (or one cash account) it is found automatically.",
               "Production apps can have Webull's two-factor token switched on. Sooppiy does not create that token yet; an app that requires it answers 401 and the order is refused, never filled on paper."],
        "ko": ["미국 주식 현물·롱 전용입니다: 매수와 매도는 정규장 시장가 DAY 주문으로 전송됩니다. 공매도(short)와 상환(cover) 주문은 Webull로 절대 전송되지 않습니다.",
               "Webull 로그인에 계좌가 둘 이상이면 연결할 때 선택 입력란에 <b>계좌 ID</b>를 입력하세요 — Sooppiy는 계좌를 추측하지 않습니다. 계좌가 하나(또는 현금 계좌가 하나)면 자동으로 찾습니다.",
               "Production 앱은 Webull 2단계 인증 토큰이 켜져 있을 수 있습니다. Sooppiy는 아직 그 토큰을 만들지 않으며, 토큰이 필요한 앱은 401로 응답해 주문이 거부됩니다 — 모의로 체결되는 일은 없습니다."],
        "ja": ["米国株の現物・ロングのみです: 買いと売りは通常取引時間の成行DAY注文として送信されます。空売り(short)と買い戻し(cover)はWebullに送信されません。",
               "Webullのログインに複数の口座がある場合は、接続時に任意欄へ<b>口座ID</b>を入力してください — Sooppiyは口座を推測しません。口座が1つ(または現金口座が1つ)なら自動で見つけます。",
               "本番アプリではWebullの二段階認証トークンが有効な場合があります。Sooppiyはまだそのトークンを作成しません。トークンが必要なアプリは401を返し、注文は拒否されます — ペーパーで約定することはありません。"],
        "th": ["เฉพาะหุ้นสหรัฐฯ แบบ spot และซื้ออย่างเดียว: คำสั่งซื้อและขายส่งเป็นคำสั่ง market DAY ในช่วงตลาดปกติ คำสั่ง short และ cover จะไม่ถูกส่งไป Webull",
               "ถ้าบัญชีล็อกอิน Webull มีมากกว่าหนึ่งบัญชี ให้กรอก <b>รหัสบัญชี</b> ในช่องที่ไม่บังคับตอนเชื่อมต่อ — Sooppiy จะไม่เดาบัญชีให้ ถ้ามีบัญชีเดียว (หรือบัญชีเงินสดเดียว) จะหาให้อัตโนมัติ",
               "แอป production อาจเปิดโทเค็นยืนยันสองขั้นของ Webull ไว้ Sooppiy ยังไม่สร้างโทเค็นนั้น แอปที่ต้องใช้โทเค็นจะตอบ 401 และคำสั่งถูกปฏิเสธ — ไม่มีการจับคู่แบบกระดาษแทน"],
        "vi": ["Chỉ cổ phiếu Mỹ, giao ngay và chỉ mua: lệnh mua và bán được gửi dạng lệnh thị trường DAY trong phiên chính. Lệnh short và cover không bao giờ được gửi tới Webull.",
               "Nếu đăng nhập Webull có nhiều tài khoản, hãy nhập <b>mã tài khoản</b> vào ô tùy chọn khi kết nối — Sooppiy không đoán tài khoản. Với một tài khoản (hoặc một tài khoản tiền mặt) hệ thống tự tìm.",
               "Ứng dụng production có thể bật token xác thực hai lớp của Webull. Sooppiy chưa tạo token đó; ứng dụng cần token sẽ trả 401 và lệnh bị từ chối — không bao giờ khớp giả lập thay thế."],
        "id": ["Hanya saham AS, spot dan long saja: beli dan jual dikirim sebagai order market DAY di sesi reguler. Order short dan cover tidak pernah dikirim ke Webull.",
               "Jika login Webull Anda memiliki lebih dari satu akun, isi <b>ID akun</b> di kolom opsional saat menghubungkan — Sooppiy tidak menebak akun. Dengan satu akun (atau satu akun tunai) akun ditemukan otomatis.",
               "Aplikasi production bisa mengaktifkan token dua faktor Webull. Sooppiy belum membuat token itu; aplikasi yang memerlukannya menjawab 401 dan order ditolak — tidak pernah dieksekusi sebagai simulasi."],
    },
    "trouble": {
        "en": [("401 on every order", "Production keys used in shadow (PaperTrade) or the reverse, a revoked key, or the app requires a two-factor token. Match the key pair to the mode you are in."),
               ("“Webull returned N accounts”", "Your login holds several accounts. Reconnect and enter the account id of the one to trade.")],
        "ko": [("모든 주문에서 401", "Production 키를 shadow(PaperTrade)에 쓰거나 그 반대, 폐기된 키, 또는 앱이 2단계 인증 토큰을 요구하는 경우입니다. 현재 모드에 맞는 키 쌍인지 확인하세요."),
               ("“Webull returned N accounts”", "로그인에 계좌가 여러 개 있습니다. 다시 연결하면서 거래할 계좌의 ID를 입력하세요.")],
        "ja": [("すべての注文で401", "本番キーをshadow(PaperTrade)で使っている、またはその逆、失効したキー、あるいはアプリが二段階認証トークンを要求しています。モードに合ったキーペアか確認してください。"),
               ("“Webull returned N accounts”", "ログインに複数の口座があります。再接続して取引する口座のIDを入力してください。")],
        "th": [("401 กับทุกคำสั่ง", "ใช้คีย์ production ใน shadow (PaperTrade) หรือกลับกัน คีย์ถูกเพิกถอน หรือแอปต้องใช้โทเค็นยืนยันสองขั้น ให้ใช้คู่คีย์ที่ตรงกับโหมด"),
               ("“Webull returned N accounts”", "ล็อกอินของคุณมีหลายบัญชี เชื่อมต่อใหม่แล้วกรอกรหัสบัญชีที่จะเทรด")],
        "vi": [("401 với mọi lệnh", "Dùng khóa production cho shadow (PaperTrade) hoặc ngược lại, khóa bị thu hồi, hoặc ứng dụng yêu cầu token hai lớp. Khớp cặp khóa với chế độ đang dùng."),
               ("“Webull returned N accounts”", "Đăng nhập của bạn có nhiều tài khoản. Kết nối lại và nhập mã tài khoản muốn giao dịch.")],
        "id": [("401 pada setiap order", "Kunci production dipakai di shadow (PaperTrade) atau sebaliknya, kunci dicabut, atau aplikasi mewajibkan token dua faktor. Cocokkan pasangan kunci dengan mode yang dipakai."),
               ("“Webull returned N accounts”", "Login Anda memiliki beberapa akun. Hubungkan ulang dan isi ID akun yang akan diperdagangkan.")],
    },
},
}

TITLES = {
    "webull":   {"en": "Connect Webull", "ko": "Webull 연결 가이드", "ja": "Webull接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Webull", "vi": "Hướng dẫn kết nối Webull", "id": "Panduan Menghubungkan Webull"},
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
    "coinbase": {"en": "Connect Coinbase", "ko": "코인베이스 연결 가이드", "ja": "Coinbase接続ガイド",
                 "th": "คู่มือเชื่อมต่อ Coinbase", "vi": "Hướng dẫn kết nối Coinbase", "id": "Panduan Menghubungkan Coinbase"},
}


# What the venue calls each credential → the Sooppiy connect-form field it
# belongs in. This is the step members get wrong most often: the venue's
# wording rarely matches ours (Alpaca "Key ID", Kraken "Private Key",
# Upbit "Access key").
PASTE_MAP = {
    "binance":   [("API Key", "key"), ("Secret Key", "secret")],
    "alpaca":    [("API Key ID", "key"), ("Secret Key", "secret")],
    "ibkr":      [("The address you log in to the gateway at", "gwurl"),
                  ("Account id shown in the Client Portal", "acct")],
    "bybit":     [("API Key", "key"), ("API Secret", "secret")],
    "okx":       [("API key", "key"), ("Secret key", "secret"), ("Passphrase", "pass")],
    "kraken":    [("API Key", "key"), ("Private Key", "secret")],
    "cryptocom": [("API Key", "key"), ("Secret Key", "secret")],
    "upbit":     [("Access key (액세스 키)", "key"), ("Secret key (시크릿 키)", "secret")],
    "kucoin":    [("API Key", "key"), ("API Secret", "secret"), ("API Passphrase", "pass")],
    "coinbase":  [("API key name (organizations/…/apiKeys/…)", "key"),
                  ("Private key — the whole PEM block", "secret")],
    "webull":    [("App Key", "key"), ("App Secret", "secret")],
}


# Where each venue may legally be used. FACTS a member needs before spending
# time on a key — not legal advice, and deliberately phrased so: eligibility is
# decided by the venue's own KYC and by the member's local law, never by
# Sooppiy. Verify against the venue's current terms; access rules change.
AVAIL = {
"binance": {
 "en": "Not available to residents of the <b>United States</b> — binance.com blocks US users, and Binance.US is a separate company Sooppiy does not connect to. Restricted or limited in several other jurisdictions; derivatives access varies by country. Your eligibility is settled at Binance's own KYC.",
 "ko": "<b>미국</b> 거주자는 이용할 수 없습니다 — binance.com은 미국 사용자를 차단하며, Binance.US는 별개 회사로 Sooppiy가 연결하지 않습니다. 일부 국가에서는 이용이 제한되며 파생상품 접근 범위도 국가마다 다릅니다. 최종 가입 가능 여부는 바이낸스의 KYC에서 결정됩니다.",
 "ja": "<b>米国</b>居住者は利用できません — binance.comは米国ユーザーをブロックしており、Binance.USはSooppiyが接続しない別会社です。他のいくつかの法域でも制限があり、デリバティブの提供範囲は国により異なります。最終的な可否はBinanceのKYCで決まります。",
 "th": "ผู้พำนักใน<b>สหรัฐอเมริกา</b>ใช้ไม่ได้ — binance.com บล็อกผู้ใช้สหรัฐฯ และ Binance.US เป็นบริษัทแยกที่ Sooppiy ไม่ได้เชื่อมต่อ บางเขตอำนาจศาลมีข้อจำกัด และการเข้าถึงอนุพันธ์ต่างกันไปตามประเทศ สิทธิ์ของคุณตัดสินที่ KYC ของ Binance เอง",
 "vi": "Không khả dụng với người cư trú tại <b>Hoa Kỳ</b> — binance.com chặn người dùng Mỹ, và Binance.US là công ty riêng mà Sooppiy không kết nối. Bị hạn chế ở một số khu vực pháp lý khác; quyền truy cập phái sinh khác nhau theo quốc gia. Điều kiện của bạn do KYC của Binance quyết định.",
 "id": "Tidak tersedia bagi penduduk <b>Amerika Serikat</b> — binance.com memblokir pengguna AS, dan Binance.US adalah perusahaan terpisah yang tidak dihubungkan Sooppiy. Dibatasi di beberapa yurisdiksi lain; akses derivatif berbeda per negara. Kelayakan Anda ditentukan oleh KYC Binance sendiri."},
"bybit": {
 "en": "Not available to residents of the <b>United States</b>. Restricted in several other jurisdictions and unavailable to UK retail users for derivatives. Check Bybit's restricted-country list before creating a key.",
 "ko": "<b>미국</b> 거주자는 이용할 수 없습니다. 일부 국가에서도 제한되며 영국 개인 투자자는 파생상품을 이용할 수 없습니다. 키를 만들기 전에 바이비트의 제한 국가 목록을 확인하세요.",
 "ja": "<b>米国</b>居住者は利用できません。他のいくつかの法域でも制限があり、英国のリテール利用者はデリバティブを利用できません。キー作成前にBybitの制限国リストを確認してください。",
 "th": "ผู้พำนักใน<b>สหรัฐอเมริกา</b>ใช้ไม่ได้ มีข้อจำกัดในบางเขตอำนาจศาล และผู้ใช้รายย่อยในสหราชอาณาจักรใช้อนุพันธ์ไม่ได้ ตรวจรายชื่อประเทศที่ถูกจำกัดของ Bybit ก่อนสร้างคีย์",
 "vi": "Không khả dụng với người cư trú tại <b>Hoa Kỳ</b>. Bị hạn chế ở một số khu vực khác và người dùng cá nhân tại Anh không dùng được phái sinh. Hãy kiểm tra danh sách quốc gia bị hạn chế của Bybit trước khi tạo khóa.",
 "id": "Tidak tersedia bagi penduduk <b>Amerika Serikat</b>. Dibatasi di beberapa yurisdiksi lain dan pengguna ritel Inggris tidak dapat mengakses derivatif. Periksa daftar negara terbatas Bybit sebelum membuat kunci."},
"okx": {
 "en": "Not available to residents of the <b>United States</b>. Availability elsewhere varies — OKX operates licensed entities in some markets (including Singapore) and restricts others.",
 "ko": "<b>미국</b> 거주자는 이용할 수 없습니다. 그 외 지역은 국가별로 다르며, OKX는 일부 시장(싱가포르 등)에서 라이선스 법인을 운영하고 다른 지역은 제한합니다.",
 "ja": "<b>米国</b>居住者は利用できません。その他の地域は国により異なり、OKXは一部市場(シンガポールなど)でライセンス法人を運営し、他地域は制限しています。",
 "th": "ผู้พำนักใน<b>สหรัฐอเมริกา</b>ใช้ไม่ได้ พื้นที่อื่นแตกต่างกันไป — OKX มีนิติบุคคลที่ได้รับใบอนุญาตในบางตลาด (รวมสิงคโปร์) และจำกัดในบางแห่ง",
 "vi": "Không khả dụng với người cư trú tại <b>Hoa Kỳ</b>. Nơi khác thì khác nhau — OKX vận hành pháp nhân được cấp phép ở một số thị trường (gồm Singapore) và hạn chế ở nơi khác.",
 "id": "Tidak tersedia bagi penduduk <b>Amerika Serikat</b>. Ketersediaan di tempat lain bervariasi — OKX mengoperasikan entitas berlisensi di beberapa pasar (termasuk Singapura) dan membatasi yang lain."},
"kraken": {
 "en": "One of the few venues here that <b>does serve US residents</b> (most states), alongside the EU, UK, Japan and much of Asia. Product availability still varies by country and by US state.",
 "ko": "여기 있는 거래소 중 <b>미국 거주자를 지원하는</b> 몇 안 되는 곳입니다(대부분의 주). EU·영국·일본과 아시아 상당 지역도 지원합니다. 다만 상품별 이용 가능 범위는 국가와 미국 주에 따라 다릅니다.",
 "ja": "ここに挙げた取引所の中で<b>米国居住者に対応する</b>数少ない一つです(大半の州)。EU・英国・日本およびアジアの多くも対象です。ただし取扱商品は国や米国の州により異なります。",
 "th": "เป็นหนึ่งในไม่กี่กระดานที่นี่ที่<b>ให้บริการผู้พำนักในสหรัฐฯ</b> (เกือบทุกรัฐ) รวมถึงสหภาพยุโรป สหราชอาณาจักร ญี่ปุ่น และเอเชียส่วนใหญ่ ผลิตภัณฑ์ที่ใช้ได้ยังต่างกันตามประเทศและรัฐ",
 "vi": "Một trong số ít sàn ở đây <b>có phục vụ người cư trú Hoa Kỳ</b> (hầu hết các bang), cùng EU, Anh, Nhật Bản và phần lớn châu Á. Sản phẩm khả dụng vẫn khác nhau theo quốc gia và theo bang.",
 "id": "Salah satu dari sedikit bursa di sini yang <b>melayani penduduk AS</b> (sebagian besar negara bagian), selain UE, Inggris, Jepang, dan sebagian besar Asia. Ketersediaan produk tetap berbeda per negara dan per negara bagian."},
"cryptocom": {
 "en": "The Exchange serves many markets including the <b>United States</b> in most states, but product access differs by country and state — and the Exchange is a different service from the Crypto.com App.",
 "ko": "거래소(Exchange)는 <b>미국</b>을 포함한 다수 시장을 지원하지만(대부분의 주), 상품별 이용 범위는 국가·주에 따라 다릅니다. 또한 Exchange는 Crypto.com 앱과 별개 서비스입니다.",
 "ja": "Exchangeは<b>米国</b>(大半の州)を含む多くの市場に対応しますが、取扱商品は国や州により異なります。またExchangeはCrypto.comアプリとは別のサービスです。",
 "th": "Exchange ให้บริการหลายตลาดรวมถึง<b>สหรัฐอเมริกา</b>ในเกือบทุกรัฐ แต่การเข้าถึงผลิตภัณฑ์ต่างกันตามประเทศและรัฐ และ Exchange เป็นคนละบริการกับแอป Crypto.com",
 "vi": "Sàn phục vụ nhiều thị trường gồm <b>Hoa Kỳ</b> ở hầu hết các bang, nhưng quyền truy cập sản phẩm khác nhau theo quốc gia và bang — và Exchange là dịch vụ khác với ứng dụng Crypto.com.",
 "id": "Exchange melayani banyak pasar termasuk <b>Amerika Serikat</b> di sebagian besar negara bagian, tetapi akses produk berbeda per negara dan negara bagian — dan Exchange adalah layanan berbeda dari aplikasi Crypto.com."},
"upbit": {
 "en": "A <b>Korean</b> exchange operating under Korea's VASP registration. Practically it requires Korean residency, a Korean phone number and a linked K-Bank account for KRW deposits. Non-residents generally cannot complete verification.",
 "ko": "국내 VASP 신고를 마친 <b>한국</b> 거래소입니다. 실질적으로 국내 거주·국내 휴대전화·KRW 입금용 케이뱅크 계좌 연동이 필요하며, 비거주자는 일반적으로 인증을 완료할 수 없습니다.",
 "ja": "韓国のVASP登録の下で運営される<b>韓国</b>の取引所です。実務上、韓国在住・韓国の電話番号・KRW入金用のK-Bank口座連携が必要で、非居住者は通常、認証を完了できません。",
 "th": "เป็นกระดานของ<b>เกาหลีใต้</b> ที่ดำเนินการภายใต้การจดทะเบียน VASP ของเกาหลี ในทางปฏิบัติต้องพำนักในเกาหลี มีเบอร์โทรเกาหลี และผูกบัญชี K-Bank สำหรับฝากเงิน KRW ผู้ที่ไม่ได้พำนักมักยืนยันตัวตนไม่ผ่าน",
 "vi": "Là sàn của <b>Hàn Quốc</b> hoạt động theo đăng ký VASP của Hàn Quốc. Trên thực tế cần cư trú tại Hàn Quốc, số điện thoại Hàn Quốc và tài khoản K-Bank liên kết để nạp KRW. Người không cư trú thường không hoàn tất được xác minh.",
 "id": "Bursa <b>Korea Selatan</b> yang beroperasi di bawah registrasi VASP Korea. Praktisnya memerlukan domisili Korea, nomor telepon Korea, dan rekening K-Bank tertaut untuk setoran KRW. Non-penduduk umumnya tidak dapat menyelesaikan verifikasi."},
"kucoin": {
 "en": "Not available to residents of the <b>United States</b>. Availability elsewhere varies and verification level affects limits — check KuCoin's terms for your country before creating a key.",
 "ko": "<b>미국</b> 거주자는 이용할 수 없습니다. 그 외 지역은 국가별로 다르고 인증 등급에 따라 한도가 달라지므로, 키를 만들기 전에 거주 국가 기준 약관을 확인하세요.",
 "ja": "<b>米国</b>居住者は利用できません。その他の地域は国により異なり、認証レベルで上限が変わります。キー作成前に居住国の規約を確認してください。",
 "th": "ผู้พำนักใน<b>สหรัฐอเมริกา</b>ใช้ไม่ได้ พื้นที่อื่นแตกต่างกันและระดับการยืนยันตัวตนมีผลต่อวงเงิน ตรวจข้อกำหนดสำหรับประเทศของคุณก่อนสร้างคีย์",
 "vi": "Không khả dụng với người cư trú tại <b>Hoa Kỳ</b>. Nơi khác thì khác nhau và mức xác minh ảnh hưởng tới hạn mức — hãy xem điều khoản cho quốc gia của bạn trước khi tạo khóa.",
 "id": "Tidak tersedia bagi penduduk <b>Amerika Serikat</b>. Ketersediaan di tempat lain bervariasi dan tingkat verifikasi memengaruhi limit — periksa ketentuan untuk negara Anda sebelum membuat kunci."},
"coinbase": {
 "en": "A <b>US-regulated</b> exchange serving the <b>United States</b> (most states) and 100+ other countries. One of the two crypto venues here a US resident can actually use — product availability still varies by state and country.",
 "ko": "<b>미국</b>(대부분의 주)과 100여 개국을 지원하는 <b>미국 규제</b> 거래소입니다. 여기 있는 암호화폐 거래소 중 미국 거주자가 실제로 이용할 수 있는 두 곳 중 하나이며, 상품별 이용 범위는 주·국가에 따라 다릅니다.",
 "ja": "<b>米国</b>(大半の州)と100か国以上に対応する<b>米国規制</b>の取引所です。ここに挙げた暗号資産取引所の中で米国居住者が実際に利用できる2つのうちの1つで、取扱商品は州や国により異なります。",
 "th": "กระดานที่<b>กำกับดูแลโดยสหรัฐฯ</b> ให้บริการ<b>สหรัฐอเมริกา</b> (เกือบทุกรัฐ) และอีกกว่า 100 ประเทศ เป็นหนึ่งในสองกระดานคริปโตที่นี่ที่ผู้พำนักในสหรัฐฯ ใช้ได้จริง — ผลิตภัณฑ์ที่ใช้ได้ต่างกันตามรัฐและประเทศ",
 "vi": "Sàn <b>chịu quản lý của Hoa Kỳ</b>, phục vụ <b>Hoa Kỳ</b> (hầu hết các bang) và hơn 100 quốc gia khác. Một trong hai sàn crypto ở đây mà người cư trú Mỹ thực sự dùng được — sản phẩm khả dụng vẫn khác nhau theo bang và quốc gia.",
 "id": "Bursa <b>teregulasi AS</b> yang melayani <b>Amerika Serikat</b> (sebagian besar negara bagian) dan 100+ negara lain. Salah satu dari dua bursa kripto di sini yang benar-benar bisa dipakai penduduk AS — ketersediaan produk tetap berbeda per negara bagian dan negara."},
"alpaca": {
 "en": "A <b>US broker-dealer</b> for US-listed stocks. It serves US residents and a list of supported non-US countries — check that list before opening the account. US market hours and pattern-day-trading rules apply to your account, not to Sooppiy.",
 "ko": "미국 상장 주식을 다루는 <b>미국 브로커-딜러</b>입니다. 미국 거주자와 지원 국가 목록의 해외 거주자를 대상으로 하니 계좌 개설 전 목록을 확인하세요. 미국 장 시간과 패턴 데이트레이딩(PDT) 규정은 Sooppiy가 아니라 회원님 계좌에 적용됩니다.",
 "ja": "米国上場株を扱う<b>米国のブローカーディーラー</b>です。米国居住者と対応国リストの海外居住者が対象なので、口座開設前にリストを確認してください。米国市場の時間とパターンデイトレード規制は、Sooppiyではなくご自身の口座に適用されます。",
 "th": "เป็น<b>โบรกเกอร์-ดีลเลอร์สหรัฐฯ</b> สำหรับหุ้นจดทะเบียนในสหรัฐฯ ให้บริการผู้พำนักในสหรัฐฯ และประเทศที่รองรับ ตรวจรายชื่อก่อนเปิดบัญชี เวลาทำการตลาดสหรัฐฯ และกฎ pattern day trading ใช้กับบัญชีของคุณ ไม่ใช่กับ Sooppiy",
 "vi": "Là <b>broker-dealer Hoa Kỳ</b> cho cổ phiếu niêm yết tại Mỹ. Phục vụ người cư trú Mỹ và danh sách quốc gia được hỗ trợ — hãy kiểm tra danh sách trước khi mở tài khoản. Giờ giao dịch Mỹ và quy định pattern day trading áp dụng cho tài khoản của bạn, không phải Sooppiy.",
 "id": "Sebuah <b>broker-dealer AS</b> untuk saham yang tercatat di AS. Melayani penduduk AS dan daftar negara yang didukung — periksa daftar itu sebelum membuka akun. Jam pasar AS dan aturan pattern day trading berlaku pada akun Anda, bukan pada Sooppiy."},
"ibkr": {
 "en": "A regulated broker operating in most countries through local entities. Which products you may trade, and the margin rules that apply, depend on the entity your account sits under (IBKR LLC, IBKR UK, IBKR Japan and so on).",
 "ko": "각국 현지 법인을 통해 대부분의 국가에서 영업하는 규제 브로커입니다. 거래 가능한 상품과 적용되는 증거금 규정은 계좌가 속한 법인(IBKR LLC, IBKR UK, IBKR Japan 등)에 따라 달라집니다.",
 "ja": "各国の現地法人を通じて多くの国で営業する規制対象ブローカーです。取引できる商品や適用される証拠金規制は、口座が属する法人(IBKR LLC、IBKR UK、IBKR Japanなど)によって異なります。",
 "th": "เป็นโบรกเกอร์ที่อยู่ภายใต้การกำกับ ดำเนินงานในหลายประเทศผ่านนิติบุคคลท้องถิ่น ผลิตภัณฑ์ที่เทรดได้และกฎมาร์จิ้นขึ้นกับนิติบุคคลที่บัญชีของคุณสังกัด (IBKR LLC, IBKR UK, IBKR Japan ฯลฯ)",
 "vi": "Một broker chịu quản lý, hoạt động tại hầu hết các nước qua pháp nhân địa phương. Sản phẩm bạn được giao dịch và quy định ký quỹ áp dụng tùy theo pháp nhân mà tài khoản của bạn thuộc về (IBKR LLC, IBKR UK, IBKR Japan…).",
 "id": "Broker teregulasi yang beroperasi di sebagian besar negara melalui entitas lokal. Produk yang boleh Anda perdagangkan dan aturan margin yang berlaku bergantung pada entitas tempat akun Anda berada (IBKR LLC, IBKR UK, IBKR Japan, dan seterusnya)."},
"webull": {
 "en": "<b>Webull Financial LLC</b>, a US broker-dealer, for US-listed stocks and ETFs. OpenAPI trading is offered to Webull US account holders; residency and account eligibility are decided by Webull's own onboarding. US market hours and pattern-day-trading rules apply to your account, not to Sooppiy.",
 "ko": "미국 상장 주식·ETF를 다루는 미국 브로커-딜러 <b>Webull Financial LLC</b>입니다. OpenAPI 거래는 Webull 미국 계좌 보유자에게 제공되며, 거주지와 계좌 자격은 Webull의 가입 심사가 결정합니다. 미국 장 시간과 패턴 데이트레이딩 규정은 Sooppiy가 아니라 회원님 계좌에 적용됩니다.",
 "ja": "米国上場株・ETFを扱う米国のブローカーディーラー<b>Webull Financial LLC</b>です。OpenAPI取引はWebull米国口座の保有者向けで、居住地と口座の適格性はWebull自身の審査が決めます。米国市場の時間とパターン・デイトレード規制はSooppiyではなくあなたの口座に適用されます。",
 "th": "<b>Webull Financial LLC</b> โบรกเกอร์-ดีลเลอร์สหรัฐฯ สำหรับหุ้นและ ETF ที่จดทะเบียนในสหรัฐฯ การเทรดผ่าน OpenAPI ให้บริการแก่ผู้ถือบัญชี Webull สหรัฐฯ ถิ่นพำนักและคุณสมบัติบัญชีขึ้นกับการเปิดบัญชีของ Webull เวลาตลาดสหรัฐฯ และกฎ pattern day trading ใช้กับบัญชีของคุณ ไม่ใช่ Sooppiy",
 "vi": "<b>Webull Financial LLC</b>, broker-dealer Hoa Kỳ cho cổ phiếu và ETF niêm yết tại Mỹ. Giao dịch OpenAPI dành cho chủ tài khoản Webull Mỹ; nơi cư trú và điều kiện tài khoản do quy trình mở tài khoản của Webull quyết định. Giờ giao dịch Mỹ và quy tắc pattern day trading áp dụng cho tài khoản của bạn, không phải Sooppiy.",
 "id": "<b>Webull Financial LLC</b>, broker-dealer AS untuk saham dan ETF yang tercatat di AS. Trading OpenAPI ditawarkan kepada pemegang akun Webull AS; domisili dan kelayakan akun ditentukan oleh proses pembukaan akun Webull. Jam pasar AS dan aturan pattern day trading berlaku pada akun Anda, bukan pada Sooppiy.",
},
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
    avail_html = AVAIL[broker][lang]
    before_html = "".join(f"<li>{x.format(name=name)}</li>" for x in s["before_steps"])
    after_html = "".join(f"<li>{x.format(name=name)}</li>" for x in s["after_steps"])
    paste_h = [h.format(name=name) for h in s["paste_th"]]
    paste_rows = "".join(f"<tr><td>{lbl}</td><td><b>{field_rows[k]}</b></td></tr>"
                         for lbl, k in PASTE_MAP[broker])
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
  <h2><span class="no">1</span>{s["h_before"]}</h2>
  <ul>{before_html}</ul>
</section>

<section>
  <h2><span class="no">2</span>{s["h_avail"]}</h2>
  <div class="card"><p>{avail_html}</p></div>
  <div class="note">{s["avail_note"]}</div>
</section>

<section>
  <h2><span class="no">3</span>{s["h_need"]}</h2>
  <div class="card"><ul>{fields_html}</ul></div>
  <div class="note red">{s["warn_keys"]}</div>
  <div class="note">{s["ip_note"]}</div>
</section>

<section>
  <h2><span class="no">4</span>{s["h_create"].format(name=name)}</h2>
  <ol>{steps_html}</ol>
  <div class="note red">{s["once_warn"]}</div>
</section>

<section>
  <h2><span class="no">5</span>{s["h_paste"]}</h2>
  <table>
    <tr><th>{paste_h[0]}</th><th>{paste_h[1]}</th></tr>
    {paste_rows}
  </table>
</section>

<section>
  <h2><span class="no">6</span>{s["h_connect"]}</h2>
  <ol>{connect_html}</ol>
</section>

<section>
  <h2><span class="no">7</span>{s["h_after"]}</h2>
  <ol>{after_html}</ol>
</section>

<section>
  <h2><span class="no">8</span>{s["h_modes"].format(name=name)}</h2>
  <table>
    <tr><th>{mode_h[0]}</th><th>{mode_h[1]}</th></tr>
    <tr><td>paper</td><td>{s["mode_sim"].format(name=name)}</td></tr>
    <tr><td>shadow</td><td>{b["shadow"][lang]}</td></tr>
    <tr><td>live</td><td>{mode_live}</td></tr>
  </table>
  <div class="note">{s["drift_note"].format(name=name)}</div>
</section>

<section>
  <h2><span class="no">9</span>{s["h_notes"]}</h2>
  <ul>{notes_html}</ul>
</section>

<section>
  <h2><span class="no">10</span>{s["h_trouble"]}</h2>
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
