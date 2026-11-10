# Demo runbook

About 12 minutes of live demo. Rehearse it twice, once locally and once on the cloud deployment.

## Before the demo

* [ ] Deployed and the smoke test passed: `scripts/smoke_test.sh <ui> <primary> <backup>`
* [ ] Fresh prices loaded: run the `market-data-ingestor` job once that morning
* [ ] Grafana open on the platform dashboard (run Prometheus and Grafana from a laptop with `python scripts/prometheus_targets.py <ui>` feeding `file_sd`), or the compose stack if the cloud is not available
* [ ] k6 installed, `UI_URL` exported
* [ ] A terminal with `ibmcloud ce project select` already done
* [ ] A second browser tab on the UI

## Script

**1. The platform in 60 seconds (UI).** Open the UI. Say what it is: eight small services, one registry, nothing hard-wired. Type `risk`, then `price`, then clear the box. Point out the cards come from the registry, not from a fixed list.

**2. Use a tool.** Open Price History, pick AAPL, show the chart. Open Performance and compare `AAPL,MSFT,SPY`. Open Correlation. Keep this short, the point is the architecture.

**3. One address, many copies.** Open `/health` of any service twice and show `instance`. Explain that the registry holds one address per service and Code Engine spreads requests over the copies.

**4. Registry failover.** In the UI keep typing searches. Stop the primary registry:
`ibmcloud ce app delete --name registry-primary --force`
The amber banner appears within a couple of seconds, search keeps working. Bring it back with `terraform -chdir=infra/terraform apply -auto-approve` (about a minute, it recreates the missing app); the banner goes away.
Fallback: `docker compose stop registry-primary`, or `scripts/demo_failover.sh` locally.

**5. Events, end to end.** In Portfolio add AAPL to the watchlist. In Alerts create a rule `AAPL above 1`, which is already true. Run the ingestor:
`ibmcloud ce jobrun submit --job market-data-ingestor --name demo-$(date +%s) --wait`
A pop-up appears in the UI and the rule shows `triggered`. Explain the chain: ingestor commits, announces `market.data.updated`, Alerts checks its rules, announces `alert.triggered`, the UI listens.

**6. Autoscaling.** Start `k6 run -e UI_URL=<ui> loadtests/scenarios.js` and switch to Grafana. Show requests per second rising, the "Running copies" panel going from 1 toward 5, and the instance names sharing the load. If you have the numbers from the earlier 1-copy run, put them next to it.

**7. How it gets there.** Show the repository: Terraform in `infra/terraform`, the pipeline in `.github/workflows`, and the green CI run on the last commit.

## If something goes wrong

| Problem | Do this |
|---|---|
| A tool is missing from search | It is unhealthy or not registered yet. Wait 30 s, or open its `/health`. The registry only lists healthy services. |
| No alert pop-up | Check the ingestor job log. If RabbitMQ is the problem, click "Check now" on the Alerts page to show the same logic without the event. |
| Cloud is down or slow | Switch to `docker compose up` on the laptop. Everything in the script works there. |
| Scaling does not move | Make sure the test is hitting the tool addresses, and lower `target_concurrency` with `terraform apply -var target_concurrency=3`. |

## After the demo

`scripts/teardown.sh`
