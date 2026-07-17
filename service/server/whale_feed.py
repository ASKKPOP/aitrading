"""Real on-chain whale tracking (Plan 06 B1) — free sources, no estimates.

    BTC   blockchain.info mempool (keyless): large-value transactions observed
          right now. Direction is unknown without an address database, so BTC
          events are honest "large_transfer"s.
    ETH   Etherscan v2 (ETHERSCAN_API_KEY): recent native-ETH transactions on
          well-known exchange hot wallets. Direction is real:
              to the exchange   -> "in"  (potential sell pressure)
              from the exchange -> "out" (accumulation / self-custody)
          ERC-20 token flows are out of scope for v1 (native ETH only).

Feature-gated by WHALE_FEED_ENABLED (default off). Threshold WHALE_MIN_USD
(default $5M). Every event carries estimated: False plus its source. Fail-soft:
any source problem yields an empty list, never an exception to callers.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TIMEOUT = 12
_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_CACHE_TTL_SECONDS = 120

# Well-known exchange hot wallets (public, widely tagged). Lowercase.
EXCHANGE_ETH_WALLETS: dict[str, str] = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase 1",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 2",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
}
# Only ETH txs newer than this window count (exchange wallets are busy; old
# rows would otherwise dominate every poll).
ETH_LOOKBACK_SECONDS = 6 * 3600


def whale_feed_enabled() -> bool:
    return os.getenv("WHALE_FEED_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def whale_min_usd() -> float:
    try:
        return float(os.getenv("WHALE_MIN_USD", "5000000"))
    except ValueError:
        return 5_000_000.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "sooppiy/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _spot_price(symbol: str) -> Optional[float]:
    """Last perp price from the OKX feed (BTCUSDT / ETHUSDT)."""
    try:
        from crypto_feed import fetch_ticker
        ticker = fetch_ticker(symbol)
        price = float(ticker.get("last_price") or 0)
        return price if price > 0 else None
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────── BTC — blockchain.info mempool ───────────────────────────

def fetch_btc_whale_txs(min_usd: float, btc_price: float) -> list[dict[str, Any]]:
    """Large-value transactions currently in the BTC mempool."""
    data = _get_json("https://blockchain.info/unconfirmed-transactions?format=json")
    events: list[dict[str, Any]] = []
    for tx in data.get("txs", []):
        total_sats = sum(int(o.get("value") or 0) for o in tx.get("out", []))
        usd = total_sats / 1e8 * btc_price
        if usd < min_usd:
            continue
        events.append({
            "chain": "BTC",
            "symbol": "BTCUSDT",
            "direction": "transfer",       # address book needed for in/out — honest label
            "usd_value": round(usd, 2),
            "amount": round(total_sats / 1e8, 4),
            "tx_hash": tx.get("hash"),
            "ts": tx.get("time"),
            "source": "blockchain.info",
            "estimated": False,
        })
    events.sort(key=lambda e: e["usd_value"], reverse=True)
    return events[:20]


# ─────────────────────────── ETH — Etherscan exchange wallets ───────────────────────────

def fetch_eth_whale_txs(min_usd: float, eth_price: float,
                        api_key: Optional[str] = None) -> list[dict[str, Any]]:
    """Recent large native-ETH transfers touching known exchange hot wallets."""
    key = (api_key or os.getenv("ETHERSCAN_API_KEY", "")).strip()
    if not key:
        return []
    cutoff = time.time() - ETH_LOOKBACK_SECONDS
    events: list[dict[str, Any]] = []
    for wallet, label in EXCHANGE_ETH_WALLETS.items():
        try:
            data = _get_json(
                "https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist"
                f"&address={wallet}&page=1&offset=25&sort=desc&apikey={key}")
        except Exception as exc:  # noqa: BLE001
            logger.debug("etherscan fetch failed for %s: %s", label, exc)
            continue
        rows = data.get("result") if isinstance(data.get("result"), list) else []
        for tx in rows:
            try:
                ts = int(tx.get("timeStamp") or 0)
                eth = int(tx.get("value") or 0) / 1e18
            except (TypeError, ValueError):
                continue
            if ts < cutoff or eth <= 0:
                continue
            usd = eth * eth_price
            if usd < min_usd:
                continue
            to_addr = (tx.get("to") or "").lower()
            direction = "in" if to_addr == wallet else "out"
            events.append({
                "chain": "ETH",
                "symbol": "ETHUSDT",
                "direction": direction,
                "exchange": label,
                "usd_value": round(usd, 2),
                "amount": round(eth, 4),
                "tx_hash": tx.get("hash"),
                "ts": ts,
                "source": "etherscan",
                "estimated": False,
            })
    # dedup by hash (a transfer between two tracked wallets appears twice)
    seen: set = set()
    unique = []
    for e in sorted(events, key=lambda e: e["usd_value"], reverse=True):
        if e["tx_hash"] in seen:
            continue
        seen.add(e["tx_hash"])
        unique.append(e)
    return unique[:20]


# ─────────────────────────── aggregate payload ───────────────────────────

def get_whale_payload(force_refresh: bool = False) -> dict[str, Any]:
    """Cached snapshot of current whale activity. Fail-soft per chain."""
    if not whale_feed_enabled():
        return {"available": False, "reason": "WHALE_FEED_ENABLED off",
                "events": [], "totals": {}, "min_usd": whale_min_usd()}
    now = time.time()
    if not force_refresh and _CACHE["payload"] is not None and now - _CACHE["at"] < _CACHE_TTL_SECONDS:
        return _CACHE["payload"]

    min_usd = whale_min_usd()
    events: list[dict[str, Any]] = []
    btc_price = _spot_price("BTCUSDT")
    if btc_price:
        try:
            events.extend(fetch_btc_whale_txs(min_usd, btc_price))
        except Exception as exc:  # noqa: BLE001
            logger.debug("btc whale fetch failed: %s", exc)
    eth_price = _spot_price("ETHUSDT")
    if eth_price:
        try:
            events.extend(fetch_eth_whale_txs(min_usd, eth_price))
        except Exception as exc:  # noqa: BLE001
            logger.debug("eth whale fetch failed: %s", exc)

    eth_in = sum(e["usd_value"] for e in events if e["chain"] == "ETH" and e["direction"] == "in")
    eth_out = sum(e["usd_value"] for e in events if e["chain"] == "ETH" and e["direction"] == "out")
    payload = {
        "available": True,
        "events": events,
        "totals": {
            "btc_transfer_usd": round(sum(e["usd_value"] for e in events if e["chain"] == "BTC"), 2),
            "eth_exchange_in_usd": round(eth_in, 2),
            "eth_exchange_out_usd": round(eth_out, 2),
            "eth_net_flow_usd": round(eth_in - eth_out, 2),  # positive = net INTO exchanges (sell pressure)
        },
        "count": len(events),
        "min_usd": min_usd,
        "created_at": _now_iso(),
    }
    _CACHE["payload"] = payload
    _CACHE["at"] = now
    return payload


def whale_scanner_signals() -> list[dict[str, Any]]:
    """Adapter for scanner.assemble_candidates: [{symbol, direction, usd_value, reason}]."""
    payload = get_whale_payload()
    if not payload.get("available"):
        return []
    signals: list[dict[str, Any]] = []
    for e in payload["events"][:6]:
        usd_m = e["usd_value"] / 1e6
        if e["chain"] == "ETH":
            verb = "into" if e["direction"] == "in" else "out of"
            reason = f"whale: ${usd_m:.1f}M ETH {verb} {e.get('exchange', 'exchange')}"
        else:
            reason = f"whale: ${usd_m:.1f}M BTC on-chain transfer"
        signals.append({"symbol": e["symbol"], "direction": e["direction"],
                        "usd_value": e["usd_value"], "reason": reason})
    return signals
