#!/usr/bin/env python3
"""Plan 31 — THE PAIR REPLAY: stop 0.5% x target 0.30% replayed AS A PAIR.

=========================== PRE-REGISTERED (written before any number) =========
WHY THIS EXPERIMENT EXISTS
  The deployed crypto bracket (STOP_CAP_PCT_CRYPTO=0.5 + TARGET_PSYCH_CAP
  0.30%) was never measured as a pair. The 0.30% target sweep ran against the
  THEN-EXISTING wide stops (1.5-8%); the stop-cap replay truncated losses at
  0.5% while leaving winners at their ACTUAL exits. Each half was scored
  against the other half's old value. Since the ship (2026-08-30T01:48Z) the
  desk has taken ZERO entries and 15/96 decisions say a defensible bracket
  "cannot be constructed under house limits".

H1 (the ship's implicit claim)  The pair A (stop 0.5 / target 0.30 / ratchet /
  trail) has mean net bp/trip > 0 and beats control E (authored stop, authored
  target) at 90% CI.
H0  No arm's mean net bp/trip clears zero. Geometry cannot make this book
  profitable; only an entry-side edge can.
H2  A tighter stop is monotonically better (B 0.3% > A 0.5% > C 1.0%).
H3  Removing the take-profit entirely (D) beats every capped-target arm,
  because the trail/ratchet are the real winner-capping mechanism and a
  0.30% TP only truncates the right tail that pays for the stops.

FALSIFIERS (any one kills the arm it names)
  F-A   A's mean net bp/trip <= 0, or its 90% CI overlaps E's mean  -> H1 dead.
  F-H2  B does not beat A, or C beats B                             -> H2 dead.
  F-H3  D does not beat A                                            -> H3 dead.
  F-N   Stripping the single largest |net $| contributor flips the sign of any
        headline mean -> that row is reported INCONCLUSIVE (owner rule sec.6).

DECISION RULE (fixed before looking)
  A is VINDICATED only if mean net bp/trip > 0 AND better than E at 90% CI.
  If another arm beats A materially, name it and its margin.
  If ALL arms are negative, say so plainly: geometry is not the lever.

METHOD
  n = the 68 crypto trips in r1_trips.json (2026-08-12..08-29), replayed from
  each trip's FIRST entry fill (real fill price + quantity from the signals
  tape) forward over OKX 1m candles. One position per trip; adds are NOT
  replayed (under a 0.5% stop most adds could never have happened - stated as
  a limitation, and the actual tape is reported beside the arms).

  Every arm shares: entry, path, horizon, cost model, and the FULL production
  exit stack read out of the code, not assumed:
    - stop_loss / take_profit  : SL/TP watcher (risk_engine.run_sltp_watcher_tick),
                                 stop checked BEFORE target, on the POLLED mark
                                 (POSITION_REFRESH_INTERVAL=60 -> 1m closes).
    - max_loss_usd / profit_target_usd : each run's OWN stop_conditions_json.
    - trailing_lock            : each run's OWN trail config
                                 (activate_usd, giveback_frac, tighten_usd,
                                 tighten_giveback_frac), exactly
                                 run_engine._trailing_lock_hit, including the
                                 +exit_fee term priced at the flat
                                 BREAKEVEN_FEE_RATE 0.001 the code actually uses.
    - breakeven ratchet        : run_engine._breakeven_floor_hit with the
                                 deployed crypto arm
                                 fee_rate(crypto)=0.00045 x 2 x
                                 BREAKEVEN_ARM_FEES(1.78) = 16.02bp of notional,
                                 fee floor 9bp, RATCHET_LOCK_FRAC=0.5.
    - at_time / horizon        : min(entry+24h, the run's own at_time).
  PEAK LAG: production stamps peak_pnl_usd AFTER _evaluate_stop in the same
  control pass (run_engine._control_active), so trail/ratchet are evaluated
  against the PREVIOUS bar's peak. Modelled.

  COSTS: net = gross - 9bp round-trip fees - 6.8bp measured slip = 15.8bp,
  the low end of Plan 31 A5's 15.8-22.6bp band. Sensitivity at 22.6bp.

  ARMS
    A  stop 0.5%, TP 0.30%   (the deployed pair)
    B  stop 0.3%, TP 0.30%   (the D7 arm that was silently dropped)
    C  stop 1.0%, TP 0.30%
    D  stop 0.5%, NO TP      (pure trail - the trend pole)
    E  authored stop, authored target (pre-ship geometry) - the control
    Z  ratchet+trail OFF, arm A geometry (isolates the ratchet's contribution)

  BASIS TRAP (memory: ratchet-lock-cadence-replay-verdict): the fills came
  from the prod feed; the paths here are OKX spot 1m. Levels 0.3-0.5% wide are
  within a percent or two of feed disagreement, so per-trip attribution is
  noisier than the aggregate. Reported, not hidden.
================================================================================
"""
from __future__ import annotations

