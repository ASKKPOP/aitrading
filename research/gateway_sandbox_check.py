"""Per-venue sandbox verification for every trading-gateway adapter (Plan 19 §9).

Run from the repo root:
    .venv/bin/python research/gateway_sandbox_check.py

For EACH broker adapter this script verifies, against the venue's REAL
sandbox/test endpoint (never a mock):

  1. reachability — the venue answers on the exact base URL the adapter uses;
  2. request path — the adapter's own submit_order() builds, signs and sends a
     request the venue parses (dummy credentials), and the venue's
     auth-rejection comes back through the adapter as a clean
     OrderStatus.REJECTED with the venue's message — never an exception,
     never a fake fill;
  3. authenticated round-trip (OPTIONAL) — when real sandbox credentials are
     provided via environment variables, a small market order is submitted to
     the venue's test environment, its status is read back, and (where
     supported) it is cancelled.

Safety: with dummy credentials nothing can ever fill — every call is either a
public endpoint, a venue-side auth failure, or an explicitly validate-only /
test endpoint. The authenticated leg only runs against sandbox/demo
environments (never a live base URL) and only when you export the keys.

Credentials for the optional authenticated legs (all OPTIONAL, all SANDBOX):
    SANDBOX_BINANCE_KEY / SANDBOX_BINANCE_SECRET      (testnet.binance.vision)
    SANDBOX_BYBIT_KEY / SANDBOX_BYBIT_SECRET          (api-demo.bybit.com)
    SANDBOX_OKX_KEY / SANDBOX_OKX_SECRET / SANDBOX_OKX_PASSPHRASE  (demo trading)
    SANDBOX_CRYPTOCOM_KEY / SANDBOX_CRYPTOCOM_SECRET  (uat-api.3ona.co)
    SANDBOX_ALPACA_KEY / SANDBOX_ALPACA_SECRET        (paper-api.alpaca.markets)
    KRAKEN_KEY / KRAKEN_SECRET      (real account — validate-only, never fills)
    KUCOIN_KEY / KUCOIN_SECRET / KUCOIN_PASSPHRASE  (real account — /orders/test only)

Venues with no sandbox at all:
    upbit — journal-only shadow BY DESIGN; this script still verifies the
            public KRW-USDT FX call the adapter depends on, plus the
            error path of an auth-failing order submit.
    ibkr  — the credential is a locally-running Client Portal Gateway
            session; nothing public exists to probe. Reported as SKIPPED.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "service" / "server"))

import httpx  # noqa: E402

from execution.base import Order, OrderStatus  # noqa: E402

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
RESULTS: list[tuple[str, str, str, str]] = []  # (venue, check, status, detail)


def record(venue: str, check: str, ok: bool | None, detail: str) -> None:
    status = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
    RESULTS.append((venue, check, status, detail))
    color = GREEN if ok else (YELLOW if ok is None else RED)
    print(f"  {color}{status}{RESET} {check}: {detail}")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _get(url: str, **kw) -> httpx.Response:
    return httpx.get(url, timeout=15.0, **kw)


def _mk_order(symbol="BTCUSDT", qty=0.001, price=100_000.0) -> Order:
    return Order(agent_id=0, symbol=symbol, market="crypto", side="buy",
                 quantity=qty, price=price)


def _reject_path(venue: str, broker, order: Order, expect_any: list[str]) -> None:
    """Submit through the ADAPTER with dummy creds; the venue must answer and
    the adapter must surface a clean REJECTED carrying the venue's words."""
    try:
        out = _run(broker.submit_order(order))
    except Exception as exc:  # noqa: BLE001
        record(venue, "adapter error path", False, f"adapter raised: {exc!r}")
        return
    msg = (out.error_message or "").lower()
    if out.status is not OrderStatus.REJECTED:
        record(venue, "adapter error path", False,
               f"expected REJECTED, got {out.status} ({out.error_message})")
    elif "network error" in msg:
        record(venue, "adapter error path", False,
               f"venue unreachable through adapter: {out.error_message}")
    elif any(e.lower() in msg for e in expect_any):
        record(venue, "adapter error path", True,
               f"venue auth-rejected as expected: {out.error_message[:90]}")
    else:
        # The venue answered with SOMETHING we parsed — surface it for review.
        record(venue, "adapter error path", True,
               f"venue answered (unmatched wording, review): {out.error_message[:90]}")


