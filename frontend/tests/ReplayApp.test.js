// Synthetic mocked transport fixtures only; not live or genuine recorded-provider evidence.
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { FakeWebSocket, frame } from './socketFixture.js'
import { candle } from './chartFixture.js'
vi.mock('../src/services/chartRenderer.js', () => ({ createChartRenderer: () => ({ apply() {}, fit() {}, remove() {} }) }))
import App from '../src/App.vue'
let wrapper
beforeEach(() => {
  FakeWebSocket.sockets = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.stubGlobal('fetch', vi.fn(async url => ({ ok: true, json: async () => {
    const query = new URL(url, 'http://localhost').searchParams
    if (url.includes('/replay/catalog')) return { event_count: 4, first_receipt: '2026-01-06T15:00:31.000000Z', last_receipt: '2026-01-06T15:02:00.000000Z' }
    if (url.includes('/candles')) return { symbol: query.get('symbol'), interval: query.get('interval'), candles: [] }
    if (url.includes('/symbols')) return { active_symbol: 'AAPL', active_interval: '1m' }
    return { status: 'ok', database: 'connected', version: '0.1.0' }
  } })))
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals() })
function emit(socket, type, data, generation = 1) {
  socket.emit({ schema_version: 1, display_mode: 'replay', generation, type, data })
}
it('isolates replay, controls playback, clears old generations and restores live state', async () => {
  wrapper = mount(App)
  await flushPromises()
  const originalLive = FakeWebSocket.sockets.at(-1)
  originalLive.open()
  await wrapper.get('select[aria-label="Data mode"]').setValue('replay')
  await flushPromises()
  const replay = FakeWebSocket.sockets.at(-1)
  expect(originalLive.readyState).toBe(3)
  expect(replay.url).toContain('/ws/replay')
  replay.open()
  expect(replay.sent.at(-1).type).toBe('load')
  emit(replay, 'replay_loaded', { state: 'ready', generation: 1, total: 4, position: 0, baseline: [], snapshot_max_id: 10 })
  await flushPromises()
  expect(wrapper.text()).toContain('REPLAY · RECORDED')
  expect(wrapper.text()).toContain('Yahoo connectivity not required')
  await wrapper.get('button[aria-label="Play replay"]').trigger('click')
  expect(replay.sent.at(-1).type).toBe('play')
  emit(replay, 'replay_status', { state: 'playing', generation: 1, total: 4, position: 1, playhead_receipt_timestamp: '2026-01-06T15:00:31.000000Z' })
  emit(replay, 'replay_event', { record: candle() })
  originalLive.emit(frame('market_observation', originalLive, 'AAPL', { data: { id: 999, symbol: 'AAPL', price: 999 } }))
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('102')
  expect(wrapper.get('[data-testid="source-time"]').text()).toBe('2026-01-06T15:00:30.000000Z')
  expect(wrapper.get('[data-testid="data-age"]').text()).toBe('1.0s')
  emit(replay, 'replay_event', { record: candle({ id: 3, revision: 2, volume: 50, metadata: { volume_reliable: true } }) })
  await flushPromises()
  expect(wrapper.text()).toContain('Only reliable interval volume')
  await wrapper.get('button[aria-label="Pause replay"]').trigger('click')
  expect(replay.sent.at(-1).type).toBe('pause')
  emit(replay, 'replay_status', { state: 'paused', generation: 1, total: 4, position: 1 })
  await flushPromises()
  await wrapper.get('select[aria-label="Replay speed"]').setValue('50')
  expect(replay.sent.at(-1)).toMatchObject({ type: 'speed', speed: 50 })
  await wrapper.get('button[aria-label="Resume replay"]').trigger('click')
  expect(replay.sent.at(-1).type).toBe('resume')
  await wrapper.get('button[aria-label="Restart replay"]').trigger('click')
  emit(replay, 'replay_loaded', { state: 'playing', generation: 2, position: 0, total: 4, baseline: [] }, 2)
  emit(replay, 'replay_event', { record: candle({ close: 999, high: 999 }) }, 1)
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('—')
  emit(replay, 'replay_event', { record: candle() }, 2)
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('102')
  await wrapper.get('button[aria-label="Stop replay"]').trigger('click')
  expect(replay.sent.at(-1).type).toBe('stop')
  await wrapper.get('select[aria-label="Data mode"]').setValue('live')
  await flushPromises()
  const newLive = FakeWebSocket.sockets.at(-1)
  expect(replay.readyState).toBe(3)
  newLive.open()
  newLive.emit(frame('market_observation', newLive, 'AAPL', { data: { id: 50, symbol: 'AAPL', price: 200,
    source_timestamp: '2026-01-06T15:03:00.000000Z', received_timestamp: '2026-01-06T15:03:01.000000Z',
    observation_type: 'raw_provider', data_mode: 'delayed' } }))
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('200')
  expect(wrapper.text()).not.toContain('REPLAY · RECORDED')
})

it('loads UTC ranges and commit ordering, isolates symbol changes, and permits retry after transport loss', async () => {
  wrapper = mount(App)
  await flushPromises()
  await wrapper.get('select[aria-label="Data mode"]').setValue('replay')
  await flushPromises()
  const first = FakeWebSocket.sockets.at(-1)
  first.open()
  emit(first, 'replay_loaded', { state: 'ready', generation: 1, total: 4, position: 0, baseline: [] })
  await flushPromises()
  await wrapper.get('input[aria-label="Replay start UTC"]').setValue('2026-01-06T15:01:00')
  await wrapper.get('input[aria-label="Replay end UTC"]').setValue('2026-01-06T15:02:00')
  await wrapper.get('select[aria-label="Replay ordering"]').setValue('arrival')
  await wrapper.get('button[aria-label="Load replay selection"]').trigger('click')
  expect(first.sent.at(-1)).toMatchObject({type: 'load', selection: {
    symbol: 'AAPL', start: '2026-01-06T15:01Z', end: '2026-01-06T15:02Z', order: 'arrival', interval: '1m',
  }})
  await wrapper.get('select[aria-label="Stock symbol"]').setValue('MSFT')
  await flushPromises()
  expect(first.readyState).toBe(3)
  const second = FakeWebSocket.sockets.at(-1)
  second.open()
  expect(second.sent.at(-1).selection.symbol).toBe('MSFT')
  first.emit({ schema_version: 1, display_mode: 'replay', generation: 5, type: 'replay_event', data: {record: candle()} })
  emit(second, 'replay_loaded', { state: 'ready', generation: 1, total: 4, position: 0, baseline: [] })
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('—')
  second.onclose()
  await flushPromises()
  expect(wrapper.text()).toContain('Replay connection lost')
  await wrapper.get('button[aria-label="Load replay selection"]').trigger('click')
  const retry = FakeWebSocket.sockets.at(-1)
  expect(retry).not.toBe(second)
  retry.open()
  expect(retry.sent.at(-1).type).toBe('load')
})
