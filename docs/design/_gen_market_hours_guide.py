"""Generate the member guide "When your markets are open" in all 6 languages.

Run from the repo root:
    .venv/bin/python docs/design/_gen_market_hours_guide.py

Writes docs/design/market-hours-{en,ko,ja,th,vi,id}.html, which
build_guide_content.py then copies into service/server/guide_content/.

Why generated rather than five hand-written files: every number in this guide
comes from markets.is_session_open(), and the five language versions must
agree to the minute. Hand-maintaining them would guarantee drift the first
time a session calendar changes. The session windows below are COMPUTED here,
not typed in.

Each language shows only the regions that speak it — a Korean reader does not
need Sydney's clock, and a guide that lists all eight everywhere buries the
one row that matters.
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

# language → the regions whose members read it
BY_LANG = {
    "en": [("United States", "America/New_York"), ("Canada", "America/Toronto"),
           ("Australia", "Australia/Sydney"), ("Singapore", "Asia/Singapore")],
    "ko": [("대한민국", "Asia/Seoul")],
    "ja": [("日本", "Asia/Tokyo")],
    "th": [("ประเทศไทย", "Asia/Bangkok")],
    "vi": [("Việt Nam", "Asia/Ho_Chi_Minh")],
    "id": [("Indonesia", "Asia/Jakarta")],
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
        "en": "Exchanges open on their own clock, not yours. This page shows every market's hours in <b>your</b> local time, so you know when your automation can actually trade.",
        "ko": "거래소는 자기 시간에 맞춰 열립니다. 이 페이지는 각 시장이 <b>내 현지 시각</b>으로 몇 시에 열리는지 보여줍니다. 자동매매가 실제로 거래할 수 있는 시간대를 알 수 있습니다.",
        "ja": "取引所は自分の時間で開きます。このページでは各市場の時間を<b>あなたの現地時刻</b>で示します。自動売買が実際に取引できる時間がわかります。",
        "th": "ตลาดหลักทรัพย์เปิดตามเวลาของตัวเอง ไม่ใช่ของคุณ หน้านี้แสดงเวลาทำการของแต่ละตลาดตาม<b>เวลาท้องถิ่นของคุณ</b> เพื่อให้รู้ว่าระบบอัตโนมัติเทรดได้จริงตอนไหน",
        "vi": "Các sàn mở cửa theo giờ của họ, không phải giờ của bạn. Trang này hiển thị giờ giao dịch của từng thị trường theo <b>giờ địa phương của bạn</b>, để bạn biết khi nào hệ thống tự động thực sự có thể giao dịch.",
        "id": "Bursa buka menurut jamnya sendiri, bukan jam Anda. Halaman ini menampilkan jam buka setiap pasar dalam <b>waktu lokal Anda</b>, sehingga Anda tahu kapan otomatisasi Anda benar-benar bisa bertransaksi."},
    "always_h": {
        "en": "Always open", "ko": "항상 열려 있는 시장", "ja": "常に開いている市場",
        "th": "เปิดตลอดเวลา", "vi": "Luôn mở cửa",
        "id": "Selalu buka"},
    "always_p": {
        "en": "These never close during the week, so they are available whenever you are — whatever your region.",
        "ko": "이 시장들은 주중에 닫히지 않습니다. 지역과 관계없이 언제든 거래할 수 있습니다.",
        "ja": "これらは平日は閉じません。地域を問わず、いつでも取引できます。",
        "th": "ตลาดเหล่านี้ไม่ปิดในวันธรรมดา จึงเทรดได้ทุกเมื่อไม่ว่าคุณอยู่ภูมิภาคใด",
        "vi": "Những thị trường này không đóng cửa trong tuần, nên luôn sẵn sàng dù bạn ở khu vực nào.",
        "id": "Pasar ini tidak pernah tutup pada hari kerja, jadi tersedia kapan pun Anda siap — di wilayah mana pun Anda berada."},
    "sched_h": {
        "en": "Markets with fixed hours — in your time",
        "ko": "정해진 시간에만 열리는 시장 — 내 시각 기준",
        "ja": "決まった時間に開く市場 — あなたの時刻で",
        "th": "ตลาดที่มีเวลาทำการแน่นอน — ตามเวลาของคุณ",
        "vi": "Thị trường có giờ cố định — theo giờ của bạn",
        "id": "Pasar dengan jam tetap — dalam waktu Anda"},
    "region_h": {
        "en": "Region", "ko": "지역", "ja": "地域", "th": "ภูมิภาค", "vi": "Khu vực",
        "id": "Wilayah"},
    "market_h": {
        "en": "Market", "ko": "시장", "ja": "市場", "th": "ตลาด", "vi": "Thị trường",
        "id": "Pasar"},
    "hours_h": {
        "en": "Your local hours", "ko": "내 현지 시각", "ja": "現地時刻",
        "th": "เวลาท้องถิ่นของคุณ", "vi": "Giờ địa phương của bạn",
        "id": "Jam lokal Anda"},
    "awake_h": {
        "en": "While you're awake", "ko": "깨어 있는 동안", "ja": "起きている時間帯",
        "th": "ช่วงที่คุณตื่น", "vi": "Khi bạn thức",
        "id": "Saat Anda terjaga"},
    "nextday": {
        "en": "next day", "ko": "다음 날", "ja": "翌日", "th": "วันถัดไป", "vi": "hôm sau",
        "id": "hari berikutnya"},
    "note_h": {
        "en": "What this means for you",
        "ko": "이것이 의미하는 것",
        "ja": "これが意味すること",
        "th": "สิ่งนี้หมายความว่าอย่างไรกับคุณ",
        "vi": "Điều này có ý nghĩa gì với bạn",
        "id": "Apa artinya ini bagi Anda"},
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
    "dst": {
        "en": "US, Canadian and Australian hours shift by an hour when daylight saving starts or ends — and Australia's runs opposite to the northern hemisphere. The site always shows the current, correct time.",
        "ko": "미국·캐나다·호주는 서머타임 시작과 종료에 따라 한 시간씩 이동합니다. 호주는 북반구와 반대로 적용됩니다. 사이트는 항상 현재 기준의 정확한 시각을 표시합니다.",
        "ja": "米国・カナダ・オーストラリアの時間は夏時間の開始と終了で1時間ずれます。オーストラリアは北半球と逆です。サイトでは常に現在の正しい時刻を表示します。",
        "th": "เวลาของสหรัฐฯ แคนาดา และออสเตรเลียจะเลื่อนหนึ่งชั่วโมงเมื่อเริ่มหรือสิ้นสุดเวลาออมแสง และของออสเตรเลียสวนทางกับซีกโลกเหนือ เว็บไซต์แสดงเวลาที่ถูกต้องตามปัจจุบันเสมอ",
        "vi": "Giờ của Mỹ, Canada và Úc dịch một tiếng khi bắt đầu hoặc kết thúc giờ mùa hè — và của Úc ngược với bắc bán cầu. Trang luôn hiển thị thời gian đúng ở hiện tại.",
        "id": "Jam Amerika Serikat, Kanada, dan Australia bergeser satu jam saat waktu musim panas dimulai atau berakhir — dan Australia berlawanan dengan belahan bumi utara. Situs ini selalu menampilkan waktu yang benar saat itu."},
    "hrs": {"en": "{h}h", "ko": "{h}시간", "ja": "{h}時間", "th": "{h} ชม.", "vi": "{h} giờ",
        "id": "{h} jam"},
}

MARKET_NAME = {
    "crypto": {"en": "Crypto", "ko": "가상자산", "ja": "暗号資産", "th": "คริปโต", "vi": "Tiền mã hoá",
        "id": "Kripto"},
    "forex": {"en": "Forex", "ko": "외환", "ja": "外国為替", "th": "ฟอเร็กซ์", "vi": "Ngoại hối",
        "id": "Forex"},
    "futures": {"en": "Futures", "ko": "선물", "ja": "先物", "th": "ฟิวเจอร์ส", "vi": "Hợp đồng tương lai",
        "id": "Futures"},
    "us-stock": {"en": "US stocks", "ko": "미국 주식", "ja": "米国株", "th": "หุ้นสหรัฐฯ", "vi": "Cổ phiếu Mỹ",
        "id": "Saham AS"},
    "a-stock": {"en": "China A-shares", "ko": "중국 A주", "ja": "中国A株", "th": "หุ้น A จีน", "vi": "Cổ phiếu A Trung Quốc",
        "id": "Saham A Tiongkok"},
}
ALWAYS = ["crypto", "forex", "futures"]
SCHEDULED = ["us-stock", "a-stock"]


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
main{max-width:820px;margin:0 auto;padding:38px 22px 80px}
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
.rg{font-size:15px;font-weight:700;color:var(--ink);margin:20px 0 2px}
.tz{font-size:11.5px;color:var(--muted);margin-bottom:6px}
.bar{display:inline-block;height:8px;border-radius:4px;vertical-align:1px;margin-right:7px}
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


def build(lang: str) -> str:
    t = lambda k: T[k][lang]  # noqa: E731
    rows = []
    for region_name, tz in BY_LANG[lang]:
        rows.append(f'<div class="rg">{region_name}</div>'
                    f'<div class="tz">{tz}</div>')
        rows.append('<div class="sw"><table><tr>'
                    f'<th>{t("market_h")}</th><th>{t("hours_h")}</th>'
                    f'<th>{t("awake_h")}</th></tr>')
        for mk in SCHEDULED:
            bands = _bands(mk, tz)
            awake = _awake_hours(mk, tz)
            # bar length relative to a full NYSE session (6.5h)
            pct = max(4, min(100, round(awake / 6.5 * 100)))
            color = "var(--go)" if awake >= 4 else (
                "var(--warn)" if awake >= 2 else "var(--ai)")
            rows.append(
                f'<tr><td class="m">{MARKET_NAME[mk][lang]}</td>'
                f'<td class="h">{_window_text(bands, lang)}</td>'
                f'<td class="h"><span class="bar" style="width:{pct}px;'
                f'background:{color}"></span>'
                f'{t("hrs").format(h=awake)}</td></tr>')
        rows.append("</table></div>")

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

<h2>{t('always_h')}</h2>
<p>{t('always_p')}</p>
<div class="fig"><div class="always">{always}</div></div>

<h2>{t('sched_h')}</h2>
{''.join(rows)}

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
    for lang in BY_LANG:
        path = OUT / f"market-hours-{lang}.html"
        path.write_text(build(lang), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
