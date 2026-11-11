const TYPES = new Set(['connection_status', 'market_observation', 'candle_update', 'candle_completed', 'feed_status', 'error'])
export const SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'SPY']

export function marketSocketUrl(location = window.location) {
  const url = new URL('/ws/market', location.href)
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

// Only this module owns browser WebSockets. It never accesses Yahoo directly.
export function createMarketSocket({ url = marketSocketUrl(), symbol = 'AAPL',
  onMessage = () => {}, onState = () => {}, onError = () => {},
  WebSocketClass = globalThis.WebSocket, maxRetries = 8, baseDelay = 500, maxDelay = 15000,
  connectTimeout = 10000, idleTimeout = 10000, stableAfter = 10000 } = {}) {
  let socket, retryTimer, watchdog, stableTimer
  let stopped = true
  let failures = 0
  let requestId = 0
  let selected = symbol

  function clearConnectionTimers() { clearTimeout(watchdog); clearTimeout(stableTimer) }
  function retire() {
    clearConnectionTimers()
    if (socket) {
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null
      try { socket.close() } catch { /* Transport may already be gone. */ }
      socket = undefined
    }
  }
  function fail(message) {
    if (stopped) return
    retire()
    onError(message)
    if (failures >= maxRetries) { onState('unavailable'); return }
    const delay = Math.min(baseDelay * 2 ** failures, maxDelay)
    failures += 1
    onState('reconnecting')
    clearTimeout(retryTimer)
    retryTimer = setTimeout(connect, delay)
  }
  function subscribe() {
    if (socket?.readyState === 1) {
      requestId += 1
      try { socket.send(JSON.stringify({ type: 'subscribe', symbol: selected, request_id: requestId })) }
      catch { fail('Subscription could not be sent') }
    }
  }
  function connect() {
    if (stopped) return
    onState(failures ? 'reconnecting' : 'connecting')
    try { socket = new WebSocketClass(url) }
    catch { fail('WebSocket could not be created'); return }
    const current = socket
    watchdog = setTimeout(() => fail('Backend WebSocket connection timed out'), connectTimeout)
    socket.onopen = () => {
      if (socket !== current || stopped) return
      clearTimeout(watchdog)
      onState('connected')
      subscribe()
      watchdog = setTimeout(() => fail('Backend status updates stopped'), idleTimeout)
      stableTimer = setTimeout(() => { failures = 0 }, stableAfter)
    }
    socket.onmessage = event => {
      if (socket !== current || stopped) return
      let message
      try { message = JSON.parse(event.data) } catch { onError('Invalid backend JSON'); return }
      if (!message || message.schema_version !== 1 || !TYPES.has(message.type) ||
          message.symbol !== selected || message.subscription_id !== requestId) return
      clearTimeout(watchdog)
      watchdog = setTimeout(() => fail('Backend status updates stopped'), idleTimeout)
      if (message.type === 'error') onError(message.data?.message || 'Backend subscription error')
      onMessage(message)
    }
    socket.onerror = () => { if (socket === current) fail('Backend WebSocket connection failed') }
    socket.onclose = () => { if (socket === current) fail('Backend WebSocket disconnected') }
  }
  return {
    start() { if (!stopped) return; stopped = false; failures = 0; connect() },
    selectSymbol(value) {
      if (!SYMBOLS.includes(value)) throw new Error('Unsupported symbol')
      selected = value
      subscribe()
    },
    reconnect() { clearTimeout(retryTimer); retire(); stopped = false; failures = 0; connect() },
    stop() { stopped = true; clearTimeout(retryTimer); retire(); onState('disconnected') },
  }
}
