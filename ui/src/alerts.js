// Optional: listens for alert.triggered events on RabbitMQ and forwards them to browsers.
// If RabbitMQ or the amqplib package is missing the UI still works, it just has no live alerts.
function listenForAlerts(url, onAlert, log = console) {
  let amqp;
  try {
    amqp = require('amqplib');
  } catch (err) {
    log.warn('amqplib not installed, live alerts disabled');
    return { stop() {} };
  }
  let stopped = false;
  let connection;
  async function connect() {
    if (stopped) return;
    try {
      connection = await amqp.connect(url);
      const ch = await connection.createChannel();
      await ch.assertExchange('platform.events', 'topic', { durable: true });
      const q = await ch.assertQueue('ui.alerts', { durable: true });
      await ch.bindQueue(q.queue, 'platform.events', 'alert.triggered');
      await ch.consume(q.queue, (msg) => {
        if (!msg) return;
        try {
          onAlert(JSON.parse(msg.content.toString()));
        } catch (err) {
          log.warn('bad alert message dropped');
        }
        ch.ack(msg);
      });
      connection.on('close', () => setTimeout(connect, 3000));
      connection.on('error', () => {});
    } catch (err) {
      log.warn(`RabbitMQ not reachable (${err.message}), retrying`);
      setTimeout(connect, 3000);
    }
  }
  connect();
  return { stop() { stopped = true; if (connection) connection.close().catch(() => {}); } };
}

module.exports = { listenForAlerts };
