import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { candle } from './chartFixture.js'
const mocks = vi.hoisted(() => ({ apply: vi.fn(), fit: vi.fn(), remove: vi.fn() }))
vi.mock('../src/services/chartRenderer.js', () => ({ createChartRenderer: () => mocks }))
import MarketChart from '../src/components/MarketChart.vue'
let wrapper
afterEach(() => { wrapper?.unmount(); vi.clearAllMocks() })
describe('reusable chart component', () => {
  it('renders unavailable volume honestly and forwards revisions to the renderer', async () => {
    wrapper = mount(MarketChart, { props: { symbol: 'AAPL', interval: '1m', candles: [candle()] } })
    expect(wrapper.text()).toContain('Volume unavailable')
    expect(wrapper.find('a').attributes('href')).toBe('https://www.tradingview.com/')
    await wrapper.setProps({ candles: [candle({ id: 3, revision: 2, candle_complete: true })] })
    expect(mocks.apply).toHaveBeenLastCalledWith(expect.arrayContaining([expect.objectContaining({ revision: 2 })]), 'AAPL:1m', { loading: false })
    wrapper.unmount()
    expect(mocks.remove).toHaveBeenCalledOnce()
    wrapper = undefined
  })
  it('reports only reliable supplied volume and keeps an honest empty state', async () => {
    wrapper = mount(MarketChart, { props: { symbol: 'MSFT', interval: '5m', candles: [], loading: true } })
    expect(wrapper.text()).toContain('Loading saved candles')
    await wrapper.setProps({ loading: false })
    expect(wrapper.text()).toContain('No saved candles')
    await wrapper.setProps({ candles: [candle({ volume: 42, metadata: { volume_reliable: true } })] })
    expect(wrapper.text()).toContain('Only reliable interval volume')
  })
})

it('passes automatic zoom and follow settings to the renderer', async () => {
  mocks.focus=vi.fn()
  wrapper=mount(MarketChart,{props:{symbol:'AAPL',interval:'1m',candles:[candle()],visibleCandles:25,followLatest:true}})
  expect(mocks.focus).toHaveBeenLastCalledWith(25,true)
  await wrapper.setProps({visibleCandles:10,followLatest:false})
  expect(mocks.focus).toHaveBeenLastCalledWith(10,false)
  delete mocks.focus
})
