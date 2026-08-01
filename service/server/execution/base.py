"""
execution/base.py — Broker ABC, Order dataclass, and execution enums.

All broker implementations must subclass Broker and implement the three
abstract methods.  The Order dataclass travels through the full lifecycle:

    created (pending) → submitted → filled | partial_fill | rejected | cancelled

PaperBroker fulfils immediately (no async round-trip to a real API).
Real brokers (Alpaca, Binance, IBKR) submit and may see partial fills.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OrderStatus(str, Enum):
    PENDING       = "pending"
    SUBMITTED     = "submitted"
    FILLED        = "filled"
    PARTIAL_FILL  = "partial_fill"
    REJECTED      = "rejected"
    CANCELLED     = "cancelled"
    # Dry-run shadow only: the venue validated the order (auth, symbol, size)
    # without placing it. Never a fill; terminal by construction.
    VALIDATED     = "validated"


class ExecutionMode(str, Enum):
    """Per-agent execution mode.

    paper  — all trades stay inside Sooppiy's simulated ledger.
    shadow — platform ledger is authoritative; real broker runs in parallel
             for comparison.  No live money moves.
    live   — real broker is authoritative; platform reflects broker fills.
    """
    PAPER  = "paper"
    SHADOW = "shadow"
    LIVE   = "live"


@dataclass(frozen=True)
class BrokerSpec:
    """Declarative per-broker metadata (Plan 19).

    fields — credential blob keys the connect form must supply.
    shadow — how a shadow rule exercises this venue:
        sandbox  — real order to the venue's test environment.
        dry_run  — validate-only call against the LIVE endpoint; the request
                   is unfillable by construction (venue's own test/validate API).
        journal  — no network call at all; the intended order is journalled.
    quote  — the venue's quote currency. Non-USD/USDT quotes (KRW) force an
             FX capture at fill recording (broker_orders.fx_rate_usd).
    """
    fields: tuple
    shadow: str
    quote: str


BROKER_SPECS: dict[str, BrokerSpec] = {
    "alpaca":    BrokerSpec(fields=("key", "secret"),               shadow="sandbox", quote="USD"),
    "binance":   BrokerSpec(fields=("key", "secret"),               shadow="sandbox", quote="USDT"),
    "ibkr":      BrokerSpec(fields=("gateway_url", "account_id"),   shadow="sandbox", quote="USD"),
    "bybit":     BrokerSpec(fields=("key", "secret"),               shadow="sandbox", quote="USDT"),
    "okx":       BrokerSpec(fields=("key", "secret", "passphrase"), shadow="sandbox", quote="USDT"),
    "kraken":    BrokerSpec(fields=("key", "secret"),               shadow="dry_run", quote="USD"),
    "cryptocom": BrokerSpec(fields=("key", "secret"),               shadow="sandbox", quote="USDT"),
    "upbit":     BrokerSpec(fields=("key", "secret"),               shadow="journal", quote="KRW"),
    "kucoin":    BrokerSpec(fields=("key", "secret", "passphrase"), shadow="dry_run", quote="USDT"),
}

AVAILABLE_BROKERS = tuple(BROKER_SPECS)

# Plan 19 §2 — which venues the Accounts page recommends per region
# (users.region country codes; GLOBAL is the fallback row). Informational
# ordering only, never a geo-block: every venue stays connectable everywhere.
REGION_VENUES: dict[str, tuple] = {
    "GLOBAL": ("binance", "bybit", "okx", "kraken", "cryptocom"),
    "KR": ("upbit", "kraken"),
    "JP": ("kraken",),
    "TH": ("binance", "bybit", "kucoin"),
    "VN": ("binance", "bybit", "kucoin"),
    "ID": ("binance", "bybit", "kucoin"),
    "PH": ("binance", "bybit", "kucoin"),
    "SG": ("cryptocom", "kucoin", "okx"),
}

# Longest-first so USDT wins over USD and IDR never eats the R of EUR.
_KNOWN_QUOTES = ("USDT", "USDC", "KRW", "USD", "EUR", "JPY", "BUSD")


def split_symbol(symbol: str, default_quote: str = "USDT") -> tuple:
    """Split a Sooppiy symbol (BTCUSDT / BTC/USDT / BTC-USDT / bare BTC) into
    (base, quote). Bare assets get *default_quote* — every venue adapter needs
    an explicit pair, and the platform's crypto feed quotes in USDT."""
    s = symbol.upper().replace("/", "").replace("-", "").replace("_", "")
    for q in _KNOWN_QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)], q
    return s, default_quote


