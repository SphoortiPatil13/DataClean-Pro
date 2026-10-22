import io
import json
import unittest
from datetime import datetime
from unittest.mock import patch

from flask import Flask
import pymysql

from routes import api_bp
from services.csv_cleaning import clean_dataframe, read_csv_for_cleaning


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
        if "INSERT INTO cleaning_history" in query and self.connection.history_insert_error:
            raise self.connection.history_insert_error
        return None

    def fetchone(self):
        return self.connection.user

    def fetchall(self):
        return self.connection.history_rows

    @property
    def lastrowid(self):
        return 42


class TestConnection:
    def __init__(self, user_id=1, history_rows=None, history_insert_error=None):
        self.user = (user_id, "Test User", "test@example.com")
        self.history_rows = history_rows or []
        self.history_insert_error = history_insert_error
        self.queries = []
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
        self.assertIn("user_id", insert_query)
        self.assertEqual(insert_params[:2], (1, "sample.csv"))
        self.assertEqual(json.loads(insert_params[2]), [
            "Trim leading and trailing whitespace",
            "Fill missing values with Not Available",
        ])
        self.assertEqual(insert_params[3:], (2, 2))
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

    def test_history_endpoint_returns_current_users_rows_newest_first(self):
        row = (
            8,
            "report.csv",
            '["Remove duplicate rows"]',
            12,
            10,
            datetime(2026, 10, 17, 8, 30),
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
        user_one_row = (1, "one.csv", "[]", 2, 2, datetime(2026, 10, 17, 8, 0))
        user_two_row = (2, "two.csv", "[]", 4, 3, datetime(2026, 10, 17, 9, 0))
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


if __name__ == "__main__":
    unittest.main()
