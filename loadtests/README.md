# Load tests

Two k6 scripts answer the two questions the demo has to answer.

## 1. Does autoscaling help?

```
k6 run -e UI_URL=<ui address> loadtests/scenarios.js        # with max_instances = 1
terraform -chdir=infra/terraform apply -var max_instances=5  # then wait a minute
k6 run -e UI_URL=<ui address> loadtests/scenarios.js        # with max_instances = 5
```

The ramp goes from 20 to 200 virtual users over four minutes. With one copy per service the p95
response time climbs and some requests fail. With up to five copies Code Engine starts more when
requests per copy pass `target_concurrency` (10), so the p95 stays flat. Watch the "Running copies"
and "Requests per second by instance" panels in Grafana while the test runs: the instance names are
the `X-Instance-Id` values, so you can see the load spread over the copies.

Record for the report: p95 and error rate for both runs, and the highest number of copies seen.

## 2. Does search survive a registry failure?

```
k6 run -e UI_URL=<ui address> loadtests/failover.js
```

Stop the primary registry while it runs (the commands are at the top of the script). The test
fails if more than 1% of searches fail or any takes more than 10 seconds. The metric
`searches_answered_by_backup` shows how many were served by the backup.

## No k6 installed?

`python scripts/loadtest_local.py <ui address>` runs a smaller version of the first test with plain Python
and prints the percentiles. It is good for a quick check on a laptop, not for the comparison above.
