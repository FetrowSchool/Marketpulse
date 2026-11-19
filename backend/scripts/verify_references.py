"""Synthetic SMA reference probe; pandas/Fraction are independent of app arithmetic.

Run from backend: python scripts/verify_references.py [--output path.json]
"""
import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from app.services.database import utc_timestamp
from app.services.indicators import evaluate, sma_step

TOLERANCE = 1e-9  # USD absolute, relative tolerance zero, for prices <= 1,000,000.


def fixture(closes):
    base = datetime(2026, 1, 6, 15, tzinfo=timezone.utc)
    return [dict(id=i+1,symbol='AAPL',data_source='yahoo_finance',data_mode='simulated',
        observation_type='constructed_candle',source_observation_id=f'reference-fixture:{i}',
        candle_interval='1m',candle_open_timestamp=utc_timestamp(base+timedelta(minutes=i)),
        source_timestamp=utc_timestamp(base+timedelta(minutes=i)),
        received_timestamp=utc_timestamp(base+timedelta(minutes=i+1)),
        revision=1,candle_complete=True,close=float(close)) for i,close in enumerate(closes)]


def compare(closes):
    rows=fixture(closes)
    batch=evaluate(rows,'AAPL','1m')['points']
    window=deque(maxlen=50);previous=None;maximum=0.0
    # Independent exact rolling sums, not the application's Decimal/window algorithm.
    rational_windows={20:deque(),50:deque()};totals={20:Fraction(0),50:Fraction(0)}
    pandas_values={n:pd.Series([r['close'] for r in rows]).rolling(n,min_periods=n).mean().tolist() for n in (20,50)}
    references=[]
    for i,row in enumerate(rows):
        window.append(Decimal(str(row['close'])))
        fast,slow,signal,confirmed,_=sma_step(list(window),previous)
        if fast is not None and slow is not None:previous=(fast,slow)
        assert (signal,confirmed)==(batch[i]['signal'],batch[i]['confirmed'])
        entry={'completed_count':i+1}
        for period,value,key in ((20,fast,'sma20'),(50,slow,'sma50')):
            exact_value=Fraction(str(row['close']))
            totals[period]+=exact_value;rational_windows[period].append(exact_value)
            if len(rational_windows[period])>period:totals[period]-=rational_windows[period].popleft()
            reference=sum(Fraction(str(r['close'])) for r in rows[max(0,i+1-period):i+1])/period if i+1>=period else None
            incremental_reference=totals[period]/period if i+1>=period else None
            assert reference==incremental_reference
            if reference is None:
                assert value is None and batch[i][key] is None and pd.isna(pandas_values[period][i])
                entry[key]=None
            else:
                errors=[abs(float(value)-float(reference)),abs(batch[i][key]-float(reference)),abs(pandas_values[period][i]-float(reference))]
                maximum=max(maximum,*errors)
                assert max(errors)<=TOLERANCE,(i,period,errors)
                entry[key]={'expected_fraction':str(reference),'expected':float(reference),'batch':batch[i][key], 'incremental':float(value),'pandas':pandas_values[period][i]}
        if i+1 in (19,20,49,50,51,60):references.append(entry)
    return {'points_checked':len(rows),'max_absolute_error_usd':maximum,'selected_reference_values':references}


def report():
    datasets={'constant':[Decimal('100.125')]*60,'rising':list(range(1,61)),
              'falling':list(range(60,0,-1)),
              'decimal_rising':[Decimal('100.1')+Decimal(i)/10 for i in range(60)],
              'crossover':[100]*50+[120,80,80]+[100]*7,
              'precision_bound':[Decimal('999999.000001')+Decimal(i)/1000000 for i in range(60)]}
    return {'data_kind':'explicitly synthetic reference fixtures; no provider observations',
            'reference':'Exact fractions.Fraction batch sums and running sums; independently pandas rolling mean',
            'pandas_version':pd.__version__,'absolute_tolerance_usd':TOLERANCE,'relative_tolerance':0,
            'datasets':{name:compare(values) for name,values in datasets.items()}}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    data=report();encoded=json.dumps(data,indent=2,allow_nan=False)+'\n'
    if args.output:args.output.write_text(encoded)
    print(encoded)
