import { describe, expect, it, vi } from 'vitest'
import { createChartRenderer } from '../src/services/chartRenderer.js'
const markerMocks = vi.hoisted(() => ({setMarkers:vi.fn()}))
vi.mock('lightweight-charts', async original => ({...await original(),createSeriesMarkers:()=>markerMocks}))
import { candle, nextCandle } from './chartFixture.js'
function harness(onSignalSelect=vi.fn()) {
  const series = [0, 1, 2, 3].map(() => ({ setData: vi.fn(), update: vi.fn() }))
  const scale = { setVisibleLogicalRange: vi.fn(), fitContent: vi.fn(), getVisibleRange: vi.fn(() => ({ from: 1, to: 2 })), setVisibleRange: vi.fn() }
  const chart = { addSeries: vi.fn().mockReturnValueOnce(series[0]).mockReturnValueOnce(series[1]).mockReturnValueOnce(series[2]).mockReturnValueOnce(series[3]),
    panes: () => [{ setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }],
    subscribeClick:vi.fn(),unsubscribeClick:vi.fn(),subscribeCrosshairMove:vi.fn(),unsubscribeCrosshairMove:vi.fn(),timeScale: () => scale, resize: vi.fn(), remove: vi.fn() }
  const factory = vi.fn(() => chart)
  const container = document.createElement('div')
  Object.defineProperty(container, 'clientWidth', { value: 800 })
  Object.defineProperty(container, 'clientHeight', { value: 500 })
  return { renderer: createChartRenderer(container, factory,{onSignalSelect}),onSignalSelect, factory, chart, series, scale }
}
describe('TradingView renderer adapter', () => {
  it('initializes price and aligned volume panes from saved candles', () => {
    const h = harness()
    h.renderer.apply([candle(), nextCandle({ volume: 50, metadata: { volume_reliable: true } })], 'AAPL:1m')
    expect(h.factory).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ autoSize: false, width: 800, height: 500 }))
    expect(h.chart.addSeries.mock.calls.map(call => call[2])).toEqual([0, 1, 0, 0])
    expect(h.series[0].setData.mock.calls[0][0][0]).toMatchObject({ time: 1767711600, open: 100, close: 102 })
    expect(h.series[1].setData.mock.calls[0][0][0]).toEqual({ time: 1767711600 })
    expect(h.series[1].setData.mock.calls[0][0][1].value).toBe(50)
    expect(h.scale.fitContent).toHaveBeenCalledOnce()
    h.renderer.resize(640, 480)
    expect(h.chart.resize).toHaveBeenCalledWith(640, 480)
    h.renderer.remove()
    expect(h.chart.remove).toHaveBeenCalledOnce()
  })
  it('updates active candles incrementally and completes them without refitting each tick', () => {
    const h = harness()
    h.renderer.apply([candle()], 'AAPL:1m')
    h.renderer.apply([candle({ id: 4, revision: 2, close: 103, candle_complete: true })], 'AAPL:1m')
    expect(h.series[0].update).toHaveBeenLastCalledWith(expect.objectContaining({ close: 103 }), false)
    expect(h.series[0].setData).toHaveBeenCalledOnce()
    expect(h.scale.fitContent).toHaveBeenCalledOnce()
  })
  it('uses historicalUpdate for an existing older candle and resets sorted data for unseen late insertions', () => {
    const h = harness()
    h.renderer.apply([candle(), nextCandle()], 'AAPL:1m')
    const revision = candle({ id: 8, revision: 3, high: 110 })
    h.renderer.apply([revision, nextCandle()], 'AAPL:1m')
    expect(h.series[0].update).toHaveBeenLastCalledWith(expect.objectContaining({ high: 110 }), true)
    expect(h.series[1].setData).toHaveBeenCalledTimes(2) // Safe historical whitespace handling.
    const earlier = candle({ id: 9, source_observation_id: 'earlier', candle_open_timestamp: '2026-01-06T14:59:00.000000Z' })
    h.renderer.apply([earlier, revision, nextCandle()], 'AAPL:1m')
    expect(h.series[0].setData.mock.calls.at(-1)[0].map(row => row.time)).toEqual([1767711540, 1767711600, 1767711660])
    expect(h.scale.setVisibleRange).toHaveBeenCalled()
  })
  it('clears the previous symbol, ignores identical snapshots and waits to fit until history resolves', () => {
    const h = harness()
    h.renderer.apply([candle()], 'AAPL:1m', { loading: true })
    expect(h.scale.fitContent).not.toHaveBeenCalled()
    h.renderer.apply([candle()], 'AAPL:1m')
    expect(h.series[0].update).not.toHaveBeenCalled()
    h.renderer.apply([], 'MSFT:1m')
    expect(h.series[0].setData).toHaveBeenLastCalledWith([])
    expect(h.series[1].setData).toHaveBeenLastCalledWith([])
  })
})

