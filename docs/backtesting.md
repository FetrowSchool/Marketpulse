# Historical SMA backtesting

## Scope and configuration
Backtesting is a historical **SIMULATED** account, separate from live paper trading,
recorded replay and provider ingestion. There is no brokerage connection. Choose a
supported symbol (AAPL/MSFT/NVDA/SPY), interval (1m/5m/15m), UTC start inclusive and end
exclusive, candle origin, starting cash and SMA periods. Defaults are $10,000 and20/50.
Fast must be less than slow, with periods1–500 and starting cash positive/up to$1,000,000,
in micro-USD increments. The date controls send UTC midnight; the API also accepts
explicit timezone-aware intraday timestamps. No warm-up candles are loaded before start.
At least slow+1 completed candles available by the range end are required.

The Backtesting panel sits below the main chart and strategy controls. Running does not
enable/disable the live strategy or change its account. The result is labeled BACKTEST,
with its captured symbol/interval/range even if the chart selection subsequently changes.
The equity curve, summary, fill history and completed round trips belong only to that run.

## Stored data and validation
This stage uses saved observations, with no additional Yahoo history downloader. Select
constructed_candle or provider_candle explicitly; they are never merged. Source is
currently yahoo_finance. Provider candles already stored through the persistence service
are supported, but the app still has no provider-OHLCV ingestion/downloader UI. Raw Yahoo
price observations are not treated as full candles. Constructed OHLC may be sparse and
its first observed price is only a proxy for the interval open, not an exchange opening
auction. Missing volume remains unavailable; this strategy uses prices only.

One SQLite read transaction captures a maximum observation ID and selected rows. The
first completed observation for each opening is retained in recorded receipt/ID order;
subsequent completed identities/revisions cannot replace it with corrected future data.
Incomplete rows are excluded and counted. Timestamps are timezone-aware UTC; candles
are sorted by opening, missing slots counted, and no gap candles synthesized. Gaps may
include closed-market hours; there is no exchange-calendar completeness assertion.
OHLC must be finite/positive and low<=min(open,close)<=max(open,close)<=high. Volume,
if supplied, must be finite/nonnegative. Bad OHLC fails clearly rather than fabricating
values. Mixed symbol/interval/source/origin inputs are rejected. Runs are bounded to
10,000 selected candles and100,000 input observation versions; narrow the range on error.

Data modes are preserved, including explicitly simulated fixtures. Mode changes reset
SMA warm-up and cancel pending crossings rather than combining unlike provenance. The
result's input rows expose original modes, observation IDs, revisions and availability.

## Event-driven availability and execution
Each selected candle has an open event and a completion-availability event. Availability
is max(interval end, recorded backend receipt). Only the open price is exposed at its
open event. Only when completion becomes available is the close appended to SMA history.
At equal timestamps, completion events precede open events, with observation ID as a
stable tie-breaker. Consequently a promptly available close can signal at the boundary
and execute at the next candle opening, never its own close.

A delayed confirmation skips any already-passed opening and waits for a later one.
Late completion of an older candle is recorded as ignored; it cannot rewrite decisions
or make its close the latest market mark. Later revisions are excluded entirely. This
is a conservative first-completion policy, not the replay engine's revision visualization.
Retrospectively downloaded candles received after the entire test range cannot supply
signals that pretend to have been known then: insufficient timely history is an error.
A future downloader would need an explicit, documented historical-availability policy.

SMA averages and equality/crossing rules use the same `sma_step` function as existing live
indicators (and therefore the live strategy). Previous fast<=slow and current fast>slow
is BUY; previous fast>=slow and current fast<slow is SELL. Current equality/no crossing
is HOLD. Custom periods change only window lengths. Completed input/previous pairs are
required; no provisional indicators or decisions use future closes.

A confirmed crossing queues a decision. The next eligible completed historical candle
opening executes it if its opening is at/after availability and later than the signal
candle opening. BUY uses the shared `allocation_quantity`: floor(floor(cash_microUSD/5)
/price_microUSD). Already long, insufficient one-share cash or exceeding the account's
1,000,000-share order limit produces a skip. SELL closes the entire isolated position;
none means skip. A newer crossing supersedes a pending one. If no eligible opening is
available before end, the decision stays unfilled. Positions are not forcibly liquidated.

