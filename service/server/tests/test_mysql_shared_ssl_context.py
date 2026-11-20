"""MySQL connections must reuse ONE SSLContext instead of building one per call.

PyMySQL 1.2's default (PREFERRED) TLS mode calls ssl.create_default_context()
-> load_default_certs() inside every Connection.__init__. Measured on prod
2026-11-20: 9.8 ms CPU per connect just for that context, out of a 14.3 ms
connect (shared context: 4.6 ms); py-spy put the context build at 42% of the
sampled time of DB-touching API routes, most of them on the event loop.

These tests run the REAL pymysql.Connection constructor (defer_connect, so no
server is needed) on the kwargs get_db_connection passes, so they check what
pymysql actually ends up with, not just the call shape.
"""
import os
import ssl
import sys
from unittest.mock import patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import pymysql
import pymysql.connections

import database

_URL = "mysql+pymysql://u:p@dbhost:3306/sooppiy"


def _deferred_connect(**kwargs):
    return pymysql.connections.Connection(defer_connect=True, **kwargs)


def _open_raw_connections(n):
    with patch.object(database, "DATABASE_URL", _URL), \
            patch.object(database.pymysql, "connect", side_effect=_deferred_connect):
        return [database.get_db_connection()._connection for _ in range(n)]


def test_connections_share_one_ssl_context():
    real_create = ssl.create_default_context
    calls = []

    def counting_create(*a, **kw):
        calls.append(1)
        return real_create(*a, **kw)

    cached = getattr(database, "_mysql_ssl_context", None)
    if cached is not None:
        cached.cache_clear()
    with patch.object(ssl, "create_default_context", side_effect=counting_create):
        conns = _open_raw_connections(3)
    assert all(c.ssl for c in conns), "TLS must stay on"
    assert conns[0].ctx is conns[1].ctx is conns[2].ctx, (
        "each connection built its own SSLContext")
    assert len(calls) <= 1, f"create_default_context ran {len(calls)} times for 3 connects"


def test_shared_context_matches_pymysql_default_tls_settings():
    (conn,) = _open_raw_connections(1)
    default = pymysql.connections.Connection(
        defer_connect=True, host="dbhost", user="u", password="p").ctx
    ctx = conn.ctx
    assert ctx.verify_mode == default.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname == default.check_hostname is False
    assert ctx.verify_flags == default.verify_flags
    assert ctx.minimum_version == default.minimum_version
    assert ctx.options == default.options


def test_found_rows_and_autocommit_unchanged():
    (conn,) = _open_raw_connections(1)
    assert conn.client_flag & pymysql.constants.CLIENT.FOUND_ROWS
    assert conn.autocommit_mode is False
    assert conn.cursorclass is pymysql.cursors.DictCursor
    assert conn.charset == "utf8mb4"


def test_shared_context_cipher_list_matches_default():
    (conn,) = _open_raw_connections(1)
    default = pymysql.connections.Connection(
        defer_connect=True, host="dbhost", user="u", password="p").ctx
    assert [c["name"] for c in conn.ctx.get_ciphers()] == \
        [c["name"] for c in default.get_ciphers()]


def test_server_without_tls_still_falls_back_to_plaintext():
    """PyMySQL's default falls back to plaintext when the server has no TLS;
    passing a context makes TLS required. The old fallback must survive."""
    seen = []

    def fake_connect(**kwargs):
        seen.append("ssl" in kwargs)
        if "ssl" in kwargs:
            raise pymysql.err.OperationalError(
                2026, "SSL is required but the server doesn't support it")
        return pymysql.connections.Connection(defer_connect=True, **kwargs)

    with patch.object(database, "DATABASE_URL", _URL), \
            patch.object(database.pymysql, "connect", side_effect=fake_connect):
        conn = database.get_db_connection()._connection
    assert seen == [True, False]
    assert conn.client_flag & pymysql.constants.CLIENT.FOUND_ROWS
    assert conn.autocommit_mode is False


def test_other_connect_errors_are_not_retried():
    calls = []

    def fake_connect(**kwargs):
        calls.append(1)
        raise pymysql.err.OperationalError(1045, "Access denied")

    with patch.object(database, "DATABASE_URL", _URL), \
            patch.object(database.pymysql, "connect", side_effect=fake_connect):
        try:
            database.get_db_connection()
        except pymysql.err.OperationalError as exc:
            assert exc.args[0] == 1045
        else:
            raise AssertionError("expected OperationalError")
    assert calls == [1]
