# Assignment 4, Part 4.2 review

Latest verification: **2026-11-16**. The detailed November12 snapshot below is retained
for history; current test/browser evidence is linked in testing-2026-11-16.md.

## Outcome and evidence boundaries
The implemented Part4.2 services and automated tests pass. The November16 rerun passed
208backend/49frontend tests, production build, independent SMA checks and17actual browser
workflow checks using isolated synthetic fixtures. This is **not an assertion that every
submission requirement is complete**: workflow/code remain uncommitted with no hosted CI
run, and the accessible30–60second Part4.2 video/submitted commit remain unverified. No Part4.3 functionality
was added. No commit was created. An older report.md already exists and was left unchanged;
no Part4.2 report was created or rewritten.

Repository configured in Git: https://github.com/FetrowSchool/Marketpulse
Current branch: codex/part-2. Current HEAD:90cb7a00a7c9f56125fb1fd35b9140edf2a7511b.
This is **not a submitted Part4.2 commit**: the Part4.2 implementation remains uncommitted.

## Requirements checklist
“Automated” means current source plus executed tests/API evidence, not browser pixels.

| # | Requirement | Audit finding / evidence |
| --- | --- | --- |
|1 | SMA20 displayed | Implemented LineSeries/legend; chart renderer/component tests pass; visual inspection outstanding |
|2 | SMA50 displayed | Implemented distinct LineSeries/legend; tests pass; visual inspection outstanding |
|3 | BUY crossover | Completed previous<=/current> rule, exact reference and full execution trace pass |
|4 | SELL crossover | Completed previous>=/current< rule; analytical/live/backtest tests pass |
|5 | Confirmed vs provisional | Completed-only; incomplete SMAs null/confirmed=false; no provisional implementation or trades |
|6 | Simulated account | Singleton$10,000 USD seed; visibly SIMULATED; API/account tests pass |
|7 | Persistent orders/fills | SQLite ledger, idempotency/immutability and restart tests pass |
|8 | Cash | Integer micro-USD; hand-calculated BUY/SELL checks pass |
|9 | Positions | Whole shares, average cost and separate strategy-owned quantities; tests pass |
|10 | Realized P/L | Partial/full sales and residual basis release tests pass |
|11 | Unrealized P/L | Latest saved marks with unavailable/stale labeling; equity identity tests pass |
|12 | Automatic SMA strategy | Opt-in/defaultOFF; confirmed inputs, later executable quote, full trace passes |
|13 | Execution explanations | Persisted waiting/skipped/executed reasons and Vue status panel; tests pass |
|14 | Historical backtesting | Event-driven isolated account; saved-data representative run passes |
|15 | Backtest trade history | Closed round trips distinct from fills, entry/exit IDs/prices/times; tests pass |
|16 | Performance | Equity/return/P&L/win rate/drawdown/curve; hand and saved-data tests pass |
|17 | No look-ahead in model | First-completion/as-of availability; no same-close fill; future perturbation/next-open tests pass; coverage/execution biases remain documented |
|18 | Batch/incremental SMA |360 synthetic points, exact reference + incremental production helper comparison pass |
|19 | Independent reference |Fraction batch/running sums and pandas rolling means, explicit values/tolerance recorded |
|20 | Browser testing | **Verified on November16 with synthetic fixtures**:17actual browser checks; no live-provider browser claim |
|21 | Actions on pushes | Push/PR/manual YAML locally valid; **not active/verified on GitHub for uncommitted Part4.2 code** |
|22 | Documentation | Setup/test commands, implementation/rules/schema/biases/evidence/AI disclosure current; stale scope statements corrected in this audit |

Part4.1 market streaming, normalized observations/revisions,1m/5m/15m construction,
SQLite, shared live WebSocket, chart/volume honesty and isolated replay remain in the
full passing suite. Fresh Yahoo status remains “Real-time unverified”; no entitlement
claim or new live-provider probe was made.

## End-to-end deterministic trace
Executed against a newly created disposable database with the real app factory,
MarketDataService.handle_message and repository completion/post-commit callbacks.
Provider-shaped messages in this example are **synthetic fixtures**, despite using the
Yahoo parser/source namespace; the user account was never used.
Exact IDs/payloads/timestamps/inputs/orders/fills/account are in
[evidence/part42-final-trade-trace.json](evidence/part42-final-trade-trace.json).

1. Before15:50UTC:50 completed candles close100, previous SMA20=SMA50=100. Strategy is
   explicitly enabled in the disposable test account with cash10000, no position.
