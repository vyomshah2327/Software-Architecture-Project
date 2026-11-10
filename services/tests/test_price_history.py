from price_history.main import create_app


def test_companies_and_prices(make_client):
    c = make_client(create_app)
    assert len(c.get("/api/companies").json()) >= 20
    rows = c.get("/api/prices/aapl", params={"limit": 10}).json()
    assert len(rows) == 10 and rows[0]["date"] < rows[-1]["date"] and rows[0]["close"] > 0


def test_date_range_filter(make_client):
    c = make_client(create_app)
    all_rows = c.get("/api/prices/AAPL", params={"limit": 50}).json()
    start, end = all_rows[10]["date"], all_rows[20]["date"]
    rows = c.get("/api/prices/AAPL", params={"start": start, "end": end}).json()
    assert rows[0]["date"] == start and rows[-1]["date"] == end


def test_unknown_symbol_and_bad_limit(make_client):
    c = make_client(create_app)
    assert c.get("/api/prices/NOPE").status_code == 404
    assert c.get("/api/prices/AAPL", params={"limit": 0}).status_code == 422


def test_latest(make_client):
    body = make_client(create_app).get("/api/latest/MSFT").json()
    assert body["symbol"] == "MSFT" and body["close"] > 0 and "change" in body


def test_page_health_and_instance_header(make_client):
    c = make_client(create_app)
    assert "Price history" in c.get("/").text
    assert c.get("/health").headers["x-instance-id"]
