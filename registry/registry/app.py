"""Service registry.

Two identical copies run (primary and backup) against the same Redis, so either one can answer.
Each registered service is a Redis key ``svc:{name}`` that expires after 30 seconds unless the
service sends a heartbeat. Searching is open; register, heartbeat and deregister need the shared
key in the X-Registry-Key header.
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from stockplatform import metrics as metrics_module
from stockplatform.config import env, env_bool, env_float, env_list
from stockplatform.events import Broker, SERVICE_EXPIRED, SERVICE_REGISTERED, make_broker
from stockplatform.service import INSTANCE_ID, render_page

log = logging.getLogger("registry")

LEASE_SECONDS = 30
NAMES_KEY = "svc:names"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Registration(BaseModel):
    name: str
    url: str
    description: str = Field(default="", max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=10)
    health_url: str | None = None


_client = httpx.Client(timeout=1.0, follow_redirects=False,
                       limits=httpx.Limits(max_connections=50, max_keepalive_connections=20))


def http_health_check(url: str) -> bool:
    """A service is healthy if GET {url}/health answers 200 within 1 second."""
    try:
        return _client.get(url.rstrip("/") + "/health").status_code == 200
    except httpx.HTTPError:
        return False


class CachedHealth:
    """Remembers each health answer for a few seconds so a burst of searches does not turn into a
    burst of health checks. A service that dies stays listed for at most this long."""

    def __init__(self, check: Callable[[str], bool], ttl: float):
        self.check, self.ttl = check, ttl
        self._seen: dict[str, tuple[float, bool]] = {}
        self._lock = threading.Lock()

    def __call__(self, url: str) -> bool:
        now = time.monotonic()
        if self.ttl > 0:
            with self._lock:
                hit = self._seen.get(url)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        result = self.check(url)
        if self.ttl > 0:
            with self._lock:
                self._seen[url] = (now, result)
        return result


def validate_url(url: str, allowed_domains: list[str], allow_local: bool) -> str | None:
    """Return an error message if the URL may not be registered, else None."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return "url must be an http(s) address"
    if host in LOCAL_HOSTS or host.endswith(".local") or "." not in host:
        # A bare host name such as "price-history" is how services reach each other in Compose.
        return None if allow_local else "local addresses are not allowed here"
    if parsed.scheme != "https" and not allow_local:
        return "url must use https"
    if allowed_domains and not any(host == d or host.endswith("." + d) for d in allowed_domains):
        return "url is not on an allowed domain"
    return None


