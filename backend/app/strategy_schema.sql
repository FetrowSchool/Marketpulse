CREATE TABLE IF NOT EXISTS strategy_schema_version(version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO strategy_schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS strategy_config (
    id INTEGER PRIMARY KEY CHECK(id=1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    symbol TEXT NOT NULL CHECK(symbol IN ('AAPL','MSFT','NVDA','SPY')),
    interval TEXT NOT NULL CHECK(interval IN ('1m','5m','15m')),
    updated_timestamp TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'sma20-50-long-v1' CHECK(strategy='sma20-50-long-v1'),
    fast_period INTEGER NOT NULL DEFAULT 20 CHECK(fast_period=20),
    slow_period INTEGER NOT NULL DEFAULT 50 CHECK(slow_period=50),
    allocation_percent INTEGER NOT NULL DEFAULT 20 CHECK(allocation_percent=20)
);
CREATE TABLE IF NOT EXISTS strategy_scopes (
    scope TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    enabled_at TEXT NOT NULL,
    activation_after_id INTEGER NOT NULL,
    last_completed_open TEXT
);
CREATE TABLE IF NOT EXISTS strategy_signals (
    signal_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL REFERENCES strategy_scopes(scope),
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    candle_open_timestamp TEXT NOT NULL,
    candle_end_timestamp TEXT NOT NULL,
    confirming_candle_id INTEGER NOT NULL REFERENCES observations(id),
    direction TEXT NOT NULL CHECK(direction IN ('BUY','SELL')),
    confirmed_timestamp TEXT NOT NULL,
    available_after_id INTEGER NOT NULL,
    sma20 TEXT NOT NULL,
    sma50 TEXT NOT NULL,
    inputs_json TEXT NOT NULL CHECK(json_valid(inputs_json)),
    UNIQUE(scope,candle_open_timestamp)
);
CREATE TABLE IF NOT EXISTS strategy_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_key TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL REFERENCES strategy_scopes(scope),
    signal_id TEXT REFERENCES strategy_signals(signal_id),
    candle_id INTEGER REFERENCES observations(id),
    status TEXT NOT NULL CHECK(status IN ('waiting','executed','skipped','hold','revision_ignored','canceled')),
    reason TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
    execution_price_units INTEGER,
    execution_observation_id INTEGER REFERENCES observations(id),
    order_id INTEGER REFERENCES paper_orders(id),
    fill_id INTEGER REFERENCES paper_fills(id),
    account_state_json TEXT CHECK(account_state_json IS NULL OR json_valid(account_state_json)),
    created_timestamp TEXT NOT NULL,
    updated_timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_positions (
    scope TEXT NOT NULL REFERENCES strategy_scopes(scope),
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>=0),
    PRIMARY KEY(scope,symbol)
);
CREATE TABLE IF NOT EXISTS strategy_order_links (
    order_id INTEGER PRIMARY KEY REFERENCES paper_orders(id),
    scope TEXT NOT NULL REFERENCES strategy_scopes(scope),
    observation_id INTEGER NOT NULL REFERENCES observations(id)
);
CREATE INDEX IF NOT EXISTS idx_strategy_decisions_scope ON strategy_decisions(scope,id);
CREATE INDEX IF NOT EXISTS idx_strategy_waiting ON strategy_decisions(scope,status);
CREATE TRIGGER IF NOT EXISTS strategy_signals_no_update BEFORE UPDATE ON strategy_signals
BEGIN SELECT RAISE(ABORT,'confirmed strategy signals are immutable'); END;
CREATE TRIGGER IF NOT EXISTS strategy_signals_no_delete BEFORE DELETE ON strategy_signals
BEGIN SELECT RAISE(ABORT,'confirmed strategy signals are retained'); END;
