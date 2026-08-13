# Automation monitoring — 2026-08-13 (overnight into the first full us-stock session)

Session context: seven deploys landed between 2026-08-12 20:30Z and 2026-08-13 06:11Z
(#393 #394 #396 #397 #400 #403 #404 #405). This note records the findings in
retrieval-ready form — each heading is one lesson the desk can recall.

## The finding — a "flat" brief while your own history says you traded is SUSPECT (SOL −$69.56)

Run 1099 held a losing SOL short and was told "Position: 0 units (flat)" for four
hours because a rounded-to-zero ghost row shadowed the real book. Believing it, the
desk re-opened its short six times — $9,189 stacked against a $1,580 budget — and the
max-loss rail flattened all six lots for −$69.56 realized. The platform defect is
fixed (one book per run, aggregated reads), but the desk-side lesson stands: when the
position brief reads flat while your own recent decisions say you sold or shorted,
treat the flat read as suspect and do NOT size a fresh entry as if starting clean.
Repeated identical entries on an unchanged thesis are adds, and adds into a losing
position must be earned by the position working — never by the book looking empty.

## us-stock: the open IS the trade — a plan acted on at the bell beats the same plan 30 minutes late

Most participants transact at the US open; the first 30 minutes carry the day's
highest volume and range, and gap continuations or fades resolve there at the best
liquidity of the session. The scheduler now fires every us-stock desk within a minute
of 13:30 UTC with the pre-open analysis already done. When holding a plan into the
open: act on it in the opening window rather than waiting for confirmation that
arrives after the move; when flat at the bell on a mover thesis, the first orderly
pullback that holds is the entry, taken on resumption — chasing the first vertical
minutes buys someone's exit.

## us-stock: read the 2-day mover footprint before any entry or exit (mom_2d_pct, volume_ratio)

Your thesis carries mom_2d_pct (the symbol's 2-day move) and volume_ratio (latest
volume vs its own normal) — the reason the symbol was selected. A large 2-day move
WITH elevated volume is an institutional footprint: size that cannot enter or exit in
one print, so the flow tends to continue across days — trade in its direction and do
not fade it by reflex. A large move on thin volume is a drift nobody funded: no
continuation bet. High volume with a NARROW range is absorption — direction undecided,
stand aside until the range breaks. Two consecutive outsized up-days mean the next
vertical push is late: wait for the pullback. If price falls back through the level
where the big volume appeared, the footprint failed — exit the idea, do not argue.

## us-stock and everywhere: a young position moving against you INSIDE the ordinary day is noise, not evidence

The book's largest measured losses are full exits made minutes after entry on moves
smaller than the symbol's ordinary daily range: KAITO was fully covered 30 minutes
after entry on a −0.9% wiggle for −$10.14 and the tape then went the thesis's way.
When the position is young and the adverse move is inside one ordinary day, a full
close realizes fees on a wiggle. If exiting anyway, state why a FULL close beats a
HALF reduce; when your component scores disagree with your headline confidence,
trust the scores. Holding through noise is not stubbornness when the thesis is
intact — dumping on noise is the measured leak.

## Holding against your own reading is the invalidation signal (ZEC −$5.55)

A short was held for three consecutive cycles while the desk's own report read
"technical buy, news 10 bullish vs 1 bearish" — the position bled to a forced retire.
When the technical signal and the news balance BOTH oppose the held side for two
cycles running, a silent hold is not an available action: reduce, or explicitly
re-underwrite the thesis with fresh evidence in the report. At three straight
contradicted cycles the platform reduces half by itself; being ahead of that rail is
the desk's job.

## Sleepy symbols lose by idling; movers earn their slot (GLD −$300/trade class)

Trend-blend picks with no short-term range (GLD, SLV-class names) burned twelve
30-minute cycles holding, idle-retired without a trade, and GLD's account history ran
−$300.66 per closed trade over seven trades before the expectancy gate blocked it.
A 30-minute desk needs symbols with real 2-day range: prefer the mover the selection
gave you, and when a symbol produces nothing but holds for a session, the slot is
better handed back early than defended out of habit.

## Scaled-out winners must CLOSE their tail, not halve it forever

Four correct "cover half" decisions on a winning short decayed the book to a $4.45
remainder that could never pay its own round trip, then consumed desk cycles
babysitting dust. When a reduce would leave a remainder below the manage-worthy
floor (about $25), take the full close — the compiler now enforces this, but the
desk deciding it first is always cleaner: bank the tail with the second-to-last
reduce instead of leaving a crumb.

## Fleet mechanics verified live this session (for the operator, not the desk)

Replenish now holds the defined slot count at all times (market clock never blocks a
build; only AI verdicts — fee, expectancy, swing-history, funding — leave a slot
empty). Research supply scales to fleet demand per market (cap 40). The us-stock
survivor pool widened from 4 to 24 theses in one batch and fleet 31 grew 2→16 slots
in a day; fleet 32 recycled its SOL slot within the hour of the max-loss stop. The
liquidation-defense daemon, orphan sweep (ghost cleanup verified: 1 deleted), young-
dump flag, contradiction rail, dust rail, and bell-aligned scheduling are all live
and journalled — measure them in run_events before tuning anything.
