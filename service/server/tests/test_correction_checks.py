"""Corrections turned into checks.

Each test here replaces a correction that used to live only as prose in
agent memory and was re-learned the hard way. The failure message says what to
do instead. Add a test here whenever the same correction is given twice.
docs/plan/correction-log.md maps every check to the incident behind it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1]
REPO = SERVER.parents[1]

_SQL = re.compile(r"\b(SELECT|UPDATE|INSERT|DELETE)\b", re.I)


def _python_sources() -> list[Path]:
    files = [p for p in SERVER.rglob("*.py") if "tests" not in p.relative_to(SERVER).parts]
    files += sorted((REPO / "scripts").rglob("*.py"))
    return files


def _sql_literals() -> list[tuple[str, str]]:
    out = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _SQL.search(node.value):
                out.append((f"{path.relative_to(REPO)}:{node.lineno}", node.value))
    return out


def test_sql_literals_are_parsed():
    assert len(_sql_literals()) > 200, "the SQL scanner found almost nothing; it is blind, not clean"


def test_sql_contains_no_backslash():
    bad = [loc for loc, sql in _sql_literals() if "\\" in sql]
    assert not bad, (
        "SQL text must not contain a backslash. MySQL reads `\\` inside a quoted "
        "literal as an escape while SQLite does not, so `LIKE ... ESCAPE '\\'` passes "
        "every test and 500s on prod (pymysql 1064, /api/profit/history 2026-08-01). "
        "Escape LIKE patterns with `ESCAPE '!'` instead. Offenders: " + ", ".join(bad))


def test_run_events_is_never_queried_by_created_at():
    bad = [loc for loc, sql in _sql_literals()
           if re.search(r"\brun_events\b", sql) and "created_at" in sql]
    assert not bad, (
        "run_events has no created_at column; its time column is `ts`. A filter on "
        "created_at returns nothing without an error, which once produced a false "
        "'not journaled' finding. Use ts. Offenders: " + ", ".join(bad))


def test_sql_has_no_space_form_timestamp_literal():
    bad = [loc for loc, sql in _sql_literals() if re.search(r"'\d{4}-\d\d-\d\d \d\d:", sql)]
    assert not bad, (
        "Timestamp columns such as run_events.ts and trading_runs.stopped_at hold ISO "
        "strings ('2026-09-05T02:52:50Z') and compare as text. A space-form literal "
        "('2026-09-05 02:52:50') sorts below 'T', so the filter silently matches the "
        "whole day. Write the literal as 'YYYY-MM-DDTHH:MM:SSZ'. Offenders: " + ", ".join(bad))


def _execute_sql_text(fn: ast.AST, call: ast.Call, src: str) -> str:
    arg = call.args[0]
    if isinstance(arg, ast.Name):
        parts = []
        for node in ast.walk(fn):
            targets = [node.target] if isinstance(node, ast.AugAssign) else getattr(node, "targets", [])
            if isinstance(node, (ast.Assign, ast.AugAssign)) and any(
                    isinstance(t, ast.Name) and t.id == arg.id for t in targets):
                parts.append(ast.get_source_segment(src, node) or "")
        return "\n".join(parts)
    return ast.get_source_segment(src, arg) or ""


def _unscoped_position_book_reads() -> list[str]:
    bad = []
    for path in _python_sources():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            scope_names = set()
            for node in ast.walk(fn):
                if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                        and getattr(node.value.func, "id", getattr(node.value.func, "attr", None))
                        == "run_scope_sql"):
                    for target in node.targets:
                        for name in ast.walk(target):
                            if isinstance(name, ast.Name):
                                scope_names.add(name.id)
            for call in ast.walk(fn):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "execute" and call.args):
                    continue
                sql = _execute_sql_text(fn, call, src)
                if (re.search(r"\bFROM\s+positions\b", sql, re.I)
                        and re.search(r"\bagent_id\s*=", sql)
                        and re.search(r"\bsymbol\s*=", sql)
                        and "run_id" not in sql
                        and not any(re.search(rf"\b{re.escape(n)}\b", sql) for n in scope_names)
                        and not re.search(r"\b(SUM|COUNT|MAX|MIN|AVG)\s*\(", sql, re.I)):
                    bad.append(f"{path.relative_to(REPO)}:{call.lineno} ({fn.name})")
    return bad


def test_position_book_reads_are_run_scoped():
    bad = _unscoped_position_book_reads()
    assert not bad, (
        "A positions read keyed on agent+symbol must say which book it reads. Several "
        "runs can hold the same agent+market+symbol, so an unscoped fetchone() returns "
        "an arbitrary run's row (a flatten once found 'no position' and left the book "
        "open). Add `scope, args = run_scope_sql(run_id)` from routes_shared and append "
        "it, passing ANY_RUN only for a deliberate cross-book aggregate. Offenders: "
        + ", ".join(bad))


BANNED_PACKAGES = {
    "authlib": "OAuth runs on PyJWT + httpx; Authlib had no import site and carried 8 of 13 "
               "advisories (removed 95e50b3, 2026-11-07).",
    "joserfc": "only Authlib used it.",
}


@pytest.mark.parametrize("lockfile", ["service/requirements.txt", "service/constraints.txt"])
def test_banned_packages_absent(lockfile):
    names = {re.split(r"[<>=!~\[;\s]", line.strip(), maxsplit=1)[0].lower()
             for line in (REPO / lockfile).read_text().splitlines()
             if line.strip() and not line.lstrip().startswith(("#", "-"))}
    found = sorted(names & BANNED_PACKAGES.keys())
    assert not found, f"{lockfile} re-adds a banned package: " + "; ".join(
        f"{n}: {BANNED_PACKAGES[n]}" for n in found)


_CHINA_TERMS = re.compile(r"\ba-stock\b|\bA_STOCK|\bA-shares?\b|A주|A股|A株", re.I)
_CHINA_ROOTS = ("service/server", "service/frontend/src", "skills", "marketing/src")
_CHINA_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".astro", ".html"}


def test_china_a_shares_stay_removed():
    import markets

    assert not {m for m in markets.supported_markets() if "a-stock" in m or "china" in m}
    bad = []
    for root in _CHINA_ROOTS:
        for path in (REPO / root).rglob("*"):
            rel = path.relative_to(REPO)
            if (path.suffix not in _CHINA_SUFFIXES or "node_modules" in rel.parts
                    or "tests" in rel.parts or not path.is_file()):
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if _CHINA_TERMS.search(line):
                    bad.append(f"{rel}:{n}")
    assert not bad, (
        "China A-shares were removed platform-wide by owner order (2026-08-01, PR #173) "
        "and must not be reintroduced or mentioned in code, copy or translations. "
        "Offenders: " + ", ".join(bad))


def test_suite_cannot_reach_a_real_llm():
    import llm_client

    assert llm_client.resolve_provider() is None, (
        "The test suite resolved a live LLM provider. tests/conftest.py blanks every "
        "provider key derived from llm_client._PROVIDERS; a provider read from somewhere "
        "else has to be blanked there too. Stub generate_text in the test that needs it.")
    assert not llm_client.llm_configured()
