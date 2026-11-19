import asyncio,json,tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from app.config import Settings
from app.main import create_app
from app.services.database import Database,utc_timestamp

BASE=datetime.now(timezone.utc).replace(second=0,microsecond=0)-timedelta(minutes=51)
DATA=Path(tempfile.mkdtemp(prefix='marketpulse-browser-db-'))/'fixture.sqlite3'
db=Database(DATA);db.initialize()
def seed(symbol,closes,mode,opens=None):
 for i,close in enumerate(closes):
  opening=BASE+timedelta(minutes=i);op=(opens or {}).get(i,close)
  raw=db.insert_observation(symbol=symbol,data_source='yahoo_finance',source_observation_id=f'browser-fixture-price:{symbol}:{i}',observation_type='raw_provider',data_mode=mode,source_timestamp=opening+timedelta(seconds=30),received_timestamp=opening+timedelta(seconds=31),payload={'price':close,'fixture':True})
  db.insert_observation(symbol=symbol,data_source='yahoo_finance',source_observation_id=f'browser-fixture-candle:{symbol}:{i}',observation_type='constructed_candle',data_mode=mode,candle_interval='1m',candle_open_timestamp=opening,open=op,high=max(op,close),low=min(op,close),close=close,volume=100+i,candle_complete=True,source_timestamp=opening+timedelta(seconds=59),received_timestamp=opening+timedelta(minutes=1),payload={'fixture':True,'volume_reliable':True,'volume_semantics':'interval_trade_volume','contributing_observation_ids':[raw]})
seed('AAPL',[100]*50,'delayed')
seed('MSFT',[100]*50+[120,80,80,90],'simulated',{51:125,53:90})
app=create_app(Settings(database_path=DATA,feed_enabled=False,cors_origins=('http://127.0.0.1:5174',),reconnect_base_seconds=.01,reconnect_max_seconds=.02,max_reconnect_attempts=1))
clock=[BASE+timedelta(minutes=50,seconds=1)];app.state.market.clock=lambda:clock[0]
class OfflineStream:
 async def connect(self,*a):raise ConnectionError('Intentional fixture feed outage; no provider request')
 async def close(self):pass
app.state.market.stream_factory=OfflineStream
stages=[]
async def raw(index,seconds,price,receipt):
 source=BASE+timedelta(minutes=index,seconds=seconds);clock[0]=BASE+receipt
 await app.state.market.handle_message({'id':'AAPL','price':price,'time':str(int(source.timestamp()*1000)),'fixture':True})
async def complete(index):
 clock[0]=BASE+timedelta(minutes=index,milliseconds=500)
 await asyncio.to_thread(app.state.market.repository.complete_due,clock[0])
@app.post('/_test/stage/{stage}')
async def stage(stage:str):
 if stage in stages:return {'stage':stage,'duplicate':True}
 if stage=='buy':
  await raw(50,30,120,timedelta(minutes=50,seconds=31));await complete(51)
  await raw(51,1,125,timedelta(minutes=51,seconds=2))
 elif stage=='sell':
  if 'buy' not in stages:raise HTTPException(409,'Run buy fixture first')
  await raw(51,30,80,timedelta(minutes=51,seconds=31));await complete(52)
  await raw(52,30,80,timedelta(minutes=52,seconds=31));await complete(53)
  await raw(53,1,90,timedelta(minutes=53,seconds=2))
 else:raise HTTPException(422,'Unknown fixture stage')
 stages.append(stage)
 return {'stage':stage,'fixture':True}
@app.get('/_test/info')
def info():return {'fixture':True,'database':str(DATA),'base':utc_timestamp(BASE),'stages':stages,'feed':'intentionally offline; no Yahoo dependency'}
