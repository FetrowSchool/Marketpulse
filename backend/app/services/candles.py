"""Deterministic source-time quote candles; never presented as exchange OHLCV."""
import json
from datetime import datetime, timedelta, timezone

from app.services.database import utc_timestamp
from app.services.normalization import INTERVALS


def candle_bounds(source_timestamp, interval):
    timestamp = datetime.fromisoformat(utc_timestamp(source_timestamp).replace("Z", "+00:00"))
    seconds = INTERVALS[interval]
    start = datetime.fromtimestamp((int(timestamp.timestamp()) // seconds) * seconds, timezone.utc)
    return start, start + timedelta(seconds=seconds)


def build_candle(rows, interval, now):
    """rows are effective latest raw revisions, already filtered to one bucket.

    Source time determines open/close. Equal-time messages use ingest ID as an
    explicit tie-break because Yahoo exposes no source sequence number.
    """
    if not rows:
        raise ValueError("Cannot build an empty candle")
    rows = sorted(rows, key=lambda row: (row["source_timestamp"], row["id"]))
    start, end = candle_bounds(rows[0]["source_timestamp"], interval)
    if any(candle_bounds(row["source_timestamp"], interval)[0] != start for row in rows):
        raise ValueError("Mixed candle intervals")
    prices = [json.loads(row["payload_json"])["price"] for row in rows]
    mode = rows[0]["data_mode"]
    return dict(symbol=rows[0]["symbol"], data_source=rows[0]["data_source"],
        source_observation_id=f"quote-candle-v1:{mode}:{interval}:{utc_timestamp(start)}",
        observation_type="constructed_candle", data_mode=mode,
        source_timestamp=rows[-1]["source_timestamp"], received_timestamp=utc_timestamp(now),
        candle_interval=interval, candle_open_timestamp=utc_timestamp(start),
        open=prices[0], high=max(prices), low=min(prices), close=prices[-1], volume=None,
        candle_complete=now >= end,
        payload={"construction": "source_time_quotes_v1", "candle_origin": "locally_constructed",
                 "contributing_observation_ids": [row["id"] for row in rows],
                 "observation_count": len(rows), "tie_break": "ingest_id",
                 "volume_unavailable_reason": "No reliable interval trade volume in Yahoo quote stream",
                 "coverage": "observed_quotes_only; gaps and late corrections possible"})
