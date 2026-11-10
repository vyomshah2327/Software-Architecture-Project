# Stock Analytics Platform

Group 9, cs4471A/cs9549A Software Design and Architecture, Western University.

A micro-service platform built around a service registry. Eight stock analytics services register themselves in the registry, a web UI lets users search for them and open them, and a backup registry takes over automatically if the primary fails. Services announce events through RabbitMQ, scale with IBM Cloud Code Engine, and read daily prices from PostgreSQL that a scheduled ingestor loads from Alpha Vantage.

Team: Vyom Shah (group leader), Bipon Roy, Timur Enikeev, Daniel Bernaziuk.

## What is in the box

| Part | What it does |
|---|---|
| Registry (primary and backup) | Services register with a shared key and renew a 30 second lease every 10 seconds. Search is open and only lists services that pass a health check. Both copies share one Redis, so either can answer. |
| Consumer UI | Search box, tool cards, live list updates, alert pop-ups, and an amber banner while the backup registry is answering. Retries on the backup after 2 seconds. |
| S1 Price History | Daily prices for a company over a date range |
| S2 Performance | Total and annualised return, side by side comparison |
| S3 Volatility and Risk | Volatility, drawdown, value at risk, beta, Sharpe ratio |
| S4 Technical Indicators | SMA, EMA, RSI, MACD |
| S5 Fund Builder | Back-test a basket of companies, suggestions by sector |
| S6 Portfolio | Holdings, watchlist, profit and loss |
| S7 Correlation | Correlation matrix of daily returns |
| S8 Alerts and Monitor | Price alerts that fire once when a rule becomes true, and a watchlist monitor |
| Market Data Ingestor | Daily job. The only caller of Alpha Vantage. Tracks the API quota, archives raw responses, upserts prices, then announces `market.data.updated`. |

Every response carries an `X-Instance-Id` header so a demo can show which copy answered. Every service has a `/health` page and a `/metrics` page.

## Layout

| Path | Contents |
|---|---|
| `registry/` | Service registry (primary and backup run from one image) |
| `ui/` | Service consumer: web UI and Node backend |
| `ingestor/` | Market Data Ingestor job |
| `services/` | The eight stock services, one Python package each, one shared Dockerfile |
| `libs/python/` | Shared library: events, registry client, service factory, analytics, database helpers |
| `db/` | Schema, least-privilege roles and sample data |
| `infra/terraform/` | Terraform for IBM Cloud Code Engine and managed data services |
| `scripts/` | Build, deploy, smoke test, failover demo, load test and local run scripts |
| `loadtests/` | k6 scripts for scaling and failover |
| `monitoring/` | Prometheus and Grafana configuration |
| `docs/` | Architecture, deployment, demo runbook, requirement checklist, OpenAPI files |
| `.github/workflows/` | CI, image publishing and deploy |

## Run it on your machine

With Docker:

```
cp .env.example .env
docker compose up --build            # add --profile monitoring for Prometheus and Grafana
```

UI http://localhost:8080, registry http://localhost:8000 (backup 8001), RabbitMQ http://localhost:15672.
Load a fresh day of prices with `docker compose run --rm ingestor`.

Without Docker (PostgreSQL and Redis must be running):

```
pip install -e libs/python -e registry -e ingestor -e services
export DATABASE_URL=postgresql://user:pass@localhost:5432/stock REDIS_URL=redis://localhost:6379/0
python db/init_db.py --seed --roles
(cd ui && npm ci)
scripts/run_local.sh start           # eight services, two registries and the UI
python scripts/e2e_local.py          # checks the whole thing
scripts/demo_failover.sh             # stops the primary registry and shows search keep working
scripts/run_local.sh stop
```

Without RabbitMQ the services skip events and everything else still works.

## Tests

```
python -m pytest libs/python registry ingestor services     # needs DATABASE_URL
(cd ui && npm test)
python scripts/check_terraform.py
```

## Deploy to IBM Cloud

See `docs/deployment.md`. In short: CI publishes the images, then `scripts/deploy.sh` runs Terraform, creates the schema, loads the first prices and runs the smoke test. `scripts/teardown.sh` removes everything.

## More

* `docs/architecture.md` explains the design and why it is built this way.
* `docs/demo-runbook.md` is the step by step script for the final demo.
* `docs/requirements-checklist.md` maps each requirement to the code and the test that proves it.