2. Source observation120 at15:50:30, received15:50:31, updates the15:50candle while
   incomplete. No crossing/order can use it yet; completed count remains50.
3. Completion timer at15:51:00.500 marks the elapsed candle complete and commits it.
   Available history is those50 closes plus120. SMA20=(19×100+120)/20=101;
   SMA50=(49×100+120)/50=100.4. Previous equality followed by fast>slow confirms BUY.
   The signal records its confirming candle ID,51 input candle IDs, confirmation time
   and maximum available observation ID. The decision waits; **no order exists yet**.
4. Only later, source quote125 at15:51:01 is received15:51:02. Its ID is greater than
   the signal's available boundary, source/receipt are after confirmation, both fresh.
   This observation was not available when the signal was calculated. The engine uses
   it for execution, rather than the earlier close120.
5. Allocation20%×10000=2000; floor(2000/125)=16 whole shares. Cost2000, fees0,
   cash8000, quantity16, basis2000, average125. Mark125 gives market value2000,
   equity10000, realized/unrealized P/L0. Order, fill, ownership, account and decision
   commit together with traceable foreign keys. Duplicate quote delivery leaves one fill.

This verifies simulation accounting/availability, not real execution or profitability.
Incomplete, out-of-order, replay and restart cases also pass in the full suite.

## Representative saved-data backtest
A SQLite-aware read-only backup of the running recording database was copied into a
disposable directory. No POST/order was sent to the user application. The isolated
runner processed AAPL1m,2026-11-09inclusive to2026-11-13exclusive, initial10000,
SMA20/50, constructed origin. First completed versions and recorded availability were
used; live main-account/strategy state was not involved.

Actual result from this snapshot:

| Metric | Result |
| --- | ---: |
| Selected completed candles |327 |
| Confirmed crossings |12 |
| Fills / completed round trips |11 /5 |
| Ending cash |$8,216.324500 |
| Open quantity |5 |
| Ending equity |$9,996.525000 |
| Realized / unrealized P/L |−$5.100500 /+$1.625500 |
| Total return |−0.0347500% |
| Maximum event-mark drawdown |0.1657518944286704424372801105% |
| Closed-trade win rate |20% |
| Equity curve events |652 |

Not every crossing fills: a SELL without a strategy position, a BUY while already long,
or a final decision without a later eligible open can skip/remain unfilled. The trace
contains actual reasons, individual fills and understandable entry/exit round trips.
Ending equity=starting equity+realized+unrealized=10000−5.100500+1.625500=9996.525.
Two runs on the same snapshot/config matched except run ID. All11 original market,
account and strategy tables in the backup retained identical hashes; only disposable
backtest results were inserted. See
[evidence/part42-final-backtest.json](evidence/part42-final-backtest.json).

Historical inputs/API/result computation were verified. Result display/equity SVG/history
have passing Vue tests, but **actual browser display was not inspected**. This capture
contains trading behavior; no fake trades were needed. The synthetic fast2/slow3 reference
also verifies loss798/equity9202/drawdown9.31% independently (verification.md).
These limited historical results are not investment advice or expected future returns.

## SMA and accounting verification
Reference probe rerun: exact Fraction and pandas3.1.1 rolling means vs batch/incremental
app calculations. Absolute tolerance1e-9 USD, relative0; max difference
2.3283064365386963e-10 USD over360 points. Rising1…50 produces40.5/25.5; constant100.125
produces equal100.125/100.125 with HOLD. Missing/incomplete/boundary/revision tests pass.
Selected expected/actual values: evidence/sma-reference-verification.json.

Partial-sale example verified: buy10@100 and10@120 →20shares/basis2200/cash7800;
sell5@140 →15shares/basis1650/cash8500/realized150; mark130 →unrealized300/equity10450.
Fees/slippage0; rejected orders create no fill or account mutation. The second decimal
reference table and exact equations are in verification.md.

## Historical automated and runtime verification — November12
Executed from matching source at /private/tmp/marketpulse-final-review, using existing
installed dependencies. Commands: `cd backend && ../.venv/bin/python -m pytest` and
`cd frontend && npm test && npm run build`, plus the independent reference probe.
No dependency updates were needed. Full output/result counts are recorded in the evidence
log. Backend204passed with one existing Starlette/httpx warning; frontend42passed/11files;
production build succeeded (26modules). No failures in either suite.

Read-only runtime checks: health ok/database connected/version0.1.0; Vite returned the
MarketPulse entry HTML; feed state real_time_unverified; automatic strategyOFF;
main account cash10000. Receiving entry HTML is not browser verification.

