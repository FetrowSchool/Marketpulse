# Manual simulated account and accounting

## Scope and execution assumptions
A singleton USD account is visibly **SIMULATED** and seeded once with $10,000. There is
no brokerage client or real order routing. Historical backtests use a separate isolated account. An explicitly enabled separate SMA
strategy can submit simulated orders; analytical chart markers never submit orders themselves.

Manual market-style simulated orders fill the whole requested integer quantity at the
user-supplied reference price: no order book, spread, liquidity, partial fills or timing
guarantee. Commission/fees=0 and slippage=0bps are stored on every fill. Long-only holdings,
no leverage, no short selling and no fractional shares. Price must be finite, positive,
no more than $1,000,000 and representable in six decimals; order quantity1–1,000,000.
Users can enter prices independently of Yahoo. This is a documented toy fill model,
not evidence of a real exchange execution. The dashboard's copy-price button rounds to
six decimals and keeps the order explicitly manual, even if its source quote is stale.

By default submission performs pending→filled immediately in one transaction. Optional
execute_immediately=false retains pending status and its fixed creation reference price.
Only an explicit manual execute endpoint/action fills it later. Pending orders reserve
no cash/shares: validation is repeated at execution, so another trade can cause rejection.
Pending cancellation moves to canceled; filled/rejected/canceled are terminal. Filled
execution and canceled cancellation retries return the existing result. Other invalid
terminal transitions return409. There is no automatic retry that creates a new order.

Unsupported symbols, invalid sides, fractional/nonpositive/excess quantities, bad prices
and malformed keys return422 and create no order. Insufficient funds/shares creates a
persistent rejected order with a reason and no fill/account mutation. No short position
or negative cash is permitted. strategy_signal_id is optional reference metadata only;
manual order execution never treats it as a confirmed signal or automatic instruction.

## Exact accounting
All persisted monetary values are signed integer **micro-USD** (1 unit=$0.000001), not
SQLite REAL. Public money fields are decimal strings with six fractional digits. Quantity
is an integer. UI dollar formatting is presentation-only and never drives ledger updates.

- Cash =10,000 + sell proceeds − buy costs − fees.
- Position market value = quantity × current saved mark.
- Equity = cash + total position market value.
- Unrealized P/L = current value − remaining cost basis.
- Realized P/L = net sale proceeds − cost basis released on the shares sold.

Buys add quantity and full purchase cost to total remaining basis. Average entry is basis
÷ quantity, displayed at six decimals; the rounded average is never multiplied back into
cost accounting. A partial sale allocates `basis × sold / held`, rounded once to the
nearest micro-USD with exact integer half-even tie handling. A full close releases all
remaining basis, eliminating residual pennies/units. Fees are currently exactly zero.
Realized P/L accumulates only sale outcomes; it is not added to cash a second time.
For fully marked holdings, equity=starting cash+realized P/L+unrealized P/L.

Independent reference example used in tests:
1. Buy10 at100 and10 at120:20 shares, basis2200, average110, cash7800.
2. Saved mark130: market value2600, unrealized400, equity10400.
3. Sell5 at140: proceeds700, released basis550, realized150, cash8500.
4. Remaining15 at mark130: basis1650, value1950, unrealized300, equity10450.
   Identity:10000+150+300=10450.
5. Sell remaining15 at90: proceeds1350, realized loss300 for that fill, cumulative
   realized−150, no open position, cash/equity9850 and unrealized0.

Micro-unit reference: buy1 at0.100001 plus2 at0.100000 => basis0.300001. Selling three
shares individually at0.200000 releases total basis0.300001 and realizes0.299999,
with no lost residual. Exact half-even tests include0.5→0 and1.5→2 at the unit level.

