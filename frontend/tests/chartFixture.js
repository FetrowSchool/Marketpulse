// Synthetic, explicitly simulated chart fixtures. Never served by the application.
export function candle(overrides = {}) {
  return { id: 2, symbol: 'AAPL', data_source: 'yahoo_finance', observation_type: 'constructed_candle',
    source_observation_id: 'quote-candle-v1:simulated:1m:2026-01-06T15:00:00.000000Z',
    data_mode: 'simulated', candle_interval: '1m', candle_open_timestamp: '2026-01-06T15:00:00.000000Z',
    source_timestamp: '2026-01-06T15:00:30.000000Z', received_timestamp: '2026-01-06T15:00:31.000000Z',
    revision: 1, candle_complete: false, open: 100, high: 103, low: 99, close: 102, volume: null,
    metadata: { construction: 'source_time_quotes_v1' }, ...overrides }
}
export function nextCandle(overrides = {}) {
  return candle({ id: 5, source_observation_id: 'next-synthetic-candle',
    candle_open_timestamp: '2026-01-06T15:01:00.000000Z', ...overrides })
}
export function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
export function historyResponse(symbol, interval, candles) { return { ok: true, json: async () => ({ symbol, interval, candles }) } }