import csv
import json
import os
import random
import statistics
from collections import Counter, defaultdict

D = os.path.dirname(os.path.abspath(__file__))
CD = os.path.join(D, "candles")

# ── production constants, read out of the code (see docstring) ───────────────
CRYPTO_FEE = 0.00045              # fees.fee_rate("crypto"), one leg
ARM_FEES = 1.78                   # prod BREAKEVEN_ARM_FEES
RATCHET_ARM = CRYPTO_FEE * 2 * ARM_FEES          # 0.0016023 of notional
RATCHET_FEE_FLOOR = CRYPTO_FEE * 2               # 0.0009
RATCHET_LOCK_FRAC = 0.5           # prod default
FLAT_BE_RATE = 0.001              # BREAKEVEN_FEE_RATE default used by the
                                  # trail's +exit_fee term in _evaluate_stop
HORIZON_S = 24 * 3600
FEE_RT = 0.0009                   # 9bp round trip, real
SLIP_RT = 0.00068                 # 6.8bp measured
COST = FEE_RT + SLIP_RT           # 15.8bp
COST_HIGH = FEE_RT + 2 * 0.00068  # 22.6bp sensitivity

SEED = 20260830


def f(x):
    return None if x in ("NULL", "", None) else float(x)


def load_tsv(fn):
    with open(os.path.join(D, fn)) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def iso_ep(s):
    from datetime import datetime, timezone
    if not s:
        return None
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc).timestamp())


# ── build the trip inputs ────────────────────────────────────────────────────
def build_trips():
    trips = json.load(open(os.path.join(D, "r1_trips.json")))
    crypto = [t for t in trips if t["market"] == "crypto"]

    live = load_tsv("fills_live.tsv")
    bak = load_tsv("fills_bak.tsv")
    fills = [r for r in live if r["agent_id"] != "6"] + bak
    by_run = defaultdict(list)
    for r in fills:
        by_run[(r["run_id"], r["symbol"])].append(r)

    cfgs = {r["id"]: r for r in load_tsv("crypto_runs_cfg.tsv")}
    events = load_tsv("crypto_run_events.tsv")

    # entry cycle -> authored bracket, from the journalled order_params events
    authored = {}
    entry_cycle = {}
    for r in events:
        if r["event_type"] != "trade":
            continue
        try:
            p = json.loads(r["payload"])
        except Exception:                                   # noqa: BLE001
            continue
        if p.get("side") not in ("buy", "short"):
            continue
        coid = str(p.get("client_order_id") or "")
        cyc = None
        if ":cyc:" in coid:
            try:
                cyc = int(coid.split(":cyc:")[1])
            except ValueError:
                cyc = None
        rid = r["run_id"]
        if rid not in entry_cycle and cyc is not None:
            entry_cycle[rid] = cyc
    for r in events:
        if r["event_type"] != "order_params":
            continue
        try:
            p = json.loads(r["payload"])
        except Exception:                                   # noqa: BLE001
            continue
        rid = r["run_id"]
        if entry_cycle.get(rid) != p.get("cycle"):
            continue
        pr = p.get("params") or {}
        if pr.get("stop_pct") is not None and pr.get("target_pct") is not None:
            authored[rid] = (float(pr["stop_pct"]) / 100.0,
                             float(pr["target_pct"]) / 100.0)

    out = []
    for t in crypto:
        rid, sym = t["run_id"], t["symbol"]
        rows = sorted(by_run[(rid, sym)], key=lambda r: int(r["timestamp"]))
        ent = [r for r in rows if r["side"] in ("buy", "short")]
        if not ent:
            continue
        e0 = ent[0]
        p0, q0 = f(e0["entry_price"]), f(e0["quantity"])
        if not p0 or not q0:
            continue
        notional = p0 * q0
        cfg = cfgs.get(rid, {})
        sc = json.loads(cfg.get("sc") or "{}")
        trail = sc.get("trail") or {}
        out.append(dict(
            run_id=rid, symbol=sym, agent=t["agent"], side=t["side"],
            t0=int(e0["timestamp"]), entry=p0, qty=q0, notional=notional,
            n_entries=t["n_entries"], actual_pnl=t["pnl"],
            actual_fees=t["fees"], actual_hold_s=t["hold_s"],
            max_loss=(float(sc["max_loss_usd"]) / notional
                      if sc.get("max_loss_usd") else None),
            profit_target=(float(sc["profit_target_usd"]) / notional
                           if sc.get("profit_target_usd") else None),
            trail_activate=(float(trail["activate_usd"]) / notional
                            if trail.get("activate_usd") else None),
            trail_give=float(trail.get("giveback_frac") or 0),
            trail_tighten=(float(trail["tighten_usd"]) / notional
                           if trail.get("tighten_usd") else None),
            trail_tighten_give=float(trail.get("tighten_giveback_frac") or 0),
            at_time=iso_ep(sc.get("at_time")),
            authored=authored.get(rid),
        ))
    return out


