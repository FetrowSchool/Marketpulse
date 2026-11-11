"""All provider traffic here is mocked; no Yahoo network calls."""
import asyncio
import sqlite3
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.main import create_app
from app.services.market_socket import MarketClient
from test_market_processing import NOW, message
from test_market_service import FakeStream


@pytest.fixture
def app(tmp_path):
    application = create_app(Settings(database_path=tmp_path / "socket.sqlite3", feed_enabled=False))
    application.state.market.clock = lambda: NOW
    application.state.market_hub.status_seconds = .01
    return application


def until(socket, kind, *, symbol=None):
    for _ in range(50):
        item = socket.receive_json()
        if item["type"] == kind and (symbol is None or item["symbol"] == symbol):
            return item
    raise AssertionError(f"Missing {kind}")


def subscribe(socket, symbol="AAPL", identifier=1):
    socket.send_json({"type": "subscribe", "symbol": symbol, "request_id": identifier})
    return until(socket, "connection_status", symbol=symbol)


def test_connection_serialization_timestamps_candles_and_dedup(app):
    with TestClient(app) as client, client.websocket_connect("/ws/market") as socket:
        connection = socket.receive_json()
        assert connection["type"] == "connection_status"
        assert connection["source_timestamp"] is None
        assert connection["observation_identity"] is None
        assert subscribe(socket)["data"]["state"] == "subscribed"
        app.state.market.clock = lambda: NOW + timedelta(seconds=2)
        client.portal.call(app.state.market.handle_message, message())
        observation = until(socket, "market_observation")
        assert observation["schema_version"] == 1
        assert observation["source"] == "yahoo_finance"
        assert observation["subscription_id"] == 1
        assert observation["source_timestamp"] == "2026-01-06T15:00:30.000000Z"
        assert observation["received_timestamp"] == "2026-01-06T15:00:32.000000Z"
        assert observation["data_age_seconds"] == 2
        assert observation["revision"] == 1
        assert observation["candle_complete"] is None
        assert observation["data"]["price"] == 100
        stored = client.get("/api/market/observations").json()["observations"][0]
        assert observation["data"] == stored  # Broadcast uses committed record, not reconstructed fields.
        candle = until(socket, "candle_update")
        assert candle["interval"] == "1m" and candle["candle_complete"] is False
        assert candle["data"]["volume"] is None
        app.state.market.repository.complete_due(NOW.replace(minute=1))
        completed = until(socket, "candle_completed")
        assert completed["revision"] == 2 and completed["candle_complete"] is True
        client.portal.call(app.state.market.handle_message, message())
        assert len(client.get("/api/market/observations").json()["observations"]) == 1
        assert app.state.market.status.duplicates == 1


def test_multiple_clients_and_symbol_switching_are_isolated(app):
    with TestClient(app) as client:
        with client.websocket_connect("/ws/market") as first, client.websocket_connect("/ws/market") as second:
            first.receive_json(); second.receive_json()
            subscribe(first); subscribe(second)
            client.portal.call(app.state.market.handle_message, message())
            one = until(first, "market_observation")
            two = until(second, "market_observation")
            assert one["event_id"] == two["event_id"]
            assert len(app.state.market_hub.clients) == 2
            subscribe(second, "MSFT", 2)
            client.portal.call(app.state.market.handle_message, message(price=200, id="MSFT"))
            switched = until(second, "market_observation", symbol="MSFT")
            assert switched["subscription_id"] == 2 and switched["data"]["symbol"] == "MSFT"
            client.portal.call(app.state.market.handle_message, message(price=101))
            assert until(first, "market_observation")["data"]["price"] == 101
            # Switching back gets persisted latest data, not a second provider subscription.
            subscribe(second, "AAPL", 3)
            snapshot = until(second, "market_observation")
            assert snapshot["data"]["snapshot"] is True
            assert snapshot["data"]["price"] == 101
            assert app.state.market.status.attempts == 0
        # A new browser can resubscribe after clean disconnect.
        with client.websocket_connect("/ws/market") as reconnected:
            reconnected.receive_json(); subscribe(reconnected)
            assert until(reconnected, "market_observation")["data"]["price"] == 101


@pytest.mark.parametrize("payload", [
    {"type": "subscribe", "symbol": "INVALID", "request_id": 1},
    {"type": "subscribe", "symbol": "AAPL", "request_id": True},
    {"type": "subscribe", "symbol": "AAPL", "request_id": -1},
    {"type": "unknown"}, [], None,
])
def test_invalid_subscriptions_do_not_break_socket(app, payload):
    with TestClient(app) as client, client.websocket_connect("/ws/market") as socket:
        socket.receive_json()
        socket.send_json(payload)
        error = until(socket, "error")
        assert error["data"]["code"] == "invalid_subscription"
        assert subscribe(socket)["data"]["state"] == "subscribed"


def test_invalid_json_origin_and_snapshot_error(app, monkeypatch):
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/market", headers={"origin": "https://untrusted.example"}):
                pass
        with client.websocket_connect("/ws/market", headers={"origin": "http://localhost:5173"}) as socket:
            socket.receive_json(); socket.send_bytes(b"not-a-text-frame")
            assert until(socket, "error")["data"]["message"] == "Expected a JSON text frame"
            socket.send_text("not-json")
            assert until(socket, "error")["data"]["code"] == "invalid_subscription"
            def fail(*args):
                raise sqlite3.OperationalError("private details")
            monkeypatch.setattr(app.state.market.repository, "latest_quote", fail)
            subscribe(socket)
            error = until(socket, "error")
            assert error["data"] == {"code": "database_unavailable", "message": "Market snapshot unavailable"}


