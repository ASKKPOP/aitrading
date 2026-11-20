# buylow_tp_slots — 10 slots, buy low, sell at +X %, repeat (2026-11-19)

Report: `docs/reports/2026-11-19-buy-low-take-profit-slots-research.md`.
Pre-registration (+ deviations): `PREREG.md`.

Reproduce (project venv, from this folder):

    python fetch.py            # Binance spot 1h, 35 coins (public data-api.binance.vision)
    python fetch_stocks.py     # Yahoo daily, 55 US stocks
    python fetch_spy.py        # SPY benchmark only
    python run.py stock 200    # -> results_stock.json  (~4 min, 115,632 runs)
    python run.py crypto 50    # -> results_crypto.json (~9 min, 24,450 runs)
    python summarize.py stock  > summary_stock.txt
    python summarize.py crypto > summary_crypto.txt

`engine.py` is the replay; `summary_*.txt|json` are the committed outputs.
