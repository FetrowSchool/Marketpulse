<script setup>
import {vRememberPanel} from '../services/panelPreferences.js'
import CollapsiblePanel from './CollapsiblePanel.vue'
import {ref,computed,onMounted,onUnmounted,watch} from 'vue'
const props=defineProps({symbol:{type:String,default:'AAPL'},latestPrice:{default:null},replay:Boolean,docked:Boolean,feedStatus:{type:String,default:'unknown'},sourceTime:{type:String,default:''}})
const account=ref(null),orders=ref([]),fills=ref([]),error=ref(''),notice=ref(''),loading=ref(false),busy=ref(false)
const selectedPosition=computed(()=>account.value?.positions.find(p=>p.symbol===props.symbol))
const estimate=computed(()=>{const amount=Number(price.value)*Number(quantity.value);return price.value && Number(price.value)>0 && Number.isFinite(amount) && amount>0?amount:null})
const side=ref('BUY'),quantity=ref(1),price=ref(''),immediate=ref(true)
let controller,timer,generation=0,disposed=false,pendingRequest
function dollars(value){return value===null || value===undefined ? 'Unavailable' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(value))}
async function request(url,options={}) {
  const response=await fetch('/api/paper/'+url,options)
  const data=await response.json()
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check symbol, whole-share quantity and execution price.')
  return data
}
async function refresh() {
  const current=++generation
  controller?.abort();controller=new AbortController()
  const own=controller,timeout=setTimeout(()=>own.abort(),10000)
  loading.value=true
  try{
    const [summary,orderData,fillData]=await Promise.all([
      request('account',{signal:own.signal}),request('orders',{signal:own.signal}),request('fills',{signal:own.signal})])
    if(disposed || current!==generation)return
    if(summary.mode!=='SIMULATED' || typeof summary.cash!=='string' || !Array.isArray(summary.positions) || !Array.isArray(summary.unpriced_symbols) || !Array.isArray(orderData.orders) || !Array.isArray(fillData.fills))throw new Error('Invalid simulated account response')
    account.value=summary;orders.value=orderData.orders;fills.value=fillData.fills;error.value=''
  }catch(e){if(!disposed && current===generation)error.value=e.message || 'Simulated account unavailable'}
  finally{clearTimeout(timeout);if(!disposed && current===generation)loading.value=false}
}
async function mutation(url,body) {
  if(busy.value)return
  busy.value=true;error.value='';notice.value=''
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),10000)
  try{
    const data=await request(url,{method:'POST',headers:{'Content-Type':'application/json'},signal:abort.signal,...(body?{body:JSON.stringify(body)}:{})})
    if(disposed)return
    notice.value=`SIMULATED order #${data.id}: ${data.status}${data.rejection_reason?' · '+data.rejection_reason.replaceAll('_',' '):''}`
    if(url==='orders')pendingRequest=undefined
    await refresh()
  }catch(e){if(!disposed)error.value=e.message || 'Order request unavailable. Retry uses the same order identity.'}
  finally{clearTimeout(timeout);if(!disposed)busy.value=false}
}
function submit(){
  if(props.replay)return
  const values={symbol:props.symbol,side:side.value,quantity:quantity.value,execution_price:String(price.value),execute_immediately:immediate.value}
  const key=JSON.stringify(values)
  if(!pendingRequest || pendingRequest.key!==key)pendingRequest={key,body:{client_order_id:crypto.randomUUID(),...values}}
  return mutation('orders',pendingRequest.body)
}
function useDisplayedPrice(){if(!props.replay && Number.isFinite(props.latestPrice))price.value=props.latestPrice.toFixed(6)}
watch(()=>props.symbol,()=>{price.value='';pendingRequest=undefined;notice.value=''})
onMounted(()=>{refresh();timer=setInterval(refresh,15000)})
onUnmounted(()=>{disposed=true;generation++;controller?.abort();clearInterval(timer)})
</script>

