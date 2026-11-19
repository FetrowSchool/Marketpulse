"""User feed recovery with mocked Yahoo connections and isolated SQLite only."""
import asyncio,sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.services.market_data import MarketDataService,PersistenceFailure
from test_market_service import FakeStream,wait_for


def test_enables_disabled_feed_and_coalesces_multiple_clients(db):
    async def scenario():
        streams=[]
        def factory():
            stream=FakeStream();streams.append(stream);return stream
        service=MarketDataService(db,Settings(database_path=db.path,feed_enabled=False),stream_factory=factory)
        service.start();assert not service.tasks
        results=await asyncio.gather(service.reconnect(),service.reconnect())
        await wait_for(lambda:len(streams)==1 and streams[0].connected.is_set())
        assert sum(r['requested'] for r in results)==1
        assert len(service.tasks)==2 and service.settings.feed_enabled
        service.start();assert len(service.tasks)==2
        assert streams[0].subscriptions=={'AAPL','MSFT','NVDA','SPY'}
        assert service.snapshot()['state']!='live'  # No observation received.
        await service.stop();assert streams[0].closed
    asyncio.run(scenario())


def test_failed_storage_stays_visible_and_can_retry_after_recovery(db,monkeypatch):
    async def scenario():
        service=MarketDataService(db,Settings(database_path=db.path,feed_enabled=False),stream_factory=FakeStream)
        original=db.transaction
        def fail():raise sqlite3.OperationalError('private path')
        monkeypatch.setattr(db,'transaction',fail)
        with pytest.raises(PersistenceFailure):await service.reconnect()
        assert service.snapshot()['persistence']=='failed' and not service.tasks
        monkeypatch.setattr(db,'transaction',original)
        result=await service.reconnect()
        assert result['requested'] and result['feed_status']['persistence']=='no_failure_reported'
        await service.stop()
    asyncio.run(scenario())


def test_existing_connection_closes_before_new_shared_session(db):
    async def scenario():
        streams=[]
        def factory():
            if streams:assert streams[-1].closed
            stream=FakeStream();streams.append(stream);return stream
        service=MarketDataService(db,Settings(database_path=db.path,feed_enabled=True),stream_factory=factory)
        service.start();await wait_for(lambda:len(streams)==1 and streams[0].connected.is_set())
        await service.reconnect();await wait_for(lambda:len(streams)==2 and streams[1].connected.is_set())
        assert streams[0].closed and len(service.tasks)==2
        await service.stop()
    asyncio.run(scenario())


def test_api_safe_errors_origin_and_no_account_changes(db,monkeypatch):
    app=create_app(Settings(database_path=db.path,feed_enabled=False))
    app.state.market.stream_factory=FakeStream
    with TestClient(app) as client:
        before=client.get('/api/paper/account').json()
        assert client.post('/api/market/reconnect',headers={'Origin':'https://untrusted.example'}).status_code==403
        def fail():raise sqlite3.OperationalError('private path')
        monkeypatch.setattr(app.state.market,'_check_restart_storage',fail)
        response=client.post('/api/market/reconnect')
        assert response.status_code==503 and 'private path' not in response.text
        monkeypatch.undo()
        response=client.post('/api/market/reconnect',headers={'Origin':'http://127.0.0.1:5173'})
        assert response.status_code==202 and response.json()['requested']
        assert client.get('/api/paper/account').json()['cash']==before['cash']
        assert client.get('/api/strategy/status').json()['enabled'] is False
        assert client.get('/api/paper/orders').json()['orders']==[]
