import uuid

import pytest

from alerts_monitor.main import create_app as alerts
from portfolio.main import create_app as portfolio
from stockplatform import db
from stockplatform.events import ALERT_TRIGGERED, HOLDING_CHANGED, WATCHLIST_CHANGED


@pytest.fixture
def user():
    uid = "test-" + uuid.uuid4().hex[:8]
    yield uid
    db.execute("DELETE FROM alerts WHERE rule_id IN (SELECT id FROM alert_rules WHERE user_id=%s)", (uid,))
    for table in ("alert_rules", "holdings", "watchlist"):
        db.execute(f"DELETE FROM {table} WHERE user_id=%s", (uid,))


def test_holdings_merge_value_and_events(make_client, broker, user):
    c = make_client(portfolio)
    c.post("/api/holdings", json={"user_id": user, "symbol": "aapl", "quantity": 10, "avg_cost": 100})
    merged = c.post("/api/holdings", json={"user_id": user, "symbol": "AAPL", "quantity": 10, "avg_cost": 200}).json()
    assert merged["quantity"] == 20 and merged["avg_cost"] == 150
    c.post("/api/holdings", json={"user_id": user, "symbol": "MSFT", "quantity": 5, "avg_cost": 50})
    p = c.get("/api/portfolio", params={"user_id": user}).json()
    assert [x["symbol"] for x in p["positions"]] == ["AAPL", "MSFT"]
    assert sum(x["weight"] for x in p["positions"]) == pytest.approx(1.0)
    assert p["total_value"] == pytest.approx(sum(x["value"] for x in p["positions"]))
    assert c.delete(f"/api/holdings/MSFT?user_id={user}").status_code == 204
    assert c.delete(f"/api/holdings/MSFT?user_id={user}").status_code == 404
    assert [e.type for e in broker.published].count(HOLDING_CHANGED) == 4


@pytest.mark.parametrize("body", [
    {"symbol": "AAPL", "quantity": 0, "avg_cost": 1},
    {"symbol": "AAPL", "quantity": 1, "avg_cost": -1},
    {"symbol": "NOPE", "quantity": 1, "avg_cost": 1},
])
def test_holding_validation(make_client, user, body):
    assert make_client(portfolio).post("/api/holdings", json={"user_id": user, **body}).status_code in (404, 422)


def test_watchlist_add_is_idempotent_and_publishes_once(make_client, broker, user):
    c = make_client(portfolio)
    assert c.put(f"/api/watchlist/aapl?user_id={user}").status_code == 204
    c.put(f"/api/watchlist/AAPL?user_id={user}")
    assert c.get("/api/watchlist", params={"user_id": user}).json()["symbols"] == ["AAPL"]
    assert [e.type for e in broker.published] == [WATCHLIST_CHANGED]
    c.delete(f"/api/watchlist/AAPL?user_id={user}")
    assert c.get("/api/watchlist", params={"user_id": user}).json()["symbols"] == []
    assert c.put(f"/api/watchlist/NOPE?user_id={user}").status_code == 404


def last_close(symbol="AAPL"):
    return float(db.query("SELECT close FROM prices WHERE symbol=%s ORDER BY date DESC LIMIT 1", (symbol,))[0]["close"])


def test_alert_fires_once_then_rearms(make_client, broker, user):
    c = make_client(alerts)
    price = last_close()
    rid = c.post("/api/rules", json={"user_id": user, "symbol": "AAPL", "direction": "above",
                                     "threshold": price - 1}).json()["id"]
    c.post("/api/evaluate")
    c.post("/api/evaluate")  # second check must not repeat the alert
    assert len(c.get("/api/alerts", params={"user_id": user}).json()) == 1
    assert [e.type for e in broker.published] == [ALERT_TRIGGERED]
    db.execute("UPDATE alert_rules SET threshold=%s WHERE id=%s", (price + 1000, rid))
    c.post("/api/evaluate")  # condition no longer met: rule re-arms
    assert c.get("/api/rules", params={"user_id": user}).json()[0]["last_state"] == "clear"
    db.execute("UPDATE alert_rules SET threshold=%s WHERE id=%s", (price - 1, rid))
    c.post("/api/evaluate")
    assert len(c.get("/api/alerts", params={"user_id": user}).json()) == 2


def test_below_rule_and_not_met(make_client, user):
    c = make_client(alerts)
    price = last_close()
    c.post("/api/rules", json={"user_id": user, "symbol": "AAPL", "direction": "below", "threshold": price - 1})
    c.post("/api/evaluate")
    assert c.get("/api/alerts", params={"user_id": user}).json() == []


def test_market_event_triggers_evaluation_only_for_updated_symbols(make_client, broker, user):
    c = make_client(alerts)
    price = last_close()
    c.post("/api/rules", json={"user_id": user, "symbol": "AAPL", "direction": "above", "threshold": price - 1})
    with c:
        broker.publish("market.data.updated", {"symbols": ["MSFT"]}, "ingestor")
        assert c.get("/api/alerts", params={"user_id": user}).json() == []
        broker.publish("market.data.updated", {"symbols": ["AAPL"]}, "ingestor")
        assert len(c.get("/api/alerts", params={"user_id": user}).json()) == 1


def test_rule_validation_and_delete(make_client, user):
    c = make_client(alerts)
    assert c.post("/api/rules", json={"user_id": user, "symbol": "AAPL", "direction": "sideways", "threshold": 1}).status_code == 422
    assert c.post("/api/rules", json={"user_id": user, "symbol": "NOPE", "direction": "above", "threshold": 1}).status_code == 404
    rid = c.post("/api/rules", json={"user_id": user, "symbol": "AAPL", "direction": "above", "threshold": 1}).json()["id"]
    assert c.delete(f"/api/rules/{rid}").status_code == 204 and c.delete(f"/api/rules/{rid}").status_code == 404


def test_monitor_lists_watchlist_with_change(make_client, user):
    p, a = make_client(portfolio), make_client(alerts)
    p.put(f"/api/watchlist/AAPL?user_id={user}")
    m = a.get("/api/monitor", params={"user_id": user}).json()
    assert m[0]["symbol"] == "AAPL" and m[0]["close"] > 0
