import pytest
from app.services.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "market.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def observation():
    # Explicitly simulated test fixture; never served to the dashboard.
    return dict(symbol="TEST", data_source="test-fixture", source_observation_id="event-1",
        observation_type="raw_provider", data_mode="simulated",
        source_timestamp="2026-01-01T10:00:00Z",
        payload={"price": 100, "provider_fields": ["price", "timestamp"]})


@pytest.fixture(autouse=True)
def disable_real_feed(monkeypatch):
    # Tests must never open a real provider connection.
    monkeypatch.setenv("MARKETPULSE_FEED_ENABLED", "false")
