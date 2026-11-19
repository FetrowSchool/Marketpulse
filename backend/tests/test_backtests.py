"""Synthetic deterministic historical fixtures; not investment-performance evidence."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.backtests import Backtests, simulate
from app.services.database import Database, utc_timestamp
from app.services.indicators import evaluate

BASE = datetime(2026, 1, 6, 15, tzinfo=timezone.utc)


def configuration(**kwargs):
    return dict(symbol='AAPL', interval='1m', candle_type='constructed_candle',
                start=utc_timestamp(BASE), end=utc_timestamp(BASE + timedelta(minutes=100)),
                starting_balance='10000', fast_period=2, slow_period=3, **kwargs)


def candles(closes=(10,10,10,12,8,8,9), opens=None):
    opens = opens or {4:15,6:9}
    return [dict(id=i+1, symbol='AAPL',data_source='yahoo_finance',data_mode='simulated',
            observation_type='constructed_candle',source_observation_id=f'fixture:{i}',revision=1,
            candle_interval='1m',candle_open_timestamp=utc_timestamp(BASE+timedelta(minutes=i)),
            received_timestamp=utc_timestamp(BASE+timedelta(minutes=i+1)),
            source_timestamp=utc_timestamp(BASE+timedelta(minutes=i,seconds=59)),
            open=opens.get(i,p),high=max(opens.get(i,p),p),low=min(opens.get(i,p),p),close=p,
            volume=None,candle_complete=True,payload_json='{"fixture":true}') for i,p in enumerate(closes)]


def save(db, rows):
    for row in rows:
        data={k:v for k,v in row.items() if k not in ('id','revision','payload_json')}
        db.insert_observation(**data,payload={'fixture':True})


def test_known_cash_accounting_equity_drawdown_and_unfilled_final_signal():
    result=simulate(candles(),configuration()); summary=result['summary']
    # Independent arithmetic: floor(2000/15)=133; buy1995; sell1197; loss798.
    assert [(f['side'],f['quantity'],f['price'],f['candle_id']) for f in result['fills']]==[('BUY',133,'15.000000',5),('SELL',133,'9.000000',7)]
    assert summary['ending_cash']==summary['ending_equity']=='9202.000000'
    assert summary['realized_pl']=='-798.000000' and summary['unrealized_pl']=='0.000000'
    assert Decimal(summary['total_return_percent'])==Decimal('-7.98')
    # Worst mark: cash8005 +133*8=9069; drawdown=(10000-9069)/10000.
    assert Decimal(summary['max_drawdown_percent'])==Decimal('9.31')
    assert summary['completed_trades']==1 and summary['fill_count']==2
    assert summary['win_rate_percent']=='0'
    assert result['decisions'][-1]['status']=='unfilled'
    assert result['fills'][0]['signal_candle_id']==4


def test_default_rules_match_existing_indicator_calculator():
    rows=candles([100]*50+[120,80,80,90],{51:125,53:90})
    config=configuration();config.update(fast_period=20,slow_period=50)
    result=simulate(rows,config)
    indicators=evaluate(rows,'AAPL','1m')
    expected=[(p['id'],p['signal']) for p in indicators['signals']]
    assert [(p['candle_id'],p['signal']) for p in result['decisions'] if p['signal']!='HOLD']==expected
    assert result['fills'][0]['price']=='125.000000'
    assert result['fills'][0]['quantity']==16
    assert result['summary']['ending_equity']=='9440.000000'


def test_prefix_decisions_and_fills_do_not_depend_on_future_close():
    rows=candles();changed=deepcopy(rows);changed[-1].update(close=1000,high=1000)
    a=simulate(rows,configuration());b=simulate(changed,configuration())
    assert a['fills']==b['fills']
    assert a['decisions'][:-1]==b['decisions'][:-1]
    assert all(f['timestamp']>=f['signal_available_at'] for f in a['fills'])
    assert all(f['candle_id']>f['signal_candle_id'] for f in a['fills'])


def test_receipt_delay_prevents_backdated_execution():
    rows=candles(); rows[3]['received_timestamp']=utc_timestamp(BASE+timedelta(minutes=4,seconds=30))
    result=simulate(rows,configuration())
    assert result['fills'][0]['candle_id']==6
    assert result['fills'][0]['timestamp']==utc_timestamp(BASE+timedelta(minutes=5))


def test_open_position_unrealized_and_no_forced_close():
    result=simulate(candles()[:5],configuration())
    assert result['summary']['completed_trades']==0
    assert result['summary']['win_rate_percent'] is None
    assert result['summary']['realized_pl']=='0.000000'
    assert result['summary']['unrealized_pl']=='-931.000000'
    assert result['summary']['ending_equity']=='9069.000000'


def test_no_trade_zero_drawdown_and_insufficient_cash():
    result=simulate(candles([10]*6),configuration())
    assert result['fills']==[] and result['summary']['win_rate_percent'] is None
    assert result['summary']['max_drawdown_percent']=='0'
    config=configuration();config['starting_balance']='1'
    result=simulate(candles(),config)
    assert result['fills']==[]
    assert any(d['reason']=='insufficient_cash' for d in result['decisions'])


def test_incomplete_gap_duplicate_and_revisions():
    rows=candles(); duplicate=deepcopy(rows[3]);duplicate.update(id=100,revision=2,close=1,low=1,received_timestamp=utc_timestamp(BASE+timedelta(minutes=20)))
    result=simulate(rows+[duplicate],configuration())
    assert result['summary']==simulate(rows,configuration())['summary']
    assert result['input_hash']==simulate(rows,configuration())['input_hash']
    assert result['quality']['later_completed_versions_excluded']==1
    rows[4]['candle_complete']=False
    result=simulate(rows,configuration())
    assert result['quality']['incomplete_rows_excluded']==1
    assert result['quality']['missing_interval_slots']==1
    assert result['fills'][0]['candle_id']==6


def test_late_completion_does_not_rewrite_current_state():
    rows=candles();rows[1]['received_timestamp']=utc_timestamp(BASE+timedelta(minutes=6,seconds=30))
    result=simulate(list(reversed(rows)),configuration())
    assert any(d['reason']=='out_of_order_completion' for d in result['decisions'])
    assert result==simulate(rows,configuration())


@pytest.mark.parametrize('change', [{'close':None},{'low':100},{'open':0},{'high':float('nan')}])
def test_invalid_ohlc_is_visible(change):
    rows=candles();rows[0].update(change)
    with pytest.raises(ValueError,match='OHLC'):
        simulate(rows,configuration())


def test_insufficient_history_and_invalid_parameters():
    with pytest.raises(ValueError,match='Insufficient'):
        simulate(candles()[:3],configuration())
    config=configuration();config['fast_period']=3
    with pytest.raises(ValueError,match='fast SMA'):
        simulate(candles(),config)
    with pytest.raises(ValueError,match='Mixed'):
        rows=candles();rows[0]['symbol']='MSFT';simulate(rows,configuration())


def test_persistence_isolation_restart_and_deterministic_runs(db):
    save(db,candles())
    tables=['observations','simulated_accounts','paper_orders','paper_fills','paper_positions','strategy_config','strategy_signals','strategy_decisions']
    def snapshot():
        with closing(db.connect()) as c:
            return {t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}
    before=snapshot();service=Backtests(db)
    a=service.run(configuration());b=service.run(configuration())
    assert a['id']!=b['id']
    assert {k:v for k,v in a.items() if k!='id'}=={k:v for k,v in b.items() if k!='id'}
    assert snapshot()==before
    restarted=Database(db.path);restarted.initialize();restarted.initialize()
    assert Backtests(restarted).get(a['id'])==a
    assert len(Backtests(restarted).list())==2
    with db.transaction() as c:
        with pytest.raises(Exception,match='immutable'):
            c.execute('UPDATE backtest_runs SET input_hash=?',('x'*64,))


def test_api_errors_and_provider_origin_selection(db):
    save(db,candles())
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    with TestClient(app) as client:
        body=configuration()
        response=client.post('/api/backtests',json=body)
        assert response.status_code==200,response.text
        run=response.json()
        assert client.get('/api/backtests/'+str(run['id'])).json()==run
        assert client.get('/api/backtests').json()['runs'][0]['id']==run['id']
        assert client.get('/api/backtests/999').status_code==404
        assert client.post('/api/backtests',json={**body,'fast_period':50,'slow_period':20}).status_code==422
        assert client.post('/api/backtests',json={**body,'start':'2026-01-01'}).status_code==422
        assert client.post('/api/backtests',json={**body,'symbol':'INVALID'}).status_code==422
        response=client.post('/api/backtests',json={**body,'candle_type':'provider_candle'})
        assert response.status_code==422 and 'Insufficient' in response.json()['detail']
        assert client.get('/api/paper/account').json()['cash']=='10000.000000'


def test_end_boundary_and_missing_next_open():
    rows=candles()[:4];config=configuration();config['end']=utc_timestamp(BASE+timedelta(minutes=4))
    result=simulate(rows,config)
    assert result['fills']==[] and result['decisions'][-1]['status']=='unfilled'
    # A later final close not recorded by the range end cannot generate a signal.
    rows[-1]['received_timestamp']=utc_timestamp(BASE+timedelta(minutes=5))
    with pytest.raises(ValueError,match='available by end'):
        simulate(rows,config)


def test_positive_round_trip_win_rate():
    rows=candles(opens={4:5,6:9})
    result=simulate(rows,configuration())
    assert result['summary']['win_rate_percent']=='100'
    assert result['summary']['realized_pl']=='1600.000000'


def test_provider_candles_are_separate_and_supported(db):
    rows=candles()
    for row in rows:row['observation_type']='provider_candle'
    save(db,rows)
    config=configuration();config['candle_type']='provider_candle'
    result=Backtests(db).run(config)
    assert result['configuration']['candle_type']=='provider_candle'
    assert result['summary']['ending_equity']=='9202.000000'
    with pytest.raises(ValueError,match='Insufficient'):
        Backtests(db).run(configuration())


def test_retrospectively_received_history_cannot_claim_timely_signals():
    rows=candles()
    for row in rows:row['received_timestamp']=utc_timestamp(BASE+timedelta(days=1))
    with pytest.raises(ValueError,match='available by end'):
        simulate(rows,configuration())


def test_entire_equity_curve_chronology_against_hand_reference():
    result=simulate(candles(),configuration())
    curve=result['equity_curve']
    assert [p['timestamp'] for p in curve]==sorted(p['timestamp'] for p in curve)
    assert [p['equity'] for p in curve]==['10000.000000']*9+['9069.000000']*3+['9202.000000']*2
    assert [p['event'] for p in curve]==['open','close']*7
    assert [f['signal_candle_id'] for f in result['fills']]==[4,6]
    assert [f['candle_id'] for f in result['fills']]==[5,7]
    assert result['trades']==[{'entry_timestamp':utc_timestamp(BASE+timedelta(minutes=4)),
        'entry_price':'15.000000','quantity':133,'entry_candle_id':5,
        'exit_timestamp':utc_timestamp(BASE+timedelta(minutes=6)),
        'exit_price':'9.000000','exit_candle_id':7,'realized_pl':'-798.000000'}]


def test_backtest_chart_uses_saved_decisions_and_exact_revisions(db):
    rows=candles([100]*50+[120,80,80,90],{51:125,53:90})
    save(db,rows);config=configuration();config.update(fast_period=20,slow_period=50)
    service=Backtests(db);run=service.run(config)
    # A later revision may alter today's indicators but must not change this saved run.
    revised=deepcopy(rows[50]);revised.update(close=5,low=5)
    save(db,[revised])
    before=db.retrieve(limit=10000)
    chart=service.chart(run['id'])
    assert chart['candles'][50]['close']==120 and chart['candles'][50]['revision']==1
    assert [p['signal'] for p in chart['indicators']['signals']]==['BUY','SELL']
    expected=[d['candle_id'] for d in run['decisions'] if d.get('confirmed') and d['signal']!='HOLD']
    assert [s['id'] for s in chart['indicators']['signals']]==expected
    assert [(s['sma20'],s['sma50']) for s in chart['indicators']['signals']]==[(101,100.4),(99,99.6)]
    assert all(s['candle_complete'] and s['confirmed'] for s in chart['indicators']['signals'])
    assert len(chart['fills'])==len(run['fills'])==2
    assert chart['fills'][0]['signal_id']==chart['indicators']['signals'][0]['signal_id']
    assert chart['fills'][0]['source_timestamp']==run['fills'][0]['timestamp']
    assert db.retrieve(limit=10000)==before
    assert service.chart(run['id'])==chart
    assert service.get(999) is None and service.chart(999) is None


def test_backtest_chart_never_invents_a_fill_and_keeps_custom_periods(db):
    save(db,candles()[:4]);run=Backtests(db).run(configuration())
    chart=Backtests(db).chart(run['id'])
    assert chart['indicators']['configuration']=={'fast_period':2,'slow_period':3}
    assert len(chart['indicators']['signals'])==1
    assert chart['indicators']['signals'][0]['decision_status']=='unfilled'
    assert chart['fills']==[]


def test_saved_backtest_chart_endpoint_validates_and_is_read_only(db):
    save(db,candles());run=Backtests(db).run(configuration())
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    with TestClient(app) as client:
        response=client.get(f"/api/backtests/{run['id']}/chart")
        assert response.status_code==200,response.text
        assert response.json()['symbol']=='AAPL' and len(response.json()['candles'])==7
        assert client.get('/api/backtests/999/chart').status_code==404
        assert client.get('/api/backtests/0/chart').status_code==422
        assert client.get('/api/paper/orders').json()['orders']==[]
        assert client.get('/api/paper/account').json()['cash']=='10000.000000'
