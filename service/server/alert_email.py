"""Rich alert emails — branded HTML + extended plain text, 6 languages.

The short catalogue sentence in notifications_i18n is written for the in-app
feed and SMS, where space is scarce. In email it left members guessing what a
"member replacement" or "trailing profit lock" actually is (2026-07-31, owner
feedback on the Korean alert digest). This module wraps that same sentence in
a full email:

    header (Sooppiy brand + tagline)
    the alert title/body exactly as journaled
    EXPLAIN[msg_id]  — why this fired / what happens next / what you can do
    live snapshot    — the recipient's active AI runs and their current P&L
    GLOSSARY         — the platform terms this alert uses (fleet, member, …)
    footer           — dashboard link + why-you-received-this note

Everything here is presentation: build_alert_email must never raise into the
send path (send_alert additionally guards it), and every catalogue string is
STATIC — no .format params — so a copy edit can never produce the param-
mismatch English fallback. English is authoritative; ko was reviewed with the
owner, ja/th/vi/id are machine-generated pending native review (same status
as notifications_i18n).
"""
from __future__ import annotations

import html as _html
import logging
from typing import Any, Optional

from analysis_agents import normalize_lang

logger = logging.getLogger(__name__)

SITE_URL = "https://sooppiy.com"
DASHBOARD_URL = f"{SITE_URL}/automation"
_SNAPSHOT_MAX_RUNS = 12      # displayed rows — total/count always cover all runs
_SNAPSHOT_FETCH_CAP = 100    # safety bound on per-run P&L replays per email

# ── section labels / chrome ────────────────────────────────────────────────

_UI: dict[str, dict[str, str]] = {
    'en': {
        'tagline': 'AI trading, watched for you',
        'why': 'Why you received this',
        'next': 'What happens next',
        'action': 'What you can do',
        'status_title': 'Your AI runs right now',
        'glossary': 'Glossary',
        'total': 'Total P&L across active runs',
        'active_runs': 'active run(s)',
        'no_runs': 'You have no active AI runs at the moment.',
        'open_app': 'Open the automation dashboard',
        'footer': ('You are receiving this because alerts are enabled for your '
                   'Sooppiy account. Manage them in Settings → Notifications.'),
    },
    'ko': {
        'tagline': 'AI 트레이딩을 대신 지켜봐 드립니다',
        'why': '이 알림을 받은 이유',
        'next': '앞으로 일어나는 일',
        'action': '할 수 있는 조치',
        'status_title': '현재 AI 런 현황',
        'glossary': '용어 설명',
        'total': '활성 런 전체 손익 합계',
        'active_runs': '개의 활성 런',
        'no_runs': '현재 활성 상태인 AI 런이 없습니다.',
        'open_app': '자동매매 대시보드 열기',
        'footer': ('Sooppiy 계정에 알림이 켜져 있어 발송된 메일입니다. '
                   '설정 → 알림에서 관리할 수 있습니다.'),
    },
    'ja': {
        'tagline': 'AIトレーディングをあなたの代わりに見守ります',
        'why': 'この通知が届いた理由',
        'next': 'これから起こること',
        'action': 'あなたにできること',
        'status_title': '現在のAI Runの状況',
        'glossary': '用語解説',
        'total': 'アクティブなRun全体の損益合計',
        'active_runs': '件のアクティブなRun',
        'no_runs': '現在アクティブなAI Runはありません。',
        'open_app': '自動売買ダッシュボードを開く',
        'footer': ('このメールはSooppiyアカウントでアラートが有効なため送信されました。'
                   '設定 → 通知で管理できます。'),
    },
    'th': {
        'tagline': 'ให้เราเฝ้าดูการเทรดด้วย AI แทนคุณ',
        'why': 'เหตุผลที่คุณได้รับการแจ้งเตือนนี้',
        'next': 'สิ่งที่จะเกิดขึ้นต่อไป',
        'action': 'สิ่งที่คุณทำได้',
        'status_title': 'สถานะรัน AI ของคุณตอนนี้',
        'glossary': 'อภิธานศัพท์',
        'total': 'กำไรขาดทุนรวมของรันที่ทำงานอยู่',
        'active_runs': 'รันที่ทำงานอยู่',
        'no_runs': 'ขณะนี้คุณไม่มีรัน AI ที่ทำงานอยู่',
        'open_app': 'เปิดแดชบอร์ดการเทรดอัตโนมัติ',
        'footer': ('คุณได้รับอีเมลนี้เนื่องจากเปิดการแจ้งเตือนไว้ในบัญชี Sooppiy ของคุณ '
                   'จัดการได้ที่ การตั้งค่า → การแจ้งเตือน'),
    },
    'vi': {
        'tagline': 'Chúng tôi theo dõi giao dịch AI thay cho bạn',
        'why': 'Vì sao bạn nhận được thông báo này',
        'next': 'Điều gì sẽ diễn ra tiếp theo',
        'action': 'Bạn có thể làm gì',
        'status_title': 'Các run AI của bạn hiện tại',
        'glossary': 'Giải thích thuật ngữ',
        'total': 'Tổng lãi/lỗ của các run đang hoạt động',
        'active_runs': 'run đang hoạt động',
        'no_runs': 'Hiện bạn không có run AI nào đang hoạt động.',
        'open_app': 'Mở bảng điều khiển giao dịch tự động',
        'footer': ('Bạn nhận được email này vì đã bật cảnh báo cho tài khoản Sooppiy. '
                   'Quản lý trong Cài đặt → Thông báo.'),
    },
    'id': {
        'tagline': 'Kami memantau trading AI untuk Anda',
        'why': 'Mengapa Anda menerima ini',
        'next': 'Apa yang terjadi selanjutnya',
        'action': 'Apa yang bisa Anda lakukan',
        'status_title': 'Status run AI Anda saat ini',
        'glossary': 'Daftar istilah',
        'total': 'Total laba rugi semua run aktif',
        'active_runs': 'run aktif',
        'no_runs': 'Saat ini Anda tidak memiliki run AI yang aktif.',
        'open_app': 'Buka dasbor trading otomatis',
        'footer': ('Anda menerima email ini karena notifikasi diaktifkan untuk akun '
                   'Sooppiy Anda. Kelola di Pengaturan → Notifikasi.'),
    },
}

# ── per-alert explanations (static text — no format params by design) ──────
# msg_id -> lang -> {'why', 'next', 'action'}

