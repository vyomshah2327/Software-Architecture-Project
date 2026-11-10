# Requirement checklist

Each row says where a requirement is built and what proves it. "Test" means an automated test that runs in CI. "Script" means something you run by hand. "Not verified here" means it is written but could not be run in the place it was developed (no Docker, Terraform or RabbitMQ there).

## Service registry

| Requirement | Where | Proof |
|---|---|---|
| Services register themselves and can be searched | `registry/registry/app.py`, `libs/python/stockplatform/registry_client.py` | Test: `test_search_is_open_and_matches_name_description_and_tags`, `test_register_sends_key_and_payload_to_both_registries`. Script: `scripts/e2e_local.py` |
| Only trusted services can register | Shared key in `X-Registry-Key` | Test: `test_register_needs_the_key` |
| Only https addresses on our own domain | `validate_url`, `ALLOWED_DOMAINS`, local override `ALLOW_LOCAL_URLS` | Test: `test_url_rules`, `test_bad_name_and_url_are_rejected` |
| Dead services drop out | 30 s lease, 10 s heartbeat | Test: `test_heartbeat_renews_lease_and_unknown_service_gets_404`, `test_expired_lease_disappears_and_event_is_published_once_across_two_registries` |
| Only healthy services are listed | Health check before listing, cached 5 s | Test: `test_unhealthy_services_are_not_listed`, `test_health_results_are_cached_for_the_ttl` |
| Backup registry with identical data | Same image, same Redis | Test: `test_backup_answers_with_the_same_data_as_primary` |
| Fail over to the backup quickly | UI retries on the backup after 2 s (plan: within 10 s) | Test: `a silent primary is abandoned after the timeout and the backup answers` (UI). Script: `scripts/demo_failover.sh` measured about 2 s locally. Load: `loadtests/failover.js` (not run here) |
| Services survive a registry failure | Client registers with both registries and heartbeats both | Test: `test_register_survives_one_registry_being_down` |
| Registry announces changes | `registry.service.registered` and `.expired` | Test: `test_registered_event_is_published_once_per_new_service` |

## Consumer UI

| Requirement | Where | Proof |
|---|---|---|
| Search for tools and open them | `ui/public/index.html`, `ui/src/app.js` | Test: UI `search endpoint returns services`. Script: `scripts/e2e_local.py` |
| Tells the user when the backup is serving | Amber banner from `/api/events` | Test: UI `event stream announces registry role, list changes and alerts` |
| Clear message when no registry answers | HTTP 503 with a friendly message | Test: UI `answers 503 with a friendly message` |
| List updates without a refresh | Server-sent events, polling the registry | Test: UI `event stream announces ...` |
| Shows alerts as they happen | `alert.triggered` from RabbitMQ to a pop-up | Not verified here (needs RabbitMQ) |

## Stock services

| Service | API | Proof |
|---|---|---|
| S1 Price History | `/api/companies`, `/api/prices/{symbol}`, `/api/latest/{symbol}` | `services/tests/test_price_history.py` |
| S2 Performance | `/api/performance/{symbol}`, `/api/compare` | `services/tests/test_analytical_services.py` |
| S3 Volatility and Risk | `/api/risk/{symbol}` | same file |
| S4 Technical Indicators | `/api/indicators/{symbol}` | same file |
| S5 Fund Builder | `/api/backtest`, `/api/suggest`, `/api/sectors` | `services/tests/test_fund_correlation.py` |
| S6 Portfolio | `/api/holdings`, `/api/portfolio`, `/api/watchlist` | `services/tests/test_portfolio_alerts.py` |
| S7 Correlation | `/api/correlation` | `services/tests/test_fund_correlation.py` |
| S8 Alerts and Monitor | `/api/rules`, `/api/alerts`, `/api/monitor`, `/api/evaluate` | `services/tests/test_portfolio_alerts.py` |
| The maths | `libs/python/stockplatform/analytics.py` | `libs/python/tests/test_analytics.py` |
| Each service has a page, an API description, a health check and registers itself | `create_service`, `docs/openapi/*.json` | `libs/python/tests/test_service.py`, `scripts/e2e_local.py` |

## Data and events

| Requirement | Where | Proof |
|---|---|---|
| Daily ingestion that stays inside the API limits | `ingestor/ingestor/run.py` | Test: `test_run_stops_at_daily_limit`, `test_per_minute_pacing_sleeps_between_paid_calls`, `test_rate_limit_from_source_stops_the_run` |
| Running twice adds no duplicates | Upsert on (symbol, date) | Test: `test_run_is_idempotent_archives_and_publishes_after_commit` |
| Raw responses are kept | `ingestor/ingestor/archive.py` | Test: `test_local_archive_writes_raw`, `test_s3_archive_puts_object` |
| Announce new data only after commit, and only if something changed | `run.py` | Test: same idempotency test, `test_no_event_when_nothing_updated` |
| Least-privilege database roles | `db/roles.sql` | Run: the service tests pass under `svc_reader`, `svc_s6`, `svc_s8` (done during development) |
| Retries, dead letters and idempotent handling | `libs/python/stockplatform/events.py` | Test: `test_handler_failing_three_times_goes_to_dead_letters`, `test_same_message_twice_is_handled_once`, `test_amqp_retries_then_dead_letters_after_three_attempts`. Real RabbitMQ: not verified here |
| Publishing never breaks the caller | `Broker.publish` | Test: `test_amqp_publish_never_raises_when_broker_is_unreachable` |
| Alerts fire once | `alerts_monitor/main.py` | Test: `test_alert_fires_once_then_rearms` |

## Cloud, scaling and operations

| Requirement | Where | Proof |
|---|---|---|
| Runs on IBM Cloud | `infra/terraform/` | `scripts/check_terraform.py` and CI `terraform validate`. Not verified here: a real `terraform apply` |
| Infrastructure as code | Terraform | same |
| Autoscaling 1 to 5 copies | `scale_min_instances`, `scale_max_instances`, `scale_concurrency_target` in `services.tf` | Compare `loadtests/scenarios.js` at `max_instances` 1 and 5. Not verified here |
| Load balanced over copies, visible in the demo | One address per app, `X-Instance-Id` header | Test: `test_health_and_instance_header`. Script: `scripts/smoke_test.sh` prints the instance |
| Daily scheduled ingestion | Code Engine job and cron subscription in `ingestor.tf` | Not verified here |
| Deploy, smoke test and teardown scripts | `scripts/deploy.sh`, `smoke_test.sh`, `teardown.sh` | Smoke test run against the local stack. Deploy and teardown not verified here |
| Continuous integration and delivery | `.github/workflows/` | Workflow files parse; first run happens on GitHub |
| Monitoring | `/metrics`, `monitoring/` | Test: `libs/python/tests/test_metrics.py`. Prometheus and Grafana not run here |
