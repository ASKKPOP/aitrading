"""Localization catalogue for the desk-cycle free text the platform authors.

These are the strings behind /api/automation/ai-analysis — the gate-skip
reasons the run engine writes into the journal, plus the one report string the
platform (not the model) authors when a light cycle returns no verdict.

Separate file from market_i18n_data.MARKET_PHRASES because these are not
market-intel strings; same shape and the same matcher, so market_i18n indexes
both catalogues into one lookup. English source key -> {ko, ja, th, vi, id};
`en` is passthrough and never stored. A string missing here falls through to
the cached LLM translator, exactly like the desk's model-written report.

`{}` marks an interpolated value, matched left-to-right, exactly like
i18n_errors.

Coverage is evidence-led: prod's last 6,000 gate_skip rows (2026-08-07) held
only five distinct reasons — "decision is 'hold'" (78), 'loss cooldown' (16),
're-entry cooldown (45m at 2x leverage)' (4), 'desk retired this run' (3) and
one dust skip. The rest below are the other reasons run_engine/automation can
emit, entered so a quiet rail does not surface untranslated the first time it
fires.

th/vi/id below are machine-quality and want a native proofread before they are
treated as final — see the i18n-translations-need-native-review note.
"""

DESK_PHRASES: dict[str, dict[str, str]] = {
    # ── the verdict itself declined to trade ────────────────────────────
    # Spelled out per action rather than interpolated: the quoted verb is the
    # part that has to localize, and there are only four of them.
    "decision is 'hold'": {
        'ko': "판단이 '보류'였습니다",
        'ja': "判断が「ホールド」でした",
        'th': "การตัดสินใจคือ 'ถือไว้'",
        'vi': "quyết định là 'giữ nguyên'",
        'id': "keputusannya adalah 'tahan'",
    },
    "decision is 'buy'": {
        'ko': "판단이 '매수'였습니다",
        'ja': "判断が「買い」でした",
        'th': "การตัดสินใจคือ 'ซื้อ'",
        'vi': "quyết định là 'mua'",
        'id': "keputusannya adalah 'beli'",
    },
    "decision is 'sell'": {
        'ko': "판단이 '매도'였습니다",
        'ja': "判断が「売り」でした",
        'th': "การตัดสินใจคือ 'ขาย'",
        'vi': "quyết định là 'bán'",
        'id': "keputusannya adalah 'jual'",
    },
    "decision is 'retire'": {
        'ko': "판단이 '슬롯 반납'이었습니다",
        'ja': "判断が「スロット返却」でした",
        'th': "การตัดสินใจคือ 'คืนสล็อต'",
        'vi': "quyết định là 'trả lại suất'",
        'id': "keputusannya adalah 'kembalikan slot'",
    },

    # ── cooldowns ───────────────────────────────────────────────────────
    'loss cooldown': {
        'ko': '손실 후 쿨다운',
        'ja': '損失後のクールダウン',
        'th': 'พักหลังขาดทุน',
        'vi': 'nghỉ sau khi lỗ',
        'id': 'jeda setelah rugi',
    },
    'adapt loss cooldown': {
        'ko': '적응 손실 쿨다운',
        'ja': 'アダプト損失クールダウン',
        'th': 'พักหลังขาดทุน (โหมดปรับตัว)',
        'vi': 'nghỉ sau khi lỗ (chế độ thích ứng)',
        'id': 'jeda rugi (mode adaptif)',
    },
    're-entry cooldown ({}m at {}x leverage)': {
        'ko': '재진입 쿨다운 ({}분, {}배 레버리지)',
        'ja': '再エントリーのクールダウン（{}分、{}倍レバレッジ）',
        'th': 'พักก่อนเข้าใหม่ ({} นาที ที่เลเวอเรจ {}x)',
        'vi': 'nghỉ trước khi vào lại ({} phút, đòn bẩy {}x)',
        'id': 'jeda sebelum masuk lagi ({} menit, leverage {}x)',
    },
    'adapt re-entry blocked after losing close': {
        'ko': '손실 종료 후 재진입이 차단되었습니다',
        'ja': '損失クローズ後の再エントリーがブロックされました',
        'th': 'ห้ามเข้าใหม่หลังปิดขาดทุน',
        'vi': 'chặn vào lại sau khi đóng lệnh lỗ',
        'id': 'masuk kembali diblokir setelah tutup rugi',
    },
    'add_limit: cooldown {}m since the last add': {
        'ko': '추가 매수 제한: 마지막 추가 이후 {}분 쿨다운',
        'ja': '買い増し制限: 前回の買い増しから{}分のクールダウン',
        'th': 'จำกัดการเพิ่มไม้: พัก {} นาทีนับจากการเพิ่มครั้งล่าสุด',
        'vi': 'giới hạn gia tăng: nghỉ {} phút kể từ lần thêm gần nhất',
        'id': 'batas penambahan: jeda {} menit sejak penambahan terakhir',
    },

    # ── the desk handed the slot back ───────────────────────────────────
    'desk retired this run': {
        'ko': '데스크가 이 RUN을 종료했습니다',
        'ja': 'デスクがこの RUN を終了しました',
        'th': 'เดสก์ปิด RUN นี้แล้ว',
        'vi': 'bàn giao dịch đã kết thúc RUN này',
        'id': 'meja menutup RUN ini',
    },
    'adapt_retired': {
        'ko': '적응 로직이 이 RUN을 종료했습니다',
        'ja': 'アダプトロジックがこの RUN を終了しました',
        'th': 'ตรรกะปรับตัวปิด RUN นี้',
        'vi': 'logic thích ứng đã kết thúc RUN này',
        'id': 'logika adaptif menutup RUN ini',
    },

    # ── size / cost rails ───────────────────────────────────────────────
    'dust order skip (margin {} < floor {})': {
        'ko': '주문이 너무 작아 건너뛰었습니다 (증거금 {} < 최소 {})',
        'ja': '注文が小さすぎるためスキップしました（証拠金 {} < 下限 {}）',
        'th': 'ข้ามคำสั่งที่เล็กเกินไป (มาร์จิ้น {} < ขั้นต่ำ {})',
        'vi': 'bỏ qua lệnh quá nhỏ (ký quỹ {} < mức tối thiểu {})',
        'id': 'lewati order terlalu kecil (margin {} < minimum {})',
    },
    'budget_headroom_skip': {
        'ko': '예산 여유가 부족해 건너뛰었습니다',
        'ja': '予算の余裕が不足のためスキップしました',
        'th': 'ข้ามเพราะงบประมาณไม่พอ',
        'vi': 'bỏ qua vì không còn dư ngân sách',
        'id': 'dilewati karena sisa anggaran tidak cukup',
    },
    'confidence {} below threshold {}': {
        'ko': '신뢰도 {}가 기준치 {}보다 낮습니다',
        'ja': '信頼度 {} が基準値 {} を下回っています',
        'th': 'ความเชื่อมั่น {} ต่ำกว่าเกณฑ์ {}',
        'vi': 'độ tin cậy {} thấp hơn ngưỡng {}',
        'id': 'keyakinan {} di bawah ambang {}',
    },

    # ── nothing to trade against ────────────────────────────────────────
    'market closed': {
        'ko': '장이 마감되었습니다',
        'ja': '市場が閉じています',
        'th': 'ตลาดปิด',
        'vi': 'thị trường đã đóng cửa',
        'id': 'pasar tutup',
    },
    'spot sell with no inventory — treated as hold': {
        'ko': '보유 수량이 없어 현물 매도를 할 수 없어 보류로 처리했습니다',
        'ja': '在庫がなく現物売却できないためホールドとして扱いました',
        'th': 'ไม่มีของในมือจึงขายสปอตไม่ได้ — ถือว่าเป็นการถือไว้',
        'vi': 'không có hàng nên không bán giao ngay được — coi như giữ nguyên',
        'id': 'tidak ada stok sehingga jual spot tidak mungkin — dianggap tahan',
    },
    'scanner: no candidates available': {
        'ko': '스캐너가 후보 종목을 찾지 못했습니다',
        'ja': 'スキャナーが候補銘柄を見つけられませんでした',
        'th': 'สแกนเนอร์ไม่พบตัวเลือก',
        'vi': 'bộ quét không tìm được mã nào phù hợp',
        'id': 'pemindai tidak menemukan kandidat',
    },
    'no valid price in decision': {
        'ko': '판단에 유효한 가격이 없었습니다',
        'ja': '判断に有効な価格がありませんでした',
        'th': 'ไม่มีราคาที่ใช้ได้ในการตัดสินใจ',
        'vi': 'quyết định không có mức giá hợp lệ',
        'id': 'tidak ada harga valid dalam keputusan',
    },
    'no gate verdict': {
        'ko': '게이트 판정이 없었습니다',
        'ja': 'ゲートの判定がありませんでした',
        'th': 'ไม่มีผลตัดสินจากประตูตรวจ',
        'vi': 'không có phán quyết từ cổng kiểm',
        'id': 'tidak ada putusan dari gerbang',
    },

    # ── switched off, or held by the operator ───────────────────────────
    'auto_execute off': {
        'ko': '자동 실행이 꺼져 있습니다',
        'ja': '自動執行がオフです',
        'th': 'ปิดการทำงานอัตโนมัติอยู่',
        'vi': 'tự động thực thi đang tắt',
        'id': 'eksekusi otomatis dimatikan',
    },
    'account AI automation held by master switch': {
        'ko': '마스터 스위치로 계정의 AI 자동매매가 정지되어 있습니다',
        'ja': 'マスタースイッチによりアカウントの AI 自動売買が停止中です',
        'th': 'ระบบอัตโนมัติ AI ของบัญชีถูกหยุดด้วยสวิตช์หลัก',
        'vi': 'tự động hóa AI của tài khoản đang bị giữ bởi công tắc tổng',
        'id': 'otomatisasi AI akun ditahan oleh sakelar utama',
    },
    'account held (master switch, mid-cycle)': {
        'ko': '사이클 도중 마스터 스위치로 계정이 정지되었습니다',
        'ja': 'サイクル途中にマスタースイッチでアカウントが停止されました',
        'th': 'บัญชีถูกหยุดด้วยสวิตช์หลักระหว่างรอบ',
        'vi': 'tài khoản bị giữ bởi công tắc tổng giữa chu kỳ',
        'id': 'akun ditahan sakelar utama di tengah siklus',
    },
    'master-hold check unavailable': {
        'ko': '마스터 정지 상태를 확인할 수 없었습니다',
        'ja': 'マスター停止の状態を確認できませんでした',
        'th': 'ตรวจสอบสถานะการหยุดหลักไม่ได้',
        'vi': 'không kiểm tra được trạng thái giữ tổng',
        'id': 'status tahan utama tidak dapat diperiksa',
    },
    'master-hold recheck unavailable': {
        'ko': '마스터 정지 상태를 다시 확인할 수 없었습니다',
        'ja': 'マスター停止の状態を再確認できませんでした',
        'th': 'ตรวจสอบสถานะการหยุดหลักซ้ำไม่ได้',
        'vi': 'không kiểm tra lại được trạng thái giữ tổng',
        'id': 'pemeriksaan ulang tahan utama tidak tersedia',
    },

    # ── infrastructure, not a trading judgement ─────────────────────────
    'not claimed (lease held elsewhere or not running)': {
        'ko': '다른 워커가 점유 중이거나 실행 중이 아닙니다',
        'ja': '他のワーカーが保持中、または実行中ではありません',
        'th': 'ถูกจองโดยตัวประมวลผลอื่น หรือไม่ได้กำลังทำงาน',
        'vi': 'đang do tiến trình khác giữ, hoặc không chạy',
        'id': 'sedang dipegang proses lain, atau tidak berjalan',
    },
    'adapt state fence lost': {
        'ko': '적응 상태 저장에 실패했습니다',
        'ja': 'アダプト状態の保存に失敗しました',
        'th': 'บันทึกสถานะปรับตัวไม่สำเร็จ',
        'vi': 'không lưu được trạng thái thích ứng',
        'id': 'gagal menyimpan status adaptif',
    },

    # ── the platform's own stand-in for a report ────────────────────────
    # Not the model's words: run_engine writes this when the light cycle
    # returns no parsable verdict, and it lands in the report slot the panel
    # renders. Catalogued so it never shows up English inside a localized list.
    'light cycle: no LLM verdict': {
        'ko': '간이 사이클 — AI 판단을 받지 못했습니다',
        'ja': '簡易サイクル — AI の判定を取得できませんでした',
        'th': 'รอบแบบเบา — ไม่ได้รับคำตัดสินจาก AI',
        'vi': 'chu kỳ rút gọn — không nhận được phán quyết từ AI',
        'id': 'siklus ringan — tidak ada putusan dari AI',
    },
}
