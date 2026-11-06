# READ-ONLY dump, part 2 (run_events has no agent_id: join through trading_runs). SELECT only. Streams tar.gz to stdout.
import os, sys, io, tarfile, time
from urllib.parse import urlparse, unquote
import pymysql
u = urlparse(os.environ["DATABASE_URL"])
conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username or ""),
                       password=unquote(u.password or ""), database=u.path.lstrip("/"),
                       charset="utf8mb4", read_timeout=900)
cur = conn.cursor(); cur.execute("SET SESSION TRANSACTION READ ONLY")
START = "2026-09-25 00:00:00"
RUNS = "(SELECT id FROM trading_runs WHERE agent_id IN (6,60,63))"
tar = tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz")
def clean(v):
    if v is None: return "NULL"
    s = v if isinstance(v, str) else (v.isoformat() if hasattr(v, "isoformat") else str(v))
    return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")
def dump(name, sql, params=()):
    t0 = time.time()
    try:
        cur.execute(sql, params)
    except Exception as e:
        sys.stderr.write(f"{name}: FAILED {e}\n"); conn.rollback(); return
    cols = [d[0] for d in cur.description]
    buf = io.StringIO(); buf.write("\t".join(cols) + "\n"); n = 0
    while True:
        rows = cur.fetchmany(5000)
        if not rows: break
        for r in rows: buf.write("\t".join(clean(v) for v in r) + "\n"); n += 1
    data = buf.getvalue().encode(); ti = tarfile.TarInfo(name); ti.size = len(data); ti.mtime = int(time.time())
    tar.addfile(ti, io.BytesIO(data)); sys.stderr.write(f"{name}: {n} rows {time.time()-t0:.1f}s\n")
dump("event_counts.tsv", f"SELECT event_type, COUNT(*) n FROM run_events WHERE run_id IN {RUNS} AND ts >= %s GROUP BY event_type ORDER BY n DESC", (START,))
dump("events.tsv", f"SELECT e.id, r.agent_id, e.run_id, e.seq, e.event_type, e.ts, e.payload FROM run_events e JOIN trading_runs r ON r.id = e.run_id WHERE r.agent_id IN (6,60,63) AND e.ts >= %s ORDER BY e.id", (START,))
dump("llm_usage.tsv", "SELECT id,user_id,agent_id,provider,model,tier,key_source,prompt_tokens,completion_tokens,cost_usd,created_at FROM llm_usage WHERE created_at >= %s ORDER BY id", (START,))
dump("llm_daily.tsv", "SELECT DATE(created_at) d, provider, model, key_source, COUNT(*) n, SUM(cost_usd) cost FROM llm_usage WHERE created_at >= %s GROUP BY 1,2,3,4 ORDER BY 1,2,3,4", (START,))
dump("settings.tsv", "SELECT setting_key, setting_value, updated_by, updated_at FROM platform_settings")
dump("fleets.tsv", "SELECT * FROM fleets WHERE agent_id IN (6,60,63)")
dump("equity_now.tsv", "SELECT id, name, cash, starting_capital, updated_at FROM agents WHERE id IN (6,60,63)")
cur.execute("SELECT UTC_TIMESTAMP()"); sys.stderr.write(f"db clock {cur.fetchone()[0]}\n")
tar.close()
