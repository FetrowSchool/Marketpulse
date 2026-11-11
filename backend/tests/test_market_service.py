"""Deterministic synthetic streams: these tests NEVER call Yahoo."""
import asyncio
import sqlite3
from dataclasses import replace
from datetime import timedelta
import pytest

from app.config import Settings
from app.services.market_data import FeedStatus, MarketDataService, PersistenceFailure
from app.services.yahoo_stream import StreamingUnavailable, YahooStream
from test_market_processing import NOW, message


def settings(**values):
    return Settings(feed_enabled=True, reconnect_base_seconds=.01, reconnect_max_seconds=.015,
                    max_reconnect_attempts=3, **values)


class FakeStream:
    def __init__(self, *, fail_connect=False, events=()):
        self.fail_connect, self.events = fail_connect, list(events)
        self.closed = False
        self.symbol = None
        self.connected = asyncio.Event()

    async def connect(self, symbol):
        if self.fail_connect:
            raise ConnectionError("synthetic connection failure")
        self.symbol = symbol[0] if isinstance(symbol, list) else symbol
        self.subscriptions = set(symbol) if isinstance(symbol, list) else {symbol}
        self.connected.set()

    async def subscribe(self, symbols):
        self.subscriptions = set([self.symbol, *symbols])

    async def receive(self):
        if self.events:
            value = self.events.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        await asyncio.Event().wait()

    async def close(self):
        self.closed = True


