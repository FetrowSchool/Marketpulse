import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import pytest
from app.services.database import Database


def test_initialization_and_connectivity(db):
    assert db.is_connected()
    with closing(db.connect()) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 1
    assert not Database(db.path.parent / "missing" / "missing.sqlite3").is_connected()


def test_insert_retrieve_and_preserve_metadata(db, observation):
    identifier = db.insert_observation(**observation)
    row, = db.retrieve("test")
    assert row["id"] == identifier
    for key in ("symbol", "data_source", "source_observation_id", "observation_type", "data_mode"):
        assert row[key] == observation[key]
    assert json.loads(row["payload_json"]) == observation["payload"]
    assert row["source_timestamp"] == "2026-01-01T10:00:00.000000Z"
    assert datetime.fromisoformat(row["received_timestamp"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert row["revision"] == 1
    assert len(row["content_hash"]) == 64
    for key in ("open", "high", "low", "close", "volume", "candle_interval", "candle_open_timestamp", "candle_complete"):
        assert row[key] is None


def test_repeated_initialization_preserves_records(db, observation):
    db.insert_observation(**observation)
    before = db.retrieve()
    db.initialize()
    db.initialize()
    assert db.retrieve() == before


def test_duplicates_and_revisions_are_append_only(db, observation):
    original = db.insert_observation(**observation)
    assert db.insert_observation(**observation) == original
    revised = dict(observation, payload={"price": 101})
    assert db.insert_observation(**revised) != original
    assert db.insert_observation(**observation) == original
    rows = db.retrieve()
    assert [row["revision"] for row in rows] == [1, 2]
    assert json.loads(rows[0]["payload_json"]) == observation["payload"]
    for statement in ("UPDATE observations SET revision=99", "DELETE FROM observations"):
        with closing(db.connect()) as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)


@pytest.mark.parametrize("kind", ["constructed_candle", "provider_candle"])
def test_candle_revisions_and_multiple_observations(db, observation, kind):
    candle = dict(observation, observation_type=kind, candle_interval="1m",
        candle_open_timestamp="2026-01-01T05:00:00-05:00", open=100, high=104,
        low=99, close=102, volume=42, candle_complete=False)
    db.insert_observation(**candle)
    db.insert_observation(**dict(candle, close=103, candle_complete=True))
    db.insert_observation(**dict(candle, source_observation_id="event-2"))
    rows = db.retrieve()
    assert [row["revision"] for row in rows] == [1, 2, 1]
    assert [row["candle_complete"] for row in rows] == [0, 1, 0]
    assert all(row["candle_open_timestamp"] == "2026-01-01T10:00:00.000000Z" for row in rows)
    assert [rows[0][key] for key in ("open", "high", "low", "close", "volume")] == [100, 104, 99, 102, 42]


def test_out_of_order_source_timestamps_and_replay_cursor(db, observation):
    first = db.insert_observation(**observation)
    second = db.insert_observation(**dict(observation, source_observation_id="late-event",
                                           source_timestamp="2026-01-01T09:59:00Z"))
    assert [row["id"] for row in db.retrieve()] == [first, second]
    assert [row["id"] for row in db.retrieve(order="source")] == [second, first]
    assert [row["id"] for row in db.retrieve(after_id=first)] == [second]
    assert len(db.retrieve(limit=1)) == 1
    assert db.retrieve("OTHER") == []


@pytest.mark.parametrize("changes", [
    {"observation_type": "unknown"}, {"volume": -1}, {"data_mode": "unclassified"},
    {"observation_type": "provider_candle"}, {"candle_complete": True},
    {"source_observation_id": ""}, {"symbol": " "},
    {"observation_type": "provider_candle", "candle_open_timestamp": "2026-01-01T10:00:00Z", "candle_complete": True},
])
def test_sql_constraints(db, observation, changes):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_observation(**dict(observation, **changes))
    assert db.retrieve() == []


@pytest.mark.parametrize("changes", [{"source_timestamp": "2026-01-01T10:00:00"},
    {"close": float("nan")}, {"payload": {"price": float("inf")}}])
def test_invalid_values_rejected(db, observation, changes):
    with pytest.raises(ValueError):
        db.insert_observation(**dict(observation, **changes))


def test_concurrent_writers_allocate_revisions_and_deduplicate(db, observation):
    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(lambda _: db.insert_observation(**observation), range(8)))
    assert len(set(ids)) == 1
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda n: db.insert_observation(**dict(observation, payload={"price": n})), range(8)))
    assert [row["revision"] for row in db.retrieve()] == list(range(1, 10))
