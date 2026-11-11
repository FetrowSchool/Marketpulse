import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App.vue'
import { FakeWebSocket, frame, source } from './socketFixture.js'
import { candle } from './chartFixture.js'
vi.mock('../src/services/chartRenderer.js', () => ({ createChartRenderer: () => ({ apply() {}, fit() {}, remove() {} }) }))
let wrapper
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-01-06T15:00:32Z'))
  FakeWebSocket.sockets = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.stubGlobal('fetch', vi.fn(async url => ({ ok: true, json: async () => url.includes('/symbols')
    ? { symbols: ['AAPL', 'MSFT', 'NVDA', 'SPY'], active_symbol: 'AAPL' }
    : url.includes('/candles') ? { symbol: new URL(url, 'http://localhost').searchParams.get('symbol'), interval: new URL(url, 'http://localhost').searchParams.get('interval'), candles: [] }
    : { status: 'ok', database: 'connected', version: '0.1.0' } })))
})
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals(); vi.useRealTimers() })
async function mounted() {
  wrapper = mount(App)
  await flushPromises()
  const socket = FakeWebSocket.sockets.at(-1)
  socket.open()
  socket.emit(frame('connection_status', socket, 'AAPL', { data: { state: 'subscribed' } }))
  return socket
}
function quote(socket, symbol = 'AAPL', price = 100, id = 1, timestamp = source) {
  socket.emit(frame('market_observation', socket, symbol, { data: { id, symbol, price,
    source_timestamp: timestamp, received_timestamp: '2026-01-06T15:00:31.000000Z', data_mode: 'delayed',
    metadata: { original: {} } } }))
}
describe('MarketPulse connected dashboard', () => {
  it('renders health and keeps connected browser distinct from unavailable Yahoo feed', async () => {
    const socket = await mounted()
    socket.emit(frame('feed_status', socket, 'AAPL', { feed_status: { state: 'unavailable', transport_connected: false } }))
    await flushPromises()
    expect(wrapper.text()).toContain('MarketPulse')
    expect(wrapper.find('[data-testid=chart-canvas]').exists()).toBe(true)
    expect(wrapper.get('[role="status"]').text()).toContain('Database: Connected')
    expect(wrapper.get('[data-testid="socket-status"]').text()).toContain('connected')
    expect(wrapper.get('[data-testid="feed-status"]').text()).toContain('unavailable')
    expect(wrapper.text()).not.toContain('LIVE · FRESH')
    expect(wrapper.get('select[aria-label="Stock symbol"]').element.disabled).toBe(false)
    expect(wrapper.findAll('.replay-actions button').every(button => button.element.disabled)).toBe(true)
  })
  it('handles delayed observations, preserves timestamps and keeps values after disconnect', async () => {
    const socket = await mounted()
    quote(socket)
    socket.emit(frame('candle_completed', socket, 'AAPL', { data: {
      ...candle({ id: 3, revision: 2, candle_complete: true }),
    } }))
    await flushPromises()
    expect(wrapper.text()).toContain('1m · complete · r2')
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('100')
    expect(wrapper.get('[data-testid="source-time"]').text()).toBe(source)
    expect(wrapper.get('[data-testid="receipt-time"]').text()).toBe('2026-01-06T15:00:31.000000Z')
    expect(wrapper.get('[data-testid="feed-status"]').text()).toBe('delayed')
    expect(wrapper.text()).toContain('LAST KNOWN · NOT CURRENT')
    socket.emit(frame('feed_status', socket, 'AAPL', { feed_status: {
      state: 'delayed', last_received_timestamp: '2026-01-06T15:00:32.000000Z',
    } }))
    socket.disconnect()
    await flushPromises()
    expect(wrapper.get('[data-testid="receipt-time"]').text()).toBe('2026-01-06T15:00:32.000000Z')
    expect(wrapper.get('[data-testid="socket-status"]').text()).toBe('reconnecting')
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('100')
    expect(wrapper.get('[data-testid="feed-status"]').text()).toBe('disconnected')
  })
  it('switches symbols without cross-stock or late-price contamination', async () => {
    const socket = await mounted()
    quote(socket)
    await wrapper.get('select[aria-label="Stock symbol"]').setValue('MSFT')
    expect(socket.sent.at(-1).symbol).toBe('MSFT')
    quote(socket, 'AAPL', 999)
    await flushPromises()
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('—')
    quote(socket, 'MSFT', 200, 3)
    quote(socket, 'MSFT', 1, 4, '2026-01-06T14:00:00.000000Z')
    await flushPromises()
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('200')
    await wrapper.get('select[aria-label="Stock symbol"]').setValue('AAPL')
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('100')
  })
  it('reports unreachable backend health without invented prices', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network failure')))
    wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('Unavailable')
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('—')
  })
  it('reports degraded database health', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ status: 'degraded', database: 'unavailable', version: '0.1.0' }) }))
    wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('Degraded')
  })
  it('loads saved recorded candles, displays their close, and isolates a different interval', async () => {
    vi.stubGlobal('fetch', vi.fn(async url => {
      if (url.includes('/candles')) {
        const query = new URL(url, 'http://localhost').searchParams
        return { ok: true, json: async () => ({ symbol: query.get('symbol'), interval: query.get('interval'),
          candles: query.get('interval') === '1m' ? [candle({ data_mode: 'recorded', candle_complete: true })] : [] }) }
      }
      return { ok: true, json: async () => url.includes('/symbols')
        ? { active_symbol: 'AAPL', active_interval: '1m' } : { status: 'ok', database: 'connected', version: '0.1.0' } }
    }))
    await mounted()
    await flushPromises()
    expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('102')
    expect(wrapper.text()).toContain('RECORDED')
    expect(wrapper.text()).toContain('Last saved candle close')
    expect(wrapper.text()).toContain('1 saved / received candles')
    await wrapper.get('select[aria-label="Candle interval"]').setValue('5m')
    await flushPromises()
    expect(wrapper.text()).toContain('0 saved / received candles')
    expect(wrapper.text()).toContain('Saved 5m candles only')
  })

})

