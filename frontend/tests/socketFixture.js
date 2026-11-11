export class FakeWebSocket {
  static sockets = []
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; FakeWebSocket.sockets.push(this) }
  open() { this.readyState = 1; this.onopen?.({}) }
  send(value) { this.sent.push(JSON.parse(value)) }
  emit(message) { this.onmessage?.({ data: typeof message === 'string' ? message : JSON.stringify(message) }) }
  close() { this.readyState = 3 }
  disconnect() { this.readyState = 3; this.onclose?.({ code: 1006 }) }
}
export const source = '2026-01-06T15:00:30.000000Z'
export function frame(type, socket, symbol = 'AAPL', extra = {}) {
  return { schema_version: 1, type, symbol, source: 'yahoo_finance',
    subscription_id: socket.sent.at(-1)?.request_id || 1,
    source_timestamp: source, received_timestamp: '2026-01-06T15:00:31.000000Z',
    feed_status: { state: 'delayed', transport_connected: true, fresh_seconds: 15, stale_seconds: 120,
      latest_source_timestamp: source, last_received_timestamp: '2026-01-06T15:00:31.000000Z' },
    data: {}, ...extra }
}
