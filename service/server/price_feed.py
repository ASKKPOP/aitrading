"""price_feed.py — Phase 4.5 push-based price feed abstraction.

PriceFeed defines the contract every push provider implements:
  - start(on_tick): begin delivering ticks via the callback
  - subscribe(symbols): request prices for additional symbols
  - close(): tear down; any later push is silently dropped

Two implementations ship today:
  - InMemoryPriceFeed: deterministic fake. push() injects ticks for tests
    and local development.
  - HyperliquidWebSocketFeed: connects to wss://api.hyperliquid.xyz/ws
    and subscribes to the `allMids` channel — one subscription, mid-prices
    for every coin. We expose `_parse_message()` separately so the parser
    has unit-test coverage without standing up a real socket.

A Polygon equity feed is a natural Phase 4.5b once production has a
paid Polygon subscription.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Optional, Union


@dataclass
class PriceTick:
    symbol: str
    market: str
    price: float
    timestamp: float = 0.0


# A tick callback may be sync or async; the feed accepts both.
TickHandler = Callable[[PriceTick], Union[None, Awaitable[None]]]


class PriceFeed(ABC):
    """Abstract push-based price feed."""

    @abstractmethod
    async def start(self, *, on_tick: TickHandler) -> None: ...

    @abstractmethod
    async def subscribe(self, symbols: Iterable[str]) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


# ── InMemoryPriceFeed ────────────────────────────────────────────────────

class InMemoryPriceFeed(PriceFeed):
    """Deterministic fake — `push(tick)` invokes the handler in order."""

    def __init__(self) -> None:
        self._handler: Optional[TickHandler] = None
        self._closed: bool = False
        self._subscriptions: set[str] = set()

    async def start(self, *, on_tick: TickHandler) -> None:
        self._handler = on_tick

    async def subscribe(self, symbols: Iterable[str]) -> None:
        for s in symbols:
            self._subscriptions.add(s)

    async def close(self) -> None:
        self._closed = True

    async def push(self, tick: PriceTick) -> None:
        """Test helper — inject a tick. No-op if closed or before start()."""
        if self._closed or self._handler is None:
            return
        result = self._handler(tick)
        if inspect.isawaitable(result):
            await result


# ── HyperliquidWebSocketFeed ──────────────────────────────────────────────

HYPERLIQUID_WS_URL = os.environ.get(
    "HYPERLIQUID_WS_URL", "wss://api.hyperliquid.xyz/ws"
).strip()


class HyperliquidWebSocketFeed(PriceFeed):
    """Push prices from Hyperliquid's `allMids` channel.

    Hyperliquid sends a `mids` map with every mid-price refresh. One
    subscription covers every traded coin so we don't need per-symbol
    subscribe calls — `subscribe(symbols)` is recorded but a no-op at
    the protocol level.

    The actual WS run loop lives in `start()`. Tests call `_parse_message()`
    directly because we don't want to depend on Hyperliquid being reachable.
    """

    def __init__(self, *, url: str = HYPERLIQUID_WS_URL) -> None:
        self._url = url
        self._handler: Optional[TickHandler] = None
        self._closed: bool = False
        self._subscriptions: set[str] = set()
        self._ws_task: Optional[asyncio.Task] = None

    async def start(self, *, on_tick: TickHandler) -> None:
        self._handler = on_tick
        self._ws_task = asyncio.create_task(self._run(), name="hyperliquid-ws-feed")

    async def subscribe(self, symbols: Iterable[str]) -> None:
        # allMids covers everything; we just track the set for diagnostics.
        for s in symbols:
            self._subscriptions.add(s)

    async def close(self) -> None:
        self._closed = True
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):
                pass

    # ── parser (unit-testable without sockets) ────────────────────────────

    def _parse_message(self, raw: Union[str, bytes]) -> list[PriceTick]:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                return []
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(msg, dict):
            return []
        if msg.get("channel") != "allMids":
            return []
        data = msg.get("data")
        if not isinstance(data, dict):
            return []
        mids = data.get("mids")
        if not isinstance(mids, dict):
            return []
        ticks: list[PriceTick] = []
        for sym, raw_price in mids.items():
            try:
                ticks.append(PriceTick(symbol=str(sym), market="crypto", price=float(raw_price)))
            except (TypeError, ValueError):
                continue
        return ticks

    # ── runtime ───────────────────────────────────────────────────────────

    async def _run(self) -> None:
        # Late import so the test suite doesn't require an internet build.
        import websockets

        backoff = 1.0
        while not self._closed:
            try:
                async with websockets.connect(self._url, ping_interval=20) as ws:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "allMids"},
                    }))
                    backoff = 1.0  # connection healthy, reset backoff
                    async for raw in ws:
                        if self._closed:
                            break
                        for tick in self._parse_message(raw):
                            if self._handler is None:
                                continue
                            try:
                                result = self._handler(tick)
                                if inspect.isawaitable(result):
                                    await result
                            except Exception:
                                # Handler errors shouldn't break the feed.
                                pass
            except asyncio.CancelledError:
                raise
            except Exception:
                # Connection dropped, transient error, etc.
                if self._closed:
                    return
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
