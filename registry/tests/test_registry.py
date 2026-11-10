import time

import fakeredis
import pytest
from fastapi.testclient import TestClient

from registry.app import create_app, validate_url
from stockplatform.events import InMemoryBroker, SERVICE_EXPIRED, SERVICE_REGISTERED

KEY = {"X-Registry-Key": "secret"}
SVC = {"name": "price-history", "url": "https://s1.example.com", "description": "Price history", "tags": ["price"]}


@pytest.fixture
def parts():
    redis_client = fakeredis.FakeRedis()
    broker = InMemoryBroker()
    healthy = {"value": True}
    app = create_app(redis_client, broker, key="secret", allowed_domains=["example.com"], allow_local=False,
                     health_check=lambda url: healthy["value"], start_sweeper=False)
    return TestClient(app), redis_client, broker, healthy, app


def test_register_needs_the_key(parts):
    client = parts[0]
    assert client.post("/services", json=SVC).status_code == 401
    assert client.post("/services", json=SVC, headers={"X-Registry-Key": "wrong"}).status_code == 401
    assert client.post("/services", json=SVC, headers=KEY).status_code == 201


def test_search_is_open_and_matches_name_description_and_tags(parts):
    client = parts[0]
    client.post("/services", json=SVC, headers=KEY)
    for q in ("price", "HISTORY", "pri"):
        assert [s["name"] for s in client.get("/services", params={"q": q}).json()["services"]] == ["price-history"]
    assert client.get("/services", params={"q": "nothing"}).json()["services"] == []
    assert len(client.get("/services").json()["services"]) == 1


def test_unhealthy_services_are_not_listed(parts):
    client, _, _, healthy, _ = parts
    client.post("/services", json=SVC, headers=KEY)
    healthy["value"] = False
    assert client.get("/services").json()["services"] == []


@pytest.mark.parametrize("url,ok", [
    ("https://s1.example.com", True),
    ("https://example.com", True),
    ("http://s1.example.com", False),
    ("https://evil.com", False),
    ("https://notexample.com", False),
    ("https://localhost", False),
    ("ftp://s1.example.com", False),
])
def test_url_rules(url, ok):
    assert (validate_url(url, ["example.com"], False) is None) is ok


def test_local_override_allows_local_http():
    assert validate_url("http://localhost:9000", ["example.com"], True) is None
    assert validate_url("http://price-history:8000", ["example.com"], True) is None


def test_bad_name_and_url_are_rejected(parts):
    client = parts[0]
    assert client.post("/services", json={**SVC, "name": "Bad Name"}, headers=KEY).status_code == 422
    assert client.post("/services", json={**SVC, "url": "https://evil.com"}, headers=KEY).status_code == 422


def test_heartbeat_renews_lease_and_unknown_service_gets_404(parts):
    client, redis_client, *_ = parts
    client.post("/services", json=SVC, headers=KEY)
    redis_client.expire("svc:price-history", 3)
    assert client.post("/services/price-history/heartbeat", headers=KEY).status_code == 200
    assert redis_client.ttl("svc:price-history") > 20
    assert client.post("/services/ghost/heartbeat", headers=KEY).status_code == 404


def test_deregister_removes_service(parts):
    client = parts[0]
    client.post("/services", json=SVC, headers=KEY)
    assert client.delete("/services/price-history", headers=KEY).status_code == 204
    assert client.get("/services").json()["services"] == []


def test_registered_event_is_published_once_per_new_service(parts):
    client, _, broker, *_ = parts
    client.post("/services", json=SVC, headers=KEY)
    client.post("/services", json=SVC, headers=KEY)  # a re-register is not a new service
    assert [e.type for e in broker.published] == [SERVICE_REGISTERED]


def test_expired_lease_disappears_and_event_is_published_once_across_two_registries():
    redis_client = fakeredis.FakeRedis()  # shared by both registries
    broker_a, broker_b = InMemoryBroker(), InMemoryBroker()
    make = lambda b: create_app(redis_client, b, key="secret", allowed_domains=["example.com"],
                                health_check=lambda u: True, start_sweeper=False)
    a, b = make(broker_a), make(broker_b)
    TestClient(a).post("/services", json=SVC, headers=KEY)
    redis_client.pexpire("svc:price-history", 1)
    time.sleep(0.05)
    assert TestClient(a).get("/services").json()["services"] == []
    total = a.state.sweep_once() + b.state.sweep_once()
    assert total == 1
    events = [e.type for e in broker_a.published + broker_b.published if e.type == SERVICE_EXPIRED]
    assert events == [SERVICE_EXPIRED]


def test_backup_answers_with_the_same_data_as_primary():
    redis_client = fakeredis.FakeRedis()
    make = lambda: create_app(redis_client, InMemoryBroker(), key="secret", allowed_domains=["example.com"],
                              health_check=lambda u: True, start_sweeper=False)
    primary, backup = TestClient(make()), TestClient(make())
    primary.post("/services", json=SVC, headers=KEY)
    assert backup.get("/services").json() == primary.get("/services").json()


def test_health_reports_redis_down():
    class Broken(fakeredis.FakeRedis):
        def ping(self, *a, **k):
            raise ConnectionError("down")
    app = create_app(Broken(), InMemoryBroker(), key="secret", start_sweeper=False)
    assert TestClient(app).get("/health").status_code == 503


def test_health_check_uses_health_url_when_given():
    checked = []
    app = create_app(fakeredis.FakeRedis(), InMemoryBroker(), key="secret", allowed_domains=["example.com"],
                     allow_local=True, health_check=lambda u: checked.append(u) or True, start_sweeper=False)
    client = TestClient(app)
    client.post("/services", json={**SVC, "health_url": "http://price-history:8000"}, headers=KEY)
    body = client.get("/services").json()["services"]
    assert checked == ["http://price-history:8000"] and body[0]["url"] == "https://s1.example.com"
    assert "health_url" not in body[0]


def test_bad_health_url_is_rejected(parts):
    client = parts[0]
    r = client.post("/services", json={**SVC, "health_url": "http://localhost:1"}, headers=KEY)
    assert r.status_code == 422