it('zooms to recent candles, follows updates and releases the viewport for manual navigation', () => {
  const h = harness()
  h.renderer.focus(10)
  const rows = Array.from({length:30},(_,i) => candle({id:i+1,candle_open_timestamp:new Date(Date.UTC(2026,0,6,15,i)).toISOString()}))
  h.renderer.apply(rows,'AAPL:1m')
  expect(h.scale.setVisibleLogicalRange).toHaveBeenLastCalledWith({from:19.5,to:31.5})
  const extra=candle({id:31,candle_open_timestamp:'2026-01-06T15:30:00.000000Z'})
  h.renderer.apply([...rows,extra],'AAPL:1m')
  expect(h.scale.setVisibleLogicalRange).toHaveBeenLastCalledWith({from:20.5,to:32.5})
  h.renderer.focus(10,false)
  const calls=h.scale.setVisibleLogicalRange.mock.calls.length
  h.renderer.apply([...rows,{...extra,id:32,revision:2}],'AAPL:1m')
  expect(h.scale.setVisibleLogicalRange).toHaveBeenCalledTimes(calls)
  h.renderer.focus(0,false)
  expect(h.scale.fitContent).toHaveBeenCalled()
  h.renderer.focus(25)
  h.renderer.apply([candle()],'MSFT:5m')
  expect(h.scale.setVisibleLogicalRange).toHaveBeenLastCalledWith({from:-.5,to:2.5})
})

it('renders distinct SMA lines and confirmed markers and clears them when hidden',()=>{
  const h=harness()
  h.renderer.apply([candle({candle_complete:true})],'AAPL:1m')
  const point={...candle({candle_complete:true}),candle_open_timestamp:'2026-01-06T15:00:00Z',sma20:105,sma50:100,signal:'BUY',confirmed:true,signal_id:'stable'}
  h.renderer.indicators({points:[point],signals:[point]})
  expect(h.series[2].setData).toHaveBeenLastCalledWith([{time:1767711600,value:105}])
  expect(h.series[3].setData).toHaveBeenLastCalledWith([{time:1767711600,value:100}])
  expect(markerMocks.setMarkers).toHaveBeenLastCalledWith([expect.objectContaining({id:'stable',shape:'arrowUp',text:'BUY'})])
  h.renderer.indicators({points:[point],signals:[point]},false)
  expect(h.series[2].setData).toHaveBeenLastCalledWith([])
  expect(markerMocks.setMarkers).toHaveBeenLastCalledWith([expect.objectContaining({text:'BUY'})])
  h.renderer.indicators({points:[point],signals:[point]},false,[],{showSignals:false})
  expect(markerMocks.setMarkers).toHaveBeenLastCalledWith([])
})

it('distinguishes paper fills from signal arrows and filters other symbol/interval fills',()=>{
 const h=harness();h.renderer.apply([candle({candle_complete:true})],'live:AAPL:1m')
 const point={...candle({candle_complete:true}),candle_open_timestamp:'2026-01-06T15:00:00Z',signal:'BUY',confirmed:true,signal_id:'signal'}
 const fill={id:8,symbol:'AAPL',interval:'1m',side:'BUY',quantity:16,source_timestamp:'2026-01-06T15:00:20Z'}
 h.renderer.indicators({points:[],signals:[point]},true,[fill,{...fill,id:9,symbol:'MSFT'},{...fill,id:10,interval:'5m'}])
 expect(markerMocks.setMarkers.mock.calls.at(-1)[0]).toEqual(expect.arrayContaining([
  expect.objectContaining({shape:'arrowUp',text:'BUY'}),expect.objectContaining({shape:'circle',text:'FILL BUY 16',id:'paper-fill:8'})]))
 expect(markerMocks.setMarkers.mock.calls.at(-1)[0]).toHaveLength(2)
})


it('selects signals on marker hover or candle click and removes handlers cleanly',()=>{
 const h=harness(),row=candle({candle_complete:true})
 const point={...row,signal:'SELL',signal_id:'sell-id',confirmed:true,sma20:99,sma50:99.6}
 h.renderer.apply([row],'replay:2:AAPL:1m');h.renderer.indicators({points:[point],signals:[point,point]})
 expect(markerMocks.setMarkers.mock.calls.at(-1)[0]).toEqual([expect.objectContaining({id:'sell-id',shape:'arrowDown',position:'aboveBar',text:'SELL',time:1767711600})])
 h.chart.subscribeCrosshairMove.mock.calls[0][0]({hoveredObjectId:'sell-id'})
 expect(h.onSignalSelect).toHaveBeenLastCalledWith('sell-id')
 h.chart.subscribeClick.mock.calls[0][0]({time:1767711600})
 expect(h.onSignalSelect).toHaveBeenLastCalledWith('sell-id')
 h.renderer.apply([],'live:MSFT:5m')
 expect(h.onSignalSelect).toHaveBeenLastCalledWith(null)
 h.renderer.remove();expect(h.chart.unsubscribeClick).toHaveBeenCalled();expect(h.chart.unsubscribeCrosshairMove).toHaveBeenCalled()
})
