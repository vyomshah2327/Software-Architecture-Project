"""Where daily prices come from. The ingestor is the only part of the platform that calls a source."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import httpx

from stockplatform import fakedata


class SourceError(Exception):
    """The source refused or failed. ``rate_limited`` tells the caller to stop for today."""

    def __init__(self, message: str, rate_limited: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited


@dataclass
class Fetched:
    rows: list[dict]
    raw: str            # the untouched response, archived as it came
    api_calls: int      # calls spent against the daily quota


class DataSource(Protocol):
    def fetch_daily(self, symbol: str) -> Fetched: ...


class FakeSource:
    """Deterministic sample data. Costs no quota, so demos never run dry."""

    def __init__(self, days: int = 365, today: date | None = None):
        self.days, self.today = days, today

    def fetch_daily(self, symbol: str) -> Fetched:
        end = self.today or date.today()
        rows = fakedata.generate_prices(symbol, end - timedelta(days=self.days), end)
        raw = json.dumps([{**r, "date": r["date"].isoformat()} for r in rows], default=str)
        return Fetched(rows, raw, 0)


class AlphaVantageSource:
    """Alpha Vantage TIME_SERIES_DAILY. The free tier has no adjusted close, so close is used for both."""

    URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, function: str = "TIME_SERIES_DAILY", client: httpx.Client | None = None):
        self.api_key, self.function = api_key, function
        self.client = client or httpx.Client(timeout=20)

    def fetch_daily(self, symbol: str) -> Fetched:
        try:
            r = self.client.get(self.URL, params={"function": self.function, "symbol": symbol,
                                                   "outputsize": "compact", "apikey": self.api_key})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError(f"request failed: {exc}") from exc
        return Fetched(parse_alpha_vantage(r.json()), r.text, 1)


def parse_alpha_vantage(payload: dict) -> list[dict]:
    for key in ("Note", "Information"):
        if key in payload:
            raise SourceError(payload[key], rate_limited=True)
    if "Error Message" in payload:
        raise SourceError(payload["Error Message"])
    series = payload.get("Time Series (Daily)")
    if not series:
        raise SourceError("response has no daily series")
    rows = []
    for day, v in series.items():
        close = float(v["4. close"])
        rows.append({
            "date": date.fromisoformat(day),
            "open": float(v["1. open"]), "high": float(v["2. high"]), "low": float(v["3. low"]),
            "close": close, "adjusted_close": float(v.get("5. adjusted close", close)),
            "volume": int(float(v.get("6. volume", v.get("5. volume", 0)))),
        })
    return sorted(rows, key=lambda r: r["date"])
