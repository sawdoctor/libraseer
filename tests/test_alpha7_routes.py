import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("STACKARR_NO_SCHED", "true")

from flask import Flask

from stackarr import config, db, routes


class Alpha7RouteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_db_path = db.DB_PATH
        self._original_data_dir = config.DATA_DIR
        config.DATA_DIR = self._tmp.name
        db.DB_PATH = os.path.join(self._tmp.name, "test.db")
        db.init()
        with db.conn() as connection:
            connection.execute(
                "INSERT INTO users (username,password_hash,role) VALUES ('tester','x','admin')"
            )
            self.user_id = connection.execute(
                "SELECT id FROM users WHERE username='tester'"
            ).fetchone()["id"]

        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(routes.bp)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["uid"] = self.user_id

    def tearDown(self):
        db.DB_PATH = self._original_db_path
        config.DATA_DIR = self._original_data_dir
        routes._LAST_HEAVY.clear()
        self._tmp.cleanup()

    def test_suggest_uses_local_data_without_remote_search(self):
        with db.conn() as connection:
            connection.execute(
                "INSERT INTO library (item_id,title,author,asin,format,last_seen) "
                "VALUES ('1','Dune','Frank Herbert','B001','audiobook',datetime('now'))"
            )
        with patch.object(routes, "_search_catalog", side_effect=AssertionError("remote search")):
            response = self.client.get("/api/suggest?q=dune")
        self.assertEqual(200, response.status_code)
        self.assertEqual("B001", response.get_json()[0]["asin"])

    def test_manual_prowlarr_fallback_updates_existing_request(self):
        with db.conn() as connection:
            cursor = connection.execute(
                "INSERT INTO requests (user_id,asin,title,author,status,format) "
                "VALUES (?,?,?,?,?,?)",
                (self.user_id, "B002", "Project Hail Mary", "Andy Weir", "failed", "audiobook"),
            )
            request_id = cursor.lastrowid

        result = {"ok": True, "ref": "task-7", "detail": "Queued through Prowlarr"}
        with patch.object(routes.audiobridge, "fallback_source", return_value="prowlarr"), patch.object(
            routes, "_acquisition_handoff", return_value=result
        ) as handoff:
            response = self.client.post(f"/api/request/{request_id}/prowlarr-fallback")

        self.assertEqual(200, response.status_code)
        handoff.assert_called_once_with(
            "Project Hail Mary",
            "Andy Weir",
            "B002",
            fmt="audiobook",
            audiobook_source="prowlarr",
        )
        with db.conn() as connection:
            row = connection.execute(
                "SELECT status,chaptarr_ref FROM requests WHERE id=?", (request_id,)
            ).fetchone()
        self.assertEqual("handed", row["status"])
        self.assertEqual("task-7", row["chaptarr_ref"])


if __name__ == "__main__":
    unittest.main()
