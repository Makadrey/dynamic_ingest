"""Database settings come from environment variables / a .env file, never from code."""
import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL

REQUIRED = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")


def get_database_url():
    load_dotenv()  # does not override variables already set in the shell
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            f"Missing settings: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
    # URL.create escapes special characters in the password for us
    return URL.create(
        "postgresql+psycopg2",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
