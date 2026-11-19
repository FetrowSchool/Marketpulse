// All SMA arithmetic lives in FastAPI, including replay's arrived-only candle snapshot.
export function createIndicators({onChange=()=>{},onState=()=>{},fetcher=globalThis.fetch}={}) {
  let timer,controller,version=0,lastKey='',context='',disposed=false,pending
  const empty={points:[],signals:[],latest:null}
  function load(rows,symbol,interval,selectionContext) {
    const key=JSON.stringify([selectionContext,symbol,interval,rows.map(r=>[r.id,r.revision,r.candle_complete,r.close])])
    if (disposed || key===lastKey) return
    lastKey=key;version+=1
    const nextContext=`${selectionContext}:${symbol}:${interval}`
    // Never leave old confirmed markers on a new revision or selection while recalculating.
    onChange(empty);onState({loading:true,error:''})
    if(context!==nextContext){controller?.abort();clearTimeout(timer);timer=undefined;context=nextContext}
    pending={rows,symbol,interval,version}
    if(!timer)timer=setTimeout(run,100)
  }
  async function run() {
    timer=undefined
    const current=pending
    controller?.abort();controller=new AbortController()
    const ownController=controller
    const timeout=setTimeout(()=>ownController.abort(),10000)
    try {
      const candles=current.rows.map(row=>Object.fromEntries(['id','symbol','data_source','data_mode','observation_type',
        'source_observation_id','candle_interval','candle_open_timestamp','source_timestamp','received_timestamp',
        'revision','candle_complete','close'].map(key=>[key,row[key]])))
      const response=await fetcher('/api/indicators/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},
        signal:ownController.signal,body:JSON.stringify({symbol:current.symbol,interval:current.interval,candles})})
      if(!response.ok)throw new Error('Indicator calculation unavailable')
      const data=await response.json()
      if(disposed || current.version!==version)return
      if(data.symbol!==current.symbol || data.interval!==current.interval || !Array.isArray(data.points) || !Array.isArray(data.signals))throw new Error('Invalid indicator response')
      onChange(data);onState({loading:false,error:''})
    } catch {
      if(!disposed && current.version===version)onState({loading:false,error:'Indicators unavailable. Candles and replay remain available.'})
    } finally {clearTimeout(timeout)}
  }
  return {load,dispose(){disposed=true;version+=1;clearTimeout(timer);controller?.abort()}}
}
