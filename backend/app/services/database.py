"""Append-only observations. All writes use a serialized SQLite transaction."""
import hashlib
import json
import math
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_timestamp(value: str | datetime) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def read_connection(self):
        connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def verify_integrity(self):
        with closing(self.read_connection()) as conn:
            checks = [row[0] for row in conn.execute("PRAGMA integrity_check")]
            foreign_keys = list(conn.execute("PRAGMA foreign_key_check"))
            revision_gaps = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM observations GROUP BY data_source,symbol,observation_type,source_observation_id
                    HAVING MIN(revision)!=1 OR MAX(revision)!=COUNT(*))
            """).fetchone()[0]
            invalid = []
            for row in conn.execute("SELECT id,source_timestamp,received_timestamp,content_hash FROM observations"):
                try:
                    valid = all(utc_timestamp(row[key]) == row[key] for key in ("source_timestamp", "received_timestamp"))
                except (ValueError, TypeError):
                    valid = False
                if not valid or len(row["content_hash"]) != 64:
                    invalid.append(row["id"])
            count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            return {"ok": checks == ["ok"] and not foreign_keys and not revision_gaps and not invalid,
                    "sqlite_integrity": checks, "foreign_key_violations": len(foreign_keys),
                    "revision_gap_groups": revision_gaps, "invalid_metadata_ids": invalid[:20],
                    "invalid_metadata_count": len(invalid), "observation_count": count}

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema = Path(__file__).resolve().parents[1].joinpath("schema.sql").read_text()
        with closing(self.connect()) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            try:
                conn.executescript("BEGIN IMMEDIATE;\n" + schema + "\nCOMMIT;")
            except Exception:
                conn.rollback()
                raise

    def is_connected(self):
        try:
            with closing(self.connect()) as conn:
                version = conn.execute("SELECT version FROM schema_version").fetchone()
                conn.execute("SELECT id FROM observations LIMIT 1").fetchone()
                return version is not None and version["version"] == 1
        except (sqlite3.Error, OSError, TypeError):
            return False

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    def insert_observation(self, *, symbol, data_source, source_observation_id,
                           observation_type, data_mode, source_timestamp, payload,
                           candle_interval=None, candle_open_timestamp=None,
                           open=None, high=None, low=None, close=None, volume=None,
                           candle_complete=None, received_timestamp=None, connection=None):
        """Return existing ID for a duplicate, otherwise append an identity revision.

        Receipt time defaults to now, or is supplied by the ingestion boundary;
        it is always excluded from duplicate fingerprints.
        A provider adapter must assign a stable observation ID before calling.
        """
        for number in (open, high, low, close, volume):
            if number is not None and (isinstance(number, bool) or not math.isfinite(number)):
                raise ValueError("Market values must be finite numbers")
        values = dict(symbol=symbol.strip().upper(), data_source=data_source,
            source_observation_id=source_observation_id, observation_type=observation_type,
            data_mode=data_mode, source_timestamp=utc_timestamp(source_timestamp),
            candle_interval=candle_interval,
            candle_open_timestamp=utc_timestamp(candle_open_timestamp) if candle_open_timestamp else None,
            open=open, high=high, low=low, close=close, volume=volume,
            candle_complete=None if candle_complete is None else int(candle_complete),
            payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        identity = (data_source, values["symbol"], observation_type, source_observation_id)
        where = "data_source=? AND symbol=? AND observation_type=? AND source_observation_id=?"
        receipt = utc_timestamp(received_timestamp or datetime.now(timezone.utc))

        def append(conn):
            duplicate = conn.execute(f"SELECT id FROM observations WHERE {where} AND content_hash=?",
                                     (*identity, fingerprint)).fetchone()
            if duplicate:
                return duplicate["id"]
            revision = conn.execute(f"SELECT COALESCE(MAX(revision), 0)+1 FROM observations WHERE {where}",
                                    identity).fetchone()[0]
            values.update(content_hash=fingerprint, revision=revision, received_timestamp=receipt)
            columns = ",".join(values)
            cursor = conn.execute(f"INSERT INTO observations ({columns}) VALUES ({','.join('?' for _ in values)})",
                                  tuple(values.values()))
            return cursor.lastrowid

        if connection is not None:
            return append(connection)
        with self.transaction() as conn:
            return append(conn)

    def retrieve(self, symbol=None, *, order="receipt", limit=1000, after_id=0):
        """Stable ingest replay via ID cursor; source order is for historical analysis.

        ID is authoritative ingest order even if the wall clock moves backwards.
        Pagination using after_id is supported only in receipt order.
        """
        if order not in ("receipt", "source") or not 1 <= limit <= 10000:
            raise ValueError("Invalid retrieval options")
        if order == "source" and after_id:
            raise ValueError("Source ordering does not support an ingest cursor")
        clauses, args = ["id > ?"], [after_id]
        if symbol:
            clauses.append("symbol = ?")
            args.append(symbol.strip().upper())
        ordering = "id" if order == "receipt" else "source_timestamp, id"
        with closing(self.connect()) as conn:
            return [dict(row) for row in conn.execute(
                f"SELECT * FROM observations WHERE {' AND '.join(clauses)} ORDER BY {ordering} LIMIT ?",
                (*args, limit))]