## Historical browser and CI status — November12
CUA browser inventory again returned `native pipe path unavailable`. Chart, volume,
SMAs/markers/toggle, account/manual/auto controls, histories, backtest curve, errors,
replay and feed visuals remain **unverified in a Part4.2 browser pass**. Historical
Part4.1 screenshots are not evidence for new Part4.2 UI. A future UI pass should use a
disposable database and clearly labeled deterministic data for trades/error injection.

CI workflow .github/workflows/ci.yml has push, pull_request and workflow_dispatch,
Python3.13/backend lock install/tests/reference probe, Node24/npm ci/tests/build,
explicit directories, Yahoo disabled, read-only permissions and15-minute timeout.
Local YAML/events/directories/feed checks passed. GitHub connector query for current
HEAD returned no push-triggered workflow runs. The workflow itself is untracked/local;
no GitHub green check or deployment is claimed. No commit/push was performed.

## Security review and limits
- No brokerage SDK/client/order routing in app sources/manifests; fills are local paper
  accounting only. No real-money trade was executed.
- Common credential-pattern scan of103 tracked files plus current app/workflow text
  found no private-key/token patterns. Configuration uses environment variables; no
  secrets are required for tests or sent to browser bundles. This is a scoped source
  scan, not a complete entropy-based audit of all historical blobs.
- No .env/database/dependency paths in tracked files. A local all-ref filename history
  check found no *.sqlite*,*.db or .env commits. .gitignore excludes local DBs/WAL,
  .env, virtualenv and node_modules. The history command was slow but completed.
- Incomplete-signal, idempotency/restart/reconnect, replay isolation, cash/share rejection
  and backtest-isolation tests all passed. Main account stayed untouched/defaultOFF.
- This is a single-user local app without authentication, production deployment,
  exchange-calendar coverage or realistic spread/liquidity/fee/slippage execution.
  Sparse history, corporate-action coverage, survivorship/selection bias and parameter
  overfitting remain. Next-open timing tests do not eliminate all historical data biases.

## Documentation revisions and submission gaps
This audit corrected stale “no indicators/trading/backtesting” statements left from earlier
stage narratives and a stale timing-helper docstring. No behavioral patch was necessary.
Earlier actual revised approaches include fixing chart watcher fill-marker forwarding,
correcting an ad-hoc workflow step-count validator and restoring a missing legacy script
in the temporary verification tree; see evidence-log.md. None is invented browser evidence.

Before the eventual Canvas report-only submission:
- November16 isolated browser workflow review is complete; retain the distinction from
  live-provider verification and the still-untested manual replay-date edit.
- Obtain explicit instruction before committing/pushing the Part4.2 implementation and
  workflow, then verify the actual hosted CI run and identify the submitted commit.
- Provide/verify an accessible30–60second Part4.2 demonstration video; none was created
  or verified here. Existing older report/video artifacts are not new Part4.2 evidence.
- Only when requested, prepare report.md with overview/features/design/verification,
  limitations, repository URL/submitted commit, supporting doc links and video.

Supporting current docs: README.md, design.md, architecture.md, database.md,
indicators.md, paper-trading.md, strategy.md, backtesting.md, verification.md, AI-USE.md
and evidence-log.md. No Part4.3 work was begun.

## Files changed in this audit

- `README.md`
- `AGENTS.md`
- `design.md`
- `AI-USE.md`
- `docs/architecture.md`
- `docs/indicators.md`
- `docs/paper-trading.md`
- `docs/verification.md`
- `docs/evidence-log.md`
- `docs/part-4.2-review.md`
- `backend/app/services/strategy.py`
- `docs/evidence/part42-final-trade-trace.json`
- `docs/evidence/part42-final-backtest.json`
- `docs/evidence/part42-final-audit.json`

The only source edit is a stale docstring correction; other edits are documentation/evidence.

## November16 update
Browser access worked in a separate labeled fixture app.17checks passed, including actual
manual/automatic simulated trades, chart/volume/SMAs/markers, account P/L, replay controls,
backtest results/equity/history/errors and refresh persistence. Automated208backend and
49frontend checks, build and references passed. No production source or report change,
commit/push or new live-provider proof. See [testing-2026-11-16.md](testing-2026-11-16.md),
[browser cases](browser-test-cases.md) and [summary](evidence/2026-11-16/summary.json).
The older browser-unavailable observations above remain dated historical evidence only.