Assumptions: long-only, no leverage/shorts/fractional shares, fees0, slippage0bps, immediate
whole-order fill at historical open. Quote precision uses existing micro-USD half-even
rounding. No order-book/spread/market-impact/liquidity/partial-fill model. Historical open
execution is a hypothetical assumption; a constructed first tick may not be executable.
Live simulation retains its different first-subsequent-observed-quote execution timing.

## Accounting and performance
Each run creates only in-memory cash, quantity and remaining cost basis, seeded from its
configuration. There is at most one long position; BUY adds cost, full SELL releases all
basis. Integer micro-USD avoids float ledger accumulation.

- Equity = cash + held shares × latest available mark.
- Realized P/L = full sale proceeds minus entry basis; unrealized P/L = marked position
  value minus remaining basis. No realized/unrealized double counting.
- Total return = (ending equity / starting equity −1) ×100.
- Completed trades count BUY→SELL round trips; fill count counts individual executions.
- Win rate = positive-P/L completed trades / completed trades ×100. Breakeven is not a
  win. No completed trades returns null/N/A, not division by zero.
- Maximum drawdown = max((running equity peak − current equity)/peak) ×100, with starting
  equity included as the first peak. Marks occur at open/completion events, without
  intrabar low/high drawdown assumptions. Older delayed closes cannot override newer marks.

The equity curve records timestamp, event type, candle ID, cash, quantity and equity.
Ending equity marks any open position; trade history contains only completed round trips.
Deterministic example (synthetic, fast2/slow3): closes10,10,10,12,8,8,9; next BUY open15,
SELL open9. floor(2000/15)=133 shares, cash8005, low marked equity9069, sale proceeds1197,
ending cash/equity9202, realized loss798, return−7.98%, maximum drawdown9.31%. A final BUY
signal has no next open and remains unfilled. This is arithmetic verification, not a
profitability claim. Default20/50 fixtures are also compared with the existing calculator.

## Persistence and API isolation
POST `/api/backtests` accepts the configuration; GET `/api/backtests?limit=20` lists
saved runs; GET `/api/backtests/{id}` restores a result. Validation errors are422, unknown
IDs404 and storage failures503. Each run has a separate ID, UTC creation timestamp,
canonical input SHA256 and immutable configuration/result JSON in backtest_runs.
Results include selected immutable candle IDs/revisions, decisions/SMAs, fills/trades and
equity curve. A snapshot maximum ID records the read boundary. Identical inputs/config
produce identical results except the new run ID; repeated runs are deliberately saved.
There is no HTTP client signal/order path to the live account, no WebSocket broadcast of
backtest fills, and no automatic strategy configuration change. The only writes are to
backtest_runs. The additive schema is transactional and repeatable.

## Limits and interpretation
Avoiding future closes in decisions does not remove all historical bias. First-completion
coverage is imperfect; sparse constructed bars, missing sessions, delayed receipts,
corporate-action adjustments or unavailable historical constituents can change results.
The four currently supported symbols introduce survivorship/selection bias. Choosing
periods after seeing outcomes risks overfitting and multiple-testing bias. There is no
out-of-sample/walk-forward analysis or comprehensive corporate-action calendar. Returns
are not annualized/risk-adjusted and exclude financing/taxes/real execution friction.
Historical results do not guarantee future performance.

Verification evidence in evidence/backtest-verification.json separates actual saved
provider-derived inputs from deterministic synthetic unit fixtures. Two stored-data runs
matched, with original market/account/strategy rows unchanged.192 backend tests and42
frontend tests passed, plus production build. Browser inventory failed because its native
pipe was unavailable; no successful visual or new live-provider probe is claimed.


## Saved signal chart — November 18, 2026

Show backtest signals on chart retrieves exact saved input IDs/revisions, recorded confirmed decisions and actual fills. Custom periods retain their labels. Later market revisions do not change the displayed run.
See [marker behavior and verification](chart-signals.md).
