from datetime import date

from stockplatform import fakedata


def test_same_input_gives_same_prices():
    a = fakedata.generate_prices("AAPL", date(2025, 1, 1), date(2025, 3, 31))
    b = fakedata.generate_prices("AAPL", date(2025, 1, 1), date(2025, 3, 31))
    assert a == b and len(a) > 50


def test_extending_the_range_keeps_earlier_prices():
    short = fakedata.generate_prices("MSFT", date(2025, 1, 1), date(2025, 2, 28))
    long = fakedata.generate_prices("MSFT", date(2025, 1, 1), date(2025, 4, 30))
    assert long[: len(short)] == short


def test_only_business_days_and_valid_prices():
    rows = fakedata.generate_prices("KO", date(2025, 1, 1), date(2025, 2, 28))
    assert all(r["date"].weekday() < 5 for r in rows)
    assert all(r["low"] <= r["close"] <= r["high"] or r["low"] <= r["open"] for r in rows)
    assert all(r["close"] > 0 for r in rows)


def test_universe_has_index_and_unique_symbols():
    assert fakedata.INDEX_SYMBOL in fakedata.SYMBOLS
    assert len(set(fakedata.SYMBOLS)) == len(fakedata.SYMBOLS) == 26
