"""Daily US-stock bars, Yahoo chart API v8, 2016-01-01 -> last completed session.
OHLC scaled by adjclose/close (split + dividend adjusted). Universe fixed before
any result: megacap tech + Dow 30 + 2020-21 high-flyers that later fell 60-95%
and are still listed (partial survivorship control; delisted names are absent)."""
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone
U = sorted(set(["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","AMD","NFLX",
 "AMGN","AXP","BA","CAT","CRM","CSCO","CVX","DIS","GS","HD","HON","IBM","JNJ","JPM","KO",
 "MCD","MMM","MRK","NKE","PG","SHW","TRV","UNH","V","WMT",
 "PYPL","INTC","ZM","PTON","SNAP","ROKU","DOCU","PLTR","SHOP","TDOC","MRNA","CVNA",
 "COIN","RIVN","LCID","NIO","BABA","U","NET","SE"]))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
START = int(datetime(2016, 1, 1, tzinfo=timezone.utc).timestamp())
now = datetime.now(timezone.utc)
END = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
for t in U:
    path = f"{OUT}/stk_{t}_1d.json"
    if os.path.exists(path):
        continue
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?" +
           urllib.parse.urlencode({"period1": START, "period2": END, "interval": "1d", "events": "div,splits"}))
    for k in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            res = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
            break
        except Exception:
            time.sleep(3 * (k + 1)); res = None
    if not res:
        print("FAIL", t); continue
    q = res["indicators"]["quote"][0]; adj = res["indicators"]["adjclose"][0]["adjclose"]
    rows = []
    for i, ts in enumerate(res["timestamp"]):
        o, h, l, c, a = q["open"][i], q["high"][i], q["low"][i], q["close"][i], adj[i]
        if None in (o, h, l, c, a) or c <= 0:
            continue
        f = a / c
        rows.append([ts * 1000, o * f, h * f, l * f, a, 0.0])
    json.dump(rows, open(path, "w"))
    print(t, len(rows), datetime.fromtimestamp(rows[0][0] / 1000, timezone.utc).date(), flush=True)
    time.sleep(0.5)
