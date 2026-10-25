import json
import hashlib
import hmac
import re
import secrets
import uuid
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, send_file
import pymysql
import pandas as pd
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import MAX_UPLOAD_SIZE
from services.csv_cleaning import (
    MISSING_PLACEHOLDERS,
    clean_dataframe,
    get_data_quality_stats,
    read_csv_for_cleaning,
)
from services.database import get_db_connection
from services.cleaned_file_storage import (
    delete_cleaned_csv,
    get_cleaned_csv_path,
    save_cleaned_csv,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
DUMMY_PASSWORD_HASH = generate_password_hash("datacleanpro-nonexistent-account")
SESSION_DURATION_SECONDS = 8 * 60 * 60


def hash_session_token(session_token):
    secret_key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(secret_key, session_token.encode("utf-8"), hashlib.sha256).hexdigest()


@api_bp.app_errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify(status="error", message="CSV file exceeds the 5 MB upload limit"), 413


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        session_token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
        if not session_token or len(session_token) > 128:
            return jsonify(status="error", message="Authentication required"), 401

        connection = None
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT users.id, users.name, users.email
                    FROM auth_sessions
                    JOIN users ON users.id = auth_sessions.user_id
                    WHERE auth_sessions.token_hash = %s
                      AND auth_sessions.expires_at > UTC_TIMESTAMP()
                    LIMIT 1
                    """,
                    (hash_session_token(session_token),),
                )
                user = cursor.fetchone()
        except (pymysql.MySQLError, OSError):
            return jsonify(
                status="error",
                message="Authentication is temporarily unavailable. Please try again later.",
            ), 503
        finally:
            if connection is not None:
                connection.close()

        if user is None:
            return jsonify(status="error", message="Authentication required"), 401
        g.authenticated_user = {"id": user[0], "name": user[1], "email": user[2]}
        return view(*args, **kwargs)

    return wrapped


def require_trusted_origin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        origin = request.headers.get("Origin")
        if origin and origin not in current_app.config["FRONTEND_ORIGINS"]:
            return jsonify(status="error", message="Request origin is not allowed"), 403
        return view(*args, **kwargs)

    return wrapped


@api_bp.get("/health")
def health():
    return jsonify(status="success", message="DataCleanPro API is running")


@api_bp.get("/db-test")
def db_test():
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return jsonify(
            status="success",
            connected=True,
            message="Database connection successful",
        )
    except (pymysql.MySQLError, OSError):
        return jsonify(
            status="error",
            connected=False,
            message="Database connection failed",
        ), 503
    finally:
        if connection is not None:
            connection.close()


@api_bp.post("/register")
@require_trusted_origin
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="A JSON object is required"), 400

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not all(isinstance(value, str) for value in (name, email, password)):
        return jsonify(status="error", message="Name, email, and password are required"), 400

    name = name.strip()
    email = email.strip().lower()
    if (
        not name
        or len(name) > 100
        or len(email) > 150
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        or not password.strip()
    ):
        return jsonify(status="error", message="Invalid registration input"), 400

    password_hash = generate_password_hash(password)
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (email,))
            if cursor.fetchone() is not None:
                return jsonify(status="error", message="Email is already registered"), 409

            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, password_hash),
            )
        connection.commit()
        return jsonify(status="success", message="User registered successfully"), 201
    except pymysql.IntegrityError as error:
        if connection is not None:
            connection.rollback()
        if error.args and error.args[0] == 1062:
            return jsonify(status="error", message="Email is already registered"), 409
        return jsonify(status="error", message="Registration failed due to a server error"), 500
    except pymysql.MySQLError:
        if connection is not None:
            connection.rollback()
        return jsonify(status="error", message="Registration failed due to a server error"), 500
    finally:
        if connection is not None:
            connection.close()


@api_bp.post("/login")
@require_trusted_origin
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="A JSON object is required"), 400

    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify(status="error", message="Email and password are required"), 400

    email = email.strip().lower()
    if (
        not email
        or len(email) > 150
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        or not password.strip()
    ):
        return jsonify(status="error", message="Invalid login input"), 400

    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name, email, password FROM users WHERE email = %s LIMIT 1", (email,))
            user = cursor.fetchone()

        stored_password_hash = user[3] if user is not None else DUMMY_PASSWORD_HASH
        if not check_password_hash(stored_password_hash, password) or user is None:
            return jsonify(status="error", message="Invalid email or password"), 401

        session_token = secrets.token_urlsafe(32)
        token_hash = hash_session_token(session_token)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM auth_sessions WHERE expires_at <= UTC_TIMESTAMP()")
            cursor.execute(
                """
                INSERT INTO auth_sessions (token_hash, user_id, expires_at)
                VALUES (%s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND))
                """,
                (token_hash, user[0], SESSION_DURATION_SECONDS),
            )
        connection.commit()
        response = jsonify(
            status="success",
            message="Login successful",
            user={"name": user[1], "email": user[2]},
        )
        response.set_cookie(
            current_app.config["SESSION_COOKIE_NAME"],
            session_token,
            max_age=SESSION_DURATION_SECONDS,
            httponly=current_app.config["SESSION_COOKIE_HTTPONLY"],
            secure=current_app.config["SESSION_COOKIE_SECURE"],
            samesite=current_app.config["SESSION_COOKIE_SAMESITE"],
            path=current_app.config["SESSION_COOKIE_PATH"],
        )
        return response, 200
    except (pymysql.MySQLError, OSError):
        if connection is not None:
            connection.rollback()
        return jsonify(
            status="error",
            message="Login is temporarily unavailable. Please try again later.",
        ), 503
    finally:
        if connection is not None:
            connection.close()


@api_bp.get("/session")
@login_required
def session_status():
    return jsonify(status="success", authenticated=True, user={
        "name": g.authenticated_user["name"],
        "email": g.authenticated_user["email"],
    })


@api_bp.post("/logout")
@require_trusted_origin
def logout():
    session_token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if session_token and len(session_token) <= 128:
        connection = None
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM auth_sessions WHERE token_hash = %s",
                    (hash_session_token(session_token),),
                )
            connection.commit()
        except (pymysql.MySQLError, OSError):
            if connection is not None:
                connection.rollback()
            return jsonify(status="error", message="Logout could not be completed. Please try again."), 503
        finally:
            if connection is not None:
                connection.close()

    response = jsonify(status="success", message="Logged out successfully")
    response.delete_cookie(
        current_app.config["SESSION_COOKIE_NAME"],
        path=current_app.config["SESSION_COOKIE_PATH"],
        httponly=current_app.config["SESSION_COOKIE_HTTPONLY"],
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        samesite=current_app.config["SESSION_COOKIE_SAMESITE"],
    )
    return response


@api_bp.post("/upload")
@require_trusted_origin
@login_required
def upload_csv():
    uploaded_file = request.files.get("file")
    if uploaded_file is None:
        return jsonify(status="error", message="Please provide a CSV file"), 400

    filename = secure_filename(uploaded_file.filename or "")
    if not filename:
        return jsonify(status="error", message="Please choose a valid file"), 400
    if not filename.lower().endswith(".csv"):
        return jsonify(status="error", message="Only CSV files are accepted"), 400
    uploaded_file.stream.seek(0, 2)
    uploaded_size = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)
    if uploaded_size > MAX_UPLOAD_SIZE:
        return jsonify(status="error", message="CSV file exceeds the 5 MB upload limit"), 413

    try:
        dataframe = pd.read_csv(uploaded_file.stream)
    except pd.errors.EmptyDataError:
        return jsonify(status="error", message="The CSV file is empty or has no header"), 400
    except pd.errors.ParserError:
        return jsonify(status="error", message="The CSV file is malformed or could not be parsed"), 400
    except UnicodeDecodeError:
        return jsonify(status="error", message="CSV files must use UTF-8 text encoding"), 400

    preview = json.loads(dataframe.head(10).to_json(orient="records", date_format="iso"))
    return jsonify(
        status="success",
        columns=[str(column) for column in dataframe.columns],
        row_count=len(dataframe),
        preview=preview,
    ), 200


@api_bp.post("/clean")
@require_trusted_origin
@login_required
def clean_csv():
    uploaded_file = request.files.get("file")
    if uploaded_file is None:
        return jsonify(status="error", message="Please provide a CSV file"), 400

    original_filename = uploaded_file.filename or ""
    filename = secure_filename(original_filename)
    if not filename:
        return jsonify(status="error", message="Please choose a valid file"), 400
    if not filename.lower().endswith(".csv"):
        return jsonify(status="error", message="Only CSV files are accepted"), 400
    if len(original_filename) > 255:
        return jsonify(status="error", message="The CSV filename is too long"), 400
    uploaded_file.stream.seek(0, 2)
    uploaded_size = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)
    if uploaded_size > MAX_UPLOAD_SIZE:
        return jsonify(status="error", message="CSV file exceeds the 5 MB upload limit"), 413

    boolean_options = {}
    for option in ("remove_duplicates", "remove_empty_rows", "trim_whitespace", "handle_missing"):
        value = request.form.get(option)
        if value not in ("true", "false"):
            return jsonify(
                status="error",
                message=f"Invalid cleaning option: {option.replace('_', ' ')}",
            ), 400
        boolean_options[option] = value == "true"

    missing_strategy = request.form.get("missing_strategy")
    if missing_strategy not in ("remove", "fill"):
        return jsonify(
            status="error",
            message="Choose whether to remove rows with missing values or fill them.",
        ), 400

    missing_placeholder = request.form.get("missing_placeholder", "Not Provided")
    if missing_strategy == "fill" and missing_placeholder not in MISSING_PLACEHOLDERS:
        return jsonify(
            status="error",
            message="Choose a valid placeholder for missing values.",
        ), 400

    try:
        dataframe = read_csv_for_cleaning(uploaded_file.stream)
    except pd.errors.EmptyDataError:
        return jsonify(status="error", message="The CSV file is empty or has no header"), 400
    except pd.errors.ParserError:
        return jsonify(status="error", message="The CSV file is malformed or could not be parsed"), 400
    except UnicodeDecodeError:
        return jsonify(status="error", message="CSV files must use UTF-8 text encoding"), 400
    except ValueError:
        return jsonify(status="error", message="The CSV file is malformed or could not be parsed"), 400

    original_dataframe = dataframe
    original_row_count = len(original_dataframe)
    quality_before = get_data_quality_stats(original_dataframe)
    dataframe, unfilled_columns = clean_dataframe(
        dataframe,
        remove_empty_rows=boolean_options["remove_empty_rows"],
        remove_duplicates=boolean_options["remove_duplicates"],
        trim_whitespace=boolean_options["trim_whitespace"],
        handle_missing=boolean_options["handle_missing"],
        missing_strategy=missing_strategy,
        missing_placeholder=missing_placeholder,
    )
    quality_after = get_data_quality_stats(dataframe)

    preview = json.loads(dataframe.head(10).to_json(orient="records", date_format="iso"))
    cleaned_csv = dataframe.to_csv(index=False)
    operations = []
    if boolean_options["remove_duplicates"]:
        operations.append("Remove duplicate rows")
    if boolean_options["remove_empty_rows"]:
        operations.append("Remove completely empty rows")
    if boolean_options["trim_whitespace"]:
        operations.append("Trim leading and trailing whitespace")
    if boolean_options["handle_missing"]:
        if missing_strategy == "remove":
            operations.append("Remove rows with missing values")
        else:
            operations.append(f"Fill missing values with {missing_placeholder}")

    cleaned_file_id = uuid.uuid4().hex
    try:
        save_cleaned_csv(cleaned_file_id, cleaned_csv)
    except OSError:
        current_app.logger.exception("Could not persist cleaned CSV output")
        return jsonify(
            status="error",
            message="The CSV was cleaned, but its download could not be made available. Please try again.",
        ), 503

    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cleaning_history (
                    user_id, original_filename, operations,
                    original_row_count, final_row_count, cleaned_file_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    g.authenticated_user["id"],
                    original_filename,
                    json.dumps(operations),
                    original_row_count,
                    len(dataframe),
                    cleaned_file_id,
                ),
            )
            history_id = cursor.lastrowid
        connection.commit()
    except (pymysql.MySQLError, OSError) as error:
        if connection is not None:
            connection.rollback()
        try:
            delete_cleaned_csv(cleaned_file_id)
        except OSError:
            current_app.logger.exception("Could not remove unreferenced cleaned CSV output")
        if isinstance(error, pymysql.MySQLError):
            error_code = error.args[0] if error.args and isinstance(error.args[0], int) else "unknown"
            sqlstate = getattr(error, "sqlstate", None) or "unknown"
            current_app.logger.error(
                "Could not save CSV cleaning history "
                "(database error type=%s, code=%s, SQLSTATE=%s)",
                type(error).__name__,
                error_code,
                sqlstate,
            )
        else:
            current_app.logger.error(
                "Could not save CSV cleaning history (error type=%s)",
                type(error).__name__,
            )
        return jsonify(
            status="error",
            message="The CSV was cleaned, but its history could not be saved. Please try again.",
        ), 503
    finally:
        if connection is not None:
            connection.close()

    return jsonify(
        status="success",
        history_id=history_id,
        columns=[str(column) for column in dataframe.columns],
        original_row_count=original_row_count,
        row_count=len(dataframe),
        quality_report={
            "before": quality_before,
            "after": quality_after,
            "rows_removed": original_row_count - len(dataframe),
        },
        preview=preview,
        cleaned_csv=cleaned_csv,
        unfilled_columns=unfilled_columns,
    ), 200


@api_bp.get("/cleaning-history/<int:history_id>/download")
@login_required
def download_cleaned_csv(history_id):
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT original_filename, cleaned_file_id
                FROM cleaning_history
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """,
                (history_id, g.authenticated_user["id"]),
            )
            history_record = cursor.fetchone()
    except (pymysql.MySQLError, OSError):
        current_app.logger.exception("Could not retrieve cleaned CSV history record")
        return jsonify(
            status="error",
            message="The cleaned CSV is temporarily unavailable. Please try again later.",
        ), 503
    finally:
        if connection is not None:
            connection.close()

    if history_record is None or history_record[1] is None:
        return jsonify(status="error", message="The cleaned CSV is not available."), 404

    try:
        cleaned_csv_path = get_cleaned_csv_path(history_record[1])
        if not cleaned_csv_path.is_file():
            return jsonify(status="error", message="The cleaned CSV is not available."), 404
        safe_filename = secure_filename(history_record[0])
        download_name = f"{safe_filename.rsplit('.', 1)[0] or 'cleaned'}-cleaned.csv"
        return send_file(
            cleaned_csv_path,
            mimetype="text/csv",
            as_attachment=True,
            download_name=download_name,
        )
    except FileNotFoundError:
        return jsonify(status="error", message="The cleaned CSV is not available."), 404
    except ValueError:
        current_app.logger.error("Cleaning history contains an invalid cleaned CSV reference")
        return jsonify(status="error", message="The cleaned CSV is not available."), 404
    except OSError:
        current_app.logger.exception("Could not read persisted cleaned CSV output")
        return jsonify(
            status="error",
            message="The cleaned CSV is temporarily unavailable. Please try again later.",
        ), 503


