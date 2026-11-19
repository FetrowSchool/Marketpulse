"""Explicit synthetic provider-shaped fixtures; no actual provider or profitability claim."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.database import Database,utc_timestamp
from app.services.market_repository import serialize
from app.services.paper_account import PaperAccount,OrderConflict
from app.services.strategy import StrategyService,next_historical_open

BASE=datetime(2026,1,6,15,tzinfo=timezone.utc)


def record(db,identifier):
    with closing(db.connect()) as c:return serialize(c.execute('SELECT * FROM observations WHERE id=?',(identifier,)).fetchone())


def candle(db,index,price,complete=True):
    opening=BASE+timedelta(minutes=index)
    raw=db.insert_observation(symbol='AAPL',data_source='yahoo_finance',observation_type='raw_provider',data_mode='delayed',
        source_observation_id=f'synthetic-price:{index}:{price}',source_timestamp=opening+timedelta(seconds=30),received_timestamp=opening+timedelta(seconds=31),
        payload={'price':price,'fixture':True})
    identifier=db.insert_observation(symbol='AAPL',data_source='yahoo_finance',observation_type='constructed_candle',data_mode='delayed',
        source_observation_id=f'synthetic-candle:{index}',candle_interval='1m',candle_open_timestamp=opening,
        source_timestamp=opening+timedelta(seconds=30),received_timestamp=opening+timedelta(seconds=61),
        open=price,high=price,low=price,close=price,candle_complete=complete,payload={'fixture':True,'contributing_observation_ids':[raw]})
    return record(db,identifier)


def quote(db,price,source,receipt,mode='delayed'):
    identifier=db.insert_observation(symbol='AAPL',data_source='yahoo_finance',observation_type='raw_provider',data_mode=mode,
        source_observation_id=f'synthetic-execution:{source.isoformat()}:{price}:{mode}',source_timestamp=source,received_timestamp=receipt,
        payload={'price':price,'fixture':True})
    return record(db,identifier)


@pytest.fixture
def setup(db):
    for i in range(50):candle(db,i,100)
    clock=[BASE+timedelta(minutes=50,seconds=1)]
    engine=StrategyService(db,Settings(database_path=db.path,feed_enabled=False),clock=lambda:clock[0])
    return db,clock,engine


def confirm(setup,price,index=50):
    db,clock,engine=setup
    clock[0]=BASE+timedelta(minutes=index+1,milliseconds=500)
    bar=candle(db,index,price)
    engine.on_records([bar])
    assert engine.runtime_error is None
    return bar


def execute(setup,price,mode='delayed'):
    db,clock,engine=setup
    clock[0]+=timedelta(seconds=2)
    tick=quote(db,price,clock[0]-timedelta(seconds=1),clock[0],mode)
    engine.on_records([tick])
    assert engine.runtime_error is None
    return tick


def test_default_off_enable_future_only_buy_sizing_trace_and_sell(setup):
    db,clock,engine=setup
    assert not engine.status()['enabled']
    engine.configure(True)
    bar=confirm(setup,120)
    status=engine.status()
    assert status['last_signal']['direction']=='BUY' and status['last_decision']['status']=='waiting'
    assert not PaperAccount(db).orders()  # Never use signal's historical close120.
    tick=execute(setup,125)
    status=engine.status();action=status['last_action']
    assert action['status']=='executed' and action['quantity']==16 and action['execution_price']=='125.000000'
    assert action['execution_observation_id']==tick['id']
    assert action['account_state']['cash']=='8000.000000'
    signal=status['last_signal']
    expected=hashlib.sha256(json.dumps(['sma20-50-long-v1','AAPL','1m',bar['candle_open_timestamp'],'BUY']).encode()).hexdigest()
    assert signal['signal_id']==expected and signal['confirming_candle_id']==bar['id']
    assert len(json.loads(signal['inputs_json']))==51
    fill=PaperAccount(db).fills()[0]
    assert fill['price_source']=='observed_quote' and fill['execution_observation_id']==tick['id']
    confirm(setup,80,51)  # Current equality => HOLD.
    assert engine.status()['last_decision']['status']=='hold'
    confirm(setup,80,52)
    assert engine.status()['last_signal']['direction']=='SELL'
    execute(setup,90)
    status=engine.status()
    assert status['last_action']['quantity']==16 and status['account']['positions']==[]
    assert status['account']['cash']=='9440.000000'  # Test arithmetic, not profitability evidence.


def test_sell_with_no_strategy_position_and_insufficient_cash(setup):
    db,clock,engine=setup;engine.configure(True)
    confirm(setup,80);execute(setup,80)
    assert engine.status()['last_action']['reason']=='no_strategy_position'
    assert not PaperAccount(db).fills()
    engine.configure(False)
    PaperAccount(db).submit(client_order_id='manual-all-cash',symbol='AAPL',side='BUY',quantity=100,execution_price='100')
    engine.configure(True)
    confirm(setup,140,51);execute(setup,125)
    assert engine.status()['last_action']['reason']=='insufficient_cash_for_one_share_at_20_percent'
    assert len(PaperAccount(db).fills())==1


def test_incomplete_hold_and_disabled_do_not_trade(setup):
    db,clock,engine=setup;engine.configure(True)
    engine.on_records([candle(db,50,120,False)])
    assert engine.status()['last_signal'] is None
    confirm(setup,100)
    assert engine.status()['last_decision']['status']=='hold'
    engine.configure(False);confirm(setup,140,51);execute(setup,150)
    assert not PaperAccount(db).orders()


def test_first_eligible_price_rejects_stale_backdated_future_and_recorded(setup):
    db,clock,engine=setup;engine.configure(True);confirm(setup,120)
    confirmed=clock[0]
    clock[0]+=timedelta(seconds=2)
    for source,receipt,mode in [
        (confirmed-timedelta(seconds=1),clock[0],'delayed'),
        (confirmed,clock[0],'recorded'),
        (confirmed,clock[0],'simulated'),
        (clock[0]+timedelta(seconds=1),clock[0],'delayed')]:
        engine.on_records([quote(db,125,source,receipt,mode)])
    assert not PaperAccount(db).orders()
    clock[0]+=timedelta(seconds=20)
    engine.on_records([quote(db,125,confirmed+timedelta(seconds=1),clock[0])])
    assert not PaperAccount(db).orders()
    tick=execute(setup,125)
    assert engine.status()['last_action']['execution_observation_id']==tick['id']


def test_duplicate_reconnect_restart_and_opposite_revision_never_reexecute(setup):
    db,clock,engine=setup;engine.configure(True);bar=confirm(setup,120);tick=execute(setup,125)
    engine.on_records([bar,tick,{**tick,'snapshot':True}])
    db.initialize()
    recovered=StrategyService(Database(db.path),engine.settings,clock=lambda:clock[0]);setup=(db,clock,recovered)
    assert recovered.status()['enabled']
    recovered.on_records([bar,tick])
    revised=candle(db,50,80);recovered.on_records([revised])
    assert recovered.status()['last_decision']['status']=='revision_ignored'
    assert recovered.status()['last_signal']['direction']=='BUY'
    assert len(PaperAccount(db).fills())==1


def test_strategy_owns_only_its_shares_and_manual_cannot_sell_them(setup):
    db,clock,engine=setup;paper=PaperAccount(db)
    paper.submit(client_order_id='manual',symbol='AAPL',side='BUY',quantity=4,execution_price='100')
    engine.configure(True);confirm(setup,120);execute(setup,125)
    position=paper.summary()['positions'][0]
    assert position['manual_quantity']==4 and position['strategy_quantity']==15
    rejected=paper.submit(client_order_id='cannot-sell-strategy',symbol='AAPL',side='SELL',quantity=5,execution_price='130')
    assert rejected['rejection_reason']=='insufficient_manual_shares'
    confirm(setup,80,51);confirm(setup,80,52);execute(setup,90)
    position=paper.summary()['positions'][0]
    assert position['quantity']==position['manual_quantity']==4 and position['strategy_quantity']==0


def test_disable_cancels_waiting_and_reenable_does_not_catch_up(setup):
    db,clock,engine=setup;engine.configure(True);bar=confirm(setup,120)
    engine.configure(False)
    assert engine.status()['last_decision']['status']=='canceled'
    engine.configure(True);execute(setup,125);engine.on_records([bar])
    assert not PaperAccount(db).orders()
    with pytest.raises(OrderConflict):engine.configure(True,'MSFT','5m')


def test_historical_policy_next_eligible_open_without_a_runner():
    boundary=utc_timestamp(BASE+timedelta(minutes=1))
    candidates=[{'id':1,'candle_open_timestamp':utc_timestamp(BASE),'open':100},
                {'id':2,'candle_open_timestamp':boundary,'open':None},
                {'id':3,'candle_open_timestamp':utc_timestamp(BASE+timedelta(minutes=2)),'open':110}]
    assert next_historical_open(boundary,boundary,candidates)['candle_id']==3
    assert next_historical_open(utc_timestamp(BASE+timedelta(minutes=3)),boundary,candidates) is None


def test_replay_and_client_indicators_cannot_drive_live_strategy(db):
    for i in range(50):candle(db,i,100)
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    app.state.market.clock=lambda:BASE+timedelta(minutes=50,seconds=1)
    with TestClient(app) as client:
        assert client.get('/api/strategy/status').json()['enabled'] is False
        assert client.post('/api/strategy/config',json={'enabled':True,'symbol':'AAPL','interval':'1m'}).status_code==200
        candle(db,50,120)  # Saved data inserted externally, not a provider callback.
        assert client.get('/api/indicators/sma?symbol=AAPL').json()['signals']
        with client.websocket_connect('/ws/replay') as replay:
            replay.receive_json();replay.send_json({'type':'load','selection':{'symbol':'AAPL','interval':'1m'},'speed':100})
            replay.receive_json()
        assert client.get('/api/paper/orders').json()['orders']==[]
        assert client.get('/api/strategy/fills?symbol=AAPL&interval=1m').json()['fills']==[]
        assert client.post('/api/strategy/config',json={'enabled':'yes'}).status_code==422
        assert client.post('/api/strategy/config',json={'enabled':True,'symbol':'BAD'}).status_code==422


def test_legacy_manual_fill_migration_preserves_every_row_and_balance(tmp_path):
    # Build the actual prior-stage CHECK constraint, then migrate a nonempty ledger.
    from app.services.database import utc_timestamp
    from app.services.paper_account import PaperAccount
    from app import __file__ as app_file
    root=Path(app_file).parent
    db=Database(tmp_path/'legacy.sqlite3')
    legacy=(root/'paper_schema.sql').read_text().replace("price_source IN ('manual_reference','observed_quote')","price_source='manual_reference'")
    with closing(db.connect()) as conn:
        conn.executescript((root/'schema.sql').read_text()+legacy)
        conn.execute("INSERT INTO simulated_accounts VALUES(1,'SIMULATED','USD',10000000000,10000000000,0,?)",(utc_timestamp(BASE),))
        conn.commit()
    # Seed a legacy fill directly; no strategy-specific queries existed in that version.
    with db.transaction() as conn:
        conn.execute("INSERT INTO paper_orders VALUES(1,1,'legacy','hash','AAPL','BUY',1,100000000,'filled',?,?,NULL,NULL)",(utc_timestamp(BASE),utc_timestamp(BASE)))
        conn.execute("INSERT INTO paper_fills VALUES(1,1,1,'AAPL','BUY',1,100000000,?,0,0,'manual_reference',0,0,9900000000,1)",(utc_timestamp(BASE),))
        conn.execute("UPDATE simulated_accounts SET cash_units=9900000000 WHERE id=1")
        conn.execute("INSERT INTO paper_positions VALUES(1,'AAPL',1,100000000)")
    def rows(table):
        with closing(db.connect()) as conn:return [dict(r) for r in conn.execute('SELECT * FROM '+table)]
    before={table:rows(table) for table in ['paper_orders','paper_fills','paper_positions','simulated_accounts']}
    db.initialize();db.initialize()
    assert {table:rows(table) for table in before}==before
    assert db.verify_integrity()['ok'] and len(PaperAccount(db).fills())==1


def test_strategy_failure_rolls_back_execution_and_suspends_without_corrupting_market(setup,monkeypatch):
    db,clock,engine=setup;engine.configure(True);confirm(setup,120)
    with db.transaction() as conn:
        conn.execute("CREATE TRIGGER fail_strategy_fill BEFORE INSERT ON paper_fills BEGIN SELECT RAISE(ABORT,'test failure'); END")
    clock[0]+=timedelta(seconds=2)
    tick=quote(db,125,clock[0]-timedelta(seconds=1),clock[0]);engine.on_records([tick])
    assert engine.status()['state']=='suspended' and not PaperAccount(db).fills()
    assert PaperAccount(db).summary()['cash']=='10000.000000'
    assert record(db,tick['id'])['price']==125  # Original market transaction survives.


@pytest.mark.parametrize('execution_price',[127,13.000001])
def test_maximum_whole_shares_fit_exact_twenty_percent_budget(setup,execution_price):
    from app.services.paper_account import price_units
    db,clock,engine=setup;engine.configure(True);confirm(setup,120);execute(setup,execution_price)
    quantity=engine.status()['last_action']['quantity'];price=price_units(execution_price)
    assert quantity*price<=2_000_000_000<(quantity+1)*price


def test_actual_post_commit_hook_executes_without_browser_driving_signals(db):
    for i in range(50):candle(db,i,100)
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    clock=[BASE+timedelta(minutes=50,seconds=1)];app.state.market.clock=lambda:clock[0]
    def message(price,source):return {'id':'AAPL','price':price,'time':str(int(source.timestamp()*1000))}
    with TestClient(app) as client:
        client.post('/api/strategy/config',json={'enabled':True})
        clock[0]=BASE+timedelta(minutes=50,seconds=31)
        client.portal.call(app.state.market.handle_message,message(120,BASE+timedelta(minutes=50,seconds=30)))
        assert client.get('/api/paper/orders').json()['orders']==[]
        clock[0]=BASE+timedelta(minutes=51,milliseconds=500)
        client.portal.call(__import__('asyncio').to_thread,app.state.market.repository.complete_due,clock[0])
        assert client.get('/api/strategy/status').json()['last_decision']['status']=='waiting'
        clock[0]=BASE+timedelta(minutes=51,seconds=2)
        tick=message(125,BASE+timedelta(minutes=51,seconds=1))
        client.portal.call(app.state.market.handle_message,tick)
        fills=client.get('/api/paper/fills').json()['fills']
        assert len(fills)==1 and fills[0]['quantity']==16 and fills[0]['price_source']=='observed_quote'
        client.portal.call(app.state.market.handle_message,tick)
        assert len(client.get('/api/paper/fills').json()['fills'])==1
        assert client.get('/api/strategy/status').json()['error'] is None


def test_full_trace_links_completed_inputs_signal_decision_fill_and_account(setup):
    db,clock,engine=setup;engine.configure(True)
    incomplete=candle(db,50,120,complete=False);engine.on_records([incomplete])
    assert not PaperAccount(db).orders()
    completed=confirm(setup,120)
    with closing(db.read_connection()) as conn:
        signal=dict(conn.execute('SELECT * FROM strategy_signals').fetchone())
        assert signal['confirming_candle_id']==completed['id']
        assert Decimal(str(signal['sma20']))==Decimal('101')
        assert Decimal(str(signal['sma50']))==Decimal('100.4')
    observed=execute(setup,125)
    with closing(db.read_connection()) as conn:
        decision=dict(conn.execute("SELECT * FROM strategy_decisions WHERE status='executed'").fetchone())
        order=dict(conn.execute('SELECT * FROM paper_orders').fetchone())
        fill=dict(conn.execute('SELECT * FROM paper_fills').fetchone())
        assert decision['signal_id']==signal['signal_id']==order['strategy_signal_id']
        assert decision['order_id']==order['id']==fill['order_id']
        assert decision['fill_id']==fill['id']
        assert decision['execution_observation_id']==observed['id']
    summary=PaperAccount(db).summary()
    assert summary['cash']=='8000.000000' and summary['positions'][0]['quantity']==16
    before=PaperAccount(db).fills()
    engine.on_records([completed,observed,candle(db,49,1)])
    assert PaperAccount(db).fills()==before


def test_fill_history_exposes_actual_confirming_candle_for_marker_details(setup):
    db,clock,engine=setup;engine.configure(True);bar=confirm(setup,120);execute(setup,125)
    fill=engine.fills('AAPL','1m')[0]
    assert fill['signal_candle_open_timestamp']==bar['candle_open_timestamp']
    assert fill['signal_direction']=='BUY' and fill['signal_id']==engine.status()['last_signal']['signal_id']
