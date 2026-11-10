"""Event publishing and subscribing on one topic exchange.

Rules every service follows:
  * One topic exchange, ``platform.events``; every subscriber has its own durable queue.
  * Every message is a JSON envelope: id, type, time, source, data.
  * A handler is acknowledged only after it succeeds. A message that fails 3 times goes to a
    dead-letter queue for inspection.
  * Handlers are idempotent: a message id that was already handled on a queue is skipped.
  * Publishing is best effort. If the broker is down, ``publish`` returns False and never raises,
    so searching, registering and tool pages keep working.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable

log = logging.getLogger("events")

EXCHANGE = "platform.events"
DEAD_LETTER_EXCHANGE = "platform.events.dlx"
MAX_ATTEMPTS = 3

# Event types
SERVICE_REGISTERED = "registry.service.registered"
SERVICE_EXPIRED = "registry.service.expired"
MARKET_DATA_UPDATED = "market.data.updated"
HOLDING_CHANGED = "portfolio.holding.changed"
WATCHLIST_CHANGED = "portfolio.watchlist.changed"
ALERT_TRIGGERED = "alert.triggered"


@dataclass
class Envelope:
    type: str
    source: str
    data: dict
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(text: str | bytes) -> "Envelope":
        raw = json.loads(text)
        return Envelope(type=raw["type"], source=raw["source"], data=raw.get("data", {}),
                        id=raw["id"], time=raw["time"])


Handler = Callable[[Envelope], None]


def topic_matches(pattern: str, key: str) -> bool:
    """AMQP topic matching: ``*`` is exactly one word, ``#`` is zero or more words."""
    def match(p: list[str], k: list[str]) -> bool:
        if not p:
            return not k
        if p[0] == "#":
            return any(match(p[1:], k[i:]) for i in range(len(k) + 1))
        if not k:
            return False
        if p[0] == "*" or p[0] == k[0]:
            return match(p[1:], k[1:])
        return False

    return match(pattern.split("."), key.split("."))


