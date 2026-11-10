import json
from datetime import date

import pytest

from ingestor import run as ing
from ingestor.archive import LocalArchive, S3Archive
from ingestor.sources import (AlphaVantageSource, FakeSource, Fetched, SourceError, parse_alpha_vantage)
from stockplatform.events import InMemoryBroker, MARKET_DATA_UPDATED

SAMPLE = {"Time Series (Daily)": {
    "2024-03-02": {"1. open": "10", "2. high": "12", "3. low": "9", "4. close": "11", "5. volume": "1000"},
    "2024-03-01": {"1. open": "9", "2. high": "11", "3. low": "8", "4. close": "10", "5. volume": "900"}}}


def test_parse_alpha_vantage_sorts_and_uses_close_when_no_adjusted():
    rows = parse_alpha_vantage(SAMPLE)
    assert [r["date"] for r in rows] == [date(2024, 3, 1), date(2024, 3, 2)]
    assert rows[1]["adjusted_close"] == 11 and rows[1]["volume"] == 1000


@pytest.mark.parametrize("payload,limited", [
    ({"Note": "5 calls per minute"}, True),
    ({"Information": "daily limit reached"}, True),
    ({"Error Message": "bad symbol"}, False),
    ({}, False),
])
def test_parse_errors(payload, limited):
    with pytest.raises(SourceError) as e:
        parse_alpha_vantage(payload)
    assert e.value.rate_limited is limited


def test_alpha_vantage_source_counts_one_call_and_keeps_raw():
    import httpx
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=SAMPLE)))
    fetched = AlphaVantageSource("k", client=client).fetch_daily("AAPL")
    assert fetched.api_calls == 1 and "Time Series" in fetched.raw and len(fetched.rows) == 2


def test_local_archive_writes_raw(tmp_path):
    path = LocalArchive(str(tmp_path)).save("run1", "AAPL", '{"a":1}')
    assert json.loads(open(path).read()) == {"a": 1}


def test_s3_archive_puts_object():
    calls = []

    class Client:
        def put_object(self, **kw):
            calls.append(kw)

    where = S3Archive("bucket", "https://x", "a", "b", client=Client()).save("run1", "AAPL", "{}")
    assert where.startswith("s3://bucket/raw/") and calls[0]["Bucket"] == "bucket"


class Counting:
    def __init__(self, calls=1, fail=None):
        self.calls, self.fail, self.seen = calls, fail or {}, []

    def fetch_daily(self, symbol):
        self.seen.append(symbol)
        if symbol in self.fail:
            raise self.fail[symbol]
        f = FakeSource(30, today=date(2024, 6, 3)).fetch_daily(symbol)
        return Fetched(f.rows, f.raw, self.calls)


def count(db, symbol):
    return db.query("SELECT count(*) AS n FROM prices WHERE symbol=%s", (symbol,))[0]["n"]


def test_run_is_idempotent_archives_and_publishes_after_commit(database, tmp_path):
    broker = InMemoryBroker()
    seen_in_db = []
    broker.subscribe("check", [MARKET_DATA_UPDATED], lambda e: seen_in_db.append(count(database, "AAPL")))
    args = dict(source=Counting(calls=0), archive=LocalArchive(str(tmp_path)), broker=broker,
                symbols=["AAPL", "MSFT"], daily_limit=25, per_minute=0)
    first = ing.run(**args)
    n = count(database, "AAPL")
    second = ing.run(**args)
    assert first["updated"] == ["AAPL", "MSFT"] and first["published"] is True
    assert count(database, "AAPL") == n          # no duplicates on a second run
    assert seen_in_db[0] >= 20                   # data was already committed when the event fired
    assert len(list(tmp_path.rglob("AAPL.json"))) == 2 and second["failed"] == []


def test_run_stops_at_daily_limit(database, tmp_path):
    source = Counting(calls=1)
    result = ing.run(source, LocalArchive(str(tmp_path)), InMemoryBroker(),
                     symbols=["AAPL", "MSFT", "GOOGL", "AMZN"], daily_limit=2, per_minute=0)
    assert source.seen == ["AAPL", "MSFT"] and result["skipped"] == ["GOOGL", "AMZN"]
    assert ing.calls_used_today() == 2
    again = ing.run(Counting(), LocalArchive(str(tmp_path)), InMemoryBroker(), symbols=["AAPL"],
                    daily_limit=2, per_minute=0)
    assert again["skipped"] == ["AAPL"] and again["updated"] == []


def test_rate_limit_from_source_stops_the_run(database, tmp_path):
    source = Counting(fail={"MSFT": SourceError("limit", rate_limited=True)})
    result = ing.run(source, LocalArchive(str(tmp_path)), InMemoryBroker(),
                     symbols=["AAPL", "MSFT", "GOOGL"], daily_limit=25, per_minute=0)
    assert result["updated"] == ["AAPL"] and result["failed"] == ["MSFT"] and result["skipped"] == ["GOOGL"]


def test_other_failure_skips_symbol_but_continues(database, tmp_path):
    source = Counting(fail={"MSFT": SourceError("bad")})
    result = ing.run(source, LocalArchive(str(tmp_path)), InMemoryBroker(),
                     symbols=["AAPL", "MSFT", "GOOGL"], daily_limit=25, per_minute=0)
    assert result["updated"] == ["AAPL", "GOOGL"] and result["failed"] == ["MSFT"]


def test_no_event_when_nothing_updated(database, tmp_path):
    broker = InMemoryBroker()
    ing.run(Counting(fail={"AAPL": SourceError("bad")}), LocalArchive(str(tmp_path)), broker,
            symbols=["AAPL"], daily_limit=25, per_minute=0)
    assert broker.published == []


def test_per_minute_pacing_sleeps_between_paid_calls(database, tmp_path):
    waits = []
    ing.run(Counting(calls=1), LocalArchive(str(tmp_path)), InMemoryBroker(),
            symbols=["AAPL", "MSFT", "GOOGL"], daily_limit=25, per_minute=5, sleep=waits.append)
    assert waits == [12.0, 12.0]
