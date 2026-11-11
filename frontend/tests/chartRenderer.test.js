import { describe, expect, it, vi } from 'vitest'
import { createChartRenderer } from '../src/services/chartRenderer.js'
import { candle, nextCandle } from './chartFixture.js'
function harness() {
  const series = [0, 1].map(() => ({ setData: vi.fn(), update: vi.fn() }))
  const scale = { setVisibleLogicalRange: vi.fn(), fitContent: vi.fn(), getVisibleRange: vi.fn(() => ({ from: 1, to: 2 })), setVisibleRange: vi.fn() }
  const chart = { addSeries: vi.fn().mockReturnValueOnce(series[0]).mockReturnValueOnce(series[1]),
    panes: () => [{ setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }],
    timeScale: () => scale, resize: vi.fn(), remove: vi.fn() }
  const factory = vi.fn(() => chart)
  const container = document.createElement('div')
  Object.defineProperty(container, 'clientWidth', { value: 800 })
  Object.defineProperty(container, 'clientHeight', { value: 500 })
  return { renderer: createChartRenderer(container, factory), factory, chart, series, scale }
}
describe('TradingView renderer adapter', () => {
  it('initializes price and aligned volume panes from saved candles', () => {
    const h = harness()
    h.renderer.apply([candle(), nextCandle({ volume: 50, metadata: { volume_reliable: true } })], 'AAPL:1m')
    expect(h.factory).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ autoSize: false, width: 800, height: 500 }))
    expect(h.chart.addSeries.mock.calls.map(call => call[2])).toEqual([0, 1])
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
