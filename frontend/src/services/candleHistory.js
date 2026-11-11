import { createCandleBook } from './candleBook.js'

// HTTP history and live messages merge into the SAME book. No stale response ever replaces live state.
export function createCandleHistory({ onChange = () => {}, onState = () => {}, fetcher = globalThis.fetch } = {}) {
  let symbol, interval, book, controller
  let generation = 0
  let disposed = false
  const notify = () => onChange(book.rows())
  async function load(nextSymbol, nextInterval) {
    if (disposed) return
    const same = nextSymbol === symbol && nextInterval === interval
    symbol = nextSymbol; interval = nextInterval
    if (!same || !book) { book = createCandleBook(symbol, interval); notify() }
    const version = ++generation
    controller?.abort()
    controller = new AbortController()
    const ownController = controller
    const timeout = setTimeout(() => ownController.abort(), 10000)
    onState({ loading: true, error: '', invalid: book.invalid })
    try {
      const query = new URLSearchParams({ symbol, interval, limit: '1000' })
      const response = await fetcher(`/api/market/candles?${query}`, { signal: controller.signal })
      if (!response.ok) throw new Error('Saved candles unavailable')
      const result = await response.json()
      if (disposed || generation !== version) return
      if (result.symbol !== symbol || result.interval !== interval || !Array.isArray(result.candles)) {
        throw new Error('Invalid candle history response')
      }
      book.merge(result.candles)
      notify()
      onState({ loading: false, error: '', invalid: book.invalid })
    } catch {
      if (!disposed && generation === version) {
        onState({ loading: false, error: 'Saved history unavailable. Received updates are preserved.', invalid: book.invalid })
      }
    } finally { clearTimeout(timeout) }
  }
  return {
    load,
    merge(row) {
      if (!disposed && book?.merge([row])) { notify() }
    },
    dispose() { disposed = true; generation += 1; controller?.abort() },
  }
}
