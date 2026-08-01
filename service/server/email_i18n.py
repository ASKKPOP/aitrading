"""Localized transactional email copy (signup verification / password reset),
6 languages, branded HTML.

English is authoritative; ko/ja/th/vi/id are machine-generated pending native
review. Unknown language falls back to English via normalize_lang + .get.

2026-07-31: both flows used one bare '<p>code</p>' template, so a password
reset arrived titled 'verification code' with no branding at all. Each purpose
now has its own subject/heading/copy inside the same Sooppiy shell the alert
emails use (header bar, card, footer).
"""
from __future__ import annotations

import html as _html

from analysis_agents import normalize_lang

SITE_URL = "https://sooppiy.com"

# lang -> shared chrome strings
_CHROME = {
    'en': {'tagline': 'AI trading, watched for you',
           'footer': 'You received this email because this address was used on '
                     'Sooppiy. If this was not you, no action is needed.'},
    'ko': {'tagline': 'AI 트레이딩을 대신 지켜봐 드립니다',
           'footer': '이 주소가 Sooppiy에서 사용되어 발송된 메일입니다. 본인이 '
                     '아니라면 아무 조치도 필요하지 않습니다.'},
    'ja': {'tagline': 'AIトレーディングをあなたの代わりに見守ります',
           'footer': 'このメールは、このアドレスがSooppiyで使用されたため送信'
                     'されました。心当たりがない場合、操作は不要です。'},
    'th': {'tagline': 'ให้เราเฝ้าดูการเทรดด้วย AI แทนคุณ',
           'footer': 'คุณได้รับอีเมลนี้เนื่องจากมีการใช้ที่อยู่นี้บน Sooppiy '
                     'หากไม่ใช่คุณ ไม่จำเป็นต้องดำเนินการใด ๆ'},
    'vi': {'tagline': 'Chúng tôi theo dõi giao dịch AI thay cho bạn',
           'footer': 'Bạn nhận được email này vì địa chỉ này đã được dùng trên '
                     'Sooppiy. Nếu không phải bạn, không cần làm gì cả.'},
    'id': {'tagline': 'Kami memantau trading AI untuk Anda',
           'footer': 'Anda menerima email ini karena alamat ini digunakan di '
                     'Sooppiy. Jika bukan Anda, tidak perlu tindakan apa pun.'},
}

