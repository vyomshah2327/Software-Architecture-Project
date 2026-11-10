import pytest


@pytest.fixture(autouse=True)
def no_health_cache(monkeypatch):
    """Existing tests expect every search to check health again; the cache has its own tests."""
    monkeypatch.setenv("HEALTH_CACHE_SECONDS", "0")
