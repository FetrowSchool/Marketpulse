import {it,expect} from 'vitest'
import {candle,nextCandle} from './chartFixture.js'
import {confirmedChartSignals,chartPoints,scopedFills,signalFills} from '../src/services/chartSignals.js'
const bar=candle({candle_complete:true})
const point=(row=bar,signal='BUY',extra={})=>({...row,signal,signal_id:`signal:${row.id}`,confirmed:true,sma20:101,sma50:100.4,...extra})
it('only accepts completed BUY/SELL backend records on matching candles',()=>{
 const second=nextCandle({candle_complete:true})
 const data={signals:[point(),point(second,'SELL')]}
 expect(confirmedChartSignals(data,[bar,second],'AAPL','1m').map(s=>s.signal)).toEqual(['BUY','SELL'])
 for(const invalid of [point(bar,'HOLD'),point(bar,'BUY',{confirmed:false}),point(bar,'BUY',{candle_complete:false})])expect(confirmedChartSignals({signals:[invalid]},[bar],'AAPL','1m')).toEqual([])
 expect(confirmedChartSignals(data,[{...bar,candle_complete:false}],'AAPL','1m')).toEqual([])
})
it('deduplicates repeated/reloaded signals and rejects stale revisions or other scopes',()=>{
 expect(confirmedChartSignals({signals:[point(),point(),point()]},[bar],'AAPL','1m')).toHaveLength(1)
 const newer={...bar,id:50,revision:2}
 expect(confirmedChartSignals({signals:[point(),point(newer,'SELL')]},[newer],'AAPL','1m').map(s=>s.signal)).toEqual(['SELL'])
 for(const invalid of [point(bar,'BUY',{symbol:'MSFT'}),point(bar,'BUY',{candle_interval:'5m'}),point(bar,'BUY',{data_mode:'recorded'}),point(bar,'BUY',{signal_id:null})])expect(confirmedChartSignals({signals:[invalid]},[bar],'AAPL','1m')).toEqual([])
})
it('aligns timestamps to real historical candles and sorts replay arrivals',()=>{
 const second=nextCandle({candle_complete:true})
 const first=point(bar,'BUY',{candle_open_timestamp:'2026-01-06T15:00:00Z'})
 const data={points:[point(second,'SELL'),first,first],signals:[point(second,'SELL'),first]}
 expect(chartPoints(data,[bar,second],'AAPL','1m').map(s=>s.id)).toEqual([bar.id,second.id])
 expect(confirmedChartSignals(data,[second],'AAPL','1m').map(s=>s.id)).toEqual([second.id])
})
it('associates actual fills by backend signal or exact scoped candle/direction',()=>{
 const fill={id:1,symbol:'AAPL',interval:'1m',side:'BUY',quantity:2,source_timestamp:'2026-01-06T15:01:00.125000Z',signal_candle_open_timestamp:bar.candle_open_timestamp,signal_direction:'BUY'}
 expect(scopedFills([fill,fill,{...fill,id:2,symbol:'MSFT'},{...fill,id:3,interval:'5m'}],'AAPL','1m')).toEqual([fill])
 expect(signalFills(point(),[fill],'AAPL','1m')).toEqual([fill])
 expect(signalFills(point(bar,'SELL'),[fill],'AAPL','1m')).toEqual([])
 expect(scopedFills([{...fill,id:null}],'AAPL','1m')).toEqual([])
})
it('handles large snapshots without duplicate marker identities',()=>{
 const rows=Array.from({length:5000},(_,i)=>candle({id:i+1,candle_complete:true,candle_open_timestamp:new Date(Date.UTC(2026,0,1,0,i)).toISOString()}))
 const signals=rows.map(row=>point(row))
 expect(confirmedChartSignals({signals:[...signals,...signals]},rows,'AAPL','1m')).toHaveLength(5000)
})
