"""Request metrics in the Prometheus text format, with no extra dependency.

Adds /metrics to an app. Counts requests by route and status class and records latency in a
histogram. Routes are the path templates (/api/prices/{symbol}), so labels stay few.
"""
from __future__ import annotations

import threading
import time

from fastapi import FastAPI, Request, Response

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


class Metrics:
    def __init__(self, service: str, instance: str):
        self.service, self.instance = service, instance
        self.requests: dict[tuple[str, str, str], int] = {}
        self.buckets: dict[str, list[int]] = {}
        self.sums: dict[str, float] = {}
        self.counts: dict[str, int] = {}
        self.in_flight = 0
        self._lock = threading.Lock()

    def observe(self, route: str, method: str, status: int, seconds: float) -> None:
        with self._lock:
            key = (route, method, f"{status // 100}xx")
            self.requests[key] = self.requests.get(key, 0) + 1
            counts = self.buckets.setdefault(route, [0] * len(BUCKETS))
            for i, edge in enumerate(BUCKETS):
                if seconds <= edge:
                    counts[i] += 1
            self.sums[route] = self.sums.get(route, 0.0) + seconds
            self.counts[route] = self.counts.get(route, 0) + 1

    def render(self) -> str:
        base = f'service="{self.service}",instance="{self.instance}"'
        lines = ["# TYPE http_requests_total counter"]
        with self._lock:
            for (route, method, status), n in sorted(self.requests.items()):
                lines.append(f'http_requests_total{{{base},route="{route}",method="{method}",status="{status}"}} {n}')
            lines.append("# TYPE http_request_duration_seconds histogram")
            for route, counts in sorted(self.buckets.items()):
                for edge, c in zip(BUCKETS, counts):
                    lines.append(f'http_request_duration_seconds_bucket{{{base},route="{route}",le="{edge}"}} {c}')
                lines.append(f'http_request_duration_seconds_bucket{{{base},route="{route}",le="+Inf"}} {self.counts[route]}')
                lines.append(f'http_request_duration_seconds_sum{{{base},route="{route}"}} {self.sums[route]:.6f}')
                lines.append(f'http_request_duration_seconds_count{{{base},route="{route}"}} {self.counts[route]}')
            lines.append("# TYPE http_requests_in_flight gauge")
            lines.append(f"http_requests_in_flight{{{base}}} {self.in_flight}")
        return "\n".join(lines) + "\n"


def install(app: FastAPI, service: str, instance: str) -> Metrics:
    metrics = Metrics(service, instance)
    app.state.metrics = metrics

    @app.middleware("http")
    async def measure(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        metrics.in_flight += 1
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            metrics.in_flight -= 1
            route = request.scope.get("route")
            metrics.observe(getattr(route, "path", "unmatched"), request.method, status, time.perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    def expose():
        return Response(metrics.render(), media_type="text/plain; version=0.0.4")

    return metrics
