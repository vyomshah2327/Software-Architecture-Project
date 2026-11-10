from fastapi.testclient import TestClient

from stockplatform.events import InMemoryBroker
from stockplatform.service import create_service, render_page, INSTANCE_ID


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


def test_health_and_instance_header():
    app = create_service("demo", "Demo", "A demo", broker=InMemoryBroker(), registry=None)
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json()["service"] == "demo"
    assert r.headers["x-instance-id"] == INSTANCE_ID


def test_registers_on_startup_and_deregisters_on_shutdown():
    reg = FakeRegistry()
    app = create_service("demo", "Demo", "A demo", broker=InMemoryBroker(), registry=reg)
    with TestClient(app):
        assert reg.calls == ["start"]
    assert reg.calls == ["start", "stop"]


def test_subscribes_and_receives_events():
    broker, got = InMemoryBroker(), []
    app = create_service("demo", "Demo", "A demo", subscriptions=["market.data.updated"],
                         on_event=got.append, broker=broker, registry=None)
    with TestClient(app):
        broker.publish("market.data.updated", {"symbols": ["AAPL"]}, "ingestor")
    assert got and got[0].data == {"symbols": ["AAPL"]}


def test_page_helper_escapes_title_and_shows_instance():
    page = render_page("<b>x</b>", "<p>hi</p>").body.decode()
    assert "&lt;b&gt;" in page and "<p>hi</p>" in page and INSTANCE_ID in page


def test_no_registration_without_env(monkeypatch):
    monkeypatch.delenv("SERVICE_URL", raising=False)
    app = create_service("demo", "Demo", "A demo", broker=InMemoryBroker())
    assert app.state.registry is None
