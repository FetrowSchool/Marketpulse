from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


def test_health_initializes_database_and_reports_connectivity(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "health.sqlite3", version="test-version"))
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected", "version": "test-version"}
        assert app.state.database.is_connected()


def test_health_database_failure_does_not_expose_details(tmp_path, monkeypatch):
    app = create_app(Settings(database_path=tmp_path / "health.sqlite3"))
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.database, "is_connected", lambda: False)
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"status": "degraded", "database": "unavailable", "version": "0.1.0"}


def test_cors_local_origin_and_untrusted_origin(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "health.sqlite3"))
    with TestClient(app) as client:
        for origin, allowed in [("http://localhost:5173", True), ("https://untrusted.example", False)]:
            response = client.get("/api/health", headers={"Origin": origin})
            assert (response.headers.get("access-control-allow-origin") == origin) is allowed


def test_environment_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKETPULSE_DB_PATH", str(tmp_path / "env.sqlite3"))
    monkeypatch.setenv("MARKETPULSE_VERSION", "env-test")
    monkeypatch.setenv("MARKETPULSE_CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")
    settings = Settings()
    assert settings.database_path == tmp_path / "env.sqlite3"
    assert settings.version == "env-test"
    assert len(settings.cors_origins) == 2
