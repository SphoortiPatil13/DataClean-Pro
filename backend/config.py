import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

MAX_UPLOAD_SIZE = 5 * 1024 * 1024


class Config:
    """Basic settings for the DataCleanPro Flask application."""

    HOST = "127.0.0.1"
    PORT = 5000
    DEBUG = True
    MAX_CONTENT_LENGTH = MAX_UPLOAD_SIZE + 64 * 1024
    SECRET_KEY = os.getenv("SECRET_KEY")
    SESSION_COOKIE_NAME = "datacleanpro_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_PATH = "/api"
    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "datacleanpro")