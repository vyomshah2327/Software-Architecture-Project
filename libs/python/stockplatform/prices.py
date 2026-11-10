"""Loading price series from the database for the analytical services."""
from __future__ import annotations

from datetime import date

from . import db


def load_series(symbol: str, days: int = 252, end: date | None = None) -> list[tuple[date, float]]:
    """The last ``days`` trading rows for a symbol, oldest first, as (date, adjusted close)."""
    rows = db.query(
        "SELECT date, adjusted_close FROM prices WHERE symbol = %s AND (%s::date IS NULL OR date <= %s) "
        "ORDER BY date DESC LIMIT %s", (symbol, end, end, days))
    return [(r["date"], float(r["adjusted_close"])) for r in reversed(rows)]


def load_aligned(symbols: list[str], days: int = 252) -> tuple[list[date], dict[str, list[float]]]:
    """Series for several symbols cut down to the dates every symbol has."""
    raw = {s: dict(load_series(s, days)) for s in symbols}
    common = sorted(set.intersection(*(set(v) for v in raw.values()))) if raw else []
    return common, {s: [raw[s][d] for d in common] for s in symbols}


def symbol_exists(symbol: str) -> bool:
    return bool(db.query("SELECT 1 FROM companies WHERE symbol = %s", (symbol,)))
