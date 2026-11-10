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
from . import metrics as metrics_module
from . import ui_kit
from .events import Broker, Handler, make_broker
from .registry_client import RegistryClient

log = logging.getLogger("service")

INSTANCE_ID = os.environ.get("INSTANCE_ID") or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

def code_engine_url() -> str:
    """On IBM Cloud Code Engine every app gets CE_APP and CE_DOMAIN, which give its public address."""
    app, domain = env("CE_APP"), env("CE_DOMAIN")
    return f"https://{app}.{domain}" if app and domain else ""


def render_page(title: str, body: str, script: str = "", subtitle: str = "") -> HTMLResponse:
    """Wrap a tool's body HTML in the shared page layout, styles and chart helpers."""
    t = html.escape(title)
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else "<p>Stock Analytics Platform</p>"
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>{t}</title><style>{ui_kit.CSS}</style></head>"
        f"<body><header><div class='row'><div class='logo'>{ui_kit.LOGO}</div><div><h1>{t}</h1>{sub}</div>"
        f"<a id='back' href='/'>&larr; All tools</a></div></header><main>{body}</main>"
        f"<footer>Served by instance <b>{html.escape(INSTANCE_ID)}</b></footer>"
        f"<script>{ui_kit.JS}</script><script>{script}</script></body></html>")


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
        public_url = env("SERVICE_URL") or code_engine_url()
        urls = env_list("REGISTRY_URLS")
        registry = RegistryClient(urls, env("REGISTRY_KEY", ""), name, public_url or "",
                                  description, tags,
                                  health_url=env("SERVICE_HEALTH_URL") or None) if public_url and urls else None

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
    metrics_module.install(app, name, INSTANCE_ID)
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
