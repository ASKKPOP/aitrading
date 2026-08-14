"""No hardcoded hosts in backend source — every public URL comes from .env.

Owner rule 2026-08-13, after SOOPPIY_FRONTEND_URL was unset on prod and its
``http://localhost:3000`` default silently redirected every paying member back
to their own machine. Nothing errored; only the user saw it.

Two rules, both aimed at that failure mode:
  * no os.getenv default that points at localhost — a wrong-but-plausible
    default is worse than a missing one, because it cannot fail loudly;
  * no literal https://sooppiy.com in backend source — the platform's own
    address is configuration, and a staging box hardcoding it mails users
    straight to production.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

# i18n_errors_data quotes example URLs inside user-facing message text;
# site_config is the module that DEFINES this rule and cites the old literal
# in its docstring to explain why the rule exists.
_EXEMPT = {"i18n_errors_data.py", "site_config.py"}

_LOCALHOST_DEFAULT = re.compile(
    r"""getenv\(\s*["'][A-Z0-9_]+["']\s*,\s*["'][^"']*(?:localhost|127\.0\.0\.1)""")
_OWN_HOST = re.compile(r"https?://(?:www\.)?sooppiy\.com")


def _sources():
    for p in sorted(SERVER_DIR.rglob("*.py")):
        rel = p.relative_to(SERVER_DIR)
        if rel.parts[0] in ("tests", "alembic") or p.name in _EXEMPT:
            continue
        yield rel, p.read_text(encoding="utf-8", errors="replace")


class NoHardcodedUrlTests(unittest.TestCase):
    def test_no_getenv_default_points_at_localhost(self):
        bad = []
        for rel, text in _sources():
            for i, line in enumerate(text.splitlines(), 1):
                if _LOCALHOST_DEFAULT.search(line):
                    bad.append(f"{rel}:{i}: {line.strip()[:100]}")
        self.assertEqual(bad, [], "getenv() defaults pointing at localhost — these "
                                 "ship to production and fail silently:\n  "
                                 + "\n  ".join(bad))

    def test_no_hardcoded_own_hostname(self):
        """The platform's own address is configuration, not a constant."""
        bad = []
        for rel, text in _sources():
            for i, line in enumerate(text.splitlines(), 1):
                if _OWN_HOST.search(line) and "site_config" not in line:
                    bad.append(f"{rel}:{i}: {line.strip()[:100]}")
        self.assertEqual(bad, [], "hardcoded https://sooppiy.com — use "
                                 "site_config.site_url():\n  " + "\n  ".join(bad))


class SiteUrlContractTests(unittest.TestCase):
    def test_unset_raises_rather_than_guessing(self):
        import os
        from importlib import reload
        import site_config
        saved = os.environ.pop("SOOPPIY_FRONTEND_URL", None)
        try:
            reload(site_config)
            with self.assertRaises(RuntimeError):
                site_config.site_url()
        finally:
            if saved is not None:
                os.environ["SOOPPIY_FRONTEND_URL"] = saved
            reload(site_config)

    def test_trailing_slash_is_stripped(self):
        import os
        import site_config
        os.environ["SOOPPIY_FRONTEND_URL"] = "https://example.test/"
        try:
            self.assertEqual(site_config.site_url(), "https://example.test")
        finally:
            os.environ["SOOPPIY_FRONTEND_URL"] = "https://sooppiy.test"

    def test_scheme_is_required(self):
        import os
        import site_config
        os.environ["SOOPPIY_FRONTEND_URL"] = "sooppiy.com"
        try:
            with self.assertRaises(RuntimeError):
                site_config.site_url()
        finally:
            os.environ["SOOPPIY_FRONTEND_URL"] = "https://sooppiy.test"


if __name__ == "__main__":
    unittest.main()
