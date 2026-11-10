// k6: steady searches while the primary registry is stopped. Searches must keep succeeding.
//   k6 run -e UI_URL=https://ui.xxx... loadtests/failover.js
// While it runs (90 seconds), stop the primary registry:
//   Code Engine:  ibmcloud ce app update --name registry-primary --min-scale 0 --max-scale 0   (undo with 1 and 2)
//   Compose:      docker compose stop registry-primary
//   Local:        scripts/demo_failover.sh
// Target: no failed searches, and every search under 10 s (the plan is about 2 s).
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const UI = (__ENV.UI_URL || 'http://localhost:8080').replace(/\/$/, '');
const onBackup = new Counter('searches_answered_by_backup');

export const options = {
  scenarios: {
    steady: { executor: 'constant-arrival-rate', rate: 10, timeUnit: '1s', duration: '90s', preAllocatedVUs: 30 },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['max<10000'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const res = http.get(`${UI}/api/search?q=risk`, { timeout: '10s' });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'found the risk tool': (r) => r.status === 200 && r.json('services').length >= 1,
  });
  if (res.status === 200 && res.json('role') === 'backup') onBackup.add(1);
}
