// k6 load test: a realistic mix of searches and tool calls.
//   k6 run -e UI_URL=https://ui.xxx.codeengine.appdomain.cloud loadtests/scenarios.js
// Run it twice, once with max_instances=1 and once with 5 (terraform apply -var max_instances=N),
// and compare the p95 response time and the error rate.
import http from 'k6/http';
import { check, sleep } from 'k6';

const UI = (__ENV.UI_URL || 'http://localhost:8080').replace(/\/$/, '');
const SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'JPM', 'XOM', 'JNJ', 'KO', 'SPY'];

export const options = {
  stages: [
    { duration: '30s', target: 20 },
    { duration: '1m', target: 100 },
    { duration: '2m', target: 200 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
};

// Find every tool's address once, through the same search a user would do.
export function setup() {
  const found = http.get(`${UI}/api/search`).json('services');
  const urls = {};
  found.forEach((s) => { urls[s.name] = s.url.replace(/\/$/, ''); });
  return urls;
}

const pick = () => SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)];

export default function (urls) {
  const roll = Math.random();
  let res;
  if (roll < 0.4) {
    res = http.get(`${UI}/api/search?q=${['risk', 'price', 'portfolio', 'correlation', ''][Math.floor(Math.random() * 5)]}`);
  } else if (roll < 0.6) {
    res = http.get(`${urls['price-history']}/api/prices/${pick()}?limit=60`);
  } else if (roll < 0.75) {
    res = http.get(`${urls['performance']}/api/performance/${pick()}?period=1y`);
  } else if (roll < 0.9) {
    res = http.get(`${urls['volatility-risk']}/api/risk/${pick()}?days=252`);
  } else {
    res = http.get(`${urls['correlation']}/api/correlation?symbols=${pick()},${pick() === 'AAPL' ? 'MSFT' : 'AAPL'},SPY&days=252`);
  }
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(Math.random() * 0.5);
}
