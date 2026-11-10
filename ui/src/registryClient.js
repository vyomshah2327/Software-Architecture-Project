// Talks to the registry primary and backup. A request that gets no answer from the primary within
// the timeout is retried on the backup, so a search still works while the primary is down.
class RegistryClient {
  constructor(urls, { timeoutMs = 2000, stickyMs = 10000, fetchImpl = fetch } = {}) {
    this.urls = urls.map((u) => u.replace(/\/+$/, ''));
    this.timeoutMs = timeoutMs;
    this.stickyMs = stickyMs;
    this.fetch = fetchImpl;
    this.skipPrimaryUntil = 0;
  }

  async get(path) {
    const order = this.urls.map((_, i) => i);
    // After a primary failure go straight to the backup for a short while instead of waiting 2 s every time.
    if (Date.now() < this.skipPrimaryUntil && order.length > 1) order.push(order.shift());
    let lastError;
    for (const i of order) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      try {
        const res = await this.fetch(this.urls[i] + path, { signal: controller.signal });
        if (!res.ok) throw new Error(`registry answered ${res.status}`);
        if (i === 0) this.skipPrimaryUntil = 0;
        else if (order[0] === 0) this.skipPrimaryUntil = Date.now() + this.stickyMs;
        return { data: await res.json(), registry: this.urls[i], role: i === 0 ? 'primary' : 'backup' };
      } catch (err) {
        lastError = err;
      } finally {
        clearTimeout(timer);
      }
    }
    const error = new Error(`no registry answered: ${lastError && lastError.message}`);
    error.code = 'REGISTRY_DOWN';
    throw error;
  }

  async search(q = '') {
    const { data, role, registry } = await this.get(`/services?q=${encodeURIComponent(q)}`);
    return { services: data.services || [], role, registry, degraded: role !== 'primary' };
  }
}

module.exports = { RegistryClient };
