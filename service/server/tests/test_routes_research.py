"""Integration tests for research export routes (GET /api/research/*)."""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app
from routes_shared import utc_now_iso_z


def _create_agent(name: str = "research-agent", token_raw: str = "tok-research") -> int:
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO agents (name, token, token_hash, points, cash, created_at, updated_at)
        VALUES (?, NULL, ?, 0, 100000.0, ?, ?)
        """,
        (name, token_hash, utc_now_iso_z(), utc_now_iso_z()),
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id


class ResearchDatasetListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_datasets_endpoint_returns_200(self) -> None:
        resp = self.client.get("/api/research/datasets")
        self.assertEqual(resp.status_code, 200)

    def test_datasets_response_has_datasets_key(self) -> None:
        resp = self.client.get("/api/research/datasets")
        body = resp.json()
        self.assertIn("datasets", body)
        self.assertIsInstance(body["datasets"], list)

    def test_datasets_includes_known_exports(self) -> None:
        resp = self.client.get("/api/research/datasets")
        datasets = resp.json()["datasets"]
        # Core datasets that always exist
        for expected in ("agents.csv", "events.csv", "signals.csv"):
            self.assertIn(expected, datasets)

    def test_datasets_list_is_nonempty(self) -> None:
        resp = self.client.get("/api/research/datasets")
        self.assertGreater(len(resp.json()["datasets"]), 0)


class ResearchEventsEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_events_endpoint_returns_200(self) -> None:
        resp = self.client.get("/api/research/events")
        self.assertEqual(resp.status_code, 200)

    def test_events_response_shape(self) -> None:
        resp = self.client.get("/api/research/events")
        body = resp.json()
        self.assertIn("columns", body)
        self.assertIn("events", body)
        self.assertIn("limit", body)
        self.assertIn("offset", body)

    def test_events_columns_list_nonempty(self) -> None:
        resp = self.client.get("/api/research/events")
        self.assertIsInstance(resp.json()["columns"], list)
        self.assertGreater(len(resp.json()["columns"]), 0)

    def test_events_empty_on_fresh_db(self) -> None:
        resp = self.client.get("/api/research/events")
        self.assertEqual(resp.json()["events"], [])

    def test_events_limit_param_respected(self) -> None:
        resp = self.client.get("/api/research/events?limit=5")
        self.assertEqual(resp.json()["limit"], 5)

    def test_events_offset_param_returned(self) -> None:
        resp = self.client.get("/api/research/events?offset=10")
        self.assertEqual(resp.json()["offset"], 10)


class ResearchSchemaEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_for_events_returns_200(self) -> None:
        resp = self.client.get("/api/research/schema/events.csv")
        self.assertEqual(resp.status_code, 200)

    def test_schema_has_properties(self) -> None:
        resp = self.client.get("/api/research/schema/events.csv")
        body = resp.json()
        # Schema endpoint returns a JSON Schema object
        self.assertIn("properties", body)
        self.assertIsInstance(body["properties"], dict)

    def test_schema_for_agents_has_properties(self) -> None:
        resp = self.client.get("/api/research/schema/agents.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("properties", resp.json())

    def test_schema_for_unknown_dataset_returns_400(self) -> None:
        resp = self.client.get("/api/research/schema/no-such-dataset")
        self.assertEqual(resp.status_code, 400)


class ResearchExportCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agents_csv_export_returns_csv_content_type(self) -> None:
        resp = self.client.get("/api/research/export/agents.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers.get("content-type", ""))

    def test_agents_csv_has_header_row(self) -> None:
        resp = self.client.get("/api/research/export/agents.csv")
        lines = resp.text.strip().splitlines()
        self.assertGreater(len(lines), 0)
        # Header line must contain known column names
        self.assertIn("agent_id", lines[0])

    def test_events_csv_export_succeeds(self) -> None:
        resp = self.client.get("/api/research/export/events.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers.get("content-type", ""))

    def test_signals_csv_export_succeeds(self) -> None:
        resp = self.client.get("/api/research/export/signals.csv")
        self.assertEqual(resp.status_code, 200)

    def test_unknown_dataset_csv_returns_400(self) -> None:
        resp = self.client.get("/api/research/export/no-such-dataset.csv")
        self.assertEqual(resp.status_code, 400)

    def test_csv_content_disposition_header_present(self) -> None:
        resp = self.client.get("/api/research/export/agents.csv")
        self.assertIn("attachment", resp.headers.get("content-disposition", ""))


class ResearchExportJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agents_json_export_returns_200(self) -> None:
        resp = self.client.get("/api/research/export/agents.json")
        self.assertEqual(resp.status_code, 200)

    def test_json_export_has_required_keys(self) -> None:
        resp = self.client.get("/api/research/export/agents.json")
        body = resp.json()
        self.assertIn("dataset", body)
        self.assertIn("columns", body)
        self.assertIn("rows", body)
        self.assertIn("limit", body)
        self.assertIn("offset", body)

    def test_json_export_dataset_name_normalized(self) -> None:
        resp = self.client.get("/api/research/export/agents.json")
        self.assertEqual(resp.json()["dataset"], "agents.csv")

    def test_unknown_dataset_json_returns_400(self) -> None:
        resp = self.client.get("/api/research/export/no-such-dataset.json")
        self.assertEqual(resp.status_code, 400)

    def test_json_export_rows_is_list(self) -> None:
        resp = self.client.get("/api/research/export/agents.json")
        self.assertIsInstance(resp.json()["rows"], list)


class ResearchShortcutCsvTests(unittest.TestCase):
    """Test the convenience shortcut CSV endpoints (/api/research/*.csv)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agents_shortcut_csv_returns_200(self) -> None:
        resp = self.client.get("/api/research/agents.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers.get("content-type", ""))

    def test_events_shortcut_csv_returns_200(self) -> None:
        resp = self.client.get("/api/research/events.csv")
        self.assertEqual(resp.status_code, 200)

    def test_signals_shortcut_csv_returns_200(self) -> None:
        resp = self.client.get("/api/research/signals.csv")
        self.assertEqual(resp.status_code, 200)

    def test_network_edges_shortcut_csv_returns_200(self) -> None:
        resp = self.client.get("/api/research/network_edges.csv")
        self.assertEqual(resp.status_code, 200)

    def test_agents_csv_contains_seeded_agent(self) -> None:
        agent_id = _create_agent("csv-export-agent", "tok-csv")
        resp = self.client.get("/api/research/agents.csv")
        self.assertEqual(resp.status_code, 200)
        # agent_id should appear in the CSV body (anonymized as hash, not raw id)
        # Just verify we have at least one data row beyond the header
        lines = resp.text.strip().splitlines()
        self.assertGreaterEqual(len(lines), 2)  # header + at least 1 row


if __name__ == "__main__":
    unittest.main()
