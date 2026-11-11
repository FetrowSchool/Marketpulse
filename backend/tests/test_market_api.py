import asyncio
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from test_market_processing import NOW, message


def test_market_api_empty_defaults_and_persisted_data(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.sqlite3", feed_enabled=False))
    app.state.market.clock = lambda: NOW
    with TestClient(app) as client:
        symbols = client.get("/api/market/symbols").json()
        assert symbols["symbols"] == ["AAPL", "MSFT", "NVDA", "SPY"]
        assert symbols["active_symbol"] == "AAPL"
        assert client.get("/api/market/status").json()["reason"] == "feed_disabled"
        assert client.get("/api/market/observations").json()["observations"] == []
        asyncio.run(app.state.market.handle_message(message()))
        result = client.get("/api/market/observations?symbol=AAPL&limit=1").json()
        row, = result["observations"]
        assert row["price"] == 100
        assert row["data_mode"] == "delayed"
        assert row["metadata"]["original"] == message()
        assert client.get(f"/api/market/observations?after_id={row['id']}").json()["observations"] == []
        candle, = client.get("/api/market/candles").json()["candles"]
        assert candle["observation_type"] == "constructed_candle"
        assert candle["volume"] is None and candle["candle_complete"] is False
        assert client.get("/api/market/candles?symbol=MSFT").json()["candles"] == []
        app.state.market.repository.complete_due(NOW.replace(minute=1))
        assert len(client.get("/api/market/candles?revisions=true").json()["candles"]) == 2
        assert len(client.get("/api/market/candles").json()["candles"]) == 1


@pytest.mark.parametrize("path", [
    "observations?symbol=INVALID", "observations?limit=0", "observations?limit=1001",
    "observations?after_id=-1", "observations?limit=abc", "candles?interval=2m",
    "candles?symbol=invalid", "candles?limit=-1", "candles?revisions=invalid",
])
def test_invalid_queries_return_422(tmp_path, path):
    app = create_app(Settings(database_path=tmp_path / "api.sqlite3", feed_enabled=False))
    with TestClient(app) as client:
        assert client.get("/api/market/" + path).status_code == 422


def test_market_database_errors_are_clear_and_safe(tmp_path, monkeypatch):
    app = create_app(Settings(database_path=tmp_path / "api.sqlite3", feed_enabled=False))
    def fail(*args):
        raise sqlite3.OperationalError("private/path must not leak")
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.market.repository, "observations", fail)
        response = client.get("/api/market/observations")
        assert response.status_code == 503
        assert response.json() == {"detail": "Market database unavailable"}


def test_active_symbol_and_interval_configuration(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "api.sqlite3", feed_enabled=False,
                              active_symbol="NVDA", candle_interval="5m"))
    with TestClient(app) as client:
        assert client.get("/api/market/symbols").json()["active_symbol"] == "NVDA"
        assert client.get("/api/market/symbols").json()["active_interval"] == "5m"
        assert client.get("/api/market/observations").json()["symbol"] == "NVDA"
        assert client.get("/api/market/candles").json()["interval"] == "5m"


def test_enabled_lifespan_uses_injected_stream_and_shuts_down(tmp_path):
    import time
    from test_market_service import FakeStream
    stream = FakeStream(events=[message()])
    app = create_app(Settings(database_path=tmp_path / "lifecycle.sqlite3", feed_enabled=True))
    app.state.market.clock = lambda: NOW
    app.state.market.stream_factory = lambda: stream
    with TestClient(app) as client:
        deadline = time.monotonic() + 3
        while client.get("/api/market/status").json()["accepted_observations"] == 0:
            assert time.monotonic() < deadline
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/market/status").json()["transport_connected"] is True
    assert stream.closed
    assert all(task.done() for task in app.state.market.tasks)
