import {mount,flushPromises} from '@vue/test-utils'
import {afterEach,it,expect,vi} from 'vitest'
import BacktestPanel from '../src/components/BacktestPanel.vue'
let wrapper
const result={id:1,input_hash:'fixture-only',configuration:{symbol:'AAPL',interval:'1m',fast_period:20,slow_period:50,start:'2026-01-01',end:'2026-01-02'},summary:{starting_equity:'10000',ending_equity:'10000',total_return_percent:'0',realized_pl:'0',unrealized_pl:'0',completed_trades:0,fill_count:0,win_rate_percent:null,max_drawdown_percent:'0'},equity_curve:[{timestamp:'2026-01-01',equity:'10000'}],quality:{incomplete_rows_excluded:0,later_completed_versions_excluded:0,missing_interval_slots:0},fills:[],trades:[],decisions:[]}
afterEach(()=>{wrapper?.unmount();vi.unstubAllGlobals()})
async function form(){wrapper=mount(BacktestPanel,{props:{symbol:'AAPL',interval:'5m'}});await wrapper.get('[aria-label="Backtest start date"]').setValue('2026-01-01');await wrapper.get('[aria-label="Backtest end date"]').setValue('2026-01-02')}
it('only submits explicitly and renders zero-trade results and equity curve',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>result})))
 await form();expect(fetch).not.toHaveBeenCalled()
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({symbol:'AAPL',interval:'5m',fast_period:20,slow_period:50,starting_balance:'10000',start:'2026-01-01T00:00:00Z'})
 expect(wrapper.text()).toContain('No completed round trips')
 expect(wrapper.text()).toContain('N/A')
 expect(wrapper.get('[aria-label="Backtest equity curve"] polyline').attributes('points')).not.toContain('NaN')
 expect(wrapper.text()).toContain('no changes to your live paper account')
})
it('shows loading then insufficient-data errors without affecting account endpoints',async()=>{
 let resolve;vi.stubGlobal('fetch',vi.fn(()=>new Promise(r=>{resolve=r})))
 await form();await wrapper.get('form').trigger('submit')
 expect(wrapper.get('button').element.disabled).toBe(true)
 expect(wrapper.text()).toContain('Processing recorded events')
 resolve({ok:false,json:async()=>({detail:'Insufficient completed history: need51, found2'})});await flushPromises()
 expect(wrapper.get('[role="alert"]').text()).toContain('Insufficient')
 expect(wrapper.get('button').element.disabled).toBe(false)
 expect(fetch.mock.calls.every(([url])=>url==='/api/backtests')).toBe(true)
})
it('renders actual completed trades separately from fills',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({...result,summary:{...result.summary,completed_trades:1,fill_count:2},fills:[{side:'BUY',quantity:16,price:'125',timestamp:'2026-01-01',signal_candle_id:51,candle_id:52}],trades:[{quantity:16,entry_price:'125',exit_price:'90',entry_timestamp:'2026-01-01',exit_timestamp:'2026-01-02',realized_pl:'-560'}]})})))
 await form();await wrapper.get('form').trigger('submit');await flushPromises()
 expect(wrapper.text()).toContain('Completed trade history (1)')
 expect(wrapper.text()).toContain('Simulated fill history (1)')
 expect(wrapper.text()).toContain('#51 → #52')
})
it('loads exact saved backtest candles/signals only on request and keeps the saved scope',async()=>{
 const bar={id:1,symbol:'AAPL',data_source:'yahoo_finance',data_mode:'simulated',observation_type:'constructed_candle',source_observation_id:'fixture',revision:1,candle_complete:true,candle_interval:'1m',candle_open_timestamp:'2026-01-01T15:00:00Z',open:100,high:120,low:100,close:120,volume:null}
 const signal={...bar,signal:'BUY',signal_id:'actual-backtest-signal',confirmed:true,sma20:101,sma50:100.4,decision_status:'unfilled'}
 const chart={id:1,mode:'BACKTEST · SIMULATED',symbol:'AAPL',interval:'1m',candles:[bar],indicators:{configuration:{fast_period:20,slow_period:50},points:[signal],signals:[signal]},fills:[]}
 vi.stubGlobal('fetch',vi.fn(async(url)=>({ok:true,json:async()=>url.endsWith('/chart')?chart:result})))
 wrapper=mount(BacktestPanel,{props:{symbol:'AAPL',interval:'1m'},global:{stubs:{MarketChart:true}}})
 await wrapper.get('[aria-label="Backtest start date"]').setValue('2026-01-01');await wrapper.get('[aria-label="Backtest end date"]').setValue('2026-01-02')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(fetch.mock.calls.some(([url])=>url.endsWith('/chart'))).toBe(false)
 await wrapper.setProps({symbol:'MSFT',interval:'5m'})
 await wrapper.get('[aria-label="Show backtest signals on chart"]').trigger('click');await flushPromises()
 const child=wrapper.findComponent({name:'MarketChart'})
 expect(child.props('symbol')).toBe('AAPL');expect(child.props('interval')).toBe('1m')
 expect(child.props('candles')).toEqual(chart.candles)
 expect(child.props('indicators').signals).toEqual(chart.indicators.signals)
 expect(child.props('strategyFills')).toEqual([])
 await wrapper.get('[aria-label="Show Backtest Crossover Signals"]').setValue(false)
 expect(child.props('showSignals')).toBe(false)
 expect(child.props('showFills')).toBe(true)
})