def create_app(redis_client, broker: Broker | None = None, key: str | None = None,
               allowed_domains: list[str] | None = None, allow_local: bool | None = None,
               health_check: Callable[[str], bool] = http_health_check,
               sweep_seconds: float = 5.0, start_sweeper: bool = True,
               health_ttl: float | None = None) -> FastAPI:
    key = key if key is not None else env("REGISTRY_KEY", "")
    allowed_domains = allowed_domains if allowed_domains is not None else \
        [d.lower() for d in env_list("ALLOWED_DOMAINS")]
    allow_local = allow_local if allow_local is not None else env_bool("ALLOW_LOCAL_URLS", False)
    broker = broker if broker is not None else make_broker()
    health_check = CachedHealth(health_check, env_float("HEALTH_CACHE_SECONDS", 5.0) if health_ttl is None else health_ttl)
    stop = threading.Event()

    # ------------------------------------------------------------------ helpers
    def lease_key(name: str) -> str:
        return f"svc:{name}"

    def require_key(x_registry_key: str | None = Header(default=None)):
        if not key or not x_registry_key or not hmac.compare_digest(x_registry_key, key):
            raise HTTPException(401, "missing or wrong registry key")

    def sweep_once() -> int:
        """Publish an expired event for each service whose lease ran out.

        SREM returns 1 for only one caller, so when both registries sweep, one event goes out.
        """
        published = 0
        for raw in redis_client.smembers(NAMES_KEY):
            name = raw.decode() if isinstance(raw, bytes) else raw
            if not redis_client.exists(lease_key(name)) and redis_client.srem(NAMES_KEY, name):
                broker.publish(SERVICE_EXPIRED, {"name": name}, "registry")
                published += 1
        return published

    def sweep_loop():
        while not stop.wait(sweep_seconds):
            try:
                sweep_once()
            except Exception:
                log.exception("sweep failed")

    def load_all() -> list[dict]:
        names = sorted(n.decode() if isinstance(n, bytes) else n for n in redis_client.smembers(NAMES_KEY))
        records = []
        for name in names:
            raw = redis_client.get(lease_key(name))
            if raw:
                records.append(json.loads(raw))
        return records

    # ------------------------------------------------------------------ app
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_sweeper:
            threading.Thread(target=sweep_loop, name="expiry-sweeper", daemon=True).start()
        yield
        stop.set()
        broker.close()

    app = FastAPI(title="Service Registry", description="Registers stock services and lets the UI search them.",
                  lifespan=lifespan)
    app.state.sweep_once = sweep_once
    metrics_module.install(app, "registry", INSTANCE_ID)

    @app.middleware("http")
    async def instance_header(request, call_next):
        response = await call_next(request)
        response.headers["X-Instance-Id"] = INSTANCE_ID
        return response

    @app.get("/health", include_in_schema=False)
    def health():
        try:
            redis_client.ping()
        except Exception:
            raise HTTPException(503, "redis unavailable")
        return {"status": "ok", "service": "registry", "instance": INSTANCE_ID}

    @app.post("/services", status_code=201, dependencies=[Depends(require_key)])
    def register(reg: Registration):
        if not NAME_RE.match(reg.name):
            raise HTTPException(422, "name must be lower case letters, digits and dashes")
        problem = validate_url(reg.url, allowed_domains, allow_local)
        if problem:
            raise HTTPException(422, problem)
        if reg.health_url:
            problem = validate_url(reg.health_url, allowed_domains, allow_local)
            if problem:
                raise HTTPException(422, "health_url: " + problem)
        is_new = not redis_client.exists(lease_key(reg.name))
        record = {**reg.model_dump(), "registered_at": time.time()}
        redis_client.set(lease_key(reg.name), json.dumps(record), ex=LEASE_SECONDS)
        redis_client.sadd(NAMES_KEY, reg.name)
        if is_new:
            broker.publish(SERVICE_REGISTERED, {"name": reg.name, "url": reg.url}, "registry")
        return {"name": reg.name, "lease_seconds": LEASE_SECONDS}

    @app.post("/services/{name}/heartbeat", dependencies=[Depends(require_key)])
    def heartbeat(name: str):
        if not redis_client.expire(lease_key(name), LEASE_SECONDS):
            raise HTTPException(404, "not registered")
        return {"name": name, "lease_seconds": LEASE_SECONDS}

    @app.delete("/services/{name}", status_code=204, dependencies=[Depends(require_key)])
    def deregister(name: str):
        redis_client.delete(lease_key(name))
        redis_client.srem(NAMES_KEY, name)

    @app.get("/services")
    def search(q: str = Query(default="", max_length=100)):
        """Open search over name, description and tags. Only services that pass a health check are listed."""
        needle = q.strip().lower()
        found = [r for r in load_all()
                 if not needle or needle in r["name"].lower() or needle in r["description"].lower()
                 or any(needle in t.lower() for t in r["tags"])]
        if not found:
            return {"query": q, "services": []}
        with ThreadPoolExecutor(max_workers=min(8, len(found))) as pool:
            healthy = list(pool.map(lambda r: health_check(r.get("health_url") or r["url"]), found))
        return {"query": q, "services": [
            {k: r[k] for k in ("name", "url", "description", "tags")}
            for r, ok in zip(found, healthy) if ok]}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        rows = "".join(f"<tr><td>{r['name']}</td><td>{r['url']}</td><td>{r['description']}</td></tr>"
                       for r in load_all()) or "<tr><td colspan=3>No services registered yet.</td></tr>"
        return render_page("Service Registry",
                           f"<div class='card'><table><tr><th>Name</th><th>URL</th><th>Description</th></tr>{rows}"
                           f"</table></div>")

    return app
