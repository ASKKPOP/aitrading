# MySQL cutover runbook (sooppiy.com)

**Status:** ✅ **Executed.** Production runs on MySQL. Verified 2026-07-17:
the `sooppiy-backend` container logs `Database ready: backend=mysql`
(`database_name=sooppiy`) against **MySQL 8.0.46**, and the live data is intact
(agents 5, `profit_history` 2,622 rows, leaderboard returning results, `/health` 200).

**Deployment target:** Docker containers on the **AWS EC2 host** (`ec2-user@52.9.147.202`)
behind an AWS ALB. Deploys are image rebuilds on that host — there is no PaaS involved.

**Date:** 2026-07-17

> ⚠️ **The MySQL code is not on `main` yet.** It lives on `feat/mysql-backend-port`
> (PR #4, open). Production is running that branch. Deploying `main` today would ship a
> backend without the MySQL port against a MySQL database. **Merge PR #4 before any
> further deploy.**

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

The SQLite path is unchanged — the suite still passes on SQLite (1119 tests).

## Requirements for the target MySQL

- **MySQL 8.0.13 or newer** (the schema uses expression defaults on TEXT columns,
  e.g. `created_at ... DEFAULT (DATE_FORMAT(...))` and `positions_json DEFAULT ('[]')`).
  In production: MySQL **8.0.46**.
- Database created with **`CHARACTER SET utf8mb4`**.
- A user with full DDL+DML on that database.

## How production is wired

- `DATABASE_URL` lives in **`~/sooppiy/app/.env`** on the EC2 host and is passed to the
  container via `--env-file` at `docker run`.
- **`--env-file` is read only at `docker run`, never on restart.** Changing `.env`
  requires `docker rm -f` + `docker run`, not `docker restart`.
- On boot the app runs `alembic upgrade head` (a no-op once at head) and logs
  `Database ready: backend=mysql`.

## Re-running the cutover (fresh environment / disaster recovery)

> Do this in a **maintenance window / write freeze**. Between copying the SQLite
> data and flipping `DATABASE_URL`, any writes that hit SQLite would be lost. Stop
> the worker container and put the API in read-only (or accept brief downtime) first.

1. **Provision** MySQL 8.0.13+ and create the database:
   ```sql
   CREATE DATABASE sooppiy CHARACTER SET utf8mb4;
   CREATE USER 'sooppiy'@'%' IDENTIFIED BY '<pw>';
   GRANT ALL PRIVILEGES ON sooppiy.* TO 'sooppiy'@'%';
   ```

2. **Copy the current SQLite off the host** (only relevant when migrating from a
   SQLite deployment — the live DB lives in the `sooppiy_data` Docker volume at
   `/app/service/server/data/sooppiy.db`):
   ```bash
   ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202 \
     'docker cp sooppiy-backend:/app/service/server/data/sooppiy.db /tmp/prod-sooppiy.db'
   scp -i ~/shell/sierrabiolab/sierrabiolab-aws.pem \
     ec2-user@52.9.147.202:/tmp/prod-sooppiy.db ./prod-sooppiy.db
   ```

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

5. **Point production at MySQL and recreate the containers** (backup `.env` first):
   ```bash
   ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202 '
     cd ~/sooppiy/app
     cp .env .env.bak-$(date +%Y%m%d-%H%M%S)
     # set DATABASE_URL=mysql+pymysql://sooppiy:<pw>@<host>:3306/sooppiy in .env
     docker rm -f sooppiy-backend
     docker run -d --name sooppiy-backend --restart unless-stopped \
       --env-file ~/sooppiy/app/.env -e SOOPPIY_API_BACKGROUND_TASKS=true \
       -p 127.0.0.1:8101:8001 -v sooppiy_data:/app/service/server/data \
       sooppiy-backend:test'
   ```

6. **Verify**:
   ```bash
   ssh -i <key> ec2-user@52.9.147.202 \
     'docker logs sooppiy-backend 2>&1 | grep "Database ready"'   # backend=mysql
   curl -s -o /dev/null -w '%{http_code}\n' https://sooppiy.com/health        # 200
   curl -s https://sooppiy.com/api/claw/agents/count                          # sane count
   ```
   Exercise a signal-feed read, an agent-message read (the `read` column), and a
   config-profile save (the upsert path).

## Rollback

Restore the backed-up `.env` (which has no `DATABASE_URL`, or the previous value) and
recreate the container — the app falls back to SQLite in the `sooppiy_data` volume.
**Caveat:** any writes made after cutover live only in MySQL and are lost on rollback.
Keep the pre-cutover `prod-sooppiy.db` as the rollback data source and treat rollback as
"revert to the frozen snapshot," not "no data loss."

## Follow-ups

- **Merge PR #4** so `main` matches what production runs (see the warning above).
- `CLAUDE.md` said "PostgreSQL in production" — corrected to MySQL.