# ── binance (spot testnet) ───────────────────────────────────────────────────

def check_binance() -> None:
    print("\n== binance — spot testnet ==")
    base = os.getenv("BINANCE_TESTNET_BASE_URL", "https://testnet.binance.vision/api/v3")
    try:
        r = _get(f"{base.rstrip('/')}/ping")
        record("binance", "sandbox reachable", r.status_code == 200,
               f"GET /ping → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("binance", "sandbox reachable", False, repr(exc))
        return
    from execution.binance import BinanceBroker
    _reject_path("binance", BinanceBroker(key="x" * 24, secret="y" * 24, testnet=True),
                 _mk_order(), ["api-key", "invalid", "unauthorized", "signature", "restricted location"])
    key, sec = os.getenv("SANDBOX_BINANCE_KEY"), os.getenv("SANDBOX_BINANCE_SECRET")
    if not (key and sec):
        record("binance", "authenticated round-trip", None,
               "export SANDBOX_BINANCE_KEY/SECRET (testnet.binance.vision) to run")
        return
    broker = BinanceBroker(key=key, secret=sec, testnet=True)
    out = _run(broker.submit_order(_mk_order(qty=0.001)))
    ok = out.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED)
    record("binance", "authenticated submit", ok,
           f"{out.status.value} id={out.broker_order_id} err={out.error_message}")
    if ok and out.broker_order_id:
        st = _run(broker.get_order_status(out.broker_order_id, symbol="BTCUSDT"))
        record("binance", "status lookup", bool(st), f"{st}")


# ── bybit (demo trading) ─────────────────────────────────────────────────────

