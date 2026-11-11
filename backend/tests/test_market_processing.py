"""All messages here are synthetic/simulated, NOT recorded Yahoo observations."""
import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest

from app.services.normalization import normalize_message
from app.services.market_repository import MarketRepository
from app.services.candles import candle_bounds
from app.services.database import Database

NOW = datetime(2026, 1, 6, 15, 0, 30, tzinfo=timezone.utc)


def message(price=100, seconds=0, **extra):
    source = NOW + timedelta(seconds=seconds)
    return {"id": "AAPL", "price": price, "time": str(int(source.timestamp() * 1000)),
            "market_hours": 1, "day_volume": "2000000", **extra}


def normalized(price=100, seconds=0, receipt=None, **extra):
    return normalize_message(message(price, seconds, **extra), receipt or NOW + timedelta(minutes=5),
                             symbol="AAPL", data_mode="simulated")


def repo(db):
    return MarketRepository(db, symbol="AAPL", interval="1m", data_mode="simulated")


def test_normalization_preserves_price_provenance_metadata_and_missing_ohlcv(db):
    raw = message(custom_field={"unknown": "preserve me"})
    observation = normalize_message(raw, NOW, symbol="AAPL", data_mode="simulated")
    assert observation.price == 100
    assert observation.source_timestamp == "2026-01-06T15:00:30.000000Z"
    assert observation.received_timestamp == observation.source_timestamp
    assert observation.data_source == "yahoo_finance"
    assert observation.observation_type == "raw_provider"
    assert observation.payload["original"] == raw
    assert observation.payload["provider_volume"] == {"day_volume": "2000000"}
    assert observation.payload["provider_event_id"] is None
    assert observation.source_observation_id != "AAPL"
    raw["custom_field"]["unknown"] = "changed externally"
    assert observation.payload["original"]["custom_field"]["unknown"] == "preserve me"
    db.insert_observation(**observation.record())
    row, = db.retrieve()
    assert row["received_timestamp"] == observation.received_timestamp
    assert all(row[key] is None for key in ("open", "high", "low", "close", "volume"))
    assert json.loads(row["payload_json"])["price"] == 100


def test_timestamp_offset_and_millisecond_precision():
    value = message(time="1767711630123")
    receipt = datetime(2026, 1, 6, 10, 0, 31, tzinfo=timezone(timedelta(hours=-5)))
    result = normalize_message(value, receipt, symbol="AAPL")
    assert result.source_timestamp == "2026-01-06T15:00:30.123000Z"
    assert result.received_timestamp == "2026-01-06T15:00:31.000000Z"


@pytest.mark.parametrize("changes", [
    {"id": "MSFT"}, {"price": None}, {"price": True}, {"price": float("nan")},
    {"price": -1}, {"time": None}, {"time": "1767711630"}, {"time": True},
    {"time": 1767711630123.5}, {"time": "invalid"}, {"custom": float("inf")},
])
def test_bad_provider_messages_rejected(changes):
    with pytest.raises(ValueError):
        normalize_message(dict(message(), **changes), NOW, symbol="AAPL")


def test_future_and_naive_time_rejected():
    with pytest.raises(ValueError):
        normalize_message(message(seconds=20), NOW, symbol="AAPL")
    with pytest.raises(ValueError):
        normalize_message(message(), NOW.replace(tzinfo=None), symbol="AAPL")


def test_fingerprint_is_stable_across_key_order_and_receipt_time():
    first = normalize_message(message(), NOW, symbol="AAPL")
    second = normalize_message(dict(reversed(list(message().items()))), NOW + timedelta(minutes=1), symbol="AAPL")
    assert first.source_observation_id == second.source_observation_id
    assert normalized(price=101).source_observation_id != normalized(price=100).source_observation_id


