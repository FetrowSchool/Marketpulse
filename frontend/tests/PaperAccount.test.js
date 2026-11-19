import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import PaperAccount from '../src/components/PaperAccount.vue'
let wrapper
const summary={mode:'SIMULATED',cash:'10000.000000',starting_cash:'10000.000000',equity:'10000.000000',realized_pl:'0.000000',unrealized_pl:'0.000000',positions:[],unpriced_symbols:[],valuation_complete:true}
beforeEach(()=>{
 vi.stubGlobal('fetch',vi.fn(async(url,options={})=>({ok:true,json:async()=>options.method==='POST'?{id:1,status:'filled'}:url.endsWith('/account')?summary:url.endsWith('/orders')?{orders:[]}:{fills:[]}})))
})
afterEach(()=>{wrapper?.unmount();vi.unstubAllGlobals()})
it('renders a simulated account and submits explicit manual paper orders',async()=>{
 wrapper=mount(PaperAccount,{props:{symbol:'AAPL',latestPrice:100}})
 await flushPromises()
 expect(wrapper.get('[data-testid="paper-cash"]').text()).toBe('$10,000.00')
 expect(wrapper.text()).toContain('SIMULATED')
 await wrapper.get('button[type="button"]').trigger('click')
 await wrapper.get('input[aria-label="Paper order quantity"]').setValue('2')
 await wrapper.get('form').trigger('submit')
 await flushPromises()
 const submission=fetch.mock.calls.find(([url,options])=>url.endsWith('/orders')&&options.method==='POST')
 expect(JSON.parse(submission[1].body)).toMatchObject({symbol:'AAPL',side:'BUY',quantity:2,execution_price:'100.000000',execute_immediately:true})
 expect(wrapper.text()).toContain('SIMULATED order #1: filled')
 await wrapper.setProps({replay:true})
 expect(wrapper.get('button[type="submit"]').element.disabled).toBe(true)
 expect(wrapper.text()).toContain('This account is not replayed or reset')
})
it('reuses the order identity after a lost response and exposes failures',async()=>{
 const original=globalThis.fetch,keys=[]
 vi.stubGlobal('fetch',vi.fn(async(url,options={})=>{
  if(options.method==='POST'){keys.push(JSON.parse(options.body).client_order_id);throw new Error('Connection lost')}
  return original(url,options)
 }))
 wrapper=mount(PaperAccount,{props:{symbol:'MSFT'}});await flushPromises()
 await wrapper.get('input[aria-label="Paper execution price"]').setValue('50')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(wrapper.get('[role="alert"]').text()).toContain('Connection lost')
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(keys).toHaveLength(2);expect(keys[0]).toBe(keys[1])
})
it('reports missing valuation without inventing an equity value',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url)=>({ok:true,json:async()=>url.endsWith('/account')?{...summary,equity:null,unrealized_pl:null,valuation_complete:false,unpriced_symbols:['AAPL']}:url.endsWith('/orders')?{orders:[]}:{fills:[]}})))
 wrapper=mount(PaperAccount);await flushPromises()
 expect(wrapper.get('[data-testid="paper-equity"]').text()).toBe('Unavailable')
 expect(wrapper.text()).toContain('no valid saved quote for AAPL')
})
it('keeps selected-symbol position and order estimate beside the chart without automatic orders',async()=>{
 const position={symbol:'AAPL',quantity:5,manual_quantity:3,strategy_quantity:2,average_entry_price:'100',cost_basis:'500',current_price:'125',market_value:'625',unrealized_pl:'125',mark:null}
 vi.stubGlobal('fetch',vi.fn(async(url)=>({ok:true,json:async()=>url.endsWith('/account')?{...summary,positions:[position]}:url.endsWith('/orders')?{orders:[]}:{fills:[]}})))
 wrapper=mount(PaperAccount,{props:{docked:true,symbol:'AAPL',latestPrice:125,feedStatus:'real_time_unverified',sourceTime:'2026-01-06T15:00:00Z'}})
 await flushPromises()
 expect(wrapper.get('.ticket-market').text()).toContain('5 shares')
 expect(wrapper.get('.ticket-market').text()).toContain('manual 3 · strategy 2')
 expect(wrapper.get('.ticket-market').text()).toContain('real time unverified')
 await wrapper.get('button[type="button"]').trigger('click')
 await wrapper.get('[aria-label="Paper order quantity"]').setValue('2')
 expect(wrapper.get('.ticket-estimate').text()).toContain('$250.00')
 const ticket=wrapper.get('.paper-ticket')
 ticket.element.open=false;await ticket.trigger('toggle')
 await wrapper.get('button').trigger('click');await flushPromises()
 expect(ticket.element.open).toBe(false)
 expect(wrapper.get('[aria-label="Paper execution price"]').element.value).toBe('125.000000')
 expect(wrapper.get('[aria-label="Paper order quantity"]').element.value).toBe('2')
 ticket.element.open=true;await ticket.trigger('toggle')
 await wrapper.setProps({symbol:'MSFT',latestPrice:320})
 expect(wrapper.get('[aria-label="Paper execution price"]').element.value).toBe('')
 expect(wrapper.get('.ticket-market').text()).toContain('0 shares')
 expect(wrapper.find('.ticket-estimate').exists()).toBe(false)
 expect(fetch.mock.calls.every(([,options])=>!options || options.method!=='POST')).toBe(true)
 await wrapper.setProps({replay:true})
 expect(wrapper.get('button[type="submit"]').element.disabled).toBe(true)
})
