"""Synthetic deterministic examples; these tests never connect to Yahoo."""
from contextlib import closing
from datetime import timedelta
from dataclasses import replace
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.database import Database
from app.services.normalization import normalize_message
from app.services.market_repository import MarketRepository
from app.services.replay import ReplayRepository, ReplaySession
from test_market_processing import NOW, message


def insert(db, price, source_offset, receipt_offset):
    observation = normalize_message(message(price, source_offset), NOW + timedelta(seconds=receipt_offset),
                                     symbol="AAPL", data_mode="simulated")
    repository = MarketRepository(db, symbol="AAPL", interval="1m", data_mode="simulated")
    return repository.ingest(observation, NOW + timedelta(seconds=receipt_offset))


def recording(db):
    insert(db, 100, 0, 1)
    insert(db, 110, 40, 41)
    repo = MarketRepository(db, symbol="AAPL", interval="1m", data_mode="simulated")
    repo.complete_due(NOW + timedelta(seconds=41))
    insert(db, 95, -10, 45)  # Late quote revises previous minute, not current 110 candle.
    insert(db, 100, 10, 46)  # Same price as first observation, different source time/identity.
    repo.complete_due(NOW + timedelta(seconds=100))
    return ReplayRepository(db).load("AAPL", "1m")


def final_candles(records):
    result = {}
    for row in records:
        if row["observation_type"] == "raw_provider":
            continue
        key = row["source_observation_id"]
        if key not in result or row["revision"] > result[key]["revision"]:
            result[key] = row
    return sorted(result.values(), key=lambda row: row["candle_open_timestamp"])


def test_exact_duplicates_vs_same_price_different_time_identity_and_metadata(db):
    identifier, _ = insert(db, 100, 0, 1)
    before = db.retrieve()
    assert insert(db, 100, 0, 2) == (identifier, False)
    assert db.retrieve() == before
    assert insert(db, 100, 1, 3)[1] is True
    raw = [row for row in db.retrieve() if row["observation_type"] == "raw_provider"]
    assert len(raw) == 2 and raw[0]["source_observation_id"] != raw[1]["source_observation_id"]
    observation = normalize_message(message(100), NOW + timedelta(seconds=4), symbol="AAPL", data_mode="simulated")
    revised = replace(observation, payload={**observation.payload, "provider_revision": 2})
    second = db.insert_observation(**revised.record())
    assert second != identifier
    assert [row["revision"] for row in db.retrieve() if row["source_observation_id"] == observation.source_observation_id] == [1, 2]
    # Redelivering revision-one content never replaces revision two or allocates revision three.
    assert db.insert_observation(**observation.record()) == identifier


def test_frozen_replay_no_writes_and_expected_final_candles(db):
    data = recording(db)
    before = db.retrieve(limit=10000)
    session = ReplaySession(data)
    session.control("play", 0)
    emitted = session.tick(1000)
    assert [row["id"] for row in emitted] == [row["id"] for row in data["records"]]
    old, current = final_candles(emitted)
    assert [old[key] for key in ("open", "high", "low", "close")] == [95, 100, 95, 100]
    assert old["candle_complete"] and old["revision"] == 4
    assert current["close"] == 110 and current["candle_complete"]
    session.control("restart", 2000)
    again = session.tick(3000)
    assert final_candles(again) == final_candles(emitted)
    assert db.retrieve(limit=10000) == before
    insert(db, 120, 120, 121)
    assert all(row["id"] <= data["snapshot_max_id"] for row in session.records)
    assert session.records == data["records"]


def test_pause_resume_speed_restart_and_stop_with_injected_clock(db):
    data = recording(db)
    session = ReplaySession(data)
    session.control("play", 10)
    first = session.tick(10)
    assert len(first) == 2  # raw + provisional candle share receipt timestamp; ID tie-break.
    session.control("pause", 15)
    position = session.position
    assert session.tick(500) == [] and session.position == position
    session.control("speed", 500, 2)
    session.control("resume", 600)
    assert session.tick(610) == []  # virtual elapsed 25, next event at 40.
    assert session.tick(618)
    session.control("speed", 618, 100)
    assert session.tick(620)
    assert session.state == "completed"
    session.control("restart", 700)
    assert session.position == 0 and session.generation == 2
    assert [row["id"] for row in session.tick(700)] == [row["id"] for row in first]
    session.control("stop", 701)
    assert session.state == "stopped" and session.position == 0
    assert session.tick(999) == []


