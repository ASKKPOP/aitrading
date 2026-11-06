# READ-ONLY dump of the last-month tape. SELECT only. Streams a tar.gz to stdout.
import os, sys, io, tarfile, json, time, re
from urllib.parse import urlparse, unquote
import pymysql
u = urlparse(os.environ["DATABASE_URL"])
conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username or ""),
                       password=unquote(u.password or ""), database=u.path.lstrip("/"),
                       charset="utf8mb4", read_timeout=600, cursorclass=pymysql.cursors.Cursor)
cur = conn.cursor()
cur.execute("SET SESSION TRANSACTION READ ONLY")
START = "2026-09-25 00:00:00"     # legs before the window so open positions close properly
AG = "(6,60,63)"
tar = tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz")
def clean(v):
    if v is None: return "NULL"
    s = v if isinstance(v, str) else (v.isoformat() if hasattr(v, "isoformat") else str(v))
    return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")
def dump(name, sql, params=()):
    t0 = time.time(); cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    buf = io.StringIO(); buf.write("\t".join(cols) + "\n"); n = 0
    while True:
        rows = cur.fetchmany(5000)
        if not rows: break
        for r in rows:
            buf.write("\t".join(clean(v) for v in r) + "\n"); n += 1
    data = buf.getvalue().encode(); ti = tarfile.TarInfo(name); ti.size = len(data); ti.mtime = int(time.time())
    tar.addfile(ti, io.BytesIO(data)); sys.stderr.write(f"{name}: {n} rows {time.time()-t0:.1f}s\n")
def schema(table):
    try: dump(f"schema_{table}.tsv", f"SHOW COLUMNS FROM `{table}`")
    except Exception as e: sys.stderr.write(f"schema {table}: {e}\n")
for t in ("signals","run_events","trading_runs","agents","positions","llm_usage","platform_settings","fleets","automation_rules"):
    schema(t)
dump("agents.tsv", f"SELECT * FROM agents WHERE id IN {AG}")
dump("signals.tsv", f"SELECT id,agent_id,created_at,symbol,side,entry_price,exit_price,quantity,pnl,fee_usd,run_id,client_order_id FROM signals WHERE agent_id IN {AG} AND created_at >= %s ORDER BY id", (START,))
dump("runs.tsv", f"SELECT * FROM trading_runs WHERE agent_id IN {AG} AND (created_at >= %s OR stopped_at IS NULL OR stopped_at >= %s) ORDER BY id", (START, START))
dump("positions.tsv", f"SELECT * FROM positions WHERE agent_id IN {AG}")
dump("event_counts.tsv", f"SELECT event_type, COUNT(*) n FROM run_events WHERE agent_id IN {AG} AND ts >= %s GROUP BY event_type ORDER BY n DESC", (START,))
dump("events.tsv", f"SELECT id,agent_id,run_id,event_type,ts,payload FROM run_events WHERE agent_id IN {AG} AND ts >= %s ORDER BY id", (START,))
try:
    dump("llm_usage.tsv", "SELECT * FROM llm_usage WHERE created_at >= %s ORDER BY id", (START,))
except Exception as e:
    sys.stderr.write(f"llm_usage: {e}\n"); conn.rollback(); cur = conn.cursor()
    try: dump("llm_usage.tsv", "SELECT * FROM llm_usage WHERE ts >= %s", (START,))
    except Exception as e2: sys.stderr.write(f"llm_usage2: {e2}\n"); conn.rollback(); cur = conn.cursor()
try: dump("settings.tsv", "SELECT * FROM platform_settings")
except Exception as e: sys.stderr.write(f"settings: {e}\n"); conn.rollback(); cur = conn.cursor()
try: dump("fleets.tsv", f"SELECT * FROM fleets WHERE agent_id IN {AG}")
except Exception as e: sys.stderr.write(f"fleets: {e}\n"); conn.rollback(); cur = conn.cursor()
cur.execute("SELECT UTC_TIMESTAMP()"); sys.stderr.write(f"db clock {cur.fetchone()[0]}\n")
tar.close()