async def wait_for(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(.001)
    await asyncio.wait_for(poll(), 2)


def test_connect_failure_bounded_exponential_backoff(db):
    async def scenario():
        streams, delays = [], []
        def factory():
            stream = FakeStream(fail_connect=True)
            streams.append(stream)
            return stream
        async def sleep(delay):
            delays.append(delay)
        service = MarketDataService(db, settings(), stream_factory=factory, sleep=sleep)
        await service.run()
        assert service.status.state == "unavailable"
        assert service.status.last_error == "reconnect_attempts_exhausted"
        assert service.status.attempts == 3
        assert delays == [.01, .015]
        assert all(stream.closed for stream in streams)
    asyncio.run(scenario())


def test_reconnect_resubscribes_deduplicates_and_shutdown_closes(db):
    async def scenario():
        first = FakeStream(events=[message(), ConnectionError("synthetic disconnect")])
        second = FakeStream(events=[message()])
        streams = iter([first, second])
        service = MarketDataService(db, settings(), stream_factory=lambda: next(streams), clock=lambda: NOW)
        task = asyncio.create_task(service.run())
        service.tasks = [task]
        await wait_for(lambda: service.status.duplicates == 1)
        assert first.closed
        assert first.symbol == second.symbol == "AAPL"
        assert service.status.attempts == 2 and service.status.accepted == 1
        assert len(service.repository.observations("AAPL", 100)) == 1
        await service.stop()
        assert second.closed and task.done()
        assert service.status.state == "disconnected"
    asyncio.run(scenario())


def test_unavailable_streaming_does_not_poll_or_retry(db):
    async def scenario():
        def unavailable():
            raise StreamingUnavailable("synthetic incompatible library")
        service = MarketDataService(db, settings(), stream_factory=unavailable)
        await service.run()
        assert service.status.state == "unavailable"
        assert service.status.last_error == "streaming_incompatible"
        assert service.status.attempts == 1
    asyncio.run(scenario())


def test_database_failure_is_visible_and_not_network_retried(db, monkeypatch):
    async def scenario():
        stream = FakeStream(events=[message()])
        service = MarketDataService(db, settings(), stream_factory=lambda: stream, clock=lambda: NOW)
        def fail(*args):
            raise sqlite3.OperationalError("synthetic persistence failure")
        monkeypatch.setattr(service.repository, "ingest", fail)
        await service.run()
        assert service.status.database_error and service.status.state == "unavailable"
        assert service.status.last_error == "database_error"
        assert service.status.attempts == 1 and stream.closed
        assert service.status.accepted == 0
    asyncio.run(scenario())


def test_completion_database_failure_is_visible(db, monkeypatch):
    async def scenario():
        service = MarketDataService(db, settings(), clock=lambda: NOW)
        def fail(*args):
            raise sqlite3.OperationalError("synthetic persistence failure")
        monkeypatch.setattr(service.repository, "complete_due", fail)
        await service.complete_loop()
        assert service.status.snapshot(NOW)["persistence"] == "failed"
        assert service.status.state == "unavailable"
    asyncio.run(scenario())


def test_rejected_messages_and_source_highwater_are_separate_from_receipt(db):
    async def scenario():
        clock = [NOW]
        service = MarketDataService(db, settings(), clock=lambda: clock[0])
        await service.handle_message({"id": "AAPL"})
        assert service.status.rejected == 1 and service.status.source_at is None
        await service.handle_message(message())
        clock[0] += timedelta(seconds=10)
        await service.handle_message(message(90, -10))
        assert service.status.source_at == NOW
        assert service.status.received_at == NOW + timedelta(seconds=10)
        snapshot = service.status.snapshot(clock[0])
        assert snapshot["source_data_age_seconds"] == 10
        assert snapshot["seconds_since_receipt"] == 0
    asyncio.run(scenario())


def test_feed_freshness_session_and_transport_states():
    status = FeedStatus(settings(realtime_confirmed=True), connected=True,
                        source_at=NOW, received_at=NOW, connected_at=NOW)
    assert status.snapshot(NOW)["state"] == "live"
    assert status.snapshot(NOW + timedelta(seconds=30))["state"] == "delayed"
    assert status.snapshot(NOW + timedelta(seconds=121))["state"] == "stale"
    status.source_at = NOW + timedelta(seconds=121)
    assert status.snapshot(NOW + timedelta(seconds=121))["state"] == "stale"  # Old receipt.
    status.source_at = status.received_at = NOW
    status.settings = replace(status.settings, realtime_confirmed=False)
    assert status.snapshot(NOW)["state"] == "real_time_unverified"
    assert status.snapshot(NOW)["reason"] == "realtime_entitlement_unverified"
    sunday = NOW + timedelta(days=5)
    status.source_at = status.received_at = sunday
    status.settings = replace(status.settings, realtime_confirmed=True)
    assert status.snapshot(sunday)["state"] == "real_time_unverified"
    assert status.snapshot(sunday)["market_session"] == "regular_session_weekend_closed"
    status.connected, status.state = False, "disconnected"
    assert status.snapshot(sunday)["state"] == "disconnected"
    status.state = "unavailable"
    assert status.snapshot(sunday)["state"] == "unavailable"


def test_connected_socket_without_observations_is_not_live():
    status = FeedStatus(settings(), connected=True, connected_at=NOW)
    assert status.snapshot(NOW)["state"] == "connecting"
    assert status.snapshot(NOW + timedelta(seconds=121))["state"] == "stale"
    assert status.snapshot(NOW)["source_data_age_seconds"] is None


@pytest.mark.parametrize("values", [
    {"active_symbol": "INVALID"}, {"candle_interval": "2m"},
    {"fresh_seconds": -1}, {"stale_seconds": 1}, {"max_reconnect_attempts": 0},
    {"fresh_seconds": float("nan")},
])
def test_configuration_validation(values):
    with pytest.raises(ValueError):
        Settings(**values)


def test_adapter_rejects_uninspected_version(monkeypatch):
    import yfinance
    monkeypatch.setattr(yfinance, "__version__", "unsupported-test-version")
    with pytest.raises(StreamingUnavailable):
        YahooStream()


def test_connect_timeout_closes_and_stops_after_budget(db):
    async def scenario():
        class HangingStream(FakeStream):
            async def connect(self, symbol):
                await asyncio.Event().wait()
        stream = HangingStream()
        config = replace(settings(), connect_timeout_seconds=.01, max_reconnect_attempts=1)
        service = MarketDataService(db, config, stream_factory=lambda: stream)
        await service.run()
        assert service.status.attempts == 1 and stream.closed
        assert service.status.state == "unavailable"
    asyncio.run(scenario())


def test_installed_yfinance_decodes_synthetic_protobuf_without_network():
    import base64
    import json
    from yfinance.pricing_pb2 import PricingData
    async def scenario():
        wire = PricingData(id="AAPL", price=123.5,
                           time=int(NOW.timestamp() * 1000), day_volume=123456)
        envelope = json.dumps({"message": base64.b64encode(wire.SerializeToString()).decode()})
        class WireSocket:
            async def recv(self):
                return envelope
            async def close(self):
                pass
        adapter = YahooStream()
        adapter.client._ws = WireSocket()
        decoded = await adapter.receive()
        assert decoded["id"] == "AAPL" and decoded["price"] == 123.5
        assert decoded["time"] == str(int(NOW.timestamp() * 1000))
        assert decoded["day_volume"] == "123456"
        await adapter.close()
    asyncio.run(scenario())


def test_unverified_freshness_thresholds_preserve_provenance_and_session_context():
    status = FeedStatus(settings(realtime_confirmed=False), connected=True,
                        source_at=NOW, received_at=NOW, connected_at=NOW)
    assert status.snapshot(NOW + timedelta(seconds=15))["state"] == "real_time_unverified"
    assert status.snapshot(NOW + timedelta(seconds=16))["state"] == "delayed"
    assert status.snapshot(NOW + timedelta(seconds=120))["state"] == "delayed"
    assert status.snapshot(NOW + timedelta(seconds=121))["state"] == "stale"
    status.source_at = NOW + timedelta(seconds=16)
    assert status.snapshot(status.source_at)["state"] == "delayed"  # Receipt independently old.
    sunday = NOW + timedelta(days=5)
    status.source_at = status.received_at = sunday
    fresh = status.snapshot(sunday)
    assert fresh["state"] == "real_time_unverified"
    assert fresh["reason"] == "outside_regular_trading_window"
    assert fresh["market_session_verified"] is False and fresh["data_mode"] == "delayed"
