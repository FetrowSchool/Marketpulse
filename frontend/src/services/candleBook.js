// One immutable producer identity can have many revisions; the chart has one bar per UTC opening.
export const INTERVALS = ['1m', '5m', '15m']
export function candleIdentity(row) {
  return JSON.stringify([row.symbol, row.data_source, row.observation_type, row.data_mode,
    row.source_observation_id, row.candle_interval, row.candle_open_timestamp])
}
export function validCandle(row, symbol, interval) {
  if (!row || row.symbol !== symbol || row.candle_interval !== interval ||
      !['constructed_candle', 'provider_candle'].includes(row.observation_type) ||
      !['live', 'delayed', 'recorded', 'simulated'].includes(row.data_mode) ||
      !row.data_source || !row.source_observation_id || !Number.isInteger(row.id) || row.id < 1 ||
      !Number.isInteger(row.revision) || row.revision < 1 || typeof row.candle_complete !== 'boolean') return false
  const time = Date.parse(row.candle_open_timestamp) / 1000
  return typeof row.candle_open_timestamp === 'string' && /Z$/.test(row.candle_open_timestamp) &&
    Number.isInteger(time) && time >= 0 && ['open', 'high', 'low', 'close'].every(key => Number.isFinite(row[key])) &&
    row.high >= Math.max(row.open, row.close, row.low) && row.low <= Math.min(row.open, row.close, row.high)
}
export function reliableVolume(row) {
  return Number.isFinite(row.volume) && row.volume >= 0 &&
    (row.metadata?.volume_reliable === true || row.metadata?.volume_semantics === 'interval_trade_volume')
}
export function createCandleBook(symbol, interval, limit = 1000) {
  const identities = new Map()
  let invalid = false
  function rows() {
    const openings = new Map()
    for (const row of identities.values()) {
      const previous = openings.get(row.candle_open_timestamp)
      // Different producer/mode identities are never aggregated together. Latest committed row wins a time slot.
      if (!previous || row.id > previous.id) openings.set(row.candle_open_timestamp, row)
    }
    return [...openings.values()].sort((a, b) => a.candle_open_timestamp.localeCompare(b.candle_open_timestamp)).slice(-limit)
  }
  return {
    merge(incoming) {
      let changed = false
      for (const row of incoming) {
        if (!row || row.symbol !== symbol || row.candle_interval !== interval) continue
        if (!validCandle(row, symbol, interval)) { invalid = true; continue }
        const identity = candleIdentity(row)
        const previous = identities.get(identity)
        if (!previous || row.revision > previous.revision) {
          identities.set(identity, row)
          changed = true
        }
      }
      const retained = rows()
      if (retained.length === limit) {
        const earliest = retained[0].candle_open_timestamp
        for (const [key, row] of identities) if (row.candle_open_timestamp < earliest) identities.delete(key)
      }
      return changed
    },
    rows,
    get invalid() { return invalid },
  }
}
