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

Staleness (D5b, 2026-07-17): each feed's age is measured and passed to the
model, judged against that feed's own cadence — quant is fetched live per
call, psych is cached ~120s, and the Fear & Greed vendor prints once daily,
so one "too old" threshold would be wrong for all three. Feeds without a
timestamp are reported in `age_unknown` rather than omitted: silence would
read as freshness.

REMAINING GAP: whale/ETF/calibration blocks are aged only by the ETF print
date; the rest carry no per-block stamp yet.
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
    """Decision tier (Opus), and the cheap tier is a false economy here.

    Measured live on prod, same BTCUSDT snapshot, 4 runs per tier (2026-07-17,
    when 'brief' was Haiku): Haiku returned 'suspect' with two HIGH-severity
    concerns every run, all wrong — it read "price above MA20" against
    price_above_ma200 as a contradiction (different indicators; ordinary in a
    downtrend bounce), and called missing sentiment disqualifying despite the
    prompt ruling sparse data out. Opus returned 'ok' 4/4 and filed the one
    real oddity (-44.74% momentum) as low severity. A verifier that invents
    high-severity faults blocks good trades in enforce mode — worse than no
    verifier.

    'brief' is Sonnet since 2026-07-17 and was measured on the same task:
    it caught an injected 3h-stale quant feed 2/2 with the right reasoning
    ("~180x past cadence"), and never produced a false HIGH. It is less
    settled than Opus on the status label — 1 of 2 clean runs said 'suspect'
    while raising only LOW concerns — which enforcement ignores, since it
    requires suspect AND a high-severity concern. So brief is a usable
    economy here; decision is the steadier read."""
    tier = os.getenv("DATA_VERIFY_TIER", "decision").strip().lower()
    return tier if tier in ("brief", "decision") else "decision"


def _age_days(iso_date: Any) -> Optional[int]:
    """Whole days since a YYYY-MM-DD print. None when unparseable — an
    unreadable date is reported as absent rather than guessed at."""
    try:
        d = date.fromisoformat(str(iso_date)[:10])
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc).date() - d).days


def _age_seconds(iso_ts: Any) -> Optional[int]:
    """Seconds since an ISO timestamp (D5b). None when unparseable or in the
    future — a negative age means a clock problem, not fresh data, and saying
    'unknown' is honest where a negative number would read as very fresh."""
    text = str(iso_ts).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:                      # feeds store naive UTC
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = int((datetime.now(timezone.utc) - parsed).total_seconds())
    return age if age >= 0 else None


def _expected_ages() -> dict[str, int]:
    """What each feed's age SHOULD be, read from the config that governs it.

    An age means nothing without its cadence: 2,900s is broken for a live
    quote and unremarkable for an hourly snapshot. These were prose in the
    prompt until 2026-07-17, which was wrong twice over — it claimed psych was
    "~120s" (that is only the Redis cache on the payload; the data is written
    by the hourly PSYCH_REFRESH_INTERVAL loop), and it would silently rot the
    moment an operator retuned the interval. Read the config instead.
    """
    try:
        psych_interval = max(300, int(os.getenv("PSYCH_REFRESH_INTERVAL", "3600")))
    except ValueError:
        psych_interval = 3600
    return {
        # fetched live per call, straight from OKX
        "quant": 60,
        "cross_market": 60,
        # written by the psych worker loop, then Redis-cached ~120s on read
        "psych": psych_interval + 120,
        # the vendor prints once a day; we cannot be fresher than it is
        "fear_greed_vendor_print": 86_400,
    }


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

    # D5b: per-feed age. Feeds that carry no stamp are reported as unknown
    # rather than omitted — "we cannot tell how old this is" is a fact the
    # model should weigh, and silence would read as freshness.
    ages: dict[str, Any] = {}
    for key, block in (("quant", quant), ("psych", psych),
                       ("cross_market", snapshot.get("cross_market") or {})):
        if snapshot.get(key):
            ages[key] = _age_seconds((block or {}).get("as_of"))
    fg_block = psych.get("fear_greed") or {}
    if fg_block:
        ages["fear_greed_vendor_print"] = _age_seconds(fg_block.get("as_of"))

    facts: dict[str, Any] = {
        "sources_present": present,
        "sources_missing": missing,
        "out_of_range": out_of_range,
        "age_seconds": ages,
        "age_unknown": sorted(k for k, v in ages.items() if v is None),
        "expected_max_age_seconds": _expected_ages(),
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
    "  * staleness — compare age_seconds against expected_max_age_seconds for the "
    "SAME feed. Each feed has its own cadence (a live quote and an hourly "
    "snapshot cannot share one threshold), so an age within its expectation is "
    "normal no matter how large it looks. Flag a feed meaningfully past its own "
    "expectation. A feed in age_unknown carries no timestamp — worth saying, but "
    "unknown age is not by itself a fault.\n"
    "  * contradiction — two fields that cannot both be right, or a headline that "
    "disagrees with the numbers under it\n"
    "  * anomaly — values that are technically in range but implausible together\n"
    "  * disqualifying absence — a source whose absence makes this specific verdict "
    "unsafe (not merely incomplete: missing data is normal)\n"
    "Return 'suspect' ONLY when a concern would change a trading decision. False "
    "alarms cost real trades, so do not reach. Specifically NOT suspect:\n"
    "  * sparse or missing data — the fusion step already handles absent inputs\n"
    "  * different indicators disagreeing. MA20, MA60 and MA200 are distinct "
    "measures: price above MA20 while below MA200 is an ordinary pullback/bounce, "
    "not a contradiction. Only flag two fields that measure THE SAME thing and "
    "disagree.\n"
    "  * a market simply looking unusual — you verify the data, not the trade\n"
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
