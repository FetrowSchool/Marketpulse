import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = field(default_factory=lambda: Path(os.getenv(
        "MARKETPULSE_DB_PATH", str(Path(__file__).resolve().parents[1] / "data/marketpulse.sqlite3"))))
    version: str = field(default_factory=lambda: os.getenv("MARKETPULSE_VERSION", "0.1.0"))
    cors_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        value.strip() for value in os.getenv("MARKETPULSE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173").split(",") if value.strip()))

    feed_enabled: bool = field(default_factory=lambda: env_bool("MARKETPULSE_FEED_ENABLED", True))
    active_symbol: str = field(default_factory=lambda: os.getenv("MARKETPULSE_SYMBOL", "AAPL").strip().upper())
    candle_interval: str = field(default_factory=lambda: os.getenv("MARKETPULSE_CANDLE_INTERVAL", "1m"))
    realtime_confirmed: bool = field(default_factory=lambda: env_bool("MARKETPULSE_REALTIME_CONFIRMED", False))
    fresh_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_FRESH_SECONDS", "15")))
    stale_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_STALE_SECONDS", "120")))
    max_future_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_MAX_FUTURE_SECONDS", "5")))
    connect_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_CONNECT_TIMEOUT_SECONDS", "15")))
    close_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_CLOSE_TIMEOUT_SECONDS", "5")))
    reconnect_base_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_RECONNECT_BASE_SECONDS", "1")))
    reconnect_max_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_RECONNECT_MAX_SECONDS", "30")))
    max_reconnect_attempts: int = field(default_factory=lambda: int(os.getenv("MARKETPULSE_MAX_RECONNECT_ATTEMPTS", "5")))
    completion_check_seconds: float = field(default_factory=lambda: float(os.getenv("MARKETPULSE_COMPLETION_CHECK_SECONDS", "1")))

    def __post_init__(self):
        import math
        from app.services.normalization import INTERVALS, SUPPORTED_SYMBOLS
        if self.active_symbol not in SUPPORTED_SYMBOLS or self.candle_interval not in INTERVALS:
            raise ValueError("Unsupported MarketPulse symbol or candle interval")
        numbers = (self.fresh_seconds, self.stale_seconds, self.max_future_seconds,
                   self.connect_timeout_seconds, self.close_timeout_seconds,
                   self.reconnect_base_seconds, self.reconnect_max_seconds, self.completion_check_seconds)
        if any(not math.isfinite(value) or value <= 0 for value in numbers):
            raise ValueError("Feed thresholds/timeouts must be positive and finite")
        if self.stale_seconds < self.fresh_seconds or self.reconnect_max_seconds < self.reconnect_base_seconds:
            raise ValueError("Invalid freshness or backoff threshold order")
        if not 1 <= self.max_reconnect_attempts <= 20:
            raise ValueError("Reconnect attempts must be between 1 and 20")


def env_bool(name, default):
    value = os.getenv(name, str(default)).lower()
    if value not in ("true", "false", "1", "0"):
        raise ValueError(f"{name} must be true or false")
    return value in ("true", "1")