def test_candle_source_order_late_data_duplicate_and_completion(db):
    repository = repo(db)
    repository.ingest(normalized(100), NOW)
    repository.ingest(normalized(104, 10), NOW + timedelta(seconds=10))
    repository.ingest(normalized(98, -10), NOW + timedelta(seconds=15))
    candles = repository.candles("AAPL", "1m", 100)
    candle, = candles
    assert [candle[key] for key in ("open", "high", "low", "close")] == [98, 104, 98, 104]
    assert candle["volume"] is None
    assert candle["candle_complete"] is False
    assert candle["candle_open_timestamp"] == "2026-01-06T15:00:00.000000Z"
    assert candle["metadata"]["observation_count"] == 3
    before = db.retrieve()
    assert repository.ingest(normalized(98, -10), NOW + timedelta(seconds=16))[1] is False
    assert db.retrieve() == before
    assert repository.complete_due(NOW + timedelta(seconds=29)) == 0
    assert repository.complete_due(NOW + timedelta(seconds=30)) == 1
    final, = repository.candles("AAPL", "1m", 100)
    assert final["candle_complete"] is True
    assert final["revision"] == 4
    assert repository.complete_due(NOW + timedelta(minutes=1)) == 0


def test_late_closed_candle_correction_does_not_corrupt_current_candle(db):
    repository = repo(db)
    repository.ingest(normalized(100), NOW)
    repository.complete_due(NOW + timedelta(minutes=1))
    repository.ingest(normalized(110, 40), NOW + timedelta(seconds=40))
    repository.ingest(normalized(90, -20), NOW + timedelta(seconds=45))
    old, current = repository.candles("AAPL", "1m", 100)
    assert old["open"] == 90 and old["close"] == 100 and old["candle_complete"] is True
    assert current["open"] == current["close"] == 110
    assert current["candle_complete"] is False
    revisions = repository.candles("AAPL", "1m", 100, revisions=True)
    assert len(revisions) == 4
    assert revisions[0]["open"] == 100  # Earlier immutable revision remains.


def test_effective_raw_revision_not_double_counted(db):
    repository = repo(db)
    observation = normalized(100)
    repository.ingest(observation, NOW)
    revised = replace(observation, price=105, payload={**observation.payload, "price": 105})
    repository.ingest(revised, NOW + timedelta(seconds=1))
    raw = repository.observations("AAPL", 100)
    assert [row["revision"] for row in raw] == [1, 2]
    candle, = repository.candles("AAPL", "1m", 100)
    assert candle["open"] == candle["close"] == 105
    assert candle["metadata"]["observation_count"] == 1
    assert candle["metadata"]["contributing_observation_ids"] == [raw[-1]["id"]]


def test_raw_and_candle_commit_atomically(db, monkeypatch):
    insert = db.insert_observation
    def fail_candle(**values):
        if values["observation_type"] == "constructed_candle":
            raise sqlite3.OperationalError("simulated disk failure")
        return insert(**values)
    monkeypatch.setattr(db, "insert_observation", fail_candle)
    with pytest.raises(sqlite3.OperationalError):
        repo(db).ingest(normalized(), NOW)
    assert db.retrieve() == []


def test_restart_uses_persisted_quotes_and_deduplicates(db):
    repo(db).ingest(normalized(100), NOW)
    restarted = repo(Database(db.path))
    assert restarted.ingest(normalized(100), NOW + timedelta(seconds=1))[1] is False
    assert restarted.complete_due(NOW + timedelta(minutes=1)) == 1
    restarted.ingest(normalized(101, 10), NOW + timedelta(minutes=2))
    candle, = restarted.candles("AAPL", "1m", 100)
    assert candle["close"] == 101 and candle["candle_complete"] is True
    assert len(restarted.observations("AAPL", 100)) == 2


def test_interval_boundaries_and_no_empty_gap_candles(db):
    assert candle_bounds("2026-01-06T15:04:59Z", "5m")[0].minute == 0
    assert candle_bounds("2026-01-06T15:05:00Z", "5m")[0].minute == 5
    repository = repo(db)
    repository.ingest(normalized(), NOW)
    repository.ingest(normalized(110, 180), NOW + timedelta(minutes=4))
    assert len(repository.candles("AAPL", "1m", 100)) == 2


