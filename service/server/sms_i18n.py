"""SMS message bodies — 6 languages, keyed off users.lang.

Kept deliberately short: SMS segments cost money and Twilio truncates at
1600 chars. Every body carries the brand, the code, the 5-minute note and
the never-share line the email templates use."""
from __future__ import annotations

from analysis_agents import normalize_lang

_VERIFY = {
    'en': 'Sooppiy verification code: {code}. Expires in 5 minutes. Never share this code.',
    'ko': 'Sooppiy 인증 코드: {code}. 5분 후 만료됩니다. 코드를 절대 공유하지 마세요.',
    'ja': 'Sooppiy認証コード：{code}。有効期限は5分です。コードは誰にも共有しないでください。',
    'th': 'รหัสยืนยัน Sooppiy: {code} หมดอายุใน 5 นาที อย่าเปิดเผยรหัสนี้ให้ใคร',
    'vi': 'Mã xác minh Sooppiy: {code}. Hết hạn sau 5 phút. Không chia sẻ mã này.',
    'id': 'Kode verifikasi Sooppiy: {code}. Kedaluwarsa dalam 5 menit. Jangan bagikan kode ini.',
}

_RESET = {
    'en': 'Sooppiy password reset code: {code}. Expires in 5 minutes. If you did not request this, ignore it. Never share this code.',
    'ko': 'Sooppiy 비밀번호 재설정 코드: {code}. 5분 후 만료됩니다. 요청하지 않았다면 무시하세요. 코드를 절대 공유하지 마세요.',
    'ja': 'Sooppiyパスワード再設定コード：{code}。有効期限は5分です。依頼していない場合は無視してください。コードは共有しないでください。',
    'th': 'รหัสรีเซ็ตรหัสผ่าน Sooppiy: {code} หมดอายุใน 5 นาที หากไม่ได้ขอ ให้เพิกเฉย อย่าเปิดเผยรหัสนี้',
    'vi': 'Mã đặt lại mật khẩu Sooppiy: {code}. Hết hạn sau 5 phút. Nếu không phải bạn yêu cầu, hãy bỏ qua. Không chia sẻ mã này.',
    'id': 'Kode atur ulang kata sandi Sooppiy: {code}. Kedaluwarsa dalam 5 menit. Abaikan jika Anda tidak memintanya. Jangan bagikan kode ini.',
}


def verification_sms(code: str, lang: str) -> str:
    return _VERIFY.get(normalize_lang(lang), _VERIFY['en']).format(code=code)


def reset_sms(code: str, lang: str) -> str:
    return _RESET.get(normalize_lang(lang), _RESET['en']).format(code=code)
