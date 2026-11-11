// Separate transport: replay frames can never enter the live WebSocket/history book.
export function createReplaySocket({ onMessage = () => {}, onState = () => {}, onError = () => {},
  WebSocketClass = globalThis.WebSocket, url } = {}) {
  const address = new URL('/ws/replay', window.location.href)
  address.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  let socket, pending, generation = 0, timeout
  function transmit(request) {
    if (socket?.readyState === 1) socket.send(JSON.stringify(request))
    else pending = request
  }
  function start() {
    stop()
    onState('connecting')
    try { socket = new WebSocketClass(url || address.toString()) }
    catch { onState('disconnected'); onError('Replay connection could not be created'); return }
    const current = socket
    timeout = setTimeout(() => { if (socket === current) failed() }, 10000)
    function failed() {
      if (socket !== current) return
      stop()
      onState('disconnected')
      onError('Replay connection lost. Load the selection again to restart the session.')
    }
    socket.onopen = () => {
      if (socket !== current) return
      clearTimeout(timeout); onState('connected')
      if (pending) { const request = pending; pending = undefined; transmit(request) }
    }
    socket.onmessage = event => {
      if (socket !== current) return
      let message
      try { message = JSON.parse(event.data) } catch { onError('Invalid replay message'); return }
      if (message.schema_version !== 1 || message.display_mode !== 'replay' || message.generation < generation) return
      if (message.type === 'replay_loaded') generation = message.generation
      if (message.type === 'replay_event' && message.generation !== generation) return
      if (message.type === 'error') onError(message.data?.message || 'Replay request failed')
      onMessage(message)
    }
    socket.onerror = failed
    socket.onclose = failed
  }
  function stop() {
    clearTimeout(timeout)
    if (socket) {
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null
      try { socket.close() } catch {}
    }
    socket = undefined; generation = 0
  }
  return { start, stop,
    load(selection, speed = 1, autoplay = false) {
      pending = undefined
      const request = { type: 'load', selection, speed }
      // Queue only load; play is sent after the loaded acknowledgment by the UI.
      transmit(request)
      return autoplay
    },
    command(type, speed) { if (socket?.readyState === 1) transmit({ type, ...(speed === undefined ? {} : { speed }) }) },
  }
}