@api_bp.get("/dashboard-stats")
@login_required
def get_dashboard_stats():
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total_cleaning_jobs,
                       COALESCE(SUM(original_row_count), 0) AS rows_reviewed,
                       COALESCE(
                           SUM(GREATEST(
                               CAST(original_row_count AS SIGNED)
                               - CAST(final_row_count AS SIGNED),
                               0
                           )),
                           0
                       ) AS total_rows_removed
                FROM cleaning_history
                WHERE user_id = %s
                """,
                (g.authenticated_user["id"],),
            )
            totals = cursor.fetchone()
            cursor.execute(
                """
                SELECT original_filename, original_row_count, final_row_count, created_at
                FROM cleaning_history
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 5
                """,
                (g.authenticated_user["id"],),
            )
            recent_rows = cursor.fetchall()
    except (pymysql.MySQLError, OSError):
        current_app.logger.exception("Could not retrieve dashboard statistics")
        return jsonify(
            status="error",
            message="Dashboard statistics are temporarily unavailable. Please try again later.",
        ), 503
    finally:
        if connection is not None:
            connection.close()

    recent_activity = []
    for row in recent_rows:
        created_at = row[3]
        recent_activity.append({
            "filename": row[0],
            "original_row_count": row[1],
            "final_row_count": row[2],
            "rows_removed": max(row[1] - row[2], 0),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        })

    return jsonify(
        status="success",
        statistics={
            "total_cleaning_jobs": int(totals[0] or 0),
            "rows_reviewed": int(totals[1] or 0),
            "total_rows_removed": int(totals[2] or 0),
            "recent_activity": recent_activity,
        },
    ), 200


@api_bp.get("/cleaning-history")
@login_required
def get_cleaning_history():
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, original_filename, operations,
                       original_row_count, final_row_count, created_at,
                       cleaned_file_id
                FROM cleaning_history
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (g.authenticated_user["id"],),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, OSError):
        current_app.logger.exception("Could not retrieve CSV cleaning history")
        return jsonify(
            status="error",
            message="Cleaning history is temporarily unavailable. Please try again later.",
        ), 503
    finally:
        if connection is not None:
            connection.close()

    history = []
    try:
        for row in rows:
            operations = row[2]
            if isinstance(operations, str):
                operations = json.loads(operations)
            if (
                not isinstance(operations, list)
                or any(not isinstance(operation, str) or len(operation) > 300 for operation in operations)
            ):
                raise ValueError("Invalid cleaning history operations")

            created_at = row[5]
            history.append({
                "id": row[0],
                "filename": row[1],
                "operations": operations,
                "original_row_count": row[3],
                "final_row_count": row[4],
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
                "has_cleaned_file": row[6] is not None,
            })
    except (TypeError, ValueError, json.JSONDecodeError):
        current_app.logger.exception("Cleaning history contains invalid stored data")
        return jsonify(
            status="error",
            message="Cleaning history is temporarily unavailable. Please try again later.",
        ), 503

    return jsonify(status="success", history=history), 200