# ── candle access ────────────────────────────────────────────────────────────
_CACHE = {}


def candles(symbol):
    if symbol not in _CACHE:
        path = os.path.join(CD, f"okx1m_{symbol[:-4]}-USDT.json")
        _CACHE[symbol] = json.load(open(path)) if os.path.exists(path) else []
    return _CACHE[symbol]


# ── the walker ───────────────────────────────────────────────────────────────
def walk(trip, stop_pct, target_pct, use_ratchet=True, use_trail=True,
         bar_s=60, intrabar=False):
    """Replay one trip. Returns (gross_frac, exit_author, hold_s) or None.

    gross_frac is the signed price move IN THE TRADE'S FAVOUR as a fraction of
    entry (long: (p-p0)/p0, short: (p0-p)/p0). Costs are applied by the caller.
    """
    cs = candles(trip["symbol"])
    if not cs:
        return None
    t0, p0 = trip["t0"], trip["entry"]
    sgn = 1.0 if trip["side"] == "long" else -1.0
    t_end = t0 + HORIZON_S
    if trip["at_time"]:
        t_end = min(t_end, trip["at_time"])
    if t_end <= t0:
        t_end = t0 + HORIZON_S

    def g_of(price):
        return sgn * (price - p0) / p0

    peak = 0.0                    # previous-bar peak (production lag)
    last_g = 0.0
    last_eval = t0
    for c in cs:
        ts, hi, lo, close = c[0], c[2], c[3], c[4]
        if ts <= t0:
            continue
        if ts > t_end:
            break
        # mark cadence: only bars on the refresh grid are seen
        if ts - last_eval < bar_s:
            continue
        last_eval = ts
        g = g_of(close)
        if intrabar:
            g_lo = g_of(lo if sgn > 0 else hi)   # worst
            g_hi = g_of(hi if sgn > 0 else lo)   # best
        else:
            g_lo = g_hi = g

        # Exits FILL AT THE POLLED MARK, not at the level: the watcher calls
        # execute_paper_trade(..., price=pos["current_price"]) and the run
        # flatten uses the same mark. On closes-only that is the bar close
        # (overrun is real and is charged). Under `intrabar` the level is
        # touched inside the bar and fills at the level (optimistic bound).
        # 1. SL/TP watcher — stop checked BEFORE target (risk_engine order)
        if stop_pct is not None and g_lo <= -stop_pct:
            return (-stop_pct if intrabar else g), "stop", ts - t0
        if target_pct is not None and g_hi >= target_pct:
            return (target_pct if intrabar else g), "target", ts - t0
        # 2. run-level P&L stops (max_loss wins ties)
        ml = None if trip["max_loss"] is None else -(trip["max_loss"]) + CRYPTO_FEE
        if ml is not None and g_lo <= ml:
            return (ml if intrabar else g), "max_loss", ts - t0
        pt = None if trip["profit_target"] is None \
            else trip["profit_target"] + CRYPTO_FEE
        if pt is not None and g_hi >= pt:
            return (pt if intrabar else g), "profit_target", ts - t0
        # 3. trailing lock (the run's own config), peak lagged one bar
        if use_trail and trip["trail_activate"] and peak >= trip["trail_activate"]:
            gb = trip["trail_give"]
            if trip["trail_tighten"] and peak >= trip["trail_tighten"] \
                    and 0 < trip["trail_tighten_give"] < gb:
                gb = trip["trail_tighten_give"]
            if 0 < gb < 1:
                lock = (1 - gb) * peak + FLAT_BE_RATE
                if g <= lock:
                    return g, "trail", ts - t0
        # 4. breakeven ratchet
        if use_ratchet and peak >= RATCHET_ARM:
            floor = RATCHET_FEE_FLOOR + RATCHET_LOCK_FRAC * (peak - RATCHET_FEE_FLOOR)
            if g <= floor:
                return g, "ratchet", ts - t0
        # peak_pnl_usd is stamped from the POLLED mark, after _evaluate_stop
        peak = max(peak, g)
        last_g = g
    return last_g, "horizon", t_end - t0


