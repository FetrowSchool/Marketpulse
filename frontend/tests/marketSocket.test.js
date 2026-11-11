import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMarketSocket, marketSocketUrl } from '../src/services/marketSocket.js'
import { FakeWebSocket, frame } from './socketFixture.js'
let service
beforeEach(() => { vi.useFakeTimers(); FakeWebSocket.sockets = [] })
afterEach(() => { service?.stop(); vi.useRealTimers() })
function start(options = {}) {
  service = createMarketSocket({ url: 'ws://localhost/ws/market', WebSocketClass: FakeWebSocket, ...options })
  service.start()
  return FakeWebSocket.sockets.at(-1)
}
describe('browser market transport', () => {
  it('uses the backend origin, handles messages and rejects other symbols / old generations', () => {
    expect(marketSocketUrl({ href: 'https://example.test/dashboard', protocol: 'https:' })).toBe('wss://example.test/ws/market')
    const messages = vi.fn()
    const socket = start({ onMessage: messages })
    socket.open()
    expect(socket.sent[0]).toEqual({ type: 'subscribe', symbol: 'AAPL', request_id: 1 })
    const old = frame('market_observation', socket)
    socket.emit(old)
    expect(messages).toHaveBeenCalledOnce()
    service.selectSymbol('MSFT')
    socket.emit(old)
    socket.emit(frame('market_observation', socket, 'AAPL'))
    expect(messages).toHaveBeenCalledOnce()
    socket.emit(frame('market_observation', socket, 'MSFT'))
    expect(messages).toHaveBeenCalledTimes(2)
  })
  it('reconnects with capped exponential waits, resubscribes, and exhausts a finite budget', () => {
    const states = vi.fn()
    let socket = start({ onState: states, baseDelay: 100, maxDelay: 200, maxRetries: 3 })
    socket.open(); service.selectSymbol('NVDA'); socket.disconnect()
    for (const delay of [100, 200, 200]) {
      const before = FakeWebSocket.sockets.length
      vi.advanceTimersByTime(delay - 1)
      expect(FakeWebSocket.sockets).toHaveLength(before)
      vi.advanceTimersByTime(1)
      socket = FakeWebSocket.sockets.at(-1)
      socket.open()
      expect(socket.sent.at(-1).symbol).toBe('NVDA')
      socket.disconnect()
    }
    expect(states).toHaveBeenLastCalledWith('unavailable')
    vi.advanceTimersByTime(30000)
    expect(FakeWebSocket.sockets).toHaveLength(4)
  })
  it('handles parse / server errors, timeouts, and explicit cleanup', () => {
    const errors = vi.fn()
    const socket = start({ onError: errors, idleTimeout: 100 })
    socket.open(); socket.emit('invalid JSON')
    expect(errors).toHaveBeenCalledWith('Invalid backend JSON')
    socket.emit(frame('error', socket, 'AAPL', { data: { message: 'Subscription rejected' } }))
    expect(errors).toHaveBeenCalledWith('Subscription rejected')
    vi.advanceTimersByTime(100)
    expect(socket.readyState).toBe(3)
    service.stop()
    const count = FakeWebSocket.sockets.length
    vi.advanceTimersByTime(60000)
    expect(FakeWebSocket.sockets).toHaveLength(count)
  })
})