EXPLAIN: dict[str, dict[str, dict[str, str]]] = {
    'hot_issue_position': {
        'en': {
            'why': ('Sooppiy scans the market every hour for hot issues — sentiment '
                    'shocks, macro event windows, sharp price moves. This alert fires '
                    'only when such a trigger touches a symbol you actually hold, so '
                    'it always concerns one of your own open positions.'),
            'next': ('The affected run is escalated automatically: on its next '
                     'scheduled cycle the decision is made by the full AI analyst '
                     'desk (news, technicals, risk) instead of the routine light '
                     'check. Stop-losses and all other safety rails keep working '
                     'the whole time.'),
            'action': ('No action is required — the AI desk performs the deeper '
                       'review on its own. If you prefer to sit out the turbulence, '
                       'you can pause or stop the run on the automation dashboard; '
                       'stopping with flatten closes the position immediately.'),
        },
        'ko': {
            'why': ('Sooppiy는 매시간 시장의 핫이슈(심리 충격, 거시 이벤트 구간, 급격한 '
                    '가격 변동)를 감시합니다. 이 알림은 그런 트리거가 실제로 보유 중인 '
                    '종목에 닿았을 때만 발송되므로, 항상 본인의 미결제 포지션과 관련된 '
                    '내용입니다.'),
            'next': ('영향을 받은 런은 자동으로 승격됩니다. 다음 예정 사이클에서는 평소의 '
                     '간이 점검 대신 풀 AI 데스크(뉴스·기술적 분석·리스크 분석가)가 '
                     '판단을 내립니다. 그동안에도 손절매 등 모든 안전장치는 계속 '
                     '작동합니다.'),
            'action': ('별도의 조치는 필요 없습니다 — 심층 검토는 AI 데스크가 알아서 '
                       '수행합니다. 변동성을 피하고 싶다면 자동매매 대시보드에서 런을 '
                       '일시중지하거나 중지할 수 있으며, 청산 옵션과 함께 중지하면 '
                       '포지션이 즉시 정리됩니다.'),
        },
        'ja': {
            'why': ('Sooppiyは毎時間、市場のホットイシュー（センチメント・ショック、'
                    'マクロイベント期間、急激な価格変動）を監視しています。この通知は、'
                    'そうしたトリガーが実際に保有中の銘柄に影響したときにのみ送信される'
                    'ため、常にご自身の建玉に関する内容です。'),
            'next': ('該当するRunは自動的に昇格されます。次の予定サイクルでは、通常の'
                     '簡易チェックの代わりにフルAIデスク（ニュース・テクニカル・リスク'
                     'の各アナリスト）が判断を行います。その間もストップロスなどの安全'
                     '装置はすべて作動し続けます。'),
            'action': ('特に操作は不要です — 詳細なレビューはAIデスクが自動で行います。'
                       '荒れた相場を避けたい場合は、自動売買ダッシュボードからRunを一時'
                       '停止または停止できます。手仕舞いオプション付きで停止すると、'
                       'ポジションは即座にクローズされます。'),
        },
        'th': {
            'why': ('Sooppiy สแกนตลาดทุกชั่วโมงเพื่อหาประเด็นร้อน เช่น ความผันผวนด้านจิตวิทยา '
                    'ช่วงเหตุการณ์มหภาค หรือราคาเคลื่อนไหวรุนแรง การแจ้งเตือนนี้จะส่งเฉพาะเมื่อ'
                    'ทริกเกอร์นั้นกระทบเหรียญ/หุ้นที่คุณถืออยู่จริง จึงเกี่ยวข้องกับสถานะที่เปิดอยู่ของคุณเสมอ'),
            'next': ('รันที่ได้รับผลกระทบจะถูกยกระดับโดยอัตโนมัติ: ในรอบถัดไปการตัดสินใจจะทำโดย'
                     'ทีมวิเคราะห์ AI เต็มรูปแบบ (ข่าว เทคนิค ความเสี่ยง) แทนการตรวจแบบย่อ '
                     'ระหว่างนี้จุดตัดขาดทุนและระบบป้องกันทั้งหมดยังทำงานตามปกติ'),
            'action': ('ไม่จำเป็นต้องทำอะไร — ทีม AI จะตรวจสอบเชิงลึกให้เอง หากต้องการหลีกเลี่ยง'
                       'ความผันผวน คุณสามารถหยุดชั่วคราวหรือหยุดรันได้จากแดชบอร์ดการเทรดอัตโนมัติ '
                       'การหยุดพร้อมปิดสถานะจะปิดสถานะทันที'),
        },
        'vi': {
            'why': ('Sooppiy quét thị trường mỗi giờ để tìm các sự kiện nóng — cú sốc '
                    'tâm lý, khung sự kiện vĩ mô, biến động giá mạnh. Cảnh báo này chỉ '
                    'được gửi khi sự kiện đó chạm đến mã bạn đang nắm giữ, nên luôn '
                    'liên quan đến vị thế đang mở của chính bạn.'),
            'next': ('Run bị ảnh hưởng sẽ được nâng cấp tự động: ở chu kỳ kế tiếp, '
                     'quyết định sẽ do bàn phân tích AI đầy đủ (tin tức, kỹ thuật, rủi '
                     'ro) đưa ra thay vì kiểm tra nhanh thông thường. Trong suốt thời '
                     'gian đó, cắt lỗ và mọi cơ chế an toàn vẫn hoạt động.'),
            'action': ('Bạn không cần làm gì — bàn AI sẽ tự thực hiện việc rà soát sâu. '
                       'Nếu muốn đứng ngoài giai đoạn biến động, bạn có thể tạm dừng '
                       'hoặc dừng run trên bảng điều khiển; dừng kèm đóng vị thế sẽ '
                       'đóng vị thế ngay lập tức.'),
        },
        'id': {
            'why': ('Sooppiy memindai pasar setiap jam untuk isu penting — guncangan '
                    'sentimen, jendela peristiwa makro, pergerakan harga tajam. '
                    'Peringatan ini hanya dikirim saat pemicu tersebut menyentuh simbol '
                    'yang benar-benar Anda pegang, jadi selalu menyangkut posisi '
                    'terbuka Anda sendiri.'),
            'next': ('Run yang terdampak dinaikkan secara otomatis: pada siklus '
                     'berikutnya keputusan dibuat oleh meja analis AI penuh (berita, '
                     'teknikal, risiko) alih-alih pemeriksaan ringan rutin. Stop loss '
                     'dan semua pengaman lain tetap bekerja sepanjang waktu.'),
            'action': ('Tidak perlu tindakan — meja AI melakukan tinjauan mendalam '
                       'sendiri. Jika ingin menghindari gejolak, Anda dapat menjeda '
                       'atau menghentikan run di dasbor otomatisasi; berhenti dengan '
                       'opsi tutup posisi akan menutup posisi seketika.'),
        },
    },
    'fleet_churn': {
        'en': {
            'why': ('Your Full-Auto fleet runs several member strategies at once. When '
                    'a member is stopped out (stop-loss, retire rail, …) the fleet '
                    'replaces it with a freshly researched candidate. This alert fires '
                    'when unusually many replacements happened in one day — usually a '
                    'sign that a choppy market keeps knocking strategies out.'),
            'next': ('The fleet keeps operating inside its budget and drawdown rails; '
                     'every replacement re-enters with fresh research. If losses '
                     'deepen, the drawdown warning rail pauses new entries and the '
                     'stop rail closes everything automatically.'),
            'action': ('Consider pausing the fleet on the automation dashboard until '
                       'the market calms — frequent churn in a whipsaw market tends to '
                       'accumulate fees and small losses. Resuming later costs '
                       'nothing but time.'),
        },
        'ko': {
            'why': ('Full Auto 플릿은 여러 개의 멤버 전략을 동시에 운용합니다. 어떤 '
                    '멤버가 손절매나 회수 레일 등으로 정리되면, 플릿이 새로 리서치한 '
                    '후보로 그 자리를 교체합니다. 이 알림은 하루 동안 교체가 유난히 '
                    '많이 발생했을 때 발송되며, 대개 요동치는 장세가 전략을 반복해서 '
                    '청산시키고 있다는 신호입니다.'),
            'next': ('플릿은 계속해서 예산과 드로우다운 레일 안에서 운용됩니다. 교체된 '
                     '멤버는 매번 새로운 리서치를 거쳐 재진입합니다. 손실이 깊어지면 '
                     '경고 레일이 신규 진입을 일시중지하고, 스탑 레일이 모든 포지션을 '
                     '자동으로 정리합니다.'),
            'action': ('시장이 진정될 때까지 자동매매 대시보드에서 플릿을 일시중지하는 '
                       '것을 고려하세요. 급등락 장세에서 잦은 교체는 수수료와 소액 '
                       '손실이 누적되기 쉽습니다. 나중에 재개해도 잃는 것은 시간뿐입니다.'),
        },
        'ja': {
            'why': ('Full Autoフリートは複数のメンバー戦略を同時に運用します。メンバー'
                    'がストップロスやリタイアレールで整理されると、フリートは新たに'
                    'リサーチした候補でその枠を入れ替えます。この通知は1日の入れ替えが'
                    '異常に多いときに送信され、通常は荒れた相場が戦略を繰り返し損切り'
                    'させているサインです。'),
            'next': ('フリートは引き続き予算とドローダウンレールの範囲内で運用されます。'
                     '入れ替えのたびに新しいリサーチを経て再エントリーします。損失が'
                     '深まると警告レールが新規エントリーを一時停止し、ストップレールが'
                     'すべてを自動的にクローズします。'),
            'action': ('相場が落ち着くまで、自動売買ダッシュボードからフリートの一時停止'
                       'をご検討ください。乱高下相場での頻繁な入れ替えは手数料と小さな'
                       '損失が積み重なりがちです。後で再開しても失うのは時間だけです。'),
        },
        'th': {
            'why': ('ฟลีท Full Auto ของคุณรันกลยุทธ์สมาชิกหลายตัวพร้อมกัน เมื่อสมาชิกตัวใดถูกปิด'
                    ' (จุดตัดขาดทุน เรลปลดระวาง ฯลฯ) ฟลีทจะแทนที่ด้วยกลยุทธ์ใหม่ที่วิจัยมาสด '
                    'การแจ้งเตือนนี้จะส่งเมื่อมีการเปลี่ยนสมาชิกมากผิดปกติในหนึ่งวัน ซึ่งมักหมายความว่า'
                    'ตลาดที่ผันผวนกำลังเขี่ยกลยุทธ์ของคุณออกซ้ำ ๆ'),
            'next': ('ฟลีทยังคงทำงานภายในงบประมาณและเรลป้องกันการขาดทุน สมาชิกที่ถูกแทนที่จะ'
                     'กลับเข้าตลาดพร้อมงานวิจัยใหม่ทุกครั้ง หากขาดทุนลึกขึ้น เรลเตือนจะหยุดการเข้า'
                     'เทรดใหม่ชั่วคราว และเรลหยุดจะปิดทุกสถานะโดยอัตโนมัติ'),
            'action': ('พิจารณาหยุดฟลีทชั่วคราวจากแดชบอร์ดจนกว่าตลาดจะสงบ — การเปลี่ยนสมาชิกบ่อย'
                       'ในตลาดแกว่งแรงมักสะสมค่าธรรมเนียมและการขาดทุนย่อย การกลับมาเริ่มใหม่'
                       'ภายหลังไม่เสียอะไรนอกจากเวลา'),
        },
        'vi': {
            'why': ('Fleet Full Auto của bạn vận hành nhiều chiến lược thành viên cùng '
                    'lúc. Khi một thành viên bị dừng (cắt lỗ, thu hồi, …), fleet thay '
                    'thế bằng một ứng viên vừa được nghiên cứu mới. Cảnh báo này gửi '
                    'khi số lượt thay thế trong một ngày cao bất thường — thường là '
                    'dấu hiệu thị trường giật cục đang liên tục loại chiến lược của '
                    'bạn.'),
            'next': ('Fleet vẫn hoạt động trong ngân sách và các ngưỡng drawdown; mỗi '
                     'lượt thay thế đều vào lại với nghiên cứu mới. Nếu lỗ sâu hơn, '
                     'ngưỡng cảnh báo sẽ tạm dừng lệnh mới và ngưỡng dừng sẽ tự đóng '
                     'toàn bộ.'),
            'action': ('Cân nhắc tạm dừng fleet trên bảng điều khiển cho đến khi thị '
                       'trường ổn định — thay thế liên tục trong thị trường giật cục '
                       'dễ tích lũy phí và các khoản lỗ nhỏ. Tiếp tục sau đó chỉ mất '
                       'thời gian, không mất gì khác.'),
        },
        'id': {
            'why': ('Fleet Full Auto Anda menjalankan beberapa strategi anggota '
                    'sekaligus. Saat satu anggota terhenti (stop loss, rel penarikan, '
                    '…), fleet menggantinya dengan kandidat baru hasil riset segar. '
                    'Peringatan ini dikirim saat pergantian dalam satu hari luar biasa '
                    'banyak — biasanya tanda pasar yang bergejolak terus menggugurkan '
                    'strategi Anda.'),
            'next': ('Fleet tetap beroperasi dalam anggaran dan rel penurunan; setiap '
                     'pengganti masuk kembali dengan riset baru. Jika kerugian '
                     'mendalam, rel peringatan menjeda entri baru dan rel stop menutup '
                     'semuanya secara otomatis.'),
            'action': ('Pertimbangkan menjeda fleet di dasbor sampai pasar tenang — '
                       'pergantian yang sering di pasar bergejolak cenderung '
                       'menumpuk biaya dan kerugian kecil. Melanjutkan nanti hanya '
                       'kehilangan waktu, tidak lebih.'),
        },
    },
    'run_stop_event': {
        'en': {
            'why': ('Every run continuously checks its own safety rails — stop-loss, '
                    'profit target, trailing profit lock, time and price limits, '
                    'no-trade reclaim. One of those rails has now triggered; the alert '
                    'above says which one.'),
            'next': ('The run carries out the action shown above — usually closing '
                     'the position, or holding it under the SL/TP watcher. Realized '
                     'profit or loss is settled to your ledger and the run\'s capital '
                     'is freed for reuse.'),
            'action': ('Nothing is required. You can review the run\'s full trade '
                       'history on the automation dashboard, and start a new run with '
                       'the same or adjusted settings at any time.'),
        },
        'ko': {
            'why': ('모든 런은 자신의 안전장치(손절매, 목표 수익, 추적 이익 보호, '
                    '시간·가격 제한, 무거래 회수)를 상시 점검합니다. 그중 하나가 '
                    '발동했으며, 어떤 장치인지는 위 알림 내용에 표시되어 있습니다.'),
            'next': ('런은 위에 표시된 조치를 수행합니다 — 보통 포지션을 청산하거나, '
                     'SL/TP 워처 관리하에 유지합니다. 확정 손익은 장부에 정산되고 '
                     '해당 런의 자본은 재사용할 수 있도록 회수됩니다.'),
            'action': ('별도의 조치는 필요 없습니다. 자동매매 대시보드에서 런의 전체 '
                       '거래 내역을 확인할 수 있고, 언제든 동일하거나 조정된 설정으로 '
                       '새 런을 시작할 수 있습니다.'),
        },
        'ja': {
            'why': ('すべてのRunは自身の安全装置（ストップロス、利益目標、トレーリング'
                    '利益ロック、時間・価格制限、無取引リタイア）を常時チェックして'
                    'います。そのいずれかが発動しました。どの装置かは上の通知内容に'
                    '記載されています。'),
            'next': ('Runは上記の措置を実行します — 通常はポジションのクローズ、または'
                     'SL/TPウォッチャー管理下での保有です。確定損益は台帳に清算され、'
                     'そのRunの資金は再利用できるよう解放されます。'),
            'action': ('特に操作は不要です。自動売買ダッシュボードでRunの全取引履歴を'
                       '確認でき、いつでも同じ設定または調整した設定で新しいRunを開始'
                       'できます。'),
        },
        'th': {
            'why': ('ทุกรันตรวจสอบระบบป้องกันของตัวเองอย่างต่อเนื่อง — จุดตัดขาดทุน เป้าหมายกำไร '
                    'การล็อกกำไรแบบเลื่อนตาม ขีดจำกัดเวลาและราคา การปลดระวางเพราะไม่มีการเทรด '
                    'ตอนนี้หนึ่งในนั้นทำงานแล้ว การแจ้งเตือนด้านบนบอกว่าเป็นตัวใด'),
            'next': ('รันจะดำเนินการตามที่แสดงด้านบน — โดยปกติคือปิดสถานะ หรือถือไว้ภายใต้'
                     'การเฝ้าระวัง SL/TP กำไรหรือขาดทุนที่เกิดขึ้นจริงจะถูกบันทึกในบัญชี และ'
                     'เงินทุนของรันจะถูกปล่อยให้ใช้ใหม่ได้'),
            'action': ('ไม่จำเป็นต้องทำอะไร คุณสามารถดูประวัติการเทรดทั้งหมดของรันได้ในแดชบอร์ด '
                       'และเริ่มรันใหม่ด้วยการตั้งค่าเดิมหรือปรับใหม่ได้ทุกเมื่อ'),
        },
        'vi': {
            'why': ('Mỗi run liên tục kiểm tra các cơ chế an toàn của chính nó — cắt '
                    'lỗ, mục tiêu lợi nhuận, khóa lợi nhuận trượt, giới hạn thời '
                    'gian/giá, thu hồi do không giao dịch. Một trong số đó vừa kích '
                    'hoạt; thông báo phía trên cho biết là cơ chế nào.'),
            'next': ('Run thực hiện hành động nêu trên — thường là đóng vị thế, hoặc '
                     'giữ dưới sự theo dõi của SL/TP watcher. Lãi/lỗ đã thực hiện '
                     'được ghi vào sổ và vốn của run được giải phóng để tái sử dụng.'),
            'action': ('Không cần làm gì. Bạn có thể xem toàn bộ lịch sử giao dịch của '
                       'run trên bảng điều khiển, và bắt đầu run mới với cấu hình cũ '
                       'hoặc đã điều chỉnh bất cứ lúc nào.'),
        },
        'id': {
            'why': ('Setiap run terus-menerus memeriksa pengaman miliknya sendiri — '
                    'stop loss, target profit, penguncian profit beruntun, batas waktu '
                    'dan harga, penarikan tanpa transaksi. Salah satunya kini terpicu; '
                    'peringatan di atas menyebutkan yang mana.'),
            'next': ('Run menjalankan tindakan yang tertera di atas — biasanya menutup '
                     'posisi, atau menahannya di bawah pengawas SL/TP. Laba rugi yang '
                     'terealisasi dicatat ke buku Anda dan modal run dibebaskan untuk '
                     'dipakai lagi.'),
            'action': ('Tidak ada yang perlu dilakukan. Anda dapat meninjau riwayat '
                       'transaksi lengkap run di dasbor, dan memulai run baru dengan '
                       'pengaturan sama atau yang disesuaikan kapan saja.'),
        },
    },
    'run_report': {
        'en': {
            'why': ('This is the periodic P&L digest you scheduled for this run — a '
                    'summary of the period\'s profit/loss and trade count, sent at the '
                    'configured frequency.'),
            'next': ('The run continues unchanged. The next digest arrives at the '
                     'same frequency; stop events and thresholds are alerted '
                     'separately and immediately.'),
            'action': ('Change the digest frequency (hourly / daily / weekly / off) in '
                       'the run\'s settings, or open the dashboard for the full trade '
                       'log and equity curve.'),
        },
        'ko': {
            'why': ('이 메일은 이 런에 설정한 정기 손익 요약입니다 — 설정된 주기에 '
                    '맞춰 해당 기간의 손익과 거래 건수를 요약해 보내드립니다.'),
            'next': ('런은 변경 없이 계속 운용됩니다. 다음 요약도 같은 주기로 도착하며, '
                     '스탑 이벤트나 임계값 알림은 별도로 즉시 발송됩니다.'),
            'action': ('런 설정에서 요약 주기(매시간/매일/매주/끄기)를 변경할 수 있고, '
                       '대시보드에서 전체 거래 기록과 자산 곡선을 확인할 수 있습니다.'),
        },
        'ja': {
            'why': ('このメールはこのRunに設定した定期損益レポートです — 設定した頻度'
                    'で、その期間の損益と取引件数をまとめてお送りしています。'),
            'next': ('Runは変更なく継続します。次のレポートも同じ頻度で届きます。'
                     'ストップイベントやしきい値の通知は別途、即時に送信されます。'),
            'action': ('Runの設定でレポート頻度（毎時/毎日/毎週/オフ）を変更できます。'
                       'ダッシュボードでは全取引履歴と資産推移を確認できます。'),
        },
        'th': {
            'why': ('อีเมลนี้คือสรุปกำไรขาดทุนตามรอบเวลาที่คุณตั้งไว้สำหรับรันนี้ — สรุปกำไรขาดทุน'
                    'และจำนวนเทรดของช่วงเวลา ส่งตามความถี่ที่กำหนด'),
            'next': ('รันยังคงทำงานตามเดิม สรุปฉบับถัดไปจะมาตามรอบเดิม ส่วนเหตุการณ์หยุด'
                     'และการแจ้งเตือนเกณฑ์จะถูกส่งแยกต่างหากทันที'),
            'action': ('เปลี่ยนความถี่ของสรุป (รายชั่วโมง/รายวัน/รายสัปดาห์/ปิด) ได้ในการตั้งค่าของรัน '
                       'หรือเปิดแดชบอร์ดเพื่อดูบันทึกการเทรดทั้งหมด'),
        },
        'vi': {
            'why': ('Đây là bản tóm tắt lãi/lỗ định kỳ bạn đã đặt cho run này — tổng '
                    'hợp lãi/lỗ và số lệnh trong kỳ, gửi theo tần suất đã cấu hình.'),
            'next': ('Run tiếp tục hoạt động như cũ. Bản tóm tắt kế tiếp sẽ đến theo '
                     'cùng tần suất; các sự kiện dừng và ngưỡng được cảnh báo riêng và '
                     'ngay lập tức.'),
            'action': ('Thay đổi tần suất tóm tắt (mỗi giờ / hằng ngày / hằng tuần / '
                       'tắt) trong cài đặt của run, hoặc mở bảng điều khiển để xem '
                       'toàn bộ nhật ký giao dịch.'),
        },
        'id': {
            'why': ('Ini adalah ringkasan laba rugi berkala yang Anda jadwalkan untuk '
                    'run ini — rangkuman laba rugi dan jumlah transaksi periode '
                    'tersebut, dikirim sesuai frekuensi yang diatur.'),
            'next': ('Run berlanjut tanpa perubahan. Ringkasan berikutnya datang pada '
                     'frekuensi yang sama; peristiwa stop dan ambang batas '
                     'diberitahukan terpisah dan segera.'),
            'action': ('Ubah frekuensi ringkasan (per jam / harian / mingguan / mati) '
                       'di pengaturan run, atau buka dasbor untuk log transaksi '
                       'lengkap.'),
        },
    },
    'run_threshold_loss': {
        'en': {
            'why': ('You set a loss-threshold notification on this run. Its total P&L '
                    '(realized + unrealized, fees included) has crossed that '
                    'percentage of the run\'s budget.'),
            'next': ('This alert is informational — the run keeps trading. The hard '
                     'protections (max-loss stop, drawdown rails) act separately and '
                     'will stop the run on their own if their levels are hit. You get '
                     'at most one of these alerts per day.'),
            'action': ('If the loss makes you uncomfortable, pause or stop the run on '
                       'the automation dashboard — stopping with flatten closes the '
                       'position immediately. Otherwise no action is needed.'),
        },
        'ko': {
            'why': ('이 런에 손실 임계값 알림을 설정해 두셨습니다. 런의 총 손익(확정 '
                    '+ 미확정, 수수료 포함)이 런 예산 대비 설정한 비율을 넘어섰습니다.'),
            'next': ('이 알림은 참고용이며 런은 계속 거래합니다. 최대 손실 스탑이나 '
                     '드로우다운 레일 같은 강제 보호장치는 별도로 작동하며, 각자의 '
                     '기준에 도달하면 스스로 런을 중지시킵니다. 이 알림은 하루 최대 '
                     '1회만 발송됩니다.'),
            'action': ('손실이 부담스럽다면 자동매매 대시보드에서 런을 일시중지하거나 '
                       '중지하세요 — 청산 옵션과 함께 중지하면 포지션이 즉시 정리됩니다. '
                       '그렇지 않다면 별도의 조치는 필요 없습니다.'),
        },
        'ja': {
            'why': ('このRunに損失しきい値の通知を設定しています。Runの合計損益（確定'
                    '＋未確定、手数料込み）が、Run予算に対する設定比率を超えました。'),
            'next': ('この通知は参考情報であり、Runは取引を継続します。最大損失ストップ'
                     'やドローダウンレールなどの強制保護は別途作動し、各自の水準に達す'
                     'ればRunを自動的に停止します。この通知は1日最大1回のみ送信され'
                     'ます。'),
            'action': ('損失が気になる場合は、自動売買ダッシュボードからRunを一時停止'
                       'または停止してください — 手仕舞いオプション付きで停止すると'
                       'ポジションは即座にクローズされます。そうでなければ操作は不要'
                       'です。'),
        },
        'th': {
            'why': ('คุณตั้งการแจ้งเตือนเกณฑ์ขาดทุนไว้สำหรับรันนี้ กำไรขาดทุนรวมของรัน '
                    '(ที่เกิดขึ้นจริง + ยังไม่เกิดขึ้นจริง รวมค่าธรรมเนียม) ทะลุเปอร์เซ็นต์ที่ตั้งไว้'
                    'ของงบประมาณรันแล้ว'),
            'next': ('การแจ้งเตือนนี้เป็นเพียงข้อมูล — รันยังเทรดต่อ ระบบป้องกันหลัก (จุดหยุดขาดทุนสูงสุด '
                     'เรลป้องกันการขาดทุน) ทำงานแยกต่างหากและจะหยุดรันเองเมื่อถึงระดับของมัน '
                     'คุณจะได้รับการแจ้งเตือนนี้ไม่เกินวันละครั้ง'),
            'action': ('หากกังวลกับการขาดทุน ให้หยุดชั่วคราวหรือหยุดรันจากแดชบอร์ด — การหยุดพร้อม'
                       'ปิดสถานะจะปิดสถานะทันที มิฉะนั้นไม่จำเป็นต้องทำอะไร'),
        },
        'vi': {
            'why': ('Bạn đã đặt thông báo ngưỡng lỗ cho run này. Tổng lãi/lỗ của nó '
                    '(đã và chưa thực hiện, gồm phí) đã vượt tỷ lệ phần trăm đó so '
                    'với ngân sách run.'),
            'next': ('Cảnh báo này chỉ mang tính thông tin — run vẫn tiếp tục giao '
                     'dịch. Các bảo vệ cứng (dừng lỗ tối đa, ngưỡng drawdown) hoạt '
                     'động riêng và sẽ tự dừng run khi chạm mức của chúng. Bạn nhận '
                     'tối đa một cảnh báo như vậy mỗi ngày.'),
            'action': ('Nếu khoản lỗ khiến bạn không yên tâm, hãy tạm dừng hoặc dừng '
                       'run trên bảng điều khiển — dừng kèm đóng vị thế sẽ đóng ngay. '
                       'Nếu không, không cần hành động gì.'),
        },
        'id': {
            'why': ('Anda mengatur notifikasi ambang kerugian pada run ini. Total laba '
                    'ruginya (terealisasi + belum terealisasi, termasuk biaya) telah '
                    'melewati persentase tersebut dari anggaran run.'),
            'next': ('Peringatan ini bersifat informasi — run tetap berdagang. '
                     'Perlindungan keras (stop kerugian maksimum, rel penurunan) '
                     'bekerja terpisah dan akan menghentikan run sendiri jika levelnya '
                     'tersentuh. Anda menerima peringatan ini maksimal sekali sehari.'),
            'action': ('Jika kerugian membuat Anda tidak nyaman, jeda atau hentikan '
                       'run di dasbor — berhenti dengan tutup posisi menutup posisi '
                       'seketika. Selain itu tidak perlu tindakan.'),
        },
    },
    'run_threshold_profit': {
        'en': {
            'why': ('You set a profit-threshold notification on this run. Its total '
                    'P&L (realized + unrealized, fees included) has crossed that '
                    'percentage of the run\'s budget.'),
            'next': ('The run keeps trading. If a profit target or trailing profit '
                     'lock is configured, those rails will bank the gain automatically '
                     'when their own conditions are met. You get at most one of these '
                     'alerts per day.'),
            'action': ('To take the profit now, stop the run with flatten on the '
                       'automation dashboard. Otherwise you can simply let the '
                       'configured exit rails manage the position.'),
        },
        'ko': {
            'why': ('이 런에 수익 임계값 알림을 설정해 두셨습니다. 런의 총 손익(확정 '
                    '+ 미확정, 수수료 포함)이 런 예산 대비 설정한 비율을 넘어섰습니다.'),
            'next': ('런은 계속 거래합니다. 목표 수익이나 추적 이익 보호가 설정되어 '
                     '있다면, 각 조건이 충족될 때 해당 장치가 수익을 자동으로 '
                     '확정합니다. 이 알림은 하루 최대 1회만 발송됩니다.'),
            'action': ('지금 수익을 확정하려면 대시보드에서 청산 옵션과 함께 런을 '
                       '중지하세요. 그렇지 않다면 설정된 청산 장치에 포지션 관리를 '
                       '맡겨 두면 됩니다.'),
        },
        'ja': {
            'why': ('このRunに利益しきい値の通知を設定しています。Runの合計損益（確定'
                    '＋未確定、手数料込み）が、Run予算に対する設定比率を超えました。'),
            'next': ('Runは取引を継続します。利益目標やトレーリング利益ロックが設定'
                     'されていれば、それぞれの条件を満たしたときに自動的に利益を確定'
                     'します。この通知は1日最大1回のみ送信されます。'),
            'action': ('今すぐ利益を確定するには、ダッシュボードから手仕舞いオプション'
                       '付きでRunを停止してください。そうでなければ、設定済みの決済'
                       'レールにポジション管理を任せておけます。'),
        },
        'th': {
            'why': ('คุณตั้งการแจ้งเตือนเกณฑ์กำไรไว้สำหรับรันนี้ กำไรขาดทุนรวมของรัน '
                    '(ที่เกิดขึ้นจริง + ยังไม่เกิดขึ้นจริง รวมค่าธรรมเนียม) ทะลุเปอร์เซ็นต์ที่ตั้งไว้'
                    'ของงบประมาณรันแล้ว'),
            'next': ('รันยังเทรดต่อ หากตั้งเป้าหมายกำไรหรือการล็อกกำไรแบบเลื่อนตามไว้ '
                     'ระบบเหล่านั้นจะเก็บกำไรโดยอัตโนมัติเมื่อเงื่อนไขของมันครบ '
                     'คุณจะได้รับการแจ้งเตือนนี้ไม่เกินวันละครั้ง'),
            'action': ('หากต้องการเก็บกำไรตอนนี้ ให้หยุดรันพร้อมปิดสถานะจากแดชบอร์ด '
                       'หรือปล่อยให้ระบบปิดสถานะที่ตั้งไว้จัดการต่อก็ได้'),
        },
        'vi': {
            'why': ('Bạn đã đặt thông báo ngưỡng lợi nhuận cho run này. Tổng lãi/lỗ '
                    'của nó (đã và chưa thực hiện, gồm phí) đã vượt tỷ lệ phần trăm '
                    'đó so với ngân sách run.'),
            'next': ('Run tiếp tục giao dịch. Nếu đã cấu hình mục tiêu lợi nhuận hoặc '
                     'khóa lợi nhuận trượt, các cơ chế đó sẽ tự chốt lời khi điều '
                     'kiện của chúng được đáp ứng. Bạn nhận tối đa một cảnh báo như '
                     'vậy mỗi ngày.'),
            'action': ('Để chốt lời ngay, hãy dừng run kèm đóng vị thế trên bảng điều '
                       'khiển. Nếu không, bạn có thể để các cơ chế thoát lệnh đã cấu '
                       'hình quản lý vị thế.'),
        },
        'id': {
            'why': ('Anda mengatur notifikasi ambang profit pada run ini. Total laba '
                    'ruginya (terealisasi + belum terealisasi, termasuk biaya) telah '
                    'melewati persentase tersebut dari anggaran run.'),
            'next': ('Run tetap berdagang. Jika target profit atau penguncian profit '
                     'beruntun diatur, rel tersebut akan membukukan keuntungan secara '
                     'otomatis saat syaratnya terpenuhi. Anda menerima peringatan ini '
                     'maksimal sekali sehari.'),
            'action': ('Untuk mengambil profit sekarang, hentikan run dengan tutup '
                       'posisi di dasbor. Jika tidak, biarkan rel keluar yang sudah '
                       'diatur mengelola posisi.'),
        },
    },
    'fleet_drawdown_warning': {
        'en': {
            'why': ('Your fleet\'s marked-to-market loss reached the warning rail — a '
                    'fixed percentage of the fleet budget that Sooppiy watches '
                    'continuously.'),
            'next': ('New entries are paused automatically. Open positions and their '
                     'stop-losses stay fully managed. If the loss deepens to the stop '
                     'rail, the fleet closes every position on its own.'),
            'action': ('Protection is already engaged, so no immediate action is '
                       'required. If you resume entries yourself, that decision and '
                       'its risk are yours; many users simply wait, or stop the fleet '
                       'here to cap the loss.'),
        },
        'ko': {
            'why': ('플릿의 평가 손실이 경고 레일에 도달했습니다 — Sooppiy가 상시 '
                    '감시하는, 플릿 예산 대비 고정 비율 기준입니다.'),
            'next': ('신규 진입은 자동으로 일시중지됩니다. 보유 포지션과 손절매는 계속 '
                     '관리됩니다. 손실이 스탑 레일까지 깊어지면 플릿이 스스로 모든 '
                     '포지션을 청산합니다.'),
            'action': ('보호장치가 이미 작동 중이므로 당장 필요한 조치는 없습니다. 직접 '
                       '진입을 재개한다면 그 판단과 위험은 본인 몫입니다. 많은 '
                       '사용자는 그냥 기다리거나, 여기서 플릿을 중지해 손실을 '
                       '제한합니다.'),
        },
        'ja': {
            'why': ('フリートの評価損が警告レールに達しました — Sooppiyが常時監視して'
                    'いる、フリート予算に対する固定比率の水準です。'),
            'next': ('新規エントリーは自動的に一時停止されます。保有ポジションとその'
                     'ストップロスは引き続き完全に管理されます。損失がストップレール'
                     'まで深まると、フリートは自動的に全ポジションをクローズします。'),
            'action': ('保護は既に作動しているため、直ちに必要な操作はありません。'
                       'ご自身でエントリーを再開する場合、その判断とリスクはご自身の'
                       'ものです。多くのユーザーはそのまま待つか、ここでフリートを'
                       '停止して損失を確定させます。'),
        },
        'th': {
            'why': ('การขาดทุนตามราคาตลาดของฟลีทถึงเรลเตือนแล้ว — เป็นเปอร์เซ็นต์คงที่ของ'
                    'งบประมาณฟลีทที่ Sooppiy เฝ้าดูตลอดเวลา'),
            'next': ('การเข้าเทรดใหม่ถูกหยุดชั่วคราวโดยอัตโนมัติ สถานะที่เปิดอยู่และจุดตัดขาดทุน'
                     'ยังถูกจัดการเต็มรูปแบบ หากขาดทุนลึกถึงเรลหยุด ฟลีทจะปิดทุกสถานะเอง'),
            'action': ('ระบบป้องกันทำงานแล้ว จึงไม่จำเป็นต้องทำอะไรทันที หากคุณกลับมาเข้าเทรดเอง '
                       'การตัดสินใจและความเสี่ยงเป็นของคุณ ผู้ใช้จำนวนมากเลือกที่จะรอ '
                       'หรือหยุดฟลีทตรงนี้เพื่อจำกัดการขาดทุน'),
        },
        'vi': {
            'why': ('Khoản lỗ theo giá thị trường của fleet đã chạm ngưỡng cảnh báo — '
                    'một tỷ lệ cố định trên ngân sách fleet mà Sooppiy theo dõi liên '
                    'tục.'),
            'next': ('Lệnh vào mới tự động bị tạm dừng. Các vị thế đang mở và điểm '
                     'dừng lỗ của chúng vẫn được quản lý đầy đủ. Nếu lỗ sâu đến '
                     'ngưỡng dừng, fleet tự đóng mọi vị thế.'),
            'action': ('Cơ chế bảo vệ đã kích hoạt nên không cần hành động ngay. Nếu '
                       'bạn tự tiếp tục vào lệnh, quyết định và rủi ro thuộc về bạn; '
                       'nhiều người dùng chọn chờ, hoặc dừng fleet tại đây để giới '
                       'hạn khoản lỗ.'),
        },
        'id': {
            'why': ('Kerugian mark-to-market fleet Anda mencapai rel peringatan — '
                    'persentase tetap dari anggaran fleet yang dipantau Sooppiy terus-'
                    'menerus.'),
            'next': ('Entri baru dijeda otomatis. Posisi terbuka dan stop loss-nya '
                     'tetap dikelola penuh. Jika kerugian mendalam ke rel stop, fleet '
                     'menutup setiap posisi dengan sendirinya.'),
            'action': ('Perlindungan sudah aktif, jadi tidak perlu tindakan segera. '
                       'Jika Anda melanjutkan entri sendiri, keputusan dan risikonya '
                       'milik Anda; banyak pengguna memilih menunggu, atau '
                       'menghentikan fleet di sini untuk membatasi kerugian.'),
        },
    },
    'fleet_breaker': {
        'en': {
            'why': ('Your fleet\'s loss crossed the hard stop rail — the final '
                    'automatic protection on the fleet budget.'),
            'next': ('Every position is being closed and the fleet stops. Because the '
                     'rail fires at the first check that observes the breach, the '
                     'final booked loss can slightly exceed the threshold (price '
                     'movement between checks, fees).'),
            'action': ('Review the fleet\'s report on the automation dashboard to see '
                       'which members lost and why. When you are ready, you can start '
                       'a new fleet — a smaller budget or fewer members is a common '
                       'next step after a stop.'),
        },
        'ko': {
            'why': ('플릿 손실이 강제 스탑 레일을 넘었습니다 — 플릿 예산을 지키는 '
                    '마지막 자동 보호장치입니다.'),
            'next': ('모든 포지션이 청산되고 플릿은 중지됩니다. 이 레일은 이탈을 처음 '
                     '감지한 점검 시점에 발동하므로, 점검 사이의 가격 변동과 수수료로 '
                     '인해 최종 확정 손실이 임계값을 다소 초과할 수 있습니다.'),
            'action': ('자동매매 대시보드에서 플릿 보고서를 열어 어떤 멤버가 왜 손실을 '
                       '냈는지 확인하세요. 준비가 되면 새 플릿을 시작할 수 있습니다 — '
                       '중지 이후에는 예산을 줄이거나 멤버 수를 줄이는 것이 일반적인 '
                       '다음 단계입니다.'),
        },
        'ja': {
            'why': ('フリートの損失が強制ストップレールを超えました — フリート予算を'
                    '守る最終の自動保護装置です。'),
            'next': ('すべてのポジションがクローズされ、フリートは停止します。この'
                     'レールは超過を最初に検知したチェックで発動するため、チェック間の'
                     '価格変動や手数料により、最終確定損失がしきい値をやや上回ること'
                     'があります。'),
            'action': ('自動売買ダッシュボードでフリートのレポートを確認し、どの'
                       'メンバーがなぜ損失を出したかを確認してください。準備ができたら'
                       '新しいフリートを開始できます — 停止後は予算やメンバー数を'
                       '減らすのが一般的な次のステップです。'),
        },
        'th': {
            'why': ('การขาดทุนของฟลีททะลุเรลหยุดแบบบังคับ — ระบบป้องกันอัตโนมัติขั้นสุดท้าย'
                    'ของงบประมาณฟลีท'),
            'next': ('ทุกสถานะกำลังถูกปิดและฟลีทหยุดทำงาน เนื่องจากเรลนี้ทำงานทันทีที่การตรวจสอบ'
                     'พบการทะลุระดับครั้งแรก การขาดทุนสุดท้ายอาจเกินเกณฑ์เล็กน้อย '
                     '(ราคาเคลื่อนไหวระหว่างการตรวจสอบ ค่าธรรมเนียม)'),
            'action': ('ดูรายงานของฟลีทในแดชบอร์ดเพื่อดูว่าสมาชิกตัวใดขาดทุนและเพราะอะไร '
                       'เมื่อพร้อมแล้วคุณสามารถเริ่มฟลีทใหม่ได้ — งบประมาณที่เล็กลงหรือสมาชิกน้อยลง'
                       'เป็นก้าวถัดไปที่พบบ่อยหลังการหยุด'),
        },
        'vi': {
            'why': ('Khoản lỗ của fleet đã vượt ngưỡng dừng cứng — lớp bảo vệ tự động '
                    'cuối cùng cho ngân sách fleet.'),
            'next': ('Mọi vị thế đang được đóng và fleet dừng lại. Vì ngưỡng này kích '
                     'hoạt ngay tại lần kiểm tra đầu tiên phát hiện vi phạm, khoản lỗ '
                     'chốt cuối cùng có thể hơi vượt ngưỡng (giá biến động giữa các '
                     'lần kiểm tra, phí).'),
            'action': ('Xem báo cáo fleet trên bảng điều khiển để biết thành viên nào '
                       'lỗ và vì sao. Khi sẵn sàng, bạn có thể bắt đầu fleet mới — '
                       'giảm ngân sách hoặc giảm số thành viên là bước tiếp theo phổ '
                       'biến sau một lần dừng.'),
        },
        'id': {
            'why': ('Kerugian fleet Anda melewati rel stop keras — perlindungan '
                    'otomatis terakhir untuk anggaran fleet.'),
            'next': ('Setiap posisi sedang ditutup dan fleet berhenti. Karena rel ini '
                     'terpicu pada pemeriksaan pertama yang mendeteksi pelanggaran, '
                     'kerugian akhir yang dibukukan bisa sedikit melebihi ambang '
                     '(pergerakan harga antar-pemeriksaan, biaya).'),
            'action': ('Tinjau laporan fleet di dasbor untuk melihat anggota mana yang '
                       'rugi dan mengapa. Saat siap, Anda dapat memulai fleet baru — '
                       'anggaran lebih kecil atau anggota lebih sedikit adalah langkah '
                       'lanjutan yang umum setelah stop.'),
        },
    },
    'fleet_partial_build': {
        'en': {
            'why': ('Fleets only compose slots into markets that are open right now '
                    'and have research candidates that pass the safety gates. At '
                    'build time, fewer symbols qualified than the slot count you '
                    'chose — typically because the other markets were closed (e.g. '
                    'a weekend or overnight start).'),
            'next': ('The budget for the missing slots is reserved, not spent. The '
                     'fleet supervisor retries them continuously; as markets open '
                     'and new research qualifies, the empty slots are composed '
                     'automatically and you get another email.'),
            'action': ('Nothing is required. If you prefer a full fleet immediately, '
                       'you can stop this fleet and start it when your target '
                       'markets are open.'),
        },
        'ko': {
            'why': ('플릿은 지금 열려 있는 시장 중 안전 게이트를 통과한 리서치 후보가 있는 '
                    '시장에만 슬롯을 구성합니다. 빌드 시점에 선택하신 슬롯 수보다 적은 종목만 '
                    '조건을 충족했습니다 — 보통 다른 시장이 휴장 중일 때(주말·야간 시작 등) '
                    '발생합니다.'),
            'next': ('비어 있는 슬롯의 예산은 소진되지 않고 예약된 상태로 유지됩니다. 플릿 '
                     '감독자가 계속 재시도하며, 시장이 열리고 새 리서치가 조건을 충족하면 '
                     '빈 슬롯이 자동으로 구성되고 다시 이메일을 보내드립니다.'),
            'action': ('별도의 조치는 필요 없습니다. 처음부터 전체 슬롯을 원하시면 이 플릿을 '
                       '중지하고 목표 시장이 열려 있을 때 시작할 수 있습니다.'),
        },
        'ja': {
            'why': ('フリートは、現在開場中でかつ安全ゲートを通過したリサーチ候補がある市場に'
                    'のみ枠を構成します。ビルド時点で、選択された枠数より少ない銘柄しか条件を'
                    '満たしませんでした — 通常、他の市場が休場中（週末や夜間の開始など）に'
                    '起こります。'),
            'next': ('埋まっていない枠の予算は消費されず、確保されたままです。フリート・'
                     'スーパーバイザーが継続的に再試行し、市場が開き新しいリサーチが条件を'
                     '満たし次第、空き枠は自動的に構成され、改めてメールをお送りします。'),
            'action': ('特に操作は不要です。最初からすべての枠を埋めたい場合は、この'
                       'フリートを停止し、対象市場の開場中に開始し直すこともできます。'),
        },
        'th': {
            'why': ('ฟลีทจะจัดสรรช่องเฉพาะในตลาดที่เปิดทำการอยู่และมีผลวิจัยที่ผ่านเกณฑ์ความ'
                    'ปลอดภัยเท่านั้น ณ เวลาสร้าง มีสัญลักษณ์ที่ผ่านเกณฑ์น้อยกว่าจำนวนช่องที่คุณเลือก '
                    '— โดยทั่วไปเพราะตลาดอื่นปิดทำการ (เช่น เริ่มในวันหยุดสุดสัปดาห์หรือกลางคืน)'),
            'next': ('งบประมาณของช่องที่ยังว่างถูกกันไว้ ไม่ได้ถูกใช้ ตัวควบคุมดูแลฟลีทจะพยายามต่อ'
                     'เนื่อง เมื่อตลาดเปิดและมีผลวิจัยใหม่ที่ผ่านเกณฑ์ ช่องว่างจะถูกจัดสรรโดย'
                     'อัตโนมัติและคุณจะได้รับอีเมลอีกครั้ง'),
            'action': ('ไม่ต้องดำเนินการใด ๆ หากต้องการฟลีทเต็มจำนวนทันที คุณสามารถหยุดฟลีทนี้'
                       'และเริ่มใหม่เมื่อตลาดเป้าหมายเปิดทำการ'),
        },
        'vi': {
            'why': ('Fleet chỉ ghép vị trí vào các thị trường đang mở cửa và có ứng viên '
                    'nghiên cứu vượt qua các cổng an toàn. Tại thời điểm xây dựng, số '
                    'mã đạt chuẩn ít hơn số vị trí bạn chọn — thường do các thị trường '
                    'khác đang đóng cửa (ví dụ bắt đầu vào cuối tuần hoặc ban đêm).'),
            'next': ('Ngân sách của các vị trí còn thiếu được giữ lại, không bị tiêu. Bộ '
                     'giám sát fleet liên tục thử lại; khi thị trường mở cửa và nghiên '
                     'cứu mới đạt chuẩn, các vị trí trống sẽ tự động được ghép và bạn '
                     'sẽ nhận thêm email.'),
            'action': ('Không cần làm gì. Nếu muốn fleet đầy đủ ngay từ đầu, bạn có thể '
                       'dừng fleet này và khởi động khi các thị trường mục tiêu mở cửa.'),
        },
        'id': {
            'why': ('Fleet hanya menyusun slot ke pasar yang sedang buka dan memiliki '
                    'kandidat riset yang lolos gerbang keamanan. Saat pembuatan, '
                    'jumlah simbol yang memenuhi syarat lebih sedikit dari jumlah slot '
                    'yang Anda pilih — biasanya karena pasar lain sedang tutup '
                    '(misalnya mulai di akhir pekan atau malam hari).'),
            'next': ('Anggaran untuk slot yang belum terisi dicadangkan, tidak '
                     'terpakai. Pengawas fleet terus mencoba lagi; saat pasar buka dan '
                     'riset baru memenuhi syarat, slot kosong akan disusun otomatis '
                     'dan Anda menerima email lagi.'),
            'action': ('Tidak perlu tindakan apa pun. Jika ingin fleet penuh sejak '
                       'awal, Anda bisa menghentikan fleet ini dan memulainya saat '
                       'pasar target sedang buka.'),
        },
    },
    'fleet_slots_filled': {
        'en': {
            'why': ('Your fleet had fewer running slots than its target. Markets '
                    'opened or new research qualified, so the supervisor composed '
                    'new slots from the reserved budget.'),
            'next': ('The new members trade under the same safety rails as the rest '
                     'of the fleet. If slots remain, they keep filling automatically '
                     'the same way.'),
            'action': ('Nothing is required. You can review the new members on the '
                       'automation dashboard.'),
        },
        'ko': {
            'why': ('플릿의 가동 슬롯이 목표보다 적었는데, 시장이 열리거나 새 리서치가 조건을 '
                    '충족하여 감독자가 예약된 예산으로 새 슬롯을 구성했습니다.'),
            'next': ('새 멤버는 플릿의 나머지 멤버와 동일한 안전장치 아래에서 거래합니다. '
                     '남은 슬롯이 있으면 같은 방식으로 계속 자동으로 채워집니다.'),
            'action': ('별도의 조치는 필요 없습니다. 자동매매 대시보드에서 새 멤버를 확인할 수 '
                       '있습니다.'),
        },
        'ja': {
            'why': ('フリートの稼働枠が目標を下回っていましたが、市場が開くか新しいリサーチが'
                    '条件を満たしたため、スーパーバイザーが確保済みの予算から新しい枠を構成'
                    'しました。'),
            'next': ('新しいメンバーは、フリートの他のメンバーと同じ安全レールの下で取引します。'
                     '枠が残っている場合は、同じ方法で自動的に埋まり続けます。'),
            'action': ('特に操作は不要です。自動売買ダッシュボードで新しいメンバーを確認'
                       'できます。'),
        },
        'th': {
            'why': ('ฟลีทของคุณมีช่องทำงานน้อยกว่าเป้าหมาย เมื่อตลาดเปิดหรือมีผลวิจัยใหม่ที่ผ่าน'
                    'เกณฑ์ ตัวควบคุมดูแลจึงจัดสรรช่องใหม่จากงบประมาณที่กันไว้'),
            'next': ('สมาชิกใหม่ซื้อขายภายใต้ระบบป้องกันเดียวกับสมาชิกอื่นของฟลีท '
                     'หากยังมีช่องเหลือ ก็จะถูกเติมต่อไปโดยอัตโนมัติด้วยวิธีเดียวกัน'),
            'action': ('ไม่ต้องดำเนินการใด ๆ คุณสามารถดูสมาชิกใหม่ได้ที่แดชบอร์ดการซื้อขาย'
                       'อัตโนมัติ'),
        },
        'vi': {
            'why': ('Fleet của bạn có ít vị trí chạy hơn mục tiêu. Thị trường đã mở '
                    'cửa hoặc nghiên cứu mới đạt chuẩn, nên bộ giám sát đã ghép các '
                    'vị trí mới từ ngân sách dự trữ.'),
            'next': ('Các thành viên mới giao dịch dưới cùng các rào an toàn như phần '
                     'còn lại của fleet. Nếu vẫn còn vị trí trống, chúng sẽ tiếp tục '
                     'được lấp tự động theo cách tương tự.'),
            'action': ('Không cần làm gì. Bạn có thể xem các thành viên mới trên bảng '
                       'điều khiển giao dịch tự động.'),
        },
        'id': {
            'why': ('Fleet Anda memiliki slot berjalan lebih sedikit dari target. '
                    'Pasar telah buka atau riset baru memenuhi syarat, sehingga '
                    'pengawas menyusun slot baru dari anggaran yang dicadangkan.'),
            'next': ('Anggota baru berdagang di bawah rel keamanan yang sama dengan '
                     'anggota fleet lainnya. Jika masih ada slot tersisa, slot akan '
                     'terus terisi otomatis dengan cara yang sama.'),
            'action': ('Tidak perlu tindakan apa pun. Anda dapat meninjau anggota '
                       'baru di dasbor trading otomatis.'),
        },
    },
    'fleet_profit_target': {
        'en': {
            'why': ('Your fleet\'s total gain reached the profit goal you configured '
                    'for it.'),
            'next': ('Every position is closed and the gains are banked to your '
                     'ledger. The fleet then stops — it does not keep trading past '
                     'its goal.'),
            'action': ('Nothing is required. Start a new fleet whenever you like, '
                       'with the same or a fresh configuration.'),
        },
        'ko': {
            'why': ('플릿의 총 수익이 설정해 둔 목표 수익에 도달했습니다.'),
            'next': ('모든 포지션이 청산되고 수익이 장부에 확정됩니다. 이후 플릿은 '
                     '중지됩니다 — 목표를 넘긴 뒤에도 계속 거래하지는 않습니다.'),
            'action': ('별도의 조치는 필요 없습니다. 원할 때 언제든 동일하거나 새로운 '
                       '구성으로 새 플릿을 시작할 수 있습니다.'),
        },
        'ja': {
            'why': ('フリートの合計利益が、設定した利益目標に到達しました。'),
            'next': ('すべてのポジションがクローズされ、利益は台帳に確定されます。'
                     'その後フリートは停止します — 目標を超えて取引を続けることは'
                     'ありません。'),
            'action': ('特に操作は不要です。いつでも同じ構成または新しい構成で、'
                       '新しいフリートを開始できます。'),
        },
        'th': {
            'why': ('กำไรรวมของฟลีทถึงเป้าหมายกำไรที่คุณตั้งไว้แล้ว'),
            'next': ('ทุกสถานะถูกปิดและกำไรถูกบันทึกเข้าบัญชีของคุณ จากนั้นฟลีทจะหยุด — '
                     'มันจะไม่เทรดต่อเมื่อเกินเป้าหมายแล้ว'),
            'action': ('ไม่จำเป็นต้องทำอะไร เริ่มฟลีทใหม่ได้ทุกเมื่อ ด้วยการตั้งค่าเดิมหรือแบบใหม่'),
        },
        'vi': {
            'why': ('Tổng lợi nhuận của fleet đã đạt mục tiêu bạn cấu hình cho nó.'),
            'next': ('Mọi vị thế được đóng và lợi nhuận được ghi vào sổ của bạn. Sau '
                     'đó fleet dừng lại — nó không tiếp tục giao dịch vượt quá mục '
                     'tiêu.'),
            'action': ('Không cần làm gì. Bắt đầu fleet mới bất cứ khi nào bạn muốn, '
                       'với cấu hình cũ hoặc mới.'),
        },
        'id': {
            'why': ('Total keuntungan fleet Anda mencapai target profit yang Anda '
                    'atur.'),
            'next': ('Semua posisi ditutup dan keuntungan dibukukan ke buku Anda. '
                     'Fleet kemudian berhenti — ia tidak terus berdagang melampaui '
                     'targetnya.'),
            'action': ('Tidak ada yang perlu dilakukan. Mulai fleet baru kapan saja, '
                       'dengan konfigurasi yang sama atau baru.'),
        },
    },
    'run_trade_executed': {
        'en': {
            'why': ('On its scheduled cycle, the run\'s AI decided to trade: its '
                    'confidence cleared the minimum-confidence gate you configured, '
                    'so it placed the order shown above.'),
            'next': ('The position is now managed by the run\'s safety rails — '
                     'stop-loss, targets, trailing lock — checked continuously. You '
                     'will be alerted when it closes.'),
            'action': ('Nothing is needed. To trade less often or demand more '
                       'conviction, raise the run\'s confidence gate or lengthen its '
                       'cycle interval in the run settings.'),
        },
        'ko': {
            'why': ('예정된 사이클에서 런의 AI가 거래를 결정했습니다. AI의 신뢰도가 '
                    '설정한 최소 신뢰도 기준을 통과하여 위에 표시된 주문을 '
                    '실행했습니다.'),
            'next': ('이 포지션은 이제 런의 안전장치(손절매, 목표가, 추적 이익 보호)가 '
                     '상시 점검하며 관리합니다. 포지션이 종료되면 다시 알림을 '
                     '보내드립니다.'),
            'action': ('별도의 조치는 필요 없습니다. 거래 빈도를 줄이거나 더 높은 '
                       '확신을 요구하려면, 런 설정에서 신뢰도 기준을 높이거나 사이클 '
                       '주기를 늘리세요.'),
        },
        'ja': {
            'why': ('予定されたサイクルで、RunのAIが取引を決定しました。AIの信頼度が'
                    '設定した最低信頼度ゲートを通過したため、上記の注文を実行しました。'),
            'next': ('このポジションは以後、Runの安全装置（ストップロス、目標価格、'
                     'トレーリングロック）が常時チェックしながら管理します。クローズ'
                     '時には再度通知が届きます。'),
            'action': ('特に操作は不要です。取引頻度を減らしたい、またはより高い確信を'
                       '求めたい場合は、Run設定で信頼度ゲートを引き上げるか、サイクル'
                       '間隔を長くしてください。'),
        },
        'th': {
            'why': ('ในรอบที่กำหนด AI ของรันตัดสินใจเทรด: ความเชื่อมั่นของมันผ่านเกณฑ์'
                    'ความเชื่อมั่นขั้นต่ำที่คุณตั้งไว้ จึงส่งคำสั่งตามที่แสดงด้านบน'),
            'next': ('สถานะนี้จะถูกจัดการโดยระบบป้องกันของรัน — จุดตัดขาดทุน เป้าหมาย '
                     'การล็อกกำไรแบบเลื่อนตาม — ตรวจสอบต่อเนื่อง คุณจะได้รับแจ้งเมื่อปิดสถานะ'),
            'action': ('ไม่จำเป็นต้องทำอะไร หากต้องการเทรดน้อยลงหรือต้องการความมั่นใจสูงขึ้น '
                       'ให้เพิ่มเกณฑ์ความเชื่อมั่นหรือยืดรอบเวลาในการตั้งค่าของรัน'),
        },
        'vi': {
            'why': ('Ở chu kỳ đã lên lịch, AI của run quyết định giao dịch: độ tin '
                    'cậy của nó vượt cổng tin cậy tối thiểu bạn cấu hình, nên nó đặt '
                    'lệnh như hiển thị phía trên.'),
            'next': ('Vị thế giờ được quản lý bởi các cơ chế an toàn của run — cắt '
                     'lỗ, mục tiêu, khóa trượt — kiểm tra liên tục. Bạn sẽ được báo '
                     'khi nó đóng.'),
            'action': ('Không cần làm gì. Để giao dịch ít hơn hoặc đòi hỏi độ chắc '
                       'chắn cao hơn, hãy nâng cổng tin cậy hoặc kéo dài chu kỳ trong '
                       'cài đặt run.'),
        },
        'id': {
            'why': ('Pada siklus terjadwal, AI run memutuskan untuk berdagang: '
                    'keyakinannya melewati gerbang keyakinan minimum yang Anda atur, '
                    'sehingga ia menempatkan order seperti di atas.'),
            'next': ('Posisi kini dikelola oleh pengaman run — stop loss, target, '
                     'kunci beruntun — diperiksa terus-menerus. Anda akan diberi tahu '
                     'saat posisi ditutup.'),
            'action': ('Tidak perlu tindakan. Untuk berdagang lebih jarang atau '
                       'menuntut keyakinan lebih tinggi, naikkan gerbang keyakinan '
                       'atau perpanjang interval siklus di pengaturan run.'),
        },
    },
    'run_goal_restart': {
        'en': {
            'why': ('This run reached its goal and is configured to restart '
                    'automatically, so a new run with identical settings took its '
                    'place.'),
            'next': ('The finished run\'s book is closed and archived; the new run '
                     'starts with a fresh budget and the same rails.'),
            'action': ('Nothing is needed. If you no longer want the strategy to '
                       'continue, stop the new run on the automation dashboard.'),
        },
        'ko': {
            'why': ('이 런은 목표를 달성했고 자동 재시작이 설정되어 있어, 동일한 '
                    '설정의 새 런이 그 자리를 이어받았습니다.'),
            'next': ('종료된 런의 장부는 마감되어 보관되고, 새 런은 새 예산과 동일한 '
                     '안전장치로 시작합니다.'),
            'action': ('별도의 조치는 필요 없습니다. 전략을 더 이상 계속하고 싶지 '
                       '않다면 자동매매 대시보드에서 새 런을 중지하세요.'),
        },
        'ja': {
            'why': ('このRunは目標を達成し、自動再開が設定されているため、同一設定の'
                    '新しいRunが引き継ぎました。'),
            'next': ('終了したRunの台帳はクローズされ保管されます。新しいRunは新しい'
                     '予算と同じ安全装置で開始します。'),
            'action': ('特に操作は不要です。この戦略を続けたくない場合は、自動売買'
                       'ダッシュボードから新しいRunを停止してください。'),
        },
        'th': {
            'why': ('รันนี้บรรลุเป้าหมายและถูกตั้งค่าให้เริ่มใหม่อัตโนมัติ รันใหม่ที่ตั้งค่าเหมือนกัน'
                    'จึงเข้ามาแทนที่'),
            'next': ('บัญชีของรันที่จบแล้วถูกปิดและเก็บถาวร รันใหม่เริ่มด้วยงบประมาณใหม่และ'
                     'ระบบป้องกันชุดเดิม'),
            'action': ('ไม่จำเป็นต้องทำอะไร หากไม่ต้องการให้กลยุทธ์ดำเนินต่อ ให้หยุดรันใหม่'
                       'จากแดชบอร์ด'),
        },
        'vi': {
            'why': ('Run này đã đạt mục tiêu và được cấu hình tự khởi động lại, nên '
                    'một run mới với cấu hình y hệt đã thay thế nó.'),
            'next': ('Sổ của run đã kết thúc được đóng và lưu trữ; run mới bắt đầu '
                     'với ngân sách mới và các cơ chế an toàn như cũ.'),
            'action': ('Không cần làm gì. Nếu không muốn chiến lược tiếp tục, hãy '
                       'dừng run mới trên bảng điều khiển.'),
        },
        'id': {
            'why': ('Run ini mencapai targetnya dan diatur untuk mulai ulang '
                    'otomatis, sehingga run baru dengan pengaturan identik '
                    'menggantikannya.'),
            'next': ('Buku run yang selesai ditutup dan diarsipkan; run baru dimulai '
                     'dengan anggaran baru dan pengaman yang sama.'),
            'action': ('Tidak perlu tindakan. Jika tidak ingin strategi berlanjut, '
                       'hentikan run baru di dasbor.'),
        },
    },
}
# The automation-rule variant carries the same meaning as the run variant.
EXPLAIN['automation_trade_executed'] = EXPLAIN['run_trade_executed']