@dataclass
class Order:
    """Single order travelling through the execution layer."""
    agent_id:       int
    symbol:         str
    market:         str
    side:           str          # buy | sell | short | cover
    quantity:       float
    price:          float
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    broker:         str           = "paper"

    # Set after submission
    status:          OrderStatus        = OrderStatus.PENDING
    broker_order_id: Optional[str]      = None
    error_message:   Optional[str]      = None
    filled_qty:      Optional[float]    = None

    # Non-USD venues (Upbit/KRW): the fill's quote currency and the FX rate
    # (quote units per USD) captured AT fill time — persisted, never recomputed.
    quote_currency: Optional[str]   = None
    fx_rate_usd:    Optional[float] = None

    # Optional FK / context
    db_id:      Optional[int] = None
    signal_id:  Optional[int] = None
    leader_id:  Optional[int] = None
    token_id:   Optional[str] = None
    outcome:    Optional[str] = None
    created_at: Optional[str] = None
    filled_at:  Optional[str] = None

    def is_terminal(self) -> bool:
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.VALIDATED,
        )


class Broker(ABC):
    """Abstract base class all broker adapters must implement."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Canonical lowercase broker identifier, e.g. 'alpaca'."""

    @abstractmethod
    async def submit_order(self, order: Order, cursor=None) -> Order:
        """
        Submit *order* and return it with updated status / broker_order_id.

        Implementations MUST:
          - Set order.status to SUBMITTED (or FILLED if immediately confirmed).
          - Set order.broker_order_id when the broker assigns one.
          - Set order.error_message and status=REJECTED on failure.
          - NEVER raise for expected broker errors (rejected orders, etc.);
            only raise for unexpected infrastructure failures.

        The optional *cursor* is passed by PaperBroker only, allowing it to
        participate in the caller's open DB transaction.
        """

    async def get_order_status(self, broker_order_id: str,
                               symbol: str = "") -> Optional[dict]:
        """Current broker-side state of a previously submitted order.

        Optional capability (default None = "cannot look up"): the order
        reconciler uses it to confirm the final state of SUBMITTED orders.
        Implementations return
            {"status": OrderStatus, "filled_qty": float|None,
             "avg_price": float|None}
        with status mapped onto the OrderStatus enum, or None when the lookup
        itself failed (network, unknown id) — never raise for expected errors.
        *symbol* is required by brokers whose lookup is keyed per instrument
        (Binance); others may ignore it.
        """
        return None

    async def get_margin_state(self) -> Optional[list[dict]]:
        """Per-position margin facts, or None when this broker cannot report them.

        Optional capability, same contract as get_order_status: default None
        means "cannot look up", and implementations must never raise for
        expected errors. Plan 16 (liquidation defence) prefers a venue reading
        over its synthetic model and labels which one the desk is being shown.

        Each entry carries at minimum:
            {"symbol": str, "side": "long"|"short", "qty": float,
             "entry_price": float, "mark_price": float,
             "liquidation_price": float|None, "maintenance_margin": float|None,
             "leverage": float|None, "margin_mode": "isolated"|"cross"|None}

        NOTE none of the shipped adapters implement this yet. Alpaca has no
        futures margin concept on the endpoints we use and should keep
        returning None. Binance would need a NEW futures adapter — the current
        one is spot-only (/api/v3) and cannot see a futures position at all,
        let alone its liquidation price. IBKR reports margin at the ACCOUNT
        level, so a per-position liq price has to be derived and must be
        labelled source="derived" rather than "broker".
        """
        return None

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel a pending/submitted order.  Returns True on success."""

    @abstractmethod
    async def get_broker_positions(self) -> list[dict]:
        """
        Return the broker's current position list as a list of dicts with at
        minimum: symbol, qty (float), side ('long'|'short').
        Used by the reconciler to detect drift.
        """
