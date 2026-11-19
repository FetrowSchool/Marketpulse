"""Manual SIMULATED account. Integer micro-USD ledger; never contacts a brokerage."""
from contextlib import closing, nullcontext
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from datetime import datetime, timezone
import hashlib
import json

from app.services.database import utc_timestamp
from app.services.normalization import SUPPORTED_SYMBOLS

SCALE = 1_000_000
MAX_INT = 2**63 - 1
ASSUMPTIONS = {'mode': 'SIMULATED', 'currency': 'USD', 'long_only': True,
    'whole_shares_only': True, 'leverage': False, 'fees': '0', 'slippage_bps': 0,
    'execution_model': 'manual reference price, immediate whole-order simulated fill',
    'pending_model': 'no cash/share reservation; fixed creation reference price; revalidate on manual execution',
    'money_unit': '0.000001 USD', 'cost_allocation_rounding': 'half-even micro-USD; final sale releases all residual basis',
    'automatic_trading': 'separate opt-in SIMULATED strategy, default OFF'}


class OrderConflict(ValueError):
    pass


class OrderNotFound(ValueError):
    pass


def price_units(value, *, round_quote=False):
    if isinstance(value, bool):
        raise ValueError('Execution price must be a finite positive decimal')
    try:
        price = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid execution price') from exc
    if not price.is_finite() or not 0 < price <= 1_000_000:
        raise ValueError('Execution price must be positive and at most 1000000 USD')
    units = price * SCALE
    if round_quote:
        rounded = int(units.quantize(Decimal(1),rounding=ROUND_HALF_EVEN))
        if rounded <= 0:
            raise ValueError('Quote is below the valuation precision')
        return rounded
    if units != units.to_integral_value():
        raise ValueError('Execution price supports at most six decimal places')
    return int(units)


