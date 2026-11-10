"""Factory every stock service uses to build its web app.

It gives each service the same behaviour: a /health endpoint, an X-Instance-Id header on every
response (so the demo can show which copy answered), a landing page at /, registration with the
registry on startup and removal on shutdown, and an optional event subscription.
"""
from __future__ import annotations

import html
import logging
import os
import socket
import uuid
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from .config import env, env_list
from .events import Broker, Handler, make_broker
from .registry_client import RegistryClient

log = logging.getLogger("service")

INSTANCE_ID = os.environ.get("INSTANCE_ID") or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

PAGE_STYLE = """
body{font-family:system-ui,sans-serif;margin:0;background:#f5f6f8;color:#1b1f24}
header{background:#4f2683;color:#fff;padding:14px 24px}
header a{color:#fff;text-decoration:none;font-weight:600}
main{max-width:980px;margin:24px auto;padding:0 16px}
.card{background:#fff;border-radius:8px;padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 3px #0002}
label{display:block;margin:8px 0 2px;font-size:14px}
input,select,button{font:inherit;padding:6px 10px;border:1px solid #bbb;border-radius:6px}
button{background:#4f2683;color:#fff;border:0;cursor:pointer}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e3e3e3}
.muted{color:#666;font-size:13px}.err{color:#b00020}
pre{background:#f0f0f4;padding:10px;border-radius:6px;overflow:auto}
"""


def render_page(title: str, body: str, script: str = "") -> HTMLResponse:
    """Wrap a tool's body HTML in the shared page layout."""
    t = html.escape(title)
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>{t}</title><style>{PAGE_STYLE}</style></head>"
        f"<body><header><a href='/'>{t}</a></header><main>{body}"
        f"<p class='muted'>Served by instance {html.escape(INSTANCE_ID)}</p></main>"
        f"<script>{script}</script></body></html>")


def create_service(name: str, title: str, description: str, tags: list[str] | None = None,
                   subscriptions: list[str] | None = None, on_event: Handler | None = None,
                   broker: Broker | None = None,
                   registry: RegistryClient | None = None,
                   on_startup: Callable[[], None] | None = None,
                   on_shutdown: Callable[[], None] | None = None) -> FastAPI:
    """Build the FastAPI app for one service.

    SERVICE_URL is the public https URL the registry should list (the Code Engine app URL).
    REGISTRY_URLS lists the primary and backup registry; REGISTRY_KEY is the shared secret.
    """
    broker = broker if broker is not None else make_broker()
    if registry is None:
        public_url = env("SERVICE_URL")
        urls = env_list("REGISTRY_URLS")
        registry = RegistryClient(urls, env("REGISTRY_KEY", ""), name, public_url or "",
                                  description, tags) if public_url and urls else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if on_startup:
            on_startup()
        if subscriptions and on_event:
            broker.subscribe(f"{name}.events", subscriptions, on_event)
        if registry:
            registry.start()
        try:
            yield
        finally:
            if registry:
                registry.stop()
            broker.close()
            if on_shutdown:
                on_shutdown()

    app = FastAPI(title=title, description=description, lifespan=lifespan)
    app.state.name = name
    app.state.broker = broker
    app.state.registry = registry

    @app.middleware("http")
    async def add_instance_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Instance-Id"] = INSTANCE_ID
        return response

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "service": name, "instance": INSTANCE_ID}

    return app
