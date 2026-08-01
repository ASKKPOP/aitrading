"""
routes_execution.py — Broker account management and order inspection.

Endpoints:
  GET  /api/execution/brokers                 — list available broker names
  POST /api/execution/accounts                — create / update broker account
  GET  /api/execution/accounts                — list agent's broker accounts
  PUT  /api/execution/accounts/{id}/mode      — set paper|shadow|live
  POST /api/execution/tcs-accept              — accept T&Cs for live mode
  GET  /api/execution/orders                  — list agent's broker_orders
  GET  /api/execution/orders/{order_id}       — single order detail
  GET  /api/execution/reconciliations         — shadow-mode drift log
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator
from typing import Optional

import database
from execution.base import AVAILABLE_BROKERS, BROKER_SPECS, REGION_VENUES, ExecutionMode
from execution.crypto import encrypt_credentials
from routes_shared import RouteContext, utc_now_iso_z


# ── Request / response models ─────────────────────────────────────────────────

class CreateBrokerAccountRequest(BaseModel):
    """Most venues authenticate with a key/secret pair; OKX and KuCoin add a
    passphrase; IBKR has neither — its Client Portal Gateway holds the session,
    so it takes the gateway URL and the account id instead. One model,
    validated per broker from BROKER_SPECS."""
    broker: str
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    gateway_url: str = ""
    account_id: str = ""
    allow_self_signed: bool = False

    @field_validator("broker")
    @classmethod
    def _valid_broker(cls, v: str) -> str:
        if v not in AVAILABLE_BROKERS:
            raise ValueError(f"broker must be one of {AVAILABLE_BROKERS}")
        return v

    def credentials(self) -> dict:
        """The blob to encrypt at rest, shaped for this broker."""
        if self.broker == "ibkr":
            if not self.gateway_url.strip() or not self.account_id.strip():
                raise ValueError("ibkr requires gateway_url and account_id")
            if not self.gateway_url.strip().lower().startswith(("http://", "https://")):
                raise ValueError("gateway_url must start with http:// or https://")
            return {
                "gateway_url": self.gateway_url.strip(),
                "account_id": self.account_id.strip(),
                "allow_self_signed": self.allow_self_signed,
            }
        if not self.api_key.strip() or not self.api_secret.strip():
            raise ValueError(f"{self.broker} requires api_key and api_secret")
        blob = {"key": self.api_key.strip(), "secret": self.api_secret.strip()}
        spec = BROKER_SPECS.get(self.broker)
        if spec and "passphrase" in spec.fields:
            if not self.passphrase.strip():
                raise ValueError(f"{self.broker} requires api_key, api_secret and passphrase")
            blob["passphrase"] = self.passphrase.strip()
        return blob


class SetExecutionModeRequest(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        valid = {m.value for m in ExecutionMode}
        if v not in valid:
            raise ValueError(f"mode must be one of {sorted(valid)}")
        return v


class TcsAcceptRequest(BaseModel):
    broker: str
    tcs_version: str = "v1"


# ── Route registration ────────────────────────────────────────────────────────

def register_execution_routes(app: FastAPI, ctx: RouteContext) -> None:

    # ── GET /api/execution/brokers ────────────────────────────────────────────
    @app.get("/api/execution/brokers")
    def list_brokers():
        """Broker names plus the per-broker connect-form spec and the regional
        recommendation matrix (Plan 19). Informational only — every broker
        stays connectable regardless of region."""
        return {
            "brokers": list(AVAILABLE_BROKERS),
            "specs": {
                name: {"fields": list(spec.fields), "shadow": spec.shadow,
                       "quote": spec.quote}
                for name, spec in BROKER_SPECS.items()
            },
            "regions": {code: list(venues) for code, venues in REGION_VENUES.items()},
        }

    # ── POST /api/execution/accounts ─────────────────────────────────────────
    @app.post("/api/execution/accounts", status_code=201)
    def create_broker_account(req: Request, body: CreateBrokerAccountRequest):
        agent = _require_agent(req)
        try:
            creds_enc = encrypt_credentials(body.credentials())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        conn = database.get_db_connection()
        cursor = conn.cursor()
        # Deactivate existing accounts for this broker
        cursor.execute(
            "UPDATE broker_accounts SET is_active=0, updated_at=? WHERE agent_id=? AND broker=?",
            (utc_now_iso_z(), agent["id"], body.broker),
        )
        cursor.execute(
            """INSERT INTO broker_accounts
               (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
               VALUES (?,?,?,?,1,?,?)""",
            (agent["id"], body.broker, ExecutionMode.PAPER.value,
             creds_enc, utc_now_iso_z(), utc_now_iso_z()),
        )
        account_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "account_id": account_id,
            "broker": body.broker,
            "execution_mode": ExecutionMode.PAPER.value,
            "message": "Broker account created. Start in paper mode, switch to shadow to compare against live fills."
        }

    # ── GET /api/execution/accounts ───────────────────────────────────────────
    @app.get("/api/execution/accounts")
    def list_broker_accounts(req: Request):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, broker, execution_mode, is_active, created_at, updated_at
               FROM broker_accounts WHERE agent_id=? ORDER BY updated_at DESC""",
            (agent["id"],),
        )
        rows = cursor.fetchall()
        conn.close()
        return {"accounts": [dict(r) for r in rows]}

    # ── GET /api/execution/health ─────────────────────────────────────────────
    @app.get("/api/execution/health")
    def gateway_health_check(req: Request):
        """Live readiness of the agent's gateway.

        Credentials on file is not the same as the venue accepting orders —
        IBKR sessions expire — so this probes rather than trusting the row.
        """
        agent = _require_agent(req)
        from execution.gateway import gateway_health
        return gateway_health(agent["id"])

    # ── PUT /api/execution/accounts/{account_id}/mode ─────────────────────────
    @app.put("/api/execution/accounts/{account_id}/mode")
    def set_execution_mode(account_id: int, req: Request, body: SetExecutionModeRequest):
        agent = _require_agent(req)

        # live mode requires accepted T&Cs
        if body.mode == ExecutionMode.LIVE.value:
            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, broker FROM broker_accounts WHERE id=? AND agent_id=?""",
                (account_id, agent["id"]),
            )
            acc = cursor.fetchone()
            if not acc:
                conn.close()
                raise HTTPException(status_code=404, detail="Account not found")
            broker_name = dict(acc)["broker"]
            cursor.execute(
                """SELECT id FROM broker_live_optins WHERE agent_id=? AND broker=?""",
                (agent["id"], broker_name),
            )
            optin = cursor.fetchone()
            conn.close()
            if not optin:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "You must accept the live-trading T&Cs before switching to live mode. "
                        "POST /api/execution/tcs-accept first."
                    ),
                )

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE broker_accounts SET execution_mode=?, updated_at=?
               WHERE id=? AND agent_id=?""",
            (body.mode, utc_now_iso_z(), account_id, agent["id"]),
        )
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Account not found")
        conn.commit()
        conn.close()
        return {"account_id": account_id, "execution_mode": body.mode}

    # ── POST /api/execution/tcs-accept ────────────────────────────────────────
    @app.post("/api/execution/tcs-accept", status_code=201)
    def accept_tcs(req: Request, body: TcsAcceptRequest):
        """
        Record that the agent has accepted the live-trading T&Cs.
        This is required before switching to live execution mode.
        The record is immutable — the row is never deleted.
        """
        agent = _require_agent(req)
        if body.broker not in AVAILABLE_BROKERS:
            raise HTTPException(status_code=400, detail=f"Unknown broker: {body.broker}")

        ip_address = req.client.host if req.client else None
        user_agent = req.headers.get("user-agent", "")

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_live_optins
               (agent_id, broker, tcs_version, ip_address, user_agent, created_at)
               VALUES (?,?,?,?,?,?)""",
            (agent["id"], body.broker, body.tcs_version,
             ip_address, user_agent, utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

        return {
            "message": f"T&Cs accepted for {body.broker} (version {body.tcs_version}). "
                       f"You may now switch to live mode.",
            "broker":      body.broker,
            "tcs_version": body.tcs_version,
        }

    # ── GET /api/execution/orders ─────────────────────────────────────────────
    @app.get("/api/execution/orders")
    def list_orders(req: Request, limit: int = 50, offset: int = 0, status: Optional[str] = None):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        q = "SELECT * FROM broker_orders WHERE agent_id=?"
        params: list = [agent["id"]]
        if status:
            q += " AND status=?"
            params.append(status)
        # Clamp both ends: a negative LIMIT is "unlimited" in SQLite and a
        # negative OFFSET errors — never let a query string decide page size.
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [max(1, min(limit, 200)), max(0, offset)]
        cursor.execute(q, params)
        rows = cursor.fetchall()
        conn.close()
        return {"orders": [dict(r) for r in rows], "limit": limit, "offset": offset}

    # ── GET /api/execution/orders/{order_id} ─────────────────────────────────
    @app.get("/api/execution/orders/{order_id}")
    def get_order(order_id: int, req: Request):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM broker_orders WHERE id=? AND agent_id=?",
            (order_id, agent["id"]),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        return dict(row)

    # ── GET /api/execution/reconciliations ────────────────────────────────────
    @app.get("/api/execution/reconciliations")
    def list_reconciliations(req: Request, limit: int = 50, offset: int = 0):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM position_reconciliations
               WHERE agent_id=? ORDER BY recorded_at DESC LIMIT ? OFFSET ?""",
            (agent["id"], min(limit, 200), offset),
        )
        rows = cursor.fetchall()
        conn.close()
        return {"reconciliations": [dict(r) for r in rows], "limit": limit, "offset": offset}


# ── Auth helper ───────────────────────────────────────────────────────────────

def _require_agent(req: Request) -> dict:
    from services import _get_agent_by_token
    auth = req.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent
