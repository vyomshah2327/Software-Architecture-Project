import pytest

from indicators.main import create_app as indicators
from performance.main import create_app as performance
from volatility_risk.main import create_app as risk


def test_performance_period_and_comparison(make_client):
    c = make_client(performance)
    one = c.get("/api/performance/AAPL", params={"period": "3m"}).json()
    assert one["symbol"] == "AAPL" and one["start"] < one["end"] and one["best_day"] >= one["worst_day"]
    cmp = c.get("/api/compare", params={"symbols": "AAPL,msft", "period": "1y"}).json()
    assert [r["symbol"] for r in cmp["results"]] == ["AAPL", "MSFT"]


def test_performance_validation(make_client):
    c = make_client(performance)
    assert c.get("/api/performance/AAPL", params={"period": "5y"}).status_code == 422
    assert c.get("/api/performance/NOPE").status_code == 404
    assert c.get("/api/compare", params={"symbols": ",".join(["AAPL"] * 11)}).status_code == 422
    assert c.get("/api/performance/AAPL", params={"period": "ytd"}).status_code == 200


def test_risk_numbers_are_sensible(make_client):
    j = make_client(risk).get("/api/risk/AAPL", params={"days": 200}).json()
    assert 0 < j["volatility"] < 3 and j["max_drawdown"] <= 0 and j["var_95"] >= 0
    spy = make_client(risk).get("/api/risk/SPY").json()
    assert spy["beta"] == pytest.approx(1.0)


def test_risk_validation(make_client):
    c = make_client(risk)
    assert c.get("/api/risk/NOPE").status_code == 404
    assert c.get("/api/risk/AAPL", params={"days": 5}).status_code == 422


@pytest.mark.parametrize("name", ["sma", "ema", "rsi"])
def test_indicator_series(make_client, name):
    j = make_client(indicators).get("/api/indicators/AAPL", params={"name": name, "window": 14, "limit": 50}).json()
    assert len(j["values"]) == len(j["dates"]) == 50 and j["latest"] is not None
    if name == "rsi":
        assert 0 <= j["latest"] <= 100


def test_macd_and_validation(make_client):
    c = make_client(indicators)
    j = c.get("/api/indicators/AAPL", params={"name": "macd", "limit": 30}).json()
    assert set(j["latest"]) == {"macd", "signal", "histogram"}
    assert c.get("/api/indicators/AAPL", params={"name": "bogus"}).status_code == 422
    assert c.get("/api/indicators/NOPE").status_code == 404


def test_market_event_clears_cache(make_client, broker):
    c = make_client(performance)
    c.get("/api/performance/AAPL")
    with c:  # starts the app so the subscription is live
        broker.publish("market.data.updated", {}, "ingestor")
    assert c.get("/api/performance/AAPL").status_code == 200
