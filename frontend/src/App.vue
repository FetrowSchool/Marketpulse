<script setup>
import { ref, shallowRef, reactive, computed, onMounted, onUnmounted } from 'vue'
import { createMarketSocket, SYMBOLS } from './services/marketSocket.js'
import { createCandleHistory } from './services/candleHistory.js'
import { INTERVALS, reliableVolume, createCandleBook } from './services/candleBook.js'
import MarketChart from './components/MarketChart.vue'
import { createReplaySocket } from './services/replaySocket.js'
const mode = ref('live')
const replayConnection = ref('disconnected'), replayError = ref('')
const replayState = ref({ state: 'idle', generation: 0, position: 0, total: 0 })
const replayRecord = ref(null), replayCatalog = ref(null), replayLoaded = ref(false)
const rangeStart = ref(''), rangeEnd = ref(''), playbackSpeed = ref(10), replayOrder = ref('receipt'), rangeDirty = ref(false)
const displayConnection = computed(() => mode.value === 'replay' ? replayConnection.value : connection.value)
const backend = ref('Checking'), database = ref('Unknown'), version = ref('—')
const selectedSymbol = ref('AAPL'), selectedInterval = ref('1m'), configuredInterval = ref('1m')
const liveIntervals = ref(null)
const connection = ref('connecting'), feed = ref(null), socketError = ref(''), subscribed = ref(false)
const quotes = reactive({})
const lastReceipts = reactive({})
const chartRows = shallowRef([])
const historyState = ref({ loading: true, error: '', invalid: false })
const chart = ref(null)
const zoomCount = ref(25), followLatest = ref(true)
function changeZoom() { if (zoomCount.value === 0) followLatest.value = false }
function fitAllCandles() { zoomCount.value = 0; followLatest.value = false; chart.value?.fit() }
const lastCandle = computed(() => chartRows.value.at(-1) || null)
const latestQuote = computed(() => quotes[selectedSymbol.value] || null)
const latest = computed(() => {
  const quote = latestQuote.value, candle = lastCandle.value
  const closingQuoteId = candle?.metadata?.contributing_observation_ids?.at(-1)
  const quoteIsLatest = quote && (!candle || quote.source_timestamp > candle.source_timestamp ||
    (quote.source_timestamp === candle.source_timestamp && (!closingQuoteId || quote.id >= closingQuoteId)))
  return quoteIsLatest ? quote : candle
})
const now = ref(Date.now())
const sourceTime = computed(() => latest.value?.source_timestamp || feed.value?.latest_source_timestamp || null)
const receiptTime = computed(() => lastReceipts[selectedSymbol.value] || latest.value?.received_timestamp || null)
const dataAge = computed(() => {
  const clock = mode.value === 'replay' ? Date.parse(replayState.value.playhead_receipt_timestamp || receiptTime.value) : now.value
  return sourceTime.value && Number.isFinite(clock) ? (clock - Date.parse(sourceTime.value)) / 1000 : null
})
const price = computed(() => number(latest.value?.price ?? latest.value?.close))
const providerChange = computed(() => latestQuote.value?.metadata?.original || {})
const hasChange = computed(() => Number.isFinite(providerChange.value.change) || Number.isFinite(providerChange.value.change_percent))
const chartModes = computed(() => [...new Set(chartRows.value.map(row => row.data_mode))].join(' / '))
const visibleFeedState = computed(() => {
  if (mode.value === 'replay') return 'replay'
  if (connection.value !== 'connected') return 'disconnected'
  if (!subscribed.value || !feed.value) return 'connecting'
  if (['live', 'real_time_unverified', 'delayed'].includes(feed.value.state)) {
    const receiptAge = receiptTime.value ? (now.value - Date.parse(receiptTime.value)) / 1000 : null
    if (dataAge.value > feed.value.stale_seconds || receiptAge > feed.value.stale_seconds) return 'stale'
    if (dataAge.value > feed.value.fresh_seconds || receiptAge > feed.value.fresh_seconds) return 'delayed'
  }
  return feed.value.state
})
const classification = computed(() => {
  if (mode.value === 'replay') return 'REPLAY · RECORDED'
  if (!latest.value) return 'NO MARKET DATA'
  const provenance = latest.value.data_mode
  if (provenance === 'recorded' || provenance === 'simulated') return provenance.toUpperCase()
  if (visibleFeedState.value === 'real_time_unverified') return 'Real-time unverified'
  const current = connection.value === 'connected' && subscribed.value && visibleFeedState.value === 'live'
    && provenance === 'live' && dataAge.value <= feed.value.fresh_seconds
  return current ? 'LIVE · FRESH' : 'LAST KNOWN · NOT CURRENT'
})
const historyOnly = computed(() => mode.value === 'live' && !(liveIntervals.value || [configuredInterval.value]).includes(selectedInterval.value))
function number(value) { return Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 8 }) : '—' }
function signed(value) { return Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—' }
function readable(value) { if (value === 'real_time_unverified') return 'Real-time unverified'; return value ? value.replaceAll('_', ' ') : 'Awaiting status' }
function shortTime(value) { return value ? value.replace('T', ' ').replace('.000000Z', ' UTC').replace('Z', ' UTC') : '—' }
let timer, ageTimer, controller, socket, symbolsController, history
let userSelected = false, userInterval = false
let liveEpoch = 0, replayEpoch = 0, replayClient, replayBook, replayCatalogController, autoplay = false, disposed = false
function clearData() {
  for (const key of Object.keys(quotes)) delete quotes[key]
  for (const key of Object.keys(lastReceipts)) delete lastReceipts[key]
  chartRows.value = []; replayRecord.value = null
}
function createLiveHistory() {
  const epoch = ++liveEpoch
  history = createCandleHistory({
    onChange: rows => { if (mode.value === 'live' && epoch === liveEpoch) chartRows.value = rows },
    onState: value => { if (mode.value === 'live' && epoch === liveEpoch) historyState.value = value },
  })
}
function loadHistory() { if (mode.value === 'live') return history.load(selectedSymbol.value, selectedInterval.value) }
function updateQuote(incoming) {
  if (!incoming || incoming.symbol !== selectedSymbol.value || !Number.isFinite(incoming.price)) return
  const previous = quotes[incoming.symbol]
  if (!previous || incoming.source_timestamp > previous.source_timestamp ||
      (incoming.source_timestamp === previous.source_timestamp && incoming.id > previous.id)) quotes[incoming.symbol] = incoming
}
function applyRecorded(row, baseline = false) {
  if (row.symbol !== selectedSymbol.value) return
  if (row.observation_type === 'raw_provider') updateQuote(row)
  else replayBook.merge([row])
  if (row.received_timestamp && (!baseline || !lastReceipts[row.symbol] || row.received_timestamp > lastReceipts[row.symbol])) {
    lastReceipts[row.symbol] = row.received_timestamp
  }
  if (!baseline) replayRecord.value = row
  chartRows.value = replayBook.rows()
}
function replayMessage(message) {
  if (mode.value !== 'replay') return
  if (message.type === 'replay_loaded') {
    clearData()
    replayBook = createCandleBook(selectedSymbol.value, selectedInterval.value)
    replayState.value = message.data
    for (const row of message.data.baseline || []) applyRecorded(row, true)
    replayLoaded.value = true; rangeDirty.value = false; replayError.value = ''
    if (autoplay) { autoplay = false; replayClient.command('play') }
  } else if (message.type === 'replay_event') applyRecorded(message.data.record)
  else if (message.type === 'replay_status' && !(message.data.state === 'idle' && replayState.value.state === 'loading')) replayState.value = message.data
}
function replaySelection() {
  return { symbol: selectedSymbol.value, interval: selectedInterval.value,
    start: rangeStart.value ? rangeStart.value + 'Z' : null, end: rangeEnd.value ? rangeEnd.value + 'Z' : null,
    order: replayOrder.value }
}
function loadReplay(play = false) {
  if (!replayCatalog.value?.event_count) return
  if (replayConnection.value === 'disconnected') replayClient.start()
  replayLoaded.value = false; replayError.value = ''; autoplay = play
  replayState.value = { ...replayState.value, state: 'loading' }
  replayClient.load(replaySelection(), playbackSpeed.value)
}
async function prepareReplay() {
  const epoch = ++replayEpoch
  replayClient?.stop(); replayCatalogController?.abort()
  clearData(); replayLoaded.value = false; replayError.value = ''; replayCatalog.value = null; autoplay = false
  replayState.value = { state: 'idle', generation: 0, position: 0, total: 0 }
  historyState.value = { loading: false, error: '', invalid: false }
  replayBook = createCandleBook(selectedSymbol.value, selectedInterval.value)
  replayClient = createReplaySocket({
    onMessage: message => { if (epoch === replayEpoch && mode.value === 'replay') replayMessage(message) },
    onState: state => { if (epoch === replayEpoch) replayConnection.value = state },
    onError: error => { if (epoch === replayEpoch) { replayError.value = error; replayLoaded.value = false; replayState.value = { ...replayState.value, state: 'error' } } },
  })
  replayClient.start()
  replayCatalogController = new AbortController()
  try {
    const query = new URLSearchParams({ symbol: selectedSymbol.value, interval: selectedInterval.value })
    const response = await fetch('/api/replay/catalog?' + query, { signal: replayCatalogController.signal })
    if (!response.ok) throw new Error('Recordings unavailable')
    const data = await response.json()
    if (epoch !== replayEpoch || mode.value !== 'replay' || disposed) return
    replayCatalog.value = data
    if (data.event_count) {
      const first = Date.parse(data.first_receipt), end = Math.ceil(Date.parse(data.last_receipt) / 1000) * 1000 + 1000
      rangeStart.value = new Date(Math.max(first, end - 15 * 60000)).toISOString().slice(0, 19)
      rangeEnd.value = new Date(end).toISOString().slice(0, 19)
      loadReplay(false)
    }
  } catch {
    if (epoch === replayEpoch && mode.value === 'replay') replayError.value = 'Saved recording catalog unavailable'
  }
}
function switchMode() {
  if (mode.value === 'replay') {
    liveEpoch += 1; history?.dispose(); socket.stop(); feed.value = null
    prepareReplay()
  } else {
    replayEpoch += 1; replayClient?.stop(); replayCatalogController?.abort()
    clearData(); replayLoaded.value = false; replayError.value = ''; feed.value = null
    createLiveHistory(); loadHistory(); socket.selectSymbol(selectedSymbol.value); socket.start()
  }
}
function playReplay() {
  if (!replayLoaded.value || rangeDirty.value) loadReplay(true)
  else replayClient.command(replayState.value.state === 'completed' ? 'restart' : 'play')
}
function replayCommand(type) { replayClient.command(type) }
function changeSpeed() { if (mode.value === 'replay' && replayLoaded.value) replayClient.command('speed', playbackSpeed.value) }
function changeRange() {
  rangeDirty.value = true
  if (replayState.value.state === 'playing') replayClient.command('pause')
}

function receiveMarket(message) {
  if (mode.value !== 'live') return
  const receipt = message.feed_status?.last_received_timestamp
  if (receipt) lastReceipts[selectedSymbol.value] = receipt
  else if (message.type === 'market_observation' && !lastReceipts[selectedSymbol.value]) {
    lastReceipts[selectedSymbol.value] = message.data?.received_timestamp
  }
  if (message.feed_status) {
    feed.value = message.feed_status
    if (Array.isArray(message.feed_status.live_intervals)) liveIntervals.value = message.feed_status.live_intervals.filter(value => INTERVALS.includes(value))
    if (INTERVALS.includes(message.feed_status.interval)) {
      configuredInterval.value = message.feed_status.interval
      if (!userInterval && selectedInterval.value !== configuredInterval.value) {
        selectedInterval.value = configuredInterval.value
        loadHistory()
      }
    }
  }
  if (message.type === 'connection_status' && message.data?.state === 'subscribed') {
    subscribed.value = true
    socketError.value = ''
    // Catch up the interval between an HTTP request and successful subscription/reconnection.
    loadHistory()
  }
  if (message.type === 'candle_update' || message.type === 'candle_completed') history.merge(message.data)
  if (message.type === 'market_observation') updateQuote(message.data)
}
function switchSymbol() {
  userSelected = true
  if (mode.value === 'replay') { prepareReplay(); return }
  subscribed.value = false
  feed.value = null
  socketError.value = ''
  loadHistory()
  socket.selectSymbol(selectedSymbol.value)
}
function switchInterval() { userInterval = true; if (mode.value === 'replay') prepareReplay(); else loadHistory() }
async function checkHealth() {
  controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch('/api/health', { signal: controller.signal })
    const health = await response.json()
    if (typeof health.version !== 'string') throw new Error('Invalid health response')
    backend.value = response.ok && health.status === 'ok' ? 'Available' : 'Degraded'
    database.value = health.database === 'connected' ? 'Connected' : 'Unavailable'
    version.value = health.version
  } catch {
    backend.value = 'Unavailable'
    database.value = 'Unknown'
    version.value = '—'
  } finally { clearTimeout(timeout) }
}
onMounted(() => {
  createLiveHistory()
  loadHistory()
  socket = createMarketSocket({ symbol: selectedSymbol.value, onMessage: receiveMarket,
    onState: state => { connection.value = state; if (state !== 'connected') { subscribed.value = false; feed.value = null } },
    onError: error => { socketError.value = error },
  })
  socket.start()
  checkHealth()
  timer = setInterval(checkHealth, 15000)
  ageTimer = setInterval(() => { now.value = Date.now() }, 1000)
  symbolsController = new AbortController()
  fetch('/api/market/symbols', { signal: symbolsController.signal }).then(response => response.json()).then(result => {
    if (mode.value !== 'live' || disposed) return
    if (Array.isArray(result.live_intervals)) liveIntervals.value = result.live_intervals.filter(value => INTERVALS.includes(value))
    let changed = false
    if (!userInterval && INTERVALS.includes(result.active_interval)) {
      configuredInterval.value = selectedInterval.value = result.active_interval
      changed = true
    }
    if (!userSelected && result.active_symbol !== selectedSymbol.value && SYMBOLS.includes(result.active_symbol)) {
      selectedSymbol.value = result.active_symbol
      subscribed.value = false
      feed.value = null
      socket.selectSymbol(selectedSymbol.value)
      changed = true
    }
    if (changed) loadHistory()
  }).catch(() => {})
})
onUnmounted(() => {
  disposed = true; replayEpoch += 1; replayClient?.stop(); replayCatalogController?.abort()
  clearInterval(timer); clearInterval(ageTimer)
  controller?.abort(); symbolsController?.abort(); history?.dispose(); socket?.stop()
})
</script>

