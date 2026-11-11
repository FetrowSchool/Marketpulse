"""Read-only frozen recordings and a deterministic, clock-injected playback state machine."""
from contextlib import closing
from datetime import datetime
import math

from app.services.database import utc_timestamp
from app.services.market_repository import serialize
from app.services.normalization import SOURCE

MAX_EVENTS = 10000


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ReplayRepository:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def scope():
        return """symbol=? AND data_source=? AND (observation_type='raw_provider'
                  OR (observation_type IN ('constructed_candle','provider_candle') AND candle_interval=?))"""

    def catalog(self, symbol, interval):
        with closing(self.database.read_connection()) as conn:
            row = conn.execute(f"""SELECT COUNT(*) AS event_count,MIN(received_timestamp) AS first_receipt,
                MAX(received_timestamp) AS last_receipt,MAX(id) AS snapshot_max_id
                FROM observations WHERE {self.scope()}""", (symbol, SOURCE, interval)).fetchone()
            return {"symbol": symbol, "interval": interval, "source": SOURCE,
                    **dict(row), "max_events": MAX_EVENTS, "range_clock": "backend_receipt_utc"}

    def load(self, symbol, interval, start=None, end=None, order="receipt", snapshot_max_id=None):
        start = utc_timestamp(start) if start is not None else None
        end = utc_timestamp(end) if end is not None else None
        if order not in ("receipt", "arrival") or (start and end and start >= end):
            raise ValueError("Invalid replay ordering or time range")
        with closing(self.database.read_connection()) as conn:
            conn.execute("BEGIN")
            maximum = conn.execute("SELECT COALESCE(MAX(id),0) FROM observations").fetchone()[0]
            boundary = min(maximum, snapshot_max_id) if snapshot_max_id is not None else maximum
            clauses = [self.scope(), "id<=?"]
            args = [symbol, SOURCE, interval, boundary]
            if start:
                clauses.append("received_timestamp>=?"); args.append(start)
            if end:
                clauses.append("received_timestamp<?"); args.append(end)
            ordering = "received_timestamp,id" if order == "receipt" else "id"
            rows = conn.execute(f"SELECT * FROM observations WHERE {' AND '.join(clauses)} ORDER BY {ordering} LIMIT ?",
                                (*args, MAX_EVENTS + 1)).fetchall()
            if len(rows) > MAX_EVENTS:
                raise ValueError("Recording exceeds 10000 events; narrow the time range")
            records = [serialize(row) for row in rows]
            baseline = []
            if start and records:
                baseline_boundary = min(boundary, min(row["id"] for row in records) - 1) if order == "arrival" else boundary
                # As-of context only: never initialize replay with a final future revision.
                previous = conn.execute(f"""
                    WITH past AS (
                        SELECT *,ROW_NUMBER() OVER(PARTITION BY data_source,symbol,observation_type,source_observation_id
                            ORDER BY revision DESC,id DESC) AS rank
                        FROM observations WHERE {self.scope()} AND id<=? AND received_timestamp<?)
                    SELECT * FROM past WHERE rank=1 AND observation_type!='raw_provider'
                    ORDER BY candle_open_timestamp DESC,id DESC LIMIT 1000
                """, (symbol, SOURCE, interval, baseline_boundary, start)).fetchall()
                baseline = [serialize({key: row[key] for key in row.keys() if key != "rank"}) for row in reversed(previous)]
                quote = conn.execute(f"""SELECT * FROM observations WHERE {self.scope()} AND id<=?
                    AND received_timestamp<? AND observation_type='raw_provider'
                    ORDER BY source_timestamp DESC,id DESC LIMIT 1""", (symbol, SOURCE, interval, baseline_boundary, start)).fetchone()
                if quote:
                    baseline.insert(0, serialize(quote))
        return {"symbol": symbol, "interval": interval, "start": start, "end": end, "order": order,
                "snapshot_max_id": boundary, "records": records, "baseline": baseline}


class ReplaySession:
    def __init__(self, recording, *, speed=1, generation=1):
        self.recording = recording
        self.records = recording["records"]
        self.generation = generation
        self.speed = self.validate_speed(speed)
        self.position = 0
        self.elapsed = 0.0
        self.last_tick = None
        self.state = "ready"
        self.schedule = []
        duration = 0.0
        previous = None
        for row in self.records:
            current = timestamp(row["received_timestamp"])
            if previous is not None:
                duration += max(0, (current - previous).total_seconds())
            self.schedule.append(duration)
            previous = current
        self.duration = duration

    @staticmethod
    def validate_speed(value):
        if type(value) not in (int, float) or not math.isfinite(value) or not .25 <= value <= 100:
            raise ValueError("Playback speed must be a finite number from 0.25 to 100")
        return float(value)

    def tick(self, now):
        if self.state != "playing":
            return []
        self.elapsed += max(0, now - self.last_tick) * self.speed
        self.last_tick = now
        emitted = []
        while self.position < len(self.records) and self.schedule[self.position] <= self.elapsed and len(emitted) < 100:
            emitted.append(self.records[self.position]); self.position += 1
        if self.position == len(self.records):
            self.state = "completed"; self.last_tick = None
        return emitted

    def control(self, command, now, speed=None):
        if command not in ("play", "pause", "resume", "restart", "stop", "speed"):
            raise ValueError("Unknown replay control")
        value = self.validate_speed(speed) if command == "speed" else None
        if command in ("restart", "stop"):
            self.position = 0; self.elapsed = 0; self.generation += 1
            self.state = "playing" if command == "restart" else "stopped"
            self.last_tick = now if command == "restart" else None
            return []
        emitted = self.tick(now)
        if command == "pause" and self.state == "playing":
            self.state = "paused"; self.last_tick = None
        elif command in ("play", "resume") and self.state in ("ready", "paused", "stopped"):
            self.state = "playing"; self.last_tick = now
        elif command == "speed":
            self.speed = value
        return emitted

    def status(self):
        row = self.records[self.position - 1] if self.position else None
        return {"state": self.state, "generation": self.generation, "speed": self.speed,
                "position": self.position, "total": len(self.records),
                "progress": self.position / len(self.records) if self.records else 0,
                "playhead_receipt_timestamp": row["received_timestamp"] if row else None,
                "playhead_source_timestamp": row["source_timestamp"] if row else None,
                "last_record_id": row["id"] if row else None,
                "duration_seconds": self.duration, "elapsed_seconds": min(self.elapsed, self.duration),
                **{key: self.recording[key] for key in ("symbol", "interval", "start", "end", "order", "snapshot_max_id")}}