def test_recorded_provider_fixture_replays_deterministically(db):
    # This fixture was captured from Yahoo; this test itself is fully offline.
    from pathlib import Path
    fixture = json.loads(Path(__file__).with_name("fixtures").joinpath("yahoo_recorded_quote.json").read_text())
    received = datetime.fromisoformat(fixture["recorded_received_timestamp"].replace("Z", "+00:00"))
    observation = normalize_message(fixture["message"], received, symbol="AAPL", data_mode="recorded")
    repository = MarketRepository(db, symbol="AAPL", interval="1m", data_mode="recorded")
    identifier, inserted = repository.ingest(observation, received)
    assert inserted
    assert repository.ingest(observation, received + timedelta(seconds=10)) == (identifier, False)
    row, = repository.observations("AAPL", 100)
    assert row["data_mode"] == "recorded"
    assert row["metadata"]["original"] == fixture["message"]
    candle, = repository.candles("AAPL", "1m", 100)
    assert candle["open"] == candle["close"] == fixture["message"]["price"]
    assert candle["volume"] is None


def test_completion_does_not_regress_after_clock_rollback(db):
    repository = repo(db)
    repository.ingest(normalized(100), NOW)
    repository.complete_due(NOW + timedelta(minutes=1))
    repository.ingest(normalized(105, -5), NOW)  # Scheduler clock rolled back.
    candle, = repository.candles("AAPL", "1m", 100)
    assert candle["candle_complete"] is True
    assert candle["high"] == 105


@pytest.mark.parametrize("symbol", ["AAPL", "MSFT", "NVDA", "SPY"])
def test_each_supported_symbol_normalizes(symbol):
    observation = normalize_message(message(id=symbol), NOW, symbol=symbol, data_mode="simulated")
    assert observation.symbol == symbol


def test_multiple_live_intervals_late_revisions_completion_and_restart(db):
    repository = MarketRepository(db, symbol='AAPL', interval='1m', data_mode='simulated', intervals=('1m','5m','15m'))
    repository.ingest(normalized(100, receipt=NOW), NOW)
    repository.ingest(normalized(110, 300, receipt=NOW + timedelta(minutes=5)), NOW + timedelta(minutes=5))
    repository.ingest(normalized(95, -10, receipt=NOW + timedelta(minutes=6)), NOW + timedelta(minutes=6))
    before = db.retrieve(limit=10000)
    assert sum(row['observation_type'] == 'raw_provider' for row in before) == 3
    five = repository.candles('AAPL','5m',100)
    assert len(five) == 2
    assert [five[0][key] for key in ('open','high','low','close')] == [95,100,95,100]
    assert five[0]['candle_complete'] and not five[1]['candle_complete']
    fifteen = repository.candles('AAPL','15m',100)[0]
    assert [fifteen[key] for key in ('open','high','low','close')] == [95,110,95,110]
    assert not fifteen['candle_complete'] and fifteen['revision'] == 3
    assert all(row['volume'] is None for row in before)
    db.initialize()
    recovered = MarketRepository(Database(db.path), symbol='AAPL', interval='1m', data_mode='simulated', intervals=('1m','5m','15m'))
    assert recovered.ingest(normalized(95,-10,receipt=NOW+timedelta(minutes=7)), NOW+timedelta(minutes=7))[1] is False
    assert db.retrieve(limit=10000) == before
    recovered.complete_due(NOW.replace(minute=15,second=0))
    assert all(row['candle_complete'] for interval in ('1m','5m','15m') for row in recovered.candles('AAPL',interval,100))
    assert len(recovered.candles('AAPL','15m',100,revisions=True)) == 4


def test_failure_in_last_interval_rolls_back_raw_and_all_candles(db, monkeypatch):
    events=[]
    repository=MarketRepository(db,symbol='AAPL',interval='1m',data_mode='simulated',intervals=('1m','5m','15m'),on_commit=events.extend)
    original=db.insert_observation
    def fail(**values):
        if values.get('candle_interval') == '15m':
            raise sqlite3.OperationalError('Explicit simulated last-interval failure')
        return original(**values)
    monkeypatch.setattr(db,'insert_observation',fail)
    with pytest.raises(sqlite3.OperationalError):
        repository.ingest(normalized(),NOW+timedelta(minutes=5))
    assert db.retrieve() == [] and events == []
