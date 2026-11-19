import {it,expect,vi,afterEach} from 'vitest'
import {createIndicators} from '../src/services/indicators.js'
import {candle,deferred} from './chartFixture.js'
afterEach(()=>vi.useRealTimers())
it('sends arrived candles only, ignores stale selection responses and survives API errors',async()=>{
  vi.useFakeTimers()
  const first=deferred(),onChange=vi.fn(),onState=vi.fn()
  const fetcher=vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce({ok:true,json:async()=>({symbol:'MSFT',interval:'5m',points:[],signals:[],latest:null})}).mockRejectedValueOnce(new Error('offline'))
  const service=createIndicators({onChange,onState,fetcher})
  service.load([candle()],'AAPL','1m','replay:1')
  await vi.advanceTimersByTimeAsync(100)
  expect(JSON.parse(fetcher.mock.calls[0][1].body).candles).toHaveLength(1)
  service.load([candle({symbol:'MSFT',candle_interval:'5m'})],'MSFT','5m','live')
  await vi.advanceTimersByTimeAsync(100)
  first.resolve({ok:true,json:async()=>({symbol:'AAPL',interval:'1m',points:[{sma20:999}],signals:[]})})
  await vi.advanceTimersByTimeAsync(0)
  expect(onChange.mock.calls.at(-1)[0].symbol).toBe('MSFT')
  service.load([candle()],'AAPL','1m','replay:2')
  await vi.advanceTimersByTimeAsync(100)
  expect(onState.mock.calls.at(-1)[0].error).toContain('Indicators unavailable')
  service.dispose()
})