## Valuation and provenance
Valuation reads the latest source-time raw Yahoo observation after resolving original
identity revisions. Provider prices are rounded half-even to micro-USD for marking only.
Metadata includes original source/receipt times, provider row ID, mode and source age.
Quotes can be delayed/stale; account equity is a last-known estimate, not current live
execution equity. Missing, invalid or below-precision marks leave the position's value
and P/L null; aggregate equity/unrealized are null if any held symbol lacks a valid mark.
Cash, cost basis, realized P/L and other marked positions remain available. No quote is
fabricated from entry price. Valuation does not create observations, fills or profits.

Replay does not rewind the account or feed recorded prices into execution. The manual
form/Fill controls are disabled in replay; current account readouts remain independent.
API clients must explicitly submit manual prices. There is no replay account simulation.

## Schema and transaction integrity
`app/paper_schema.sql` is an additive component migration executed alongside the market
DDL in Database.initialize. accounting_schema_version1 tracks this component without
changing the original schema_version1 CHECK contract. Tables:
- simulated_accounts: starting cash, available cash, cumulative realized P/L and UTC creation.
- paper_orders: account, unique client key/hash, symbol/side/quantity, reference price,
  pending/filled/rejected/canceled, UTC creation/update, optional signal reference/reason.
- paper_positions: one account/symbol slot with integer quantity and remaining basis.
- paper_fills: unique order FK, symbol/side/quantity/price/time, fees/slippage/source,
  released basis, realized fill P/L and post-fill cash/quantity for audit.

Initialization uses CREATE IF NOT EXISTS and INSERT OR IGNORE for the account seed. It
never replaces balances or resets trades. Original observations retain append-only
triggers and are not changed. Fill update/delete and order delete are prohibited;
terminal statuses and order input details are immutable. Foreign keys and indexes retain
relationships. Zero-quantity slots remain with zero basis but are hidden from open holdings.

BEGIN IMMEDIATE serializes validation, fill insertion, account/position mutation and
status update. An injected fill failure rolls everything back, including the pending
order on immediate submission. Repeated identical client_order_id/payload returns its
original order; different payload under the same key conflicts409. UNIQUE(order_id)
on fills is an additional exactly-once guard. Concurrent duplicates fill once; concurrent
different buys cannot spend the same cash. Rejected/canceled attempts do not change cash.

## APIs and UI
| Endpoint | Behavior |
| --- | --- |
| GET /api/paper/account | SIMULATED summary, positions, valuation completeness and assumptions |
| GET /api/paper/positions | Open positions with mark metadata |
| GET /api/paper/orders | Latest orders, limit1–1000 default100 |
| GET /api/paper/fills | Latest immutable fills, limit1–1000 default100 |
| GET /api/paper/trades | Same fill history; not a separate ledger that double-counts outcomes |
| POST /api/paper/orders | client_order_id, symbol, side, integer quantity, execution_price; optional execute_immediately/signal reference |
| POST /api/paper/orders/{id}/execute | Manually fill pending, or return an existing filled result |
| POST /api/paper/orders/{id}/cancel | Manually cancel pending, or return an existing cancellation |

Not found404, invalid request422, incompatible idempotency/status409, storage failure503
with safe text. If a submission response is lost, retry the identical client key/body;
never generate another key just to recover a network timeout. The Vue form retains the
key across an unsuccessful response, disables duplicate clicks, and shows errors/results.
GET refresh every15s and after actions is independent from chart/indicator updates.
The history UI shows the latest100 records. Single local account only; there is no auth,
multi-user ownership model, account reset, deposits/withdrawals or production deployment.
There is no reporting export. Performance metrics belong to the separate isolated
backtest service (backtesting.md), not this live paper account.

## Opt-in strategy integration
Automatic simulated orders reuse this accounting service with observed_quote provenance
and an execution-observation foreign key. Only trusted internal calls can acquire scope
ownership; a manual strategy_signal_id field remains metadata. Manual SELL may consume
only manual-owned shares. Account basis stays pooled average cost across owners; scope
quantities do not establish separate strategy P/L. See strategy.md. Default automatic
trading is OFF; manual reference-price rules remain unchanged.
