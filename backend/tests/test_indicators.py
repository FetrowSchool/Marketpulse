"""Explicit synthetic data. Fraction-based reference is independent of service Decimal windows."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from fractions import Fraction
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.indicators import evaluate,saved_snapshot
from app.services.database import utc_timestamp


def candles(closes,complete=True):
    result=[]
    for i,close in enumerate(closes):
        timestamp=utc_timestamp(datetime(2026,1,6,15,tzinfo=timezone.utc)+timedelta(minutes=i))
        result.append(dict(id=i+1,symbol='AAPL',data_source='yahoo_finance',data_mode='simulated',
          observation_type='constructed_candle',source_observation_id=f'fixture:{i}',candle_interval='1m',
          candle_open_timestamp=timestamp,source_timestamp=timestamp,received_timestamp=timestamp,
          revision=1,candle_complete=complete,close=close))
    return result


def result(rows):return evaluate(rows,'AAPL','1m')


def test_manual_arithmetic_reference_and_insufficient_history():
    # Closes 1..50: last20 =31..50 => (31+50)*20/2 /20 =40.5.
    # Last50 sum=1275 =>25.5. No previous SMA50 => no crossover yet.
    data=result(candles(range(1,81)))
    for i,point in enumerate(data['points']):
        for period,key in ((20,'sma20'),(50,'sma50')):
            if i+1<period:assert point[key] is None
            else:assert point[key]==float(sum(Fraction(n) for n in range(i+2-period,i+2))/period)
    assert data['points'][49]['sma20']==40.5 and data['points'][49]['sma50']==25.5
    assert data['points'][49]['confirmed'] is False
    assert data['latest']['signal']=='HOLD' and not data['signals']


@pytest.mark.parametrize('last,signal',[(120,'BUY'),(80,'SELL'),(100,'HOLD')])
def test_equality_departure_and_no_repeated_direction(last,signal):
    data=result(candles([100]*50+[last]*10))
    assert data['points'][50]['signal']==signal
    assert data['points'][50]['confirmed'] is True
    assert all(p['signal']=='HOLD' for p in data['points'][51:])
    assert len(data['signals'])==(0 if signal=='HOLD' else 1)


def test_current_equality_is_hold_and_actual_opposite_crossover():
    data=result(candles([100]*50+[120]+[80]*30))
    assert [p['signal'] for p in data['signals']]==['BUY','SELL']
    assert result(candles([100]*60))['signals']==[]


def test_incomplete_candle_cannot_create_sma_or_signal_until_completed():
    rows=candles([100]*50+[120]);rows[-1]['candle_complete']=False
    data=result(rows)
    assert data['points'][-1]['sma20'] is None and not data['points'][-1]['confirmed']
    assert not data['signals'] and data['completed_count']==50
    revised={**rows[-1],'candle_complete':True,'revision':2,'id':90}
    assert result(rows+[revised])['signals'][0]['signal']=='BUY'


def test_revisions_out_of_order_duplicates_retract_and_replace_stable_signal():
    rows=candles([100]*50+[120]);initial=result(rows)
    assert result(list(reversed(rows))+[rows[-1]])==initial
    correction={**rows[-1],'id':99,'revision':2,'close':80}
    updated=result(rows+[correction,rows[-1],correction])
    assert len(updated['signals'])==1 and updated['signals'][0]['signal']=='SELL'
    assert updated['signals'][0]['signal_id']==initial['signals'][0]['signal_id']
    neutral={**correction,'id':100,'revision':3,'close':100}
    assert result(rows+[correction,neutral])['signals']==[]


def test_symbols_intervals_and_provenance_are_never_mixed():
    rows=candles([100]*50+[120])
    for field,value in [('symbol','MSFT'),('candle_interval','5m')]:
        invalid=deepcopy(rows);invalid[-1][field]=value
        with pytest.raises(ValueError):result(invalid)
    rows[-1]['data_mode']='delayed'
    assert result(rows)['points'][-1]['sma20'] is None and not result(rows)['signals']


def test_saved_snapshot_api_and_replay_evaluation_preserve_asof_and_do_not_write(db):
    rows=candles([100]*50+[120]);ids=[]
    for row in rows:
        values={k:v for k,v in row.items() if k not in ('id','revision')}
        ids.append(db.insert_observation(**values,payload={'fixture':True}))
    before=db.retrieve(limit=10000)
    data=saved_snapshot(db,'AAPL','1m')
    assert data['signals'][0]['signal']=='BUY'
    correction={k:v for k,v in rows[-1].items() if k not in ('id','revision')}
    correction['close']=80
    db.insert_observation(**correction,payload={'fixture':True})
    assert saved_snapshot(db,'AAPL','1m',as_of_id=ids[-1])['signals'][0]['signal']=='BUY'
    assert saved_snapshot(db,'AAPL','1m')['signals'][0]['signal']=='SELL'
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    with TestClient(app) as client:
        assert client.get('/api/indicators/config').json()['execution_enabled'] is False
        assert client.get('/api/indicators/sma?symbol=AAPL&interval=1m').json()['latest']['sma20']==99
        assert client.get('/api/indicators/signals?symbol=AAPL').json()['signals'][0]['signal']=='SELL'
        # Replay/visible snapshot has only the old arrived revision: do not consult future SQLite correction.
        response=client.post('/api/indicators/evaluate',json={'symbol':'AAPL','interval':'1m','candles':rows})
        assert response.status_code==200 and response.json()['signals'][0]['signal']=='BUY'
        assert client.post('/api/indicators/evaluate',json={'symbol':'MSFT','interval':'1m','candles':rows}).status_code==422
        assert client.get('/api/indicators/sma?symbol=BAD').status_code==422
        assert client.get('/api/indicators/sma?limit=1001').status_code==422
    assert len(db.retrieve(limit=10000))==len(before)+1


def test_api_rejects_invalid_candles_and_keeps_read_errors_clear(db,monkeypatch):
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    with TestClient(app) as client:
        row=candles([100])[0]
        for field,value in [('close',True),('candle_complete','yes'),('source_timestamp','2026-01-01T00:00:00')]:
            invalid={**row,field:value}
            assert client.post('/api/indicators/evaluate',json={'symbol':'AAPL','interval':'1m','candles':[invalid]}).status_code==422
        def fail():raise __import__('sqlite3').OperationalError('private path')
        monkeypatch.setattr(app.state.database,'read_connection',fail)
        response=client.get('/api/indicators/sma')
        assert response.status_code==503 and 'private path' not in response.text


def test_invalid_completed_close_breaks_the_window_without_fabrication():
    rows=candles([100]*50+[120]);rows[-1]['close']=None
    data=result(rows)
    assert data['points'][-1]['reason']=='invalid_close' and not data['signals']
