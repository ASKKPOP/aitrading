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
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderStatus(str, Enum):
    PENDING       = "pending"
    SUBMITTED     = "submitted"
    FILLED        = "filled"
    PARTIAL_FILL  = "partial_fill"
    REJECTED      = "rejected"
    CANCELLED     = "cancelled"


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


AVAILABLE_BROKERS = ("alpaca", "binance", "ibkr")


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