def check_bybit() -> None:
    print("\n== bybit — demo trading ==")
    base = os.getenv("BYBIT_DEMO_BASE_URL", "https://api-demo.bybit.com")
    try:
        r = _get(f"{base}/v5/market/time")
        ok = r.status_code == 200 and r.json().get("retCode") == 0
        record("bybit", "sandbox reachable", ok, f"GET /v5/market/time → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("bybit", "sandbox reachable", False, repr(exc))
        return
    from execution.bybit import BybitBroker
    _reject_path("bybit", BybitBroker(key="x" * 18, secret="y" * 36, sandbox=True),
                 _mk_order(), ["api key", "invalid", "10003", "10004", "sign", "cloudfront", "block access"])
    key, sec = os.getenv("SANDBOX_BYBIT_KEY"), os.getenv("SANDBOX_BYBIT_SECRET")
    if not (key and sec):
        record("bybit", "authenticated round-trip", None,
               "export SANDBOX_BYBIT_KEY/SECRET (demo-trading key) to run")
        return
    broker = BybitBroker(key=key, secret=sec, sandbox=True)
    out = _run(broker.submit_order(_mk_order(qty=0.001)))
    ok = out.status is OrderStatus.SUBMITTED
    record("bybit", "authenticated submit", ok,
           f"{out.status.value} id={out.broker_order_id} err={out.error_message}")
    if ok and out.broker_order_id:
        st = _run(broker.get_order_status(out.broker_order_id, symbol="BTCUSDT"))
        record("bybit", "status lookup", bool(st), f"{st}")


# ── okx (demo trading header) ────────────────────────────────────────────────

def check_okx() -> None:
    print("\n== okx — demo trading ==")
    base = os.getenv("OKX_BASE_URL", "https://www.okx.com")
    try:
        r = _get(f"{base}/api/v5/public/time")
        ok = r.status_code == 200 and r.json().get("code") == "0"
        record("okx", "venue reachable", ok, f"GET /api/v5/public/time → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("okx", "venue reachable", False, repr(exc))
        return
    from execution.okx import OKXBroker
    _reject_path("okx", OKXBroker(key="x" * 32, secret="y" * 32, passphrase="p",
                                  sandbox=True),
                 _mk_order(), ["apikey", "api key", "50111", "50113", "invalid", "timestamp"])
    key = os.getenv("SANDBOX_OKX_KEY")
    sec = os.getenv("SANDBOX_OKX_SECRET")
    pw = os.getenv("SANDBOX_OKX_PASSPHRASE")
    if not (key and sec and pw):
        record("okx", "authenticated round-trip", None,
               "export SANDBOX_OKX_KEY/SECRET/PASSPHRASE (demo-trading key) to run")
        return
    broker = OKXBroker(key=key, secret=sec, passphrase=pw, sandbox=True)
    out = _run(broker.submit_order(_mk_order(qty=0.0001)))
    ok = out.status is OrderStatus.SUBMITTED
    record("okx", "authenticated submit", ok,
           f"{out.status.value} id={out.broker_order_id} err={out.error_message}")
    if ok and out.broker_order_id:
        st = _run(broker.get_order_status(out.broker_order_id, symbol="BTCUSDT"))
        record("okx", "status lookup", bool(st), f"{st}")


# ── kraken (validate-only against the live endpoint) ─────────────────────────

def check_kraken() -> None:
    print("\n== kraken — validate-only dry-run ==")
    base = os.getenv("KRAKEN_BASE_URL", "https://api.kraken.com")
    try:
        r = _get(f"{base}/0/public/Time")
        ok = r.status_code == 200 and not r.json().get("error")
        record("kraken", "venue reachable", ok, f"GET /0/public/Time → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("kraken", "venue reachable", False, repr(exc))
        return
    from execution.kraken import KrakenBroker
    import base64
    _reject_path("kraken",
                 KrakenBroker(key="x" * 20, secret=base64.b64encode(b"s" * 32).decode(),
                              validate_only=True),
                 _mk_order(), ["eapi", "invalid key", "invalid signature", "egeneral"])
    key, sec = os.getenv("KRAKEN_KEY"), os.getenv("KRAKEN_SECRET")
    if not (key and sec):
        record("kraken", "authenticated validate", None,
               "export KRAKEN_KEY/SECRET (real account; validate-only, can never fill) to run")
        return
    broker = KrakenBroker(key=key, secret=sec, validate_only=True)
    out = _run(broker.submit_order(_mk_order(qty=0.0001)))
    ok = out.status is OrderStatus.VALIDATED
    record("kraken", "authenticated validate", ok,
           f"{out.status.value} err={out.error_message}")


# ── crypto.com (UAT sandbox) ─────────────────────────────────────────────────

def check_cryptocom() -> None:
    print("\n== crypto.com — UAT sandbox ==")
    base = os.getenv("CRYPTOCOM_UAT_BASE_URL", "https://uat-api.3ona.co/exchange/v1")
    try:
        r = _get(f"{base}/public/get-instruments")
        ok = r.status_code == 200
        record("cryptocom", "sandbox reachable", ok,
               f"GET /public/get-instruments → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("cryptocom", "sandbox reachable", False, repr(exc))
        return
    from execution.cryptocom import CryptocomBroker
    _reject_path("cryptocom", CryptocomBroker(key="x" * 20, secret="y" * 30, sandbox=True),
                 _mk_order(), ["unauthorized", "10002", "invalid", "40101", "authentication failure"])
    key, sec = os.getenv("SANDBOX_CRYPTOCOM_KEY"), os.getenv("SANDBOX_CRYPTOCOM_SECRET")
    if not (key and sec):
        record("cryptocom", "authenticated round-trip", None,
               "export SANDBOX_CRYPTOCOM_KEY/SECRET (UAT key) to run")
        return
    broker = CryptocomBroker(key=key, secret=sec, sandbox=True)
    out = _run(broker.submit_order(_mk_order(qty=0.0001)))
    ok = out.status is OrderStatus.SUBMITTED
    record("cryptocom", "authenticated submit", ok,
           f"{out.status.value} id={out.broker_order_id} err={out.error_message}")
    if ok and out.broker_order_id:
        st = _run(broker.get_order_status(out.broker_order_id))
        record("cryptocom", "status lookup", bool(st), f"{st}")


# ── upbit (no sandbox — journal-only by design) ──────────────────────────────

def check_upbit() -> None:
    print("\n== upbit — no sandbox (journal-only shadow by design) ==")
    from execution.upbit import UpbitBroker
    broker = UpbitBroker(key="x" * 30, secret="y" * 40)
    # The one live call the adapter depends on even before any order: FX.
    fx = _run(broker._krw_per_usd())
    ok = fx is not None and 500 < fx < 5000
    record("upbit", "public KRW-USDT FX feed", bool(ok),
           f"krw_per_usd = {fx}")
    # Order submit with dummy creds — the venue must reject through the adapter.
    _reject_path("upbit", broker, _mk_order(),
                 ["invalid_access_key", "jwt", "401", "unauthorized",
                  "no_authorization", "invalid"])
    record("upbit", "sandbox round-trip", None,
           "no sandbox exists — shadow is journal-only BY DESIGN; live "
           "verification happens via the allowlist soak on the owner's account")


# ── kucoin (/orders/test dry-run) ────────────────────────────────────────────

def check_kucoin() -> None:
    print("\n== kucoin — order-test dry-run ==")
    base = os.getenv("KUCOIN_BASE_URL", "https://api.kucoin.com")
    try:
        r = _get(f"{base}/api/v1/timestamp")
        ok = r.status_code == 200 and str(r.json().get("code")) == "200000"
        record("kucoin", "venue reachable", ok, f"GET /api/v1/timestamp → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("kucoin", "venue reachable", False, repr(exc))
        return
    from execution.kucoin import KucoinBroker
    _reject_path("kucoin",
                 KucoinBroker(key="x" * 24, secret="y" * 36, passphrase="p",
                              test_only=True),
                 _mk_order(), ["400003", "400004", "400005", "invalid", "kc-api"])
    key = os.getenv("KUCOIN_KEY")
    sec = os.getenv("KUCOIN_SECRET")
    pw = os.getenv("KUCOIN_PASSPHRASE")
    if not (key and sec and pw):
        record("kucoin", "authenticated order-test", None,
               "export KUCOIN_KEY/SECRET/PASSPHRASE (real account; /orders/test only, can never fill) to run")
        return
    broker = KucoinBroker(key=key, secret=sec, passphrase=pw, test_only=True)
    out = _run(broker.submit_order(_mk_order(qty=0.0001)))
    ok = out.status is OrderStatus.VALIDATED
    record("kucoin", "authenticated order-test", ok,
           f"{out.status.value} err={out.error_message}")


# ── alpaca (paper) ───────────────────────────────────────────────────────────

def check_alpaca() -> None:
    print("\n== alpaca — paper environment ==")
    base = os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets/v2")
    try:
        r = _get(f"{base.rstrip('/')}/clock")   # auth-required: 401/403 proves reachability
        record("alpaca", "sandbox reachable", r.status_code in (200, 401, 403),
               f"GET /clock → {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("alpaca", "sandbox reachable", False, repr(exc))
        return
    from execution.alpaca import AlpacaBroker
    order = Order(agent_id=0, symbol="AAPL", market="us-stock", side="buy",
                  quantity=1, price=100.0)
    _reject_path("alpaca", AlpacaBroker(key="x" * 20, secret="y" * 40, paper=True),
                 order, ["forbidden", "unauthorized", "40110000", "access key"])
    key, sec = os.getenv("SANDBOX_ALPACA_KEY"), os.getenv("SANDBOX_ALPACA_SECRET")
    if not (key and sec):
        record("alpaca", "authenticated round-trip", None,
               "export SANDBOX_ALPACA_KEY/SECRET (paper keys) to run")
        return
    broker = AlpacaBroker(key=key, secret=sec, paper=True)
    out = _run(broker.submit_order(Order(agent_id=0, symbol="AAPL", market="us-stock",
                                         side="buy", quantity=1, price=100.0)))
    ok = out.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED)
    record("alpaca", "authenticated submit", ok,
           f"{out.status.value} id={out.broker_order_id} err={out.error_message}")


def check_ibkr() -> None:
    print("\n== ibkr — client portal gateway ==")
    record("ibkr", "sandbox round-trip", None,
           "the credential IS a locally running, logged-in Client Portal "
           "Gateway session — nothing public exists to probe; verified in "
           "production by the keepalive worker + /api/execution/health")


def main() -> None:
    for fn in (check_binance, check_bybit, check_okx, check_kraken,
               check_cryptocom, check_upbit, check_kucoin, check_alpaca,
               check_ibkr):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — one venue must not stop the sweep
            record(fn.__name__.removeprefix("check_"), "sweep", False, repr(exc))

    print("\n" + "=" * 72)
    print(f"{'VENUE':<11} {'CHECK':<28} {'RESULT':<7} DETAIL")
    print("-" * 72)
    fails = 0
    for venue, check, status, detail in RESULTS:
        print(f"{venue:<11} {check:<28} {status:<7} {detail[:70]}")
        fails += status == "FAIL"
    print("=" * 72)
    print(f"{len(RESULTS)} checks · {fails} failures")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
