<script setup>
import CollapsiblePanel from './CollapsiblePanel.vue'
import {ref,onMounted,onUnmounted,watch} from 'vue'
const props=defineProps({symbol:{type:String,required:true},interval:{type:String,required:true},replay:Boolean})
const emit=defineEmits(['fills'])
const status=ref(null),error=ref(''),busy=ref(false)
let timer,controller,version=0,disposed=false
function currency(value){return value==null?'Unavailable':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(value))}
function readable(value){return value?value.replaceAll('_',' '):'None'}
async function json(url,options={}){
 const response=await fetch(url,options);const data=await response.json()
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Strategy request failed')
 return data
}
async function refresh(){
 const current=++version
 controller?.abort();controller=new AbortController()
 const own=controller,timeout=setTimeout(()=>own.abort(),10000)
 try{
  const query=new URLSearchParams({symbol:props.symbol,interval:props.interval})
  const [data,fillData]=await Promise.all([json('/api/strategy/status',{signal:own.signal}),json('/api/strategy/fills?'+query,{signal:own.signal})])
  if(disposed || current!==version)return
  if(data.mode!=='SIMULATED' || typeof data.enabled!=='boolean' || !Array.isArray(fillData.fills))throw new Error('Invalid strategy response')
  status.value=data;emit('fills',fillData.fills);error.value=''
 }catch(e){if(!disposed && current===version){error.value=e.message;emit('fills',[])}}
 finally{clearTimeout(timeout)}
}
async function toggle(){
 if(props.replay || busy.value)return
 busy.value=true;error.value=''
 const own=new AbortController(),timeout=setTimeout(()=>own.abort(),10000)
 try{
  const body=status.value?.enabled?{enabled:false}:{enabled:true,symbol:props.symbol,interval:props.interval}
  const data=await json('/api/strategy/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:own.signal})
  if(!disposed){status.value=data;await refresh()}
 }catch(e){if(!disposed)error.value=e.message}
 finally{clearTimeout(timeout);if(!disposed)busy.value=false}
}
watch(()=>[props.symbol,props.interval],()=>{emit('fills',[]);refresh()})
onMounted(()=>{refresh();timer=setInterval(refresh,5000)})
onUnmounted(()=>{disposed=true;version++;clearInterval(timer);controller?.abort()})
</script>

<template>
 <CollapsiblePanel class="panel paper-panel" storage-key="strategy" title="SMA crossover strategy" :subtitle="status?.enabled ? 'Automatic simulation ON · hiding does not disable trading' : 'Automatic simulation OFF'" aria-labelledby="strategy-title">
  <div class="paper-heading"><div><p class="eyebrow">AUTOMATIC PAPER TRADING · SIMULATED ONLY</p><h2 id="strategy-title">SMA(20) / SMA(50) crossover strategy</h2><p class="muted">BUY: up to20% of cash, whole shares · SELL: this strategy's entire holding · zero fees/slippage</p></div><button aria-label="Toggle automatic simulated trading" :disabled="busy || replay || !status" @click="toggle">{{busy?'Updating…':status?.enabled?'Disable automatic simulation':'Enable automatic simulation'}}</button></div>
  <p v-if="error" class="history-error" role="alert">{{error}}</p>
  <p v-if="status?.error" class="history-error" role="alert">Automatic simulation suspended: {{status.error}}</p>
  <p v-if="replay" class="paper-notice">Replay never submits strategy orders. If enabled, the independent live strategy may still act on new provider observations. Controls and fill markers are disabled here.</p>
  <div class="paper-balances" v-if="status">
   <div><span>Automatic SIMULATED trading</span><strong data-testid="strategy-enabled">{{status.enabled?'ON':'OFF'}} · {{status.state}}</strong></div>
   <div><span>Configured symbol / interval</span><strong>{{status.configuration.symbol}} · {{status.configuration.interval}}</strong></div>
   <div><span>Current account cash</span><strong>{{currency(status.account.cash)}}</strong></div>
   <div><span>Last-known account equity</span><strong>{{currency(status.account.equity)}}</strong></div>
   <div><span>Strategy-owned shares</span><strong>{{status.managed_positions.reduce((sum,p)=>sum+p.quantity,0)}}</strong></div>
  </div>
  <div class="strategy-details" v-if="status">
   <p><b>Strategy status reason:</b> {{readable(status.reason)}}</p>
   <p><b>Last confirmed signal:</b> {{status.last_signal?`${status.last_signal.direction} · ${status.last_signal.symbol} ${status.last_signal.interval} · candle ${status.last_signal.candle_open_timestamp}`:'None since activation'}}<br><span class="muted" v-if="status.last_signal">SMA20 {{status.last_signal.sma20}} / SMA50 {{status.last_signal.sma50}} · available {{status.last_signal.confirmed_timestamp}}</span></p>
   <p><b>Latest decision:</b> {{readable(status.last_decision?.status)}} · {{readable(status.last_decision?.reason)}}</p>
   <p><b>Last simulated action:</b> {{readable(status.last_action?.status)}} · {{readable(status.last_action?.reason)}}<br><span v-if="status.last_action">Quantity {{status.last_action.quantity}} · observed price {{currency(status.last_action.execution_price)}} · observation #{{status.last_action.execution_observation_id ?? '—'}} · order #{{status.last_action.order_id ?? '—'}} · fill #{{status.last_action.fill_id ?? '—'}}</span></p>
   <p v-if="status.last_action?.account_state"><b>Account after that action:</b> cash {{currency(status.last_action.account_state.cash)}} · {{status.last_action.account_state.symbol}} shares {{status.last_action.account_state.quantity}} · realized P/L {{currency(status.last_action.account_state.realized_pl)}}</p>
  </div>
  <p class="muted">Default OFF. Enabling starts with future completed candles; it does not trade saved crossings. Execution waits for a later fresh observed price. Disabling cancels waiting signals but does not liquidate holdings. Manual shares are protected.</p>
  <p class="muted"><span class="sma-fast">Arrow BUY/SELL = analytical crossover</span> · <span class="strategy-fill-color">Circle FILL BUY/SELL = actual paper fill</span> · Backtests use separate accounts · No real brokerage.</p>
 </CollapsiblePanel>
</template>
