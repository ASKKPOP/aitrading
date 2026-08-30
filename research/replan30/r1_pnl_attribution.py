#!/usr/bin/env python3
"""R1 — whole-history P&L attribution from fills_live.tsv + fills_bak.tsv + runs.tsv.

Trip = (run_id, symbol) group of fills. Entries: side in {buy, short} (pnl NULL).
Exits: side in {sell, cover} (pnl set). Agent 6's live pnl is zeroed (write defect);
its 174 fills are replaced by fills_bak.tsv rows.
Outputs r1_trips.json and prints the report tables.
"""
import csv, json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone

D = "/Users/desirey/Programming/src/ai-trade-wt-throughput/research/replan30/"

def load(fn):
    with open(D + fn) as f:
        return list(csv.DictReader(f, delimiter="\t"))

live = load("fills_live.tsv")
bak = load("fills_bak.tsv")
runs = {r["id"]: r for r in load("runs.tsv")}

fills = [r for r in live if r["agent_id"] != "6"] + bak
assert len(fills) == (len(live) - 174) + 174

def f(x):
    return None if x in ("NULL", "", None) else float(x)

# group into trips
trips = defaultdict(list)
for r in fills:
    trips[(r["run_id"], r["symbol"])].append(r)

trip_rows = []
open_only = 0
for (run_id, sym), rows in trips.items():
    rows.sort(key=lambda r: int(r["timestamp"]))
    entries = [r for r in rows if r["side"] in ("buy", "short")]
    exits = [r for r in rows if r["side"] in ("sell", "cover")]
    fees = sum(f(r["fee_usd"]) or 0 for r in rows)
    if not exits:
        open_only += 1
        continue
    pnl = sum(f(r["pnl"]) or 0 for r in exits)
    side = "long" if (entries and entries[0]["side"] == "buy") or (not entries and exits[0]["side"] == "sell") else "short"
    ent_ts = int(entries[0]["timestamp"]) if entries else int(exits[0]["timestamp"])
    exit_ts = int(exits[-1]["timestamp"])
    notional = sum((f(r["entry_price"]) or 0) * (f(r["quantity"]) or 0) for r in entries)
    market = rows[0]["market"]
    agent = rows[0]["agent_id"]
    trip_rows.append(dict(
        run_id=run_id, symbol=sym, agent=agent, market=market, side=side,
        n_entries=len(entries), n_exits=len(exits), pnl=round(pnl, 6),
        fees=round(fees, 6), notional=round(notional, 4),
        entry_ts=ent_ts, exit_ts=exit_ts, hold_s=exit_ts - ent_ts,
    ))

with open(D + "r1_trips.json", "w") as out:
    json.dump(trip_rows, out, indent=1)

def agg(rows, key=lambda t: "ALL"):
    g = defaultdict(list)
    for t in rows:
        g[key(t)].append(t)
    res = {}
    for k, ts in sorted(g.items()):
        pnls = [t["pnl"] for t in ts]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        aw = statistics.mean(wins) if wins else 0.0
        al = statistics.mean(losses) if losses else 0.0
        res[k] = dict(
            n=len(ts), pnl=round(sum(pnls), 2), fees=round(sum(t["fees"] for t in ts), 2),
            win_rate=round(len(wins) / len(ts), 3) if ts else None,
            avg_win=round(aw, 4), avg_loss=round(al, 4),
            payoff=round(aw / abs(al), 3) if al else None,
            median=round(statistics.median(pnls), 4),
        )
    return res

def show(title, res):
    print(f"\n== {title} ==")
    for k, v in res.items():
        print(f"{k:22s} n={v['n']:4d} pnl={v['pnl']:+9.2f} fees={v['fees']:7.2f} "
              f"wr={v['win_rate']} avgW={v['avg_win']:+.4f} avgL={v['avg_loss']:+.4f} "
              f"payoff={v['payoff']} med={v['median']:+.4f}")

