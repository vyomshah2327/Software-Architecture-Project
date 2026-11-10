"""Write a Prometheus file_sd targets file from the live registry, for the Code Engine deployment.

    python scripts/prometheus_targets.py <ui-or-registry-url> > monitoring/targets.json

Each service has one public address, so Prometheus scrapes that address; Code Engine hands each
scrape to one of the running copies. The instance label on the metrics shows which copy answered.
"""
import json
import sys
from urllib.parse import urlparse

import httpx

base = sys.argv[1].rstrip("/")
path = "/api/search" if "registry" not in base else "/services"
services = httpx.get(base + path, timeout=15).json()["services"]
targets = [{"targets": [urlparse(s["url"]).netloc], "labels": {"service": s["name"], "scheme": urlparse(s["url"]).scheme}}
           for s in services]
print(json.dumps(targets, indent=2))
