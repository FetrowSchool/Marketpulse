<script setup>
import {vRememberPanel} from '../services/panelPreferences.js'
import CollapsiblePanel from './CollapsiblePanel.vue'
import MarketChart from './MarketChart.vue'
import {computed,onUnmounted,ref} from 'vue'
const props=defineProps({symbol:{type:String,required:true},interval:{type:String,required:true}})
const start=ref(''),end=ref(''),balance=ref('10000'),fast=ref(20),slow=ref(50),candleType=ref('constructed_candle')
const busy=ref(false),error=ref(''),result=ref(null)
const chartData=ref(null),chartError=ref(''),chartLoading=ref(false),chartSignals=ref(true),chartFills=ref(true)
let chartController,chartVersion=0
let controller,disposed=false
const currency=value=>value==null?'Unavailable':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(value))
const percent=value=>value==null?'N/A':Number(value).toFixed(2)+'%'
const curve=computed(()=>result.value?.equity_curve ?? [])
const bounds=computed(()=>{const values=curve.value.map(p=>Number(p.equity));return {low:Math.min(...values),high:Math.max(...values)}})
const points=computed(()=>{
 const values=curve.value,range=bounds.value.high-bounds.value.low
 const first=Date.parse(values[0]?.timestamp),last=Date.parse(values.at(-1)?.timestamp)
 return values.map(p=>`${12+(last>first?(Date.parse(p.timestamp)-first)/(last-first):0)*776},${range?128-(Number(p.equity)-bounds.value.low)/range*116:70}`).join(' ')
})
async function run(){
 if(busy.value)return
 busy.value=true;error.value='';result.value=null;chartVersion++;chartController?.abort();chartData.value=null;chartError.value='';chartLoading.value=false
 controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),60000)
 try{
  if(!start.value || !end.value)throw new Error('Select both start and end dates (UTC).')
  const body={symbol:props.symbol,interval:props.interval,start:start.value+'T00:00:00Z',end:end.value+'T00:00:00Z',starting_balance:balance.value,fast_period:Number(fast.value),slow_period:Number(slow.value),candle_type:candleType.value}
  const response=await fetch('/api/backtests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal})
  const data=await response.json()
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(e=>e.msg).join('; '):'Backtest request failed')
  if(!data.summary || !Array.isArray(data.equity_curve))throw new Error('Invalid backtest response')
  if(!disposed)result.value=data
 }catch(e){if(!disposed)error.value=e.name==='AbortError'?'Backtest timed out; check saved runs via /api/backtests before retrying.':e.message}
 finally{clearTimeout(timeout);if(!disposed)busy.value=false}
}
async function showChart(){
 if(!result.value || chartLoading.value)return
 const id=result.value.id,version=++chartVersion
 chartLoading.value=true;chartError.value=''
 chartController?.abort();const own=new AbortController();chartController=own
 const timeout=setTimeout(()=>own.abort(),15000)
 try{
  const response=await fetch(`/api/backtests/${id}/chart`,{signal:own.signal})
  const data=await response.json()
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Backtest chart unavailable')
  if(data.id!==id || data.symbol!==result.value?.configuration.symbol || data.interval!==result.value?.configuration.interval || !Array.isArray(data.candles) || !Array.isArray(data.indicators?.signals) || !Array.isArray(data.fills))throw new Error('Invalid backtest chart response')
  if(!disposed&&version===chartVersion)chartData.value=data
 }catch(e){if(!disposed&&version===chartVersion)chartError.value=e.message}
 finally{clearTimeout(timeout);if(!disposed&&version===chartVersion)chartLoading.value=false}
}
onUnmounted(()=>{disposed=true;chartVersion++;controller?.abort();chartController?.abort()})
</script>

