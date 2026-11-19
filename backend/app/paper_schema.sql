-- Additive accounting schema; original market schema/version and rows are untouched.
CREATE TABLE IF NOT EXISTS accounting_schema_version (
    version INTEGER PRIMARY KEY CHECK(version=1)
);
INSERT OR IGNORE INTO accounting_schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS simulated_accounts (
    id INTEGER PRIMARY KEY CHECK(id=1),
    label TEXT NOT NULL CHECK(label='SIMULATED'),
    currency TEXT NOT NULL CHECK(currency='USD'),
    starting_cash_units INTEGER NOT NULL CHECK(starting_cash_units=10000000000),
    cash_units INTEGER NOT NULL CHECK(typeof(cash_units)='integer' AND cash_units>=0),
    realized_pl_units INTEGER NOT NULL,
    created_timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES simulated_accounts(id),
    client_order_id TEXT NOT NULL CHECK(length(client_order_id) BETWEEN 1 AND 100),
    request_hash TEXT NOT NULL,
    symbol TEXT NOT NULL CHECK(symbol IN ('AAPL','MSFT','NVDA','SPY')),
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity BETWEEN 1 AND 1000000),
    reference_price_units INTEGER NOT NULL CHECK(reference_price_units BETWEEN 1 AND 1000000000000),
    status TEXT NOT NULL CHECK(status IN ('pending','filled','rejected','canceled')),
    created_timestamp TEXT NOT NULL,
    updated_timestamp TEXT NOT NULL,
    strategy_signal_id TEXT,
    rejection_reason TEXT,
    UNIQUE(account_id,client_order_id)
);
CREATE TABLE IF NOT EXISTS paper_positions (
    account_id INTEGER NOT NULL REFERENCES simulated_accounts(id),
    symbol TEXT NOT NULL CHECK(symbol IN ('AAPL','MSFT','NVDA','SPY')),
    quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>=0),
    cost_basis_units INTEGER NOT NULL CHECK(typeof(cost_basis_units)='integer' AND cost_basis_units>=0),
    CHECK((quantity=0 AND cost_basis_units=0) OR quantity>0),
    PRIMARY KEY(account_id,symbol)
);
CREATE TABLE IF NOT EXISTS paper_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES paper_orders(id),
    account_id INTEGER NOT NULL REFERENCES simulated_accounts(id),
    symbol TEXT NOT NULL CHECK(symbol IN ('AAPL','MSFT','NVDA','SPY')),
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
    execution_price_units INTEGER NOT NULL CHECK(execution_price_units>0),
    execution_timestamp TEXT NOT NULL,
    fees_units INTEGER NOT NULL CHECK(fees_units=0),
    slippage_bps INTEGER NOT NULL CHECK(slippage_bps=0),
    price_source TEXT NOT NULL CHECK(price_source IN ('manual_reference','observed_quote')),
    cost_basis_released_units INTEGER NOT NULL CHECK(cost_basis_released_units>=0),
    realized_pl_units INTEGER NOT NULL,
    cash_after_units INTEGER NOT NULL CHECK(cash_after_units>=0),
    position_quantity_after INTEGER NOT NULL CHECK(position_quantity_after>=0)
);
CREATE INDEX IF NOT EXISTS idx_paper_orders_history ON paper_orders(account_id,id);
CREATE INDEX IF NOT EXISTS idx_paper_fills_history ON paper_fills(account_id,id);
CREATE TRIGGER IF NOT EXISTS paper_fills_no_update BEFORE UPDATE ON paper_fills
BEGIN SELECT RAISE(ABORT,'simulated fills are immutable'); END;
CREATE TRIGGER IF NOT EXISTS paper_fills_no_delete BEFORE DELETE ON paper_fills
BEGIN SELECT RAISE(ABORT,'simulated fills are immutable'); END;
CREATE TRIGGER IF NOT EXISTS paper_orders_no_delete BEFORE DELETE ON paper_orders
BEGIN SELECT RAISE(ABORT,'simulated orders are retained'); END;
CREATE TRIGGER IF NOT EXISTS paper_orders_terminal BEFORE UPDATE ON paper_orders
WHEN OLD.status!='pending' OR NEW.status NOT IN ('filled','rejected','canceled')
BEGIN SELECT RAISE(ABORT,'invalid simulated order transition'); END;
CREATE TRIGGER IF NOT EXISTS paper_orders_details_immutable BEFORE UPDATE ON paper_orders
WHEN NEW.account_id!=OLD.account_id OR NEW.client_order_id!=OLD.client_order_id
 OR NEW.request_hash!=OLD.request_hash OR NEW.symbol!=OLD.symbol OR NEW.side!=OLD.side
 OR NEW.quantity!=OLD.quantity OR NEW.reference_price_units!=OLD.reference_price_units
 OR NEW.created_timestamp!=OLD.created_timestamp OR NEW.strategy_signal_id IS NOT OLD.strategy_signal_id
BEGIN SELECT RAISE(ABORT,'simulated order details are immutable'); END;
