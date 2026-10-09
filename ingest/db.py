from sqlalchemy import create_engine

from .config import get_database_url


def get_engine(url=None):
    return create_engine(url or get_database_url(), pool_pre_ping=True)
