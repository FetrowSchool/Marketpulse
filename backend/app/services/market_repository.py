"""Atomic raw observation + candle revision persistence, rebuilt from SQLite."""
import json
from contextlib import closing

from app.services.candles import build_candle, candle_bounds
from app.services.database import utc_timestamp
from app.services.normalization import SOURCE, INTERVALS


class MarketRepository:
    def __init__(self, database, *, symbol, interval, data_mode, on_commit=None, intervals=None):
        self.on_commit = on_commit
        self.database, self.symbol = database, symbol
        self.interval, self.data_mode = interval, data_mode
        self.intervals = tuple(dict.fromkeys(intervals or (interval,)))
        if interval not in self.intervals or any(value not in INTERVALS for value in self.intervals):
            raise ValueError("Unsupported candle construction interval")

    def _bucket_rows(self, conn, start, end):
        # Latest revision per observation identity BEFORE filtering the time window:
        # a corrected explicit identity may move into/out of a bucket.
        return [dict(row) for row in conn.execute("""
            WITH effective AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY data_source,symbol,observation_type,source_observation_id
                    ORDER BY revision DESC) AS rank
                FROM observations WHERE symbol=? AND data_source=? AND observation_type='raw_provider'
                AND data_mode=?
            ) SELECT * FROM effective WHERE rank=1 AND source_timestamp>=? AND source_timestamp<?
              AND json_extract(payload_json, '$.normalization_version')=1
            ORDER BY source_timestamp,id
        """, (self.symbol, SOURCE, self.data_mode, utc_timestamp(start), utc_timestamp(end)))]

    def _append_candle(self, conn, rows, now, interval=None):
        candle = build_candle(rows, interval or self.interval, now)
        previous = conn.execute("""
            SELECT candle_complete FROM observations WHERE symbol=? AND data_source=?
              AND observation_type='constructed_candle' AND source_observation_id=?
            ORDER BY revision DESC LIMIT 1
        """, (self.symbol, SOURCE, candle["source_observation_id"])).fetchone()
        # An elapsed bucket must not become provisional if the wall clock rolls back.
        if previous and previous["candle_complete"]:
            candle["candle_complete"] = True
        return self.database.insert_observation(**candle, connection=conn)

    def ingest(self, observation, now):
        if observation.symbol != self.symbol or observation.data_mode != self.data_mode:
            raise ValueError("Observation does not match repository stream")
        events = []
        with self.database.transaction() as conn:
            changed = conn.total_changes
            raw_id = self.database.insert_observation(**observation.record(), connection=conn)
            inserted = conn.total_changes > changed
            if inserted:
                identifiers = [raw_id]
                for interval in self.intervals:
                    start, end = candle_bounds(observation.source_timestamp, interval)
                    rows = self._bucket_rows(conn, start, end)
                    identifiers.append(self._append_candle(conn, rows, now, interval))
                events = [serialize(conn.execute("SELECT * FROM observations WHERE id=?", (identifier,)).fetchone())
                          for identifier in identifiers]
        if events and self.on_commit:
            self.on_commit(events)
        return raw_id, inserted

    def complete_due(self, now):
        completed = 0
        events = []
        with self.database.transaction() as conn:
            candidates = conn.execute(f"""
                SELECT * FROM observations o WHERE symbol=? AND data_source=?
                  AND observation_type='constructed_candle' AND candle_interval IN ({','.join('?' for _ in self.intervals)}) AND data_mode=?
                  AND candle_complete=0 AND NOT EXISTS (
                    SELECT 1 FROM observations n WHERE n.data_source=o.data_source AND n.symbol=o.symbol
                      AND n.observation_type=o.observation_type AND n.source_observation_id=o.source_observation_id
                      AND n.revision>o.revision)
            """, (self.symbol, SOURCE, *self.intervals, self.data_mode)).fetchall()
            for candle in candidates:
                start, end = candle_bounds(candle["candle_open_timestamp"], candle["candle_interval"])
                if now >= end:
                    rows = self._bucket_rows(conn, start, end)
                    identifier = self._append_candle(conn, rows, now, candle["candle_interval"])
                    events.append(serialize(conn.execute("SELECT * FROM observations WHERE id=?", (identifier,)).fetchone()))
                    completed += 1
        if events and self.on_commit:
            self.on_commit(events)
        return completed

    def latest_quote(self, symbol):
        with closing(self.database.connect()) as conn:
            row = conn.execute("""
                SELECT * FROM observations WHERE symbol=? AND data_source=?
                AND observation_type='raw_provider' AND json_extract(payload_json, '$.normalization_version')=1
                ORDER BY source_timestamp DESC,id DESC LIMIT 1
            """, (symbol, SOURCE)).fetchone()
            return serialize(row) if row else None

    def observations(self, symbol, limit, after_id=0):
        with closing(self.database.connect()) as conn:
            return [serialize(row) for row in conn.execute("""
                SELECT * FROM observations WHERE symbol=? AND data_source=?
                AND observation_type='raw_provider' AND id>? ORDER BY id LIMIT ?
            """, (symbol, SOURCE, after_id, limit))]

    def candles(self, symbol, interval, limit, revisions=False):
        latest = "" if revisions else """AND NOT EXISTS (
            SELECT 1 FROM observations n WHERE n.symbol=o.symbol AND n.data_source=o.data_source
            AND n.observation_type=o.observation_type AND n.source_observation_id=o.source_observation_id
            AND n.revision>o.revision)"""
        with closing(self.database.connect()) as conn:
            # Latest N candles, returned in chart chronological order. Revisions
            # use the same limit on rows and remain individually identifiable.
            rows = conn.execute(f"""
                SELECT * FROM observations o WHERE symbol=? AND data_source=?
                AND candle_interval=? AND observation_type='constructed_candle'
                {latest} ORDER BY candle_open_timestamp DESC,id DESC LIMIT ?
            """, (symbol, SOURCE, interval, limit)).fetchall()
            return [serialize(row) for row in reversed(rows)]


def serialize(row):
    value = dict(row)
    value["metadata"] = json.loads(value.pop("payload_json"))
    value["price"] = value["metadata"].get("price")
    if value["candle_complete"] is not None:
        value["candle_complete"] = bool(value["candle_complete"])
    return value
