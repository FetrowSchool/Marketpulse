"""Normalize decoded yfinance PricingData messages without inventing OHLCV."""
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.database import utc_timestamp

SUPPORTED_SYMBOLS = ("AAPL", "MSFT", "NVDA", "SPY")
INTERVALS = {"1m": 60, "5m": 300, "15m": 900}
SOURCE = "yahoo_finance"


@dataclass(frozen=True)
class PriceObservation:
    symbol: str
    source_timestamp: str
    received_timestamp: str
    price: float
    source_observation_id: str
    payload: dict
    data_mode: str
    data_source: str = SOURCE
    observation_type: str = "raw_provider"

    def record(self):
        return dict(symbol=self.symbol, data_source=self.data_source,
                    source_observation_id=self.source_observation_id,
                    observation_type=self.observation_type, data_mode=self.data_mode,
                    source_timestamp=self.source_timestamp,
                    received_timestamp=self.received_timestamp, payload=self.payload)


def normalize_message(message, received_at: datetime, *, symbol: str,
                      data_mode="delayed", max_future_seconds=5) -> PriceObservation:
    """Yahoo time is epoch milliseconds; id is a ticker, NOT an event ID.

    No unique event sequence is exposed by the inspected PricingData schema.
    Exact canonical payload fingerprints suppress reconnect retransmissions but
    cannot distinguish genuinely separate identical provider events.
    """
    received = utc_timestamp(received_at)
    received_at = datetime.fromisoformat(received.replace("Z", "+00:00"))
    if not isinstance(message, dict) or message.get("id") != symbol or symbol not in SUPPORTED_SYMBOLS:
        raise ValueError("Missing or unexpected Yahoo symbol")
    if data_mode not in ("live", "delayed", "recorded", "simulated"):
        raise ValueError("Invalid data provenance")
    price = message.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError("Missing or invalid price")
    timestamp = message.get("time")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (str, int)):
        raise ValueError("Missing epoch millisecond timestamp")
    try:
        milliseconds = int(timestamp)
        if str(milliseconds) != str(timestamp) or milliseconds < 946684800000:
            raise ValueError("Expected epoch milliseconds since 2000")
        source_at = datetime.fromtimestamp(milliseconds // 1000, timezone.utc).replace(
            microsecond=(milliseconds % 1000) * 1000)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("Invalid epoch millisecond timestamp") from exc
    if (source_at - received_at).total_seconds() > max_future_seconds:
        raise ValueError("Source timestamp exceeds allowed clock skew")
    # Preserve provider fields exactly as decoded, including unknown metadata.
    encoded = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False)
    original = json.loads(encoded)
    identity = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
    payload = {"normalization_version": 1, "kind": "price_observation", "price": float(price),
               "identity_strategy": "decoded_payload_sha256", "provider_event_id": None,
               "provider_volume": {key: original[key] for key in ("day_volume", "last_size", "vol_24hr") if key in original},
               "volume_semantics": "unverified_provider_totals_or_sizes; not interval volume",
               "original": original}
    return PriceObservation(symbol, utc_timestamp(source_at), received, float(price), identity, payload, data_mode)
