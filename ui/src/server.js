const { createApp } = require('./app');
const { RegistryClient } = require('./registryClient');
const { listenForAlerts } = require('./alerts');

const urls = (process.env.REGISTRY_URLS || 'http://localhost:8000').split(',').map((s) => s.trim()).filter(Boolean);
const registry = new RegistryClient(urls);
const app = createApp({ registry });

if (process.env.AMQP_URL) {
  listenForAlerts(process.env.AMQP_URL, (alert) => app.locals.broadcast('alert', alert));
}

const port = Number(process.env.PORT || 8080);
app.listen(port, () => console.log(`UI listening on ${port}, registries: ${urls.join(', ')}`));