# ── glossary ───────────────────────────────────────────────────────────────
# term key -> lang -> (term, definition)

GLOSSARY: dict[str, dict[str, tuple[str, str]]] = {
    'run': {
        'en': ('Run', 'One autonomous AI trading session on a single symbol, with '
                      'its own budget, decision cycle and safety rails.'),
        'ko': ('런', '한 종목을 대상으로 하는 독립적인 AI 자동매매 세션. 자체 예산, '
                     '판단 사이클, 안전장치를 갖습니다.'),
        'ja': ('Run', '単一銘柄を対象とする自律的なAIトレーディングセッション。独自の'
                      '予算、判断サイクル、安全装置を持ちます。'),
        'th': ('รัน', 'เซสชันเทรด AI อัตโนมัติสำหรับหนึ่งสัญลักษณ์ มีงบประมาณ รอบการตัดสินใจ '
                      'และระบบป้องกันของตัวเอง'),
        'vi': ('Run', 'Một phiên giao dịch AI tự động trên một mã duy nhất, với ngân '
                      'sách, chu kỳ quyết định và cơ chế an toàn riêng.'),
        'id': ('Run', 'Satu sesi trading AI mandiri pada satu simbol, dengan '
                      'anggaran, siklus keputusan, dan pengaman sendiri.'),
    },
    'fleet': {
        'en': ('Fleet', 'Your Full-Auto trading group: several AI strategy slots '
                        'sharing one budget under common drawdown and stop rails.'),
        'ko': ('플릿', 'Full Auto 자동매매 그룹. 여러 AI 전략 슬롯이 하나의 예산을 '
                       '공유하며, 공통의 드로우다운·스탑 레일 아래에서 운용됩니다.'),
        'ja': ('フリート', 'Full Autoのトレーディンググループ。複数のAI戦略スロットが'
                          '1つの予算を共有し、共通のドローダウン・ストップレールの下で'
                          '運用されます。'),
        'th': ('ฟลีท', 'กลุ่มเทรด Full Auto ของคุณ: ช่องกลยุทธ์ AI หลายช่องแบ่งปันงบประมาณเดียว '
                       'ภายใต้เรลป้องกันการขาดทุนและเรลหยุดร่วมกัน'),
        'vi': ('Fleet', 'Nhóm giao dịch Full Auto của bạn: nhiều ô chiến lược AI chia '
                        'sẻ một ngân sách dưới các ngưỡng drawdown và dừng chung.'),
        'id': ('Fleet', 'Grup trading Full Auto Anda: beberapa slot strategi AI '
                        'berbagi satu anggaran di bawah rel penurunan dan stop '
                        'bersama.'),
    },
    'member': {
        'en': ('Member', 'One strategy slot inside a fleet — a single AI run trading '
                         'one symbol with its own small book.'),
        'ko': ('멤버', '플릿 안의 전략 슬롯 하나. 한 종목을 거래하는 개별 AI 런으로, '
                       '자체의 소규모 장부를 갖습니다.'),
        'ja': ('メンバー', 'フリート内の戦略スロット1つ — 1銘柄を取引する個別のAI Run'
                          'で、独自の小さな台帳を持ちます。'),
        'th': ('สมาชิก', 'ช่องกลยุทธ์หนึ่งช่องในฟลีท — รัน AI เดี่ยวที่เทรดหนึ่งสัญลักษณ์'
                         'พร้อมบัญชีย่อยของตัวเอง'),
        'vi': ('Thành viên', 'Một ô chiến lược trong fleet — một run AI đơn lẻ giao '
                             'dịch một mã với sổ nhỏ riêng.'),
        'id': ('Anggota', 'Satu slot strategi di dalam fleet — satu run AI yang '
                          'memperdagangkan satu simbol dengan buku kecil sendiri.'),
    },
    'replacement': {
        'en': ('Replacement', 'When a member\'s run is stopped out or retired, the '
                              'fleet researches a new candidate strategy and fills '
                              'the slot with it.'),
        'ko': ('교체', '멤버의 런이 손절되거나 회수되면, 플릿이 새 후보 전략을 '
                       '리서치해 그 슬롯을 채우는 것을 말합니다.'),
        'ja': ('入れ替え', 'メンバーのRunが損切りまたはリタイアされたとき、フリートが'
                          '新しい候補戦略をリサーチしてその枠を埋めることです。'),
        'th': ('การเปลี่ยนสมาชิก', 'เมื่อรันของสมาชิกถูกปิดหรือปลดระวาง ฟลีทจะวิจัยกลยุทธ์'
                                   'ตัวเลือกใหม่และเติมช่องนั้นด้วยกลยุทธ์ใหม่'),
        'vi': ('Thay thế', 'Khi run của một thành viên bị dừng hoặc thu hồi, fleet '
                           'nghiên cứu một chiến lược ứng viên mới và lấp vào ô đó.'),
        'id': ('Pergantian', 'Saat run seorang anggota terhenti atau ditarik, fleet '
                             'meriset strategi kandidat baru dan mengisi slot itu '
                             'dengannya.'),
    },
    'cycle': {
        'en': ('Cycle', 'The run\'s scheduled decision check (every few minutes): the '
                        'AI reviews the market and decides to enter, add, hold or '
                        'exit.'),
        'ko': ('사이클', '런의 정기 판단 주기(몇 분 간격). AI가 시장을 검토하고 진입, '
                        '추가, 유지, 청산 여부를 결정합니다.'),
        'ja': ('サイクル', 'Runの定期的な判断チェック（数分ごと）。AIが市場を確認し、'
                          'エントリー・追加・保有・決済を決定します。'),
        'th': ('รอบ', 'การตรวจสอบการตัดสินใจตามกำหนดของรัน (ทุกไม่กี่นาที): AI ทบทวนตลาด'
                      'และตัดสินใจว่าจะเข้า เพิ่ม ถือ หรือออก'),
        'vi': ('Chu kỳ', 'Lần kiểm tra quyết định theo lịch của run (vài phút một '
                         'lần): AI xem xét thị trường và quyết định vào, thêm, giữ '
                         'hay thoát.'),
        'id': ('Siklus', 'Pemeriksaan keputusan terjadwal milik run (tiap beberapa '
                         'menit): AI meninjau pasar dan memutuskan masuk, menambah, '
                         'menahan, atau keluar.'),
    },
    'full_ai_desk': {
        'en': ('Full AI desk', 'The heavyweight analysis path — multiple AI analysts '
                               '(news, technical, risk) instead of the routine light '
                               'check. Used when something important is happening.'),
        'ko': ('풀 AI 데스크', '심층 분석 경로. 평소의 간이 점검 대신 뉴스·기술적 '
                              '분석·리스크를 맡은 여러 AI 분석가가 함께 판단합니다. '
                              '중요한 상황에서 사용됩니다.'),
        'ja': ('フルAIデスク', '重量級の分析パス — 通常の簡易チェックの代わりに、'
                              'ニュース・テクニカル・リスクの複数AIアナリストが判断'
                              'します。重要な局面で使われます。'),
        'th': ('ทีม AI เต็มรูปแบบ', 'เส้นทางวิเคราะห์แบบเข้มข้น — นักวิเคราะห์ AI หลายตัว '
                                    '(ข่าว เทคนิค ความเสี่ยง) แทนการตรวจแบบย่อ ใช้เมื่อมี'
                                    'เหตุการณ์สำคัญ'),
        'vi': ('Bàn AI đầy đủ', 'Lộ trình phân tích chuyên sâu — nhiều nhà phân tích '
                                'AI (tin tức, kỹ thuật, rủi ro) thay cho kiểm tra '
                                'nhanh thông thường. Dùng khi có việc quan trọng.'),
        'id': ('Meja AI penuh', 'Jalur analisis kelas berat — beberapa analis AI '
                                '(berita, teknikal, risiko) alih-alih pemeriksaan '
                                'ringan rutin. Dipakai saat ada hal penting.'),
    },
    'long_short': {
        'en': ('Long / Short', 'A long position profits when the price rises; a short '
                               'position profits when the price falls.'),
        'ko': ('롱 / 숏', '롱 포지션은 가격이 오르면 수익, 숏 포지션은 가격이 내리면 '
                         '수익이 납니다.'),
        'ja': ('ロング / ショート', 'ロングは価格が上がると利益、ショートは価格が'
                                   '下がると利益になります。'),
        'th': ('ลอง / ชอร์ต', 'สถานะลองได้กำไรเมื่อราคาขึ้น สถานะชอร์ตได้กำไรเมื่อราคาลง'),
        'vi': ('Long / Short', 'Vị thế long lãi khi giá tăng; vị thế short lãi khi '
                               'giá giảm.'),
        'id': ('Long / Short', 'Posisi long untung saat harga naik; posisi short '
                               'untung saat harga turun.'),
    },
    'trailing_lock': {
        'en': ('Trailing profit lock', 'Once a position\'s profit clears a floor, the '
                                       'run banks it automatically if too much of the '
                                       'peak profit is given back.'),
        'ko': ('추적 이익 보호', '포지션 수익이 일정 기준을 넘긴 뒤, 최고 수익에서 '
                                '일정 비율 이상 반납되면 런이 자동으로 수익을 '
                                '확정하는 장치입니다.'),
        'ja': ('トレーリング利益ロック', 'ポジションの利益が一定基準を超えた後、'
                                        'ピーク利益から一定以上戻したときにRunが'
                                        '自動的に利益を確定する仕組みです。'),
        'th': ('การล็อกกำไรแบบเลื่อนตาม', 'เมื่อกำไรของสถานะผ่านเกณฑ์ขั้นต่ำแล้ว รันจะเก็บกำไร'
                                          'โดยอัตโนมัติหากกำไรถอยจากจุดสูงสุดมากเกินไป'),
        'vi': ('Khóa lợi nhuận trượt', 'Khi lợi nhuận của vị thế vượt một mức sàn, '
                                       'run sẽ tự chốt lời nếu lợi nhuận rơi quá '
                                       'nhiều từ đỉnh.'),
        'id': ('Kunci profit beruntun', 'Setelah profit posisi melewati lantai '
                                        'minimum, run membukukannya otomatis jika '
                                        'terlalu banyak profit puncak dikembalikan.'),
    },
    'idle_retire': {
        'en': ('No-trade reclaim', 'A run that has not traded for its idle window is '
                                   'closed so its capital can be reused elsewhere.'),
        'ko': ('무거래 회수', '일정 기간 거래가 없던 런을 정리해, 배정된 자본을 다른 '
                             '곳에 재사용할 수 있게 하는 장치입니다.'),
        'ja': ('無取引リタイア', '一定期間取引のなかったRunをクローズし、その資金を'
                                '他で再利用できるようにする仕組みです。'),
        'th': ('การปลดระวางเพราะไม่มีการเทรด', 'รันที่ไม่ได้เทรดตามช่วงเวลาที่กำหนดจะถูกปิด '
                                               'เพื่อให้เงินทุนถูกนำไปใช้ที่อื่นได้'),
        'vi': ('Thu hồi do không giao dịch', 'Run không giao dịch trong khoảng thời '
                                             'gian chờ sẽ bị đóng để vốn có thể được '
                                             'tái sử dụng nơi khác.'),
        'id': ('Penarikan tanpa transaksi', 'Run yang tidak bertransaksi selama '
                                            'jendela idle-nya ditutup agar modalnya '
                                            'bisa dipakai di tempat lain.'),
    },
    'drawdown_rail': {
        'en': ('Drawdown rails', 'Automatic loss protections: at the warning level '
                                 'new entries pause; at the stop level every position '
                                 'is closed automatically.'),
        'ko': ('드로우다운 레일', '자동 손실 보호장치. 경고 수준에서는 신규 진입이 '
                                 '일시중지되고, 스탑 수준에서는 모든 포지션이 자동으로 '
                                 '청산됩니다.'),
        'ja': ('ドローダウンレール', '自動損失保護。警告水準では新規エントリーが一時'
                                    '停止し、ストップ水準ではすべてのポジションが自動'
                                    '的にクローズされます。'),
        'th': ('เรลป้องกันการขาดทุน', 'ระบบป้องกันการขาดทุนอัตโนมัติ: ที่ระดับเตือน การเข้าเทรดใหม่'
                                      'จะหยุดชั่วคราว ที่ระดับหยุด ทุกสถานะจะถูกปิดโดยอัตโนมัติ'),
        'vi': ('Ngưỡng drawdown', 'Bảo vệ lỗ tự động: ở mức cảnh báo, lệnh vào mới '
                                  'tạm dừng; ở mức dừng, mọi vị thế được đóng tự '
                                  'động.'),
        'id': ('Rel penurunan', 'Perlindungan kerugian otomatis: pada level '
                                'peringatan entri baru dijeda; pada level stop setiap '
                                'posisi ditutup otomatis.'),
    },
}