def test_receipt_vs_source_vs_commit_order_and_stable_ties(db):
    insert(db, 100, 0, 10)
    insert(db, 90, -20, 11)
    receipt = ReplayRepository(db).load("AAPL", "1m")
    assert [row["id"] for row in receipt["records"]] == sorted(row["id"] for row in receipt["records"])
    raw = [row for row in receipt["records"] if row["observation_type"] == "raw_provider"]
    assert raw[0]["source_timestamp"] > raw[1]["source_timestamp"]
    # Deliberate wall-clock rollback: timestamp chronology and commit sequence differ.
    insert(db, 95, -10, 9)
    repository = ReplayRepository(db)
    by_receipt = repository.load("AAPL", "1m")["records"]
    by_arrival = repository.load("AAPL", "1m", order="arrival")["records"]
    assert [(row["received_timestamp"], row["id"]) for row in by_receipt] == sorted((row["received_timestamp"], row["id"]) for row in by_receipt)
    assert [row["id"] for row in by_arrival] == sorted(row["id"] for row in by_arrival)
    assert [row["id"] for row in by_arrival] != [row["id"] for row in by_receipt]


def test_range_uses_asof_baseline_not_future_candle_revision(db):
    data = recording(db)
    repository = ReplayRepository(db)
    bounded = repository.load("AAPL", "1m", NOW + timedelta(seconds=44), NOW + timedelta(seconds=46))
    assert all(NOW + timedelta(seconds=44) <= __import__('datetime').datetime.fromisoformat(row["received_timestamp"].replace("Z", "+00:00")) < NOW + timedelta(seconds=46) for row in bounded["records"])
    baseline = final_candles(bounded["baseline"])
    assert baseline[0]["open"] == 100 and baseline[0]["revision"] == 2
    session = ReplaySession(bounded)
    session.control("play", 0)
    result = final_candles([*bounded["baseline"], *session.tick(100)])
    assert result[0]["open"] == 95 and result[0]["revision"] == 3
    assert final_candles(data["records"])[0]["revision"] == 4


def test_database_integrity_restart_initialization_and_readonly_enforcement(db):
    recording(db)
    before = db.retrieve(limit=10000)
    assert db.verify_integrity()["ok"] is True
    db.initialize(); Database(db.path).initialize()
    assert Database(db.path).retrieve(limit=10000) == before
    assert ReplayRepository(Database(db.path)).load("AAPL", "1m")["records"]
    with closing(db.read_connection()) as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO schema_version VALUES (1)")


@pytest.mark.parametrize("speed", [0, -1, 101, float('nan'), True, "2"])
def test_invalid_speed_rejected(db, speed):
    with pytest.raises(ValueError):
        ReplaySession(recording(db), speed=speed)


def receive_kind(socket, kind):
    for _ in range(100):
        item = socket.receive_json()
        if item["type"] == kind:
            return item
    raise AssertionError(f"Missing {kind}")


def test_replay_socket_controls_without_live_feed_and_database_unchanged(db):
    recording(db)
    before = db.retrieve(limit=10000)
    app = create_app(Settings(database_path=db.path, feed_enabled=False))
    with TestClient(app) as client, client.websocket_connect('/ws/replay') as socket:
        assert socket.receive_json()["data"]["state"] == "idle"
        socket.send_json({"type": "load", "selection": {"symbol": "AAPL", "interval": "1m"}, "speed": 100})
        loaded = receive_kind(socket, "replay_loaded")
        assert loaded["display_mode"] == "replay" and loaded["data"]["total"] > 0
        socket.send_json({"type": "play"})
        first = receive_kind(socket, "replay_event")
        row = first["data"]["record"]
        assert row["data_mode"] == "simulated"  # Original provenance is NOT rewritten.
        assert row["received_timestamp"] == before[0]["received_timestamp"]
        socket.send_json({"type": "pause"})
        while receive_kind(socket, "replay_status")["data"]["state"] not in ("paused", "completed"):
            pass
        socket.send_json({"type": "speed", "speed": 25})
        for _ in range(20):
            if receive_kind(socket, "replay_status")["data"]["speed"] == 25:
                break
        else:
            raise AssertionError("Speed did not change")
        socket.send_json({"type": "restart"})
        reset = receive_kind(socket, "replay_loaded")
        assert reset["generation"] > loaded["generation"] and reset["data"]["position"] == 0
        socket.send_json({"type": "stop"})
        assert receive_kind(socket, "replay_loaded")["data"]["state"] == "stopped"
        assert client.get('/api/market/status').json()["state"] == "unavailable"
        assert app.state.market.status.attempts == 0
    assert db.retrieve(limit=10000) == before


