# Assignment 4.2 verification and CI

## Reproduction and actual results
From the repository root, after installing dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
cd backend
../.venv/bin/python -m pytest
../.venv/bin/python scripts/verify_references.py --output /tmp/sma-reference-verification.json
cd ../frontend
npm ci
npm test
npm run build
```

Actual 2026-11-12 verification used the matching dependency-equipped source copy at
/private/tmp/marketpulse-final-review, avoiding previously observed workspace dependency
read stalls. No dependencies were installed/updated in this stage. Python3.13.15,
Node24.20.0, pandas3.1.1, Vite7.3.7 were used. Backend: **204 passed**, one existing
Starlette/httpx deprecation warning,6.30s. Frontend: **42 passed in11 files**,1.27s.
Production build: successful,26 modules,618ms. `python -m pip check`: no broken
requirements. These are local results, not a GitHub-hosted CI execution.

All trading test executions used temporary databases/synthetic fixtures. The existing
running app, saved user account, enabled-state configuration and provider connection
were not modified in this stage. No new live-provider verification is claimed.

## Independent SMA reference
The checked-in [reference probe](../backend/scripts/verify_references.py) compares:
1. Application batch `evaluate` over completed candle history.
2. Incremental calls to the same production `sma_step` used by the event-driven backtest,
   appending one completed close to its bounded deque at a time.
3. Independent exact `fractions.Fraction` batch sums and rolling add/subtract sums.
4. Independent pandas `Series.rolling(N,min_periods=N).mean()`.

Fraction values are constructed from decimal strings, avoiding binary-float conversion
as the exact oracle. The trusted references are Python's standard rational arithmetic
and pandas' rolling implementation, not a duplicate of the application's Decimal code.
See [Python Fraction documentation](https://docs.python.org/3/library/fractions.html),
[pandas rolling mean](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.api.typing.Rolling.mean.html).
Pandas is already a locked yfinance dependency; no new test dependency was added.

Absolute tolerance **1e-9 USD**, relative tolerance **0**, for the supported positive
price range up to$1,000,000. This comparison tolerance is below the ledger's1e-6 USD
precision and is never used to soften crossover equality. Internal crossover decisions
retain Decimal strict/inclusive comparisons. Exact rational running sums equal batch
sums exactly; conversion to chart floats/pandas is compared with the stated tolerance.

Six explicitly synthetic60-close datasets (constant, rising, falling, decimal rising,
crossover and near$1,000,000 precision boundary) cover360 points and both periods.
Selected expected and actual values are preserved in
[evidence/sma-reference-verification.json](evidence/sma-reference-verification.json).
Maximum measured absolute difference was **2.3283064365386963e-10 USD**, within1e-9.
The first five datasets had zero measured error; the bound dataset exposed float
representation/rolling differences rather than a signal discrepancy.

| Dataset / completed count | Expected SMA20 | Expected SMA50 | Confirmation |
| --- | ---: | ---: | --- |
| Rising1…60 /19 | unavailable | unavailable | insufficient |
| Rising1…60 /20 |10.5 | unavailable | insufficient |
| Rising1…60 /49 |39.5 | unavailable | insufficient |
| Rising1…60 /50 |40.5 |25.5 | no previous SMA50 |
| Rising1…60 /51 |41.5 |26.5 | HOLD |
| Falling60…1 /50 |20.5 |35.5 | no previous SMA50 |
| Constant100.125 /51 |100.125 |100.125 | HOLD equality |
| Fifty100 closes, then120 /51 |101 |100.4 | BUY |
| Same history, then80 /52 |100 |100 | HOLD equality |
| Same history, then another80 /53 |99 |99.6 | SELL |
| Rising1…61, missing11 /50 observed |41.5 |26.3 | no synthetic missing close |

For example, rising1…50 has sum1275 /50=25.5; last20 are31…50,
sum810 /20=40.5. Fast rising window advances to32…51, sum830 /20=41.5.

Additional tests cover invalid closes resetting warm-up, incomplete exclusion without
advancing the previous pair, missing buckets, and historical revision replacement with
stable signal identity. A late corrected close80 replaces120 at one identity with
SMA20=99/SMA50=99.6 and SELL; old rows remain immutable. Live execution intentionally
latches already-processed signal slots rather than executing revised arrows again.

## Full strategy path and isolation
`test_strategy.py` verifies raw provider-shaped fixture processing and the actual
post-commit callback, plus a direct database trace:
completed confirming candle ID → SMA101/100.4 → stable BUY signal → waiting decision →
subsequent quote125 ID → simulated order/fill16 shares → cash8000/position16.
An incomplete120 candle alone creates no order. Fills retain observed_quote provenance
and the exact execution observation link; confirmation close120 is never used to fill.
Signal/order/fill IDs and database relationships are asserted.

Duplicate quote/candle delivery, older out-of-order candles, opposite historical
revisions and restart/reconnect do not repeat fills. Recorded/simulated replay inputs
cannot drive automatic orders. The existing replay WebSocket and read-only indicator
API are exercised against an enabled engine, with an empty main order/fill ledger.
These are deterministic mocked/provider-shaped fixtures, not fresh Yahoo observations.

## Independent accounting references
All values below are hand-calculated USD expectations, tested using temporary accounts.
Zero commissions and zero slippage are stored and asserted; nonzero fees are not
implemented/claimed. Rejections create retained rejected orders but no fills or changes
to cash/positions/equity.

| Action / mark | Cash | Shares | Average entry | Remaining basis | Realized P/L | Unrealized P/L | Equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Buy10@100,10@120; mark130 |7800 |20 |110 |2200 |0 |400 |10400 |
| Sell5@140; mark130 |8500 |15 |110 |1650 |150 |300 |10450 |
| Sell remaining15@90 |9850 |0 |— |0 |−150 |0 |9850 |
| Buy3@99.80,7@102.10; mark103 |8985.90 |10 |101.41 |1014.10 |0 |15.90 |10015.90 |
| Sell4@104.20; mark103 |9402.70 |6 |101.41 |608.46 |11.16 |9.54 |10020.70 |
| Sell remaining6@98.50 |9993.70 |0 |— |0 |−6.30 |0 |9993.70 |

Second example: cost=299.40+714.70=1014.10; partial basis=4×101.41=405.64;
proceeds416.80−405.64=11.16 realized; remaining mark618−608.46=9.54 unrealized.
Equity9402.70+618=10020.70=10000+11.16+9.54. Rejecting a1000-share BUY@100 or7-share
SELL while holding6 leaves that state unchanged. Existing tests also verify half-even
micro-USD allocation, full residual basis release, idempotency and concurrent spending.

## Hand-checked backtest curve and timing
Synthetic fast2/slow3 closes10,10,10,12,8,8,9 generate BUY after candle4 and SELL after
candle6. Next eligible opens15 (candle5) and9 (candle7) produce133 shares:
floor(2000/15)=133, buy cost1995, cash8005; sell proceeds1197, cash/equity9202.
Completed round trips=1, fills=2, realized P/L−798, total return−7.98%, win rate0%.
Worst marked equity8005+133×8=9069; drawdown(10000−9069)/10000=**9.31%**.

The complete14-event curve is asserted: first9 events equity10000, next3 equity9069,
last2 equity9202. Event timestamps are chronological; close availability precedes next
open at equal time. Full entry/exit history, quantities, IDs and timestamps are checked.
A final BUY without a next eligible open remains unfilled. Open positions have unrealized
P/L, not forced exits. No-trade results have null win rate and zero drawdown.

Tests perturb future closes and verify unchanged earlier decisions/fills, delay receipt
and verify already-passed opens cannot execute, exclude late corrections, compare repeated
result payloads except run ID, restore saved runs after repeated initialization and
compare pre/post main account/market/strategy rows. Historical bias/liquidity limitations
are in [backtesting.md](backtesting.md); these examples are arithmetic checks, not returns
expected from actual trading.

## GitHub Actions
[.github/workflows/ci.yml](../.github/workflows/ci.yml) is configured for every push,
pull_request and manual workflow_dispatch. One Ubuntu24.04 job installs Python3.13 and
Node24, installs backend requirements-lock.txt, runs pytest and the independent reference
probe, runs npm ci in frontend, then frontend tests/build. Cache keys use the backend lock
and frontend/package-lock.json. Yahoo is disabled with MARKETPULSE_FEED_ENABLED=false;
tests use mocks/temp databases. No user API keys/secrets or provider connectivity are
required. Registry access is needed only to install software. Permissions are contents:read;
checkout does not persist credentials. The job has a15-minute timeout and cancels obsolete
runs for the same branch/ref. Official action docs were consulted for checkout/setup
v7 and dependency caching: [checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python), [setup-node](https://github.com/actions/setup-node).

YAML parsing/triggers/disabled-feed checks passed locally. The first ad-hoc validator
incorrectly expected10 steps; the actual workflow has9. The validator was corrected;
this was not an application/test failure. This workflow remains local/uncommitted until
a requested commit/push. **No GitHub-hosted run or green Actions result is claimed.**

## Browser verification blocker and outstanding checklist
CUA browser inventory was attempted and returned `native pipe path unavailable: No such
file or directory`. No browser session, rendered page inspection, manual UI order or
screenshot was achieved in this stage. There were no observed visual defects to fix.

| Required UI check | Automated substitute executed | Browser outcome |
| --- | --- | --- |
| SMA overlays, crossover markers, visibility | chartRenderer/MarketChart/indicator tests | Not run—transport unavailable |
| Account summary, manual order, history | PaperAccount tests and backend/API tests | Not run—transport unavailable |
| Automatic trading controls | StrategyPanel tests, strategy path/isolation | Not run—transport unavailable |
| Backtest config/results/equity/history | BacktestPanel and backtest API tests | Not run—transport unavailable |
| Live/replay separation and feed statuses | App/ReplayApp/socket tests | Not run—transport unavailable |

The jsdom/renderer mocks do not verify real browser layout, pixels or canvas behavior.
A future browser pass must use a disposable app/database with Yahoo disabled and clearly
labeled fixture data; never place demonstration orders in the user's persistent account.
Remaining issues: blocked browser review, remote CI not yet run, existing dependency
warning, sparse historical coverage and the documented simplified trading assumptions.
Part4.3 remains unimplemented.

## Final requirements audit rerun
The final stage reran the same suites: backend204passed/1existing warning (final5.19s),
frontend42passed/11files (1.30s), build succeeded/26modules (573ms). The unchanged
reference probe output matched the saved Fraction/pandas evidence exactly. Full trace,
saved-data327-candle backtest, scoped security checks, hosted push-run query and submission
gaps are recorded in part-4.2-review.md and evidence/part42-final-*.json.
Current runtime health/database and Vite HTML were reachable, feed real_time_unverified,
strategyOFF/main cash10000. This did not constitute browser visual verification.

## November16 rerun and actual browser evidence
The latest run supersedes the earlier browser-access blocker:208backend and49frontend
tests, build and independent SMA probe passed;17 isolated browser workflow checks passed.
Source integrity was checked across87files. This is synthetic/provider-offline browser
evidence, not a live-provider probe. Exact steps, hand expectations, actual revised
driver approaches and artifacts are in [testing-2026-11-16.md](testing-2026-11-16.md) and
[browser-test-cases.md](browser-test-cases.md). GitHub-hosted CI remains not executed;
report.md unchanged and no commit/push. Earlier results above are historical records.
