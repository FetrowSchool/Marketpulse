"""Read-only, completed-candle SMA snapshots. No trade execution or signal ledger."""
from collections import deque
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import math

from app.services.market_repository import serialize
from app.services.normalization import SOURCE

CONFIG = {
    'algorithm': 'sma-crossover-v1', 'fast_period': 20, 'slow_period': 50,
    'completed_candles_only': True, 'provisional_indicators': False,
    'equality_rule': 'BUY: previous fast <= slow and current fast > slow; SELL: previous fast >= slow and current fast < slow; current equality is HOLD',
    'missing_intervals': 'Skip unobserved intervals; never synthesize candles',
    'max_candles': 1000, 'execution_enabled': False,
}


def sma_step(values, previous, fast_period=20, slow_period=50):
    """Shared Decimal SMA/crossing rule for live views and historical events."""
    fast = sum(values[-fast_period:]) / Decimal(fast_period) if len(values) >= fast_period else None
    slow = sum(values[-slow_period:]) / Decimal(slow_period) if len(values) >= slow_period else None
    signal, confirmed = 'HOLD', False
    reason = 'insufficient_history'
    if fast is not None and slow is not None:
        reason = 'awaiting_previous_sma' if previous is None else 'no_crossover'
        if previous is not None:
            confirmed = True
            if previous[0] <= previous[1] and fast > slow:
                signal, reason = 'BUY', 'crossed_above'
            elif previous[0] >= previous[1] and fast < slow:
                signal, reason = 'SELL', 'crossed_below'
    return fast, slow, signal, confirmed, reason


def evaluate(candles, symbol, interval):
    """Latest identity revisions first, then one canonical producer per opening.

    Provenance/source/type changes reset the window rather than mixing series.
    Repeated evaluation is idempotent; a corrected signal replaces its stable slot.
    """
    identities = {}
    for row in candles:
        if row['symbol'] != symbol or row['candle_interval'] != interval:
            raise ValueError('Mixed symbol or interval in indicator input')
        key = (row['data_source'], row['symbol'], row['observation_type'], row['source_observation_id'])
        prior = identities.get(key)
        if prior is None or (row['revision'], row['id']) > (prior['revision'], prior['id']):
            identities[key] = row
    openings = {}
    for row in identities.values():
        key = row['candle_open_timestamp']
        if key not in openings or row['id'] > openings[key]['id']:
            openings[key] = row
    rows = sorted(openings.values(), key=lambda row: row['candle_open_timestamp'])
    points, window, previous, group = [], deque(maxlen=50), None, None
    for row in rows:
        current_group = (row['data_source'], row['observation_type'], row['data_mode'])
        if group != current_group:
            window.clear(); previous = None; group = current_group
        point = {key: row[key] for key in ('symbol', 'data_source', 'data_mode', 'observation_type',
                 'source_observation_id', 'candle_interval', 'candle_open_timestamp',
                 'source_timestamp', 'received_timestamp', 'revision', 'id', 'candle_complete')}
        point.update(sma20=None, sma50=None, signal='HOLD', confirmed=False,
                     reason='incomplete_candle' if not row['candle_complete'] else 'insufficient_history')
        point['signal_id'] = hashlib.sha256(json.dumps([CONFIG['algorithm'],symbol,interval,*group,
                                                       row['candle_open_timestamp']]).encode()).hexdigest()
        valid_close = isinstance(row.get('close'), (int,float)) and not isinstance(row.get('close'),bool) and math.isfinite(row['close']) and row['close'] > 0
        if row['candle_complete'] and not valid_close:
            window.clear(); previous = None; point['reason'] = 'invalid_close'
        if row['candle_complete'] and valid_close:
            window.append(Decimal(str(row['close'])))
            values = list(window)
            fast, slow, signal, confirmed, reason = sma_step(values, previous)
            point.update(sma20=float(fast) if fast is not None else None,
                         sma50=float(slow) if slow is not None else None,
                         signal=signal, confirmed=confirmed, reason=reason)
            if fast is not None and slow is not None:
                previous = (fast, slow)
        points.append(point)
    latest = next((point for point in reversed(points) if point['candle_complete']), None)
    return {'symbol': symbol, 'interval': interval, 'configuration': CONFIG,
            'points': points, 'signals': [p for p in points if p['confirmed'] and p['signal'] != 'HOLD'],
            'latest': latest, 'completed_count': sum(row['candle_complete'] for row in rows),
            'calculation_mode': 'completed_only', 'window_limited': True}


def saved_snapshot(database, symbol, interval, limit=1000, as_of_id=None):
    with closing(database.read_connection()) as conn:
        conn.execute('BEGIN')
        maximum = conn.execute('SELECT COALESCE(MAX(id),0) FROM observations').fetchone()[0]
        boundary = min(maximum, as_of_id) if as_of_id is not None else maximum
        rows = conn.execute('''WITH effective AS (
            SELECT *,ROW_NUMBER() OVER(PARTITION BY data_source,symbol,observation_type,source_observation_id
                ORDER BY revision DESC,id DESC) AS rank
            FROM observations WHERE symbol=? AND data_source=? AND candle_interval=?
            AND observation_type='constructed_candle' AND id<=?)
            SELECT * FROM effective WHERE rank=1 ORDER BY candle_open_timestamp DESC,id DESC LIMIT ?''',
            (symbol,SOURCE,interval,boundary,limit)).fetchall()
        data = evaluate([serialize(row) for row in rows],symbol,interval)
    return {**data,'snapshot_max_id':boundary}