# msg_id -> glossary keys shown under that alert (order = display order)
GLOSSARY_FOR: dict[str, tuple[str, ...]] = {
    'hot_issue_position': ('run', 'cycle', 'full_ai_desk', 'long_short'),
    'fleet_churn': ('fleet', 'member', 'replacement', 'run'),
    'run_stop_event': ('run', 'trailing_lock', 'idle_retire'),
    'run_report': ('run', 'cycle'),
    'run_threshold_loss': ('run', 'drawdown_rail'),
    'run_threshold_profit': ('run', 'trailing_lock'),
    'fleet_drawdown_warning': ('fleet', 'drawdown_rail'),
    'fleet_breaker': ('fleet', 'member', 'drawdown_rail'),
    'fleet_profit_target': ('fleet',),
    'fleet_partial_build': ('fleet', 'member'),
    'fleet_slots_filled': ('fleet', 'member'),
    'run_trade_executed': ('run', 'cycle', 'long_short'),
    'automation_trade_executed': ('run', 'cycle', 'long_short'),
    'run_goal_restart': ('run',),
}


# ── live run snapshot ──────────────────────────────────────────────────────

def run_status_snapshot(user_id: Optional[int]) -> Optional[dict[str, Any]]:
    """Active runs (running/paused/stopping) across every agent of `user_id`,
    each with its current P&L. None on any failure — the email simply omits
    the section rather than blocking the send."""
    if not user_id:
        return None
    try:
        from database import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.* FROM trading_runs r
                   JOIN agents a ON a.id = r.agent_id
                   WHERE a.user_id = ?
                     AND r.status IN ('running', 'paused', 'stopping')
                   ORDER BY r.id DESC LIMIT ?""",
                (user_id, _SNAPSHOT_FETCH_CAP))
            runs = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
        import run_engine
        out: list[dict[str, Any]] = []
        total = 0.0
        for run in runs:
            pnl: Optional[float] = None
            try:
                pnl = float(run_engine.compute_run_pnl(run).get("total") or 0.0)
                total += pnl
            except Exception:  # noqa: BLE001 — show the run, dash the number
                logger.debug("snapshot pnl failed for run %s", run.get("id"),
                             exc_info=True)
            out.append({"id": run["id"], "symbol": run["symbol"],
                        "market": run["market"], "status": run["status"],
                        "pnl": pnl})
        # Total and count cover EVERY active run; only the row list is capped.
        # Under fleet churn "newest 12 by id" is exactly the just-built idle
        # runs — the older position-holding runs (where the P&L lives) fell off
        # the list and the email read $+0.00 while the book was down. Runs with
        # money on the line come first; ties (all-zero) stay newest-first.
        out.sort(key=lambda r: (abs(r["pnl"] or 0.0), r["id"]), reverse=True)
        return {"runs": out[:_SNAPSHOT_MAX_RUNS], "total": total,
                "count": len(out)}
    except Exception:  # noqa: BLE001
        logger.warning("run status snapshot failed for user %s", user_id,
                       exc_info=True)
        return None


def _status_label(status: str, lang: str) -> str:
    from notifications_i18n import TOKENS
    fam = TOKENS.get('status', {})
    return fam.get(lang, {}).get(status) or fam.get('en', {}).get(status) or status


def _pnl_text(pnl: Optional[float]) -> str:
    return "—" if pnl is None else f"${pnl:+,.2f}"


# ── builders ───────────────────────────────────────────────────────────────

def _explain(msg_id: Optional[str], lang: str) -> Optional[dict[str, str]]:
    variants = EXPLAIN.get(msg_id or "")
    if not variants:
        return None
    return variants.get(lang) or variants['en']


def _glossary_entries(msg_id: Optional[str], lang: str) -> list[tuple[str, str]]:
    entries = []
    for key in GLOSSARY_FOR.get(msg_id or "", ()):
        variants = GLOSSARY.get(key)
        if not variants:
            continue
        term, definition = variants.get(lang) or variants['en']
        entries.append((term, definition))
    return entries


def build_alert_email(msg_id: Optional[str], title: str, body: str, lang: str,
                      user_id: Optional[int]) -> tuple[str, str]:
    """(plain_text, html) for one alert email. The plain part extends the
    catalogue body; the HTML part is the branded layout. Callers still guard
    with try/except — a failure must fall back to the short body."""
    code = normalize_lang(lang)
    ui = _UI.get(code, _UI['en'])
    exp = _explain(msg_id, code)
    glossary = _glossary_entries(msg_id, code)
    snap = run_status_snapshot(user_id)

    text = _render_text(ui, title, body, exp, glossary, snap, code)
    html = _render_html(ui, title, body, exp, glossary, snap, code)
    return text, html


def _render_text(ui: dict[str, str], title: str, body: str,
                 exp: Optional[dict[str, str]],
                 glossary: list[tuple[str, str]],
                 snap: Optional[dict[str, Any]], lang: str) -> str:
    lines: list[str] = [body, ""]
    if exp:
        for key in ('why', 'next', 'action'):
            lines += [f"■ {ui[key]}", exp[key], ""]
    if snap is not None:
        lines.append(f"■ {ui['status_title']}")
        if snap["count"] == 0:
            lines.append(ui['no_runs'])
        else:
            for run in snap["runs"]:
                lines.append(
                    f"• Run #{run['id']} {run['symbol']} ({run['market']}) — "
                    f"{_status_label(run['status'], lang)} — {_pnl_text(run['pnl'])}")
            lines.append(f"{ui['total']}: {_pnl_text(snap['total'])} "
                         f"({snap['count']} {ui['active_runs']})")
        lines.append("")
    if glossary:
        lines.append(f"■ {ui['glossary']}")
        for term, definition in glossary:
            lines.append(f"• {term}: {definition}")
        lines.append("")
    lines += [f"{ui['open_app']}: {DASHBOARD_URL}", "", "Sooppiy — " + SITE_URL,
              ui['footer']]
    return "\n".join(lines)


def wrap_basic_email(title: str, body: str, lang: str) -> str:
    """Branded HTML shell around an already-localized title/body — for emails
    that carry no alert msg_id (support replies, announcements, notification
    tests, admin ops alerts). Same chrome as the rich alert email, none of the
    alert-specific sections."""
    code = normalize_lang(lang)
    ui = _UI.get(code, _UI['en'])
    e = _html.escape
    body_html = e(body).replace("\n", "<br>")
    return (
        '<div style="margin:0;padding:24px 12px;background:#f1f5f9;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "'Noto Sans KR','Noto Sans JP','Noto Sans Thai',Arial,sans-serif;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;">'
        '<tr><td style="background:#0f172a;border-radius:12px 12px 0 0;'
        'padding:20px 28px;">'
        '<div style="color:#ffffff;font-size:20px;font-weight:700;'
        'letter-spacing:0.5px;">Sooppiy</div>'
        f'<div style="color:#94a3b8;font-size:12px;margin-top:2px;">{e(ui["tagline"])}</div>'
        '</td></tr>'
        '<tr><td style="background:#ffffff;padding:24px 28px;">'
        f'<h2 style="margin:0 0 10px;font-size:17px;color:#0f172a;">{e(title)}</h2>'
        f'<p style="margin:0;font-size:14px;line-height:1.6;color:#334155;">'
        f'{body_html}</p></td></tr>'
        '<tr><td style="background:#0f172a;border-radius:0 0 12px 12px;'
        'padding:18px 28px;">'
        f'<a href="{DASHBOARD_URL}" style="color:#38bdf8;font-size:13px;'
        f'font-weight:600;text-decoration:none;">{e(ui["open_app"])} →</a>'
        f'<div style="color:#64748b;font-size:11px;line-height:1.6;'
        f'margin-top:10px;">{e(ui["footer"])}</div>'
        f'<div style="color:#475569;font-size:11px;margin-top:8px;">© Sooppiy — '
        f'<a href="{SITE_URL}" style="color:#475569;">sooppiy.com</a></div>'
        '</td></tr></table></td></tr></table></div>')


_SECTION_COLORS = {'why': '#0ea5e9', 'next': '#8b5cf6', 'action': '#10b981'}


def _render_html(ui: dict[str, str], title: str, body: str,
                 exp: Optional[dict[str, str]],
                 glossary: list[tuple[str, str]],
                 snap: Optional[dict[str, Any]], lang: str) -> str:
    e = _html.escape
    parts: list[str] = []
    parts.append(
        '<div style="margin:0;padding:24px 12px;background:#f1f5f9;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "'Noto Sans KR','Noto Sans JP','Noto Sans Thai',Arial,sans-serif;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;">')
    # header
    parts.append(
        '<tr><td style="background:#0f172a;border-radius:12px 12px 0 0;'
        'padding:20px 28px;">'
        '<div style="color:#ffffff;font-size:20px;font-weight:700;'
        'letter-spacing:0.5px;">Sooppiy</div>'
        f'<div style="color:#94a3b8;font-size:12px;margin-top:2px;">{e(ui["tagline"])}</div>'
        '</td></tr>')
    # alert card
    parts.append(
        '<tr><td style="background:#ffffff;padding:24px 28px 8px;">'
        f'<h2 style="margin:0 0 10px;font-size:17px;color:#0f172a;">{e(title)}</h2>'
        f'<p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#334155;">'
        f'{e(body)}</p></td></tr>')
    # explanation sections
    if exp:
        for key in ('why', 'next', 'action'):
            color = _SECTION_COLORS[key]
            parts.append(
                '<tr><td style="background:#ffffff;padding:0 28px 14px;">'
                f'<div style="border-left:3px solid {color};padding:2px 0 2px 12px;">'
                f'<div style="font-size:12px;font-weight:700;color:{color};'
                f'text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px;">'
                f'{e(ui[key])}</div>'
                f'<div style="font-size:13px;line-height:1.6;color:#475569;">'
                f'{e(exp[key])}</div></div></td></tr>')
    # live run snapshot
    if snap is not None:
        # Two-cell table rows, not flexbox — Gmail drops justify-content and
        # the P&L column would collapse against the label.
        rows = []
        if snap["count"] == 0:
            rows.append(
                '<div style="font-size:13px;color:#64748b;">'
                f'{e(ui["no_runs"])}</div>')
        else:
            body_rows = []
            for run in snap["runs"]:
                pnl = run["pnl"]
                pnl_color = ('#64748b' if pnl is None
                             else ('#dc2626' if pnl < 0 else '#16a34a'))
                body_rows.append(
                    '<tr>'
                    '<td style="font-size:13px;line-height:1.9;color:#334155;'
                    'padding:0;">'
                    f'Run #{run["id"]} {e(str(run["symbol"]))} '
                    f'<span style="color:#94a3b8;">({e(str(run["market"]))})</span> — '
                    f'{e(_status_label(run["status"], lang))}</td>'
                    f'<td align="right" style="font-size:13px;font-weight:600;'
                    f'color:{pnl_color};padding:0;white-space:nowrap;">'
                    f'{e(_pnl_text(pnl))}</td></tr>')
            total = snap["total"]
            total_color = '#dc2626' if total < 0 else '#16a34a'
            body_rows.append(
                '<tr>'
                '<td style="font-size:13px;color:#0f172a;font-weight:700;'
                'border-top:1px solid #e2e8f0;padding:8px 0 0;">'
                f'{e(ui["total"])} ({snap["count"]} {e(ui["active_runs"])})</td>'
                f'<td align="right" style="font-size:13px;font-weight:700;'
                f'color:{total_color};border-top:1px solid #e2e8f0;'
                f'padding:8px 0 0;white-space:nowrap;">{e(_pnl_text(total))}</td>'
                '</tr>')
            rows.append(
                '<table role="presentation" width="100%" cellpadding="0" '
                'cellspacing="0">' + "".join(body_rows) + '</table>')
        parts.append(
            '<tr><td style="background:#ffffff;padding:6px 28px 18px;">'
            '<div style="background:#f8fafc;border:1px solid #e2e8f0;'
            'border-radius:10px;padding:14px 16px;">'
            '<div style="font-size:12px;font-weight:700;color:#0f172a;'
            'text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">'
            f'{e(ui["status_title"])}</div>' + "".join(rows) + '</div></td></tr>')
    # glossary
    if glossary:
        items = "".join(
            f'<div style="font-size:12px;line-height:1.6;color:#475569;'
            f'margin-bottom:6px;"><span style="font-weight:700;color:#0f172a;">'
            f'{e(term)}</span> — {e(definition)}</div>'
            for term, definition in glossary)
        parts.append(
            '<tr><td style="background:#ffffff;padding:0 28px 20px;">'
            '<div style="background:#fffbeb;border:1px solid #fde68a;'
            'border-radius:10px;padding:14px 16px;">'
            '<div style="font-size:12px;font-weight:700;color:#92400e;'
            'text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;">'
            f'{e(ui["glossary"])}</div>' + items + '</div></td></tr>')
    # footer
    parts.append(
        '<tr><td style="background:#0f172a;border-radius:0 0 12px 12px;'
        'padding:18px 28px;">'
        f'<a href="{DASHBOARD_URL}" style="color:#38bdf8;font-size:13px;'
        f'font-weight:600;text-decoration:none;">{e(ui["open_app"])} →</a>'
        f'<div style="color:#64748b;font-size:11px;line-height:1.6;'
        f'margin-top:10px;">{e(ui["footer"])}</div>'
        f'<div style="color:#475569;font-size:11px;margin-top:8px;">© Sooppiy — '
        f'<a href="{SITE_URL}" style="color:#475569;">sooppiy.com</a></div>'
        '</td></tr>')
    parts.append('</table></td></tr></table></div>')
    return "".join(parts)
