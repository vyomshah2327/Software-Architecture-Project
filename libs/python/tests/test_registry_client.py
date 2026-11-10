import httpx

from stockplatform.registry_client import RegistryClient


def make(handler, urls=("http://r1", "http://r2")):
    return RegistryClient(list(urls), "secret", "price-history", "https://s1.example.com",
                          "History", ["price"], transport=httpx.MockTransport(handler))


def test_register_sends_key_and_payload_to_both_registries():
    seen = []

    def handler(req):
        seen.append((req.url.host, req.method, req.url.path, req.headers["x-registry-key"], req.content))
        return httpx.Response(201)

    assert make(handler).register() == 2
    assert {s[0] for s in seen} == {"r1", "r2"}
    assert all(s[3] == "secret" and s[2] == "/services" for s in seen)
    assert b"price-history" in seen[0][4]


def test_register_survives_one_registry_being_down():
    def handler(req):
        if req.url.host == "r1":
            raise httpx.ConnectError("down")
        return httpx.Response(201)

    assert make(handler).register() == 1


def test_register_counts_refusals_as_not_accepted():
    assert make(lambda req: httpx.Response(401)).register() == 0


def test_heartbeat_re_registers_when_registry_forgot_us():
    calls = []

    def handler(req):
        calls.append((req.url.host, req.method, req.url.path))
        if req.url.path.endswith("/heartbeat"):
            return httpx.Response(404)
        return httpx.Response(201)

    assert make(handler, urls=("http://r1",)).heartbeat() == 1
    assert calls == [("r1", "POST", "/services/price-history/heartbeat"), ("r1", "POST", "/services")]


def test_deregister_calls_delete_and_never_raises():
    calls = []

    def handler(req):
        calls.append((req.url.host, req.method))
        if req.url.host == "r1":
            raise httpx.ConnectError("down")
        return httpx.Response(204)

    make(handler).deregister()
    assert ("r2", "DELETE") in calls


def test_start_and_stop_run_heartbeats_then_deregister():
    import time
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        return httpx.Response(200)

    c = make(handler, urls=("http://r1",))
    c.heartbeat_seconds = 0.05
    c.start()
    time.sleep(0.3)
    c.stop()
    paths = [p for _, p in calls]
    assert "/services" in paths and any(p.endswith("/heartbeat") for p in paths)
    assert calls[-1] == ("DELETE", "/services/price-history")


def test_no_registry_urls_means_no_thread():
    c = RegistryClient([], "k", "n", "https://x")
    c.start()
    assert c._thread is None


def test_health_url_is_sent_only_when_set():
    sent = []
    handler = lambda req: sent.append(req.content) or httpx.Response(201)
    RegistryClient(["http://r"], "k", "n", "https://x", health_url="http://n:8000",
                   transport=httpx.MockTransport(handler)).register()
    RegistryClient(["http://r"], "k", "n", "https://x", transport=httpx.MockTransport(handler)).register()
    assert b"health_url" in sent[0] and b"health_url" not in sent[1]
