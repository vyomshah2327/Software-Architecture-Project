import os

import pytest
from fastapi.testclient import TestClient

from stockplatform import db
from stockplatform.events import InMemoryBroker


@pytest.fixture(scope="session", autouse=True)
def require_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set", allow_module_level=False)
    db.close_pool()
    if not db.ping():
        pytest.skip("database not reachable")
    yield
    db.close_pool()


@pytest.fixture
def broker():
    return InMemoryBroker()


@pytest.fixture
def make_client(broker):
    """Build a TestClient for a service factory with an in-memory broker and no registry."""
    def build(factory):
        return TestClient(factory(broker=broker, registry=None))
    return build
