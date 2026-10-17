import io
import unittest
from unittest.mock import patch

from flask import Flask

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
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        return None

    def fetchone(self):
        return (1, "Test User", "test@example.com")


class TestConnection:
    def cursor(self):
        return TestCursor()

    def close(self):
        return None


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

        with app.test_client() as client, patch("routes.get_db_connection", return_value=TestConnection()):
            client.set_cookie("datacleanpro_session", "test-session")
            response = client.post("/api/clean", data=data)

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
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


if __name__ == "__main__":
    unittest.main()
