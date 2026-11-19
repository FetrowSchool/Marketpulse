# Part4.2 browser regression cases

Last executed: **2026-11-16**,17checks passed. Actual results/screenshots are linked in
[testing-2026-11-16.md](testing-2026-11-16.md). Automated Vitest/jsdom cases remain separate
from these browser workflows.

## Safe setup
Use a disposable source copy and temporary database, not the user's running account.
The [fixture harness](evidence/2026-11-16/browser-fixture-harness.py) creates a new temp
SQLite database, seeds known synthetic prices and reliable fixture volume, disables
provider traffic, and exposes fixture-only /_test/stage/buy and /_test/stage/sell controls.
These routes are **not part of the production app**. The
[separate Vite config](evidence/2026-11-16/browser-vite.config.js) routes5174→8001 and
inserts a conspicuous synthetic-data banner. Copy that config into the temporary copy's
frontend so its imports resolve against the installed frontend dependencies. Copy the
harness to an importable temporary module name; run it with PYTHONPATH pointing to the
copy's backend and Uvicorn port8001. Serve the copy with Vite --config on5174.

Main app ports8000/5173 must remain untouched. Use no real brokerage/API keys. Do not
remove the fixture banner or present synthetic volume/prices as provider observations.

For future reruns, use the fixture base date returned by /_test/info to select a range
covering all54MSFTcandles; the November16–17 dates below record this actual execution.
The harness uses its current UTC date, so do not blindly reuse old date selections.

## Checks and expected results

| Case | Browser actions | Expected |
| --- | --- | --- |
| Initial rendering | Open5174 | Banner; chart and50fixture volume bars; SMA100/100; account10000; provider unavailable |
| Indicators | Turn SMA checkbox off/on | Checkbox and chart lines follow; no account action |
| Manual BUY | AAPL,10shares, reference100, submit | Filled order; cash9000,10shares |
| Manual SELL | Sell10, reference110, submit | Cash10100, no shares, realized100 |
| Reject short sale | Sell1 with no position | Rejected order, no fill/cash change |
| Automatic BUY | Enable automatic simulation; POST fixture /_test/stage/buy | Completed120candle confirms101/100.4 BUY; later125quote fills16; cash8100; distinct arrow/circle |
| Automatic SELL | POST fixture /_test/stage/sell | HOLD equality then99/99.6 SELL; later90quote closes16; cash9540, realized−460 |
| Backtest | Select MSFT; UTC Nov16–17; default20/50 and10000; Run | Equity9440, return−5.6%, drawdown7.2%,1round trip/2fills |
| Backtest details | Expand fill/trade tables |16shares entry125/exit90; loss560; equity SVG rendered |
| Missing history | Select SPY; run same range | Explicit insufficient51/0 error, no fake candles/trades |
| Replay | Restore MSFT, choose Replay,100×; Play/Pause | Recorded labeling; manual and automatic controls disabled; Resume available |
| Replay completion | Resume default15minute selection |30/30events; no new orders/fills/account changes |
| Return Live | Choose Live | Live controls restored; provider remains intentionally unavailable; disable test strategy |
| Unrealized P/L | Buy1MSFT@80 | Saved fixture mark90 →unrealized10, equity9550 |
| Final manual close | Sell1MSFT@90 | Cash/equity9550, aggregate realized−450, no holdings |
| Collapse | Close Backend health card | Height95→43px in observed desktop layout |
| Refresh | Reload fixture page | Closed-card preference restored; account persists |
| Repeat backtest | MSFT, same range/config | Same payload except new run ID; paper account stays9550 |

Several rows combine into the17 recorded workflow assertions; details are in
[evidence/2026-11-16/browser-checks.json](evidence/2026-11-16/browser-checks.json).

The replay datetime-local range edit was not verified: the driver failed to fill it, so
this pass used the app's generated range. This is recorded as a limitation, not a pass.
Capture screenshots and raw visible state for revised failures; never alter production
code or replace actual outcomes just to make a browser case appear successful.
