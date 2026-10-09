import os

import pytest
from sqlalchemy import MetaData, create_engine


@pytest.fixture
def engine(tmp_path):
    """SQLite by default; set TEST_DATABASE_URL to run the suite against Postgres."""
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    eng = create_engine(url)
    yield eng
    meta = MetaData()
    meta.reflect(eng)
    meta.drop_all(eng)
    eng.dispose()