def test_retrieval_validation_snapshot_paging_and_errors(db):
    recording(db)
    app = create_app(Settings(database_path=db.path, feed_enabled=False))
    with TestClient(app) as client:
        catalog = client.get('/api/replay/catalog?symbol=AAPL&interval=1m').json()
        assert catalog["event_count"] == len(db.retrieve(limit=10000))
        page = client.get('/api/replay/records?symbol=AAPL&limit=2').json()
        assert len(page["records"]) == 2
        next_page = client.get(f'/api/replay/records?symbol=AAPL&limit=2&after_sequence=2&snapshot_max_id={page["snapshot_max_id"]}').json()
        assert next_page["records"][0]["id"] == db.retrieve(limit=10000)[2]["id"]
        assert client.get('/api/replay/records?symbol=INVALID').status_code == 422
        assert client.get('/api/replay/records?symbol=AAPL&start=2026-01-01T00:00:00').status_code == 422
        assert client.get('/api/replay/records?symbol=AAPL&start=2027-01-01T00:00:00Z&end=2026-01-01T00:00:00Z').status_code == 422
        with client.websocket_connect('/ws/replay') as socket:
            socket.receive_json()
            socket.send_json({"type": "play"})
            assert receive_kind(socket, 'error')["data"]["code"] == "invalid_replay_request"
            socket.send_json({"type": "load", "selection": {"symbol": "INVALID"}})
            assert receive_kind(socket, 'error')["data"]["code"] == "invalid_replay_request"


@pytest.mark.parametrize('variation', [
    {'source_observation_id': 'another-explicit-event'}, {'symbol': 'MSFT'},
    {'data_source': 'another-test-provider'}, {'source_timestamp': '2026-01-06T15:00:31Z'},
    {'payload': {'price': 100.0, 'sequence': 2}},
])
def test_same_price_is_not_a_deduplication_key(db, variation):
    observation = normalize_message(message(100), NOW + timedelta(seconds=1), symbol='AAPL', data_mode='simulated')
    values = observation.record()
    first = db.insert_observation(**values)
    second = db.insert_observation(**{**values, **variation})
    assert first != second and len(db.retrieve()) == 2


def test_live_insert_does_not_enter_an_already_loaded_replay(db):
    recording(db)
    app = create_app(Settings(database_path=db.path, feed_enabled=False))
    app.state.market.clock = lambda: NOW + timedelta(seconds=121)
    with TestClient(app) as client, client.websocket_connect('/ws/replay') as socket:
        socket.receive_json()
        socket.send_json({'type': 'load', 'selection': {'symbol': 'AAPL'}, 'speed': 100})
        loaded = receive_kind(socket, 'replay_loaded')
        boundary = loaded['data']['snapshot_max_id']
        client.portal.call(app.state.market.handle_message, message(120, 120))
        count_with_live_insert = len(db.retrieve(limit=10000))
        socket.send_json({'type': 'play'})
        seen = []
        for _ in range(300):
            item = socket.receive_json()
            if item['type'] == 'replay_event':
                seen.append(item['data']['record']['id'])
            if item['type'] == 'replay_status' and item['data']['state'] == 'completed':
                break
        else:
            raise AssertionError('Replay failed to complete')
        assert seen and max(seen) <= boundary
        assert len(seen) == loaded['data']['total']
        assert len(db.retrieve(limit=10000)) == count_with_live_insert
