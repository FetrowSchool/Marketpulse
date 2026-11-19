// Presentation of backend-confirmed records only. No SMA/crossover calculation here.
export function chartTime(timestamp){
 const value=Date.parse(timestamp)/1000
 return typeof timestamp==='string' && timestamp.endsWith('Z') && Number.isFinite(value)?Math.floor(value):null
}
const rank=row=>[Number(row.revision)||0,Number(row.id)||0]
function newer(a,b){const x=rank(a),y=rank(b);return x[0]>y[0] || (x[0]===y[0] && x[1]>y[1])}
export function chartPoints(data,candles,symbol,interval){
 const bars=new Map(candles.filter(c=>c.symbol===symbol&&c.candle_interval===interval).map(c=>[chartTime(c.candle_open_timestamp),c]))
 const points=new Map()
 for(const point of data?.points||[]){
  const bar=bars.get(chartTime(point.candle_open_timestamp))
  if(!bar || point.symbol!==symbol || point.candle_interval!==interval || chartTime(point.candle_open_timestamp)===null)continue
  if(point.id!==bar.id || point.revision!==bar.revision)continue
  if(point.data_source!==bar.data_source || point.data_mode!==bar.data_mode || point.observation_type!==bar.observation_type)continue
  const time=chartTime(point.candle_open_timestamp)
  if(!points.has(time)||newer(point,points.get(time)))points.set(time,point)
 }
 return [...points.values()].sort((a,b)=>chartTime(a.candle_open_timestamp)-chartTime(b.candle_open_timestamp))
}
export function confirmedChartSignals(data,candles,symbol,interval){
 const bars=new Map(candles.map(c=>[chartTime(c.candle_open_timestamp),c]))
 const points=chartPoints({...data,points:data?.signals||[]},candles,symbol,interval)
 const ids=new Set()
 return points.filter(point=>{
  if(point.confirmed!==true || point.candle_complete!==true || bars.get(chartTime(point.candle_open_timestamp))?.candle_complete!==true || !['BUY','SELL'].includes(point.signal) || typeof point.signal_id!=='string' || !point.signal_id || ids.has(point.signal_id))return false
  ids.add(point.signal_id);return true
 })
}
export function scopedFills(fills,symbol,interval){
 const ids=new Set()
 return (fills||[]).filter(fill=>{
  const id=fill.marker_id || (Number.isInteger(fill.id)&&fill.id>0?`paper-fill:${fill.id}`:null)
  if(!id || ids.has(id) || fill.symbol!==symbol || fill.interval!==interval || !['BUY','SELL'].includes(fill.side) || !Number.isInteger(fill.quantity) || fill.quantity<=0 || chartTime(fill.source_timestamp)===null)return false
  ids.add(id);return true
 })
}
export function signalFills(signal,fills,symbol,interval){
 if(!signal)return []
 return scopedFills(fills,symbol,interval).filter(fill=>fill.signal_id===signal.signal_id || (chartTime(fill.signal_candle_open_timestamp)===chartTime(signal.candle_open_timestamp) && fill.signal_direction===signal.signal))
}
