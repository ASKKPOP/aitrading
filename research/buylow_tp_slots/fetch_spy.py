"""SPY daily (benchmark only, not in the strategy universe) -> data/bench_SPY_1d.json."""
import json, os, urllib.parse, urllib.request
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
end = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
u = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?" + urllib.parse.urlencode(
    {"period1": int(datetime(2016, 1, 1, tzinfo=timezone.utc).timestamp()), "period2": end,
     "interval": "1d", "events": "div,splits"})
res = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                                        timeout=30).read())["chart"]["result"][0]
q = res["indicators"]["quote"][0]; a = res["indicators"]["adjclose"][0]["adjclose"]
rows = [[t * 1000, q["open"][i] * a[i] / q["close"][i], 0, 0, a[i], 0]
        for i, t in enumerate(res["timestamp"]) if q["close"][i]]
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bench_SPY_1d.json"), "w"))
