import { createChart, CandlestickSeries, HistogramSeries, ColorType } from 'lightweight-charts'
import { reliableVolume } from './candleBook.js'

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
export function createChartRenderer(container, factory = createChart) {
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
  chart.panes()[0].setStretchFactor(4)
  chart.panes()[1].setStretchFactor(1)
  let context
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
      if (changedContext) { context = key; rendered = new Map(); fitted = false }
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
    resize(width, height) { if (width > 0 && height > 0) chart.resize(Math.floor(width), Math.floor(height)) },
    focus(count, follow = true) {
      focusCount = Number.isInteger(count) && count > 0 ? count : 0
      following = follow
      if (focusCount) focusLatest()
      else if (rendered.size) chart.timeScale().fitContent()
    },
    fit() { chart.timeScale().fitContent() },
    remove() { chart.remove() },
  }
}
