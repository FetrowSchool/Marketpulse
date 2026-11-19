import { createChart, CandlestickSeries, HistogramSeries, LineSeries, createSeriesMarkers, ColorType } from 'lightweight-charts'
import { reliableVolume } from './candleBook.js'
import {chartPoints,confirmedChartSignals,scopedFills,chartTime} from './chartSignals.js'

const UP = '#54d6b1'
const DOWN = '#ed8093'
export function chartBar(row) {
  const up = row.close >= row.open
  return { time: Date.parse(row.candle_open_timestamp) / 1000,
    open: row.open, high: row.high, low: row.low, close: row.close,
    color: row.candle_complete ? (up ? UP : DOWN) : (up ? 'rgba(84,214,177,0.48)' : 'rgba(237,128,147,0.48)'),
    borderColor: up ? UP : DOWN, wickColor: up ? UP : DOWN }
}
export function volumeBar(row) {
  const time = Date.parse(row.candle_open_timestamp) / 1000
  return reliableVolume(row) ? { time, value: row.volume, color: row.close >= row.open ? '#318872' : '#9d5265' } : { time }
}
export function createChartRenderer(container, factory = createChart, {onSignalSelect=()=>{}}={}) {
  const chart = factory(container, {
    // Supply measured dimensions before fitting data; asynchronous autoSize can fit against width zero.
    autoSize: false, width: Math.max(1, container.clientWidth), height: Math.max(1, container.clientHeight),
    layout: { background: { type: ColorType.Solid, color: '#101923' }, textColor: '#8e9fb6',
      fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11, attributionLogo: true,
      panes: { separatorColor: '#2b394a', separatorHoverColor: '#496077' } },
    grid: { vertLines: { color: '#1b2938' }, horzLines: { color: '#1b2938' } },
    rightPriceScale: { borderColor: '#2b394a', minimumWidth: 72 },
    timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 5, barSpacing: 9, borderColor: '#2b394a' },
    localization: { locale: 'en-US', timeFormatter: time => new Date(time * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC' },
    crosshair: { vertLine: { color: '#65788d', labelBackgroundColor: '#32475a' },
      horzLine: { color: '#65788d', labelBackgroundColor: '#32475a' } },
  })
  const priceSeries = chart.addSeries(CandlestickSeries, {
    upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN,
    wickUpColor: UP, wickDownColor: DOWN, priceFormat: { type: 'price', precision: 2, minMove: .01 },
  }, 0)
  const volumeSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' },
    lastValueVisible: false, priceLineVisible: false }, 1)
  const sma20Series = chart.addSeries(LineSeries, { color: '#62c9ff', lineWidth: 2, title: 'SMA 20', priceLineVisible: false, lastValueVisible: false }, 0)
  const sma50Series = chart.addSeries(LineSeries, { color: '#e9b764', lineWidth: 2, title: 'SMA 50', priceLineVisible: false, lastValueVisible: false }, 0)
  const markers = createSeriesMarkers(priceSeries, [])
  chart.panes()[0].setStretchFactor(4)
  chart.panes()[1].setStretchFactor(1)
  let context
  let markerSelection=new Map(), signalTimes=new Map(),lastMarkerKey=''
  function selectHovered(event){const id=markerSelection.get(event.hoveredObjectId);if(id)onSignalSelect(id)}
  function selectClicked(event){const id=markerSelection.get(event.hoveredObjectId)||signalTimes.get(event.time);if(id)onSignalSelect(id)}
  chart.subscribeClick?.(selectClicked)
  chart.subscribeCrosshairMove?.(selectHovered)
  let rendered = new Map()
  let fitted = false
  let focusCount = 0, following = true
  function focusLatest() {
    const count = rendered.size
    if (count && focusCount) chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, count - focusCount) - .5, to: count - .5 + 2,
    })
  }
  const stamp = row => `${row.id}:${row.revision}`
  function replace(rows, preserve) {
    const range = preserve ? chart.timeScale().getVisibleRange() : null
    priceSeries.setData(rows.map(chartBar))
    volumeSeries.setData(rows.map(volumeBar))
    if (range) chart.timeScale().setVisibleRange(range)
  }
  return {
    apply(rows, key, { loading = false } = {}) {
      const changedContext = key !== context
      if (changedContext) { context = key; rendered = new Map(); fitted = false; sma20Series.setData([]); sma50Series.setData([]); markers.setMarkers([]);markerSelection.clear();signalTimes.clear();lastMarkerKey='';onSignalSelect(null) }
      const next = new Map(rows.map(row => [Date.parse(row.candle_open_timestamp) / 1000, row]))
      const lastTime = rendered.size ? Math.max(...rendered.keys()) : -Infinity
      const changed = rows.filter(row => stamp(row) !== stamp(rendered.get(Date.parse(row.candle_open_timestamp) / 1000) || {}))
      const insertion = changed.some(row => {
        const time = Date.parse(row.candle_open_timestamp) / 1000
        return time < lastTime && !rendered.has(time)
      })
      const removal = [...rendered.keys()].some(time => !next.has(time))
      if (changedContext || !rendered.size || insertion || removal) {
        replace(rows, !changedContext && rendered.size > 0)
      } else {
        let replaceVolume = false
        for (const row of changed) {
          const time = Date.parse(row.candle_open_timestamp) / 1000
          const previous = rendered.get(time)
          const historical = time < lastTime
          priceSeries.update(chartBar(row), historical)
          // Historical whitespace ↔ real volume transitions require a volume-series refresh.
          if (historical && previous && (!reliableVolume(previous) || !reliableVolume(row))) replaceVolume = true
          else volumeSeries.update(volumeBar(row), historical)
        }
        if (replaceVolume) volumeSeries.setData(rows.map(volumeBar))
      }
      rendered = next
      if (!loading && rows.length && !fitted) { chart.timeScale().fitContent(); fitted = true }
      if (focusCount && (following || changedContext)) focusLatest()
    },
    indicators(data, visible = true, strategyFills = [], {showSignals=true,showFills=true}={}) {
      const [symbol,interval]=context?.split(':').slice(-2)||[]
      const candles=[...rendered.values()]
      const points = visible ? chartPoints(data,candles,symbol,interval) : []
      const line = key => points.map(point => ({time: chartTime(point.candle_open_timestamp),
        ...(Number.isFinite(point[key]) ? {value: point[key]} : {})}))
      sma20Series.applyOptions?.({title:`SMA ${data?.configuration?.fast_period||20}`})
      sma50Series.applyOptions?.({title:`SMA ${data?.configuration?.slow_period||50}`})
      sma20Series.setData(line('sma20')); sma50Series.setData(line('sma50'))
      const signals=confirmedChartSignals(data,candles,symbol,interval)
      const signalMarkers = showSignals ? signals.map(point => ({
        id: point.signal_id, time: chartTime(point.candle_open_timestamp),
        position: point.signal === 'BUY' ? 'belowBar' : 'aboveBar',
        shape: point.signal === 'BUY' ? 'arrowUp' : 'arrowDown',
        color: point.signal === 'BUY' ? UP : DOWN, text: point.signal,
      })) : []
      const intervals = {'1m':60,'5m':300,'15m':900}
      const fills=scopedFills(strategyFills,symbol,interval)
      const fillMarkers=showFills ? fills.map(fill=>({
        id:fill.marker_id||`paper-fill:${fill.id}`,time:Math.floor(chartTime(fill.source_timestamp)/intervals[interval])*intervals[interval],
        position:fill.side==='BUY'?'belowBar':'aboveBar',shape:'circle',color:'#d4a1f0',
        size:.75,text:`FILL ${fill.side} ${fill.quantity}`,
      })).filter(marker=>rendered.has(marker.time)) : []
      markerSelection=new Map(signalMarkers.map(marker=>[marker.id,marker.id]))
      signalTimes=new Map(signalMarkers.map(marker=>[marker.time,marker.id]))
      const signalIds=new Set(signals.map(signal=>signal.signal_id))
      const slots=new Map(signals.map(signal=>[`${chartTime(signal.candle_open_timestamp)}:${signal.signal}`,signal.signal_id]))
      const visibleFillIds=new Set(fillMarkers.map(marker=>marker.id))
      for(const fill of fills){
        const id=fill.marker_id||`paper-fill:${fill.id}`
        const signalId=signalIds.has(fill.signal_id)?fill.signal_id:slots.get(`${chartTime(fill.signal_candle_open_timestamp)}:${fill.signal_direction}`)
        if(signalId&&visibleFillIds.has(id))markerSelection.set(id,signalId)
      }
      const all=[...signalMarkers,...fillMarkers].sort((a,b)=>a.time-b.time || String(a.id).localeCompare(String(b.id)))
      const nextKey=JSON.stringify(all)
      if(nextKey!==lastMarkerKey){markers.setMarkers(all);lastMarkerKey=nextKey}
    },
    resize(width, height) { if (width > 0 && height > 0) chart.resize(Math.floor(width), Math.floor(height)) },
    focus(count, follow = true) {
      focusCount = Number.isInteger(count) && count > 0 ? count : 0
      following = follow
      if (focusCount) focusLatest()
      else if (rendered.size) chart.timeScale().fitContent()
    },
    fit() { chart.timeScale().fitContent() },
    remove() { chart.unsubscribeClick?.(selectClicked);chart.unsubscribeCrosshairMove?.(selectHovered);markers.detach?.();chart.remove() },
  }
}
