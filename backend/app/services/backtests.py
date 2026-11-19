"""Receipt-aware historical events; isolated integer-money account, no live writes."""
from collections import deque
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math

from app.services.database import utc_timestamp
from app.services.indicators import sma_step
from app.services.market_repository import serialize
from app.services.normalization import INTERVALS, SUPPORTED_SYMBOLS, SOURCE
from app.services.paper_account import SCALE, allocation_quantity, money, price_units

MAX_CANDLES = 10000
ASSUMPTIONS = {
    'mode': 'BACKTEST · SIMULATED', 'fees': '0', 'slippage_bps': 0,
    'allocation_percent': 20, 'whole_shares': True, 'long_only': True,
    'execution': 'Next eligible completed candle open after signal availability; never signal close',
    'revisions': 'First completed revision only; later corrections excluded',
    'availability': 'max(candle end, recorded receipt timestamp)',
    'liquidity': 'Whole order filled at recorded open; no spread, market impact or liquidity model',
}


def moment(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate_config(config):
    if config['symbol'] not in SUPPORTED_SYMBOLS or config['interval'] not in INTERVALS:
        raise ValueError('Unsupported symbol or interval')
    if config['candle_type'] not in ('constructed_candle', 'provider_candle'):
        raise ValueError('Invalid candle type')
    if not 1 <= config['fast_period'] < config['slow_period'] <= 500:
        raise ValueError('Require 1 <= fast SMA < slow SMA <= 500')
    if moment(config['start']) >= moment(config['end']):
        raise ValueError('Start must precede end (exclusive)')
    price_units(config['starting_balance'])


def prepare(rows, config):
    """Do not select final revised history. Retain first completed receipt per opening."""
    validate_config(config)
    selected, incomplete, duplicates = {}, 0, 0
    for row in sorted(rows, key=lambda r: (r['received_timestamp'], r['id'])):
        if row['symbol'] != config['symbol'] or row['candle_interval'] != config['interval'] or row['observation_type'] != config['candle_type'] or row['data_source'] != SOURCE:
            raise ValueError('Mixed source, symbol, interval or candle type')
        opening = utc_timestamp(row['candle_open_timestamp'])
        if not config['start'] <= opening < config['end']:
            continue
        if not row['candle_complete']:
            incomplete += 1
            continue
        if opening in selected:
            duplicates += 1
            continue
        selected[opening] = dict(row)
    candles = sorted(selected.values(), key=lambda r: r['candle_open_timestamp'])
    if len(candles) > MAX_CANDLES:
        raise ValueError(f'Select at most {MAX_CANDLES} candles; narrow the date range')
    for row in candles:
        values = [row.get(k) for k in ('open', 'high', 'low', 'close')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError(f"Candle #{row['id']} has missing/invalid OHLC")
        o, h, l, c = values
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError(f"Candle #{row['id']} has inconsistent OHLC")
        if row.get('volume') is not None and (not math.isfinite(row['volume']) or row['volume'] < 0):
            raise ValueError('Invalid volume')
        price_units(o, round_quote=True)
        row['candle_open_timestamp'] = utc_timestamp(row['candle_open_timestamp'])
        row['received_timestamp'] = utc_timestamp(row['received_timestamp'])
        row['source_timestamp'] = utc_timestamp(row['source_timestamp'])
        row['available_at'] = max(row['received_timestamp'], utc_timestamp(moment(row['candle_open_timestamp']) + timedelta(seconds=INTERVALS[config['interval']])))
    seconds = INTERVALS[config['interval']]
    gaps = sum(max(0, int((moment(b['candle_open_timestamp']) - moment(a['candle_open_timestamp'])).total_seconds()) // seconds - 1) for a, b in zip(candles, candles[1:]))
    return candles, {'incomplete_rows_excluded': incomplete, 'later_completed_versions_excluded': duplicates,
                     'missing_interval_slots': gaps, 'warmup_before_start': False}


def simulate(rows, config):
    candles, quality = prepare(rows, config)
    if len(candles) < config['slow_period'] + 1:
        raise ValueError(f"Insufficient completed history: need at least {config['slow_period'] + 1}, found {len(candles)}")
    available_count = sum(row['available_at'] <= config['end'] for row in candles)
    if available_count < config['slow_period'] + 1:
        raise ValueError(f'Insufficient completed history available by end: found {available_count}')
    quality['completed_available_by_end'] = available_count
    # Closure events occur only when recorded information became available. Open events
    # reveal only open, not the candle's future close. Completed dataset membership is
    # an explicit historical coverage restriction, never a signal input.
    events = []
    for row in candles:
        events.extend([(row['available_at'], 0, row['id'], 'close', row),
                       (row['candle_open_timestamp'], 1, row['id'], 'open', row)])
    events.sort(key=lambda e: e[:3])
    initial = price_units(config['starting_balance'])
    cash, held, basis, realized, mark = initial, 0, 0, 0, None
    peak, max_drawdown = initial, Decimal(0)
    fills, trades, decisions, curve = [], [], [], []
    window = deque(maxlen=config['slow_period'])
    previous, group, last_opening, pending, entry = None, None, None, None, None
    boundary = config['end']
    mark_time = None
    for timestamp, _, _, kind, row in events:
        if timestamp > boundary or (kind == 'open' and timestamp == boundary):
            continue
        if kind == 'open':
            # Execution only at a new opening after confirmation, never a late candle's
            # already-passed open. No pending order depends on this candle's close.
            if pending is not None and group != (row['data_source'], row['observation_type'], row['data_mode']):
                pending.update(status='canceled', reason='provenance_changed'); pending = None
            if pending is not None and timestamp >= pending['available_at'] and timestamp > pending['candle_open_timestamp']:
                units = price_units(row['open'], round_quote=True)
                side = pending['signal']
                quantity = allocation_quantity(cash, units) if side == 'BUY' and held == 0 else held if side == 'SELL' else 0
                reason = 'already_long' if side == 'BUY' and held else 'insufficient_cash' if side == 'BUY' else 'no_open_position'
                if quantity > 1_000_000:
                    quantity, reason = 0, 'quantity_exceeds_account_limit'
                if quantity:
                    if side == 'BUY':
                        cash -= quantity * units; held = quantity; basis = quantity * units
                        entry = {'entry_timestamp': timestamp, 'entry_price': money(units), 'quantity': quantity, 'entry_candle_id': row['id']}
                    else:
                        proceeds = quantity * units; profit = proceeds - basis
                        cash += proceeds; realized += profit
                        trades.append({**entry, 'exit_timestamp': timestamp, 'exit_price': money(units), 'exit_candle_id': row['id'], 'realized_pl': money(profit)})
                        held, basis, entry = 0, 0, None
                    fills.append({'side': side, 'quantity': quantity, 'price': money(units), 'timestamp': timestamp,
                                  'candle_id': row['id'], 'signal_candle_id': pending['candle_id'], 'signal_available_at': pending['available_at'], 'fees': '0.000000', 'slippage_bps': 0})
                    pending.update(status='filled', execution_candle_id=row['id'], reason='next_eligible_open')
                else:
                    pending.update(status='skipped', reason=reason)
                pending = None
            mark = price_units(row['open'], round_quote=True)
            mark_time = timestamp
        else:
            opening = row['candle_open_timestamp']
            if last_opening is not None and opening <= last_opening:
                # A late older candle is preserved in input but cannot rewrite prior
                # decisions or append its close as if it were a new current candle.
                decisions.append({'candle_id': row['id'], 'signal': 'HOLD', 'status': 'ignored', 'reason': 'out_of_order_completion', 'available_at': timestamp})
                continue
            last_opening = opening
            current_group = (row['data_source'], row['observation_type'], row['data_mode'])
            if group != current_group:
                window.clear(); previous = None; group = current_group
                if pending:
                    pending.update(status='canceled', reason='provenance_changed'); pending = None
            window.append(Decimal(str(row['close'])))
            fast, slow, signal, confirmed, reason = sma_step(list(window), previous, config['fast_period'], config['slow_period'])
            if fast is not None and slow is not None:
                previous = fast, slow
            decision = {'candle_id': row['id'], 'candle_open_timestamp': opening, 'available_at': timestamp,
                        'sma_fast': str(fast) if fast is not None else None, 'sma_slow': str(slow) if slow is not None else None,
                        'signal': signal, 'confirmed': confirmed, 'status': 'hold', 'reason': reason}
            decisions.append(decision)
            if confirmed and signal != 'HOLD':
                if pending:
                    pending.update(status='canceled', reason='superseded_signal')
                decision.update(status='unfilled', reason='no_eligible_next_open')
                pending = decision
            source_end = utc_timestamp(moment(opening) + timedelta(seconds=INTERVALS[config['interval']]))
            if mark_time is None or source_end >= mark_time:
                mark = price_units(row['close'], round_quote=True)
                mark_time = source_end
        equity = cash + held * mark
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, Decimal(peak - equity) / Decimal(peak))
        curve.append({'timestamp': timestamp, 'event': kind, 'candle_id': row['id'], 'equity': money(equity), 'cash': money(cash), 'quantity': held})
    ending = cash + held * mark if mark is not None else cash
    wins = sum(Decimal(t['realized_pl']) > 0 for t in trades)
    input_data = {'configuration': config, 'candles': candles}
    return {'mode': 'BACKTEST · SIMULATED', 'configuration': config, 'assumptions': ASSUMPTIONS,
            'input_hash': hashlib.sha256(canonical(input_data).encode()).hexdigest(),
            'input_candles': [{'id': r['id'], 'revision': r['revision'], 'opening': r['candle_open_timestamp'], 'available_at': r['available_at'], 'data_mode': r['data_mode']} for r in candles],
            'quality': quality, 'summary': {'starting_equity': money(initial), 'ending_equity': money(ending),
                'total_return_percent': str(Decimal(ending - initial) / Decimal(initial) * 100),
                'realized_pl': money(realized), 'unrealized_pl': money(held * mark - basis) if held else money(0),
                'completed_trades': len(trades), 'fill_count': len(fills), 'win_rate_percent': str(Decimal(wins) / Decimal(len(trades)) * 100) if trades else None,
                'max_drawdown_percent': str(max_drawdown * 100), 'ending_cash': money(cash), 'open_quantity': held},
            'equity_curve': curve, 'trades': trades, 'fills': fills, 'decisions': decisions}


class Backtests:
    def __init__(self, database):
        self.database = database

    def run(self, config):
        validate_config(config)
        with closing(self.database.read_connection()) as conn:
            conn.execute('BEGIN')
            maximum = conn.execute('SELECT COALESCE(MAX(id),0) FROM observations').fetchone()[0]
            rows = [dict(row) for row in conn.execute('''SELECT * FROM observations WHERE symbol=?
                AND data_source=? AND candle_interval=? AND observation_type=?
                AND candle_open_timestamp>=? AND candle_open_timestamp<? AND id<=?
                ORDER BY received_timestamp,id LIMIT 100001''', (config['symbol'], SOURCE, config['interval'], config['candle_type'], config['start'], config['end'], maximum))]
        if len(rows) > 100000:
            raise ValueError('Too many observation revisions; narrow the date range')
        result = simulate(rows, config)
        result['snapshot_max_id'] = maximum
        with self.database.transaction() as conn:
            cursor = conn.execute('INSERT INTO backtest_runs(created_timestamp,input_hash,configuration_json,result_json) VALUES(?,?,?,?)',
                (utc_timestamp(datetime.now(timezone.utc)), result['input_hash'], canonical(config), canonical(result)))
            identifier = cursor.lastrowid
        return {'id': identifier, **result}

    def get(self, identifier):
        with closing(self.database.read_connection()) as conn:
            row = conn.execute('SELECT result_json FROM backtest_runs WHERE id=?', (identifier,)).fetchone()
        return {'id': identifier, **json.loads(row[0])} if row else None

    def chart(self, identifier):
        """Read the exact immutable input versions and already-recorded decisions/fills.

        This is visualization only: never recalculate signals from today's revisions.
        """
        result = self.get(identifier)
        if result is None:
            return None
        config = result['configuration']
        inputs = result['input_candles']
        if len(inputs) > MAX_CANDLES:
            raise ValueError('Backtest chart exceeds supported candle limit')
        ids = list(dict.fromkeys(row['id'] for row in inputs))
        saved = {}
        with closing(self.database.read_connection()) as conn:
            conn.execute('BEGIN')
            for start in range(0, len(ids), 400):
                chunk = ids[start:start + 400]
                for row in conn.execute('SELECT * FROM observations WHERE id IN (' + ','.join('?' for _ in chunk) + ')', chunk):
                    saved[row['id']] = serialize(row)
        candles = []
        for original in inputs:
            row = saved.get(original['id'])
            if row is None or row['revision'] != original['revision'] or row['symbol'] != config['symbol'] or row['candle_interval'] != config['interval'] or row['observation_type'] != config['candle_type'] or row['candle_open_timestamp'] != original['opening']:
                raise ValueError('Saved backtest candle snapshot is unavailable or inconsistent')
            candles.append(row)
        points = []
        by_id = {row['id']: row for row in candles}
        for decision in result['decisions']:
            row = by_id.get(decision['candle_id'])
            if row is None or decision.get('reason') == 'out_of_order_completion':
                continue
            signal_id = hashlib.sha256(canonical(['backtest-sma', result['input_hash'], config['symbol'], config['interval'], row['candle_open_timestamp'], decision['signal']]).encode()).hexdigest()
            points.append({**{key: row[key] for key in ('id','revision','symbol','data_source','data_mode','observation_type','source_observation_id','candle_interval','candle_open_timestamp','source_timestamp','received_timestamp','candle_complete')},
                'signal_id': signal_id, 'signal': decision['signal'], 'confirmed': decision.get('confirmed', False),
                'sma20': float(decision['sma_fast']) if decision.get('sma_fast') is not None else None,
                'sma50': float(decision['sma_slow']) if decision.get('sma_slow') is not None else None,
                'decision_status': decision['status'], 'reason': decision['reason'], 'available_at': decision['available_at']})
        signals = [p for p in points if p['confirmed'] and p['candle_complete'] and p['signal'] in ('BUY','SELL')]
        signal_lookup = {(p['id'], p['signal']): p for p in signals}
        fills = []
        for index, fill in enumerate(result['fills']):
            signal = signal_lookup.get((fill['signal_candle_id'], fill['side']))
            if signal is None:
                raise ValueError('Backtest fill has no associated confirmed signal')
            fills.append({**fill, 'marker_id': f"backtest-fill:{result['input_hash']}:{index}",
                'symbol': config['symbol'], 'interval': config['interval'], 'execution_price': fill['price'],
                'source_timestamp': fill['timestamp'], 'execution_timestamp': fill['timestamp'],
                'signal_id': signal['signal_id'], 'signal_candle_open_timestamp': signal['candle_open_timestamp'], 'signal_direction': signal['signal']})
        return {'id': identifier, 'mode': 'BACKTEST · SIMULATED', 'symbol': config['symbol'], 'interval': config['interval'],
            'candles': candles, 'fills': fills, 'indicators': {'symbol': config['symbol'], 'interval': config['interval'],
                'configuration': {'fast_period': config['fast_period'], 'slow_period': config['slow_period']},
                'points': points, 'signals': signals, 'latest': points[-1] if points else None},
            'input_hash': result['input_hash'], 'snapshot_max_id': result['snapshot_max_id']}

    def list(self, limit=20):
        with closing(self.database.read_connection()) as conn:
            rows = conn.execute('SELECT id,created_timestamp,input_hash,configuration_json FROM backtest_runs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [{'id': r['id'], 'created_timestamp': r['created_timestamp'], 'input_hash': r['input_hash'], 'configuration': json.loads(r['configuration_json'])} for r in rows]
