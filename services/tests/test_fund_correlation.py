import pytest

from correlation_svc.main import create_app as correlation
from fund_builder.main import create_app as fund


def test_backtest_equal_and_weighted(make_client):
    c = make_client(fund)
    eq = c.post("/api/backtest", json={"symbols": ["AAPL", "MSFT"], "amount": 1000, "days": 100}).json()
    assert eq["weights"] == {"AAPL": 0.5, "MSFT": 0.5} and len(eq["values"]) == len(eq["dates"])
    assert eq["values"][0] == pytest.approx(1000)
    w = c.post("/api/backtest", json={"symbols": ["AAPL", "MSFT"], "weights": {"AAPL": 3, "MSFT": 1}, "days": 100}).json()
    assert w["weights"]["AAPL"] == 0.75


@pytest.mark.parametrize("body,code", [
    ({"symbols": ["AAPL", "AAPL"]}, 422),
    ({"symbols": ["NOPE"]}, 404),
    ({"symbols": ["AAPL", "MSFT"], "weights": {"AAPL": 1}}, 422),
    ({"symbols": ["AAPL"], "weights": {"AAPL": 0}}, 422),
    ({"symbols": []}, 422),
    ({"symbols": ["AAPL"], "amount": -5}, 422),
])
def test_backtest_validation(make_client, body, code):
    assert make_client(fund).post("/api/backtest", json=body).status_code == code


def test_suggest_by_sector(make_client):
    c = make_client(fund)
    sector = c.get("/api/sectors").json()[0]
    j = c.get("/api/suggest", params={"sector": sector, "count": 2}).json()
    assert 1 <= len(j["symbols"]) <= 2 and abs(sum(j["weights"].values()) - 1) < 1e-3
    assert c.get("/api/suggest", params={"sector": "Nonexistent"}).status_code == 404


def test_correlation_matrix(make_client):
    j = make_client(correlation).get("/api/correlation", params={"symbols": "AAPL,MSFT,SPY", "days": 120}).json()
    m = j["matrix"]
    assert m["AAPL"]["AAPL"] == 1.0 and m["AAPL"]["MSFT"] == m["MSFT"]["AAPL"]
    assert all(-1 <= m[a][b] <= 1 for a in m for b in m)


def test_correlation_validation(make_client):
    c = make_client(correlation)
    assert c.get("/api/correlation", params={"symbols": "AAPL"}).status_code == 422
    assert c.get("/api/correlation", params={"symbols": "AAPL,AAPL"}).status_code == 422
    assert c.get("/api/correlation", params={"symbols": "AAPL,NOPE"}).status_code == 404
