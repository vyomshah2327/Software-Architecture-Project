const express = require('express');
const path = require('path');

// Builds the consumer web app. `registry` is a RegistryClient; `onAlert` lets the server push alerts to browsers.
function createApp({ registry, pollMs = 5000 }) {
  const app = express();
  const streams = new Set();
  let lastNames = null;

  app.disable('x-powered-by');
  app.use(express.static(path.join(__dirname, '..', 'public')));

  app.get('/health', (req, res) => res.json({ status: 'ok', service: 'ui' }));

  app.get('/api/search', async (req, res) => {
    const q = String(req.query.q || '').slice(0, 100);
    try {
      res.json({ query: q, ...(await registry.search(q)) });
    } catch (err) {
      res.status(503).json({ error: 'The service registry is not reachable right now. Please try again shortly.' });
    }
  });

  function send(res, event, data) {
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  }

  function broadcast(event, data) {
    for (const res of streams) send(res, event, data);
  }

  // Poll the registry and tell browsers when the list of services changes or the registry role changes.
  async function poll() {
    try {
      const result = await registry.search('');
      const names = result.services.map((s) => s.name).sort().join(',');
      broadcast('registry', { role: result.role, degraded: result.degraded });
      if (lastNames !== null && names !== lastNames) broadcast('services', { services: result.services });
      lastNames = names;
    } catch (err) {
      broadcast('registry', { role: 'down', degraded: true });
    }
  }

  app.get('/api/events', (req, res) => {
    res.set({ 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
    res.flushHeaders();
    res.write(': connected\n\n');
    streams.add(res);
    req.on('close', () => streams.delete(res));
    poll();
  });

  const timer = setInterval(poll, pollMs);
  timer.unref();

  app.locals.broadcast = broadcast;
  app.locals.poll = poll;
  app.locals.stop = () => {
    clearInterval(timer);
    for (const res of streams) res.end();
  };
  return app;
}

module.exports = { createApp };
