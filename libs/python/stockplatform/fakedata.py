"""Deterministic sample market data.

Used for local development, tests and the demo when no Alpha Vantage key is available.
The same symbol and date always give the same prices, so loads can be repeated safely.
"""
from __future__ import annotations

import math
import random
import zlib
from datetime import date, timedelta

INDEX_SYMBOL = "SPY"

COMPANIES: list[tuple[str, str, str, str]] = [
    ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics"),
    ("MSFT", "Microsoft Corporation", "Technology", "Software"),
    ("NVDA", "NVIDIA Corporation", "Technology", "Semiconductors"),
    ("GOOGL", "Alphabet Inc.", "Communication Services", "Internet Content"),
    ("AMZN", "Amazon.com, Inc.", "Consumer Discretionary", "Internet Retail"),
    ("META", "Meta Platforms, Inc.", "Communication Services", "Internet Content"),
    ("TSLA", "Tesla, Inc.", "Consumer Discretionary", "Auto Manufacturers"),
    ("JPM", "JPMorgan Chase & Co.", "Financials", "Banks"),
    ("BAC", "Bank of America Corporation", "Financials", "Banks"),
    ("GS", "The Goldman Sachs Group, Inc.", "Financials", "Capital Markets"),
    ("V", "Visa Inc.", "Financials", "Credit Services"),
    ("XOM", "Exxon Mobil Corporation", "Energy", "Oil and Gas"),
    ("CVX", "Chevron Corporation", "Energy", "Oil and Gas"),
    ("JNJ", "Johnson & Johnson", "Health Care", "Pharmaceuticals"),
    ("PFE", "Pfizer Inc.", "Health Care", "Pharmaceuticals"),
    ("UNH", "UnitedHealth Group Incorporated", "Health Care", "Health Plans"),
    ("PG", "The Procter & Gamble Company", "Consumer Staples", "Household Products"),
    ("KO", "The Coca-Cola Company", "Consumer Staples", "Beverages"),
    ("WMT", "Walmart Inc.", "Consumer Staples", "Retail"),
    ("HD", "The Home Depot, Inc.", "Consumer Discretionary", "Home Improvement"),
    ("MCD", "McDonald's Corporation", "Consumer Discretionary", "Restaurants"),
    ("CAT", "Caterpillar Inc.", "Industrials", "Machinery"),
    ("BA", "The Boeing Company", "Industrials", "Aerospace"),
    ("NEE", "NextEra Energy, Inc.", "Utilities", "Electric Utilities"),
    ("DIS", "The Walt Disney Company", "Communication Services", "Entertainment"),
]
INDEX_COMPANY = (INDEX_SYMBOL, "SPDR S&P 500 ETF Trust", "Index", "Exchange Traded Fund")

ALL_COMPANIES = COMPANIES + [INDEX_COMPANY]
SYMBOLS = [c[0] for c in ALL_COMPANIES]

# Every series starts here, so extending the end date never changes earlier prices.
EPOCH = date(2024, 1, 1)


def business_days(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _series(symbol: str, end: date) -> list[dict]:
    rng = random.Random(zlib.crc32(symbol.encode()))
    start_price = 40 + rng.random() * 360
    drift = 0.0002 + rng.random() * 0.0006
    vol = 0.008 if symbol == INDEX_SYMBOL else 0.010 + rng.random() * 0.015
    price = start_price
    rows = []
    for day in business_days(EPOCH, end):
        shock = rng.gauss(0, 1)
        close = max(1.0, price * math.exp(drift - 0.5 * vol * vol + vol * shock))
        high = max(price, close) * (1 + abs(rng.gauss(0, vol / 3)))
        low = min(price, close) * (1 - abs(rng.gauss(0, vol / 3)))
        rows.append({
            "symbol": symbol,
            "date": day,
            "open": round(price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "adjusted_close": round(close, 4),
            "volume": int(1_000_000 + rng.random() * 9_000_000),
        })
        price = close
    return rows


def generate_prices(symbol: str, start: date, end: date) -> list[dict]:
    """Daily rows for one symbol between start and end (inclusive), business days only."""
    return [r for r in _series(symbol, end) if start <= r["date"] <= end]