def allocation_quantity(cash_units, execution_price_units):
    """Maximum whole shares within the shared 20% cash allocation."""
    return (cash_units // 5) // execution_price_units


def allocated_basis(basis, quantity, held):
    # Exact rational half-even rounding without Decimal context precision limits.
    result, remainder = divmod(basis * quantity, held)
    if remainder * 2 > held or (remainder * 2 == held and result % 2):
        result += 1
    return result


def money(units):
    return format(Decimal(units) / SCALE, '.6f') if units is not None else None


class PaperAccount:
    def __init__(self, database, clock=lambda: datetime.now(timezone.utc)):
        self.database, self.clock = database, clock

    def _order(self, conn, identifier):
        row = conn.execute('SELECT * FROM paper_orders WHERE id=? AND account_id=1', (identifier,)).fetchone()
        if row is None:
            raise OrderNotFound('Simulated order not found')
        result = dict(row)
        result['execution_reference_price'] = money(result.pop('reference_price_units'))
        result.pop('request_hash')
        result['mode'] = 'SIMULATED'
        fill = conn.execute('SELECT id FROM paper_fills WHERE order_id=?', (identifier,)).fetchone()
        result['fill_id'] = fill['id'] if fill else None
        return result

    def submit(self, *, client_order_id, symbol, side, quantity, execution_price,
               execute_immediately=True, strategy_signal_id=None, connection=None,
               strategy_scope=None, execution_observation_id=None):
        if symbol not in SUPPORTED_SYMBOLS or side not in ('BUY', 'SELL'):
            raise ValueError('Unsupported symbol or side')
        if type(quantity) is not int or not 1 <= quantity <= 1_000_000:
            raise ValueError('Quantity must be a positive whole number at most 1000000')
        if not isinstance(client_order_id, str) or not 1 <= len(client_order_id) <= 100 or not client_order_id.strip():
            raise ValueError('A nonempty client_order_id is required')
        if type(execute_immediately) is not bool:
            raise ValueError('execute_immediately must be a boolean')
        if strategy_signal_id is not None and (not isinstance(strategy_signal_id, str) or not 1 <= len(strategy_signal_id) <= 128):
            raise ValueError('Invalid strategy signal reference')
        price = price_units(execution_price)
        fingerprint = hashlib.sha256(json.dumps([symbol,side,quantity,price,execute_immediately,strategy_signal_id]).encode()).hexdigest()
        timestamp = utc_timestamp(self.clock())
        with (nullcontext(connection) if connection is not None else self.database.transaction()) as conn:
            previous = conn.execute('SELECT id,request_hash FROM paper_orders WHERE account_id=1 AND client_order_id=?', (client_order_id,)).fetchone()
            if previous:
                if previous['request_hash'] != fingerprint:
                    raise OrderConflict('client_order_id already belongs to a different order')
                return self._order(conn, previous['id'])
            order_id = conn.execute('''INSERT INTO paper_orders
                (account_id,client_order_id,request_hash,symbol,side,quantity,reference_price_units,status,
                 created_timestamp,updated_timestamp,strategy_signal_id)
                VALUES(1,?,?,?,?,?,?,'pending',?,?,?)''',
                (client_order_id,fingerprint,symbol,side,quantity,price,timestamp,timestamp,strategy_signal_id)).lastrowid
            if strategy_scope is not None:
                conn.execute('INSERT INTO strategy_order_links(order_id,scope,observation_id) VALUES(?,?,?)',
                             (order_id,strategy_scope,execution_observation_id))
            if execute_immediately:
                self._execute(conn, order_id)
            return self._order(conn, order_id)

    def _execute(self, conn, identifier):
        order = conn.execute('SELECT * FROM paper_orders WHERE id=? AND account_id=1', (identifier,)).fetchone()
        if order is None:
            raise OrderNotFound('Simulated order not found')
        if order['status'] == 'filled':
            return  # UNIQUE(order_id) is the additional database guard.
        if order['status'] != 'pending':
            raise OrderConflict('Only pending simulated orders can execute')
        account = conn.execute('SELECT * FROM simulated_accounts WHERE id=1').fetchone()
        position = conn.execute('SELECT * FROM paper_positions WHERE account_id=1 AND symbol=?', (order['symbol'],)).fetchone()
        held, basis = (position['quantity'],position['cost_basis_units']) if position else (0,0)
        ownership = conn.execute('SELECT * FROM strategy_order_links WHERE order_id=?',(identifier,)).fetchone()
        managed = conn.execute('SELECT COALESCE(SUM(quantity),0) FROM strategy_positions WHERE symbol=?',(order['symbol'],)).fetchone()[0]
        owned = conn.execute('SELECT quantity FROM strategy_positions WHERE scope=? AND symbol=?',(ownership['scope'],order['symbol'])).fetchone() if ownership else None
        sellable = (owned['quantity'] if owned else 0) if ownership else held-managed
        quantity, total = order['quantity'], order['quantity'] * order['reference_price_units']
        reason = None
        if order['side'] == 'BUY' and total > account['cash_units']:
            reason = 'insufficient_cash'
        elif order['side'] == 'SELL' and quantity > min(held,sellable):
            reason = 'insufficient_strategy_shares' if ownership else ('insufficient_manual_shares' if managed else 'insufficient_shares')
        elif order['side'] == 'SELL' and account['cash_units'] + total > MAX_INT:
            reason = 'account_limit_exceeded'
        timestamp = utc_timestamp(self.clock())
        if reason:
            conn.execute("UPDATE paper_orders SET status='rejected',rejection_reason=?,updated_timestamp=? WHERE id=?", (reason,timestamp,identifier))
            return
        released = realized = 0
        if order['side'] == 'BUY':
            cash, held, basis = account['cash_units']-total, held+quantity, basis+total
        else:
            released = basis if quantity == held else allocated_basis(basis,quantity,held)
            cash, held, basis = account['cash_units']+total, held-quantity, basis-released
            realized = total-released
        if basis > MAX_INT or held > MAX_INT or not -MAX_INT <= account['realized_pl_units']+realized <= MAX_INT:
            conn.execute("UPDATE paper_orders SET status='rejected',rejection_reason='account_limit_exceeded',updated_timestamp=? WHERE id=?", (timestamp,identifier))
            return
        conn.execute('UPDATE simulated_accounts SET cash_units=?,realized_pl_units=realized_pl_units+? WHERE id=1', (cash,realized))
        conn.execute('''INSERT INTO paper_positions(account_id,symbol,quantity,cost_basis_units) VALUES(1,?,?,?)
            ON CONFLICT(account_id,symbol) DO UPDATE SET quantity=excluded.quantity,cost_basis_units=excluded.cost_basis_units''',
            (order['symbol'],held,basis))
        conn.execute('''INSERT INTO paper_fills(order_id,account_id,symbol,side,quantity,execution_price_units,
            execution_timestamp,fees_units,slippage_bps,price_source,cost_basis_released_units,realized_pl_units,
            cash_after_units,position_quantity_after) VALUES(?,1,?,?,?,?,?,0,0,?,?,?,?,?)''',
            (identifier,order['symbol'],order['side'],quantity,order['reference_price_units'],timestamp,'observed_quote' if ownership else 'manual_reference',released,realized,cash,held))
        if ownership:
            owned_quantity = (owned['quantity'] if owned else 0) + (quantity if order['side']=='BUY' else -quantity)
            conn.execute('''INSERT INTO strategy_positions(scope,symbol,quantity) VALUES(?,?,?)
                ON CONFLICT(scope,symbol) DO UPDATE SET quantity=excluded.quantity''',
                (ownership['scope'],order['symbol'],owned_quantity))
        conn.execute("UPDATE paper_orders SET status='filled',updated_timestamp=? WHERE id=?", (timestamp,identifier))

    def execute(self, identifier):
        with self.database.transaction() as conn:
            self._execute(conn, identifier)
            return self._order(conn, identifier)

    def cancel(self, identifier):
        with self.database.transaction() as conn:
            current = self._order(conn, identifier)
            if current['status'] == 'canceled':
                return current
            if current['status'] != 'pending':
                raise OrderConflict('Only pending simulated orders can be canceled')
            conn.execute("UPDATE paper_orders SET status='canceled',updated_timestamp=? WHERE id=?", (utc_timestamp(self.clock()),identifier))
            return self._order(conn, identifier)

    def orders(self, limit=100):
        with closing(self.database.read_connection()) as conn:
            conn.execute('BEGIN')
            ids = conn.execute('SELECT id FROM paper_orders WHERE account_id=1 ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
            return [self._order(conn,row['id']) for row in ids]

    def fills(self, limit=100):
        with closing(self.database.read_connection()) as conn:
            rows = conn.execute('''SELECT f.*,l.scope AS strategy_scope,l.observation_id AS execution_observation_id FROM paper_fills f
                LEFT JOIN strategy_order_links l ON l.order_id=f.order_id WHERE f.account_id=1 ORDER BY f.id DESC LIMIT ?''', (limit,)).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            for field in ('execution_price','fees','cost_basis_released','realized_pl','cash_after'):
                value[field] = money(value.pop(field+'_units'))
            result.append({**value,'mode':'SIMULATED'})
        return result

    def summary(self):
        now = self.clock()
        with closing(self.database.read_connection()) as conn:
            conn.execute('BEGIN')
            account = dict(conn.execute('SELECT * FROM simulated_accounts WHERE id=1').fetchone())
            rows = conn.execute('SELECT * FROM paper_positions WHERE account_id=1 AND quantity>0 ORDER BY symbol').fetchall()
            positions, total_value, total_basis, missing = [], 0, 0, []
            for row in rows:
                quote = conn.execute('''SELECT * FROM observations o WHERE symbol=? AND data_source='yahoo_finance'
                    AND observation_type='raw_provider' AND NOT EXISTS (
                      SELECT 1 FROM observations n WHERE n.symbol=o.symbol AND n.data_source=o.data_source
                        AND n.observation_type=o.observation_type AND n.source_observation_id=o.source_observation_id
                        AND n.revision>o.revision)
                    ORDER BY source_timestamp DESC,id DESC LIMIT 1''', (row['symbol'],)).fetchone()
                mark, metadata = None, None
                if quote:
                    try:
                        mark = price_units(json.loads(quote['payload_json']).get('price'),round_quote=True)
                    except (ValueError,TypeError,InvalidOperation):
                        pass
                    metadata = {'observation_id':quote['id'],'data_source':quote['data_source'],'data_mode':quote['data_mode'],
                        'source_timestamp':quote['source_timestamp'],'received_timestamp':quote['received_timestamp'],
                        'source_age_seconds':(now-datetime.fromisoformat(quote['source_timestamp'].replace('Z','+00:00'))).total_seconds()}
                value = row['quantity']*mark if mark is not None else None
                if value is None: missing.append(row['symbol'])
                else: total_value += value
                total_basis += row['cost_basis_units']
                average = (Decimal(row['cost_basis_units'])/row['quantity']/SCALE).quantize(Decimal('.000001'),rounding=ROUND_HALF_EVEN)
                strategy_quantity = conn.execute('SELECT COALESCE(SUM(quantity),0) FROM strategy_positions WHERE symbol=?',(row['symbol'],)).fetchone()[0]
                positions.append({'strategy_quantity':strategy_quantity,'manual_quantity':row['quantity']-strategy_quantity,'symbol':row['symbol'],'quantity':row['quantity'],'average_entry_price':format(average,'.6f'),
                    'cost_basis':money(row['cost_basis_units']),'current_price':money(mark),'market_value':money(value),
                    'unrealized_pl':money(value-row['cost_basis_units']) if value is not None else None,'mark':metadata})
        return {'mode':'SIMULATED','account_id':1,'currency':'USD','starting_cash':money(account['starting_cash_units']),
            'cash':money(account['cash_units']),'realized_pl':money(account['realized_pl_units']),
            'equity':money(account['cash_units']+total_value) if not missing else None,
            'market_value':money(total_value) if not missing else None,'remaining_cost_basis':money(total_basis),
            'unrealized_pl':money(total_value-total_basis) if not missing else None,'positions':positions,
            'valuation_complete':not missing,'unpriced_symbols':missing,'valued_at':utc_timestamp(now),
            'valuation_note':'Last saved source quotes, possibly delayed/stale; not live execution prices',
            'assumptions':ASSUMPTIONS}
