"""Deterministic paper-ledger examples. No brokerage or real execution."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.services.database import Database
from app.services.paper_account import PaperAccount,OrderConflict,OrderNotFound

NOW=datetime(2026,1,6,15,tzinfo=timezone.utc)


def account(db):return PaperAccount(db,clock=lambda:NOW)


def order(service,key='buy',**values):
    return service.submit(**{'client_order_id':key,'symbol':'AAPL','side':'BUY','quantity':10,'execution_price':'100',**values})


def mark(db,price,symbol='AAPL'):
    db.insert_observation(symbol=symbol,data_source='yahoo_finance',observation_type='raw_provider',data_mode='simulated',
        source_observation_id='explicit-paper-valuation-fixture',source_timestamp=NOW,received_timestamp=NOW,
        payload={'price':price,'fixture':True})


def test_initial_account_and_missing_quote_is_explicit(db):
    service=account(db);summary=service.summary()
    assert summary['mode']=='SIMULATED' and summary['starting_cash']=='10000.000000'
    assert summary['cash']==summary['equity']=='10000.000000'
    assert summary['realized_pl']==summary['unrealized_pl']=='0.000000' and not summary['positions']
    order(service)
    summary=service.summary()
    assert summary['cash']=='9000.000000' and summary['equity'] is None
    assert summary['unpriced_symbols']==['AAPL'] and summary['positions'][0]['current_price'] is None


def test_independent_average_cost_partial_sale_and_equity_identity(db):
    # Buy10x100 +10x120 => cost2200,20 shares,avg110,cash7800.
    # Mark130 => value2600,unrealized400,equity10400.
    # Sell5x140 => proceeds700,releasedbasis550,realized150,cash8500.
    # Remaining15x130 =>1950,basis1650,unrealized300,equity10450=10000+150+300.
    service=account(db)
    order(service);order(service,'buy2',execution_price='120')
    mark(db,130)
    before=service.summary();position=before['positions'][0]
    assert position['quantity']==20 and position['average_entry_price']=='110.000000'
    assert before['cash']=='7800.000000' and before['equity']=='10400.000000'
    assert before['unrealized_pl']=='400.000000' and before['realized_pl']=='0.000000'
    order(service,'sale',side='SELL',quantity=5,execution_price='140')
    after=service.summary();position=after['positions'][0]
    assert after['cash']=='8500.000000' and after['realized_pl']=='150.000000'
    assert position['cost_basis']=='1650.000000' and position['average_entry_price']=='110.000000'
    assert after['unrealized_pl']=='300.000000' and after['equity']=='10450.000000'
    assert Decimal(after['equity'])==Decimal(after['starting_cash'])+Decimal(after['realized_pl'])+Decimal(after['unrealized_pl'])
    fill=service.fills()[0]
    assert fill['fees']=='0.000000' and fill['slippage_bps']==0
    assert fill['cost_basis_released']=='550.000000' and fill['price_source']=='manual_reference'
    order(service,'close',side='SELL',quantity=15,execution_price='90')
    final=service.summary()
    assert not final['positions'] and final['cash']==final['equity']=='9850.000000'
    assert final['realized_pl']=='-150.000000' and final['unrealized_pl']=='0.000000'


def test_fractional_average_rounding_conserves_basis_and_micro_precision(db):
    service=account(db)
    order(service,'one',quantity=1,execution_price='0.100001')
    order(service,'two',quantity=2,execution_price='0.100000')
    assert service.summary()['positions'][0]['cost_basis']=='0.300001'
    for i in range(3):order(service,f'sell{i}',side='SELL',quantity=1,execution_price='0.200000')
    fills=[f for f in service.fills() if f['side']=='SELL']
    assert sum(Decimal(f['cost_basis_released']) for f in fills)==Decimal('0.300001')
    assert service.summary()['realized_pl']=='0.299999'
    assert service.summary()['cash']=='10000.299999'


def test_insufficient_cash_and_shares_are_retained_rejections(db):
    service=account(db)
    assert order(service,quantity=101)['rejection_reason']=='insufficient_cash'
    assert order(service,'sell',side='SELL',quantity=1)['rejection_reason']=='insufficient_shares'
    assert not service.fills() and service.summary()['cash']=='10000.000000'
    assert {r['status'] for r in service.orders()}=={'rejected'}


@pytest.mark.parametrize('values',[
    {'quantity':0},{'quantity':-1},{'quantity':1.5},{'quantity':True},{'quantity':1000001},
    {'symbol':'BAD'},{'side':'SHORT'},{'execution_price':0},{'execution_price':-1},
    {'execution_price':'NaN'},{'execution_price':'Infinity'},{'execution_price':True},
    {'execution_price':'0.0000001'},{'execution_price':'1000001'},{'client_order_id':' '},
])
def test_invalid_requests_do_not_create_orders(db,values):
    with pytest.raises(ValueError):order(account(db),**values)
    assert not account(db).orders() and not account(db).fills()


def test_idempotent_submission_execution_and_conflicting_key(db):
    service=account(db)
    first=order(service);again=order(service)
    assert first==again and len(service.fills())==1
    assert service.execute(first['id'])==first
    with pytest.raises(OrderConflict):order(service,quantity=11)
    assert len(service.fills())==1 and service.summary()['cash']=='9000.000000'


def test_pending_cancel_revalidation_and_signal_reference(db):
    service=account(db)
    pending=order(service,execute_immediately=False,strategy_signal_id='derived-reference-only')
    assert pending['status']=='pending' and service.summary()['cash']=='10000.000000'
    canceled=service.cancel(pending['id']);assert canceled['status']=='canceled'
    assert service.cancel(pending['id'])==canceled
    with pytest.raises(OrderConflict):service.execute(pending['id'])
    with pytest.raises(OrderNotFound):service.cancel(999)
    pending=order(service,'big-pending',quantity=100,execute_immediately=False)
    order(service,'spend',quantity=1)
    assert service.execute(pending['id'])['status']=='rejected'
    with pytest.raises(OrderConflict):service.cancel(pending['id'])
    assert len(service.fills())==1


def test_concurrent_duplicate_requests_only_fill_once(db):
    service=account(db)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:order(service),range(4)))
    assert len({r['id'] for r in results})==1 and len(service.fills())==1
    assert service.summary()['cash']=='9000.000000'


def test_fill_failure_rolls_back_all_accounting_and_order(db):
    service=account(db)
    with db.transaction() as conn:
        conn.execute("CREATE TRIGGER test_fail_fill BEFORE INSERT ON paper_fills BEGIN SELECT RAISE(ABORT,'explicit simulated failure'); END")
    with pytest.raises(sqlite3.IntegrityError):order(service)
    assert service.summary()['cash']=='10000.000000' and not service.orders() and not service.summary()['positions']


def test_additive_initialization_restart_and_market_rows_preserved(db):
    mark(db,110);observations=db.retrieve();order(account(db))
    before=account(db).summary();db.initialize();Database(db.path).initialize()
    assert account(Database(db.path)).summary()==before
    assert db.retrieve()==observations and len(account(db).fills())==1
    with closing(db.connect()) as conn,pytest.raises(sqlite3.IntegrityError):
        conn.execute('DELETE FROM paper_fills')


def test_paper_api_validation_histories_and_idempotency(db,monkeypatch):
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    with TestClient(app) as client:
        assert client.get('/api/paper/account').json()['cash']=='10000.000000'
        body={'client_order_id':'api1','symbol':'MSFT','side':'BUY','quantity':2,'execution_price':'50','execute_immediately':False}
        pending=client.post('/api/paper/orders',json=body).json()
        assert pending['status']=='pending'
        filled=client.post(f"/api/paper/orders/{pending['id']}/execute").json()
        assert filled['status']=='filled'
        assert client.post('/api/paper/orders',json=body).json()==filled
        assert client.get('/api/paper/positions').json()['positions'][0]['quantity']==2
        assert len(client.get('/api/paper/orders').json()['orders'])==1
        assert client.get('/api/paper/trades').json()==client.get('/api/paper/fills').json()
        assert client.post(f"/api/paper/orders/{pending['id']}/cancel").status_code==409
        assert client.post('/api/paper/orders/999/execute').status_code==404
        for field,value in [('quantity',1.5),('quantity',True),('symbol','BAD'),('execution_price','NaN'),('execution_price','-1')]:
            assert client.post('/api/paper/orders',json={**body,field:value}).status_code==422
        assert client.get('/api/paper/fills?limit=1001').status_code==422
        def fail():raise sqlite3.OperationalError('private database path')
        monkeypatch.setattr(app.state.database,'read_connection',fail)
        response=client.get('/api/paper/account')
        assert response.status_code==503 and 'private database path' not in response.text


def test_cost_allocation_exact_ties_and_quote_rounding(db):
    from app.services.paper_account import allocated_basis
    assert allocated_basis(1,1,2)==0  # 0.5 -> even0
    assert allocated_basis(3,1,2)==2  # 1.5 -> even2
    assert allocated_basis(9_000_000_000_000_001,1,2)==4_500_000_000_000_000
    order(account(db));mark(db,100.1234567)
    result=account(db).summary()
    assert result['positions'][0]['current_price']=='100.123457'
    assert result['positions'][0]['market_value']=='1001.234570'


def test_concurrent_distinct_buys_cannot_overspend_cash(db):
    service=account(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda key:order(service,key,quantity=60,execution_price='100'),['first','second']))
    assert sorted(row['status'] for row in outcomes)==['filled','rejected']
    assert service.summary()['cash']=='4000.000000'
    assert service.summary()['positions'][0]['quantity']==60 and len(service.fills())==1


def test_second_independent_decimal_accounting_table_and_rejections(db):
    # Hand arithmetic in cents:29940+71470=101410 cost/10=10141 average.
    # Sell4 releases40564, proceeds41680 => realized1116; remaining60846.
    # Mark10300:6*10300-60846=954; equity940270+61800=1002070.
    service=account(db)
    order(service,'reference-a',quantity=3,execution_price='99.80')
    order(service,'reference-b',quantity=7,execution_price='102.10')
    mark(db,103)
    state=service.summary()
    assert (state['cash'],state['equity'],state['unrealized_pl'])==('8985.900000','10015.900000','15.900000')
    assert state['positions'][0]['average_entry_price']=='101.410000'
    order(service,'reference-sale',side='SELL',quantity=4,execution_price='104.20')
    state=service.summary();position=state['positions'][0]
    assert position['quantity']==6 and position['cost_basis']=='608.460000'
    assert (state['cash'],state['realized_pl'],state['unrealized_pl'],state['equity'])==('9402.700000','11.160000','9.540000','10020.700000')
    assert Decimal(state['equity'])==Decimal('10000')+Decimal(state['realized_pl'])+Decimal(state['unrealized_pl'])
    fills=service.fills()
    for key,side,quantity,price in [('too-expensive','BUY',1000,'100'),('too-many-shares','SELL',7,'100')]:
        rejected=order(service,key,side=side,quantity=quantity,execution_price=price)
        assert rejected['status']=='rejected'
        assert service.fills()==fills and service.summary()==state
    order(service,'reference-close',side='SELL',quantity=6,execution_price='98.50')
    state=service.summary()
    assert state['cash']==state['equity']=='9993.700000'
    assert state['realized_pl']=='-6.300000' and state['unrealized_pl']=='0.000000'
    assert all(f['fees']=='0.000000' for f in service.fills())