# purpose -> lang -> {'subject', 'heading', 'intro', 'note'}
_COPY = {
    'signup': {
        'en': {'subject': 'Welcome to Sooppiy — confirm your email',
               'heading': 'Confirm your email',
               'intro': 'Use this code to finish creating your Sooppiy account:',
               'note': ('The code expires in 5 minutes and can be used once. '
                        'Never share it with anyone — Sooppiy staff will never '
                        'ask for it.')},
        'ko': {'subject': 'Sooppiy에 오신 것을 환영합니다 — 이메일을 인증해 주세요',
               'heading': '이메일 인증',
               'intro': '아래 코드를 입력해 Sooppiy 계정 생성을 완료하세요:',
               'note': ('이 코드는 5분 후 만료되며 1회만 사용할 수 있습니다. 코드를 '
                        '타인과 공유하지 마세요 — Sooppiy는 절대 코드를 묻지 '
                        '않습니다.')},
        'ja': {'subject': 'Sooppiyへようこそ — メールアドレスをご確認ください',
               'heading': 'メールアドレスの確認',
               'intro': '次のコードを入力して、Sooppiyアカウントの作成を完了してください：',
               'note': ('このコードの有効期限は5分間で、1回のみ使用できます。コードは'
                        '誰にも共有しないでください — Sooppiyがコードをお尋ねする'
                        'ことはありません。')},
        'th': {'subject': 'ยินดีต้อนรับสู่ Sooppiy — ยืนยันอีเมลของคุณ',
               'heading': 'ยืนยันอีเมลของคุณ',
               'intro': 'ใช้รหัสนี้เพื่อสร้างบัญชี Sooppiy ของคุณให้เสร็จสมบูรณ์:',
               'note': ('รหัสนี้จะหมดอายุใน 5 นาทีและใช้ได้ครั้งเดียว อย่าเปิดเผยรหัสให้ใคร '
                        '— เจ้าหน้าที่ Sooppiy จะไม่ขอรหัสนี้จากคุณ')},
        'vi': {'subject': 'Chào mừng đến với Sooppiy — xác nhận email của bạn',
               'heading': 'Xác nhận email của bạn',
               'intro': 'Dùng mã này để hoàn tất việc tạo tài khoản Sooppiy:',
               'note': ('Mã hết hạn sau 5 phút và chỉ dùng được một lần. Không chia '
                        'sẻ mã với bất kỳ ai — nhân viên Sooppiy không bao giờ hỏi '
                        'mã này.')},
        'id': {'subject': 'Selamat datang di Sooppiy — konfirmasi email Anda',
               'heading': 'Konfirmasi email Anda',
               'intro': 'Gunakan kode ini untuk menyelesaikan pembuatan akun '
                        'Sooppiy Anda:',
               'note': ('Kode kedaluwarsa dalam 5 menit dan hanya bisa dipakai '
                        'sekali. Jangan bagikan kepada siapa pun — staf Sooppiy '
                        'tidak akan pernah memintanya.')},
    },
    'reset': {
        'en': {'subject': 'Reset your Sooppiy password',
               'heading': 'Password reset',
               'intro': 'Use this code to set a new password for your Sooppiy '
                        'account:',
               'note': ('The code expires in 5 minutes and can be used once. Your '
                        'password stays unchanged until you enter it. If you did '
                        'not request a reset, you can safely ignore this email — '
                        'and never share the code with anyone.')},
        'ko': {'subject': 'Sooppiy 비밀번호 재설정',
               'heading': '비밀번호 재설정',
               'intro': '아래 코드를 입력해 Sooppiy 계정의 새 비밀번호를 설정하세요:',
               'note': ('이 코드는 5분 후 만료되며 1회만 사용할 수 있습니다. 코드를 '
                        '입력하기 전까지 비밀번호는 변경되지 않습니다. 재설정을 요청한 '
                        '적이 없다면 이 메일은 무시하셔도 됩니다 — 코드는 절대 타인과 '
                        '공유하지 마세요.')},
        'ja': {'subject': 'Sooppiyパスワードの再設定',
               'heading': 'パスワードの再設定',
               'intro': '次のコードを入力して、Sooppiyアカウントの新しいパスワードを設定してください：',
               'note': ('このコードの有効期限は5分間で、1回のみ使用できます。コードを'
                        '入力するまでパスワードは変更されません。再設定を依頼して'
                        'いない場合、このメールは無視して構いません — コードは誰にも'
                        '共有しないでください。')},
        'th': {'subject': 'รีเซ็ตรหัสผ่าน Sooppiy ของคุณ',
               'heading': 'รีเซ็ตรหัสผ่าน',
               'intro': 'ใช้รหัสนี้เพื่อตั้งรหัสผ่านใหม่สำหรับบัญชี Sooppiy ของคุณ:',
               'note': ('รหัสนี้จะหมดอายุใน 5 นาทีและใช้ได้ครั้งเดียว รหัสผ่านของคุณจะไม่เปลี่ยน'
                        'จนกว่าคุณจะกรอกรหัส หากคุณไม่ได้ขอรีเซ็ต สามารถเพิกเฉยต่ออีเมลนี้ได้ '
                        '— และอย่าเปิดเผยรหัสให้ใคร')},
        'vi': {'subject': 'Đặt lại mật khẩu Sooppiy của bạn',
               'heading': 'Đặt lại mật khẩu',
               'intro': 'Dùng mã này để đặt mật khẩu mới cho tài khoản Sooppiy:',
               'note': ('Mã hết hạn sau 5 phút và chỉ dùng được một lần. Mật khẩu '
                        'của bạn không đổi cho đến khi bạn nhập mã. Nếu bạn không '
                        'yêu cầu đặt lại, hãy bỏ qua email này — và không chia sẻ '
                        'mã với bất kỳ ai.')},
        'id': {'subject': 'Atur ulang kata sandi Sooppiy Anda',
               'heading': 'Atur ulang kata sandi',
               'intro': 'Gunakan kode ini untuk membuat kata sandi baru bagi akun '
                        'Sooppiy Anda:',
               'note': ('Kode kedaluwarsa dalam 5 menit dan hanya bisa dipakai '
                        'sekali. Kata sandi Anda tidak berubah sampai Anda '
                        'memasukkannya. Jika Anda tidak meminta pengaturan ulang, '
                        'abaikan email ini — dan jangan bagikan kode kepada siapa '
                        'pun.')},
    },
    # Admin-created account. The member never chose a password, so the copy
    # cannot say "reset" — and the code lives 7 days, not 5 minutes, because
    # this is handed over out of band rather than requested on the spot.
    'invite': {
        'en': {'subject': 'Your Sooppiy account is ready — set your password',
               'heading': 'Set your password',
               'intro': 'An administrator created a Sooppiy account for this '
                        'address. Use this code to set your password:',
               'note': ('The code expires in 7 days and can be used once. You '
                        'cannot sign in until you set a password. Never share the '
                        'code with anyone — Sooppiy staff will never ask for it.')},
        'ko': {'subject': 'Sooppiy 계정이 준비되었습니다 — 비밀번호를 설정하세요',
               'heading': '비밀번호 설정',
               'intro': '관리자가 이 주소로 Sooppiy 계정을 생성했습니다. 아래 코드를 '
                        '입력해 비밀번호를 설정하세요:',
               'note': ('이 코드는 7일 후 만료되며 1회만 사용할 수 있습니다. 비밀번호를 '
                        '설정하기 전까지는 로그인할 수 없습니다. 코드는 절대 타인과 '
                        '공유하지 마세요 — Sooppiy는 절대 코드를 묻지 않습니다.')},
        'ja': {'subject': 'Sooppiyアカウントの準備ができました — パスワードを設定してください',
               'heading': 'パスワードの設定',
               'intro': '管理者がこのアドレスでSooppiyアカウントを作成しました。次の'
                        'コードを入力してパスワードを設定してください：',
               'note': ('このコードの有効期限は7日間で、1回のみ使用できます。パスワードを'
                        '設定するまでログインできません。コードは誰にも共有しないで'
                        'ください — Sooppiyがコードをお尋ねすることはありません。')},
        'th': {'subject': 'บัญชี Sooppiy ของคุณพร้อมแล้ว — ตั้งรหัสผ่านของคุณ',
               'heading': 'ตั้งรหัสผ่านของคุณ',
               'intro': 'ผู้ดูแลระบบได้สร้างบัญชี Sooppiy สำหรับที่อยู่นี้ '
                        'ใช้รหัสนี้เพื่อตั้งรหัสผ่านของคุณ:',
               'note': ('รหัสนี้จะหมดอายุใน 7 วันและใช้ได้ครั้งเดียว '
                        'คุณจะเข้าสู่ระบบไม่ได้จนกว่าจะตั้งรหัสผ่าน อย่าเปิดเผยรหัสให้ใคร '
                        '— เจ้าหน้าที่ Sooppiy จะไม่ขอรหัสนี้จากคุณ')},
        'vi': {'subject': 'Tài khoản Sooppiy của bạn đã sẵn sàng — hãy đặt mật khẩu',
               'heading': 'Đặt mật khẩu của bạn',
               'intro': 'Quản trị viên đã tạo một tài khoản Sooppiy cho địa chỉ '
                        'này. Dùng mã này để đặt mật khẩu:',
               'note': ('Mã hết hạn sau 7 ngày và chỉ dùng được một lần. Bạn không '
                        'thể đăng nhập cho đến khi đặt mật khẩu. Không chia sẻ mã '
                        'với bất kỳ ai — nhân viên Sooppiy không bao giờ hỏi mã này.')},
        'id': {'subject': 'Akun Sooppiy Anda sudah siap — atur kata sandi Anda',
               'heading': 'Atur kata sandi Anda',
               'intro': 'Seorang admin membuat akun Sooppiy untuk alamat ini. '
                        'Gunakan kode ini untuk mengatur kata sandi Anda:',
               'note': ('Kode kedaluwarsa dalam 7 hari dan hanya bisa dipakai '
                        'sekali. Anda tidak bisa masuk sampai kata sandi diatur. '
                        'Jangan bagikan kepada siapa pun — staf Sooppiy tidak akan '
                        'pernah memintanya.')},
    },
}


