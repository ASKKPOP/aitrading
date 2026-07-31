"""Localization catalogue for the market-intel free-text the platform itself
authors — the fixed strings behind /financial-events (macro explanations,
news-category labels/descriptions, the stock factor phrases, macro verdict
summaries).

This is deliberately SEPARATE from i18n_errors_data.MESSAGES: that catalogue's
drift test asserts every key is a message some route actually raises, and these
are not errors. Same shape though — English source key -> {ko, ja, th, vi, id};
`en` is passthrough and never stored. A string missing here is served in
English (or falls through to the cached LLM translator for external text).

`{}` marks an interpolated value, matched left-to-right, exactly like
i18n_errors. None of the current entries interpolate, but the matcher supports
it so a templated phrase can be added without a code change.

th/vi/id below are machine-quality and want a native proofread before they are
treated as final — see the i18n-translations-need-native-review note.
"""

MARKET_PHRASES: dict[str, dict[str, str]] = {
    # ── news category labels ────────────────────────────────────────────
    'Equities': {'ko': '주식', 'ja': '株式', 'th': 'หุ้น', 'vi': 'Cổ phiếu', 'id': 'Saham'},
    'Macro': {'ko': '매크로', 'ja': 'マクロ', 'th': 'มหภาค', 'vi': 'Vĩ mô', 'id': 'Makro'},
    'Crypto': {'ko': '크립토', 'ja': '暗号資産', 'th': 'คริปโต', 'vi': 'Tiền mã hóa', 'id': 'Kripto'},
    'Commodities': {'ko': '원자재', 'ja': 'コモディティ', 'th': 'สินค้าโภคภัณฑ์', 'vi': 'Hàng hóa', 'id': 'Komoditas'},

    # ── news category descriptions ──────────────────────────────────────
    'Stocks, ETFs, and company market developments.': {
        'ko': '주식, ETF, 기업 시장 동향.',
        'ja': '株式・ETF・企業の市場動向。',
        'th': 'หุ้น ETF และความเคลื่อนไหวของตลาดบริษัท',
        'vi': 'Cổ phiếu, ETF và diễn biến thị trường doanh nghiệp.',
        'id': 'Saham, ETF, dan perkembangan pasar perusahaan.',
    },
    'Macro regime, policy, and broad economic context.': {
        'ko': '매크로 국면, 정책, 거시 경제 배경.',
        'ja': 'マクロレジーム、政策、広範な経済状況。',
        'th': 'ภาวะมหภาค นโยบาย และบริบทเศรษฐกิจโดยรวม',
        'vi': 'Chế độ vĩ mô, chính sách và bối cảnh kinh tế tổng thể.',
        'id': 'Kondisi makro, kebijakan, dan konteks ekonomi secara luas.',
    },
    'Crypto market headlines anchored on BTC and ETH.': {
        'ko': 'BTC와 ETH를 중심으로 한 크립토 시장 뉴스.',
        'ja': 'BTCとETHを中心とした暗号資産市場のニュース。',
        'th': 'ข่าวตลาดคริปโตที่ยึดกับ BTC และ ETH',
        'vi': 'Tin tức thị trường tiền mã hóa xoay quanh BTC và ETH.',
        'id': 'Berita pasar kripto yang berpusat pada BTC dan ETH.',
    },
    'Energy, transport, and commodity-linked events.': {
        'ko': '에너지, 운송, 원자재 관련 이벤트.',
        'ja': 'エネルギー・輸送・商品関連のイベント。',
        'th': 'เหตุการณ์ด้านพลังงาน การขนส่ง และสินค้าโภคภัณฑ์',
        'vi': 'Các sự kiện liên quan đến năng lượng, vận tải và hàng hóa.',
        'id': 'Peristiwa terkait energi, transportasi, dan komoditas.',
    },

    # ── macro signal labels ─────────────────────────────────────────────
    'BTC trend': {'ko': 'BTC 추세', 'ja': 'BTCトレンド', 'th': 'แนวโน้ม BTC', 'vi': 'Xu hướng BTC', 'id': 'Tren BTC'},
    'QQQ trend': {'ko': 'QQQ 추세', 'ja': 'QQQトレンド', 'th': 'แนวโน้ม QQQ', 'vi': 'Xu hướng QQQ', 'id': 'Tren QQQ'},
    'QQQ vs XLP': {'ko': 'QQQ 대 XLP', 'ja': 'QQQ対XLP', 'th': 'QQQ เทียบ XLP', 'vi': 'QQQ so với XLP', 'id': 'QQQ vs XLP'},
    'Safe-haven pressure': {
        'ko': '안전자산 압력', 'ja': '安全資産圧力', 'th': 'แรงกดดันสินทรัพย์ปลอดภัย',
        'vi': 'Áp lực tài sản trú ẩn', 'id': 'Tekanan aset lindung nilai',
    },
    'Macro news tone': {
        'ko': '매크로 뉴스 톤', 'ja': 'マクロニュースのトーン', 'th': 'โทนข่าวมหภาค',
        'vi': 'Sắc thái tin tức vĩ mô', 'id': 'Nada berita makro',
    },

    # ── macro signal explanations ───────────────────────────────────────
    'BTC momentum remains positive over the last week.': {
        'ko': '최근 한 주간 BTC 모멘텀이 긍정적으로 유지되고 있습니다.',
        'ja': '過去1週間、BTCのモメンタムはプラスを維持しています。',
        'th': 'ในสัปดาห์ที่ผ่านมาโมเมนตัมของ BTC ยังคงเป็นบวก',
        'vi': 'Động lượng BTC vẫn tích cực trong tuần qua.',
        'id': 'Momentum BTC tetap positif selama sepekan terakhir.',
    },
    'BTC weakened materially over the last week.': {
        'ko': '최근 한 주간 BTC가 뚜렷하게 약세를 보였습니다.',
        'ja': '過去1週間、BTCは大きく下落しました。',
        'th': 'ในสัปดาห์ที่ผ่านมา BTC อ่อนตัวลงอย่างมีนัยสำคัญ',
        'vi': 'BTC suy yếu đáng kể trong tuần qua.',
        'id': 'BTC melemah signifikan selama sepekan terakhir.',
    },
    'BTC momentum is mixed.': {
        'ko': 'BTC 모멘텀이 혼조세입니다.',
        'ja': 'BTCのモメンタムはまちまちです。',
        'th': 'โมเมนตัมของ BTC ผสมผสาน',
        'vi': 'Động lượng BTC trái chiều.',
        'id': 'Momentum BTC beragam.',
    },
    'Growth equities are trending higher.': {
        'ko': '성장주가 상승 추세입니다.',
        'ja': 'グロース株は上昇トレンドにあります。',
        'th': 'หุ้นเติบโตกำลังมีแนวโน้มสูงขึ้น',
        'vi': 'Cổ phiếu tăng trưởng đang có xu hướng đi lên.',
        'id': 'Saham pertumbuhan sedang menanjak.',
    },
    'Growth equities are losing momentum.': {
        'ko': '성장주가 모멘텀을 잃고 있습니다.',
        'ja': 'グロース株はモメンタムを失いつつあります。',
        'th': 'หุ้นเติบโตกำลังสูญเสียโมเมนตัม',
        'vi': 'Cổ phiếu tăng trưởng đang mất động lượng.',
        'id': 'Saham pertumbuhan kehilangan momentum.',
    },
    'Growth equity momentum is mixed.': {
        'ko': '성장주 모멘텀이 혼조세입니다.',
        'ja': 'グロース株のモメンタムはまちまちです。',
        'th': 'โมเมนตัมหุ้นเติบโตผสมผสาน',
        'vi': 'Động lượng cổ phiếu tăng trưởng trái chiều.',
        'id': 'Momentum saham pertumbuhan beragam.',
    },
    'Growth is outperforming defensive staples.': {
        'ko': '성장주가 방어적 필수소비재를 앞서고 있습니다.',
        'ja': 'グロースがディフェンシブな生活必需品を上回っています。',
        'th': 'หุ้นเติบโตทำผลงานได้ดีกว่าหุ้นตั้งรับกลุ่มสินค้าจำเป็น',
        'vi': 'Nhóm tăng trưởng đang vượt trội so với nhóm phòng thủ thiết yếu.',
        'id': 'Saham pertumbuhan mengungguli saham defensif kebutuhan pokok.',
    },
    'Defensive staples are outperforming growth.': {
        'ko': '방어적 필수소비재가 성장주를 앞서고 있습니다.',
        'ja': 'ディフェンシブな生活必需品がグロースを上回っています。',
        'th': 'หุ้นตั้งรับกลุ่มสินค้าจำเป็นทำผลงานได้ดีกว่าหุ้นเติบโต',
        'vi': 'Nhóm phòng thủ thiết yếu đang vượt trội so với nhóm tăng trưởng.',
        'id': 'Saham defensif kebutuhan pokok mengungguli saham pertumbuhan.',
    },
    'Growth and defensive sectors are balanced.': {
        'ko': '성장주와 방어주가 균형을 이루고 있습니다.',
        'ja': 'グロースとディフェンシブのセクターは拮抗しています。',
        'th': 'กลุ่มเติบโตและกลุ่มตั้งรับอยู่ในภาวะสมดุล',
        'vi': 'Nhóm tăng trưởng và phòng thủ đang cân bằng.',
        'id': 'Sektor pertumbuhan dan defensif seimbang.',
    },
    'Safe-haven assets are bid.': {
        'ko': '안전자산에 매수세가 유입되고 있습니다.',
        'ja': '安全資産に買いが入っています。',
        'th': 'สินทรัพย์ปลอดภัยได้รับแรงซื้อ',
        'vi': 'Tài sản trú ẩn đang được mua vào.',
        'id': 'Aset lindung nilai sedang diburu.',
    },
    'Safe-haven demand is subdued.': {
        'ko': '안전자산 수요가 약합니다.',
        'ja': '安全資産への需要は低調です。',
        'th': 'ความต้องการสินทรัพย์ปลอดภัยอ่อนแรง',
        'vi': 'Nhu cầu tài sản trú ẩn ở mức thấp.',
        'id': 'Permintaan aset lindung nilai lesu.',
    },
    'Safe-haven demand is present but not dominant.': {
        'ko': '안전자산 수요가 있으나 지배적이지는 않습니다.',
        'ja': '安全資産への需要はあるものの支配的ではありません。',
        'th': 'มีความต้องการสินทรัพย์ปลอดภัยแต่ยังไม่เด่นชัด',
        'vi': 'Có nhu cầu tài sản trú ẩn nhưng chưa chiếm ưu thế.',
        'id': 'Permintaan aset lindung nilai ada tetapi tidak dominan.',
    },

    # ── macro news-tone explanations ────────────────────────────────────
    'Macro news snapshot is not available yet.': {
        'ko': '매크로 뉴스 스냅샷이 아직 없습니다.',
        'ja': 'マクロニュースのスナップショットはまだありません。',
        'th': 'ยังไม่มีสแนปช็อตข่าวมหภาค',
        'vi': 'Chưa có ảnh chụp tin tức vĩ mô.',
        'id': 'Snapshot berita makro belum tersedia.',
    },
    'Macro news flow leans constructive.': {
        'ko': '매크로 뉴스 흐름이 긍정적으로 기울어 있습니다.',
        'ja': 'マクロニュースの流れは建設的に傾いています。',
        'th': 'กระแสข่าวมหภาคเอนไปทางบวก',
        'vi': 'Dòng tin tức vĩ mô nghiêng về tích cực.',
        'id': 'Arus berita makro cenderung konstruktif.',
    },
    'Macro news flow leans defensive.': {
        'ko': '매크로 뉴스 흐름이 방어적으로 기울어 있습니다.',
        'ja': 'マクロニュースの流れは守勢に傾いています。',
        'th': 'กระแสข่าวมหภาคเอนไปทางตั้งรับ',
        'vi': 'Dòng tin tức vĩ mô nghiêng về phòng thủ.',
        'id': 'Arus berita makro cenderung defensif.',
    },
    'Macro news flow is mixed.': {
        'ko': '매크로 뉴스 흐름이 혼조세입니다.',
        'ja': 'マクロニュースの流れはまちまちです。',
        'th': 'กระแสข่าวมหภาคผสมผสาน',
        'vi': 'Dòng tin tức vĩ mô trái chiều.',
        'id': 'Arus berita makro beragam.',
    },

    # ── macro verdict summaries (meta.summary) ──────────────────────────
    'Risk appetite is leading across the current macro snapshot.': {
        'ko': '현재 매크로 스냅샷에서는 위험 선호가 우세합니다.',
        'ja': '現在のマクロスナップショットではリスク選好が優勢です。',
        'th': 'ในสแนปช็อตมหภาคปัจจุบัน ความต้องการเสี่ยงเป็นฝ่ายนำ',
        'vi': 'Khẩu vị rủi ro đang dẫn dắt trong ảnh chụp vĩ mô hiện tại.',
        'id': 'Selera risiko mendominasi snapshot makro saat ini.',
    },
    'Defensive pressure dominates the current macro snapshot.': {
        'ko': '현재 매크로 스냅샷에서는 방어적 압력이 우세합니다.',
        'ja': '現在のマクロスナップショットでは守勢の圧力が優勢です。',
        'th': 'แรงกดดันเชิงตั้งรับครอบงำสแนปช็อตมหภาคปัจจุบัน',
        'vi': 'Áp lực phòng thủ chi phối ảnh chụp vĩ mô hiện tại.',
        'id': 'Tekanan defensif mendominasi snapshot makro saat ini.',
    },
    'Macro signals are mixed and do not show a clear regime.': {
        'ko': '매크로 시그널이 혼조세로 뚜렷한 국면을 보이지 않습니다.',
        'ja': 'マクロシグナルはまちまちで、明確なレジームを示していません。',
        'th': 'สัญญาณมหภาคผสมผสานและยังไม่แสดงภาวะที่ชัดเจน',
        'vi': 'Các tín hiệu vĩ mô trái chiều và chưa cho thấy một chế độ rõ ràng.',
        'id': 'Sinyal makro beragam dan belum menunjukkan kondisi yang jelas.',
    },

    # ── stock analysis factors (fixed vocabulary) ───────────────────────
    'Price is above the 20-day moving average.': {
        'ko': '주가가 20일 이동평균선 위에 있습니다.',
        'ja': '価格は20日移動平均線を上回っています。',
        'th': 'ราคาอยู่เหนือค่าเฉลี่ยเคลื่อนที่ 20 วัน',
        'vi': 'Giá nằm trên đường trung bình động 20 ngày.',
        'id': 'Harga berada di atas rata-rata bergerak 20 hari.',
    },
    'Price is below the 20-day moving average.': {
        'ko': '주가가 20일 이동평균선 아래에 있습니다.',
        'ja': '価格は20日移動平均線を下回っています。',
        'th': 'ราคาอยู่ต่ำกว่าค่าเฉลี่ยเคลื่อนที่ 20 วัน',
        'vi': 'Giá nằm dưới đường trung bình động 20 ngày.',
        'id': 'Harga berada di bawah rata-rata bergerak 20 hari.',
    },
    'Price is above the 60-day moving average.': {
        'ko': '주가가 60일 이동평균선 위에 있습니다.',
        'ja': '価格は60日移動平均線を上回っています。',
        'th': 'ราคาอยู่เหนือค่าเฉลี่ยเคลื่อนที่ 60 วัน',
        'vi': 'Giá nằm trên đường trung bình động 60 ngày.',
        'id': 'Harga berada di atas rata-rata bergerak 60 hari.',
    },
    'Price is below the 60-day moving average.': {
        'ko': '주가가 60일 이동평균선 아래에 있습니다.',
        'ja': '価格は60日移動平均線を下回っています。',
        'th': 'ราคาอยู่ต่ำกว่าค่าเฉลี่ยเคลื่อนที่ 60 วัน',
        'vi': 'Giá nằm dưới đường trung bình động 60 ngày.',
        'id': 'Harga berada di bawah rata-rata bergerak 60 hari.',
    },
    'Short-term momentum is positive.': {
        'ko': '단기 모멘텀이 긍정적입니다.',
        'ja': '短期モメンタムはプラスです。',
        'th': 'โมเมนตัมระยะสั้นเป็นบวก',
        'vi': 'Động lượng ngắn hạn tích cực.',
        'id': 'Momentum jangka pendek positif.',
    },
    'Short-term momentum weakened materially.': {
        'ko': '단기 모멘텀이 뚜렷하게 약해졌습니다.',
        'ja': '短期モメンタムが大きく弱まりました。',
        'th': 'โมเมนตัมระยะสั้นอ่อนลงอย่างมีนัยสำคัญ',
        'vi': 'Động lượng ngắn hạn suy yếu đáng kể.',
        'id': 'Momentum jangka pendek melemah signifikan.',
    },
    'Monthly trend remains constructive.': {
        'ko': '월간 추세가 여전히 긍정적입니다.',
        'ja': '月間トレンドは引き続き建設的です。',
        'th': 'แนวโน้มรายเดือนยังคงเป็นบวก',
        'vi': 'Xu hướng theo tháng vẫn tích cực.',
        'id': 'Tren bulanan tetap konstruktif.',
    },
    'Monthly trend remains weak.': {
        'ko': '월간 추세가 여전히 약합니다.',
        'ja': '月間トレンドは引き続き弱いです。',
        'th': 'แนวโน้มรายเดือนยังคงอ่อนแอ',
        'vi': 'Xu hướng theo tháng vẫn yếu.',
        'id': 'Tren bulanan tetap lemah.',
    },
    'Moving averages are stacked in a bullish order.': {
        'ko': '이동평균선이 정배열(강세) 상태입니다.',
        'ja': '移動平均線が強気の並びになっています。',
        'th': 'ค่าเฉลี่ยเคลื่อนที่เรียงตัวในทิศทางขาขึ้น',
        'vi': 'Các đường trung bình động xếp theo thứ tự tăng giá.',
        'id': 'Rata-rata bergerak tersusun dalam urutan bullish.',
    },
    'Moving averages are stacked in a bearish order.': {
        'ko': '이동평균선이 역배열(약세) 상태입니다.',
        'ja': '移動平均線が弱気の並びになっています。',
        'th': 'ค่าเฉลี่ยเคลื่อนที่เรียงตัวในทิศทางขาลง',
        'vi': 'Các đường trung bình động xếp theo thứ tự giảm giá.',
        'id': 'Rata-rata bergerak tersusun dalam urutan bearish.',
    },
    'Price is approaching the recent resistance zone.': {
        'ko': '주가가 최근 저항 구간에 접근하고 있습니다.',
        'ja': '価格は直近のレジスタンス圏に接近しています。',
        'th': 'ราคากำลังเข้าใกล้โซนแนวต้านล่าสุด',
        'vi': 'Giá đang tiến gần vùng kháng cự gần đây.',
        'id': 'Harga mendekati zona resistance terbaru.',
    },
    'Price is holding near recent support.': {
        'ko': '주가가 최근 지지선 부근에서 유지되고 있습니다.',
        'ja': '価格は直近のサポート付近を維持しています。',
        'th': 'ราคายังคงยืนใกล้แนวรับล่าสุด',
        'vi': 'Giá đang giữ gần vùng hỗ trợ gần đây.',
        'id': 'Harga bertahan di dekat support terbaru.',
    },
}
