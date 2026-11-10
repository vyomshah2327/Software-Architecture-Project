from fastapi.testclient import TestClient

from stockplatform.events import InMemoryBroker
from stockplatform.service import create_service


def test_metrics_count_requests_by_route_and_time_them():
    app = create_service("demo", "Demo", "d", broker=InMemoryBroker(), registry=None)

    @app.get("/api/item/{item_id}")
    def item(item_id: int):
        return {"id": item_id}

    c = TestClient(app)
    c.get("/api/item/1"); c.get("/api/item/2"); c.get("/api/item/x"); c.get("/nothing")
    text = c.get("/metrics").text
    assert 'route="/api/item/{item_id}",method="GET",status="2xx"} 2' in text
    assert 'route="/api/item/{item_id}",method="GET",status="4xx"} 1' in text
    assert 'route="unmatched"' in text
    assert 'http_request_duration_seconds_count{service="demo"' in text
    assert 'le="+Inf"' in text and "http_requests_in_flight" in text


def test_metrics_endpoint_does_not_count_itself():
    app = create_service("demo", "Demo", "d", broker=InMemoryBroker(), registry=None)
    c = TestClient(app)
    c.get("/metrics"); c.get("/metrics")
    assert 'route="/metrics"' not in c.get("/metrics").text