T = trip_rows
print(f"trips={len(T)}  open-only(run,sym) groups excluded={open_only}")
show("TOTAL", agg(T))
show("PER-AGENT", agg(T, lambda t: "agent " + t["agent"]))
show("PER-MARKET", agg(T, lambda t: t["market"]))
show("PER-SIDE", agg(T, lambda t: t["side"]))
show("MARKET x SIDE", agg(T, lambda t: t["market"] + "/" + t["side"]))

def bucket(s):
    h = s / 3600
    if h < 0.25: return "a <15m"
    if h < 1: return "b 15m-1h"
    if h < 4: return "c 1-4h"
    if h < 12: return "d 4-12h"
    if h < 48: return "e 12-48h"
    return "f >48h"
show("HOLD-TIME BUCKET", agg(T, lambda t: bucket(t["hold_s"])))

sym = agg(T, lambda t: t["symbol"])
worst = sorted(sym.items(), key=lambda kv: kv[1]["pnl"])[:10]
best = sorted(sym.items(), key=lambda kv: -kv[1]["pnl"])[:5]
print("\n== WORST 10 SYMBOLS =="); [print(k, v) for k, v in worst]
print("\n== BEST 5 SYMBOLS =="); [print(k, v) for k, v in best]

# distribution shape
pnls = sorted(t["pnl"] for t in T)
tot = sum(pnls)
losses = [p for p in pnls if p < 0]
gross_loss = sum(losses)
gross_win = sum(p for p in pnls if p > 0)
loss_fees = sum(t["fees"] for t in T if t["pnl"] < 0)
all_fees = sum(t["fees"] for t in T)
q = lambda p: pnls[min(len(pnls)-1, int(p * len(pnls)))]
print(f"\n== DISTRIBUTION ==\nn={len(pnls)} total={tot:+.2f} gross_win={gross_win:+.2f} gross_loss={gross_loss:+.2f}")
print(f"quantiles p1={q(.01):+.3f} p5={q(.05):+.3f} p25={q(.25):+.3f} p50={q(.5):+.3f} p75={q(.75):+.3f} p95={q(.95):+.3f} p99={q(.99):+.3f}")
k5 = sum(sorted(losses)[:5]); k10 = sum(sorted(losses)[:10])
print(f"top5 losses={k5:+.2f} ({100*k5/gross_loss:.1f}% of gross loss); top10={k10:+.2f} ({100*k10/gross_loss:.1f}%)")
print(f"n losing trips={len(losses)}; median loss={statistics.median(losses):+.4f}")
print(f"fees on losing trips={loss_fees:.2f} ({100*loss_fees/abs(gross_loss):.1f}% of gross loss); all fees={all_fees:.2f}")

# largest contributor sensitivity
big = max(T, key=lambda t: abs(t["pnl"]))
rest = [t for t in T if t is not big]
print(f"\nlargest |pnl| trip: run {big['run_id']} {big['symbol']} agent {big['agent']} {big['side']} pnl={big['pnl']:+.2f} hold={big['hold_s']/3600:.1f}h")
print(f"total with={tot:+.2f} / without={sum(t['pnl'] for t in rest):+.2f}")
show("TOTAL (excl largest)", agg(rest))

# time-of-day / day-of-week (UTC, by entry ts)
def hr(t): return f"h{datetime.fromtimestamp(t['entry_ts'], tz=timezone.utc).hour:02d}"
def dow(t): return datetime.fromtimestamp(t['entry_ts'], tz=timezone.utc).strftime("%a")
show("DAY-OF-WEEK (UTC entry)", agg(T, dow))
h = agg(T, lambda t: f"h{datetime.fromtimestamp(t['entry_ts'], tz=timezone.utc).hour//4*4:02d}-{datetime.fromtimestamp(t['entry_ts'], tz=timezone.utc).hour//4*4+3:02d}")
show("HOUR-OF-DAY 4h blocks (UTC entry)", h)
