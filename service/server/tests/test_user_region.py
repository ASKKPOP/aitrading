"""Region + timezone as member-owned settings (2026-07-28).

Region is a COUNTRY and is deliberately not derived from language: English
alone serves the USA, Canada, Australia and Singapore — four countries, four
time zones, four regulators, and daylight saving that runs opposite between
hemispheres.

The invariant these tests exist to hold: an unplaceable member is `unknown`,
never `US`. Every layer here — signup, normalisation, the API, back-fill —
has a tempting place to substitute a default jurisdiction, and every one of
them is wrong.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from analysis_agents import LANG_NAMES
import database
import regions
import signup_lang

TARGETS = {"US", "CA", "AU", "SG", "KR", "JP", "TH", "VN", "ID"}
LANGS = tuple(LANG_NAMES)


class Registry(unittest.TestCase):

    def test_every_target_market_is_served(self):
        self.assertEqual(set(regions.supported_regions()), TARGETS)

    def test_english_is_four_separate_regions(self):
        """The reason region cannot be derived from lang."""
        english = [r for r in regions.REGISTRY.values() if r.lang == "en"]
        self.assertEqual({r.code for r in english}, {"US", "CA", "AU", "SG"})
        # ...and they are genuinely different clocks, not a formality
        self.assertEqual(len({r.timezone for r in english}), 4)

    def test_timezones_are_iana_not_offsets(self):
        """A stored UTC offset breaks twice a year, and Australia's DST runs
        opposite to the northern hemisphere."""
        from zoneinfo import ZoneInfo
        for r in regions.REGISTRY.values():
            self.assertIn("/", r.timezone, r.code)
            ZoneInfo(r.timezone)          # raises if unknown

    def test_every_region_names_itself_in_every_language(self):
        for r in regions.REGISTRY.values():
            for lang in LANGS:
                self.assertTrue(r.names.get(lang), f"{r.code}/{lang}")

    def test_each_default_lang_is_one_we_support(self):
        for r in regions.REGISTRY.values():
            self.assertIn(r.lang, LANGS, r.code)


class NeverDefaultToUS(unittest.TestCase):
    """The single most important behaviour in this change."""

    def test_unknown_input_is_none_not_us(self):
        for bad in (None, "", "  ", "XX", "GB", "united states", "us-stock"):
            self.assertIsNone(regions.normalize_region(bad), repr(bad))

    def test_a_served_region_normalizes_case_insensitively(self):
        self.assertEqual(regions.normalize_region("kr"), "KR")
        self.assertEqual(regions.normalize_region(" Jp "), "JP")

    def test_derived_lookups_are_none_for_unknown(self):
        self.assertIsNone(regions.default_timezone("XX"))
        self.assertIsNone(regions.default_lang(None))


class Timezone(unittest.TestCase):

    def test_any_real_zone_is_accepted(self):
        """A Korean member living in Berlin must see Berlin's clock, so the
        zone is not restricted to the eight regional defaults."""
        self.assertEqual(regions.normalize_timezone("Europe/Berlin"),
                         "Europe/Berlin")

    def test_garbage_is_rejected_not_guessed(self):
        for bad in (None, "", "Mars/Olympus", "UTC+9", "Asia/Nowhere"):
            self.assertIsNone(regions.normalize_timezone(bad), repr(bad))


class SignupGuess(unittest.TestCase):
    """The country was being computed and thrown away."""

    def _request(self, header="en-US,en;q=0.9"):
        class R:
            headers = {"accept-language": header}
            client = type("C", (), {"host": "203.0.113.9"})()
        return R()

    def test_the_country_now_comes_back(self):
        with patch.object(signup_lang, "_geo_country", return_value="KR"):
            lang, country = signup_lang.resolve_signup_locale(self._request())
        self.assertEqual((lang, country), ("ko", "KR"))

    def test_a_country_we_do_not_serve_still_yields_english(self):
        with patch.object(signup_lang, "_geo_country", return_value="DE"):
            lang, country = signup_lang.resolve_signup_locale(self._request())
        self.assertEqual(lang, "en")
        self.assertEqual(country, "DE")
        # ...and it is NOT a region
        self.assertIsNone(regions.normalize_region(country))

    def test_geo_failure_is_soft(self):
        with patch.object(signup_lang, "_geo_country",
                          side_effect=RuntimeError("timeout")):
            lang, country = signup_lang.resolve_signup_locale(self._request())
        self.assertEqual(lang, "en")
        self.assertIsNone(country)

    def test_the_old_single_value_helper_still_works(self):
        with patch.object(signup_lang, "_geo_country", return_value="JP"):
            self.assertEqual(signup_lang.resolve_signup_lang(self._request()),
                             "ja")


class Schema(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _cols(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(users)")
            return {r[1] for r in cur.fetchall()}
        finally:
            conn.close()

    def test_the_columns_exist_on_a_fresh_sqlite_db(self):
        """The SQLite path is a separate code path from alembic and has
        silently lagged it before."""
        self.assertLessEqual(
            {"region", "timezone", "locale_confirmed_at", "geo_country"},
            self._cols())

    def test_a_new_member_has_no_region_and_no_confirmation(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash, lang, "
                        "geo_country) VALUES (?, ?, ?, ?)",
                        ("a@b.c", "x", "ko", "KR"))
            conn.commit()
            cur.execute("SELECT region, timezone, locale_confirmed_at, "
                        "geo_country FROM users WHERE email = 'a@b.c'")
            row = cur.fetchone()
        finally:
            conn.close()
        # the guess is stored, and it grants nothing
        self.assertEqual(row["geo_country"], "KR")
        self.assertIsNone(row["region"])
        self.assertIsNone(row["locale_confirmed_at"])

    def test_alembic_mirrors_the_sqlite_columns(self):
        """Prod is MySQL; a column added only to database.py never lands."""
        mig = (SERVER_DIR / "alembic" / "versions"
               / "0035_user_region.py").read_text()
        for col in ("region", "timezone", "locale_confirmed_at", "geo_country"):
            self.assertIn(f'ADD COLUMN {col} ', mig, col)


class Options(unittest.TestCase):

    def test_the_picker_is_localized(self):
        ko = {o["region"]: o["name"] for o in regions.options("ko")}
        en = {o["region"]: o["name"] for o in regions.options("en")}
        self.assertEqual(ko["KR"], "대한민국")
        self.assertEqual(en["KR"], "South Korea")
        self.assertNotEqual(ko["JP"], en["JP"])

    def test_an_unsupported_ui_language_falls_back_to_english(self):
        de = {o["region"]: o["name"] for o in regions.options("de")}
        self.assertEqual(de["KR"], "South Korea")

    def test_every_option_carries_a_zone_and_a_suggested_language(self):
        for o in regions.options("en"):
            self.assertTrue(o["timezone"])
            self.assertIn(o["suggested_lang"], LANGS)

    def test_the_picker_covers_every_served_region(self):
        self.assertEqual({o["region"] for o in regions.options("en")}, TARGETS)


if __name__ == "__main__":
    unittest.main()
