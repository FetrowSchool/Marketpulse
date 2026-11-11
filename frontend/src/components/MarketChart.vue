<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { createChartRenderer } from '../services/chartRenderer.js'
import { reliableVolume } from '../services/candleBook.js'
const props = defineProps({ candles: { type: Array, required: true }, symbol: { type: String, required: true },
  interval: { type: String, required: true }, context: { type: String, default: '' }, visibleCandles: { type: Number, default: 0 }, followLatest: { type: Boolean, default: true }, loading: Boolean, error: { type: String, default: '' } })
const host = ref(null)
const chartError = ref('')
const availableVolumes = computed(() => props.candles.filter(reliableVolume).length)
let renderer, observer
function render() {
  if (!renderer) return
  try { renderer.apply(props.candles, `${props.context ? props.context + ':' : ''}${props.symbol}:${props.interval}`, { loading: props.loading }); chartError.value = '' }
  catch { chartError.value = 'Chart could not display these records. Market data is preserved.' }
}
onMounted(() => {
  try {
    renderer = createChartRenderer(host.value)
    renderer.focus?.(props.visibleCandles, props.followLatest)
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(entries => {
        const rect = entries[0]?.contentRect
        if (rect) renderer.resize?.(rect.width, rect.height)
      })
      observer.observe(host.value)
    }
    render()
  }
  catch { chartError.value = 'Chart initialization failed. Refresh to retry.' }
})
watch(() => [props.candles, props.symbol, props.interval, props.loading, props.context], render)
watch(() => [props.visibleCandles, props.followLatest], () => renderer?.focus?.(props.visibleCandles, props.followLatest))
onUnmounted(() => { observer?.disconnect(); renderer?.remove() })
defineExpose({ fit: () => renderer?.fit() })
</script>

<template>
  <div class="market-chart" :aria-label="`${symbol} ${interval} candlestick and volume chart`">
    <div ref="host" class="chart-host" data-testid="chart-canvas"></div>
    <div v-if="!candles.length || chartError" class="chart-overlay" role="status">
      <span class="chart-empty-icon" aria-hidden="true">⌁</span>
      <h3>{{ chartError || (loading ? 'Loading saved candles…' : 'No saved candles for this selection') }}</h3>
      <p>{{ chartError ? 'Prices and metadata remain available in the market panel.' : 'Only observations recorded by your backend will appear here.' }}</p>
    </div>
    <span class="volume-pane-label">VOLUME <b>{{ availableVolumes ? `${availableVolumes} reliable bars` : 'UNAVAILABLE' }}</b></span>
    <p class="volume-explanation" data-testid="volume-state">{{ availableVolumes
      ? 'Only reliable interval volume is plotted. Missing values remain gaps.'
      : 'Volume unavailable: Yahoo quote totals and unsequenced sizes cannot establish candle volume.' }}</p>
    <p v-if="error" class="history-error" role="alert">{{ error }}</p>
    <p class="chart-attribution">TradingView Lightweight Charts™ · Copyright (с) 2025 <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView, Inc.</a> · Time axis in UTC</p>
  </div>
</template>
