"""Opt-in, persistent SMA strategy; provider arrivals only, never replay or a broker."""
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging

from app.services.database import utc_timestamp
from app.services.candles import candle_bounds
from app.services.indicators import saved_snapshot
from app.services.normalization import SUPPORTED_SYMBOLS, INTERVALS
from app.services.market_repository import serialize
from app.services.paper_account import PaperAccount, OrderConflict, money, price_units, allocation_quantity

STRATEGY = 'sma20-50-long-v1'
logger = logging.getLogger(__name__)


def moment(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def scope_key(symbol, interval):
    return f'{STRATEGY}:{symbol}:{interval}'


def next_historical_open(available_at, confirming_end, candles):
    """Timing helper only; the separate historical runner is in services/backtests.py.

    Choose the next *available* opening, never a prior close or an opening already past
    at confirmation. Missing/invalid opens cannot be fabricated from another price.
    """
    boundary = max(moment(available_at),moment(confirming_end))
    for candle in sorted(candles,key=lambda row:row['candle_open_timestamp']):
        if moment(candle['candle_open_timestamp']) < boundary:
            continue
        try:
            price = price_units(candle.get('open'),round_quote=True)
        except (ValueError,TypeError):
            continue
        return {'candle_id':candle['id'],'timestamp':candle['candle_open_timestamp'],
                'execution_price':money(price),'execution_model':'historical_next_eligible_open'}
    return None


class StrategyService:
    def __init__(self,database,settings,clock=lambda:datetime.now(timezone.utc)):
        self.database,self.settings,self.clock=database,settings,clock
        self.runtime_error=None

    def configure(self,enabled,symbol=None,interval=None):
        if type(enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        now=utc_timestamp(self.clock())
        with self.database.transaction() as conn:
            current=conn.execute('SELECT * FROM strategy_config WHERE id=1').fetchone()
            symbol=symbol or current['symbol'];interval=interval or current['interval']
            if symbol not in SUPPORTED_SYMBOLS or interval not in INTERVALS:
                raise ValueError('Unsupported strategy symbol or interval')
            changed=(symbol,interval)!=(current['symbol'],current['interval'])
            if current['enabled'] and changed:
                raise OrderConflict('Disable automatic simulation before changing its symbol or interval')
            if enabled and (not current['enabled'] or changed):
                maximum=conn.execute('SELECT COALESCE(MAX(id),0) FROM observations').fetchone()[0]
                latest=conn.execute("""SELECT MAX(candle_open_timestamp) FROM observations WHERE symbol=?
                    AND candle_interval=? AND data_source='yahoo_finance' AND observation_type='constructed_candle'
                    AND candle_complete=1 AND data_mode IN ('live','delayed')""",(symbol,interval)).fetchone()[0]
                conn.execute('''INSERT INTO strategy_scopes(scope,symbol,interval,enabled_at,activation_after_id,last_completed_open)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET enabled_at=excluded.enabled_at,
                    activation_after_id=excluded.activation_after_id,last_completed_open=excluded.last_completed_open''',
                    (scope_key(symbol,interval),symbol,interval,now,maximum,latest))
            if not enabled:
                conn.execute("UPDATE strategy_decisions SET status='canceled',reason='strategy_disabled',updated_timestamp=? WHERE status='waiting'",(now,))
            conn.execute('UPDATE strategy_config SET enabled=?,symbol=?,interval=?,updated_timestamp=? WHERE id=1',
                         (int(enabled),symbol,interval,now))
        self.runtime_error=None
        return self.status()

    def on_records(self,records):
        # Called after market commit in the worker thread. A strategy error cannot break
        # provider ingestion/broadcast; suspend this engine visibly until operator action.
        if self.runtime_error:
            return
        try:
            with closing(self.database.read_connection()) as connection:
                selected=connection.execute('SELECT * FROM strategy_config WHERE id=1').fetchone()
            if not selected['enabled']:
                return
            for record in records:
                if record.get('symbol')!=selected['symbol'] or (record.get('observation_type')!='raw_provider' and record.get('candle_interval')!=selected['interval']):
                    continue
                if record.get('snapshot') or record.get('data_mode') not in ('live','delayed') or record.get('data_source')!='yahoo_finance':
                    continue
                self._record(record)
        except Exception as exc:
            self.runtime_error=f'strategy_suspended:{type(exc).__name__}'
            logger.exception('Automatic SIMULATED strategy suspended; market feed remains independent')

    def _record(self,record):
        with self.database.transaction() as conn:
            now=self.clock();timestamp=utc_timestamp(now)
            stored=conn.execute('SELECT * FROM observations WHERE id=?',(record['id'],)).fetchone()
            if stored is None:
                return
            record=serialize(stored)
            if record['data_source']!='yahoo_finance' or record['data_mode'] not in ('live','delayed'):
                return
            config=conn.execute('SELECT * FROM strategy_config WHERE id=1').fetchone()
            if not config['enabled'] or record['symbol']!=config['symbol']:
                return
            scope=scope_key(config['symbol'],config['interval'])
            state=conn.execute('SELECT * FROM strategy_scopes WHERE scope=?',(scope,)).fetchone()
            if state is None or record['id']<=state['activation_after_id']:
                return
            if record['observation_type']=='raw_provider':
                self._execute_waiting(conn,scope,record,now)
                return
            if record['observation_type']!='constructed_candle' or record['candle_interval']!=config['interval'] or not record['candle_complete']:
                return
            opening=record['candle_open_timestamp']
            end=utc_timestamp(candle_bounds(opening,config['interval'])[1])
            if moment(end)>now:
                return
            key=f"evaluation:{scope}:{record['id']}"
            if conn.execute('SELECT 1 FROM strategy_decisions WHERE decision_key=?',(key,)).fetchone():
                return
            if state['last_completed_open'] and opening<=state['last_completed_open']:
                latched=conn.execute('SELECT signal_id FROM strategy_signals WHERE scope=? AND candle_open_timestamp=?',(scope,opening)).fetchone()
                self._decision(conn,key,scope,record['id'],latched['signal_id'] if latched else None,'revision_ignored','historical_revision_not_reexecuted',timestamp)
                return
            conn.execute('UPDATE strategy_scopes SET last_completed_open=? WHERE scope=?',(opening,scope))
            if moment(end)<moment(state['enabled_at']) or (now-moment(end)).total_seconds()>self.settings.stale_seconds:
                self._decision(conn,key,scope,record['id'],None,'skipped','historical_or_stale_completion',timestamp)
                return
            data=saved_snapshot(self.database,config['symbol'],config['interval'],as_of_id=record['id'])
            point=next((p for p in data['points'] if p['id']==record['id']),None)
            if not point or not point['confirmed'] or point['signal']=='HOLD':
                reason=point['reason'] if point else 'no_completed_indicator_pair'
                self._decision(conn,key,scope,record['id'],None,'hold',reason,timestamp)
                return
            signal_id=hashlib.sha256(json.dumps([STRATEGY,config['symbol'],config['interval'],opening,point['signal']]).encode()).hexdigest()
            # Slot uniqueness is stronger than direction identity: revised opposite signals
            # at the same opening may not create another order.
            exists=conn.execute('SELECT signal_id FROM strategy_signals WHERE scope=? AND candle_open_timestamp=?',(scope,opening)).fetchone()
            if exists:
                self._decision(conn,key,scope,record['id'],exists['signal_id'],'revision_ignored','signal_slot_already_latched',timestamp)
                return
            timestamp=utc_timestamp(self.clock())
            maximum=conn.execute('SELECT COALESCE(MAX(id),0) FROM observations').fetchone()[0]
            inputs=[{'id':p['id'],'revision':p['revision'],'candle_open_timestamp':p['candle_open_timestamp']}
                    for p in data['points'] if p['candle_complete'] and p['candle_open_timestamp']<=opening][-51:]
            conn.execute('''INSERT INTO strategy_signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (signal_id,scope,STRATEGY,config['symbol'],config['interval'],opening,end,record['id'],
                 point['signal'],timestamp,maximum,str(point['sma20']),str(point['sma50']),json.dumps(inputs)))
            conn.execute("UPDATE strategy_decisions SET status='canceled',reason='superseded_by_new_crossover',updated_timestamp=? WHERE scope=? AND status='waiting'",(timestamp,scope))
            self._decision(conn,key,scope,record['id'],signal_id,'waiting','awaiting_later_executable_observation',timestamp)

    @staticmethod
    def _decision(conn,key,scope,candle_id,signal_id,status,reason,timestamp):
        conn.execute('''INSERT OR IGNORE INTO strategy_decisions
            (decision_key,scope,signal_id,candle_id,status,reason,created_timestamp,updated_timestamp)
            VALUES(?,?,?,?,?,?,?,?)''',(key,scope,signal_id,candle_id,status,reason,timestamp,timestamp))

    def _execute_waiting(self,conn,scope,record,now):
        pending=conn.execute('''SELECT d.id AS decision_id,s.* FROM strategy_decisions d
            JOIN strategy_signals s ON s.signal_id=d.signal_id WHERE d.scope=? AND d.status='waiting' ORDER BY d.id''',(scope,)).fetchall()
        if not pending:
            return
        source=moment(record['source_timestamp']);receipt=moment(record['received_timestamp'])
        # Source and receipt freshness are independent. Never execute an old/replayed,
        # backdated or future-clock quote, even if the socket just delivered it.
        if not 0 <= (now-source).total_seconds() <= self.settings.fresh_seconds or not 0 <= (now-receipt).total_seconds() <= self.settings.fresh_seconds:
            conn.execute("UPDATE strategy_decisions SET reason='awaiting_fresh_observed_price',updated_timestamp=? WHERE scope=? AND status='waiting'",(utc_timestamp(now),scope))
            return
        try:
            units=price_units(record.get('price'),round_quote=True)
        except (ValueError,TypeError):
            conn.execute("UPDATE strategy_decisions SET reason='awaiting_valid_execution_price',updated_timestamp=? WHERE scope=? AND status='waiting'",(utc_timestamp(now),scope))
            return
        for signal in pending:
            confirmed=moment(signal['confirmed_timestamp'])
            if record['id']<=signal['available_after_id'] or receipt<=confirmed or source<max(confirmed,moment(signal['candle_end_timestamp'])):
                continue
            owned=conn.execute('SELECT quantity FROM strategy_positions WHERE scope=? AND symbol=?',(scope,record['symbol'])).fetchone()
            held=owned['quantity'] if owned else 0
            cash=conn.execute('SELECT cash_units FROM simulated_accounts WHERE id=1').fetchone()[0]
            reason=None
            if signal['direction']=='BUY':
                quantity=allocation_quantity(cash, units)  # floor of 20% of available cash; no rounded-dollar budget.
                if held:reason='already_strategy_long'
                elif quantity<1:reason='insufficient_cash_for_one_share_at_20_percent'
                elif quantity>1_000_000:reason='quantity_exceeds_account_order_limit'
            else:
                quantity=held
                if not held:reason='no_strategy_position'
            order=None
            if not reason:
                order=PaperAccount(self.database,clock=self.clock).submit(client_order_id='strategy:'+signal['signal_id'],
                    symbol=record['symbol'],side=signal['direction'],quantity=quantity,execution_price=money(units),
                    strategy_signal_id=signal['signal_id'],connection=conn,strategy_scope=scope,execution_observation_id=record['id'])
                if order['status']!='filled':reason=order['rejection_reason'] or order['status']
            account=conn.execute('SELECT cash_units,realized_pl_units FROM simulated_accounts WHERE id=1').fetchone()
            position=conn.execute('SELECT quantity,cost_basis_units FROM paper_positions WHERE account_id=1 AND symbol=?',(record['symbol'],)).fetchone()
            state={'cash':money(account['cash_units']),'realized_pl':money(account['realized_pl_units']),
                   'symbol':record['symbol'],'quantity':position['quantity'] if position else 0,
                   'cost_basis':money(position['cost_basis_units']) if position else '0.000000'}
            conn.execute('''UPDATE strategy_decisions SET status=?,reason=?,quantity=?,execution_price_units=?,
                execution_observation_id=?,order_id=?,fill_id=?,account_state_json=?,updated_timestamp=? WHERE id=?''',
                ('skipped' if reason else 'executed',reason or 'first_eligible_observed_price',quantity,units,record['id'],
                 order['id'] if order else None,order['fill_id'] if order else None,json.dumps(state),utc_timestamp(now),signal['decision_id']))

    def status(self):
        with closing(self.database.read_connection()) as conn:
            conn.execute('BEGIN')
            config=dict(conn.execute('SELECT * FROM strategy_config WHERE id=1').fetchone())
            scope=scope_key(config['symbol'],config['interval'])
            signal=conn.execute('SELECT * FROM strategy_signals WHERE scope=? ORDER BY rowid DESC LIMIT 1',(scope,)).fetchone()
            last=conn.execute('SELECT * FROM strategy_decisions WHERE scope=? ORDER BY id DESC LIMIT 1',(scope,)).fetchone()
            action=conn.execute("SELECT * FROM strategy_decisions WHERE scope=? AND status IN ('executed','skipped','canceled') ORDER BY id DESC LIMIT 1",(scope,)).fetchone()
            managed=[dict(r) for r in conn.execute('SELECT * FROM strategy_positions WHERE quantity>0')]
        return {'mode':'SIMULATED','strategy':STRATEGY,'enabled':bool(config['enabled']),
            'configuration':{**config,'allocation_percent':20,'fast_period':20,'slow_period':50},
            'state':'suspended' if self.runtime_error else ('enabled' if config['enabled'] else 'disabled'),
            'reason':self.runtime_error or (last['reason'] if config['enabled'] and last else ('awaiting_next_confirmed_crossover' if config['enabled'] else 'automatic_simulation_off')),
            'error':self.runtime_error,'last_signal':dict(signal) if signal else None,
            'last_decision':self._serialize_decision(last),'last_action':self._serialize_decision(action),
            'managed_positions':managed,'account':PaperAccount(self.database,clock=self.clock).summary(),
            'execution_rule':'First fresh provider observation strictly received after confirmation; replay cannot execute',
            'historical_processing_enabled':False}

    @staticmethod
    def _serialize_decision(row):
        if row is None:return None
        value=dict(row);value['execution_price']=money(value.pop('execution_price_units'))
        raw=value.pop('account_state_json')
        value['account_state']=json.loads(raw) if raw else None
        return value

    def fills(self,symbol,interval):
        with closing(self.database.read_connection()) as conn:
            return [dict(row) for row in conn.execute('''SELECT f.id,f.order_id,f.symbol,f.side,f.quantity,
                f.execution_timestamp,f.execution_price_units,s.signal_id,s.interval,s.candle_open_timestamp AS signal_candle_open_timestamp,s.direction AS signal_direction,o.source_timestamp,o.received_timestamp,
                o.id AS observation_id FROM paper_fills f JOIN strategy_order_links l ON l.order_id=f.order_id
                JOIN strategy_signals s ON s.signal_id=(SELECT strategy_signal_id FROM paper_orders WHERE id=f.order_id)
                JOIN observations o ON o.id=l.observation_id WHERE s.scope=? ORDER BY f.id DESC LIMIT 1000''',
                (scope_key(symbol,interval),))]
