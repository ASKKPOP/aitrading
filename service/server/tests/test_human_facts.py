"""Contract tests for human_facts — the Tier-4 crowd-reading service.

Four properties matter more than any individual number:

  1. FACTS ONLY. The rendered line and the analyst payload carry numbers
     with sources — never a verdict word, never an instruction. The
     cautionary precedent is desk_record/#484: a line that editorializes
     becomes doctrine.
  2. KEY-GATED. A source without its credentials makes NO network call;
     the whole service is a no-op unless HUMAN_FACTS_ENABLED.
  3. FAIL-SOFT. One dead source never blocks another; a broken table or
     module never costs a trading cycle a decision.
  4. WIRED. The line must actually reach the composed prompt and the
     Sentiment seat's data dict (`brief-line-wiring-is-untested-by-default`).
"""
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import human_facts as hf  # noqa: E402


# ── fixtures ───────────────────────────────────────────────────────────────


def _mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE human_facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT, scope TEXT, metric TEXT, bucket TEXT,
        ts TEXT, value REAL, meta TEXT,
        UNIQUE(source, scope, metric, bucket))""")
    conn.commit()
    return conn


class _KeepOpenConn:
    """collect_once()/readers close the connection; tests need it alive."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        if name == "close":
            return lambda: None
        return getattr(self._conn, name)


@pytest.fixture
def db(monkeypatch):
    conn = _mem_conn()
    fake_db = types.ModuleType("database")
    fake_db.get_db_connection = lambda: _KeepOpenConn(conn)
    monkeypatch.setitem(sys.modules, "database", fake_db)
    hf._CACHE.clear()
    yield conn
    hf._CACHE.clear()


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("HUMAN_FACTS_ENABLED", "1")