ARMS = {
    "A deployed 0.5/0.3": dict(stop=0.005, target=0.003),
    "B 0.3/0.3":          dict(stop=0.003, target=0.003),
    "C 1.0/0.3":          dict(stop=0.010, target=0.003),
    "D 0.5/no-TP":        dict(stop=0.005, target=None),
    "E control authored": dict(stop="auth", target="auth"),
    "Z A, ratchet+trail off": dict(stop=0.005, target=0.003,
                                   use_ratchet=False, use_trail=False),
}


def basis_bp(trip):
    """|OKX close at/just before the fill ts - recorded fill price| in bp.
    The prod fill feed and OKX spot are different books; at a 30bp target this
    disagreement is not a rounding detail (memory: ratchet-lock-cadence-replay
    -verdict). Reported, and neutralised by the `reanchor` sensitivity."""
    cs = candles(trip["symbol"])
    last = None
    for ts, o, h, l, c in cs:
        if ts <= trip["t0"]:
            last = c
        else:
            break
    if last is None:
        return None
    return abs(last - trip["entry"]) / trip["entry"] * 1e4


def run_arm(trips, spec, cost=COST, bar_s=60, intrabar=False,
            reanchor=False, max_basis_bp=None):
    rows = []
    for t in trips:
        if max_basis_bp is not None:
            b = basis_bp(t)
            if b is None or b > max_basis_bp:
                continue
        if reanchor:
            cs = candles(t["symbol"])
            last = None
            for ts, o, h, l, c in cs:
                if ts <= t["t0"]:
                    last = c
                else:
                    break
            if last:
                t = dict(t, entry=last, notional=last * t["qty"])
        stop, target = spec["stop"], spec["target"]
        if stop == "auth":
            if not t["authored"]:
                stop, target = 0.05, 0.10      # the deterministic gate default
            else:
                stop, target = t["authored"]
        r = walk(t, stop, target,
                 use_ratchet=spec.get("use_ratchet", True),
                 use_trail=spec.get("use_trail", True),
                 bar_s=bar_s, intrabar=intrabar)
        if r is None:
            continue
        gross, author, hold = r
        net = gross - cost
        rows.append(dict(run_id=t["run_id"], symbol=t["symbol"],
                         side=t["side"], notional=t["notional"],
                         gross_bp=gross * 1e4, net_bp=net * 1e4,
                         net_usd=net * t["notional"], author=author,
                         hold_s=hold))
    return rows


