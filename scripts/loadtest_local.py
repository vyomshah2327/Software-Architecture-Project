"""Small load test with no extra tools:  python scripts/loadtest_local.py <ui-url> [seconds] [concurrency]"""
import asyncio
import random
import statistics
import sys
import time

import httpx

UI = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 20
CONCURRENCY = int(sys.argv[3]) if len(sys.argv) > 3 else 20
SYMBOLS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "KO", "SPY"]


async def worker(client, urls, stop_at, latencies, errors, instances):
    while time.time() < stop_at:
        roll, sym = random.random(), random.choice(SYMBOLS)
        if roll < 0.4:
            url = f"{UI}/api/search?q={random.choice(['risk', 'price', 'portfolio', ''])}"
        elif roll < 0.6:
            url = f"{urls['price-history']}/api/prices/{sym}?limit=60"
        elif roll < 0.8:
            url = f"{urls['performance']}/api/performance/{sym}?period=1y"
        else:
            url = f"{urls['volatility-risk']}/api/risk/{sym}?days=252"
        start = time.perf_counter()
        try:
            r = await client.get(url)
            latencies.append(time.perf_counter() - start)
            if r.status_code != 200:
                errors.append(r.status_code)
            if "x-instance-id" in r.headers:
                instances.add(r.headers["x-instance-id"])
        except httpx.HTTPError as exc:
            errors.append(type(exc).__name__)


async def main():
    async with httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=CONCURRENCY * 2)) as client:
        found = []
        for _ in range(30):  # wait until the tools we call have registered
            found = (await client.get(f"{UI}/api/search")).json()["services"]
            if {"price-history", "performance", "volatility-risk"} <= {s["name"] for s in found}:
                break
            await asyncio.sleep(1)
        urls = {s["name"]: s["url"].rstrip("/") for s in found}
        latencies, errors, instances = [], [], set()
        stop_at = time.time() + SECONDS
        await asyncio.gather(*[worker(client, urls, stop_at, latencies, errors, instances) for _ in range(CONCURRENCY)])
    latencies.sort()
    q = lambda p: latencies[min(len(latencies) - 1, int(len(latencies) * p))] * 1000
    print(f"{len(latencies)} requests in {SECONDS:.0f}s with {CONCURRENCY} workers = {len(latencies) / SECONDS:.0f} req/s")
    print(f"p50 {q(0.5):.0f} ms   p95 {q(0.95):.0f} ms   p99 {q(0.99):.0f} ms   mean {statistics.mean(latencies) * 1000:.0f} ms")
    from collections import Counter; print(Counter(errors)); print(f"errors {len(errors)}   distinct instances answering {len(instances)}")


asyncio.run(main())
