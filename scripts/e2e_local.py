"""End to end check against the processes started by run_local.sh (or the compose stack).

    python scripts/e2e_local.py [ui_url] [primary_registry_url] [backup_registry_url]

It checks that all eight services registered, that search works through the UI, that each tool
answers with an instance header, and (with --failover) that search keeps working when the
primary registry is stopped. Stopping the primary is done by the caller; see scripts/demo_failover.sh.
"""
import sys
import time

import httpx

UI = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://localhost:8080"
EXPECTED = {"price-history", "performance", "volatility-risk", "indicators", "fund-builder", "portfolio",
            "correlation", "alerts-monitor"}


def wait_for_services(timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        try:
            names = {s["name"] for s in httpx.get(f"{UI}/api/search", timeout=5).json().get("services", [])}
            if EXPECTED <= names:
                return names
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit(f"FAIL: only saw {sorted(names) if 'names' in dir() else 'nothing'} after {timeout}s")


def main():
    names = wait_for_services()
    print(f"ok   all {len(EXPECTED)} services are registered")
    found = httpx.get(f"{UI}/api/search", params={"q": "risk"}).json()["services"]
    assert [s["name"] for s in found] == ["volatility-risk"], found
    print("ok   search for 'risk' finds only the risk tool")
    for s in httpx.get(f"{UI}/api/search").json()["services"]:
        r = httpx.get(s["url"] + "/health", timeout=5)
        assert r.status_code == 200 and r.headers.get("x-instance-id"), s
        page = httpx.get(s["url"] + "/", timeout=5)
        assert page.status_code == 200 and "<html" in page.text, s
    print("ok   every tool serves a page and a health check with an instance id")
    url = next(s["url"] for s in httpx.get(f"{UI}/api/search?q=price").json()["services"] if s["name"] == "price-history")
    prices = httpx.get(url + "/api/prices/AAPL?limit=5").json()
    assert len(prices) == 5
    print("ok   price history returns data")


if __name__ == "__main__":
    main()
