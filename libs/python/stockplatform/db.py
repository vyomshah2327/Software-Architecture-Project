"""PostgreSQL access through a shared connection pool."""
from __future__ import annotations

import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import env

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def get_pool(url: str | None = None) -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            dsn = url or env("DATABASE_URL")
            if not dsn:
                raise RuntimeError("DATABASE_URL is not set")
            _pool = ConnectionPool(dsn, min_size=1, max_size=int(env("DB_POOL_MAX", "5")),
                                   kwargs={"row_factory": dict_row}, open=True)
        return _pool


def close_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def connection():
    with get_pool().connection() as conn:
        yield conn


def query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """Run a read query and return rows as dictionaries."""
    with connection() as conn:
        return list(conn.execute(sql, params).fetchall())


def execute(sql: str, params: tuple | dict | None = None) -> int:
    """Run a write statement in its own transaction and return the affected row count."""
    with connection() as conn:
        return conn.execute(sql, params).rowcount


def ping() -> bool:
    try:
        query("SELECT 1")
        return True
    except Exception:
        return False
