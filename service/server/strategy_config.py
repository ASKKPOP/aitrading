"""Strategy parameters for the confluence engine / regime filter / risk stack.

One env-first surface for every threshold introduced by the parameter-upgrade
plan (docs/plan/04-ai-model-parameter-upgrade.md), instead of scattering
literals. Every value here is an UNVALIDATED PLACEHOLDER until the Phase-4
walk-forward backtest confirms or rejects it — see the plan's §4 tunables list.

Read at call time (os.getenv) so tests and ops can flip without restarts,
mirroring the existing feature-gate convention.
"""

from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── Confluence engine (Phase 1) ─────────────────────────────────────────────

def volume_confirm_min() -> float:
    """B3/S3 volume confirmation: volume_ratio must be at least this.
    Research: 'no volume = no trade' (no number given — tunable placeholder)."""
    return _env_float("VOLUME_CONFIRM_MIN", 1.5)


def event_confluence_hours() -> int:
    """B6: no FOMC/CPI/NFP/election within this many hours."""
    return _env_int("EVENT_CONFLUENCE_HOURS", 24)


def confluence_min() -> int:
    """Buys (and short-opens, when they exist) need at least this many of 6."""
    return _env_int("CONFLUENCE_MIN", 4)


def confluence_gate_enabled() -> bool:
    """Phase-4 flip: when on, automation buys are gated by confluence count.
    Default OFF until the walk-forward backtest passes (plan §4 Phase 4)."""
    return _env_bool("CONFLUENCE_GATE_ENABLED", False)


# ── Fear & Greed bands (Phase 1 B5/S4 + Phase 2 regime) ─────────────────────
# Crypto F&G (alternative.me). The research's VIX bands (20/30) could not be
# used (no VIX for crypto) — these are the plan's crypto-adapted placeholders.

def fng_fear_max() -> int:
    """B5: F&G below this = fear territory (buy leg needs delta_3d > 0 too)."""
    return _env_int("FNG_FEAR_MAX", 30)


def fng_panic_max() -> int:
    """Regime: F&G below this = panic (no new buys)."""
    return _env_int("FNG_PANIC_MAX", 20)


def fng_euphoria_min() -> int:
    """S4/regime: F&G at/above this = euphoria extreme."""
    return _env_int("FNG_EUPHORIA_MIN", 80)


def fng_euphoria_ls_min() -> int:
    """S4 secondary leg: F&G at/above this AND L/S crowded also = euphoria."""
    return _env_int("FNG_EUPHORIA_LS_MIN", 75)


def ls_euphoria_min() -> float:
    """S4 secondary leg: long/short account ratio at/above this = crowded."""
    return _env_float("LS_EUPHORIA_MIN", 2.0)


def shock_clear_hours() -> int:
    """B5 shock leg: a shock flagged within this window that has since cleared
    counts as 'fear spike fading'. S5 uses unresolved (still-flagged) shocks."""
    return _env_int("SHOCK_CLEAR_HOURS", 72)


# ── Regime filter (Phase 2) ─────────────────────────────────────────────────

def regime_filter_enabled() -> bool:
    """Phase-4 flip: when on, the regime filter gates automation entries and
    the panic auto-trip may arm the per-market breaker. Default OFF —
    Phase 2 ships advisory-only (display + journal)."""
    return _env_bool("REGIME_FILTER_ENABLED", False)


def vol_caution_percentile() -> float:
    """Realized-vol percentile (vs trailing year) at/above which = caution."""
    return _env_float("VOL_CAUTION_PERCENTILE", 70.0)


def vol_panic_percentile() -> float:
    """Realized-vol percentile at/above which = panic (no new buys)."""
    return _env_float("VOL_PANIC_PERCENTILE", 90.0)


def caution_size_multiplier() -> float:
    """Entry size multiplier in the caution regime."""
    return _env_float("CAUTION_SIZE_MULTIPLIER", 0.5)


def panic_breaker_minutes() -> int:
    """Auto-tripped per-market breaker expiry. Auto-resume clears ONLY rows
    tripped_by='auto' — a manual admin HALT is never auto-cleared."""
    return _env_int("PANIC_BREAKER_MINUTES", 60)


# ── Risk & exits (Phase 3) ──────────────────────────────────────────────────

def vol_sizing_enabled() -> bool:
    """Phase-4 flip: volatility-based position sizing in the risk gate.
    Default OFF. Requires sigma_daily (20d DAILY σ) — missing σ rejects buys."""
    return _env_bool("VOL_SIZING_ENABLED", False)


def risk_budget_pct() -> float:
    """Per-position daily risk budget as % of equity: target notional =
    equity × budget ÷ σ_daily. Worked example: $100k equity, budget 0.5%,
    σ_daily 2.45% → target ≈ $20.4k (the v1 hourly-σ bug produced $100k)."""
    return _env_float("RISK_BUDGET_PCT", 0.5)


def time_stop_cooldown_hours() -> int:
    """After a time-stop exit, block automated re-entry into the same
    (agent, market, symbol) for this long — prevents a perpetual
    close→re-enter fee bleed (0.2% round trip per cycle)."""
    return _env_int("TIME_STOP_COOLDOWN_HOURS", 48)
