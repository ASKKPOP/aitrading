"""Unit tests for the swing signal stack engine (research/SWING_SIGNAL_STACK.md)."""
import pytest

import swing_stack as ss


def _bars(closes, lows=None, highs=None, vols=None):
    n = len(closes)
    lows = lows or [c * 0.99 for c in closes]
    highs = highs or [c * 1.01 for c in closes]
    vols = vols or [1000.0] * n
    return [
        {"ts": i, "open": closes[i], "high": highs[i], "low": lows[i],
         "close": closes[i], "volume": vols[i]}
        for i in range(n)
    ]


# --- composite -------------------------------------------------------------

def test_composite_reproduces_doc_worked_example():
    scores = {"sentiment": 62, "macro": 35, "thesis": 55,
              "smart_money": 20, "technical": 48}
    assert ss.composite_score(scores) == pytest.approx(46.1)


def test_composite_renormalizes_missing_feeds():
    # only technical present at +100: renormalized composite is +100, not +20
    assert ss.composite_score({"technical": 100}) == pytest.approx(100.0)


def test_composite_all_missing_is_none():
    assert ss.composite_score({}) is None


def test_composite_neutral_zero_is_not_missing():
    # 0 keeps its weight (pulls composite toward WAIT), None does not
    with_zero = ss.composite_score({"technical": 100, "sentiment": 0})
    assert with_zero == pytest.approx(100 * 0.20 / 0.45)


# --- two-axis matrix -------------------------------------------------------

def test_two_axis_agreement_and_conflicts():
    assert ss.two_axis_state({"technical": 50, "sentiment": 50}) == "AGREE_BULL"
    assert ss.two_axis_state({"technical": -50, "sentiment": -50}) == "AGREE_BEAR"
    assert (
        ss.two_axis_state({"technical": 50, "sentiment": -50})
        == "CONFLICT_CONTRARIAN_WATCH"
    )
    assert (
        ss.two_axis_state({"technical": -50, "sentiment": 50})
        == "CONFLICT_POSSIBLE_TRAP"
    )


def test_two_axis_dead_zone_is_flat():
    assert ss.two_axis_state({"technical": 5, "sentiment": 50}) == "NEUTRAL"


# --- decide ---------------------------------------------------------------

def _bull_scores():
    return {"sentiment": 62, "macro": 35, "thesis": 55,
            "smart_money": 20, "technical": 48}


def test_decide_buy_on_agreement_and_threshold():
    out = ss.decide(_bull_scores())
    assert out["action"] == "BUY"
    assert out["composite"] == pytest.approx(46.1)


def test_decide_event_blackout_vetoes_buy():
    out = ss.decide(_bull_scores(), hours_to_binary_event=6)
    assert out["action"] == "WAIT"
    assert out["veto"] == "event_blackout"


def test_decide_blackout_only_inside_24h():
    assert ss.decide(_bull_scores(), hours_to_binary_event=30)["action"] == "BUY"


def test_decide_conflict_waits_even_with_high_composite():
    # strong technical, euphoric-crowd qual: composite can clear +40 but the
    # matrix says WAIT (trap) — two-axis rule dominates the threshold
    scores = {"technical": 100, "sentiment": -20, "macro": 90}
    out = ss.decide(scores)
    assert out["action"] == "WAIT"
    assert out["axis"] == "CONFLICT_CONTRARIAN_WATCH"


def test_decide_sell_needs_agreement():
    out = ss.decide({"technical": -80, "sentiment": -80, "macro": -50})
    assert out["action"] == "SELL"


def test_decide_wait_band():
    out = ss.decide({"technical": 20, "sentiment": 20})
    assert out["action"] == "WAIT"
    assert out["veto"] is None


# --- processor scores ------------------------------------------------------

def test_technical_score_needs_history():
    assert ss.technical_score(_bars([100.0] * 10)) is None


def test_technical_score_uptrend_positive_downtrend_negative():
    up = _bars([100 + i for i in range(30)])
    down = _bars([130 - i for i in range(30)])
    assert ss.technical_score(up) > 40
    assert ss.technical_score(down) < -40


def test_technical_relative_strength_vs_benchmark():
    flat = _bars([100.0 + 0.01 * (i % 2) for i in range(30)])
    strong_bench = _bars([100 * (1.02 ** i) for i in range(30)])
    weak_bench = _bars([100 * (0.98 ** i) for i in range(30)])
    assert ss.technical_score(flat, weak_bench) > ss.technical_score(flat, strong_bench)


def test_macro_score_bands():
    calm = ss.macro_score(13, 14, 4.0, 4.1, 100, 101)  # low VIX, yields+DXY falling
    stressed = ss.macro_score(32, 25, 4.4, 4.1, 104, 101)
    assert calm > 40
    assert stressed < -70
    assert ss.macro_score(None, None, None, None, None, None) is None


def test_psych_score_contrarian():
    assert ss.psych_sentiment_score(10, 12) > 30      # extreme fear -> buy setup
    assert ss.psych_sentiment_score(10, 15) < ss.psych_sentiment_score(5, 15)
    assert ss.psych_sentiment_score(90, 85) < -30     # euphoria -> sell setup
    assert ss.psych_sentiment_score(50, 50) == 0.0    # mid-range -> neutral
    assert ss.psych_sentiment_score(None, None) is None


def test_psych_turn_out_of_fear_bonus():
    turning = ss.psych_sentiment_score(30, 22)   # fear zone, tone flipping up
    static = ss.psych_sentiment_score(30, 30)
    assert turning == static + 30


def test_psych_mid_band_follows_tone_not_zero():
    # v1 scored the whole 25..75 band 0 -> qual axis dead all month (killed
    # by the 2026-08 sim). Mid-band must follow tone level + rate of change.
    rising = ss.psych_sentiment_score(60, 52)   # improving tone
    falling = ss.psych_sentiment_score(45, 53)  # deteriorating tone
    assert rising > ss.AXIS_DEAD_ZONE
    assert falling < -ss.AXIS_DEAD_ZONE
    assert ss.psych_sentiment_score(66, 63) > 0


# --- risk gate + playbook exits -------------------------------------------

def test_position_size_fixed_fractional():
    # $100k equity, 1% risk, $5 stop distance -> 200 units
    assert ss.position_size(100_000, 105.0, 100.0) == pytest.approx(200.0)
    assert ss.position_size(100_000, 100.0, 105.0) == 0.0  # inverted stop


def test_initial_stop_is_recent_flush_low():
    bars = _bars([100, 101, 99, 102, 103], lows=[98, 97, 95, 100, 101])
    assert ss.initial_stop(bars) == 95


def test_target_is_2r():
    assert ss.target_price(105.0, 100.0) == pytest.approx(115.0)


def test_signal_exit_shock_and_euphoria():
    shock = {"technical": -80, "sentiment": -80, "macro": -60}
    assert ss.signal_exit_reason(shock) == "shock_or_broken_thesis"
    euphoria = {"technical": 60, "sentiment": -55, "macro": 10}
    assert ss.signal_exit_reason(euphoria) == "euphoria_top"
    healthy = {"technical": 50, "sentiment": 30, "macro": 10}
    assert ss.signal_exit_reason(healthy) is None


def test_time_stop_at_d5():
    assert not ss.time_stop_hit(4)
    assert ss.time_stop_hit(5)


def test_rsi_bounds():
    up = [100.0 + i for i in range(20)]
    down = [120.0 - i for i in range(20)]
    assert ss.rsi(up) == 100.0
    assert ss.rsi(down) == pytest.approx(0.0)
    assert ss.rsi([1.0, 2.0]) is None
