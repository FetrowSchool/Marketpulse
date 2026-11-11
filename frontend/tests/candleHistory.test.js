import { describe, expect, it, vi } from 'vitest'
import { createCandleHistory } from '../src/services/candleHistory.js'
import { createCandleBook, reliableVolume } from '../src/services/candleBook.js'
import { candle, nextCandle, deferred, historyResponse } from './chartFixture.js'

describe('revision-aware candle state', () => {
  it('preserves completion and historical revisions without replacing later candles', () => {
    const book = createCandleBook('AAPL', '1m')
    book.merge([candle(), nextCandle()])
    book.merge([candle({ id: 7, revision: 3, high: 105, candle_complete: true })])
    book.merge([candle({ id: 3, revision: 2 }), nextCandle()])
    expect(book.rows()).toHaveLength(2)
    expect(book.rows()[0]).toMatchObject({ revision: 3, high: 105, candle_complete: true })
    expect(book.rows()[1].id).toBe(5)
  })
  it('rejects wrong contexts, incomplete OHLC, and unverified volume', () => {
    const book = createCandleBook('AAPL', '1m')
    book.merge([candle({ symbol: 'MSFT' }), candle({ candle_interval: '5m' }), candle({ high: null })])
    expect(book.rows()).toEqual([])
    expect(book.invalid).toBe(true)
    expect(reliableVolume(candle({ volume: 500, metadata: { provider_volume: { day_volume: 500 } } }))).toBe(false)
    expect(reliableVolume(candle({ volume: 0, metadata: { volume_reliable: true } }))).toBe(true)
  })
  it('does not compare revision counters across different producer identities', () => {
    const book = createCandleBook('AAPL', '1m')
    book.merge([candle({ revision: 99 }), candle({ id: 10, revision: 1, source_observation_id: 'other-producer-identity' })])
    expect(book.rows()[0].id).toBe(10)
  })
})
describe('history and live race handling', () => {
  it('merges live updates received before historical loading completes', async () => {
    const request = deferred(), output = vi.fn()
    const history = createCandleHistory({ fetcher: () => request.promise, onChange: output })
    const pending = history.load('AAPL', '1m')
    history.merge(candle({ id: 8, revision: 4, high: 110, candle_complete: true }))
    request.resolve(historyResponse('AAPL', '1m', [candle(), nextCandle()]))
    await pending
    const rows = output.mock.calls.at(-1)[0]
    expect(rows[0]).toMatchObject({ revision: 4, high: 110, candle_complete: true })
    expect(rows).toHaveLength(2)
    history.dispose()
  })
  it('ignores superseded responses even when a transport ignores abort', async () => {
    const first = deferred(), second = deferred(), output = vi.fn()
    const fetcher = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const history = createCandleHistory({ fetcher, onChange: output })
    const old = history.load('AAPL', '1m')
    const current = history.load('MSFT', '5m')
    second.resolve(historyResponse('MSFT', '5m', [candle({ symbol: 'MSFT', candle_interval: '5m' })]))
    await current
    first.resolve(historyResponse('AAPL', '1m', [candle()]))
    await old
    expect(output.mock.calls.at(-1)[0][0].symbol).toBe('MSFT')
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true)
    history.dispose()
  })
  it('keeps received candles when saved history is unavailable', async () => {
    const request = deferred(), output = vi.fn(), states = vi.fn()
    const history = createCandleHistory({ fetcher: () => request.promise, onChange: output, onState: states })
    const pending = history.load('AAPL', '1m')
    history.merge(candle())
    request.reject(new Error('mocked network failure'))
    await pending
    expect(output.mock.calls.at(-1)[0]).toHaveLength(1)
    expect(states.mock.calls.at(-1)[0]).toMatchObject({ loading: false, error: expect.stringContaining('preserved') })
    history.dispose()
  })
})