def _no_http(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(hf, "_http_json", _boom)


# ── gating ─────────────────────────────────────────────────────────────────


def test_disabled_service_is_a_noop(monkeypatch, db):
    monkeypatch.delenv("HUMAN_FACTS_ENABLED", raising=False)
    _no_http(monkeypatch)
    assert hf.collect_once() == {"skipped": "disabled"}
    assert hf.human_facts_line("BTCUSDT", "crypto") == ""
    assert hf.human_facts_payload("BTCUSDT") is None


def test_unkeyed_sources_make_no_network_calls(monkeypatch, db, enabled):
    for var in ("TELEGRAM_BOT_TOKEN", "YOUTUBE_API_KEY", "DISCORD_BOT_TOKEN",
                "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    _no_http(monkeypatch)
    result = hf.collect_once()
    assert result["sources"] == []
    assert result["stored"] == 0


def test_tiktok_is_registered_but_never_configured(monkeypatch):
    # No env var can turn it on — the sentinel key is unsatisfiable by
    # design until an official API exists.
    assert hf.source_configured("tiktok") is False
    assert "tiktok" in hf._SOURCE_KEYS


# ── collectors (mocked HTTP) ───────────────────────────────────────────────


def test_telegram_member_count_becomes_a_fact(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("HUMAN_FACTS_CHANNELS",
                       json.dumps({"telegram": ["@cryptochat"]}))
    monkeypatch.setattr(hf, "_http_json",
                        lambda *a, **k: {"ok": True, "result": 12340})
    facts = hf.collect_telegram()
    assert facts == [{"scope": "telegram:@cryptochat", "metric": "members",
                      "value": 12340.0, "meta": None}]


def test_discord_velocity_counts_recent_messages_and_authors(monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "d")
    monkeypatch.setenv("HUMAN_FACTS_CHANNELS",
                       json.dumps({"discord": ["123"]}))
    now = datetime.now(timezone.utc)
    msgs = [
        {"timestamp": (now - timedelta(minutes=5)).isoformat(),
         "author": {"id": "a"}},
        {"timestamp": (now - timedelta(minutes=30)).isoformat(),
         "author": {"id": "b"}},
        {"timestamp": (now - timedelta(hours=3)).isoformat(),
         "author": {"id": "c"}},  # outside the hour — excluded
    ]
    monkeypatch.setattr(hf, "_http_json", lambda *a, **k: msgs)
    facts = {f["metric"]: f["value"] for f in hf.collect_discord()}
    assert facts["msgs_per_hr"] == 2.0
    assert facts["authors_per_hr"] == 2.0


def test_naver_search_index_and_delta(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "i")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "s")
    monkeypatch.setenv("HUMAN_FACTS_NAVER_KEYWORDS",
                       json.dumps({"BTCUSDT": ["비트코인"]}))
    monkeypatch.setattr(hf, "_http_json", lambda *a, **k: {
        "results": [{"title": "BTCUSDT",
                     "data": [{"period": "2026-08-23", "ratio": 51.0},
                              {"period": "2026-08-24", "ratio": 63.0}]}]})
    facts = {f["metric"]: f for f in hf.collect_naver()}
    assert facts["naver_search_idx"]["value"] == 63.0
    assert facts["naver_search_idx"]["scope"] == "BTCUSDT"
    assert facts["naver_search_idx_d1"]["value"] == 12.0


def test_youtube_uploads_24h_from_uploads_playlist(monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setenv("YOUTUBE_API_KEY", "y")
    monkeypatch.setenv("HUMAN_FACTS_CHANNELS",
                       json.dumps({"youtube": ["UCabc"]}))
    now = datetime.now(timezone.utc)

    def fake_http(method, url, **kw):
        if "youtube/v3/channels" in url:
            return {"items": [{
                "statistics": {"subscriberCount": "1000"},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        return {"items": [
            {"contentDetails": {"videoPublishedAt":
             (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}},
            {"contentDetails": {"videoPublishedAt":
             (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}},
        ]}

    monkeypatch.setattr(hf, "_http_json", fake_http)
    facts = {f["metric"]: f["value"] for f in hf.collect_youtube()}
    assert facts["subscribers"] == 1000.0
    assert facts["uploads_24h"] == 1.0


# ── storage ────────────────────────────────────────────────────────────────


def _collect_with(monkeypatch, db, facts):
    # _COLLECTORS captured the function references at import time, so the
    # registry entry is what must be patched, not the module attribute.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(hf, "_COLLECTORS",
                        dict(hf._COLLECTORS, telegram=lambda: facts))
    return hf.collect_once()


def test_collection_is_idempotent_inside_one_bucket(monkeypatch, db, enabled):
    facts = [{"scope": "telegram:@c", "metric": "members", "value": 10.0,
              "meta": None}]
    r1 = _collect_with(monkeypatch, db, facts)
    r2 = _collect_with(monkeypatch, db, facts)
    assert r1["stored"] == r2["stored"] == 1
    n = db.execute("SELECT COUNT(*) FROM human_facts").fetchone()[0]
    assert n == 1, "same bucket must upsert, not duplicate"


def test_one_broken_source_never_blocks_another(monkeypatch, db, enabled):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("NAVER_CLIENT_ID", "i")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "s")

    def _boom():
        raise RuntimeError("telegram down")

    monkeypatch.setattr(hf, "_COLLECTORS", dict(
        hf._COLLECTORS, telegram=_boom,
        naver=lambda: [{"scope": "BTCUSDT", "metric": "naver_search_idx",
                        "value": 63.0, "meta": None}]))
    result = hf.collect_once()
    assert "telegram" in result["errors"]
    assert result["stored"] == 1, "the healthy source must still store"


# ── read side: facts only, never a verdict ─────────────────────────────────


def _seed_reading(db, source="telegram", scope="telegram:@c",
                  metric="members", value=12340.0):
    from datetime import datetime, timezone
    db.execute(
        "INSERT INTO human_facts (source, scope, metric, bucket, ts, value)"
        " VALUES (?,?,?,?,?,?)",
        (source, scope, metric, "b1",
         datetime.now(timezone.utc).isoformat(), value))
    db.commit()


def test_line_renders_numbers_and_no_verdict_words(monkeypatch, db, enabled):
    _seed_reading(db)
    _seed_reading(db, source="naver", scope="BTCUSDT",
                  metric="naver_search_idx", value=63.0)
    line = hf.human_facts_line("BTCUSDT", "crypto")
    assert "12,340" in line and "63" in line
    lowered = line.lower()
    for banned in ("bullish", "bearish", "buy", "sell", "you must",
                   "do not", "should"):
        assert banned not in lowered, f"grew a verdict/instruction: {banned}"
    assert "your call" in lowered
    assert "not advice" in lowered


def test_line_is_empty_when_nothing_fresh(monkeypatch, db, enabled):
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    db.execute(
        "INSERT INTO human_facts (source, scope, metric, bucket, ts, value)"
        " VALUES ('telegram','telegram:@c','members','b0',?,10)", (old,))
    db.commit()
    assert hf.human_facts_line("BTCUSDT", "crypto") == ""


def test_payload_is_numeric_and_source_keyed(monkeypatch, db, enabled):
    _seed_reading(db, source="naver", scope="BTCUSDT",
                  metric="naver_search_idx", value=63.0)
    payload = hf.human_facts_payload("BTCUSDT")
    assert payload == {"naver": {"BTCUSDT::naver_search_idx": 63.0}}


# ── wiring: the readings must reach the prompt and the panel ───────────────


def test_line_is_wired_into_position_state(monkeypatch):
    import run_engine

    fake = types.ModuleType("human_facts")
    fake.human_facts_line = lambda symbol, market: (
        f"<<HUMANFACTS {symbol}/{market}>>")
    monkeypatch.setitem(sys.modules, "human_facts", fake)

    for name in dir(run_engine):
        if name.startswith("_") and name.endswith("_line") \
                and name != "_human_facts_line":
            try:
                monkeypatch.setattr(run_engine, name, lambda *a, **k: "")
            except AttributeError:
                pass

    out = run_engine._compose_position_state(
        {"id": 1, "symbol": "BTCUSDT", "market": "crypto"},
        {}, 0.0, {"direction": "long"})
    assert "<<HUMANFACTS BTCUSDT/crypto>>" in out, \
        "human_facts line never reached the composed prompt"


def test_line_gate_flag_can_disable(monkeypatch):
    import run_engine
    monkeypatch.setenv("HUMAN_FACTS_BRIEF", "0")
    fake = types.ModuleType("human_facts")
    fake.human_facts_line = lambda symbol, market: "<<HF>>"
    monkeypatch.setitem(sys.modules, "human_facts", fake)
    assert run_engine._human_facts_line(
        {"id": 1, "symbol": "X", "market": "crypto"}) == ""


def test_line_survives_a_broken_module(monkeypatch):
    import run_engine
    broken = types.ModuleType("human_facts")

    def _boom(*a, **k):
        raise RuntimeError("collector down")

    broken.human_facts_line = _boom
    monkeypatch.setitem(sys.modules, "human_facts", broken)
    assert run_engine._human_facts_line(
        {"id": 1, "symbol": "X", "market": "crypto"}) == ""


def test_payload_is_wired_into_sentiment_gather(monkeypatch):
    import analysis_agents

    fake = types.ModuleType("human_facts")
    fake.human_facts_payload = lambda symbol: {
        "naver": {f"{symbol}::naver_search_idx": 63.0}}
    monkeypatch.setitem(sys.modules, "human_facts", fake)
    # Kill the other network-backed enrichers.
    fake_sources = types.ModuleType("analysis_sources")
    fake_sources.fetch_stocktwits_sentiment = lambda s: None
    monkeypatch.setitem(sys.modules, "analysis_sources", fake_sources)
    fake_social = types.ModuleType("social_feed")
    fake_social.social_sentiment_for = lambda s: None
    monkeypatch.setitem(sys.modules, "social_feed", fake_social)
    fake_psych = types.ModuleType("psych_feed")
    fake_psych.get_psych_payload = lambda: {"available": False}
    monkeypatch.setitem(sys.modules, "psych_feed", fake_psych)
    monkeypatch.setattr(analysis_agents, "_whale_context", lambda s: None)

    out = analysis_agents._gather_sentiment("BTCUSDT", "crypto", {})
    assert out.get("human_facts") == {"naver": {"BTCUSDT::naver_search_idx":
                                                63.0}}
