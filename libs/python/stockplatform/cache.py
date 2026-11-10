"""Small in-process result cache. Cleared whenever new market data arrives."""
from __future__ import annotations

import threading
import time


class TTLCache:
    def __init__(self, ttl: float = 300.0, max_items: int = 500):
        self.ttl, self.max_items = ttl, max_items
        self._data: dict = {}
        self._lock = threading.Lock()

    def get_or_compute(self, key, compute):
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = compute()
        with self._lock:
            if len(self._data) >= self.max_items:
                self._data.pop(next(iter(self._data)))
            self._data[key] = (now, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
