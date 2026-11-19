# Automatic SIMULATED crossover strategy

## Rules and controls
The live engine has one active SMA20/50 long-only strategy supporting AAPL/MSFT/NVDA/SPY and1m/5m/15m.
The initial configuration is OFF; explicit enable persists across backend restarts.
Changing active scope requires disabling first. Disabled positions remain owned and are
not liquidated. Re-enabling starts after the current saved watermark: no historical
catch-up orders. A later SELL can close retained shares for that same scope.

Only completed, elapsed, provider-derived constructed candles are eligible. Both previous
and current SMA pairs are required: previous fast<=slow/current fast>slow is BUY;
previous fast>=slow/current fast<slow is SELL; equality now or no crossing is HOLD.
No provisional or browser-supplied signal can execute. Inputs retain the last51 candle
IDs/revisions and SMA values. Old/revised completion events are audited and ignored for
new execution; analytical chart markers can still change with corrected history.

## Timing and sizing
After confirmation, wait for the first eligible persisted Yahoo price observation.
Its database ID must exceed the confirmation availability watermark, its receipt must
be strictly after confirmation, and its source time must be at or after both confirmation
and candle end. Source age and receipt age must independently be nonnegative and within
the configured freshness threshold. An old/future/invalid quote cannot produce a fill.
Prices are rounded to micro-USD using account rules; actual observation ID and source/
receipt timestamps remain traceable. Fresh Yahoo data remains real-time unverified,
not verified exchange real-time. This is a zero-fee/zero-slippage toy execution model,
not a claim of exchange liquidity or availability at an actual broker.

BUY quantity=floor(floor(cash_microUSD/5)/price_microUSD). Already-owned scope shares,
insufficient cash for one share, or exceeding the account1,000,000-share order limit
produce a recorded skip. SELL sells the entire scope-managed quantity; none means skip.
Manual sells cannot consume strategy-owned shares. Position quantities are attributed
by scope, but account cost basis remains the existing pooled average cost per symbol;
there is no independent per-strategy P/L ledger. No leverage/shorts/fractional shares.

Historical timing policy selects the next eligible opening at/after confirmation and
candle end, never the confirming close. A tested policy helper exists, and the separate historical
runner is now documented in backtesting.md. Missing eligible prices remain missing.
Offline quotes cannot be reconstructed or claimed as the first actual market quote.

## Identity, transactions and isolation
Signal identity hashes strategy, symbol, interval, confirmed candle opening and direction.
A unique scope/candle slot additionally latches the first direction, so a revised opposite
crossing cannot silently execute again. Decisions have unique identities; orders use
strategy:signal_id client keys and fills are unique per order. Restarts and reconnects
cannot repeat execution. A newer crossing cancels an older waiting decision; disabling
also cancels pending decisions. HOLD and revision ignores remain auditable.

Market observations commit first. A post-commit hook evaluates signals and later quotes;
orders, fills, account changes, managed ownership and decision outcome share a serialized
SQLite transaction. Failures roll back that action and visibly suspend the engine while
market ingestion/broadcast continues. The engine does not trust callback price fields:
it reloads the immutable observation. Recorded/simulated observations and replay paths
cannot execute; replay never writes market data or calls the strategy. An enabled live
engine can continue independently while a browser views replay. DefaultOFF verification
never placed orders in the real application database.

Trace: raw observation → completed candle →51 input candle IDs/SMA values → immutable
signal → decision → idempotent order → fill/actual quote FK → account snapshot.
Status includes last signal, latest decision/action, reason, quantity, price and account.
Purple SIM circles represent fills; BUY/SELL arrows are analytical signals, not fills.
Scope filtering prevents other symbols/intervals from leaking markers into the chart.

## Verification
Deterministic fixtures cover BUY/SELL/HOLD, incomplete candles, same/opposite revisions,
restart/reconnect deduplication, replay isolation, timing/freshness, rollback, no shares,
insufficient funds, manual ownership and precise20% sizing. Example: cash10,000 and next
eligible quote125 buys16 shares, spending2,000; confirming candle close120 is not used.
A later eligible SELL90 returns1,440 and cash9,440. This checks accounting, not profitability.
All173 backend and39 frontend tests plus production build passed. Browser transport was
unavailable; no new successful visual or live automatic-fill verification is claimed.

## Historical runner extension
An isolated event-driven historical runner is now implemented; the earlier timing-policy
helper remains separate from live execution. It uses the shared SMA/crossover/sizing
functions with configurable periods, first-completion historical events and next-eligible
open fills. It cannot change the live account. See [backtesting.md](backtesting.md).