def test_feed_disconnection_does_not_disconnect_browser(app):
    with TestClient(app) as client, client.websocket_connect("/ws/market") as socket:
        socket.receive_json(); subscribe(socket)
        client.portal.call(app.state.market.handle_message, message())
        until(socket, "market_observation")
        app.state.market.status.state = "disconnected"
        # A status queued before the transition is valid; wait for the new state.
        for _ in range(50):
            frame = until(socket, "feed_status")
            if frame["feed_status"]["state"] == "disconnected":
                break
        assert frame["feed_status"]["state"] == "disconnected"
        assert frame["feed_status"]["transport_connected"] is False
        client.portal.call(app.state.market.handle_message, message(price=102))
        assert until(socket, "market_observation")["data"]["price"] == 102


def test_one_shared_provider_session_for_multiple_browsers(tmp_path):
    created = []
    stream = FakeStream(events=[message()])
    application = create_app(Settings(database_path=tmp_path / "shared.sqlite3", feed_enabled=True))
    application.state.market.clock = lambda: NOW
    application.state.market_hub.status_seconds = .01
    def factory():
        created.append(stream)
        return stream
    application.state.market.stream_factory = factory
    with TestClient(application) as client:
        with client.websocket_connect("/ws/market") as first, client.websocket_connect("/ws/market") as second:
            first.receive_json(); second.receive_json()
            subscribe(first); subscribe(second, "NVDA")
            assert created == [stream]
            assert stream.subscriptions == {"AAPL", "MSFT", "NVDA", "SPY"}
    assert stream.closed


def test_slow_client_is_bounded_and_shutdown_closes_sockets(app):
    async def overflow():
        hub = app.state.market_hub
        slow = MarketClient(None, "AAPL")
        for _ in range(129):
            hub.send(slow, "feed_status")
        assert slow.closing.is_set() and slow.close_code == 1013
        assert slow.queue.qsize() == 128
    asyncio.run(overflow())
    with TestClient(app) as client, client.websocket_connect("/ws/market") as socket:
        socket.receive_json(); subscribe(socket)
        client.portal.call(app.state.market_hub.stop)
        with pytest.raises(WebSocketDisconnect) as caught:
            while True:
                socket.receive_json()
        assert caught.value.code == 1012


def test_rollback_emits_no_committed_events(app, monkeypatch):
    events = []
    repository = app.state.market.repository
    repository.on_commit = events.extend
    original = repository.database.insert_observation
    def fail(**values):
        if values["observation_type"] == "constructed_candle":
            raise sqlite3.OperationalError("mock rollback")
        return original(**values)
    with TestClient(app):
        monkeypatch.setattr(repository.database, "insert_observation", fail)
        with pytest.raises(Exception):
            asyncio.run(app.state.market.handle_message(message()))
        assert events == []
        assert repository.database.retrieve() == []


def test_disconnecting_one_client_does_not_affect_other_clients_or_ingestion(app):
    with TestClient(app) as client, client.websocket_connect("/ws/market") as survivor:
        survivor.receive_json(); subscribe(survivor)
        with client.websocket_connect("/ws/market") as leaving:
            leaving.receive_json(); subscribe(leaving)
            assert len(app.state.market_hub.clients) == 2
        assert len(app.state.market_hub.clients) == 1
        client.portal.call(app.state.market.handle_message, message(price=105))
        assert until(survivor, "market_observation")["data"]["price"] == 105
        assert len(app.state.market.repository.observations("AAPL", 100)) == 1


def test_freshness_is_tracked_separately_for_each_stock(app):
    with TestClient(app) as client:
        client.portal.call(app.state.market.handle_message, message())
        client.portal.call(app.state.market.handle_message, message(id="MSFT", seconds=-60))
        assert app.state.market.snapshot("AAPL")["source_data_age_seconds"] == 0
        snapshot = app.state.market.snapshot("MSFT")
        assert snapshot["source_data_age_seconds"] == 60
        assert snapshot["seconds_since_receipt"] == 0
        assert snapshot["symbol"] == "MSFT"
        assert app.state.market.snapshot("SPY")["latest_source_timestamp"] is None


def test_all_live_intervals_broadcast_and_restore_snapshots(app):
    with TestClient(app) as client, client.websocket_connect('/ws/market') as first:
        first.receive_json(); subscribe(first)
        client.portal.call(app.state.market.handle_message,message())
        updates=[until(first,'candle_update') for _ in range(3)]
        assert {item['interval'] for item in updates} == {'1m','5m','15m'}
        assert all(not item['candle_complete'] for item in updates)
        assert len(client.get('/api/market/observations').json()['observations']) == 1
        assert set(client.get('/api/market/symbols').json()['live_intervals']) == {'1m','5m','15m'}
        with client.websocket_connect('/ws/market') as second:
            second.receive_json(); subscribe(second)
            snapshots=[until(second,'candle_update') for _ in range(3)]
            assert {item['interval'] for item in snapshots} == {'1m','5m','15m'}
            assert all(item['data']['snapshot'] for item in snapshots)