<template>
  <div class="workstation">
    <header class="topbar">
      <a class="brand" href="#"><span class="brand-mark" aria-hidden="true">▥</span>Market<span>Pulse</span></a>
      <span class="workspace-label">MARKET WORKSTATION</span>
      <div class="top-selectors"><label>MODE<select aria-label="Data mode" v-model="mode" @change="switchMode"><option value="live">Live</option><option value="replay">Replay</option></select></label><label>SYMBOL<select aria-label="Stock symbol" v-model="selectedSymbol" @change="switchSymbol"><option v-for="symbol in SYMBOLS" :key="symbol">{{ symbol }}</option></select></label><label>INTERVAL<select aria-label="Candle interval" v-model="selectedInterval" @change="switchInterval"><option v-for="interval in INTERVALS" :key="interval">{{ interval }}</option></select></label></div>
      <span class="feed-pill" :class="visibleFeedState"><i class="dot"></i>{{ mode === 'replay' ? `Replay · ${readable(replayState.state)}` : readable(visibleFeedState) }}</span>
    </header>
    <main>
      <div class="page-title"><div><p class="eyebrow">MARKET DATA / WORKSTATION</p><h1>Market overview</h1></div><span class="mode-badge" :class="latest?.data_mode">{{ classification }}</span></div>
      <section class="status-grid" aria-label="System status">
        <article class="status-card"><span>{{ mode === 'replay' ? 'REPLAY SOCKET' : 'BROWSER ↔ BACKEND' }}</span><strong data-testid="socket-status">{{ displayConnection }} <i class="dot" :class="displayConnection === 'connected' ? 'good' : 'neutral'"></i></strong><small>Application WebSocket</small></article>
        <article class="status-card"><span>{{ mode === 'replay' ? 'RECORDED PLAYBACK' : 'YAHOO FINANCE FEED' }}</span><strong data-testid="feed-status" :class="visibleFeedState">{{ mode === 'replay' ? readable(replayState.state) : readable(visibleFeedState) }}</strong><small>{{ mode === 'replay' ? 'Yahoo connectivity not required' : `Provider socket: ${feed?.transport_connected ? 'connected' : 'disconnected / unknown'}` }}</small></article>
        <article class="status-card"><span>{{ mode === 'replay' ? 'RECORDED SOURCE AGE' : 'SOURCE DATA AGE' }}</span><strong data-testid="data-age">{{ dataAge === null ? '—' : `${dataAge.toFixed(1)}s` }}</strong><small>{{ mode === 'live' && latest && visibleFeedState === 'real_time_unverified' ? 'Real-time unverified' : (latest?.data_mode || 'No observations') }} · source clock in UTC</small></article>
        <article class="status-card" role="status" aria-live="polite"><span>BACKEND HEALTH</span><strong>{{ backend }} <i class="dot" :class="backend === 'Available' ? 'good' : 'neutral'"></i></strong><small>Database: {{ database }} · v{{ version }}</small></article>
      </section>
      <p v-if="socketError && mode === 'live'" class="connection-error" role="alert">{{ socketError }} <button @click="socket.reconnect()">Reconnect backend</button></p>
      <div class="analysis-layout">
        <section class="panel chart-panel" aria-labelledby="chart-title">
          <div class="panel-toolbar"><div class="instrument"><span class="instrument-icon">{{ selectedSymbol.slice(0, 1) }}</span><div><h2 id="chart-title">{{ selectedSymbol }} <span>· {{ selectedInterval }}</span></h2><p>Yahoo Finance <span class="divider">/</span> Constructed quote candles</p></div></div><div class="chart-actions"><span v-if="historyState.loading" class="loading-label">Loading history…</span><label class="zoom-selector">Zoom<select aria-label="Visible candles" v-model.number="zoomCount" @change="changeZoom"><option :value="0">All history</option><option v-for="count in [10,25,50,100]" :key="count" :value="count">Latest {{ count }}</option></select></label><label class="follow-control"><input type="checkbox" aria-label="Follow latest candles" v-model="followLatest" :disabled="zoomCount === 0"> Follow latest</label><button aria-label="Fit chart to data" @click="fitAllCandles">Fit all</button></div></div>
          <div class="ohlc-legend" aria-label="Latest candle values"><span v-for="[label, key] in [['O','open'],['H','high'],['L','low'],['C','close']]" :key="key">{{ label }} <b>{{ number(lastCandle?.[key]) }}</b></span><span class="candle-state" :class="lastCandle?.candle_complete ? 'complete' : 'provisional'">{{ lastCandle ? (lastCandle.candle_complete ? 'Complete' : 'Provisional') : 'Awaiting candles' }}</span></div>
          <MarketChart ref="chart" :visible-candles="zoomCount" :follow-latest="followLatest" :context="mode === 'replay' ? `replay:${replayState.generation}` : 'live'" :candles="chartRows" :symbol="selectedSymbol" :interval="selectedInterval" :loading="historyState.loading" :error="historyState.error" />
          <div class="chart-footer"><span>{{ chartRows.length }} saved / received candles <b>Stored provenance: {{ chartModes || 'No data' }}</b></span><span>UTC · {{ selectedInterval }} · revisions preserved</span></div>
          <p v-if="historyOnly" class="interval-note">Saved {{ selectedInterval }} candles only. The backend currently constructs live {{ (liveIntervals || [configuredInterval]).join(', ') }} candles.</p>
          <p v-if="historyState.invalid" class="history-error">Some records lack valid OHLC and cannot be plotted.</p>
        </section>
        <aside class="market-sidebar">
          <section class="panel quote-panel"><p class="eyebrow">{{ selectedSymbol }} / MARKET INFORMATION</p><h2 data-testid="latest-price">{{ price }}</h2><p class="price-origin">{{ latest?.observation_type === 'raw_provider' ? 'Latest received quote' : (latest ? 'Last saved candle close' : 'No price received') }} <span>{{ latestQuote?.metadata?.original?.currency || 'Currency not supplied' }}</span></p>
            <div class="price-change" :class="hasChange ? ((providerChange.change ?? providerChange.change_percent) >= 0 ? 'positive' : 'negative') : 'muted'"><strong>{{ hasChange ? signed(providerChange.change) : '—' }}<template v-if="Number.isFinite(providerChange.change_percent)"> ({{ signed(providerChange.change_percent) }}%)</template></strong><span>Provider-reported change {{ !hasChange ? 'unavailable' : '' }}</span></div>
            <div class="data-classification">{{ classification }}</div>
            <dl class="detail-list"><div><dt>Data source</dt><dd>Yahoo Finance</dd></div><div><dt>Source timestamp · UTC</dt><dd data-testid="source-time" class="timestamp">{{ sourceTime || '—' }}</dd></div><div><dt>Backend receipt · UTC</dt><dd data-testid="receipt-time" class="timestamp">{{ receiptTime || '—' }}</dd></div><div><dt>Feed</dt><dd>{{ readable(visibleFeedState) }}</dd></div><div><dt>Feed context</dt><dd>{{ readable(feed?.reason) }}</dd></div></dl>
          </section>
          <section class="panel candle-panel"><div class="section-heading"><h2>Current candle</h2><span>{{ selectedInterval }}</span></div><p class="muted candle-summary" data-testid="candle-summary">{{ lastCandle ? `${lastCandle.candle_interval} · ${lastCandle.candle_complete ? 'complete' : 'incomplete'} · r${lastCandle.revision}` : 'No candle available' }}</p><div class="candle-values"><div v-for="key in ['open','high','low','close']" :key="key"><span>{{ key }}</span><b>{{ number(lastCandle?.[key]) }}</b></div></div><dl class="detail-list compact"><div><dt>Opening · UTC</dt><dd>{{ shortTime(lastCandle?.candle_open_timestamp) }}</dd></div><div><dt>Stored provenance</dt><dd>{{ lastCandle?.data_mode || '—' }}</dd></div><div><dt>Volume</dt><dd>{{ lastCandle && reliableVolume(lastCandle) ? number(lastCandle.volume) : 'Unavailable / not inferred' }}</dd></div></dl></section>
          <p class="integrity-note"><span aria-hidden="true">◈</span> An open connection does not establish live or current market data. Prices remain labeled by their source and age.</p>
        </aside>
      </div>
      <section class="panel observation-panel" aria-label="Observation information"><div><span class="eyebrow">LATEST OBSERVATION</span><b>{{ latestQuote ? `#${latestQuote.id} · revision ${latestQuote.revision || '—'}` : 'No raw observation received' }}</b></div><div><span class="eyebrow">SOURCE IDENTITY</span><b class="identity" :title="latestQuote?.source_observation_id">{{ latestQuote?.source_observation_id || '—' }}</b></div><div><span class="eyebrow">REGULAR SESSION</span><b>{{ readable(feed?.market_session) }}</b></div></section>
      <section class="panel replay-panel" aria-labelledby="replay-title">
        <div><p class="eyebrow">{{ mode === 'replay' ? 'REPLAY · READ-ONLY RECORDED DATA' : 'HISTORICAL WORKSPACE' }}</p><h2 id="replay-title">Market replay <span class="coming">{{ mode === 'replay' ? readable(replayState.state) : 'Select Replay mode' }}</span></h2><p class="muted">{{ mode === 'replay' ? 'Original timestamps and revisions. Live events are isolated.' : 'Switch to Replay to enable playback of saved observations.' }}</p><button v-if="mode === 'live'" class="open-replay" aria-label="Open replay" @click="mode = 'replay'; switchMode()">Open replay</button></div>
        <div class="replay-actions"><button aria-label="Play replay" :disabled="mode !== 'replay' || !replayCatalog?.event_count || ['playing','loading','paused'].includes(replayState.state)" @click="playReplay">▶ Play</button><button aria-label="Pause replay" :disabled="mode !== 'replay' || replayState.state !== 'playing'" @click="replayCommand('pause')">Pause</button><button aria-label="Resume replay" :disabled="mode !== 'replay' || replayState.state !== 'paused'" @click="replayCommand('resume')">Resume</button><button aria-label="Restart replay" :disabled="mode !== 'replay' || !replayLoaded" @click="replayCommand('restart')">Restart</button><button aria-label="Stop replay" :disabled="mode !== 'replay' || !replayLoaded" @click="replayCommand('stop')">Stop</button></div>
        <div class="replay-selection"><label>Start · UTC<input type="datetime-local" step="1" aria-label="Replay start UTC" v-model="rangeStart" @change="changeRange" :disabled="mode !== 'replay'"></label><label>End · UTC (exclusive)<input type="datetime-local" step="1" aria-label="Replay end UTC" v-model="rangeEnd" @change="changeRange" :disabled="mode !== 'replay'"></label><label>Ordering<select aria-label="Replay ordering" v-model="replayOrder" @change="changeRange" :disabled="mode !== 'replay'"><option value="receipt">Receipt time + ID</option><option value="arrival">Commit arrival ID</option></select></label><label>Speed<select aria-label="Replay speed" v-model.number="playbackSpeed" @change="changeSpeed" :disabled="mode !== 'replay'"><option v-for="speed in [.25,.5,1,2,5,10,25,50,100]" :key="speed" :value="speed">{{ speed }}×</option></select></label><button aria-label="Load replay selection" :disabled="mode !== 'replay' || !replayCatalog?.event_count" @click="loadReplay(false)">Load selection</button></div>
        <p v-if="replayError" class="replay-notice" role="alert">{{ replayError }}</p><p v-else-if="mode === 'replay' && replayCatalog && !replayCatalog.event_count" class="replay-notice">No saved observations for this symbol and interval. No demonstration prices are generated.</p><p v-else-if="rangeDirty && mode === 'replay'" class="replay-notice">Range changed. Load selection or Play to apply it.</p>
        <progress aria-label="Replay progress" :value="replayState.position || 0" :max="replayState.total || 1"></progress><div class="timeline-labels"><span data-testid="replay-progress">{{ mode === 'replay' ? `${replayState.position || 0} / ${replayState.total || 0} recorded events` : 'Live mode · replay inactive' }}</span><span>{{ mode === 'replay' ? `${playbackSpeed}× · snapshot #${replayState.snapshot_max_id ?? '—'}` : '' }}</span></div>
        <p v-if="mode === 'replay'" class="replay-record" data-testid="replay-record">{{ replayRecord ? `Record #${replayRecord.id} · ${replayRecord.observation_type} · revision ${replayRecord.revision} · source ${replayRecord.source_timestamp} · receipt ${replayRecord.received_timestamp}` : 'As-of baseline loaded; no playback event emitted yet.' }}</p>
      </section>
      <footer><span><i class="dot neutral"></i> MarketPulse · Assignment 4.1</span><span>Observation integrity first.</span></footer>
    </main>
  </div>
</template>
