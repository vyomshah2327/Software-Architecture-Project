"""Client a service uses to register itself with the service registry.

The registry runs as a primary and an identical backup. A service registers with every registry
URL it knows, sends a heartbeat every 10 seconds to renew its 30 second lease, and removes itself
on shutdown. If one registry is down, the other still gets the call, so a service stays listed
through a registry failover.

Registry API used here:
    POST   /services                  body {name, url, description, tags}   header X-Registry-Key
    POST   /services/{name}/heartbeat                                       header X-Registry-Key
    DELETE /services/{name}                                                 header X-Registry-Key
"""
from __future__ import annotations

import logging
import threading

import httpx

log = logging.getLogger("registry-client")

HEARTBEAT_SECONDS = 10.0
REQUEST_TIMEOUT = 2.0


class RegistryClient:
    def __init__(self, registry_urls: list[str], key: str, name: str, url: str,
                 description: str = "", tags: list[str] | None = None,
                 heartbeat_seconds: float = HEARTBEAT_SECONDS,
                 transport: httpx.BaseTransport | None = None):
        self.registry_urls = [u.rstrip("/") for u in registry_urls if u]
        self.name = name
        self.payload = {"name": name, "url": url, "description": description, "tags": tags or []}
        self.heartbeat_seconds = heartbeat_seconds
        self._http = httpx.Client(timeout=REQUEST_TIMEOUT, transport=transport,
                                  headers={"X-Registry-Key": key})
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ calls
    def register(self) -> int:
        """Register with every registry. Returns how many accepted."""
        accepted = 0
        for base in self.registry_urls:
            try:
                r = self._http.post(f"{base}/services", json=self.payload)
                if r.status_code < 300:
                    accepted += 1
                else:
                    log.warning("registry %s refused %s: %s %s", base, self.name, r.status_code, r.text[:200])
            except httpx.HTTPError as exc:
                log.warning("registry %s unreachable: %s", base, exc)
        return accepted

    def heartbeat(self) -> int:
        """Renew the lease on every registry. A registry that lost us (404) gets a fresh register."""
        accepted = 0
        for base in self.registry_urls:
            try:
                r = self._http.post(f"{base}/services/{self.name}/heartbeat")
                if r.status_code == 404:
                    r = self._http.post(f"{base}/services", json=self.payload)
                if r.status_code < 300:
                    accepted += 1
            except httpx.HTTPError as exc:
                log.warning("heartbeat to %s failed: %s", base, exc)
        return accepted

    def deregister(self) -> None:
        for base in self.registry_urls:
            try:
                self._http.delete(f"{base}/services/{self.name}")
            except httpx.HTTPError as exc:
                log.warning("deregister from %s failed: %s", base, exc)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Register (retrying in the background until one registry accepts) and begin heartbeats."""
        if not self.registry_urls or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="registry-heartbeat", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if self.register() == 0:
            log.warning("no registry accepted %s yet, will keep trying", self.name)
        while not self._stop.wait(self.heartbeat_seconds):
            self.heartbeat()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        self.deregister()
        self._http.close()
