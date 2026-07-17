"""AI data verification (Plan 06 D5).

D4 made the AI aggregate and calculate the signal. This is the third verb in
directive #4: VERIFY — but of the INPUTS, not the reasoning. The existing
`analysis_agents._verify_decision` is an adversarial pass over the trader's
argument; it assumes the numbers are sound. This module attacks the numbers.
The failure it exists to catch is reasoning flawlessly over a broken feed.

The split, and why (position P-3 — measure deterministically, judge with AI):
  * Code computes FACTS: which sources are present, how old the ETF print is,
    whether numbers sit in their possible ranges. These are arithmetic and
    lookups. An LLM asked "is this 4 hours old?" does arithmetic it is bad at
    and returns confident-sounding guesses — false assurance is worse than no
    check at all.
  * The AI JUDGES what those facts mean: is a missing sentiment feed
    disqualifying for this symbol right now? Does funding disagree with the
    long/short ratio in a way that says one of them is broken rather than that
    the market is interesting? That is judgment, and it is the AI's job.
  * ENFORCEMENT stays deterministic (P-1): a 'suspect' verdict downgrades the
    trade in code. The model reports; it does not reach into the risk gate.

Modes mirror VERIFY_ENABLED: off | advisory | enforce, default advisory, so
verdicts can be reviewed in telemetry before they start blocking trades.
Fail-open throughout: an unavailable verifier never blocks a decision.

KNOWN GAP (2026-07-17): per-feed staleness is NOT verifiable today. quant,
psych and cross_market do not stamp their own payloads, so nothing here can
tell a live funding rate from one cached an hour ago. Only the ETF print
carries a real date. Feed-level `as_of` stamping is the prerequisite; until
it lands, absence/contradiction/anomaly are the honest scope.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

VERDICTS = ("ok", "suspect")

# Ranges a value CANNOT leave and still be real. Deliberately wide — this
# catches a broken feed (RSI of 4000, negative price), not an unusual market.
# Narrow "that looks odd" judgments belong to the model, not to this table.
_RANGES: dict[str, tuple[float, float]] = {
    "rsi_14": (0.0, 100.0),
    "current_price": (0.0, float("inf")),
    "long_short_ratio": (0.0, float("inf")),
    "open_interest_usd": (0.0, float("inf")),
    "sigma_daily_pct": (0.0, 100.0),
    "funding_rate": (-1.0, 1.0),      # a 100% funding rate is a broken feed
}


def data_verify_mode() -> str:
    """off | advisory | enforce — read at call time so env/tests can flip it."""
    mode = os.getenv("DATA_VERIFY_MODE", "advisory").strip().lower()
    return mode if mode in ("off", "advisory", "enforce") else "advisory"


def data_verify_tier() -> str:
    """Judging measured facts is a bounded task, so this defaults to the cheap
    tier. Set DATA_VERIFY_TIER=decision to spend Opus on it."""
    tier = os.getenv("DATA_VERIFY_TIER", "brief").strip().lower()
    return tier if tier in ("brief", "decision") else "brief"


def _age_days(iso_date: Any) -> Optional[int]:
    """Whole days since a YYYY-MM-DD print. None when unparseable — an
    unreadable date is reported as absent rather than guessed at."""
    try:
        d = date.fromisoformat(str(iso_date)[:10])
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc).date() - d).days


def measure_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """The deterministic half: facts only, no interpretation. Every value here
    is something code can be right about."""
    quant = snapshot.get("quant") or {}
    psych = snapshot.get("psych") or {}

    present, missing = [], []
    for key in ("quant", "sentiment", "psych", "cross_market", "whales",
                "etf_flows", "live_calibration"):
        (present if snapshot.get(key) else missing).append(key)

    out_of_range = []
    for field, (lo, hi) in _RANGES.items():
        value = quant.get(field)
        if isinstance(value, (int, float)) and not (lo <= float(value) <= hi):
            out_of_range.append({"field": field, "value": value,
                                 "possible_range": [lo, hi if hi != float("inf") else None]})

    facts: dict[str, Any] = {
        "sources_present": present,
        "sources_missing": missing,
        "out_of_range": out_of_range,
    }

    etf = snapshot.get("etf_flows") or {}
    btc_block = etf.get("btc") or {}
    if btc_block.get("as_of"):
        facts["etf_print_age_days"] = _age_days(btc_block["as_of"])

    fg = psych.get("fear_greed") or {}
    if isinstance(fg.get("value"), (int, float)):
        facts["fear_greed_value"] = fg["value"]
        facts["fear_greed_in_range"] = 0 <= float(fg["value"]) <= 100

    nxt = snapshot.get("next_event") or {}
    if nxt.get("hours_until") is not None:
        facts["next_event_hours"] = nxt["hours_until"]

    # The whale feed reports zeros both when nothing moved and when it is
    # broken. Code can state the fact; only the model can weigh it.
    whales = snapshot.get("whales") or {}
    if whales:
        facts["whales_all_zero"] = all(
            (v == 0) for v in whales.values() if isinstance(v, (int, float)))

    return facts


PROMPT_HEADER = (
    "You are a data integrity verifier for a trading research platform. You are NOT "
    "deciding whether to trade — you are deciding whether the INPUTS can be trusted "
    "enough to decide on.\n"
    "You get MEASURED FACTS (computed in code — treat these as true) and the RAW "
    "SNAPSHOT. Judge what the facts mean. Look for:\n"
    "  * contradiction — two fields that cannot both be right, or a headline that "
    "disagrees with the numbers under it\n"
    "  * anomaly — values that are technically in range but implausible together\n"
    "  * disqualifying absence — a source whose absence makes this specific verdict "
    "unsafe (not merely incomplete: missing data is normal)\n"
    "Return 'suspect' ONLY when a concern would change a trading decision. Sparse "
    "data is NOT suspect on its own — the fusion step already handles missing "
    "inputs. False alarms cost real trades, so do not reach.\n"
    "Respond with ONLY a JSON object. Keep every 'issue' under 20 words and report at "
    "most 3 concerns — a verdict that overruns its budget is discarded unparsed, so "
    "brevity is not a style note.\n"
    '{"status":"ok|suspect",'
    '"concerns":[{"field":"which field(s)","issue":"what is wrong, <20 words","severity":"low|high"}],'
    '"reason":"1 sentence"}\n\n'
)


def _parse(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None
    if str(obj.get("status", "")).lower() not in VERDICTS:
        return None
    concerns = []
    for c in (obj.get("concerns") or [])[:6]:
        if not isinstance(c, dict):
            continue
        severity = str(c.get("severity", "low")).lower()
        concerns.append({
            "field": str(c.get("field") or "")[:80],
            "issue": str(c.get("issue") or "")[:200],
            "severity": severity if severity in ("low", "high") else "low",
        })
    return {"status": str(obj["status"]).lower(),
            "concerns": concerns,
            "reason": str(obj.get("reason") or "")[:400]}


def verify_snapshot(snapshot: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Verify the factor snapshot's inputs. Returns None (fail-open) when the
    mode is off or the model is unavailable/unusable — a verifier that cannot
    run must never be the reason a decision is blocked."""
    from llm_client import active_provider_model, generate_text, llm_configured
    if data_verify_mode() == "off" or not llm_configured():
        return None

    facts = measure_snapshot(snapshot)
    tier = data_verify_tier()
    prompt = (
        PROMPT_HEADER +
        f"MEASURED FACTS (computed in code — true by construction):\n"
        f"{json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
        f"RAW SNAPSHOT:\n{json.dumps(snapshot, ensure_ascii=False, default=str)[:5000]}\n"
    )
    # 900, not 400: a verbose model overruns a tight budget, the JSON is cut
    # mid-string and the whole verdict is discarded as unparseable. Caught by
    # live prod testing on 2026-07-17 — canned short replies never hit it.
    parsed = _parse(generate_text(prompt, max_tokens=900, temperature=0.1, tier=tier) or "")
    if not parsed:
        return None

    return {**parsed,
            "facts": facts,
            "mode": data_verify_mode(),
            "llm_model": active_provider_model(tier=tier)}


def apply_verification(verdict: dict[str, Any],
                       verification: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic application of the data verdict (P-1: the model reports,
    code enforces). enforce + suspect + a high-severity concern -> hold, since
    a trade justified by data we cannot trust is not a trade we should take.
    Low-severity concerns annotate only. Advisory attaches without changing
    anything. Fail-open: no verification -> verdict untouched."""
    if verification is None:
        return verdict

    block = {k: verification[k] for k in ("status", "concerns", "reason", "llm_model")}
    block["mode"] = verification["mode"]
    block["applied"] = False

    high = [c for c in verification["concerns"] if c["severity"] == "high"]
    if (verification["mode"] == "enforce"
            and verification["status"] == "suspect" and high):
        verdict = dict(verdict)
        verdict["signal"] = "hold"
        verdict["evidence"] = list(verdict.get("evidence") or []) + [
            f"forced hold: inputs marked suspect — {high[0]['issue']}"]
        block["applied"] = True

    verdict = dict(verdict)
    verdict["data_verification"] = block
    return verdict
