"""Generate the member guide "When your markets are open" in all 6 languages.

Run from the repo root:
    .venv/bin/python docs/design/_gen_market_hours_guide.py

Writes docs/design/market-hours-{en,ko,ja,th,vi,id}.html, which
build_guide_content.py then copies into service/server/guide_content/.

Why generated rather than six hand-written files: every session number in this
guide comes from markets.is_market_open(), and the six language versions must
agree to the minute. Hand-maintaining them would guarantee drift the first
time a session calendar changes. The session windows and the "availability
gap" bars below are COMPUTED here, not typed in.

Scope (2026-07-31): Sooppiy serves nine countries, not one. Every language
version now shows ALL nine regions — the reader's own row is not the only one
that matters when the point of the page is that the same subscription buys very
different access depending on where you live. This is a member-facing port of
docs/design/region-aware-trading-plan.html: it carries that plan's availability
gap, its region -> market matrix, and its venue-routing table, but in
member-safe wording (the plan's internal "review" / rollout-flag framing is
rephrased to "pending" / a plain roadmap).

The region -> market matrix and the venue table are a PLANNED position, not a
computed one and not legal advice — region entitlement gating is still rolling
out. The caption on each says so. Indonesia's matrix/venue rows are inferred
from its South-East-Asia peers (the source plan predates Indonesia) and should
be confirmed before that column is treated as authoritative.

Non-English prose here is machine-drafted; English is the runtime fallback.
Have ko/ja/th/vi/id proofread by a native reader before relying on them.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "service" / "server"))
import markets  # noqa: E402

OUT = Path(__file__).resolve().parent

LANGS = ["en", "ko", "ja", "th", "vi", "id"]

# The nine regions Sooppiy serves, in a fixed display order. Every language
# shows every row; only the words around them change. Jakarta is UTC+7, the
# same offset as Bangkok and Ho Chi Minh, so Indonesia's windows match theirs.
REGIONS = [
    ("United States", "America/New_York"),
    ("Canada", "America/Toronto"),
    ("Australia", "Australia/Sydney"),
    ("Singapore", "Asia/Singapore"),
    ("South Korea", "Asia/Seoul"),
    ("Japan", "Asia/Tokyo"),
    ("Thailand", "Asia/Bangkok"),
    ("Vietnam", "Asia/Ho_Chi_Minh"),
    ("Indonesia", "Asia/Jakarta"),
]

# Region name per language (the labels down the left of every table).
REGION_NAME = {
    "United States": {"en": "United States", "ko": "미국", "ja": "米国",
                      "th": "สหรัฐอเมริกา", "vi": "Hoa Kỳ", "id": "Amerika Serikat"},
    "Canada": {"en": "Canada", "ko": "캐나다", "ja": "カナダ",
               "th": "แคนาดา", "vi": "Canada", "id": "Kanada"},
    "Australia": {"en": "Australia", "ko": "호주", "ja": "オーストラリア",
                  "th": "ออสเตรเลีย", "vi": "Úc", "id": "Australia"},
    "Singapore": {"en": "Singapore", "ko": "싱가포르", "ja": "シンガポール",
                  "th": "สิงคโปร์", "vi": "Singapore", "id": "Singapura"},
    "South Korea": {"en": "South Korea", "ko": "대한민국", "ja": "韓国",
                    "th": "เกาหลีใต้", "vi": "Hàn Quốc", "id": "Korea Selatan"},
    "Japan": {"en": "Japan", "ko": "일본", "ja": "日本",
              "th": "ญี่ปุ่น", "vi": "Nhật Bản", "id": "Jepang"},
    "Thailand": {"en": "Thailand", "ko": "태국", "ja": "タイ",
                 "th": "ประเทศไทย", "vi": "Thái Lan", "id": "Thailand"},
    "Vietnam": {"en": "Vietnam", "ko": "베트남", "ja": "ベトナム",
                "th": "เวียดนาม", "vi": "Việt Nam", "id": "Vietnam"},
    "Indonesia": {"en": "Indonesia", "ko": "인도네시아", "ja": "インドネシア",
                  "th": "อินโดนีเซีย", "vi": "Indonesia", "id": "Indonesia"},
}

# A plain midweek day: every session at its normal hours, no weekend edges.
SAMPLE = datetime(2026, 7, 29, tzinfo=timezone.utc)

T = {
    "title": {
        "en": "When your markets are open",
        "ko": "내 시장은 언제 열리나요",
        "ja": "あなたの市場が開く時間",
        "th": "ตลาดของคุณเปิดเมื่อไหร่",
        "vi": "Thị trường của bạn mở khi nào",
        "id": "Kapan pasar Anda buka"},
    "lede": {
        "en": "Sooppiy serves members in nine countries, and every exchange opens on its own clock — not yours. This page shows each market's hours in <b>your</b> local time, what you can trade where, and where your orders route, so you know exactly when and how your automation can work.",
        "ko": "Sooppiy는 아홉 개 나라의 회원에게 서비스를 제공하며, 모든 거래소는 자기 시간에 맞춰 열립니다. 이 페이지는 각 시장의 개장 시간을 <b>내 현지 시각</b>으로 보여주고, 어느 지역에서 무엇을 거래할 수 있는지, 주문이 어디로 체결되는지를 안내합니다. 자동매매가 언제 어떻게 작동하는지 정확히 알 수 있습니다.",
        "ja": "Sooppiyは9か国の会員にサービスを提供しており、各取引所はそれぞれの時間で開きます。このページでは各市場の時間を<b>あなたの現地時刻</b>で示し、どの地域で何を取引できるか、注文がどこで約定するかを案内します。自動売買がいつ・どのように動くかが正確にわかります。",
        "th": "Sooppiy ให้บริการสมาชิกใน 9 ประเทศ และตลาดแต่ละแห่งเปิดตามเวลาของตัวเอง ไม่ใช่ของคุณ หน้านี้แสดงเวลาทำการของแต่ละตลาดตาม<b>เวลาท้องถิ่นของคุณ</b> สิ่งที่คุณเทรดได้ในแต่ละพื้นที่ และเส้นทางการส่งคำสั่ง เพื่อให้รู้ชัดว่าระบบอัตโนมัติทำงานได้เมื่อไหร่และอย่างไร",
        "vi": "Sooppiy phục vụ thành viên tại chín quốc gia, và mỗi sàn mở cửa theo giờ của riêng nó — không phải giờ của bạn. Trang này hiển thị giờ giao dịch của từng thị trường theo <b>giờ địa phương của bạn</b>, bạn được giao dịch gì ở đâu, và lệnh của bạn đi qua sàn nào, để bạn biết chính xác khi nào và bằng cách nào hệ thống tự động có thể hoạt động.",
        "id": "Sooppiy melayani anggota di sembilan negara, dan setiap bursa buka menurut jamnya sendiri — bukan jam Anda. Halaman ini menampilkan jam tiap pasar dalam <b>waktu lokal Anda</b>, apa yang bisa Anda perdagangkan di mana, dan ke mana order Anda diarahkan, sehingga Anda tahu persis kapan dan bagaimana otomatisasi Anda bisa bekerja."},
    "countries_h": {
        "en": "Nine countries, one platform",
        "ko": "아홉 개 나라, 하나의 플랫폼",
        "ja": "9か国、ひとつのプラットフォーム",
        "th": "เก้าประเทศ หนึ่งแพลตฟอร์ม",
        "vi": "Chín quốc gia, một nền tảng",
        "id": "Sembilan negara, satu platform"},
    "countries_p": {
        "en": "Sooppiy operates across the United States, Canada, Australia, Singapore, South Korea, Japan, Thailand, Vietnam and Indonesia. Your region decides three things: <b>when</b> your markets are open in your clock, <b>what</b> you may trade, and <b>which venue</b> fills your orders.",
        "ko": "Sooppiy는 미국, 캐나다, 호주, 싱가포르, 대한민국, 일본, 태국, 베트남, 인도네시아에서 운영됩니다. 내 지역은 세 가지를 결정합니다. 내 시각으로 시장이 <b>언제</b> 열리는지, <b>무엇</b>을 거래할 수 있는지, 주문이 <b>어느 거래소</b>에서 체결되는지입니다.",
        "ja": "Sooppiyは米国、カナダ、オーストラリア、シンガポール、韓国、日本、タイ、ベトナム、インドネシアで運営しています。あなたの地域は3つを決めます。あなたの時刻で市場が<b>いつ</b>開くか、<b>何</b>を取引できるか、注文が<b>どの取引所</b>で約定するかです。",
        "th": "Sooppiy ให้บริการในสหรัฐอเมริกา แคนาดา ออสเตรเลีย สิงคโปร์ เกาหลีใต้ ญี่ปุ่น ไทย เวียดนาม และอินโดนีเซีย พื้นที่ของคุณกำหนดสามสิ่ง คือ ตลาดเปิด<b>เมื่อไหร่</b>ตามเวลาของคุณ คุณเทรด<b>อะไร</b>ได้ และคำสั่งไปที่<b>ตลาดใด</b>",
        "vi": "Sooppiy hoạt động tại Hoa Kỳ, Canada, Úc, Singapore, Hàn Quốc, Nhật Bản, Thái Lan, Việt Nam và Indonesia. Khu vực của bạn quyết định ba điều: thị trường mở <b>khi nào</b> theo giờ của bạn, bạn được giao dịch <b>gì</b>, và lệnh của bạn khớp ở <b>sàn nào</b>.",
        "id": "Sooppiy beroperasi di Amerika Serikat, Kanada, Australia, Singapura, Korea Selatan, Jepang, Thailand, Vietnam, dan Indonesia. Wilayah Anda menentukan tiga hal: <b>kapan</b> pasar buka menurut jam Anda, <b>apa</b> yang boleh Anda perdagangkan, dan <b>bursa mana</b> yang mengeksekusi order Anda."},
    "always_h": {
        "en": "Always open", "ko": "항상 열려 있는 시장", "ja": "常に開いている市場",
        "th": "เปิดตลอดเวลา", "vi": "Luôn mở cửa", "id": "Selalu buka"},
    "always_p": {
        "en": "These never close during the week, so they are available whenever you are — whatever your region. Outside North America they are the core of the product, because they are open while you are awake.",
        "ko": "이 시장들은 주중에 닫히지 않아 지역과 관계없이 언제든 거래할 수 있습니다. 북미 밖에서는 회원이 깨어 있는 시간에 열려 있는 시장이 이것뿐이므로, 이 시장들이 서비스의 핵심입니다.",
        "ja": "これらは平日は閉じないため、地域を問わずいつでも取引できます。北米以外では、起きている時間に開いている市場はこれらだけなので、サービスの中心になります。",
        "th": "ตลาดเหล่านี้ไม่ปิดในวันธรรมดา จึงเทรดได้ทุกเมื่อไม่ว่าคุณอยู่ที่ใด นอกอเมริกาเหนือ ตลาดเหล่านี้คือหัวใจของบริการ เพราะเปิดในช่วงที่คุณตื่นอยู่",
        "vi": "Những thị trường này không đóng cửa trong tuần, nên luôn sẵn sàng dù bạn ở khu vực nào. Ngoài Bắc Mỹ, chúng là cốt lõi của sản phẩm, vì chúng mở khi bạn còn thức.",
        "id": "Pasar ini tidak pernah tutup pada hari kerja, jadi tersedia kapan pun Anda siap — di wilayah mana pun. Di luar Amerika Utara, pasar inilah inti produk, karena buka saat Anda terjaga."},
    "gap_h": {
        "en": "The availability gap",
        "ko": "접근성 격차",
        "ja": "利用できる時間の差",
        "th": "ช่องว่างของการเข้าถึง",
        "vi": "Khoảng cách tiếp cận",
        "id": "Kesenjangan ketersediaan"},
    "gap_p": {
        "en": "The same subscription buys very different access depending on where you live. US stocks trade 09:30–16:00 New York time — which lands in the middle of the night across Asia. Here is how many hours of US-stock trading fall inside a normal waking day (08:00–24:00 local), by region:",
        "ko": "같은 구독이라도 사는 곳에 따라 접근성은 크게 달라집니다. 미국 주식은 뉴욕 시간 09:30~16:00에 거래되는데, 이는 아시아에서는 한밤중입니다. 지역별로 하루 중 깨어 있는 시간(현지 08:00~24:00)에 미국 주식을 거래할 수 있는 시간은 다음과 같습니다.",
        "ja": "同じ会員でも、住む場所によって使える時間は大きく異なります。米国株はニューヨーク時間09:30〜16:00に取引され、アジアでは真夜中にあたります。地域別に、起きている時間帯（現地08:00〜24:00）に米国株を取引できる時間は次のとおりです。",
        "th": "การสมัครแบบเดียวกันให้การเข้าถึงต่างกันมากตามที่คุณอยู่ หุ้นสหรัฐฯ เทรดเวลา 09:30–16:00 ตามเวลานิวยอร์ก ซึ่งตรงกับกลางดึกในเอเชีย ต่อไปนี้คือจำนวนชั่วโมงที่เทรดหุ้นสหรัฐฯ ได้ในช่วงที่คุณตื่น (08:00–24:00 เวลาท้องถิ่น) แยกตามพื้นที่",
        "vi": "Cùng một gói nhưng mức tiếp cận rất khác nhau tùy nơi bạn sống. Cổ phiếu Mỹ giao dịch 09:30–16:00 giờ New York — rơi vào giữa đêm ở châu Á. Dưới đây là số giờ có thể giao dịch cổ phiếu Mỹ trong ngày lúc bạn thức (08:00–24:00 giờ địa phương), theo khu vực:",
        "id": "Langganan yang sama memberi akses yang sangat berbeda tergantung tempat tinggal Anda. Saham AS diperdagangkan 09:30–16:00 waktu New York — yang jatuh tengah malam di Asia. Berikut berapa jam perdagangan saham AS yang berada dalam hari terjaga normal (08:00–24:00 waktu lokal), per wilayah:"},
    "gap_cap": {
        "en": "An Australian member gets about 30 minutes of US-stock trading while awake; an American gets six and a half hours — the same price, up to 13× the access. That is exactly why crypto, forex and futures, above, are the core markets outside North America.",
        "ko": "호주 회원은 깨어 있는 동안 미국 주식을 약 30분 거래할 수 있고, 미국 회원은 6시간 30분을 거래할 수 있습니다. 같은 가격에 접근성은 최대 13배 차이입니다. 위의 가상자산·외환·선물이 북미 밖에서 핵심 시장인 이유가 바로 이것입니다.",
        "ja": "オーストラリアの会員が起きている間に米国株を取引できるのは約30分、米国の会員は6時間半です。同じ価格で最大13倍の差です。上の暗号資産・外国為替・先物が北米以外で中心市場になるのは、まさにこのためです。",
        "th": "สมาชิกในออสเตรเลียได้เทรดหุ้นสหรัฐฯ ราว 30 นาทีตอนตื่น ส่วนสมาชิกอเมริกันได้หกชั่วโมงครึ่ง ราคาเท่ากันแต่เข้าถึงต่างกันถึง 13 เท่า นี่คือเหตุผลที่คริปโต ฟอเร็กซ์ และฟิวเจอร์สข้างบนเป็นตลาดหลักนอกอเมริกาเหนือ",
        "vi": "Thành viên ở Úc có khoảng 30 phút giao dịch cổ phiếu Mỹ lúc thức; thành viên ở Mỹ có sáu tiếng rưỡi — cùng giá, chênh tới 13 lần mức tiếp cận. Đó chính là lý do tiền mã hoá, ngoại hối và hợp đồng tương lai ở trên là các thị trường cốt lõi ngoài Bắc Mỹ.",
        "id": "Anggota di Australia mendapat sekitar 30 menit perdagangan saham AS saat terjaga; anggota di Amerika mendapat enam setengah jam — harga sama, akses hingga 13× lipat. Itulah sebabnya kripto, forex, dan futures di atas menjadi pasar inti di luar Amerika Utara."},
    "sched_h": {
        "en": "Fixed-hours markets — in your time",
        "ko": "정해진 시간에 열리는 시장 — 내 시각 기준",
        "ja": "決まった時間に開く市場 — あなたの時刻で",
        "th": "ตลาดที่มีเวลาทำการแน่นอน — ตามเวลาของคุณ",
        "vi": "Thị trường có giờ cố định — theo giờ của bạn",
        "id": "Pasar berjam tetap — dalam waktu Anda"},
    "sched_p": {
        "en": "US stocks open at fixed exchange hours. Below is the session converted into every region's local clock, on a normal weekday.",
        "ko": "미국 주식은 정해진 거래소 시간에 열립니다. 아래는 평일 기준으로 개장 시간을 지역별 현지 시각으로 변환한 것입니다.",
        "ja": "米国株は決まった取引所時間に開きます。以下は平日基準で、セッションを地域ごとの現地時刻に変換したものです。",
        "th": "หุ้นสหรัฐฯ เปิดตามเวลาตลาดที่กำหนด ด้านล่างคือช่วงเวลาที่แปลงเป็นเวลาท้องถิ่นของแต่ละพื้นที่ในวันธรรมดา",
        "vi": "Cổ phiếu Mỹ mở theo giờ sàn cố định. Bên dưới là phiên quy đổi sang giờ địa phương của từng khu vực, trong một ngày thường.",
        "id": "Saham AS buka pada jam bursa tetap. Di bawah ini sesi dikonversi ke jam lokal setiap wilayah, pada hari kerja biasa."},
    "region_h": {
        "en": "Region", "ko": "지역", "ja": "地域", "th": "ภูมิภาค", "vi": "Khu vực",
        "id": "Wilayah"},
    "hours_h": {
        "en": "Your local hours", "ko": "현지 시각", "ja": "現地時刻",
        "th": "เวลาท้องถิ่น", "vi": "Giờ địa phương", "id": "Jam lokal"},
    "nextday": {
        "en": "next day", "ko": "다음 날", "ja": "翌日", "th": "วันถัดไป", "vi": "hôm sau",
        "id": "besok"},
    "matrix_h": {
        "en": "What you can trade, by region",
        "ko": "지역별로 거래할 수 있는 시장",
        "ja": "地域ごとに取引できる市場",
        "th": "สิ่งที่เทรดได้ในแต่ละพื้นที่",
        "vi": "Bạn được giao dịch gì, theo khu vực",
        "id": "Yang bisa diperdagangkan, per wilayah"},
    "matrix_p": {
        "en": "Planned availability as we roll region controls out. A <b>Pending</b> market is under review for that country and opens once it is cleared — this is a roadmap, not a legal guarantee.",
        "ko": "지역별 제어 기능을 순차 적용하면서 계획된 이용 범위입니다. <b>검토 중</b>인 시장은 해당 국가에서 검토가 진행 중이며 확정되면 열립니다. 이는 로드맵이며 법적 보장이 아닙니다.",
        "ja": "地域ごとの管理を順次適用していく中での提供予定です。<b>検討中</b>の市場はその国で確認中で、承認され次第開きます。これはロードマップであり、法的な保証ではありません。",
        "th": "ความพร้อมตามแผนขณะที่เราทยอยเปิดการควบคุมรายพื้นที่ ตลาดที่ <b>อยู่ระหว่างพิจารณา</b> กำลังตรวจสอบสำหรับประเทศนั้นและจะเปิดเมื่อผ่านแล้ว นี่คือแผนงาน ไม่ใช่การรับประกันทางกฎหมาย",
        "vi": "Khả dụng theo kế hoạch khi chúng tôi triển khai kiểm soát theo khu vực. Thị trường <b>Đang xét</b> đang được rà soát cho quốc gia đó và sẽ mở khi được thông qua — đây là lộ trình, không phải cam kết pháp lý.",
        "id": "Ketersediaan terencana seiring kami menerapkan kontrol per wilayah. Pasar <b>Ditinjau</b> sedang dikaji untuk negara itu dan terbuka setelah disetujui — ini peta jalan, bukan jaminan hukum."},
    "venue_h": {
        "en": "Where your orders route",
        "ko": "주문이 체결되는 곳",
        "ja": "注文が約定する場所",
        "th": "เส้นทางการส่งคำสั่ง",
        "vi": "Lệnh của bạn đi qua đâu",
        "id": "Ke mana order Anda diarahkan"},
    "venue_p": {
        "en": "Prices come from global data feeds everywhere. Live orders route through the broker you connect — and which brokers are available depends on your region.",
        "ko": "시세는 어디서나 글로벌 데이터 피드에서 옵니다. 실거래 주문은 연결한 증권사를 통해 체결되며, 이용 가능한 증권사는 지역에 따라 다릅니다.",
        "ja": "価格はどこでもグローバルなデータフィードから取得します。実注文は接続したブローカーを通じて約定し、利用できるブローカーは地域によって異なります。",
        "th": "ราคามาจากฟีดข้อมูลระดับโลกทุกที่ คำสั่งจริงส่งผ่านโบรกเกอร์ที่คุณเชื่อมต่อ และโบรกเกอร์ที่ใช้ได้ขึ้นกับพื้นที่ของคุณ",
        "vi": "Giá lấy từ các nguồn dữ liệu toàn cầu ở mọi nơi. Lệnh thật đi qua sàn môi giới bạn kết nối — và những sàn khả dụng tùy khu vực của bạn.",
        "id": "Harga berasal dari umpan data global di mana saja. Order live diarahkan lewat broker yang Anda hubungkan — dan broker yang tersedia bergantung pada wilayah Anda."},
    "venue_c1": {
        "en": "Stocks & futures", "ko": "주식·선물", "ja": "株式・先物",
        "th": "หุ้นและฟิวเจอร์ส", "vi": "Cổ phiếu & tương lai", "id": "Saham & futures"},
    "venue_c2": {
        "en": "Crypto", "ko": "가상자산", "ja": "暗号資産", "th": "คริปโต",
        "vi": "Tiền mã hoá", "id": "Kripto"},
    "venue_c3": {
        "en": "Note", "ko": "비고", "ja": "備考", "th": "หมายเหตุ", "vi": "Ghi chú",
        "id": "Catatan"},
    "roadmap_h": {
        "en": "What's rolling out",
        "ko": "순차 적용 중인 기능",
        "ja": "順次提供する機能",
        "th": "สิ่งที่กำลังทยอยเปิด",
        "vi": "Những gì đang triển khai",
        "id": "Yang sedang diluncurkan"},
    "note_h": {
        "en": "What this means for you",
        "ko": "이것이 의미하는 것",
        "ja": "これが意味すること",
        "th": "สิ่งนี้หมายความว่าอย่างไรกับคุณ",
        "vi": "Điều này có ý nghĩa gì với bạn",
        "id": "Apa artinya ini bagi Anda"},
    "dst": {
        "en": "US, Canadian and Australian hours shift by an hour when daylight saving starts or ends — and Australia's runs opposite to the northern hemisphere. Korea, Japan, Singapore, Thailand, Vietnam and Indonesia do not observe it. The site always shows the current, correct time.",
        "ko": "미국·캐나다·호주의 시간은 서머타임이 시작·종료될 때 한 시간씩 이동하며, 호주는 북반구와 반대로 적용됩니다. 대한민국·일본·싱가포르·태국·베트남·인도네시아는 서머타임이 없습니다. 사이트는 항상 현재 기준의 정확한 시각을 표시합니다.",
        "ja": "米国・カナダ・オーストラリアの時間は夏時間の開始・終了で1時間ずれ、オーストラリアは北半球と逆に動きます。韓国・日本・シンガポール・タイ・ベトナム・インドネシアに夏時間はありません。サイトは常に現在の正しい時刻を表示します。",
        "th": "เวลาของสหรัฐฯ แคนาดา และออสเตรเลียเลื่อนหนึ่งชั่วโมงเมื่อเริ่มหรือสิ้นสุดเวลาออมแสง และของออสเตรเลียกลับทิศกับซีกโลกเหนือ เกาหลีใต้ ญี่ปุ่น สิงคโปร์ ไทย เวียดนาม และอินโดนีเซียไม่มีเวลาออมแสง เว็บไซต์แสดงเวลาที่ถูกต้องตามปัจจุบันเสมอ",
        "vi": "Giờ của Mỹ, Canada và Úc dịch một tiếng khi bắt đầu hoặc kết thúc giờ mùa hè — và của Úc ngược với bắc bán cầu. Hàn Quốc, Nhật Bản, Singapore, Thái Lan, Việt Nam và Indonesia không áp dụng. Trang luôn hiển thị thời gian đúng ở hiện tại.",
        "id": "Jam AS, Kanada, dan Australia bergeser satu jam saat waktu musim panas dimulai atau berakhir — dan Australia berlawanan dengan belahan bumi utara. Korea Selatan, Jepang, Singapura, Thailand, Vietnam, dan Indonesia tidak memakainya. Situs ini selalu menampilkan waktu yang benar saat itu."},
    "set_h": {
        "en": "Setting your region",
        "ko": "지역 설정하기", "ja": "地域の設定",
        "th": "การตั้งค่าภูมิภาค", "vi": "Thiết lập khu vực",
        "id": "Mengatur wilayah Anda"},
    "set_p": {
        "en": "You choose your region and language when you first sign in, and can change either at any time in <b>Settings → Region &amp; Language</b>. Your region sets the clock every time on the site is shown in.",
        "ko": "처음 로그인할 때 지역과 언어를 선택하며, <b>설정 → 지역과 언어</b>에서 언제든지 바꿀 수 있습니다. 사이트에 표시되는 모든 시각은 선택한 지역의 시간대를 따릅니다.",
        "ja": "初回ログイン時に地域と言語を選択します。<b>設定 → 地域と言語</b>からいつでも変更できます。サイト上のすべての時刻は選択した地域のタイムゾーンで表示されます。",
        "th": "คุณเลือกภูมิภาคและภาษาเมื่อเข้าสู่ระบบครั้งแรก และเปลี่ยนได้ทุกเมื่อที่ <b>การตั้งค่า → ภูมิภาคและภาษา</b> ภูมิภาคของคุณกำหนดเวลาที่แสดงทั้งหมดบนเว็บไซต์",
        "vi": "Bạn chọn khu vực và ngôn ngữ khi đăng nhập lần đầu, và có thể đổi bất cứ lúc nào tại <b>Cài đặt → Khu vực &amp; Ngôn ngữ</b>. Khu vực quyết định múi giờ của mọi thời điểm hiển thị trên trang.",
        "id": "Anda memilih wilayah dan bahasa saat pertama kali masuk, dan dapat mengubah keduanya kapan saja di <b>Pengaturan → Wilayah &amp; Bahasa</b>. Wilayah Anda menentukan zona waktu untuk setiap waktu yang ditampilkan di situs ini."},
    "pill_yes": {
        "en": "Available", "ko": "가능", "ja": "利用可", "th": "พร้อม",
        "vi": "Có sẵn", "id": "Tersedia"},
    "pill_pending": {
        "en": "Pending", "ko": "검토 중", "ja": "検討中", "th": "รอพิจารณา",
        "vi": "Đang xét", "id": "Ditinjau"},
    "hrs": {"en": "{h}h", "ko": "{h}시간", "ja": "{h}時間", "th": "{h} ชม.",
            "vi": "{h} giờ", "id": "{h} jam"},
    "tl_h": {
        "en": "Where the US session falls in your day",
        "ko": "미국 장이 내 하루의 어디에 오는가",
        "ja": "米国市場は一日のどこに来るか",
        "th": "ตลาดสหรัฐฯ อยู่ตรงไหนของวันคุณ",
        "vi": "Phiên Mỹ nằm ở đâu trong ngày của bạn",
        "id": "Di mana sesi AS jatuh dalam hari Anda"},
    "tl_p": {
        "en": "The table above says how long. This says when. Each bar is one full day on that region's own clock, midnight to midnight, with the US session drawn where it actually lands.",
        "ko": "위 표는 '얼마나'를 알려줍니다. 아래 그래프는 '언제'를 보여줍니다. 각 막대는 해당 지역 현지 시각으로 자정부터 자정까지의 하루 전체이며, 미국 장이 실제로 놓이는 위치에 표시됩니다.",
        "ja": "上の表は「どれだけ」を示します。こちらは「いつ」です。各バーはその地域の現地時刻で深夜から深夜までの一日を表し、米国市場が実際に入る位置に描かれています。",
        "th": "ตารางด้านบนบอกว่านานแค่ไหน ส่วนภาพนี้บอกว่าเมื่อไหร่ แต่ละแถบคือหนึ่งวันเต็มตามเวลาท้องถิ่นของภูมิภาคนั้น ตั้งแต่เที่ยงคืนถึงเที่ยงคืน โดยวางช่วงตลาดสหรัฐฯ ไว้ตามตำแหน่งจริง",
        "vi": "Bảng trên cho biết bao lâu. Hình này cho biết khi nào. Mỗi thanh là trọn một ngày theo giờ địa phương của khu vực đó, từ nửa đêm đến nửa đêm, với phiên Mỹ được vẽ đúng chỗ nó rơi vào.",
        "id": "Tabel di atas menyatakan berapa lama. Grafik ini menyatakan kapan. Tiap batang adalah satu hari penuh dalam jam lokal wilayah tersebut, dari tengah malam ke tengah malam, dengan sesi AS digambar tepat pada posisinya."},
    "tl_cap": {
        "en": "Read the Asian rows left to right: the band that opens the day is the session that began the previous evening — which is why those windows are marked “next day” in the table above. Crypto, forex and futures are left out; on a weekday they would cover almost the whole bar.",
        "ko": "아시아 지역 막대는 왼쪽부터 읽으세요. 하루를 여는 막대는 전날 저녁에 시작된 장이며, 위 표에서 그 시간대에 '다음 날' 표시가 붙는 이유입니다. 가상자산·외환·선물은 평일에 거의 하루 전체를 덮기 때문에 제외했습니다.",
        "ja": "アジアの行は左から読んでください。一日の始まりにある帯は前日の夜に開いた立会いで、上の表でその時間帯に「翌日」と付くのはこのためです。暗号資産・外国為替・先物は平日はほぼ一日中開いているため除いています。",
        "th": "อ่านแถวของเอเชียจากซ้ายไปขวา แถบที่เปิดวันคือช่วงที่เริ่มตั้งแต่เย็นวันก่อน จึงเป็นเหตุผลที่ตารางด้านบนกำกับว่า 'วันถัดไป' ไม่รวมคริปโต ฟอเร็กซ์ และฟิวเจอร์ส เพราะในวันธรรมดาจะครอบคลุมเกือบทั้งแถบ",
        "vi": "Đọc các hàng châu Á từ trái sang phải: dải mở đầu ngày chính là phiên đã bắt đầu từ tối hôm trước — đó là lý do các khung giờ đó được ghi 'hôm sau' ở bảng trên. Không hiển thị tiền mã hoá, ngoại hối và hợp đồng tương lai; ngày thường chúng sẽ phủ gần trọn thanh.",
        "id": "Baca baris Asia dari kiri ke kanan: pita yang membuka hari adalah sesi yang dimulai malam sebelumnya — itulah sebabnya jam tersebut ditandai 'hari berikutnya' di tabel di atas. Kripto, forex, dan futures tidak ditampilkan; pada hari kerja semuanya akan menutupi hampir seluruh batang."},
    "lg_us": {
        "en": "US stocks open (NYSE)", "ko": "미국 주식 개장 (NYSE)",
        "ja": "米国株 取引時間（NYSE）", "th": "ตลาดหุ้นสหรัฐฯ เปิด (NYSE)",
        "vi": "Cổ phiếu Mỹ mở cửa (NYSE)", "id": "Saham AS buka (NYSE)"},
    "lg_cl": {
        "en": "closed", "ko": "휴장", "ja": "閉場", "th": "ปิด", "vi": "đóng cửa",
        "id": "tutup"},
    "soon": {
        "en": "coming", "ko": "준비 중", "ja": "準備中", "th": "เร็ว ๆ นี้",
        "vi": "sắp có", "id": "segera"},
}

MARKET_NAME = {
    "crypto": {"en": "Crypto", "ko": "가상자산", "ja": "暗号資産", "th": "คริปโต",
               "vi": "Tiền mã hoá", "id": "Kripto"},
    "forex": {"en": "Forex", "ko": "외환", "ja": "外国為替", "th": "ฟอเร็กซ์",
              "vi": "Ngoại hối", "id": "Forex"},
    "futures": {"en": "Futures", "ko": "선물", "ja": "先物", "th": "ฟิวเจอร์ส",
                "vi": "Tương lai", "id": "Futures"},
    "us-stock": {"en": "US stocks", "ko": "미국 주식", "ja": "米国株", "th": "หุ้นสหรัฐฯ",
                 "vi": "Cổ phiếu Mỹ", "id": "Saham AS"},
    "options": {"en": "Options", "ko": "옵션", "ja": "オプション", "th": "ออปชั่น",
                "vi": "Quyền chọn", "id": "Opsi"},
    "polymarket": {"en": "Prediction", "ko": "예측 시장", "ja": "予測市場", "th": "ตลาดทำนาย",
                   "vi": "Thị trường dự đoán", "id": "Pasar prediksi"},
}

ALWAYS = ["crypto", "forex", "futures"]
SCHEDULED = ["us-stock"]
MATRIX_COLS = ["crypto", "forex", "futures", "us-stock", "options", "polymarket"]

# Planned region -> market position, ported from region-aware-trading-plan.html
# section 5 ("y" = the plan's "yes", "p" = the plan's "review"). Indonesia is
# inferred from Thailand/Vietnam — the source plan predates it. This is a
# roadmap, not legal advice; the caption on the table says so.
MATRIX = {
    "United States": {"crypto": "y", "forex": "y", "futures": "y", "us-stock": "y",
                      "options": "y", "polymarket": "p"},
    "Canada": {"crypto": "y", "forex": "y", "futures": "y", "us-stock": "y",
               "options": "y", "polymarket": "p"},
    "Australia": {"crypto": "y", "forex": "y", "futures": "y", "us-stock": "y",
                  "options": "p", "polymarket": "p"},
    "Singapore": {"crypto": "y", "forex": "y", "futures": "y", "us-stock": "y",
                  "options": "p", "polymarket": "p"},
    "South Korea": {"crypto": "p", "forex": "p", "futures": "y", "us-stock": "y",
                    "options": "p", "polymarket": "p"},
    "Japan": {"crypto": "p", "forex": "y", "futures": "y", "us-stock": "y",
              "options": "p", "polymarket": "p"},
    "Thailand": {"crypto": "p", "forex": "p", "futures": "y", "us-stock": "y",
                 "options": "p", "polymarket": "p"},
    "Vietnam": {"crypto": "p", "forex": "p", "futures": "y", "us-stock": "y",
                "options": "p", "polymarket": "p"},
    "Indonesia": {"crypto": "p", "forex": "p", "futures": "y", "us-stock": "y",
                  "options": "p", "polymarket": "p"},
}

# Venue routing, ported from plan section 6. crypto_soon marks a domestic
# exchange with no adapter yet (shown with a "coming" tag). note is a key into
# VENUE_NOTE below. Broker names are proper nouns and stay untranslated.
# Crypto venues mirror execution/base.py REGION_VENUES — the same matrix the
# Accounts page recommends per region (2026-08-01 regional gateway, Plan 19).
# Binance is live today; the other venues connect now and run shadow first.
VENUE = {
    "United States": {"sf": "Alpaca · IBKR", "cx": "Binance · Bybit · OKX · Kraken · Crypto.com",
                      "cx_soon": False, "note": "shadow_first"},
    "Canada": {"sf": "IBKR", "cx": "Binance · Bybit · OKX · Kraken · Crypto.com",
               "cx_soon": False, "note": "shadow_first"},
    "Australia": {"sf": "IBKR", "cx": "Binance · Bybit · OKX · Kraken · Crypto.com",
                  "cx_soon": False, "note": "shadow_first"},
    "Singapore": {"sf": "IBKR", "cx": "Crypto.com · KuCoin · OKX",
                  "cx_soon": False, "note": "shadow_first"},
    "South Korea": {"sf": "IBKR", "cx": "Upbit · Kraken", "cx_soon": False, "note": "shadow_first"},
    "Japan": {"sf": "IBKR", "cx": "Kraken", "cx_soon": False, "note": "shadow_first"},
    "Thailand": {"sf": "IBKR", "cx": "Binance · Bybit · KuCoin", "cx_soon": False, "note": "shadow_first"},
    "Vietnam": {"sf": "IBKR", "cx": "Binance · Bybit · KuCoin", "cx_soon": False, "note": "shadow_first"},
    "Indonesia": {"sf": "IBKR", "cx": "Binance · Bybit · KuCoin", "cx_soon": False, "note": "shadow_first"},
}

VENUE_NOTE = {
    "both": {
        "en": "Both connected today", "ko": "두 종류 모두 연결 가능", "ja": "両方とも接続可能",
        "th": "เชื่อมต่อได้ทั้งคู่แล้ว", "vi": "Cả hai đã kết nối", "id": "Keduanya sudah terhubung"},
    "confirm": {
        "en": "Crypto brokers being confirmed", "ko": "가상자산 증권사 확인 중",
        "ja": "暗号資産ブローカーを確認中", "th": "กำลังยืนยันโบรกเกอร์คริปโต",
        "vi": "Đang xác nhận sàn crypto", "id": "Broker kripto sedang dikonfirmasi"},
    "dash": {"en": "—", "ko": "—", "ja": "—", "th": "—", "vi": "—", "id": "—"},
    "domestic": {
        "en": "Local crypto exchange support coming", "ko": "국내 거래소 지원 준비 중",
        "ja": "国内取引所への対応を準備中", "th": "กำลังเตรียมรองรับตลาดคริปโตในประเทศ",
        "vi": "Sắp hỗ trợ sàn crypto nội địa", "id": "Dukungan bursa kripto lokal segera hadir"},
    "shadow_first": {
        "en": "Connect on the Accounts page — new venues run shadow first; live opens per venue",
        "ko": "계정 페이지에서 연결 — 신규 거래소는 shadow 우선, live는 거래소별 순차 오픈",
        "ja": "アカウントページで接続 — 新規取引所はshadow優先、liveは取引所ごとに順次開放",
        "th": "เชื่อมต่อในหน้าบัญชี — กระดานใหม่รัน shadow ก่อน ส่วน live ทยอยเปิดทีละแห่ง",
        "vi": "Kết nối trên trang Tài khoản — sàn mới chạy shadow trước; live mở dần theo từng sàn",
        "id": "Hubungkan di halaman Akun — bursa baru berjalan shadow dulu; live dibuka per bursa"},
}

# Member-facing roadmap (plan section 7 phases, rephrased). Each is (title, desc).
ROADMAP = [
    {"live": True,
     "title": {"en": "Your region &amp; clock", "ko": "지역과 시간대",
               "ja": "地域と時刻", "th": "ภูมิภาคและเวลาของคุณ",
               "vi": "Khu vực &amp; giờ của bạn", "id": "Wilayah &amp; jam Anda"},
     "desc": {"en": "Pick your country and language at sign-in; every time on the site shows in your local clock.",
              "ko": "로그인 시 국가와 언어를 선택하면, 사이트의 모든 시각이 현지 시각으로 표시됩니다.",
              "ja": "ログイン時に国と言語を選ぶと、サイトのすべての時刻が現地時刻で表示されます。",
              "th": "เลือกประเทศและภาษาตอนเข้าสู่ระบบ แล้วเวลาทั้งหมดบนเว็บจะแสดงตามเวลาท้องถิ่นของคุณ",
              "vi": "Chọn quốc gia và ngôn ngữ khi đăng nhập; mọi thời điểm trên trang hiển thị theo giờ địa phương của bạn.",
              "id": "Pilih negara dan bahasa saat masuk; setiap waktu di situs tampil dalam jam lokal Anda."}},
    {"live": False,
     "title": {"en": "Schedules in your time", "ko": "내 시각 기준 일정",
               "ja": "あなたの時刻での予定", "th": "ตารางตามเวลาของคุณ",
               "vi": "Lịch theo giờ của bạn", "id": "Jadwal dalam waktu Anda"},
     "desc": {"en": "Market countdowns, automation schedules and alerts follow your clock — no alerts at 3 a.m.",
              "ko": "시장 카운트다운, 자동매매 일정, 알림이 내 시각을 따릅니다. 새벽 3시 알림은 없습니다.",
              "ja": "市場のカウントダウン、自動売買の予定、通知があなたの時刻に従います。深夜3時の通知はありません。",
              "th": "การนับถอยหลังของตลาด ตารางระบบอัตโนมัติ และการแจ้งเตือนเป็นไปตามเวลาของคุณ ไม่มีแจ้งเตือนตอนตีสาม",
              "vi": "Đếm ngược thị trường, lịch tự động và cảnh báo theo giờ của bạn — không có cảnh báo lúc 3 giờ sáng.",
              "id": "Hitung mundur pasar, jadwal otomatisasi, dan peringatan mengikuti jam Anda — tanpa peringatan pukul 3 pagi."}},
    {"live": False,
     "title": {"en": "Region availability", "ko": "지역별 이용 범위",
               "ja": "地域ごとの提供範囲", "th": "ความพร้อมรายพื้นที่",
               "vi": "Khả dụng theo khu vực", "id": "Ketersediaan per wilayah"},
     "desc": {"en": "Which markets you can trade, set per country as each is cleared.",
              "ko": "거래할 수 있는 시장을 국가별로 확정되는 대로 설정합니다.",
              "ja": "取引できる市場を、承認され次第、国ごとに設定します。",
              "th": "กำหนดตลาดที่เทรดได้เป็นรายประเทศเมื่อผ่านการพิจารณา",
              "vi": "Các thị trường bạn được giao dịch, thiết lập theo từng quốc gia khi được thông qua.",
              "id": "Pasar yang bisa Anda perdagangkan, diatur per negara begitu disetujui."}},
    {"live": True,
     "title": {"en": "Regional venues", "ko": "지역 거래소",
               "ja": "地域の取引所", "th": "กระดานเทรดประจำภูมิภาค",
               "vi": "Sàn theo khu vực", "id": "Bursa regional"},
     "desc": {"en": "Upbit, Bybit, OKX, Kraken, Crypto.com and KuCoin connect today and run shadow first; live opens per venue after its rollout check. More local venues (bitFlyer, Bitkub, Indodax) are being evaluated.",
              "ko": "업비트·Bybit·OKX·Kraken·Crypto.com·KuCoin을 지금 연결할 수 있으며 shadow 우선으로 운영됩니다. live는 검증이 끝나는 거래소부터 순차 오픈됩니다. bitFlyer, Bitkub, Indodax 등 추가 국내 거래소는 검토 중입니다.",
              "ja": "Upbit・Bybit・OKX・Kraken・Crypto.com・KuCoinは今すぐ接続でき、shadow優先で運用されます。liveは検証が完了した取引所から順次開放されます。bitFlyer、Bitkub、Indodaxなどの追加国内取引所は検討中です。",
              "th": "Upbit, Bybit, OKX, Kraken, Crypto.com และ KuCoin เชื่อมต่อได้แล้ววันนี้และรัน shadow ก่อน ส่วน live ทยอยเปิดทีละกระดานหลังผ่านการตรวจสอบ กระดานท้องถิ่นเพิ่มเติม (bitFlyer, Bitkub, Indodax) อยู่ระหว่างการประเมิน",
              "vi": "Upbit, Bybit, OKX, Kraken, Crypto.com và KuCoin kết nối được ngay và chạy shadow trước; live mở dần theo từng sàn sau kiểm chứng. Các sàn nội địa khác (bitFlyer, Bitkub, Indodax) đang được đánh giá.",
              "id": "Upbit, Bybit, OKX, Kraken, Crypto.com, dan KuCoin dapat dihubungkan hari ini dan berjalan shadow dulu; live dibuka per bursa setelah pemeriksaan. Bursa lokal lain (bitFlyer, Bitkub, Indodax) sedang dievaluasi."}},
]


def _bands(market: str, tz: str) -> list[tuple[float, float]]:
    """Open windows of `market` across one local day, in local decimal hours."""
    z = ZoneInfo(tz)
    day0 = SAMPLE.astimezone(z).replace(hour=0, minute=0, second=0, microsecond=0)
    out, cur = [], None
    for m in range(24 * 60):
        t = day0 + timedelta(minutes=m)
        if markets.is_market_open(market, t.astimezone(timezone.utc)):
            if cur is None:
                cur = m
        elif cur is not None:
            out.append((cur / 60, m / 60))
            cur = None
    if cur is not None:
        out.append((cur / 60, 24.0))
    return out


def _awake_hours(market: str, tz: str) -> float:
    """Open minutes falling in 08:00–24:00 local — the part a member can use
    without setting an alarm."""
    z = ZoneInfo(tz)
    n = sum(1 for m in range(24 * 60)
            if markets.is_market_open(market, SAMPLE + timedelta(minutes=m))
            and 8 <= (SAMPLE + timedelta(minutes=m)).astimezone(z).hour < 24)
    return round(n / 60, 1)


def _hhmm(h: float) -> str:
    return f"{int(h) % 24:02d}:{int(round((h - int(h)) * 60)):02d}"


def _window_text(bands: list[tuple[float, float]], lang: str) -> str:
    """Join a day's bands, merging a midnight wrap into one readable window.

    A session that begins the previous evening shows up as [0,x] and [y,24];
    printing those as two separate windows is technically true and useless.
    """
    if not bands:
        return "—"
    b = sorted(bands)
    if len(b) > 1 and b[0][0] == 0.0 and b[-1][1] == 24.0:
        wrapped = (b[-1][0], b[0][1])
        rest = b[1:-1]
        parts = [f"{_hhmm(wrapped[0])}–{_hhmm(wrapped[1])} "
                 f"<span class=nd>({T['nextday'][lang]})</span>"]
        parts += [f"{_hhmm(a)}–{_hhmm(c)}" for a, c in rest]
        return ", ".join(parts)
    return ", ".join(f"{_hhmm(a)}–{_hhmm(c)}" for a, c in b)


CSS = """
:root{--page:#f9f9f7;--card:#fff;--surf:#f1f0ec;--grid:#e1e0d9;--ink:#0b0b0b;--ink2:#52514e;
 --muted:#7a7975;--ai:#2a78d6;--go:#1baf7a;--warn:#c88a1a;--bd:rgba(11,11,11,.1)}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--card:#202020;--surf:#1a1a19;
 --grid:#2c2c2a;--ink:#fff;--ink2:#c3c2b7;--muted:#8f8d85;--ai:#3987e5;--go:#199e70;
 --warn:#e0a53a;--bd:rgba(255,255,255,.1)}}
:root[data-theme=dark]{--page:#0d0d0d;--card:#202020;--surf:#1a1a19;--grid:#2c2c2a;--ink:#fff;
 --ink2:#c3c2b7;--muted:#8f8d85;--ai:#3987e5;--go:#199e70;--warn:#e0a53a;--bd:rgba(255,255,255,.1)}
:root[data-theme=light]{--page:#f9f9f7;--card:#fff;--surf:#f1f0ec;--grid:#e1e0d9;--ink:#0b0b0b;
 --ink2:#52514e;--muted:#7a7975;--ai:#2a78d6;--go:#1baf7a;--warn:#c88a1a;--bd:rgba(11,11,11,.1)}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);
 font-family:system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif;
 line-height:1.72;font-size:14.5px}
main{max-width:860px;margin:0 auto;padding:38px 22px 80px}
h1{font-size:25px;line-height:1.3;margin:0 0 8px}
h2{font-size:18px;margin:34px 0 8px;padding-top:18px;border-top:1px solid var(--grid)}
p,li{color:var(--ink2)}strong,b{color:var(--ink)}
.lede{font-size:15.5px;margin-bottom:20px}
.fig{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px 18px;margin:14px 0}
.always{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}
.always span{background:color-mix(in srgb,var(--go) 14%,transparent);color:var(--go);
 font-weight:700;font-size:13px;padding:5px 13px;border-radius:999px}
.sw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.4px;margin:6px 0;min-width:460px}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--grid);color:var(--ink2)}
th{font-size:10.5px;letter-spacing:.05em;color:var(--muted);text-transform:uppercase;white-space:nowrap}
td.m{color:var(--ink);font-weight:650;white-space:nowrap}
td.h{font-variant-numeric:tabular-nums;white-space:nowrap}
.nd{color:var(--muted);font-size:11.5px}
.cap{font-size:12.5px;color:var(--muted);margin:12px 0 0}
/* availability-gap bars */
.bars{display:grid;gap:7px;margin-top:4px}
.br{display:grid;grid-template-columns:120px 1fr 46px;gap:10px;align-items:center;font-size:12.7px}
.brl{color:var(--ink2);white-space:nowrap}
.brt{height:18px;background:var(--surf);border-radius:5px;overflow:hidden}
.brf{height:100%;border-radius:5px}
.brv{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:650}
/* 24h session timeline */
.tl{display:grid;grid-template-columns:120px 1fr;gap:10px;align-items:center;margin-bottom:5px;
 font-size:12.7px}
