# MySQL cutover runbook (sooppiy.com)

**Status:** code + schema ready and validated on real MySQL 8.4; remote cutover **not yet executed** (needs `fly` access / the remote MySQL DSN, which the code environment did not have).

**Date:** 2026-07-17

## What changed and why

The app was SQLite-only in practice. `main.py:61` builds the schema via `alembic
upgrade head` when `DATABASE_URL` is set, but the alembic chain had never run on a
real MySQL — it failed on the first table. This work made the whole MySQL path
actually functional:

- **`0017_missing_init_tables.py`** — the 12 tables (+13 columns) `init_database()`
  created but alembic lacked. Schema now has full init↔alembic parity
  (verified: 73/73 tables, 0 column mismatches vs a fresh SQLite `init_database()`).
- **`0001`–`0016` DDL fixes** — 86 `TEXT`→`VARCHAR` on indexed/unique/keyed columns,
  removed ~71 `CREATE INDEX IF NOT EXISTS` (MariaDB-only), literal `TEXT` defaults →
  `VARCHAR`, backticked reserved-word columns, `sa.Text`→`sa.String` on keyed columns.
- **`database.py` adapter** — now backticks reserved-word columns (`read`, `rank`,
  `signal`) in runtime SQL and translates `INSERT ... DEFAULT VALUES` → `() VALUES ()`.
- **`config_profiles.py`** — upsert emits `ON DUPLICATE KEY UPDATE` on MySQL,
  `ON CONFLICT` on SQLite.
- **`migrate_sqlite_to_mysql.py`** — one-off data copy (IDs preserved, row counts verified).

The SQLite path is unchanged — 1118 tests still pass on SQLite.

## Requirements for the target MySQL

- **MySQL 8.0.13 or newer** (the schema uses expression defaults on TEXT columns,
  e.g. `created_at ... DEFAULT (DATE_FORMAT(...))` and `positions_json DEFAULT ('[]')`).
- Database created with **`CHARACTER SET utf8mb4`**.
- A user with full DDL+DML on that database.

## Cutover steps

> Do this in a **maintenance window / write freeze**. Between copying the SQLite
> data and flipping `DATABASE_URL`, any writes that hit SQLite would be lost. Stop
> the `worker` process and put the API in read-only (or brief downtime) first.

1. **Provision** managed MySQL 8.0.13+ and create the database:
   ```sql
   CREATE DATABASE sooppiy CHARACTER SET utf8mb4;
   CREATE USER 'sooppiy'@'%' IDENTIFIED BY '<pw>';
   GRANT ALL PRIVILEGES ON sooppiy.* TO 'sooppiy'@'%';
   ```

2. **Pull the current production SQLite** off the Fly volume (the live data source):
   ```bash
   fly ssh sftp get /app/service/server/data/sooppiy.db ./prod-sooppiy.db -a sooppiy
   ```
   ⚠️ Confirm this file is actually the live DB first — `fly.toml`'s SQLite volume
   mount is currently **commented out**. If it is not mounted, production SQLite is
   ephemeral (resets on redeploy); verify where prod data really lives before trusting it.

3. **Build the schema** on the new MySQL (from a machine that can reach it):
   ```bash
   export DATABASE_URL='mysql+pymysql://sooppiy:<pw>@<host>:3306/sooppiy'
   cd service/server && python -m alembic upgrade head
   ```

4. **Copy the data**:
   ```bash
   DATABASE_URL='mysql+pymysql://sooppiy:<pw>@<host>:3306/sooppiy' \
   DB_PATH='./prod-sooppiy.db' \
   python service/server/migrate_sqlite_to_mysql.py
   # aborts if any destination table is non-empty; prints per-table row counts and verifies them
   ```

5. **Set the Fly secret and redeploy**:
   ```bash
   fly secrets set DATABASE_URL='mysql+pymysql://sooppiy:<pw>@<host>:3306/sooppiy' -a sooppiy
   fly deploy -a sooppiy
   ```
   On boot the app runs `alembic upgrade head` (no-op — already at head) and logs
   `Database ready: backend=mysql`.

6. **Verify**:
   ```bash
   fly logs -a sooppiy | grep 'Database ready'      # backend=mysql
   curl -s https://sooppiy.com/health                # 200
   curl -s https://sooppiy.com/api/claw/agents/count # sane count
   ```
   Exercise a signal-feed read, an agent-message read (`read` column), and a
   config-profile save (the upsert path).

## Rollback

`fly secrets unset DATABASE_URL -a sooppiy && fly deploy -a sooppiy` → the app falls
back to SQLite. **Caveat:** any writes made after cutover live only in MySQL and are
lost on rollback. Keep the pre-cutover `prod-sooppiy.db` as the rollback data source
and treat rollback as "revert to the frozen snapshot," not "no data loss."

## Follow-ups (not blockers)

- `fly.toml` line ~90: the SQLite mount is commented out "remove when Postgres is
  configured" — update the comment (it's MySQL, not Postgres) and drop the mount once
  MySQL is live.
- `CLAUDE.md` still says "PostgreSQL in production" — stale; it's MySQL.
