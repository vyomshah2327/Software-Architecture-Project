# Architecture notes

## The shape of the system

```
 Browser ──> UI (Node) ──search──> Registry primary ─┐
                  │  └─retry 2 s─> Registry backup  ─┼─> Redis (leases)
                  │                                   │
                  └─ opens tool pages ─┐              │ register + heartbeat
                                       v              │
   S1 .. S8 (one Code Engine app each, 1 to 5 copies) ┘
        │ read prices                    ^ subscribe
        v                                │
    PostgreSQL <── Ingestor (daily) ──> RabbitMQ  topic exchange platform.events
```

## Decisions and the reasons

**One address per service, no gateway.** Code Engine gives each app one public address and runs 1 to 5 copies behind it. The registry stores that one address. Load balancing is Code Engine's job, so there is no gateway to build, scale or fail. The `X-Instance-Id` header makes the copies visible.

**Registry state lives in Redis.** A service is one key with a 30 second expiry that its heartbeat renews. If a service dies, its key disappears and it drops out of search by itself. Primary and backup are the same image reading the same Redis, so a failover loses nothing. Registering needs the shared key; searching is open because the UI is public.

**Health check before listing.** A search only returns services that answer `/health`. Results are remembered for 5 seconds, because without that a burst of searches caused a burst of health checks and the registry could not answer inside the UI's 2 second timeout (measured: 18 requests per second and 4 second p95 before, 325 per second and 171 ms p95 after on one machine).

**Events, best effort.** One topic exchange. Each subscriber has its own durable queue, acknowledges after handling, skips messages it has already seen, and sends a message to a dead-letter queue after 3 failures. Publishing never raises: if RabbitMQ is down, searching, registering and every tool page still work.

| Event | Published by | Used by |
|---|---|---|
| `registry.service.registered`, `registry.service.expired` | Registry | Available to any subscriber. Only one registry publishes an expiry, because the expiry sweeper removes the name from a shared set first. |
| `market.data.updated` | Ingestor, after the commit | S1 to S5 and S7 clear their result cache. S8 checks its alert rules. |
| `portfolio.holding.changed`, `portfolio.watchlist.changed` | S6 | Available to any subscriber |
| `alert.triggered` | S8 | UI shows a pop-up |

**Alerts fire on the edge.** A rule fires when it goes from not met to met and re-arms when it stops being met. Handling the same event twice, or running the check twice, never creates a second alert.

**Data access follows least privilege.** `svc_reader` (S1 to S5, S7) can only read market data. `svc_s6` can write holdings and the watchlist. `svc_s8` can write rules and alerts and read the watchlist. `ingestor` can write prices and its log. Terraform generates the passwords.

**The ingestor is the only caller of Alpha Vantage.** It counts API calls in `ingestion_log` against the daily limit of 25, waits between calls to stay under 5 per minute, stops for the day when the source says the limit is reached, archives every raw response (Object Storage in the cloud, a folder locally), and upserts so a second run never duplicates rows. The free Alpha Vantage endpoint has no adjusted close, so close is stored in both columns. A fake source with deterministic prices is used for demos and tests.

**Calculations are plain functions.** `libs/python/stockplatform/analytics.py` holds returns, risk, correlation, indicators and the back-test with no database or web code, so they are easy to test.

## Known limits

* The managed RabbitMQ and Redis certificates are signed by a private authority. The deployment turns off certificate checking for those two connections (`AMQP_TLS_VERIFY=false`, `ssl_cert_reqs=none`). That is fine for a demo; production should mount the authority's certificate.
* Code Engine apps scale on concurrent requests. A service that starts from zero would be slow to answer, so the minimum is 1 copy.
* There are no user accounts. Portfolio and alerts take a `user_id`, which defaults to `demo`.