<template>
<CollapsiblePanel class="panel paper-panel backtest-panel" storage-key="backtesting" title="Historical backtesting" :subtitle="busy ? 'Running…' : 'Isolated simulated account'" aria-labelledby="backtest-title">
 <p class="eyebrow">HISTORICAL BACKTEST · ISOLATED SIMULATED ACCOUNT</p>
 <h2 id="backtest-title">SMA crossover backtesting</h2>
 <p class="muted">Stored candles only · {{symbol}} / {{interval}} · no changes to your live paper account</p>
 <form class="backtest-form" @submit.prevent="run">
  <label>Start date (UTC)<input aria-label="Backtest start date" type="date" v-model="start" required :disabled="busy"></label>
  <label>End date (UTC, exclusive)<input aria-label="Backtest end date" type="date" v-model="end" required :disabled="busy"></label>
  <label>Starting cash ($)<input aria-label="Backtest starting balance" type="number" min="0.000001" max="1000000" step="0.000001" v-model="balance" required :disabled="busy"></label>
  <label>Fast SMA<input aria-label="Backtest fast SMA" type="number" min="1" max="499" v-model="fast" required :disabled="busy"></label>
  <label>Slow SMA<input aria-label="Backtest slow SMA" type="number" min="2" max="500" v-model="slow" required :disabled="busy"></label>
  <label>Candle origin<select aria-label="Backtest candle origin" v-model="candleType" :disabled="busy"><option value="constructed_candle">Locally constructed</option><option value="provider_candle">Provider historical OHLCV</option></select></label>
  <button type="submit" :disabled="busy">{{busy?'Running backtest…':'Run Backtest'}}</button>
 </form>
 <p v-if="busy" role="status">Processing recorded events in an isolated account…</p>
 <p v-if="error" class="history-error" role="alert">{{error}}</p>
 <p v-if="!result && !busy && !error" class="muted">Choose a range with at least slow SMA + 1 completed candles. No prices are downloaded or invented.</p>
 <div v-if="result" data-testid="backtest-result">
  <p><b>BACKTEST · SIMULATED</b> #{{result.id}} · {{result.configuration.symbol}} {{result.configuration.interval}} · SMA {{result.configuration.fast_period}}/{{result.configuration.slow_period}} · {{result.configuration.start}} → {{result.configuration.end}}</p>
  <div class="backtest-chart-actions"><button type="button" aria-label="Show backtest signals on chart" :disabled="chartLoading" @click="showChart">{{chartLoading?'Loading exact candle snapshot…':'Show backtest signals on chart'}}</button><button v-if="chartData" type="button" @click="chartData=null">Hide backtest chart</button></div>
  <p v-if="chartError" role="alert" class="history-error">{{chartError}}</p>
  <section v-if="chartData" class="backtest-market-chart" aria-label="Recorded backtest candle chart">
    <h3>BACKTEST #{{chartData.id}} · {{chartData.symbol}} · {{chartData.interval}} · recorded snapshot</h3>
    <p class="muted">SMA({{result.configuration.fast_period}}) / SMA({{result.configuration.slow_period}}) · arrows are recorded confirmed signals; FILL circles require an actual backtest fill. This chart does not change the live/replay workspace.</p>
    <div class="indicator-toolbar"><label><input type="checkbox" aria-label="Show Backtest Crossover Signals" v-model="chartSignals"> Show Crossover Signals</label><label><input type="checkbox" aria-label="Show Backtest Fills" v-model="chartFills"> Show Simulated Fills</label></div>
    <MarketChart :candles="chartData.candles" :symbol="chartData.symbol" :interval="chartData.interval" :context="`backtest:${chartData.id}`" :indicators="chartData.indicators" :strategy-fills="chartData.fills" :show-signals="chartSignals" :show-fills="chartFills" />
  </section>
  <div class="paper-balances">
   <div><span>Starting equity</span><strong>{{currency(result.summary.starting_equity)}}</strong></div>
   <div><span>Ending equity</span><strong>{{currency(result.summary.ending_equity)}}</strong></div>
   <div><span>Total return</span><strong>{{percent(result.summary.total_return_percent)}}</strong></div>
   <div><span>Realized P/L</span><strong>{{currency(result.summary.realized_pl)}}</strong></div>
   <div><span>Unrealized P/L</span><strong>{{currency(result.summary.unrealized_pl)}}</strong></div>
   <div><span>Completed round trips / fills</span><strong>{{result.summary.completed_trades}} / {{result.summary.fill_count}}</strong></div>
   <div><span>Win rate (closed trades)</span><strong>{{percent(result.summary.win_rate_percent)}}</strong></div>
   <div><span>Maximum drawdown</span><strong>{{percent(result.summary.max_drawdown_percent)}}</strong></div>
  </div>
  <figure class="backtest-curve"><figcaption>Equity at recorded open / completion events · USD · {{currency(bounds.low)}}–{{currency(bounds.high)}}</figcaption><svg viewBox="0 0 800 145" role="img" aria-label="Backtest equity curve"><polyline :points="points" fill="none" stroke="var(--accent, #42d6ae)" stroke-width="2"/></svg><div class="backtest-axis"><small>{{curve[0]?.timestamp}}</small><small>{{curve.at(-1)?.timestamp}}</small></div></figure>
  <p class="muted">Excluded incomplete rows: {{result.quality.incomplete_rows_excluded}} · later completed versions: {{result.quality.later_completed_versions_excluded}} · missing interval slots: {{result.quality.missing_interval_slots}} (may include market closures). No warm-up before start.</p>
  <p v-if="!result.summary.completed_trades">No completed round trips in this range. Open positions remain marked, not forcibly liquidated.</p>
  <details v-remember-panel="'backtest-fills'"><summary>Simulated fill history ({{result.fills.length}})</summary><div class="paper-table-wrap"><table class="paper-table"><thead><tr><th>Execution UTC</th><th>Side</th><th>Shares</th><th>Open price</th><th>Signal candle → execution candle</th></tr></thead><tbody><tr v-for="(fill,i) in result.fills" :key="i"><td>{{fill.timestamp}}</td><td>{{fill.side}}</td><td>{{fill.quantity}}</td><td>{{currency(fill.price)}}</td><td>#{{fill.signal_candle_id}} → #{{fill.candle_id}}</td></tr></tbody></table></div></details>
  <details v-remember-panel="'backtest-trades'"><summary>Completed trade history ({{result.trades.length}})</summary><div class="paper-table-wrap"><table class="paper-table"><thead><tr><th>Entry UTC</th><th>Exit UTC</th><th>Shares</th><th>Entry / exit</th><th>Realized P/L</th></tr></thead><tbody><tr v-for="(trade,i) in result.trades" :key="i"><td>{{trade.entry_timestamp}}</td><td>{{trade.exit_timestamp}}</td><td>{{trade.quantity}}</td><td>{{currency(trade.entry_price)}} / {{currency(trade.exit_price)}}</td><td>{{currency(trade.realized_pl)}}</td></tr></tbody></table></div></details>
  <p class="muted">Unfilled final signals: {{result.decisions.filter(d=>d.status==='unfilled').length}} · Input fingerprint {{result.input_hash}}</p>
 </div>
 <p class="paper-notice">Execution: next eligible completed candle open after confirmation availability; whole shares, 20% cash allocation, long-only, zero commissions/slippage. First completed revision only. Missing candles are never synthesized. No liquidity/spread/market impact model. Historical results do not guarantee future returns; gaps, survivorship bias and parameter overfitting can distort results.</p>
</CollapsiblePanel>
</template>
