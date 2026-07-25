"""Localized transactional email copy (verification / password-reset code).

en + ko are verified. ja/th/vi intentionally fall through to en until a native
speaker fills them — a wrong-language email is worse than an English one.
"""
from __future__ import annotations

from analysis_agents import normalize_lang

# {lang: (subject, html_template)}; html_template has a single {code} slot.
_VERIFICATION = {
    "en": ("Your Sooppiy verification code",
           "<p>Your verification code is: <strong>{code}</strong></p>"
           "<p>It expires in 5 minutes. Do not share it.</p>"),
    "ko": ("Sooppiy 인증 코드",
           "<p>인증 코드: <strong>{code}</strong></p>"
           "<p>5분 후 만료됩니다. 코드를 공유하지 마세요.</p>"),
    # ja/th/vi: add verified translations here; absent -> English via .get below.
}


def verification_email(code: str, lang: str) -> tuple[str, str]:
    subject, template = _VERIFICATION.get(normalize_lang(lang), _VERIFICATION["en"])
    return subject, template.format(code=code)
