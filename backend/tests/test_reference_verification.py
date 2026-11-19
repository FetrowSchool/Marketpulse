"""Exact hand/Fraction references, with an independent pandas rolling cross-check."""
from collections import deque
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import pytest
from scripts.verify_references import compare, fixture, report, TOLERANCE
from app.services.indicators import evaluate, sma_step


@pytest.mark.parametrize('values',[list(range(1,61)),list(range(60,0,-1)),[100.125]*60,
    [100]*50+[120,80,80]+[100]*7,[float(Decimal('100.1')+Decimal(i)/10) for i in range(60)]])
def test_batch_incremental_fraction_and_pandas_equivalence(values):
    result=compare(values)
    assert result['max_absolute_error_usd']<=TOLERANCE
    assert result['points_checked']==60


def test_hand_calculated_reference_values_are_explicit():
    rising=evaluate(fixture(range(1,61)),'AAPL','1m')['points']
    assert rising[18]['sma20'] is None
    assert rising[19]['sma20']==10.5 and rising[19]['sma50'] is None
    assert rising[48]['sma20']==39.5 and rising[48]['sma50'] is None
    assert (rising[49]['sma20'],rising[49]['sma50'],rising[49]['confirmed'])==(40.5,25.5,False)
    assert (rising[50]['sma20'],rising[50]['sma50'])==(41.5,26.5)
    falling=evaluate(fixture(range(60,0,-1)),'AAPL','1m')['points']
    assert (falling[49]['sma20'],falling[49]['sma50'])==(20.5,35.5)
    equal=evaluate(fixture([100.125]*60),'AAPL','1m')
    assert equal['signals']==[]
    assert (equal['latest']['sma20'],equal['latest']['sma50'])==(100.125,100.125)


def test_crossing_boundaries_match_exact_reference():
    points=evaluate(fixture([100]*50+[120,80,80]),'AAPL','1m')['points']
    assert [(p['sma20'],p['sma50'],p['signal']) for p in points[50:]]==[(101,100.4,'BUY'),(100,100,'HOLD'),(99,99.6,'SELL')]


def test_missing_bucket_and_incomplete_close_have_no_synthetic_contribution():
    rows=fixture(range(1,62));rows.pop(10)  # Missing close11; do not fill with10/zero.
    points=evaluate(rows,'AAPL','1m')['points']
    assert (points[49]['sma20'],points[49]['sma50'])==(41.5,26.3)
    rows=fixture([100]*50+[120]);rows[-1]['candle_complete']=False
    result=evaluate(rows,'AAPL','1m')
    assert not result['signals'] and result['points'][-1]['sma20'] is None
    assert result['latest']['id']==50


def test_invalid_close_resets_warmup_and_revision_recomputes_not_appends():
    rows=fixture(range(1,91));rows[25]['close']=None
    result=evaluate(rows,'AAPL','1m')
    assert result['points'][74]['sma50'] is None
    assert (result['points'][75]['sma20'],result['points'][75]['sma50'])==(66.5,51.5)
    original=fixture([100]*50+[120]);correction={**original[-1],'id':100,'revision':2,'close':80}
    updated=evaluate(list(reversed(original))+[correction,correction],'AAPL','1m')
    assert len(updated['points'])==51
    assert (updated['latest']['sma20'],updated['latest']['sma50'],updated['latest']['signal'])==(99,99.6,'SELL')
    assert original[-1]['close']==120
