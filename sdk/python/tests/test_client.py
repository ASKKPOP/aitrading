"""Unit tests for the sooppiy SDK. No network — uses pytest-httpx to mock."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

SDK_ROOT = Path(__file__).resolve().parents[1]
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from sooppiy import (
    SooppiyClient, SooppiyError, APIError, AuthError, NotFound, run_strategy,
)


# ── constructor + auth-header threading ───────────────────────────────────

class TestConstructor:
    def test_requires_token(self):
        with pytest.raises(AuthError):
            SooppiyClient(token="")

    def test_requires_non_str_token_raises(self):
        with pytest.raises(AuthError):
            SooppiyClient(token=None)  # type: ignore[arg-type]

    def test_token_threads_bearer_header(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/agents/me",
            json={"id": 1, "name": "bot"},
        )
        c = SooppiyClient(token="claw_xyz")
        c.me()
        sent = httpx_mock.get_requests()[0]
        assert sent.headers["Authorization"] == "Bearer claw_xyz"

    def test_custom_base_url(self, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:8001/api/claw/agents/me",
            json={"ok": True},
        )
        c = SooppiyClient(token="t", base_url="http://localhost:8001")
        assert c.me() == {"ok": True}


# ── error mapping ─────────────────────────────────────────────────────────

class TestErrors:
    def test_401_raises_auth_error(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/agents/me",
            status_code=401, text="bad token",
        )
        c = SooppiyClient(token="t")
        with pytest.raises(AuthError):
            c.me()

    def test_404_raises_not_found(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/agents/me",
            status_code=404, text="nope",
        )
        c = SooppiyClient(token="t")
        with pytest.raises(NotFound):
            c.me()

    def test_500_raises_api_error(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/agents/me",
            status_code=500, text="boom",
        )
        c = SooppiyClient(token="t")
        with pytest.raises(APIError) as exc:
            c.me()
        assert exc.value.status_code == 500

    def test_all_errors_subclass_SooppiyError(self):
        for cls in (AuthError, NotFound, APIError):
            assert issubclass(cls, SooppiyError)


# ── convenience shortcuts ─────────────────────────────────────────────────

class TestConvenienceShortcuts:
    def test_list_signals_passes_filters(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=10&message_type=operation&market=us-stock",
            json={"signals": []},
        )
        c = SooppiyClient(token="t")
        c.list_signals(limit=10, message_type="operation", market="us-stock")

    def test_publish_signal_payload_shape(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/realtime",
            json={"signal_id": 42},
        )
        c = SooppiyClient(token="t")
        c.publish_signal(
            market="us-stock", symbol="AAPL", side="buy",
            entry_price=195.5, content="breakout",
        )
        sent = httpx_mock.get_requests()[0]
        import json as _json
        body = _json.loads(sent.content)
        assert body["market"] == "us-stock"
        assert body["symbol"] == "AAPL"
        assert body["action"] == "buy"          # side → action mapping
        assert body["price"] == 195.5

    def test_register_returns_authed_client(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/agents/selfRegister",
            json={"token": "claw_new", "botUserId": "agent_1"},
        )
        c = SooppiyClient.register(name="my-bot", email="bot@x.io")
        assert isinstance(c, SooppiyClient)
        assert c._token == "claw_new"

    def test_leaderboard_and_positions(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/leaderboard?metric=return&limit=20",
            json={"leaderboard": []},
        )
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/positions",
            json={"positions": []},
        )
        c = SooppiyClient(token="t")
        c.leaderboard()
        c.positions()


# ── context-manager + close() ─────────────────────────────────────────────

class TestLifecycle:
    def test_context_manager_closes_http(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/claw/agents/me",
            json={"ok": True},
        )
        with SooppiyClient(token="t") as c:
            c.me()
        # After exit, the inner httpx client should be closed; calling again raises
        with pytest.raises(RuntimeError):
            c.me()


# ── run_strategy polling helper ───────────────────────────────────────────

class TestRunStrategy:
    def test_skips_signals_seen_at_bootstrap(self, httpx_mock):
        # Bootstrap fetch returns id=1, then poll returns id=1 again — should NOT fire.
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=50&message_type=operation",
            json={"signals": [{"signal_id": 1, "symbol": "AAPL"}]},
        )
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=20&message_type=operation",
            json={"signals": [{"signal_id": 1, "symbol": "AAPL"}]},
        )
        c = SooppiyClient(token="t")
        seen: list = []
        run_strategy(seen.append, client=c, interval=0, max_iterations=1)
        assert seen == []                       # bootstrap deduped it

    def test_fires_handler_on_new_signals(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=50&message_type=operation",
            json={"signals": []},
        )
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=20&message_type=operation",
            json={"signals": [
                {"signal_id": 7, "symbol": "BTC"},
                {"signal_id": 8, "symbol": "ETH"},
            ]},
        )
        c = SooppiyClient(token="t")
        seen: list = []
        run_strategy(seen.append, client=c, interval=0, max_iterations=1)
        assert [s["signal_id"] for s in seen] == [7, 8]

    def test_handler_exception_does_not_kill_loop(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=50&message_type=operation",
            json={"signals": []},
        )
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=20&message_type=operation",
            json={"signals": [
                {"signal_id": 1}, {"signal_id": 2},
            ]},
        )
        c = SooppiyClient(token="t")
        invocations: list = []

        def bad(sig):
            invocations.append(sig["signal_id"])
            raise ValueError("oops")

        run_strategy(bad, client=c, interval=0, max_iterations=1)
        assert invocations == [1, 2]            # both fired despite raises

    def test_handles_list_response_shape(self, httpx_mock):
        # /signals/feed has shipped two shapes — bare list + {signals:[...]}
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=50&message_type=operation",
            json=[],
        )
        httpx_mock.add_response(
            url="https://api.sooppiy.com/api/signals/feed?limit=20&message_type=operation",
            json=[{"signal_id": 99}],
        )
        c = SooppiyClient(token="t")
        seen: list = []
        run_strategy(seen.append, client=c, interval=0, max_iterations=1)
        assert len(seen) == 1


# ── raw escape hatch ──────────────────────────────────────────────────────

class TestRawClient:
    def test_raw_lazy_imported(self):
        c = SooppiyClient(token="t")
        assert not hasattr(c, "_raw")
        _ = c.raw
        assert hasattr(c, "_raw")
