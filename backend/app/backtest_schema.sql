CREATE TABLE IF NOT EXISTS backtest_schema_version (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO backtest_schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_timestamp TEXT NOT NULL,
    input_hash TEXT NOT NULL CHECK(length(input_hash)=64),
    configuration_json TEXT NOT NULL CHECK(json_valid(configuration_json)),
    result_json TEXT NOT NULL CHECK(json_valid(result_json))
);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_created ON backtest_runs(created_timestamp,id);
CREATE TRIGGER IF NOT EXISTS backtest_runs_no_update BEFORE UPDATE ON backtest_runs
BEGIN SELECT RAISE(ABORT,'Backtest results are immutable'); END;
CREATE TRIGGER IF NOT EXISTS backtest_runs_no_delete BEFORE DELETE ON backtest_runs
BEGIN SELECT RAISE(ABORT,'Backtest results are immutable'); END;