def boot_ci(vals, iters=10000, lo=0.05, hi=0.95, seed=SEED):
    if len(vals) < 3:
        return (None, None)
    rnd = random.Random(seed)
    n = len(vals)
    means = []
    for _ in range(iters):
        means.append(sum(vals[rnd.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (means[int(lo * iters)], means[int(hi * iters)])


def summarize(rows, label):
    if not rows:
        return None
    net = [r["net_bp"] for r in rows]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x < 0]
    aw = statistics.mean(wins) if wins else 0.0
    al = statistics.mean(losses) if losses else 0.0
    lo, hi = boot_ci(net)
    # ex-largest-|net_usd| contributor
    big = max(rows, key=lambda r: abs(r["net_usd"]))
    rest = [r for r in rows if r is not big]
    net_x = [r["net_bp"] for r in rest]
    lo_x, hi_x = boot_ci(net_x)
    return dict(
        arm=label, n=len(rows),
        mean_bp=round(statistics.mean(net), 3),
        median_bp=round(statistics.median(net), 3),
        ci90=[None if lo is None else round(lo, 3),
              None if hi is None else round(hi, 3)],
        win_rate=round(len(wins) / len(rows), 3),
        avg_win_bp=round(aw, 2), avg_loss_bp=round(al, 2),
        payoff=round(aw / abs(al), 3) if al else None,
        total_usd=round(sum(r["net_usd"] for r in rows), 2),
        authors=dict(Counter(r["author"] for r in rows).most_common()),
        median_hold_min=round(statistics.median(r["hold_s"] for r in rows) / 60, 1),
        ex_largest=dict(
            dropped=f"{big['symbol']} run {big['run_id']} "
                    f"({big['net_usd']:+.2f})",
            mean_bp=round(statistics.mean(net_x), 3),
            median_bp=round(statistics.median(net_x), 3),
            ci90=[None if lo_x is None else round(lo_x, 3),
                  None if hi_x is None else round(hi_x, 3)],
            total_usd=round(sum(r["net_usd"] for r in rest), 2),
            sign_flip=(statistics.mean(net) > 0) != (statistics.mean(net_x) > 0),
        ),
    )


def breakeven_wr(stop_bp, target_bp, cost_bp=COST * 1e4):
    """Breakeven win rate for a hard stop/target pair, net of cost."""
    w = target_bp - cost_bp
    l = stop_bp + cost_bp
    if w <= 0:
        return None
    return l / (w + l)


def main():
    trips = build_trips()
    print(f"trips built: {len(trips)}")
    have = [t for t in trips if candles(t["symbol"])]
    print(f"with candles: {len(have)}  "
          f"(authored bracket known: {sum(1 for t in have if t['authored'])})")

    results = {"pre_registered": __doc__.split("====")[1],
               "constants": dict(ratchet_arm_bp=RATCHET_ARM * 1e4,
                                 ratchet_fee_floor_bp=RATCHET_FEE_FLOOR * 1e4,
                                 ratchet_lock_frac=RATCHET_LOCK_FRAC,
                                 cost_bp=COST * 1e4,
                                 cost_bp_high=COST_HIGH * 1e4,
                                 horizon_h=HORIZON_S / 3600),
               "n_trips": len(have), "arms": [], "sensitivity": {}}

    per_arm_rows = {}
    for label, spec in ARMS.items():
        rows = run_arm(have, spec)
        per_arm_rows[label] = rows
        s = summarize(rows, label)
        results["arms"].append(s)
        print(f"\n{label}: {json.dumps(s, indent=1)}")

    # actual tape, for reference
    act = [dict(net_usd=t["actual_pnl"] - t["notional"] * CRYPTO_FEE,
                net_bp=1e4 * (t["actual_pnl"] - t["notional"] * CRYPTO_FEE)
                / t["notional"], symbol=t["symbol"], run_id=t["run_id"],
                author="actual", hold_s=t["actual_hold_s"],
                notional=t["notional"]) for t in have]
    results["actual_tape"] = summarize(act, "ACTUAL (recorded pnl - entry fee)")
    print(f"\nACTUAL: {json.dumps(results['actual_tape'], indent=1)}")

    # ── sensitivities ────────────────────────────────────────────────────
    sens = results["sensitivity"]
    results["feed_basis_bp"] = sorted(round(basis_bp(t), 2) for t in have
                                      if basis_bp(t) is not None)
    for name, kw in (("cost_22.6bp", dict(cost=COST_HIGH)),
                     ("intrabar_extremes", dict(intrabar=True)),
                     ("marks_300s", dict(bar_s=300)),
                     ("entry_reanchored_to_okx", dict(reanchor=True)),
                     ("basis_le_20bp_only", dict(max_basis_bp=20.0)),
                     ("reanchored_and_intrabar", dict(reanchor=True,
                                                      intrabar=True))):
        sens[name] = {}
        for label, spec in ARMS.items():
            r = summarize(run_arm(have, spec, **kw), label)
            sens[name][label] = dict(n=r["n"], mean_bp=r["mean_bp"],
                                     ci90=r["ci90"],
                                     total_usd=r["total_usd"],
                                     payoff=r["payoff"],
                                     win_rate=r["win_rate"],
                                     authors=r["authors"],
                                     ex_largest_mean_bp=r["ex_largest"]["mean_bp"],
                                     sign_flip=r["ex_largest"]["sign_flip"])

    # ── paired A-vs-E difference, bootstrapped on the same trips ─────────
    a = {r["run_id"]: r["net_bp"] for r in per_arm_rows["A deployed 0.5/0.3"]}
    e = {r["run_id"]: r["net_bp"] for r in per_arm_rows["E control authored"]}
    common = sorted(set(a) & set(e))
    diffs = [a[k] - e[k] for k in common]
    lo, hi = boot_ci(diffs)
    results["A_minus_E_paired"] = dict(
        n=len(diffs), mean_bp=round(statistics.mean(diffs), 3),
        ci90=[round(lo, 3), round(hi, 3)],
        beats_E_at_90=(lo is not None and lo > 0))
    for other in ("B 0.3/0.3", "C 1.0/0.3", "D 0.5/no-TP"):
        o = {r["run_id"]: r["net_bp"] for r in per_arm_rows[other]}
        cm = sorted(set(a) & set(o))
        d = [o[k] - a[k] for k in cm]
        lo2, hi2 = boot_ci(d)
        results[f"{other}_minus_A_paired"] = dict(
            n=len(d), mean_bp=round(statistics.mean(d), 3),
            ci90=[round(lo2, 3), round(hi2, 3)],
            beats_A_at_90=(lo2 is not None and lo2 > 0))

    # ── the desk-refusal arithmetic ──────────────────────────────────────
    a_rows = per_arm_rows["A deployed 0.5/0.3"]
    ratchet_exits = [r["gross_bp"] for r in a_rows if r["author"] == "ratchet"]
    results["desk_refusal"] = dict(
        breakeven_wr_hard_TP=round(breakeven_wr(50.0, 30.0), 4),
        breakeven_wr_hard_TP_zero_cost=round(breakeven_wr(50.0, 30.0, 0.0), 4),
        measured_trip_win_rate=0.427,
        note_ratchet_median_gross_bp=(round(statistics.median(ratchet_exits), 2)
                                      if ratchet_exits else None),
        realised_avg_win_bp=round(
            statistics.mean([r["net_bp"] for r in a_rows if r["net_bp"] > 0])
            if any(r["net_bp"] > 0 for r in a_rows) else 0.0, 2),
        realised_avg_loss_bp=round(
            statistics.mean([r["net_bp"] for r in a_rows if r["net_bp"] < 0])
            if any(r["net_bp"] < 0 for r in a_rows) else 0.0, 2),
    )
    ew = results["desk_refusal"]["realised_avg_win_bp"]
    el = abs(results["desk_refusal"]["realised_avg_loss_bp"])
    results["desk_refusal"]["breakeven_wr_effective"] = (
        round(el / (ew + el), 4) if (ew + el) else None)

    # The two readings the brief asked for, plus what the replay ACHIEVES.
    def be_and_achieved(rows):
        w = [r["net_bp"] for r in rows if r["net_bp"] > 0]
        l = [r["net_bp"] for r in rows if r["net_bp"] < 0]
        aw = statistics.mean(w) if w else 0.0
        al = abs(statistics.mean(l)) if l else 0.0
        return dict(breakeven_wr=round(al / (aw + al), 4) if (aw + al) else None,
                    achieved_wr=round(len(w) / len(rows), 4),
                    avg_win_bp=round(aw, 2), avg_loss_bp=round(-al, 2))
    results["desk_refusal"]["TP_hard_cap_theory"] = dict(
        breakeven_wr=round(breakeven_wr(50.0, 30.0), 4),
        note="stop 50bp / target 30bp / cost 15.8bp, as a pure binary bracket")
    results["desk_refusal"]["TP_hard_cap_replayed_armA"] = be_and_achieved(a_rows)
    results["desk_refusal"]["TP_cleared_post_arm_replayed_armD"] = \
        be_and_achieved(per_arm_rows["D 0.5/no-TP"])
    results["desk_refusal"]["reanchored_armA"] = be_and_achieved(
        run_arm(have, ARMS["A deployed 0.5/0.3"], reanchor=True))
    results["desk_refusal"]["max_stop_that_breaks_even_at_measured_wr"] = {
        "target_30bp_cost_15.8bp": round(0.427 * (30 - 15.8) / 0.573 - 15.8, 2),
        "target_30bp_cost_0bp": round(0.427 * 30 / 0.573, 2),
        "note": "negative = NO positive stop can break even at a 42.7% win rate",
    }

    results["per_trip"] = {k: v for k, v in per_arm_rows.items()}

    out = os.path.join(D, "pair_replay_results_20260830.json")
    json.dump(results, open(out, "w"), indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
