"""Backtesting engine.

Replays an agent's recorded realtime trade signals against their stored
execution prices and returns P&L metrics and a portfolio curve.

No external price calls are made — the engine uses the prices stored in the
`signals` table when each trade was submitted, keeping results deterministic
and free of API rate limits.

Public entry point:
    run_backtest(agent_id, start_at, end_at, *, initial_cash, market, symbol)
        → BacktestResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backtest_metrics import (
    avg_loss as _calc_avg_loss,
    avg_win as _calc_avg_win,
    calmar_ratio as _calc_calmar,
    daily_equity_returns as _calc_daily_returns,
    max_drawdown as _calc_max_drawdown,
    profit_factor as _calc_profit_factor,
    sharpe_ratio as _calc_sharpe,
    sortino_ratio as _calc_sortino,
)
from database import get_db_connection
from fees import TRADE_FEE_RATE
import markets


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _Position:
    """A single open directional position."""
    symbol: str
    market: str
    side: str          # 'buy' (long) or 'short'
    quantity: float    # contracts / shares, as the user entered them
    avg_price: float   # average entry price
    # Notional per point. Quantity stays in contracts so the report reads in the
    # user's units; every cash and PnL term multiplies through this.
    multiplier: float = 1.0

    @property
    def is_long(self) -> bool:
        return self.side == "buy"

    @property
    def notional_qty(self) -> float:
        return self.quantity * self.multiplier


@dataclass
class ClosedTrade:
    symbol: str
    market: str
    direction: str      # 'long' or 'short'
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    opened_at: str
    closed_at: str


@dataclass
class CurvePoint:
    timestamp: str      # ISO-8601 UTC
    portfolio_value: float
    cash: float
    position_value: float


@dataclass
class BacktestResult:
    initial_cash: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    profit_factor: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    curve: list[CurvePoint] = field(default_factory=list)
    open_positions: list[dict] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fee(price: float, qty: float) -> float:
    return price * qty * TRADE_FEE_RATE


def _position_value(positions: dict[str, _Position], last_prices: dict[str, float]) -> float:
    """Mark open positions to the last known price for each symbol."""
    total = 0.0
    for key, pos in positions.items():
        price = last_prices.get(key, pos.avg_price)
        nq = pos.notional_qty
        if pos.is_long:
            total += price * nq
        else:
            # Short P&L: we received cash at entry; unrealised gain/loss from price move
            total += pos.avg_price * nq + (pos.avg_price - price) * nq
    return total


def _portfolio_value(cash: float, positions: dict[str, _Position], last_prices: dict[str, float]) -> float:
    return cash + _position_value(positions, last_prices)




# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

_MAX_BACKTEST_SIGNALS = 10_000


def run_backtest(
    agent_id: int,
    start_at: str,
    end_at: str,
    *,
    initial_cash: float = 100_000.0,
    market: Optional[str] = None,
    symbol: Optional[str] = None,
    max_signals: int = _MAX_BACKTEST_SIGNALS,
) -> BacktestResult:
    """Replay an agent's recorded trades and return backtest metrics.

    Args:
        agent_id:     Agent whose trade signals to replay.
        start_at:     ISO-8601 UTC start of the replay window (inclusive).
        end_at:       ISO-8601 UTC end of the replay window (inclusive).
        initial_cash: Starting cash balance (default 100 000).
        market:       Optional market filter (e.g. 'us-stock').
        symbol:       Optional symbol filter (e.g. 'AAPL').

    Returns:
        BacktestResult with summary metrics, closed trade list, and portfolio curve.
    """
    initial_cash = max(0.0, float(initial_cash))

    # ------------------------------------------------------------------
    # Load trades from DB
    # ------------------------------------------------------------------
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT signal_id, symbol, market, side, entry_price, quantity, executed_at
            FROM signals
            WHERE agent_id = ?
              AND message_type = 'operation'
              AND signal_type = 'realtime'
              AND entry_price IS NOT NULL
              AND quantity IS NOT NULL
              AND executed_at >= ?
              AND executed_at <= ?
        """
        params: list = [agent_id, start_at, end_at]
        if market:
            sql += " AND market = ?"
            params.append(market)
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol.upper())
        sql += f" ORDER BY executed_at ASC, signal_id ASC LIMIT {int(max_signals)}"
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    if not rows:
        return BacktestResult(
            initial_cash=initial_cash,
            final_value=initial_cash,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            trade_count=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            sharpe_ratio=None,
        )

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------
    cash = initial_cash
    positions: dict[str, _Position] = {}   # key = "{market}:{symbol}"
    last_prices: dict[str, float] = {}
    closed_trades: list[ClosedTrade] = []
    curve: list[CurvePoint] = []
    pv_series: list[float] = [initial_cash]
    open_timestamps: dict[str, str] = {}   # position key → opened_at

    # Seed curve with start point
    curve.append(CurvePoint(
        timestamp=start_at,
        portfolio_value=initial_cash,
        cash=initial_cash,
        position_value=0.0,
    ))

    for row in rows:
        sym = (row["symbol"] or "").upper()
        mkt = (row["market"] or "").lower()
        action = (row["side"] or "").lower()
        price = float(row["entry_price"])
        qty = float(row["quantity"])
        ts = row["executed_at"] or ""
        pos_key = f"{mkt}:{sym}"

        if price <= 0 or qty <= 0:
            continue

        last_prices[pos_key] = price
        # Futures are simulated fully funded rather than on margin: a contract
        # reserves its whole notional, not the exchange's initial margin. That
        # under-states leverage (the run holds fewer contracts than a real
        # margin account could), which is the safe direction for a backtest —
        # but it means these results are not a margin-accurate simulation.
        multiplier = markets.contract_multiplier(mkt, sym)
        notional_qty = qty * multiplier
        fee = _fee(price, notional_qty)
        trade_value = price * notional_qty

        if action == "buy":
            cost = trade_value + fee
            if cash < cost:
                # Insufficient cash — skip trade (mirrors live behaviour)
                continue
            cash -= cost
            if pos_key in positions and positions[pos_key].is_long:
                # Average into existing long
                pos = positions[pos_key]
                total_qty = pos.quantity + qty
                pos.avg_price = (pos.avg_price * pos.quantity + price * qty) / total_qty
                pos.quantity = total_qty
            else:
                positions[pos_key] = _Position(sym, mkt, "buy", qty, price, multiplier)
                open_timestamps[pos_key] = ts

        elif action == "sell":
            pos = positions.get(pos_key)
            if pos is None or not pos.is_long or pos.quantity < qty - 1e-12:
                continue  # no matching long position
            proceeds = trade_value - fee
            cash += proceeds
            pnl = (price - pos.avg_price) * notional_qty - fee * 2
            closed_trades.append(ClosedTrade(
                symbol=sym,
                market=mkt,
                direction="long",
                entry_price=pos.avg_price,
                exit_price=price,
                quantity=qty,
                pnl=round(pnl, 8),
                opened_at=open_timestamps.get(pos_key, ""),
                closed_at=ts,
            ))
            pos.quantity -= qty
            if pos.quantity < 1e-12:
                del positions[pos_key]
                open_timestamps.pop(pos_key, None)

        elif action == "short":
            cost = trade_value + fee
            if cash < cost:
                continue
            cash -= cost
            if pos_key in positions and not positions[pos_key].is_long:
                pos = positions[pos_key]
                total_qty = pos.quantity + qty
                pos.avg_price = (pos.avg_price * pos.quantity + price * qty) / total_qty
                pos.quantity = total_qty
            else:
                positions[pos_key] = _Position(sym, mkt, "short", qty, price, multiplier)
                open_timestamps[pos_key] = ts

        elif action == "cover":
            pos = positions.get(pos_key)
            if pos is None or pos.is_long or pos.quantity < qty - 1e-12:
                continue
            # Return original margin minus cost to buy back
            proceeds = (pos.avg_price - price) * notional_qty - fee
            cash += pos.avg_price * notional_qty + proceeds  # return margin + gain/loss
            pnl = proceeds
            closed_trades.append(ClosedTrade(
                symbol=sym,
                market=mkt,
                direction="short",
                entry_price=pos.avg_price,
                exit_price=price,
                quantity=qty,
                pnl=round(pnl, 8),
                opened_at=open_timestamps.get(pos_key, ""),
                closed_at=ts,
            ))
            pos.quantity -= qty
            if pos.quantity < 1e-12:
                del positions[pos_key]
                open_timestamps.pop(pos_key, None)

        pv = _portfolio_value(cash, positions, last_prices)
        pv_series.append(pv)
        pos_val = _position_value(positions, last_prices)
        curve.append(CurvePoint(
            timestamp=ts,
            portfolio_value=round(pv, 8),
            cash=round(cash, 8),
            position_value=round(pos_val, 8),
        ))

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    final_value = _portfolio_value(cash, positions, last_prices)
    total_return_pct = (final_value - initial_cash) / initial_cash * 100 if initial_cash > 0 else 0.0
    max_dd = _calc_max_drawdown(pv_series)

    pnls = [t.pnl for t in closed_trades]
    winning = sum(1 for p in pnls if p > 0)
    losing = sum(1 for p in pnls if p <= 0)
    trade_count = len(closed_trades)
    win_rate = winning / trade_count if trade_count > 0 else 0.0
    # Sharpe/Sortino from the daily mark-to-market equity curve (flat days
    # included, calendar-day convention → annualise with 365). The previous
    # trade-count annualisation inflated Sharpe with trade frequency.
    daily_returns = _calc_daily_returns([(p.timestamp, p.portfolio_value) for p in curve])
    sharpe = _calc_sharpe(daily_returns, periods_per_year=365)
    sortino = _calc_sortino(daily_returns, periods_per_year=365)
    calmar = _calc_calmar(total_return_pct, max_dd)
    pf = _calc_profit_factor(pnls)

    open_pos_list = [
        {
            "symbol": pos.symbol,
            "market": pos.market,
            "direction": "long" if pos.is_long else "short",
            "quantity": pos.quantity,
            "avg_entry_price": pos.avg_price,
            "last_price": last_prices.get(f"{pos.market}:{pos.symbol}", pos.avg_price),
            "unrealised_pnl": round(
                (last_prices.get(f"{pos.market}:{pos.symbol}", pos.avg_price) - pos.avg_price)
                * pos.notional_qty * (1 if pos.is_long else -1),
                8,
            ),
        }
        for pos in positions.values()
    ]

    return BacktestResult(
        initial_cash=initial_cash,
        final_value=round(final_value, 8),
        total_return_pct=round(total_return_pct, 4),
        max_drawdown_pct=round(max_dd, 4),
        trade_count=trade_count,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=round(win_rate, 4),
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        profit_factor=round(pf, 4) if pf is not None else None,
        avg_win=_calc_avg_win(pnls),
        avg_loss=_calc_avg_loss(pnls),
        closed_trades=closed_trades,
        curve=curve,
        open_positions=open_pos_list,
    )