.tll{color:var(--ink2);line-height:1.35}
.tlt{position:relative;height:24px;background:var(--surf);border-radius:5px;overflow:hidden}
.tlb{position:absolute;top:0;height:100%;background:var(--ai)}
.axis{display:grid;grid-template-columns:120px 1fr;gap:10px;font-size:10.5px;color:var(--muted);
 margin-top:4px}
.axl{display:flex;justify-content:space-between}
.lgd{display:flex;flex-wrap:wrap;gap:14px;margin-top:13px;font-size:12.3px;color:var(--ink2)}
.lgd i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:6px;
 vertical-align:-1px}
@media(max-width:520px){.tl,.axis{grid-template-columns:76px 1fr}.tll{font-size:11.4px}}
/* matrix pills */
.pill{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}
.p-go{background:color-mix(in srgb,var(--go) 17%,transparent);color:var(--go)}
.p-w{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
.soon{color:var(--muted);font-size:11px;white-space:nowrap}
/* roadmap */
.rm{display:grid;gap:9px;margin-top:6px}
.rmi{border:1px solid var(--bd);border-left:4px solid var(--ai);background:var(--card);
 border-radius:0 10px 10px 0;padding:11px 15px}
.rmi.live{border-left-color:var(--go)}
.rmi b{color:var(--ink);font-size:13.6px;display:block;margin-bottom:2px}
.rmi span{font-size:12.7px}
.tag{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;
 padding:2px 7px;border-radius:999px;margin-left:8px;vertical-align:1px;
 background:color-mix(in srgb,var(--go) 17%,transparent);color:var(--go)}
.note{border:1px solid var(--bd);border-left:4px solid var(--ai);background:var(--card);
 border-radius:0 11px 11px 0;padding:14px 17px;margin:14px 0}
.note p{margin:0;font-size:13.6px}
"""

JS = """
(function(){try{var a=function(){var t=(window.parent&&window.parent!==window&&
window.parent.document&&window.parent.document.documentElement.getAttribute('data-theme'))||null;
if(t)document.documentElement.setAttribute('data-theme',t);};a();
if(window.parent&&window.parent!==window&&window.parent.document){
new MutationObserver(a).observe(window.parent.document.documentElement,
{attributes:true,attributeFilter:['data-theme']});}}catch(e){}})();
"""

LIVE_TAG = {"en": "Live", "ko": "제공 중", "ja": "提供中", "th": "พร้อมแล้ว",
            "vi": "Đã có", "id": "Aktif"}


def _gap_bars(lang: str) -> str:
    """US-stock awake-hours per region, longest first, as a bar chart."""
    rows = [(canon, _awake_hours("us-stock", tz)) for canon, tz in REGIONS]
    rows.sort(key=lambda r: -r[1])
    top = max(h for _, h in rows) or 1
    out = []
    for canon, h in rows:
        pct = max(3, round(h / top * 100))
        color = "var(--go)" if h >= 4 else ("var(--warn)" if h >= 2 else "var(--ai)")
        out.append(
            f'<div class="br"><div class="brl">{REGION_NAME[canon][lang]}</div>'
            f'<div class="brt"><div class="brf" style="width:{pct}%;background:{color}"></div></div>'
            f'<div class="brv">{T["hrs"][lang].format(h=h)}</div></div>')
    return '<div class="bars">' + "".join(out) + "</div>"


def _timeline(lang: str) -> str:
    """The US session drawn in place across each region's own 24-hour day.

    Regions whose windows match to the minute share a row — that is what folds
    Bangkok, Ho Chi Minh and Jakarta together without hard-coding which zones
    happen to agree, so a tzdata change re-splits them on the next run.
    """
    groups: list[tuple[tuple, list[str]]] = []
    for canon, tz in REGIONS:
        sig = tuple(_bands("us-stock", tz))
        for sig_seen, names in groups:
            if sig_seen == sig:
                names.append(canon)
                break
        else:
            groups.append((sig, [canon]))

    rows = []
    for sig, names in groups:
        label = " / ".join(REGION_NAME[c][lang] for c in names)
        bands = "".join(
            f'<div class="tlb" style="left:{a / 24 * 100:.4g}%;'
            f'width:{(b - a) / 24 * 100:.4g}%"></div>' for a, b in sig)
        rows.append(f'<div class="tl"><div class="tll">{label}</div>'
                    f'<div class="tlt">{bands}</div></div>')
    axis = "".join(f"<span>{h:02d}</span>" for h in (0, 4, 8, 12, 16, 20, 24))
    rows.append(f'<div class="axis"><div></div><div class="axl">{axis}</div></div>')
    rows.append(
        f'<div class="lgd"><span><i style="background:var(--ai)"></i>'
        f'{T["lg_us"][lang]}</span><span><i style="background:var(--surf);'
        f'border:1px solid var(--grid)"></i>{T["lg_cl"][lang]}</span></div>')
    return "".join(rows)


def _sched_table(lang: str) -> str:
    """One table: every region's US-stock window in local time."""
    head = (f'<tr><th>{T["region_h"][lang]}</th>'
            f'<th>{MARKET_NAME["us-stock"][lang]}</th></tr>')
    rows = []
    for canon, tz in REGIONS:
        us = _window_text(_bands("us-stock", tz), lang)
        rows.append(f'<tr><td class="m">{REGION_NAME[canon][lang]}</td>'
                    f'<td class="h">{us}</td></tr>')
    return f'<div class="sw"><table>{head}{"".join(rows)}</table></div>'


def _matrix_table(lang: str) -> str:
    head = "".join(f"<th>{MARKET_NAME[m][lang]}</th>" for m in MATRIX_COLS)
    yes = f'<span class="pill p-go">{T["pill_yes"][lang]}</span>'
    pend = f'<span class="pill p-w">{T["pill_pending"][lang]}</span>'
    rows = []
    for canon, _ in REGIONS:
        cells = "".join(f"<td>{yes if MATRIX[canon][m] == 'y' else pend}</td>"
                        for m in MATRIX_COLS)
        rows.append(f'<tr><td class="m">{REGION_NAME[canon][lang]}</td>{cells}</tr>')
    return (f'<div class="sw"><table><tr><th>{T["region_h"][lang]}</th>{head}</tr>'
            f'{"".join(rows)}</table></div>')


def _venue_table(lang: str) -> str:
    head = (f'<tr><th>{T["region_h"][lang]}</th><th>{T["venue_c1"][lang]}</th>'
            f'<th>{T["venue_c2"][lang]}</th><th>{T["venue_c3"][lang]}</th></tr>')
    rows = []
    for canon, _ in REGIONS:
        v = VENUE[canon]
        cx = v["cx"] or "—"
        if v["cx_soon"]:
            cx += f' <span class="soon">({T["soon"][lang]})</span>'
        note = VENUE_NOTE[v["note"]][lang]
        rows.append(f'<tr><td class="m">{REGION_NAME[canon][lang]}</td>'
                    f'<td>{v["sf"]}</td><td>{cx}</td><td>{note}</td></tr>')
    return f'<div class="sw"><table>{head}{"".join(rows)}</table></div>'


def _roadmap(lang: str) -> str:
    items = []
    for r in ROADMAP:
        tag = f'<span class="tag">{LIVE_TAG[lang]}</span>' if r["live"] else ""
        cls = "rmi live" if r["live"] else "rmi"
        items.append(f'<div class="{cls}"><b>{r["title"][lang]}{tag}</b>'
                     f'<span>{r["desc"][lang]}</span></div>')
    return '<div class="rm">' + "".join(items) + "</div>"


def build(lang: str) -> str:
    t = lambda k: T[k][lang]  # noqa: E731
    always = "".join(f"<span>{MARKET_NAME[m][lang]}</span>" for m in ALWAYS)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t('title')}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>{t('title')}</h1>
