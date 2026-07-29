"""Service regions.

A region is a COUNTRY, deliberately separate from `users.lang`. English alone
serves the USA, Canada, Australia and Singapore — four countries, four time
zones, four regulators, and daylight saving that runs opposite between the
northern and southern hemispheres. Anything keyed off language would put a
Sydney member on a New York clock.

Three independent axes, three fields:
  region    what may I trade, under whose rules   users.region
  timezone  what time is it for you               users.timezone
  lang      what words do you read                users.lang

`timezone` defaults from the region but stays separately settable — members
travel, and a Korean speaker living in Singapore is region=SG, lang=ko.

UNKNOWN IS A VALID STATE. A member whose region we have not been told is
`None`, never "US". Defaulting an unplaceable member into a jurisdiction is a
regulatory failure mode, not a cosmetic one.
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class Region(NamedTuple):
    code: str          # ISO-3166 alpha-2
    timezone: str      # IANA zone — never a fixed UTC offset; DST is real
    lang: str          # the language most members here read
    names: dict        # display name per supported UI language


REGISTRY: dict[str, Region] = {
    'US': Region('US', 'America/New_York', 'en', {
        'en': 'United States', 'ko': '미국', 'ja': 'アメリカ合衆国',
        'th': 'สหรัฐอเมริกา', 'vi': 'Hoa Kỳ', 'id': 'Amerika Serikat'}),
    'CA': Region('CA', 'America/Toronto', 'en', {
        'en': 'Canada', 'ko': '캐나다', 'ja': 'カナダ',
        'th': 'แคนาดา', 'vi': 'Canada', 'id': 'Kanada'}),
    'AU': Region('AU', 'Australia/Sydney', 'en', {
        'en': 'Australia', 'ko': '호주', 'ja': 'オーストラリア',
        'th': 'ออสเตรเลีย', 'vi': 'Úc', 'id': 'Australia'}),
    'SG': Region('SG', 'Asia/Singapore', 'en', {
        'en': 'Singapore', 'ko': '싱가포르', 'ja': 'シンガポール',
        'th': 'สิงคโปร์', 'vi': 'Singapore', 'id': 'Singapura'}),
    'KR': Region('KR', 'Asia/Seoul', 'ko', {
        'en': 'South Korea', 'ko': '대한민국', 'ja': '韓国',
        'th': 'เกาหลีใต้', 'vi': 'Hàn Quốc', 'id': 'Korea Selatan'}),
    'JP': Region('JP', 'Asia/Tokyo', 'ja', {
        'en': 'Japan', 'ko': '일본', 'ja': '日本',
        'th': 'ญี่ปุ่น', 'vi': 'Nhật Bản', 'id': 'Jepang'}),
    'TH': Region('TH', 'Asia/Bangkok', 'th', {
        'en': 'Thailand', 'ko': '태국', 'ja': 'タイ',
        'th': 'ประเทศไทย', 'vi': 'Thái Lan', 'id': 'Thailand'}),
    'VN': Region('VN', 'Asia/Ho_Chi_Minh', 'vi', {
        'en': 'Vietnam', 'ko': '베트남', 'ja': 'ベトナム',
        'th': 'เวียดนาม', 'vi': 'Việt Nam', 'id': 'Vietnam'}),
    # Jakarta is UTC+7 (Asia/Jakarta = WIB) and has no DST. Indonesia spans
    # three zones; WIB covers Jakarta and Surabaya — where the IDX trades —
    # so it is the right default, and members further east can still set
    # Asia/Makassar or Asia/Jayapura themselves via normalize_timezone.
    'ID': Region('ID', 'Asia/Jakarta', 'id', {
        'en': 'Indonesia', 'ko': '인도네시아', 'ja': 'インドネシア',
        'th': 'อินโดนีเซีย', 'vi': 'Indonesia', 'id': 'Indonesia'}),
}


def supported_regions() -> tuple[str, ...]:
    return tuple(REGISTRY)


def normalize_region(code: Optional[str]) -> Optional[str]:
    """An ISO code we serve, or None. Never guesses a default."""
    if not code:
        return None
    return code.strip().upper() if code.strip().upper() in REGISTRY else None


def get_region(code: Optional[str]) -> Optional[Region]:
    return REGISTRY.get(normalize_region(code) or '')


def default_timezone(code: Optional[str]) -> Optional[str]:
    r = get_region(code)
    return r.timezone if r else None


def default_lang(code: Optional[str]) -> Optional[str]:
    r = get_region(code)
    return r.lang if r else None


def normalize_timezone(tz: Optional[str]) -> Optional[str]:
    """Accept any zone the platform's own tzdata knows, not just the eight
    defaults — a member in a region we serve may genuinely be somewhere else,
    and rejecting their real zone would show them the wrong clock."""
    if not tz or not tz.strip():
        return None
    candidate = tz.strip()
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(candidate)
    except Exception:  # noqa: BLE001 — unknown zone is a bad input, not a crash
        return None
    return candidate


def options(lang: str = 'en') -> list[dict]:
    """Picker payload for the first-run prompt and the settings page."""
    from analysis_agents import normalize_lang
    code = normalize_lang(lang)
    return [{'region': r.code,
             'name': r.names.get(code) or r.names['en'],
             'timezone': r.timezone,
             'suggested_lang': r.lang}
            for r in REGISTRY.values()]
