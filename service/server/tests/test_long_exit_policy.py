"""Owner rule 2026-11-21: automation sells a long only above its buy price
plus fees, at the +5% target, or at the -15% emergency level."""

import pytest

import long_exit_policy as lep

ENTRY = 100.0


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # Unset = the production default (ON); conftest turns it off suite-wide.
    for k in ("LONG_EXIT_POLICY", "LONG_TARGET_FRAC", "LONG_EMERGENCY_LOSS_FRAC"):
        monkeypatch.delenv(k, raising=False)


def test_production_default_is_on():
    assert lep.enabled() is True


def test_breakeven_nets_zero_after_both_fees():
    rate = lep._fee_rate("crypto")
    be = lep.breakeven_price(ENTRY, "crypto")
    q = 1.0
    net = (be - ENTRY) * q - ENTRY * q * rate - be * q * rate
    assert abs(net) < 1e-9


@pytest.mark.parametrize("price,refused", [
    (99.0, True),     # small loss -> held
    (100.0, True),    # flat -> held (fees make it a loss)
    (100.05, True),   # gross gain smaller than fees -> held
    (100.21, False),  # above breakeven at either fee schedule -> allowed
    (105.0, False),   # target
    (85.5, True),     # -14.5% -> still held
    (85.0, False),    # exactly -15% -> emergency sell
    (60.0, False),    # beyond -15% -> emergency sell
])
def test_automated_long_close(price, refused):
    assert (lep.long_close_refusal(ENTRY, price, "crypto") is not None) is refused


def test_just_below_and_above_breakeven():
    be = lep.breakeven_price(ENTRY, "crypto")
    assert lep.long_close_refusal(ENTRY, be * 0.9999, "crypto") is not None
    assert lep.long_close_refusal(ENTRY, be * 1.0001, "crypto") is None


def test_human_close_is_never_refused():
    assert lep.long_close_refusal(ENTRY, 90.0, "crypto", automated=False) is None


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("LONG_EXIT_POLICY", "0")
    assert lep.long_close_refusal(ENTRY, 90.0, "crypto") is None
    assert lep.long_bracket(ENTRY) is None


@pytest.mark.parametrize("entry,price", [(None, 90), (0, 90), (100, None), ("x", 1)])
def test_unusable_inputs_fail_open(entry, price):
    assert lep.long_close_refusal(entry, price, "crypto") is None


def test_bracket_is_minus_15_plus_5():
    stop, tp = lep.long_bracket(ENTRY)
    assert stop == pytest.approx(85.0)
    assert tp == pytest.approx(105.0)


def test_fractions_from_env(monkeypatch):
    monkeypatch.setenv("LONG_TARGET_FRAC", "0.08")
    monkeypatch.setenv("LONG_EMERGENCY_LOSS_FRAC", "0.2")
    assert lep.long_bracket(ENTRY) == (pytest.approx(80.0), pytest.approx(108.0))
    monkeypatch.setenv("LONG_TARGET_FRAC", "5")      # nonsense -> default
    assert lep.target_frac() == 0.05
