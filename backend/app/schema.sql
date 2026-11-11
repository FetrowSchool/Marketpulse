CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY CHECK (version = 1)
);
INSERT OR IGNORE INTO schema_version(version) VALUES (1);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL CHECK(length(trim(symbol)) > 0),
    data_source TEXT NOT NULL CHECK(length(trim(data_source)) > 0),
    source_observation_id TEXT NOT NULL CHECK(length(trim(source_observation_id)) > 0),
    observation_type TEXT NOT NULL CHECK(observation_type IN
        ('raw_provider', 'constructed_candle', 'provider_candle')),
    data_mode TEXT NOT NULL CHECK(data_mode IN ('live', 'delayed', 'recorded', 'simulated')),
    candle_interval TEXT,
    candle_open_timestamp TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL CHECK(volume IS NULL OR volume >= 0),
    source_timestamp TEXT NOT NULL,
    received_timestamp TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    candle_complete INTEGER CHECK(candle_complete IN (0, 1)),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    content_hash TEXT NOT NULL,
    UNIQUE(data_source, symbol, observation_type, source_observation_id, revision),
    UNIQUE(data_source, symbol, observation_type, source_observation_id, content_hash),
    CHECK((observation_type = 'raw_provider' AND candle_interval IS NULL
        AND candle_open_timestamp IS NULL AND candle_complete IS NULL)
      OR (observation_type IN ('constructed_candle', 'provider_candle')
        AND candle_interval IS NOT NULL AND length(trim(candle_interval)) > 0 AND candle_open_timestamp IS NOT NULL
        AND candle_complete IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_observations_candle ON observations
    (symbol, data_source, observation_type, candle_interval, candle_open_timestamp, revision);
CREATE INDEX IF NOT EXISTS idx_observations_history ON observations(symbol, source_timestamp, id);
CREATE INDEX IF NOT EXISTS idx_observations_replay ON observations(received_timestamp, id);
CREATE TRIGGER IF NOT EXISTS observations_no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;

CREATE INDEX IF NOT EXISTS idx_observations_source_time ON observations
    (data_source, symbol, observation_type, data_mode, source_timestamp, id);

CREATE INDEX IF NOT EXISTS idx_observations_receipt_selection ON observations
    (symbol, data_source, received_timestamp, id);
