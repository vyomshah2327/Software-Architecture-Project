# Stock Analytics Platform

Group 9, cs4471A/cs9549A Software Design and Architecture, Western University.

A micro-service platform built around a service registry. Eight stock analytics services register themselves in the registry, a web UI lets users search for them and open them, and a backup registry takes over automatically if the primary fails. Services announce events through RabbitMQ, scale with IBM Cloud Code Engine, and read daily prices from PostgreSQL that a scheduled ingestor loads from Alpha Vantage.

## Layout

| Path | Contents |
|---|---|
| `registry/` | Service registry (primary and backup run from one image) |
| `ui/` | Service consumer: web UI and backend |
| `ingestor/` | Market Data Ingestor job |
| `services/s1` to `services/s8` | The eight stock services |
| `libs/python/` | Shared library: events, registry client, service app factory, database helpers |
| `db/` | Schema, roles and seed data |
| `infra/` | Terraform for IBM Cloud |
| `scripts/` | Build, deploy, demo and test scripts |
| `loadtests/` | k6 load tests |
| `monitoring/` | Prometheus and Grafana configuration |
| `docs/` | Architecture notes and demo runbook |

## Run locally

```
cp .env.example .env
docker compose up --build
```

Open http://localhost:8080 for the UI. See `docs/` for the demo runbook.