class SeenIds:
    """Bounded memory of handled message ids, used to make handlers idempotent."""

    def __init__(self, size: int = 5000):
        self._ids: OrderedDict[str, None] = OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def add_if_new(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self._ids:
                return False
            self._ids[message_id] = None
            if len(self._ids) > self._size:
                self._ids.popitem(last=False)
            return True

    def forget(self, message_id: str) -> None:
        with self._lock:
            self._ids.pop(message_id, None)


class Broker(ABC):
    @abstractmethod
    def publish(self, routing_key: str, data: dict, source: str) -> bool:
        """Publish an event. Returns True if the broker accepted it; never raises."""

    @abstractmethod
    def subscribe(self, queue: str, bindings: list[str], handler: Handler) -> None:
        """Start consuming ``bindings`` into the durable ``queue`` with the given handler."""

    def close(self) -> None:  # pragma: no cover - default
        pass


class NullBroker(Broker):
    """Used when no broker is configured. Publishing is skipped, subscribing does nothing."""

    def publish(self, routing_key, data, source):
        return False

    def subscribe(self, queue, bindings, handler):
        log.info("no broker configured, queue %s is not consumed", queue)


class InMemoryBroker(Broker):
    """A single-process broker with the same delivery rules. Used in tests and demos."""

    def __init__(self):
        self.queues: dict[str, dict] = {}
        self.dead_letters: list[tuple[str, Envelope]] = []
        self.published: list[Envelope] = []
        self.available = True
        self._lock = threading.Lock()

    def publish(self, routing_key, data, source):
        if not self.available:
            return False
        envelope = Envelope(type=routing_key, source=source, data=data)
        self.published.append(envelope)
        self.deliver(envelope)
        return True

    def deliver(self, envelope: Envelope) -> None:
        with self._lock:
            targets = [(name, q) for name, q in self.queues.items()
                       if any(topic_matches(b, envelope.type) for b in q["bindings"])]
        for name, q in targets:
            self._handle(name, q, envelope)

    def _handle(self, name: str, q: dict, envelope: Envelope) -> None:
        if not q["seen"].add_if_new(envelope.id):
            return
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                q["handler"](envelope)
                return
            except Exception:
                log.exception("handler failed on %s (attempt %d)", name, attempt)
        q["seen"].forget(envelope.id)
        self.dead_letters.append((name, envelope))

    def subscribe(self, queue, bindings, handler):
        with self._lock:
            self.queues[queue] = {"bindings": list(bindings), "handler": handler, "seen": SeenIds()}


class AmqpBroker(Broker):
    """RabbitMQ implementation using pika."""

    def __init__(self, url: str, reconnect_delay: float = 3.0):
        import pika  # imported here so tests that do not need RabbitMQ stay light
        self._pika = pika
        self._params = pika.URLParameters(url)
        self._params.socket_timeout = 3
        self._params.blocked_connection_timeout = 3
        self._reconnect_delay = reconnect_delay
        self._pub_conn = None
        self._pub_ch = None
        self._pub_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ publishing
    def _publisher(self):
        if self._pub_ch is None or self._pub_ch.is_closed:
            self._pub_conn = self._pika.BlockingConnection(self._params)
            self._pub_ch = self._pub_conn.channel()
            self._pub_ch.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        return self._pub_ch

    def publish(self, routing_key, data, source):
        envelope = Envelope(type=routing_key, source=source, data=data)
        for attempt in (1, 2):
            try:
                with self._pub_lock:
                    self._publisher().basic_publish(
                        EXCHANGE, routing_key, envelope.to_json().encode(),
                        properties=self._pika.BasicProperties(
                            content_type="application/json", delivery_mode=2, message_id=envelope.id))
                return True
            except Exception as exc:
                log.warning("publish %s failed (attempt %d): %s", routing_key, attempt, exc)
                with self._pub_lock:
                    self._pub_ch = None
                    try:
                        if self._pub_conn is not None:
                            self._pub_conn.close()
                    except Exception:
                        pass
        return False

    # ------------------------------------------------------------------ consuming
    def subscribe(self, queue, bindings, handler):
        thread = threading.Thread(target=self._consume_forever, args=(queue, bindings, handler),
                                  name=f"consumer-{queue}", daemon=True)
        thread.start()
        self._threads.append(thread)

    def _consume_forever(self, queue, bindings, handler):
        seen = SeenIds()
        while not self._stop.is_set():
            try:
                conn = self._pika.BlockingConnection(self._params)
                ch = conn.channel()
                self.declare_queue(ch, queue, bindings)
                ch.basic_qos(prefetch_count=10)
                ch.basic_consume(queue, lambda c, m, p, b: self.handle_delivery(c, m, p, b, queue, handler, seen))
                log.info("consuming %s bound to %s", queue, bindings)
                while not self._stop.is_set():
                    conn.process_data_events(time_limit=1)
                conn.close()
            except Exception as exc:
                log.warning("consumer %s lost its connection: %s", queue, exc)
                self._stop.wait(self._reconnect_delay)

    @staticmethod
    def declare_queue(ch, queue, bindings):
        ch.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        ch.exchange_declare(DEAD_LETTER_EXCHANGE, exchange_type="direct", durable=True)
        ch.queue_declare(f"{queue}.dlq", durable=True)
        ch.queue_bind(f"{queue}.dlq", DEAD_LETTER_EXCHANGE, routing_key=queue)
        ch.queue_declare(queue, durable=True, arguments={
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE, "x-dead-letter-routing-key": queue})
        for binding in bindings:
            ch.queue_bind(queue, EXCHANGE, routing_key=binding)

    def handle_delivery(self, ch, method, properties, body, queue, handler, seen: SeenIds):
        """Process one delivery. Acknowledge only after success; dead-letter after 3 attempts."""
        headers = (properties.headers or {}) if properties is not None else {}
        attempts = int(headers.get("x-attempts", 0)) + 1
        try:
            envelope = Envelope.from_json(body)
        except Exception:
            log.error("dropping malformed message on %s", queue)
            ch.basic_nack(method.delivery_tag, requeue=False)
            return
        if not seen.add_if_new(envelope.id):
            ch.basic_ack(method.delivery_tag)  # already handled: acknowledge and skip
            return
        try:
            handler(envelope)
            ch.basic_ack(method.delivery_tag)
        except Exception:
            log.exception("handler failed on %s (attempt %d)", queue, attempts)
            seen.forget(envelope.id)
            if attempts >= MAX_ATTEMPTS:
                ch.basic_nack(method.delivery_tag, requeue=False)  # goes to the dead-letter queue
            else:
                ch.basic_publish("", queue, body, properties=self._pika.BasicProperties(
                    content_type="application/json", delivery_mode=2, message_id=envelope.id,
                    headers={"x-attempts": attempts}))
                ch.basic_ack(method.delivery_tag)

    def close(self):
        self._stop.set()
        try:
            if self._pub_conn is not None:
                self._pub_conn.close()
        except Exception:
            pass


def make_broker(url: str | None = None) -> Broker:
    """Pick the broker from configuration: RabbitMQ if AMQP_URL is set, otherwise no broker."""
    from .config import env
    amqp = url if url is not None else env("AMQP_URL")
    if amqp == "memory://":
        return InMemoryBroker()
    if amqp:
        return AmqpBroker(amqp)
    return NullBroker()
