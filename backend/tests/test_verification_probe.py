"""Mocked probe regression: recorded snapshots must not prove live-provider receipt."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('market_probe', Path(__file__).parents[1] / 'scripts/verify_market_socket.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('snapshot', [True, False])
def test_probe_distinguishes_snapshots_and_queries_exact_record(monkeypatch, snapshot):
    row = {'id': 2001, 'symbol': 'AAPL', 'price': 100, 'source_timestamp': '2026-01-01T00:00:00.000000Z'}
    if snapshot:
        row['snapshot'] = True
    frames = [json.dumps({'type': kind, 'feed_status': {'state': 'delayed'}, 'data': row})
              for kind in ('market_observation', 'candle_update')]
    class Socket:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def send(self, text): pass
        async def recv(self):
            if frames: return frames.pop(0)
            raise TimeoutError
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params):
            assert params['after_id'] == 2000 and params['limit'] == 1
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'observations': [row]})
    monkeypatch.setattr(probe, 'connect', lambda *args, **kwargs: Socket())
    monkeypatch.setattr(probe.httpx, 'AsyncClient', Client)
    result = asyncio.run(probe.verify('ws://localhost/ws/market', 'AAPL', 1))
    if snapshot:
        assert result['outcome'] == 'socket_connected_saved_snapshots_only'
        assert not result['records'] and len(result['snapshot_records']) == 2
        assert 'database_record_matches_socket' not in result
    else:
        assert result['outcome'] == 'provider_to_sqlite_to_websocket_verified'
        assert result['database_record_matches_socket'] is True
        assert not result['snapshot_records']
    assert result['realtime_entitlement_verified'] is False
