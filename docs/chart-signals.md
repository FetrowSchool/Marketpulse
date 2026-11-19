# Confirmed crossover markers — November 18, 2026

MarketPulse uses the existing backend-confirmed crossover records. This change does not
alter SMA calculations, crossover equality, order execution, accounting or strategy controls.
BUY remains previous fast <= slow and current fast > slow; SELL uses previous fast >= slow
and current fast < slow. Only completed candles can carry confirmed arrows.

## Rendering and identity

Installed TradingView Lightweight Charts 5.2.1 supplies `createSeriesMarkers`. Green BUY
arrows appear below candles, red SELL arrows above. Purple FILL circles represent actual
persisted simulated fills, positioned in their execution interval. Source timestamps retain
microseconds in details; plotting converts UTC to chart seconds. Signal arrows and fill
circles have independent default-on controls, separate from SMA visibility. Controls only
change presentation. Zoom, follow-latest, price and volume series remain available.

The frontend performs no crossover arithmetic. It accepts backend IDs only when symbol,
interval, candle timestamp, exact observation ID/revision and provenance match the rendered
candle. HOLD, incomplete and stale-revision signals are excluded. Repeated identities are
deduplicated and markers sorted by source time. Live/replay context resets clear unrelated
markers; existing indicator recomputation consumes the mode-specific candle book.

Click a signal candle/marker, hover a recognized marker, or choose the accessible signal
selector to inspect symbol, interval, UTC candle time, SMA values and confirmation. Fills
are associated using backend signal identity or the backend's signal-candle/direction fields.
An absent loaded fill is explicitly unknown execution status, not proof no execution occurred.
The loaded live fill history is bounded; manual fills are not relabeled strategy fills.

## Backtest snapshot chart

After Run Backtest, choose **Show backtest signals on chart**. A separate BACKTEST recorded
chart appears within results, preserving the live/replay workspace and manual order context.
`GET /api/backtests/{id}/chart` reads the exact immutable candle IDs/revisions already stored
with the run and its recorded decisions/fills. It does not recalculate using newer revisions,
write market data, execute orders or mutate account state. Missing/inconsistent snapshots
produce errors. Stable display IDs include the input fingerprint and signal scope. Custom
SMA periods are labeled with their actual values. Only recorded fills get circles.

## Verification and limits

In an isolated source copy `/private/tmp/marketpulse-markers-20261118`, using existing installed
locked dependencies: backend pytest **212 passed**, one existing Starlette/httpx deprecation
warning (5.75s); frontend Vitest **58 passed / 14 files** (1.43s); Vite production build
**passed**, 29 modules (497ms). Source/test hashes were compared with the workspace.

Tests cover BUY/SELL, HOLD/incomplete rejection, exact revisions, duplicate IDs, historical
and replay timestamps, symbol/interval/provenance filtering, independent visibility, selected
details, actual fill association including fractional-second quotes, 5,000-signal snapshots,
and immutable backtest snapshots/API/account isolation. Existing processing/replay/strategy
regression suites also ran. Browser screenshots are separate from mocked chart tests.

Actual CUA browser checks used a disposable database and labeled SIMULATED fixture app on
8001/5174, with Yahoo intentionally unavailable. MSFT closes `[100]*50 + [120,80,80,90]`
produce BUY SMA101/100.4 and SELL; next-bar fills are16 shares at125 and90. Results:
$9,440 ending equity, -$560 realized P/L, one round trip/two fills. The screenshot shows
actual canvas arrows, SMA lines, reliable synthetic interval-volume bars, FILL circles and
BUY details. Turning off signals retained fills/SMAs. Switching the main workspace to empty
SPY removed unrelated signals while the backtest chart remained scoped to MSFT. Separate fill
visibility was exercised. No orders were placed in the user's persistent account.

A visible volume-label overlap was found, fixed by placing its label in normal document
flow, and rechecked in a new screenshot. Initial fixture startup needed local-listener
permission; a copy/test setup race caused a transient empty-component build failure.
After source copying finished, the final tests and build above passed. These were setup
failures, not hidden passing claims. No GitHub-hosted CI run or new live Yahoo verification
was performed in this stage. Replay marker behavior and network/revision edge cases are
covered deterministically, but were not exhaustively re-exercised in this browser session.
Dense markers can overlap at distant zoom; zoom controls and the signal selector remain
available. No dedicated frame-rate benchmark was performed. The backtest limit remains
10,000 candles. No Part4.3, commits, pushes or report.md edits.

## Changed files in this stage

- backend/app/services/backtests.py; backend/app/routes/backtests.py
- backend/app/services/strategy.py (read-only fill association metadata)
- backend/tests/test_backtests.py; backend/tests/test_strategy.py
- frontend/src/services/chartSignals.js; frontend/src/services/chartRenderer.js
- frontend/src/components/MarketChart.vue; frontend/src/components/BacktestPanel.vue
- frontend/src/components/StrategyPanel.vue; frontend/src/App.vue; frontend/src/style.css
- frontend/tests/chartSignals.test.js; frontend/tests/chartRenderer.test.js
- frontend/tests/MarketChart.test.js; frontend/tests/BacktestPanel.test.js; frontend/tests/App.test.js
- README.md; design.md; docs/architecture.md; docs/backtesting.md; docs/chart-signals.md
- docs/evidence-log.md; AI-USE.md; docs/evidence/2026-11-18-markers/

Evidence: [rendered chart](evidence/2026-11-18-markers/backtest-markers.jpg),
[source hashes](evidence/2026-11-18-markers/source-hashes.json).

Raw final logs: [backend](evidence/2026-11-18-markers/backend-tests.txt), [frontend](evidence/2026-11-18-markers/frontend-tests.txt), [build](evidence/2026-11-18-markers/frontend-build.txt).

The running local app was updated and its backend restarted against the existing database;
GET /api/health returned status ok, database connected, version0.1.0. Existing persisted
account/strategy settings were retained. Temporary fixture servers were stopped afterward.
