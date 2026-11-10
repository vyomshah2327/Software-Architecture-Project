import os

import pytest

from stockplatform import db


@pytest.fixture
def database():
    """Uses the DATABASE_URL database; skipped when none is reachable."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    db.close_pool()
    if not db.ping():
        pytest.skip("database not reachable")
    db.execute("DELETE FROM ingestion_log")
    yield db
    db.execute("DELETE FROM ingestion_log")
    db.close_pool()
