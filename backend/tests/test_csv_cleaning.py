import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from flask import Flask
import pymysql

from routes import api_bp
from services import cleaned_file_storage
from services.csv_cleaning import (
    clean_dataframe,
    get_data_quality_stats,
    read_csv_for_cleaning,
)


def clean_csv(
    source,
    *,
    missing_strategy="fill",
    missing_placeholder="Not Provided",
    remove_empty_rows=False,
):
    dataframe = read_csv_for_cleaning(io.StringIO(source))
    return clean_dataframe(
        dataframe,
        remove_empty_rows=remove_empty_rows,
        remove_duplicates=False,
        trim_whitespace=False,
        handle_missing=True,
        missing_strategy=missing_strategy,
        missing_placeholder=missing_placeholder,
    )


class TestCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        self.connection.queries.append((query, params))
        self.connection.last_query = query
        if "INSERT INTO cleaning_history" in query and self.connection.history_insert_error:
            raise self.connection.history_insert_error
        return None

    def fetchone(self):
        if self.connection.last_query and "COUNT(*) AS total_cleaning_jobs" in self.connection.last_query:
            return self.connection.statistics_row
        if self.connection.last_query and "FROM cleaning_history" in self.connection.last_query:
            return self.connection.history_record
        return self.connection.user

    def fetchall(self):
        return self.connection.history_rows

    @property
    def lastrowid(self):
        return 42


