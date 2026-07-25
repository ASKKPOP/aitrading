"""Localized system-alert copy. Producers pass a msg_id + params; send_alert /
notify render (title, body) in the recipient's language at send time.

en is authoritative and complete. ko is verified. ja/th/vi are added
incrementally; any missing (lang, msg_id) or any param mismatch renders in
English — a monolingual-but-correct alert beats a broken localized one.

Only SYSTEM-templated alerts live here. Staff free text (announcements, support
replies) and operator alerts are never routed through this module.
"""
from __future__ import annotations

import logging

from analysis_agents import normalize_lang

logger = logging.getLogger(__name__)

# msg_id -> {lang -> (title_template, body_template)}
MESSAGES: dict[str, dict[str, tuple[str, str]]] = {
    "trade_executed": {
        "en": ("Trade executed", "{side} {qty} {symbol} @ {price}"),
        "ko": ("체결 완료", "{symbol} {side} {qty} @ {price}"),
    },
    "position_closed": {
        "en": ("Position closed", "{symbol} P&L {pnl}"),
        "ko": ("포지션 종료", "{symbol} 손익 {pnl}"),
    },
    "breaker": {
        "en": ("Circuit breaker HALT ({scope})", "{reason}"),
        "ko": ("서킷 브레이커 정지 ({scope})", "{reason}"),
    },
    "verify_rejected": {
        "en": ("Pre-trade check rejected", "{reason}"),
        "ko": ("사전 점검 거부됨", "{reason}"),
    },
    "run_report": {
        "en": ("Run #{run_id} P&L digest", "{summary}"),
        "ko": ("런 #{run_id} 손익 요약", "{summary}"),
    },
    "run_threshold": {
        "en": ("Run #{run_id} threshold hit", "{detail}"),
        "ko": ("런 #{run_id} 임계값 도달", "{detail}"),
    },
    "run_stopped": {
        "en": ("Run #{run_id} stopped", "{reason}"),
        "ko": ("런 #{run_id} 중지됨", "{reason}"),
    },
    "gateway_down": {
        "en": ("Broker gateway down", "{detail}"),
        "ko": ("브로커 게이트웨이 중단", "{detail}"),
    },
    "order_drift": {
        "en": ("Order drift detected", "{detail}"),
        "ko": ("주문 불일치 감지", "{detail}"),
    },
    "fleet_drawdown_warning": {
        "en": ("Fleet drawdown warning", "{detail}"),
        "ko": ("플릿 손실 경고", "{detail}"),
    },
    "fleet_breaker": {
        "en": ("Fleet circuit breaker", "{detail}"),
        "ko": ("플릿 서킷 브레이커", "{detail}"),
    },
    "fleet_churn": {
        "en": ("Fleet churn notice", "{detail}"),
        "ko": ("플릿 회전 알림", "{detail}"),
    },
    "fleet_watchdog": {
        "en": ("Fleet watchdog", "{detail}"),
        "ko": ("플릿 워치독", "{detail}"),
    },
    "fleet_slot_dormant": {
        "en": ("Fleet slot dormant", "{detail}"),
        "ko": ("플릿 슬롯 휴면", "{detail}"),
    },
    "watch": {
        "en": ("Watch: {name}", "{detail}"),
        "ko": ("감시: {name}", "{detail}"),
    },
}


def _fmt(template: str, params: dict) -> str:
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        raise  # caller decides fallback


def render(msg_id: str, lang: str, **params) -> tuple[str, str]:
    """(title, body) for msg_id in lang. Falls back to English on any miss."""
    variants = MESSAGES.get(msg_id)
    if not variants:
        # Unknown id: no catalogue entry. Return the id + a compact param dump so
        # nothing is silently dropped, but this should never happen in prod.
        logger.warning("notifications_i18n: unknown msg_id %r", msg_id)
        return msg_id, ", ".join(f"{k}={v}" for k, v in params.items())
    en_title, en_body = variants["en"]
    code = normalize_lang(lang)
    title_t, body_t = variants.get(code, variants["en"])
    try:
        return _fmt(title_t, params), _fmt(body_t, params)
    except (KeyError, IndexError, ValueError):
        try:
            return _fmt(en_title, params), _fmt(en_body, params)
        except (KeyError, IndexError, ValueError):
            logger.warning("notifications_i18n: param mismatch for %s", msg_id)
            return en_title, en_body
