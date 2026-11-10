import pytest

from stockplatform import events
from stockplatform.events import Envelope, InMemoryBroker, topic_matches, AmqpBroker, SeenIds


@pytest.mark.parametrize("pattern,key,expected", [
    ("market.data.updated", "market.data.updated", True),
    ("market.data.updated", "market.data.other", False),
    ("registry.service.*", "registry.service.expired", True),
    ("registry.service.*", "registry.service.a.b", False),
    ("#", "anything.at.all", True),
    ("registry.#", "registry.service.expired", True),
    ("registry.#", "registry", True),
    ("registry.#", "market.data.updated", False),
    ("*.data.updated", "market.data.updated", True),
])
def test_topic_matching(pattern, key, expected):
    assert topic_matches(pattern, key) is expected


def test_envelope_round_trip():
    e = Envelope(type="market.data.updated", source="ingestor", data={"symbols": ["AAPL"]})
    back = Envelope.from_json(e.to_json())
    assert back == e and back.id and back.time


def test_publish_reaches_only_matching_queues():
    broker = InMemoryBroker()
    got_a, got_b = [], []
    broker.subscribe("a", ["market.data.updated"], got_a.append)
    broker.subscribe("b", ["registry.#"], got_b.append)
    assert broker.publish("market.data.updated", {"x": 1}, "ingestor") is True
    assert [e.type for e in got_a] == ["market.data.updated"] and got_b == []


def test_handler_failing_three_times_goes_to_dead_letters():
    broker = InMemoryBroker()
    calls = []

    def bad(envelope):
        calls.append(envelope.id)
        raise RuntimeError("boom")

    broker.subscribe("q", ["#"], bad)
    broker.publish("alert.triggered", {}, "s8")
    assert len(calls) == 3
    assert len(broker.dead_letters) == 1 and broker.dead_letters[0][0] == "q"


def test_handler_succeeding_on_retry_is_not_dead_lettered():
    broker = InMemoryBroker()
    state = {"n": 0}

    def flaky(envelope):
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("try again")

    broker.subscribe("q", ["#"], flaky)
    broker.publish("alert.triggered", {}, "s8")
    assert state["n"] == 3 and broker.dead_letters == []


def test_same_message_twice_is_handled_once():
    broker = InMemoryBroker()
    seen = []
    broker.subscribe("q", ["#"], seen.append)
    envelope = Envelope(type="market.data.updated", source="ingestor", data={})
    broker.deliver(envelope)
    broker.deliver(envelope)
    assert len(seen) == 1


def test_publish_is_best_effort_when_broker_is_down():
    broker = InMemoryBroker()
    broker.available = False
    assert broker.publish("market.data.updated", {}, "ingestor") is False


def test_amqp_publish_never_raises_when_broker_is_unreachable():
    broker = AmqpBroker("amqp://guest:guest@127.0.0.1:1/")  # nothing listens here
    assert broker.publish("market.data.updated", {}, "ingestor") is False


class FakeChannel:
    def __init__(self):
        self.acked, self.nacked, self.published = [], [], []

    def basic_ack(self, tag):
        self.acked.append(tag)

    def basic_nack(self, tag, requeue=False):
        self.nacked.append((tag, requeue))

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append((exchange, routing_key, properties.headers))


class Method:
    def __init__(self, tag):
        self.delivery_tag = tag


class Props:
    def __init__(self, headers=None):
        self.headers = headers


def amqp_for_tests():
    return AmqpBroker("amqp://guest:guest@127.0.0.1:1/")


def test_amqp_acks_only_after_success_and_skips_repeats():
    broker, ch, seen = amqp_for_tests(), FakeChannel(), SeenIds()
    handled = []
    body = Envelope(type="x", source="s", data={}).to_json().encode()
    broker.handle_delivery(ch, Method(1), Props(), body, "q", handled.append, seen)
    broker.handle_delivery(ch, Method(2), Props(), body, "q", handled.append, seen)  # same id again
    assert len(handled) == 1 and ch.acked == [1, 2]


def test_amqp_retries_then_dead_letters_after_three_attempts():
    broker, seen = amqp_for_tests(), SeenIds()

    def bad(_):
        raise RuntimeError("boom")

    body = Envelope(type="x", source="s", data={}).to_json().encode()
    ch = FakeChannel()
    broker.handle_delivery(ch, Method(1), Props({"x-attempts": 0}), body, "q", bad, seen)
    assert ch.published and ch.published[0][2] == {"x-attempts": 1} and ch.acked == [1] and not ch.nacked
    ch = FakeChannel()
    broker.handle_delivery(ch, Method(2), Props({"x-attempts": 2}), body, "q", bad, seen)
    assert ch.nacked == [(2, False)] and not ch.published


def test_amqp_malformed_message_is_dead_lettered():
    broker, ch = amqp_for_tests(), FakeChannel()
    broker.handle_delivery(ch, Method(7), Props(), b"not json", "q", lambda e: None, SeenIds())
    assert ch.nacked == [(7, False)]
