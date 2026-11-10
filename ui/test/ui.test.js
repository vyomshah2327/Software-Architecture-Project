const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { RegistryClient } = require('../src/registryClient');
const { createApp } = require('../src/app');

// A fake registry that can be switched to slow, broken or healthy.
function fakeRegistry(services) {
  const state = { mode: 'ok', services, hits: 0 };
  const server = http.createServer((req, res) => {
    state.hits++;
    if (state.mode === 'slow') return; // never answers
    if (state.mode === 'error') { res.statusCode = 500; return res.end('{}'); }
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ services: state.services }));
  });
  return new Promise((resolve) => server.listen(0, () => resolve({
    state, url: `http://127.0.0.1:${server.address().port}`, close: () => { server.closeAllConnections(); server.close(); },
  })));
}

const svc = (name) => ({ name, url: `https://${name}.example.com`, description: name, tags: [] });

test('search uses the primary when it is healthy', async () => {
  const p = await fakeRegistry([svc('a')]);
  const b = await fakeRegistry([svc('b')]);
  const r = await new RegistryClient([p.url, b.url]).search('');
  assert.strictEqual(r.role, 'primary');
  assert.deepStrictEqual(r.services.map((s) => s.name), ['a']);
  assert.strictEqual(b.state.hits, 0);
  p.close(); b.close();
});

test('a silent primary is abandoned after the timeout and the backup answers', async () => {
  const p = await fakeRegistry([svc('a')]);
  const b = await fakeRegistry([svc('a')]);
  p.state.mode = 'slow';
  const started = Date.now();
  const r = await new RegistryClient([p.url, b.url], { timeoutMs: 300 }).search('');
  const elapsed = Date.now() - started;
  assert.strictEqual(r.role, 'backup');
  assert.strictEqual(r.degraded, true);
  assert.ok(elapsed >= 250 && elapsed < 1500, `took ${elapsed} ms`);
  p.close(); b.close();
});

test('an erroring primary also falls over, and the next search skips the primary for a while', async () => {
  const p = await fakeRegistry([svc('a')]);
  const b = await fakeRegistry([svc('a')]);
  p.state.mode = 'error';
  const client = new RegistryClient([p.url, b.url], { timeoutMs: 300, stickyMs: 5000 });
  await client.search('');
  const hitsAfterFirst = p.state.hits;
  const second = await client.search('');
  assert.strictEqual(second.role, 'backup');
  assert.strictEqual(p.state.hits, hitsAfterFirst, 'primary was not tried again during the sticky window');
  p.close(); b.close();
});

test('primary is used again once the sticky window passes', async () => {
  const p = await fakeRegistry([svc('a')]);
  const b = await fakeRegistry([svc('a')]);
  p.state.mode = 'error';
  const client = new RegistryClient([p.url, b.url], { timeoutMs: 300, stickyMs: 50 });
  await client.search('');
  p.state.mode = 'ok';
  await new Promise((r) => setTimeout(r, 80));
  assert.strictEqual((await client.search('')).role, 'primary');
  p.close(); b.close();
});

test('both registries down gives a clear error', async () => {
  const p = await fakeRegistry([]);
  const b = await fakeRegistry([]);
  p.state.mode = 'error'; b.state.mode = 'error';
  await assert.rejects(new RegistryClient([p.url, b.url], { timeoutMs: 200 }).search(''), (e) => e.code === 'REGISTRY_DOWN');
  p.close(); b.close();
});

async function withApp(registry, fn, pollMs = 60000) {
  const app = createApp({ registry, pollMs });
  const server = await new Promise((resolve) => { const s = app.listen(0, () => resolve(s)); });
  try { await fn(`http://127.0.0.1:${server.address().port}`, app); }
  finally { app.locals.stop(); server.closeAllConnections(); server.close(); }
}

test('the search endpoint returns services and marks backup use', async () => {
  const p = await fakeRegistry([svc('a')]);
  const b = await fakeRegistry([svc('a'), svc('b')]);
  p.state.mode = 'error';
  await withApp(new RegistryClient([p.url, b.url], { timeoutMs: 200 }), async (base) => {
    const j = await (await fetch(`${base}/api/search?q=a`)).json();
    assert.strictEqual(j.degraded, true);
    assert.strictEqual(j.services.length, 2);
  });
  p.close(); b.close();
});

test('the search endpoint answers 503 with a friendly message when no registry is up', async () => {
  const p = await fakeRegistry([]); p.state.mode = 'error';
  await withApp(new RegistryClient([p.url], { timeoutMs: 200 }), async (base) => {
    const res = await fetch(`${base}/api/search`);
    assert.strictEqual(res.status, 503);
    assert.match((await res.json()).error, /not reachable/);
  });
  p.close();
});

test('the event stream announces registry role, list changes and alerts', async () => {
  const p = await fakeRegistry([svc('a')]);
  await withApp(new RegistryClient([p.url], { timeoutMs: 200 }), async (base, app) => {
    const res = await fetch(`${base}/api/events`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let text = '';
    const read = async (needle) => {
      const until = Date.now() + 3000;
      while (!text.includes(needle) && Date.now() < until) {
        const { value } = await Promise.race([reader.read(), new Promise((r) => setTimeout(() => r({}), 200))]);
        if (value) text += decoder.decode(value);
      }
      assert.ok(text.includes(needle), `expected ${needle} in ${text}`);
    };
    await read('event: registry');
    p.state.services = [svc('a'), svc('c')];
    await app.locals.poll();
    await read('event: services');
    app.locals.broadcast('alert', { symbol: 'AAPL' });
    await read('event: alert');
    await reader.cancel();
  });
  p.close();
});

test('health endpoint and static page are served', async () => {
  const p = await fakeRegistry([]);
  await withApp(new RegistryClient([p.url]), async (base) => {
    assert.strictEqual((await (await fetch(`${base}/health`)).json()).status, 'ok');
    assert.match(await (await fetch(base)).text(), /Stock Analytics Platform/);
  });
  p.close();
});