class TestConnection:
    def __init__(
        self,
        user_id=1,
        history_rows=None,
        history_record=None,
        history_insert_error=None,
        statistics_row=None,
    ):
        self.user = (user_id, "Test User", "test@example.com")
        self.history_rows = history_rows or []
        self.history_record = history_record
        self.history_insert_error = history_insert_error
        self.statistics_row = statistics_row or (0, 0, 0)
        self.queries = []
        self.last_query = None
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return TestCursor(self)

    def close(self):
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class CsvCleaningTests(unittest.TestCase):
    def setUp(self):
        self.storage_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage_directory.cleanup)
        self.storage_patch = patch.object(
            cleaned_file_storage,
            "CLEANED_FILE_STORAGE_DIR",
            Path(self.storage_directory.name),
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

    def test_data_quality_stats_count_missing_duplicate_and_empty_rows(self):
        dataframe = read_csv_for_cleaning(
            io.StringIO("Name,Score\nAda,10\nAda,10\n,\nGrace,\n")
        )

        self.assertEqual(get_data_quality_stats(dataframe), {
            "total_rows": 4,
            "missing_values": 3,
            "duplicate_rows": 1,
            "empty_rows": 1,
        })

    def test_data_quality_stats_support_empty_dataframe(self):
        dataframe = read_csv_for_cleaning(io.StringIO("Name,Score\n"))

        self.assertEqual(get_data_quality_stats(dataframe), {
            "total_rows": 0,
            "missing_values": 0,
            "duplicate_rows": 0,
            "empty_rows": 0,
        })

    def test_placeholder_fills_numeric_and_text_columns_without_changing_values(self):
        cleaned, unfilled = clean_csv(
            "Age,City\n20,London\n,Paris\n23,\n",
            missing_placeholder="N/A",
        )

        self.assertEqual(cleaned["Age"].tolist(), [20, "N/A", 23])
        self.assertEqual(cleaned["City"].tolist(), ["London", "Paris", "N/A"])
        self.assertEqual(unfilled, [])

    def test_placeholder_fills_all_missing_columns(self):
        cleaned, unfilled = clean_csv("Name,Empty\nAda,\nGrace,\n")

        self.assertEqual(cleaned["Empty"].tolist(), ["Not Provided", "Not Provided"])
        self.assertEqual(unfilled, [])

    def test_remove_missing_strategy_removes_incomplete_rows(self):
        cleaned, unfilled = clean_csv(
            "Age,Name\n20,Ada\n,Grace\n",
            missing_strategy="remove",
        )

        self.assertEqual(cleaned.to_dict(orient="records"), [{"Age": 20, "Name": "Ada"}])
        self.assertEqual(unfilled, [])

    def test_clean_endpoint_csv_contains_selected_placeholder(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        data = {
            "file": (io.BytesIO(b"Age,City\n20,London\n,NA\n"), "sample.csv"),
            "remove_duplicates": "false",
            "remove_empty_rows": "false",
            "trim_whitespace": "true",
            "handle_missing": "true",
            "missing_strategy": "fill",
            "missing_placeholder": "Not Available",
        }

        connection = TestConnection()
        with app.test_client() as client, patch("routes.get_db_connection", return_value=connection):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.post("/api/clean", data=data)

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["history_id"], 42)
        insert_query, insert_params = next(
            query for query in connection.queries if "INSERT INTO cleaning_history" in query[0]
        )
        self.assertRegex(insert_params[-1], r"^[0-9a-f]{32}$")
        self.assertEqual(
            cleaned_file_storage.get_cleaned_csv_path(insert_params[-1]).read_bytes().decode("utf-8"),
            payload["cleaned_csv"],
        )
        self.assertEqual(payload["quality_report"], {
            "before": {
                "total_rows": 2,
                "missing_values": 2,
                "duplicate_rows": 0,
                "empty_rows": 1,
            },
            "after": {
                "total_rows": 2,
                "missing_values": 0,
                "duplicate_rows": 0,
                "empty_rows": 0,
            },
            "rows_removed": 0,
        })
        self.assertIn("user_id", insert_query)
        self.assertEqual(insert_params[:2], (1, "sample.csv"))
        self.assertEqual(json.loads(insert_params[2]), [
            "Trim leading and trailing whitespace",
            "Fill missing values with Not Available",
        ])
        self.assertEqual(insert_params[3:5], (2, 2))
        self.assertTrue(connection.committed)
        self.assertEqual(
            payload["cleaned_csv"].splitlines(),
            ["Age,City", "20.0,London", "Not Available,Not Available"],
        )
        self.assertEqual(payload["preview"][1], {
            "Age": "Not Available",
            "City": "Not Available",
        })

    def test_clean_endpoint_rejects_unsupported_placeholder(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        data = {
            "file": (io.BytesIO(b"Age\n20\n"), "sample.csv"),
            "remove_duplicates": "false",
            "remove_empty_rows": "false",
            "trim_whitespace": "true",
            "handle_missing": "true",
            "missing_strategy": "fill",
            "missing_placeholder": "guessed value",
        }

        with app.test_client() as client, patch("routes.get_db_connection", return_value=TestConnection()):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.post("/api/clean", data=data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "error")

    def test_failed_cleaning_does_not_create_history(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        connection = TestConnection()
        data = {
            "file": (io.BytesIO(b""), "empty.csv"),
            "remove_duplicates": "false",
            "remove_empty_rows": "false",
            "trim_whitespace": "false",
            "handle_missing": "false",
            "missing_strategy": "remove",
        }

        with app.test_client() as client, patch("routes.get_db_connection", return_value=connection):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.post("/api/clean", data=data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(any("INSERT INTO cleaning_history" in query for query, _ in connection.queries))

    def test_history_save_failure_logs_database_code_without_exposing_details(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        connection = TestConnection(
            history_insert_error=pymysql.ProgrammingError(1146, "Table does not exist")
        )
        data = {
            "file": (io.BytesIO(b"Age\n20\n"), "sample.csv"),
            "remove_duplicates": "false",
            "remove_empty_rows": "false",
            "trim_whitespace": "false",
            "handle_missing": "false",
            "missing_strategy": "remove",
        }

        with (
            app.test_client() as client,
            patch("routes.get_db_connection", return_value=connection),
            self.assertLogs(app.logger, level="ERROR") as captured,
        ):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.post("/api/clean", data=data)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["message"],
            "The CSV was cleaned, but its history could not be saved. Please try again.",
        )
        self.assertTrue(connection.rolled_back)
        self.assertIn("code=1146", captured.output[0])
        self.assertNotIn("Table does not exist", captured.output[0])
        insert_params = next(
            params for query, params in connection.queries
            if "INSERT INTO cleaning_history" in query
        )
        self.assertFalse(cleaned_file_storage.get_cleaned_csv_path(insert_params[-1]).exists())

    def test_cleaned_csv_can_be_downloaded_after_a_fresh_request(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        clean_connection = TestConnection()
        data = {
            "file": (io.BytesIO(b"Name,Score\n Ada ,10\n"), "sample.csv"),
            "remove_duplicates": "false",
            "remove_empty_rows": "false",
            "trim_whitespace": "true",
            "handle_missing": "false",
            "missing_strategy": "remove",
        }

        with app.test_client() as client:
            client.set_cookie("datacleanpro_session", "test-session")
            with patch(
                "routes.get_db_connection",
                side_effect=[TestConnection(), clean_connection],
            ):
                clean_response = client.post("/api/clean", data=data)

            self.assertEqual(clean_response.status_code, 200)
            cleaned_csv = clean_response.get_json()["cleaned_csv"]
            insert_params = next(
                params for query, params in clean_connection.queries
                if "INSERT INTO cleaning_history" in query
            )
            file_id = insert_params[-1]
            self.assertEqual(
                cleaned_file_storage.get_cleaned_csv_path(file_id).read_bytes().decode("utf-8"),
                cleaned_csv,
            )

            history_connection = TestConnection(
                history_record=("sample.csv", file_id)
            )
            with patch(
                "routes.get_db_connection",
                side_effect=[TestConnection(), history_connection],
            ):
                download_response = client.get(
                    f"/api/cleaning-history/{clean_response.get_json()['history_id']}/download"
                )

        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.mimetype, "text/csv")
        self.assertIn("sample-cleaned.csv", download_response.headers["Content-Disposition"])
        self.assertEqual(download_response.get_data(as_text=True), cleaned_csv)
        self.assertEqual(
            history_connection.queries[0][1],
            (clean_response.get_json()["history_id"], 1),
        )
        download_response.close()

    def test_cleaned_csv_download_requires_authentication(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        with app.test_client() as client, patch("routes.get_db_connection") as get_connection:
            response = client.get("/api/cleaning-history/42/download")

        self.assertEqual(response.status_code, 401)
        get_connection.assert_not_called()

    def test_cleaning_storage_failure_does_not_create_history(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        auth_connection = TestConnection()
        data = {
            "file": (io.BytesIO(b"Name\nAda\n"), "sample.csv"),
            "remove_duplicates": "false",
            "remove_empty_rows": "false",
            "trim_whitespace": "false",
            "handle_missing": "false",
            "missing_strategy": "remove",
        }

        with app.test_client() as client, patch(
            "routes.get_db_connection",
            return_value=auth_connection,
        ), patch(
            "routes.save_cleaned_csv",
            side_effect=OSError("storage unavailable"),
        ), self.assertLogs(app.logger, level="ERROR"):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.post("/api/clean", data=data)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["message"],
            "The CSV was cleaned, but its download could not be made available. Please try again.",
        )
        self.assertFalse(any(
            "INSERT INTO cleaning_history" in query for query, _ in auth_connection.queries
        ))

    def test_cleaned_csv_download_is_scoped_to_authenticated_user(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        history_connection = TestConnection(user_id=27, history_record=None)

        with app.test_client() as client, patch(
            "routes.get_db_connection",
            side_effect=[TestConnection(user_id=27), history_connection],
        ):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.get("/api/cleaning-history/42/download")

        self.assertEqual(response.status_code, 404)
        query, params = history_connection.queries[0]
        self.assertIn("WHERE id = %s AND user_id = %s", query)
        self.assertEqual(params, (42, 27))

    def test_cleaned_csv_download_returns_not_found_for_missing_file_or_record(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        missing_file_connection = TestConnection(
            history_record=("missing.csv", "a" * 32)
        )
        missing_record_connection = TestConnection(history_record=None)
        invalid_reference_connection = TestConnection(
            history_record=("unsafe.csv", ".." * 16)
        )
        with app.test_client() as client, patch(
            "routes.get_db_connection",
            side_effect=[
                TestConnection(), missing_file_connection,
                TestConnection(), missing_record_connection,
                TestConnection(), invalid_reference_connection,
            ],
        ):
            client.set_cookie("datacleanpro_session", "test-session")
            missing_file_response = client.get("/api/cleaning-history/42/download")
            missing_record_response = client.get("/api/cleaning-history/9999/download")
            invalid_reference_response = client.get("/api/cleaning-history/10000/download")

        self.assertEqual(missing_file_response.status_code, 404)
        self.assertEqual(missing_record_response.status_code, 404)
        self.assertEqual(invalid_reference_response.status_code, 404)

    def test_history_endpoint_returns_current_users_rows_newest_first(self):
        row = (
            8,
            "report.csv",
            '["Remove duplicate rows"]',
            12,
            10,
            datetime(2026, 10, 17, 8, 30),
            "f" * 32,
        )
        auth_connection = TestConnection(user_id=13)
        history_connection = TestConnection(history_rows=[row])
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        with app.test_client() as client, patch(
            "routes.get_db_connection",
            side_effect=[auth_connection, history_connection],
        ):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.get("/api/cleaning-history")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["history"], [{
            "id": 8,
            "filename": "report.csv",
            "operations": ["Remove duplicate rows"],
            "original_row_count": 12,
            "final_row_count": 10,
            "created_at": "2026-10-17T08:30:00",
            "has_cleaned_file": True,
        }])
        query, params = history_connection.queries[0]
        self.assertIn("WHERE user_id = %s", query)
        self.assertIn("ORDER BY created_at DESC, id DESC", query)
        self.assertEqual(params, (13,))

    def test_history_endpoint_requires_authentication(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        with app.test_client() as client, patch("routes.get_db_connection") as get_connection:
            response = client.get("/api/cleaning-history")

        self.assertEqual(response.status_code, 401)
        get_connection.assert_not_called()

    def test_history_endpoint_isolates_users_by_authenticated_user_id(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        user_one_row = (1, "one.csv", "[]", 2, 2, datetime(2026, 10, 17, 8, 0), None)
        user_two_row = (2, "two.csv", "[]", 4, 3, datetime(2026, 10, 17, 9, 0), "f" * 32)
        connections = [
            TestConnection(user_id=21),
            TestConnection(history_rows=[user_one_row]),
            TestConnection(user_id=34),
            TestConnection(history_rows=[user_two_row]),
        ]

        with app.test_client() as first_client, app.test_client() as second_client, patch(
            "routes.get_db_connection",
            side_effect=connections,
        ):
            first_client.set_cookie("datacleanpro_session", "first-session")
            second_client.set_cookie("datacleanpro_session", "second-session")
            first_response = first_client.get("/api/cleaning-history")
            second_response = second_client.get("/api/cleaning-history")

        self.assertEqual(first_response.get_json()["history"][0]["filename"], "one.csv")
        self.assertEqual(second_response.get_json()["history"][0]["filename"], "two.csv")
        self.assertEqual(connections[1].queries[0][1], (21,))
        self.assertEqual(connections[3].queries[0][1], (34,))

    def test_dashboard_stats_returns_user_totals_and_recent_activity(self):
        recent_rows = [
            ("latest.csv", 12, 9, datetime(2026, 10, 25, 9, 30)),
            ("older.csv", 5, 6, datetime(2026, 10, 24, 8, 15)),
        ]
        connection = TestConnection(
            user_id=13,
            history_rows=recent_rows,
            statistics_row=(4, 38, 7),
        )
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        with app.test_client() as client, patch(
            "routes.get_db_connection",
            side_effect=[TestConnection(user_id=13), connection],
        ):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.get("/api/dashboard-stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "status": "success",
            "statistics": {
                "total_cleaning_jobs": 4,
                "rows_reviewed": 38,
                "total_rows_removed": 7,
                "recent_activity": [
                    {
                        "filename": "latest.csv",
                        "original_row_count": 12,
                        "final_row_count": 9,
                        "rows_removed": 3,
                        "created_at": "2026-10-25T09:30:00",
                    },
                    {
                        "filename": "older.csv",
                        "original_row_count": 5,
                        "final_row_count": 6,
                        "rows_removed": 0,
                        "created_at": "2026-10-24T08:15:00",
                    },
                ],
            },
        })
        totals_query, totals_params = connection.queries[0]
        self.assertIn("COUNT(*) AS total_cleaning_jobs", totals_query)
        self.assertIn("SUM(original_row_count)", totals_query)
        self.assertIn("GREATEST(", totals_query)
        self.assertIn("CAST(original_row_count AS SIGNED)", totals_query)
        self.assertIn("CAST(final_row_count AS SIGNED)", totals_query)
        self.assertIn("WHERE user_id = %s", totals_query)
        self.assertEqual(totals_params, (13,))
        recent_query, recent_params = connection.queries[1]
        self.assertIn("WHERE user_id = %s", recent_query)
        self.assertIn("ORDER BY created_at DESC, id DESC", recent_query)
        self.assertIn("LIMIT 5", recent_query)
        self.assertEqual(recent_params, (13,))

    def test_dashboard_stats_returns_zeros_and_empty_activity_without_history(self):
        connection = TestConnection(
            user_id=13,
            history_rows=[],
            statistics_row=(0, 0, 0),
        )
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        with app.test_client() as client, patch(
            "routes.get_db_connection",
            side_effect=[TestConnection(user_id=13), connection],
        ):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.get("/api/dashboard-stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["statistics"], {
            "total_cleaning_jobs": 0,
            "rows_reviewed": 0,
            "total_rows_removed": 0,
            "recent_activity": [],
        })

    def test_dashboard_stats_requires_authentication(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)

        with app.test_client() as client, patch("routes.get_db_connection") as get_connection:
            response = client.get("/api/dashboard-stats")

        self.assertEqual(response.status_code, 401)
        get_connection.assert_not_called()

    def test_dashboard_stats_isolates_users_by_authenticated_user_id(self):
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SESSION_COOKIE_NAME="datacleanpro_session",
            FRONTEND_ORIGINS=[],
        )
        app.register_blueprint(api_bp)
        connections = [
            TestConnection(user_id=21),
            TestConnection(
                user_id=21,
                statistics_row=(1, 2, 1),
                history_rows=[("one.csv", 2, 1, datetime(2026, 10, 17, 8, 0))],
            ),
            TestConnection(user_id=34),
            TestConnection(
                user_id=34,
                statistics_row=(1, 4, 1),
                history_rows=[("two.csv", 4, 3, datetime(2026, 10, 17, 9, 0))],
            ),
        ]

        with app.test_client() as first_client, app.test_client() as second_client, patch(
            "routes.get_db_connection",
            side_effect=connections,
        ):
            first_client.set_cookie("datacleanpro_session", "first-session")
            second_client.set_cookie("datacleanpro_session", "second-session")
            first_response = first_client.get("/api/dashboard-stats")
            second_response = second_client.get("/api/dashboard-stats")

        first_stats = first_response.get_json()["statistics"]
        second_stats = second_response.get_json()["statistics"]
        self.assertEqual(first_stats["rows_reviewed"], 2)
        self.assertEqual(first_stats["recent_activity"][0]["filename"], "one.csv")
        self.assertEqual(second_stats["rows_reviewed"], 4)
        self.assertEqual(second_stats["recent_activity"][0]["filename"], "two.csv")
        self.assertEqual(connections[1].queries[0][1], (21,))
        self.assertEqual(connections[1].queries[1][1], (21,))
        self.assertEqual(connections[3].queries[0][1], (34,))
        self.assertEqual(connections[3].queries[1][1], (34,))


if __name__ == "__main__":
    unittest.main()