def verification_email(code: str, lang: str, purpose: str = 'signup') -> tuple[str, str]:
    """(subject, html) for the signup-confirmation or password-reset code email."""
    lc = normalize_lang(lang)
    copy = _COPY.get(purpose, _COPY['signup'])
    copy = copy.get(lc, copy['en'])
    chrome = _CHROME.get(lc, _CHROME['en'])
    e = _html.escape
    html = (
        '<div style="margin:0;padding:24px 12px;background:#f1f5f9;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "'Noto Sans KR','Noto Sans JP','Noto Sans Thai',Arial,sans-serif;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;width:100%;">'
        # header
        '<tr><td style="background:#0f172a;border-radius:12px 12px 0 0;'
        'padding:20px 28px;">'
        '<div style="color:#ffffff;font-size:20px;font-weight:700;'
        'letter-spacing:0.5px;">Sooppiy</div>'
        f'<div style="color:#94a3b8;font-size:12px;margin-top:2px;">{e(chrome["tagline"])}</div>'
        '</td></tr>'
        # card
        '<tr><td style="background:#ffffff;padding:28px;">'
        f'<h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;">{e(copy["heading"])}</h2>'
        f'<p style="margin:0 0 18px;font-size:14px;line-height:1.6;color:#334155;">'
        f'{e(copy["intro"])}</p>'
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
        'padding:16px;text-align:center;margin-bottom:18px;">'
        '<span style="font-family:SFMono-Regular,Menlo,Consolas,monospace;'
        'font-size:30px;font-weight:700;letter-spacing:8px;color:#0f172a;">'
        f'{e(code)}</span></div>'
        f'<p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">'
        f'{e(copy["note"])}</p>'
        '</td></tr>'
        # footer
        '<tr><td style="background:#0f172a;border-radius:0 0 12px 12px;'
        'padding:16px 28px;">'
        f'<div style="color:#64748b;font-size:11px;line-height:1.6;">{e(chrome["footer"])}</div>'
        f'<div style="color:#475569;font-size:11px;margin-top:8px;">© Sooppiy — '
        f'<a href="{SITE_URL}" style="color:#475569;">sooppiy.com</a></div>'
        '</td></tr>'
        '</table></td></tr></table></div>')
    return copy['subject'], html
