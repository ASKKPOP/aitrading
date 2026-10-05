# Plan 32 — the trend rule on user accounts, up to real money

2026-10-05. Owner direction, in order: "real account also same"; then, asked
what that means — **real money through a broker**, the AI desk **keeps running
side by side**, the US-stock account gets it **only after a US-stock replay
passes**, **$25 risk a trade**.

Evidence for the rule itself: `research/trend_replay/` and
`docs/reports/2026-10-05-one-month-loss-analysis.md` §8.4. Nothing here claims
the rule will make money; it claims the platform should run the rule that was
tested, on the account it is pointed at.

## 0. Status: stage 1 was built and is NOT shipped

A first stage — a simulated, long-only trend "book" on the user's own account,
sharing it with the AI desk — was built the same day, with 41 tests and every
mutant killed, and reviewed twice. Both reviews returned SHIP-AFTER-FIXES. It
is parked on the local branch `trend-books-stage1-wip` and nothing from it is
on `main` or on prod.

It was stopped rather than patched a third time because the remaining findings
are one problem, not several: **on a shared account the book does not own its
rows.** A book position is a run-less row on the user's agent — the same row a
manual trade, a copy-trade fill, an automation rule and the orphan sweep all
read and write. Review 1 found the book adopting a leftover desk short and
covering it under its own order id. The fix (the book only adopts lots its own
order opened) was then broken by review 2 three ways: a manual add made the
sweep put a 5% stop on the book's position; a manual sell-and-rebuy had the
book sell the user's own lot; an un-enrol/re-enrol had it adopt a desk run's
leftover. Each has a patch, and each patch fences one more writer off a row
that was never the book's alone.

**Position taken:** the shared-account design is the wrong design, for the
simulator and more so for real money — a broker account where the desk, the
user and the module all trade the same coin has the same ownership problem
with real fills. The rule belongs on an account where every lot is the
module's. That is how it runs today (the dedicated module account), and that
model has now been through five reviews and is live.

## 1. Where things stand (verified on prod 2026-10-05)

- Both owner accounts trade the **simulated ledger**. No real-money order has
  ever been sent by anything on the platform (`broker_orders` is empty).
- `info@askkpop.com` (agent 6) has one broker link: **Coinbase, paper mode**.
  `forevery1969@gmail.com` (agent 60) has none.
- The fleet/desk engine **cannot** route real orders: `run_engine` always calls
  `execute_paper_trade`. Only automation rules go through the execution gateway
  (`automation._execute_for_account_type`: simulator | shadow | live).
- The live path has its own gates, all the owner's: a connected broker with
  credentials, the live-trading terms accepted on the Accounts page, and the
  broker on `LIVE_BROKER_ALLOWLIST` (Coinbase is not on the default list; new
  venues are capped at $1,000 an order).
- The SL/TP watcher closes positions on the ledger only. A watcher close on a
  real position would not reach the broker.
- The trend module trades one dedicated account (agent 63, $10k simulated,
  $25 risk a trade) and refuses any agent that belongs to a user.

## 2. The two replays the owner's answers required

| run | n | net | payoff | years + | max DD | permutation p | verdict |
|---|---|---|---|---|---|---|---|
| crypto long-only, daily-close exits | 66 | +107.1R | 4.22 | 6/7 | 7.9R | 0.004 | NOT FALSIFIED |
| crypto long-only, intraday module stop | 68 | +107.9R | 4.72 | 6/7 | 8.2R | 0.003 | NOT FALSIFIED |
| US stocks, megacap tech, long/short | 339 | +115.7R | 1.82 | 12/12 | 13.9R | 0.19 | INCONCLUSIVE |
| US stocks, megacap tech, long-only | 250 | +133.7R | 1.84 | 11/12 | 12.7R | 0.44 | INCONCLUSIVE |
| US stocks, Dow 30, long/short | 543 | +34.7R | 1.58 | 8/12 | 41.7R | 0.73 | INCONCLUSIVE |
| US stocks, Dow 30, long-only | 414 | +69.4R | 1.50 | 8/12 | 30.8R | 0.91 | INCONCLUSIVE |

- **Crypto long-only passes on its own** — the form a spot broker could carry.
  It is exactly the primary run's 66 long trades. Weak spots: 2025 and 2026
  are near zero (+0.6R, +0.4R), 2022 has no trade, one XRP trade is a quarter
  of the total.
- **US stocks do not pass.** Every run makes money and every run fails the
  permutation test: the same names held from random dates earn as much or
  more. That profit is the stocks drifting up, not the rule's timing. Per the
  owner's condition the US-stock account is **not** put on this rule.

## 3. Recommended path to real money: a dedicated trend account

One account per user that only the trend module trades — its own ledger, and
for real money its own broker link (or sub-account) that nothing else uses.
"Side by side with the AI desk" then holds at the level of the user, not of
the row: the desk keeps the user's main account, the rule has its own.

| stage | what runs | opened by |
|---|---|---|
| A | the module's dedicated simulated account | done (agent 63, fixed in 345b61d) |
| B | the same account in **shadow**: every order also sent to a connected broker as a dry run, drift journalled | engineering work, then the owner connects a broker link to that account |
| C | **live** on that account | owner only — see below |

What stage B/C need that does not exist yet: the module's orders routed
through the execution gateway (with the order id checked BEFORE the broker
call — a duplicate must never reach the venue); a long-only switch; exits on
the daily close only, sent by the module (no intraday stop on the row, because
the watcher's close never reaches a broker); reconciliation of the module's
state against the broker's fills; a per-account kill switch. None of this is
built. It is a piece of work with its own plan review, not a setting.

What turns real money on — each step is the owner's, and none will be done by
an engineering session: connect a live broker account and enter its API
credentials; accept the live-trading terms; put the broker on
`LIVE_BROKER_ALLOWLIST`; set that account to `live`. Until all four are true a
live order is refused with the gateway's own message, never replaced by a
simulated fill that looks real.

Gates between stages: A → B, every live-simulated entry is one the
completed-bar replay also takes that day, for at least four weeks or five
entries, whichever is later. B → C, shadow orders accepted by the venue with
no unexplained drift over the same kind of window.

## 4. Risks stated plainly

- A replay is one history. Trades cluster; the five coins are today's large
  ones; a funding/financing proxy took ~20R off.
- The rule's normal year contains a long drawdown: nine months and 20 trades'
  worth of risk in the long/short replay, a losing streak of eleven.
- Live adds what the simulator does not have: slippage on the open after a
  breakout, minimum order sizes, venue outages, and a real position if the
  platform is down at an exit.
- $25 risk on $10k is 0.25% a trade: about three positions of $300–400 each.

## 5. If the shared-account book is wanted anyway

It can be finished, and `trend-books-stage1-wip` is where it resumes. What it
still needs, from review 2: fence manual, copy-trade and automation-rule
entries off the book's symbols; treat a row the book's state holds as the
book's whatever the latest fill says; reconcile partial closes; cache the
enrolment read with a last-known-good fallback (as built, an unreadable
setting fences the five symbols for every account, enrolled or not); make
enrol/remove single operations so a stale console cannot drop a book. The
recommendation is to not spend that effort: it buys a simulated rehearsal of
a design that should not carry real money.
