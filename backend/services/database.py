import pymysql
from flask import current_app


def get_db_connection():
    """Open and return a connection using the active Flask configuration."""
    return pymysql.connect(
        host=current_app.config["DB_HOST"],
        port=current_app.config["DB_PORT"],
        user=current_app.config["DB_USER"],
        password=current_app.config["DB_PASSWORD"],
        database=current_app.config["DB_NAME"],
        charset="utf8mb4",
        connect_timeout=5,
    )