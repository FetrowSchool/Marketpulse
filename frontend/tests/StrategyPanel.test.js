import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import StrategyPanel from '../src/components/StrategyPanel.vue'
let wrapper
const state={mode:'SIMULATED',enabled:false,state:'disabled',configuration:{symbol:'AAPL',interval:'1m'},account:{cash:'10000',equity:'10000'},managed_positions:[],last_signal:null,last_decision:null,last_action:null}
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async(url,options={})=>({ok:true,json:async()=>url.includes('/fills?')?{fills:[]}:{...state,...(options.method==='POST'?{enabled:JSON.parse(options.body).enabled}: {})}}))))
afterEach(()=>{wrapper?.unmount();vi.unstubAllGlobals()})
it('defaults to OFF and enables only through an explicit simulated action',async()=>{
 wrapper=mount(StrategyPanel,{props:{symbol:'AAPL',interval:'5m'}});await flushPromises()
 expect(wrapper.get('[data-testid="strategy-enabled"]').text()).toContain('OFF')
 expect(fetch.mock.calls.every(([,options])=>options.method!=='POST')).toBe(true)
 await wrapper.get('button').trigger('click');await flushPromises()
 const action=fetch.mock.calls.find(([,options])=>options.method==='POST')
 expect(JSON.parse(action[1].body)).toEqual({enabled:true,symbol:'AAPL',interval:'5m'})
 await wrapper.setProps({replay:true})
 expect(wrapper.get('button').element.disabled).toBe(true)
 expect(wrapper.text()).toContain('Replay never submits strategy orders')
})
it('shows persisted signal, decision, execution source and account result',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url)=>({ok:true,json:async()=>url.includes('/fills?')?{fills:[]}:{...state,
  last_signal:{direction:'BUY',symbol:'AAPL',interval:'1m',candle_open_timestamp:'2026-01-06T15:50:00Z',sma20:101,sma50:100.4},
  last_decision:{status:'executed',reason:'first_eligible_observed_price'},
  last_action:{status:'executed',reason:'first_eligible_observed_price',quantity:16,execution_price:'125',execution_observation_id:103,order_id:1,fill_id:1,account_state:{cash:'8000',symbol:'AAPL',quantity:16,realized_pl:'0'}}}})))
 wrapper=mount(StrategyPanel,{props:{symbol:'AAPL',interval:'1m'}});await flushPromises()
 expect(wrapper.text()).toContain('observation #103')
 expect(wrapper.text()).toContain('$8,000.00')
 expect(wrapper.text()).toContain('Quantity 16')
})