<p class="lede">{t('lede')}</p>

<h2>{t('countries_h')}</h2>
<p>{t('countries_p')}</p>

<h2>{t('always_h')}</h2>
<p>{t('always_p')}</p>
<div class="fig"><div class="always">{always}</div></div>

<h2>{t('gap_h')}</h2>
<p>{t('gap_p')}</p>
<div class="fig">{_gap_bars(lang)}<p class="cap">{t('gap_cap')}</p></div>

<h2>{t('sched_h')}</h2>
<p>{t('sched_p')}</p>
{_sched_table(lang)}

<h2>{t('tl_h')}</h2>
<p>{t('tl_p')}</p>
<div class="fig">{_timeline(lang)}<p class="cap">{t('tl_cap')}</p></div>

<h2>{t('matrix_h')}</h2>
<p>{t('matrix_p')}</p>
{_matrix_table(lang)}

<h2>{t('venue_h')}</h2>
<p>{t('venue_p')}</p>
{_venue_table(lang)}

<h2>{t('roadmap_h')}</h2>
{_roadmap(lang)}

<h2>{t('note_h')}</h2>
<div class="note"><p>{t('dst')}</p></div>

<h2>{t('set_h')}</h2>
<p>{t('set_p')}</p>
</main>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    for lang in LANGS:
        path = OUT / f"market-hours-{lang}.html"
        path.write_text(build(lang), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
