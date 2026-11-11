import { afterEach, expect, it, vi } from 'vitest'
import { createReplaySocket } from '../src/services/replaySocket.js'
import { FakeWebSocket } from './socketFixture.js'
let client
afterEach(() => client?.stop())
it('queues loading, filters live/old-generation messages, and sends controls separately', () => {
  FakeWebSocket.sockets = []
  const messages = vi.fn()
  client = createReplaySocket({ WebSocketClass: FakeWebSocket, onMessage: messages })
  client.start(); client.load({ symbol: 'AAPL', interval: '1m', order: 'receipt' }, 25)
  const socket = FakeWebSocket.sockets.at(-1)
  expect(socket.url).toContain('/ws/replay')
  socket.open()
  expect(socket.sent.at(-1)).toMatchObject({ type: 'load', speed: 25 })
  socket.emit({ schema_version: 1, type: 'market_observation', data: { price: 999 } })
  expect(messages).not.toHaveBeenCalled()
  const envelope = (type, generation) => ({ schema_version: 1, display_mode: 'replay', type, generation, data: {} })
  socket.emit(envelope('replay_loaded', 2))
  socket.emit(envelope('replay_event', 1))
  expect(messages).toHaveBeenCalledTimes(1)
  socket.emit(envelope('replay_event', 2))
  expect(messages).toHaveBeenCalledTimes(2)
  client.command('pause'); client.command('speed', 50); client.command('resume')
  expect(socket.sent.slice(-3).map(row => row.type)).toEqual(['pause', 'speed', 'resume'])
  client.stop()
  socket.emit(envelope('replay_event', 2))
  expect(messages).toHaveBeenCalledTimes(2)
})
