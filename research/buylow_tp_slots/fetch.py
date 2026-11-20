"""Fetch Binance spot 1h klines (public data-api.binance.vision) 2020-01-01 -> now.
Universe fixed BEFORE looking at any result: 5 majors + 30 liquid 2020-22 alts,
deliberately including names that later fell 80-99% (APE, AXS, SAND, MANA, GALA,
FLOW, ICP, FIL, DYDX, CHZ, ENJ, ALGO, EOS...). Survivorship caveat: coins that
were DELISTED (LUNA, FTT on some venues) cannot be fetched and are absent."""
import json, os, time, urllib.request
UNIV = ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","AVAX","DOT","LINK","LTC","TRX",
        "ATOM","NEAR","UNI","FIL","ICP","AAVE","ALGO","EOS","XLM","ETC","SAND","MANA",
        "AXS","GALA","APE","CHZ","ENJ","FLOW","DYDX","CRV","SUSHI","1INCH","ZEC"]
START = 1577836800000  # 2020-01-01
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
def get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 + 3 * k)
    raise RuntimeError(url)
def one(c):
    path = f"{OUT}/{c}USDT_1h.json"
    if os.path.exists(path):
        return
    rows, t = [], START
    while True:
        d = get(f"https://data-api.binance.vision/api/v3/klines?symbol={c}USDT&interval=1h&startTime={t}&limit=1000")
        if not d:
            break
        rows += [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7])] for r in d]
        t = d[-1][0] + 3600_000
        if len(d) < 1000:
            break
    rows = [r for r in rows if r[0] + 3600_000 <= int(time.time() * 1000)]  # completed bars only
    json.dump(rows, open(path, "w"))
    print(c, len(rows), time.strftime("%Y-%m-%d", time.gmtime(rows[0][0] / 1000)) if rows else "-", flush=True)

from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(8) as ex:
    list(ex.map(one, UNIV))