it('labels fresh unverified streaming separately and ages into delayed and stale without new observations', async () => {
  vi.useFakeTimers()
  const socket = await mounted()
  quote(socket)
  socket.emit(frame('feed_status', socket, 'AAPL', { feed_status: {
    state: 'real_time_unverified', transport_connected: true, fresh_seconds: 15, stale_seconds: 120,
    last_received_timestamp: '2026-01-06T15:00:31.000000Z', reason: 'realtime_entitlement_unverified',
  } }))
  await flushPromises()
  expect(wrapper.get('[data-testid="feed-status"]').text()).toBe('Real-time unverified')
  expect(wrapper.find('.mode-badge').text()).toBe('Real-time unverified')
  expect(wrapper.text()).not.toContain('LIVE · FRESH')
  // Status pulses keep transport alive without refreshing quote receipt/source time.
  const heartbeat = setInterval(() => socket.emit(frame('feed_status', socket, 'AAPL', { feed_status: {
    state: 'real_time_unverified', transport_connected: true, fresh_seconds: 15, stale_seconds: 120,
    last_received_timestamp: '2026-01-06T15:00:31.000000Z',
  } })), 5000)
  await vi.advanceTimersByTimeAsync(16000)
  expect(wrapper.get('[data-testid="feed-status"]').text()).toBe('delayed')
  expect(wrapper.find('.mode-badge').text()).toBe('LAST KNOWN · NOT CURRENT')
  await vi.advanceTimersByTimeAsync(105000)
  expect(wrapper.get('[data-testid="feed-status"]').text()).toBe('stale')
  clearInterval(heartbeat)
  socket.disconnect()
  await flushPromises()
  expect(wrapper.get('[data-testid="feed-status"]').text()).toBe('disconnected')
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('100')
})

it('switches between live 5m and 15m candles and ignores other-interval updates', async () => {
  const socket = await mounted()
  socket.emit(frame('feed_status',socket,'AAPL',{feed_status:{state:'real_time_unverified',interval:'1m',live_intervals:['1m','5m','15m']}}))
  await wrapper.get('select[aria-label="Candle interval"]').setValue('5m')
  await flushPromises()
  socket.emit(frame('candle_update',socket,'AAPL',{data:candle({id:10,candle_interval:'5m',close:104,high:105})}))
  socket.emit(frame('candle_update',socket,'AAPL',{data:candle({id:11,candle_interval:'15m',close:999,high:999})}))
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('104')
  expect(wrapper.get('[data-testid="candle-summary"]').text()).toContain('5m · incomplete')
  expect(wrapper.text()).not.toContain('Saved 5m candles only')
  await wrapper.get('select[aria-label="Candle interval"]').setValue('15m')
  await flushPromises()
  socket.emit(frame('candle_update',socket,'AAPL',{data:candle({id:12,candle_interval:'15m',close:110,high:111})}))
  await flushPromises()
  expect(wrapper.get('[data-testid="latest-price"]').text()).toBe('110')
  expect(wrapper.get('[data-testid="candle-summary"]').text()).toContain('15m · incomplete')
  expect(wrapper.text()).not.toContain('Saved 15m candles only')
})

it('offers automatic recent-candle zoom, follow toggle, fit-all and direct replay entry', async () => {
  await mounted()
  expect(wrapper.get('select[aria-label="Visible candles"]').element.value).toBe('25')
  expect(wrapper.get('input[aria-label="Follow latest candles"]').element.checked).toBe(true)
  await wrapper.get('select[aria-label="Visible candles"]').setValue('10')
  expect(wrapper.get('select[aria-label="Visible candles"]').element.value).toBe('10')
  await wrapper.get('button[aria-label="Fit chart to data"]').trigger('click')
  expect(wrapper.get('select[aria-label="Visible candles"]').element.value).toBe('0')
  expect(wrapper.get('input[aria-label="Follow latest candles"]').element.checked).toBe(false)
  await wrapper.get('button[aria-label="Open replay"]').trigger('click')
  await flushPromises()
  expect(wrapper.get('select[aria-label="Data mode"]').element.value).toBe('replay')
  expect(FakeWebSocket.sockets.at(-1).url).toContain('/ws/replay')
})