<template>
  <CollapsiblePanel class="panel paper-panel paper-ticket" storage-key="paper-ticket" :class="{docked}" :title="`Simulated account · ${symbol}`" :subtitle="account ? `Cash ${dollars(account.cash)}` : 'Loading account'" aria-labelledby="paper-title">
    <div class="paper-heading"><div><p class="eyebrow">PAPER TRADING · SIMULATED · USD</p><h2 id="paper-title">Simulated account</h2><p class="muted">Whole shares · zero fees/slippage · no real brokerage</p></div><button @click="refresh" :disabled="loading">Refresh account</button></div>
    <p v-if="error" role="alert" class="history-error">{{ error }}</p><p v-if="notice" role="status" class="paper-notice">{{ notice }}</p>
    <div v-if="account" class="paper-balances">
      <div v-for="[label,key] in [['Available cash','cash'],['Account equity','equity'],['Unrealized P/L','unrealized_pl'],['Realized P/L','realized_pl'],['Starting balance','starting_cash']]" :key="key"><span>{{label}}</span><strong :data-testid="`paper-${key}`">{{dollars(account[key])}}</strong></div>
    </div>
    <p v-else class="muted">{{loading?'Loading simulated account…':'Simulated account unavailable'}}</p>
    <p v-if="account && !account.valuation_complete" class="history-error">Equity unavailable: no valid saved quote for {{account.unpriced_symbols.join(', ')}}. Cash and cost basis remain exact.</p>
    <div v-if="docked" class="ticket-market">
      <div><span>{{symbol}} · displayed reference</span><strong>{{dollars(latestPrice)}}</strong></div>
      <small>Feed: {{feedStatus.replaceAll('_',' ')}} · {{sourceTime || 'No source timestamp'}}</small>
      <p>Your position: <b>{{selectedPosition?.quantity ?? 0}} shares</b> <span v-if="selectedPosition">(manual {{selectedPosition.manual_quantity ?? selectedPosition.quantity}} · strategy {{selectedPosition.strategy_quantity ?? 0}})</span></p>
    </div>
    <p v-if="replay" class="paper-notice">Replay active: manual order submission and execution are disabled. This account is not replayed or reset.</p>
    <form class="paper-order" aria-label="Manual simulated order" @submit.prevent="submit">
      <strong>Manual SIMULATED order · {{symbol}}</strong>
      <label>Side<select aria-label="Paper order side" v-model="side" :disabled="busy || replay"><option>BUY</option><option>SELL</option></select></label>
      <label>Whole shares<input aria-label="Paper order quantity" type="number" min="1" max="1000000" step="1" required v-model.number="quantity" :disabled="busy || replay"></label>
      <label>Reference price · USD<input aria-label="Paper execution price" type="number" min="0.000001" max="1000000" step="0.000001" required v-model="price" :disabled="busy || replay"></label>
      <button type="button" @click="useDisplayedPrice" :disabled="busy || replay || !Number.isFinite(latestPrice)">Use displayed price</button>
      <label class="follow-control"><input type="checkbox" v-model="immediate" :disabled="busy || replay"> Fill immediately</label>
      <button type="submit" :disabled="busy || replay">{{busy?'Submitting…':'Submit paper order'}}</button>
    </form>
    <p v-if="estimate !== null" class="ticket-estimate">Estimated {{side === 'BUY' ? 'cost' : 'proceeds'}} <strong>{{dollars(estimate)}}</strong><small>Reference-price estimate · backend validates the order</small></p>
    <details class="paper-assumptions" v-remember-panel="'paper-assumptions'"><summary>Pricing &amp; execution assumptions</summary><p class="muted">You choose the simulated reference price (six decimal places; displayed prices are rounded when copied); it is not a market execution guarantee. Pending orders reserve no funds/shares and execute later at their fixed reference price only after a manual Fill action. Position values use last saved quotes, which may be delayed or stale. Recorded timestamps and age are shown below. The account is independent of replay.</p></details>
  </CollapsiblePanel>
  <CollapsiblePanel class="panel paper-panel paper-ledger" storage-key="paper-ledger" :class="{docked}" title="Positions & execution history" aria-label="Simulated positions and activity">
    <div class="paper-heading"><div><p class="eyebrow">SIMULATED ACCOUNT ACTIVITY</p><h2>Positions &amp; execution history</h2></div><a class="ticket-link" href="#paper-title">Back to order ticket ↑</a></div>
    <details class="ledger-section" open v-remember-panel="'positions'"><summary>Open positions</summary><div class="paper-table"><table><thead><tr><th>Symbol</th><th>Shares</th><th>Avg entry</th><th>Cost basis</th><th>Saved price</th><th>Market value</th><th>Unrealized P/L</th><th>Quote · UTC / age / mode</th></tr></thead><tbody><tr v-for="p in account?.positions || []" :key="p.symbol"><td>{{p.symbol}}</td><td>{{p.quantity}}<br><small>Manual {{p.manual_quantity ?? p.quantity}} · strategy {{p.strategy_quantity ?? 0}}</small></td><td :title="p.average_entry_price">{{dollars(p.average_entry_price)}}</td><td>{{dollars(p.cost_basis)}}</td><td>{{dollars(p.current_price)}}</td><td>{{dollars(p.market_value)}}</td><td>{{dollars(p.unrealized_pl)}}</td><td>{{p.mark?`${p.mark.source_timestamp} · ${p.mark.source_age_seconds.toFixed(1)}s · ${p.mark.data_mode}`:'Unavailable'}}</td></tr><tr v-if="!account?.positions?.length"><td colspan="8">No open simulated positions</td></tr></tbody></table></div></details>
    <details class="ledger-section" open v-remember-panel="'orders'"><summary>Order history · latest 100</summary><div class="paper-table"><table><thead><tr><th>Order</th><th>Symbol</th><th>Side</th><th>Shares</th><th>Reference</th><th>Status</th><th>Created · UTC</th><th>Manual action</th></tr></thead><tbody><tr v-for="o in orders" :key="o.id"><td>#{{o.id}}</td><td>{{o.symbol}}</td><td>{{o.side}}</td><td>{{o.quantity}}</td><td>{{dollars(o.execution_reference_price)}}</td><td>{{o.status}} {{o.rejection_reason?.replaceAll('_',' ')}}</td><td>{{o.created_timestamp}}</td><td><template v-if="o.status==='pending'"><button :disabled="busy || replay" @click="mutation(`orders/${o.id}/execute`)">Fill #{{o.id}}</button> <button :disabled="busy" @click="mutation(`orders/${o.id}/cancel`)">Cancel #{{o.id}}</button></template></td></tr><tr v-if="!orders.length"><td colspan="8">No simulated orders</td></tr></tbody></table></div></details>
    <details class="ledger-section" open v-remember-panel="'fills'"><summary>Fill / trade history · latest 100</summary><div class="paper-table"><table><thead><tr><th>Fill / order</th><th>Symbol / side</th><th>Shares</th><th>Fill price</th><th>Fees</th><th>Slippage</th><th>Execution source</th><th>Realized P/L</th><th>Executed · UTC</th></tr></thead><tbody><tr v-for="f in fills" :key="f.id"><td>#{{f.id}} / #{{f.order_id}}</td><td>{{f.symbol}} {{f.side}}</td><td>{{f.quantity}}</td><td>{{dollars(f.execution_price)}}</td><td>{{dollars(f.fees)}}</td><td>{{f.slippage_bps}} bps</td><td>{{f.price_source}}<template v-if="f.execution_observation_id"> · observation #{{f.execution_observation_id}}</template></td><td>{{dollars(f.realized_pl)}}</td><td>{{f.execution_timestamp}}</td></tr><tr v-if="!fills.length"><td colspan="9">No simulated fills</td></tr></tbody></table></div></details>
  </CollapsiblePanel>
</template>
