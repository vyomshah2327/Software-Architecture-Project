"""One ingestion run: fetch each company, archive the raw response, upsert, then announce.

Rules: stay inside the daily and per-minute API limits, never write the same row twice (upsert),
and publish ``market.data.updated`` only after the data is committed.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from stockplatform import db
from stockplatform.config import env, env_int, env_float
from stockplatform.events import Broker, MARKET_DATA_UPDATED, make_broker

from .archive import make_archive
from .sources import AlphaVantageSource, DataSource, FakeSource, SourceError

log = logging.getLogger("ingestor")

UPSERT = """INSERT INTO prices (symbol, date, open, high, low, close, adjusted_close, volume)
VALUES (%(symbol)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(adjusted_close)s, %(volume)s)
ON CONFLICT (symbol, date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
close = EXCLUDED.close, adjusted_close = EXCLUDED.adjusted_close, volume = EXCLUDED.volume"""


def calls_used_today() -> int:
    rows = db.query("SELECT COALESCE(SUM(api_calls_used), 0) AS n FROM ingestion_log "
                    "WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'")
    return int(rows[0]["n"])


def log_row(run_id: str, symbol: str | None, status: str, rows: int = 0, calls: int = 0, message: str = "") -> None:
    db.execute("INSERT INTO ingestion_log (run_id, symbol, status, rows_fetched, api_calls_used, message) "
               "VALUES (%s, %s, %s, %s, %s, %s)", (run_id, symbol, status, rows, calls, message[:500]))


def run(source: DataSource, archive, broker: Broker, symbols: list[str] | None = None,
        daily_limit: int = 25, per_minute: int = 5, sleep=time.sleep) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:6]
    if symbols is None:
        symbols = [r["symbol"] for r in db.query("SELECT symbol FROM companies ORDER BY symbol")]
    used = calls_used_today()
    updated, failed, skipped = [], [], []
    spacing = 60.0 / per_minute if per_minute > 0 else 0

    for i, symbol in enumerate(symbols):
        if used >= daily_limit:
            skipped = symbols[i:]
            log_row(run_id, None, "quota", message=f"daily limit {daily_limit} reached, {len(skipped)} left for tomorrow")
            break
        try:
            fetched = source.fetch_daily(symbol)
        except SourceError as exc:
            failed.append(symbol)
            log_row(run_id, symbol, "rate_limited" if exc.rate_limited else "failed", message=str(exc))
            if exc.rate_limited:
                skipped = symbols[i + 1:]
                break
            continue
        used += fetched.api_calls
        try:
            archive.save(run_id, symbol, fetched.raw)
            with db.connection() as conn:  # one transaction per symbol
                with conn.cursor() as cur:
                    cur.executemany(UPSERT, [{**r, "symbol": symbol} for r in fetched.rows])
            updated.append(symbol)
            log_row(run_id, symbol, "ok", len(fetched.rows), fetched.api_calls)
        except Exception as exc:
            log.exception("storing %s failed", symbol)
            failed.append(symbol)
            log_row(run_id, symbol, "failed", calls=fetched.api_calls, message=str(exc))
        if fetched.api_calls and spacing and i < len(symbols) - 1:
            sleep(spacing)

    published = broker.publish(MARKET_DATA_UPDATED, {"run_id": run_id, "symbols": updated}, "ingestor") if updated else False
    return {"run_id": run_id, "updated": updated, "failed": failed, "skipped": skipped, "published": published}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    kind = env("DATA_SOURCE", "fake")
    source = AlphaVantageSource(env("ALPHAVANTAGE_KEY", "demo")) if kind == "alphavantage" \
        else FakeSource(env_int("FAKE_DAYS", 365))
    result = run(source, make_archive(), make_broker(), daily_limit=env_int("DAILY_API_LIMIT", 25),
                 per_minute=env_int("PER_MINUTE_LIMIT", 5))
    log.info("run %s: %d updated, %d failed, %d skipped, event published: %s", result["run_id"],
             len(result["updated"]), len(result["failed"]), len(result["skipped"]), result["published"])
    db.close_pool()
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
