<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { createChartRenderer } from '../services/chartRenderer.js'
import { reliableVolume } from '../services/candleBook.js'
import {confirmedChartSignals,signalFills} from '../services/chartSignals.js'
const props = defineProps({ candles: { type: Array, required: true }, symbol: { type: String, required: true },
  interval: { type: String, required: true }, context: { type: String, default: '' }, visibleCandles: { type: Number, default: 0 }, followLatest: { type: Boolean, default: true }, strategyFills: {type:Array,default:()=>[]}, indicators: { type: Object, default: () => ({points:[],signals:[]}) }, showIndicators: {type: Boolean, default: true},showSignals:{type:Boolean,default:true},showFills:{type:Boolean,default:true}, loading: Boolean, error: { type: String, default: '' } })
const host = ref(null)
const chartError = ref('')
const selectedSignalId=ref('')
const signals=computed(()=>confirmedChartSignals(props.indicators,props.candles,props.symbol,props.interval))
const selectedSignal=computed(()=>signals.value.find(signal=>signal.signal_id===selectedSignalId.value)||null)
const executions=computed(()=>signalFills(selectedSignal.value,props.strategyFills,props.symbol,props.interval))
const periods=computed(()=>({fast:props.indicators.configuration?.fast_period||20,slow:props.indicators.configuration?.slow_period||50}))
function value(number){return Number.isFinite(number)?number.toLocaleString(undefined,{maximumFractionDigits:8}):'Unavailable'}
function executionLabel(){
 const signal=selectedSignal.value
 if(executions.value.length)return 'Executed · matching fill record(s) below'
 if(signal?.decision_status && signal.decision_status!=='filled')return `${signal.decision_status} · ${signal.reason?.replaceAll('_',' ')||'No fill recorded'}`
 return 'No matching execution in loaded fill records · execution status not established'
}
function overlays(){renderer?.indicators?.(props.indicators,props.showIndicators,props.strategyFills,{showSignals:props.showSignals,showFills:props.showFills})}
watch(signals,rows=>{if(!rows.some(signal=>signal.signal_id===selectedSignalId.value))selectedSignalId.value=''})

const availableVolumes = computed(() => props.candles.filter(reliableVolume).length)
let renderer, observer
function render() {
  if (!renderer) return
  try { renderer.apply(props.candles, `${props.context ? props.context + ':' : ''}${props.symbol}:${props.interval}`, { loading: props.loading });overlays(); chartError.value = '' }
  catch { chartError.value = 'Chart could not display these records. Market data is preserved.' }
}
onMounted(() => {
  try {
    renderer = createChartRenderer(host.value,undefined,{onSignalSelect:id=>{selectedSignalId.value=id||''}})
    renderer.focus?.(props.visibleCandles, props.followLatest)
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(entries => {
        const rect = entries[0]?.contentRect
        if (rect) renderer.resize?.(rect.width, rect.height)
      })
      observer.observe(host.value)
    }
    render()
    overlays()
  }
  catch { chartError.value = 'Chart initialization failed. Refresh to retry.' }
})
watch(() => [props.candles, props.symbol, props.interval, props.loading, props.context], render)
watch(() => [props.visibleCandles, props.followLatest], () => renderer?.focus?.(props.visibleCandles, props.followLatest))
watch(() => [props.indicators, props.showIndicators, props.strategyFills,props.showSignals,props.showFills], overlays)
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
    <section v-if="signals.length" class="signal-details" aria-label="Confirmed crossover details">
      <label>Signal details<select aria-label="Select crossover signal" v-model="selectedSignalId"><option value="">Click an arrow/candle or choose a signal</option><option v-for="signal in signals" :key="signal.signal_id" :value="signal.signal_id">{{signal.signal}} · {{signal.candle_open_timestamp}}</option></select></label>
      <p v-if="!selectedSignal" class="muted">{{signals.length}} confirmed crossover(s) in this candle snapshot. Arrows are signals; circles are actual simulated fills.</p>
      <dl v-else class="signal-detail-grid" data-testid="selected-signal-details">
        <div><dt>Signal / symbol / interval</dt><dd>{{selectedSignal.signal}} · {{symbol}} · {{interval}}</dd></div>
        <div><dt>Completed candle · UTC</dt><dd>{{selectedSignal.candle_open_timestamp}}</dd></div>
        <div><dt>SMA({{periods.fast}}) / SMA({{periods.slow}})</dt><dd>{{value(selectedSignal.sma20)}} / {{value(selectedSignal.sma50)}}</dd></div>
        <div><dt>Confirmation</dt><dd>Confirmed · completed candle</dd></div>
        <div><dt>Simulated execution</dt><dd>{{executionLabel()}}</dd></div>
        <div v-for="fill in executions" :key="fill.marker_id || fill.id"><dt>{{fill.id ? `Fill #${fill.id}` : 'Recorded backtest fill'}}</dt><dd>{{fill.side}} {{fill.quantity}} shares · price {{fill.execution_price ?? fill.price ?? 'Unavailable'}} · {{fill.execution_timestamp || fill.source_timestamp}}</dd></div>
      </dl>
    </section>
    <p class="chart-attribution">TradingView Lightweight Charts™ · Copyright (с) 2025 <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView, Inc.</a> · Time axis in UTC</p>
  </div>
</template>
