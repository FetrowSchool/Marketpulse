# MarketPulse

A university Live Market Workstation built with Vue 3, Vite, JavaScript, CSS,
Python, FastAPI, SQLite, Uvicorn, pytest, and yfinance. Part 4.1 now includes the
backend Yahoo streaming connection, observation normalization, constructed quote
candles, persistence, market APIs, and WebSocket fanout to Vue. The responsive dark
dashboard now renders TradingView Lightweight Charts 5.2.1 candlesticks and an aligned
volume pane, alongside the selected stock's latest available price, source/receipt
times, age, candle state, and separate browser/provider connections. Read-only deterministic
replay now includes symbol/range selection, playback controls, and live/replay isolation.

## Install
Use Python 3.11+ and Node 22.18+ or 24.12+ with npm. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
```

`backend/requirements-lock.txt` records the exact Python 3.13 environment verified
for this stage; install that file to reproduce it on a compatible platform. The
range-based requirements file lets pip choose compatible dependencies on other
Python versions. yfinance itself is pinned to **1.8.0** because the managed streaming
adapter depends on inspected internal receive/decode seams. npm uses its lockfile.

## Startup
Backend, from repository root in one terminal:

```sh
cd backend
../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, from repository root in another terminal:

```sh
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to port 8000. API docs are at
http://127.0.0.1:8000/docs. Use one backend worker to avoid redundant subscriptions.
No hosted deployment or production proxy is configured; `vite preview` only previews
the frontend build and does not provide the development HTTP/WebSocket proxies.

SQLite initializes automatically at backend startup. It creates missing tables/indexes
without overwriting data. A raw quote and its resulting candle revision commit in one
transaction. The existing schema remains version 1; source-time and receipt-selection indexes
are installed repeatably. Observation UPDATE and DELETE remain prohibited by triggers.

## Yahoo streaming and verification
The backend uses yfinance's `AsyncWebSocket` against
`wss://streamer.finance.yahoo.com/?version=2`, with one shared subscription to the four supported symbols.
Public subscribe/close operations establish/manage the provider connection; a narrow,
version-checked adapter receives frames and uses yfinance's protobuf decoder. The
standard `listen()` loop is deliberately avoided because its built-in retry/error
suppression conflicts with application-owned bounded reconnects. There is **no
historical-data polling fallback** or yfinance historical download. `/ws/market` broadcasts committed data to Vue,
where Lightweight Charts renders the saved and incoming candle revisions.

A real-provider attempt on **November 8, 2026 (America/New_York)** successfully
subscribed to AAPL, received **one actual provider observation**, persisted it, and
produced a provisional then completed local candle revision. Initial sandbox DNS and
Python CA-store attempts failed; selecting the installed certifi CA bundle allowed
the successful TLS-verified attempt. Captured evidence is in
[the evidence log](docs/evidence-log.md) and [provider capture](docs/evidence/yahoo-stream-2026-11-08.json).
This verifies the stream path, not exchange real-time entitlement, complete market
coverage, or active regular trading. The received data was labeled delayed/unverified.

If Python reports a local issuer/certificate error, configure a trusted CA bundle;
do not disable TLS verification. In the backend terminal, for this environment:

```sh
export SSL_CERT_FILE="$(../.venv/bin/python -m certifi)"
```

This only selects the installed trusted CA bundle for the current shell. A compatible
system trust store may need no override. No global certificate settings are changed.

## Configuration
Settings read process environment variables; `backend/.env.example` documents them.
`.env` is not automatically loaded. No API keys or credentials are needed.

| Variable (MARKETPULSE_ prefix) | Default | Meaning |
| --- | --- | --- |
| DB_PATH | Absolute backend/data/marketpulse.sqlite3 | SQLite path; supplied relative paths resolve from process working directory |
| VERSION | 0.1.0 | Application/health version |
| CORS_ORIGINS | http://localhost:5173,http://127.0.0.1:5173 | Explicit browser origins |
| FEED_ENABLED | true | Start streaming and candle finalization during lifespan |
| SYMBOL | AAPL | Default API/UI symbol; all four are recorded through one Yahoo socket; browser selection is per client |
| CANDLE_INTERVAL | 1m | Default API/UI interval (1m, 5m, or 15m); all three are constructed live |
| REALTIME_CONFIRMED | false | Explicit source provenance confirmation; socket connection alone is insufficient |
| FRESH_SECONDS / STALE_SECONDS | 15 / 120 | Independent source-age and receipt-age thresholds |
| MAX_FUTURE_SECONDS | 5 | Allowed future source clock skew; larger values rejected |
| CONNECT_TIMEOUT_SECONDS / CLOSE_TIMEOUT_SECONDS | 15 / 5 | Bounds on transport operations |
| RECONNECT_BASE_SECONDS / RECONNECT_MAX_SECONDS | 1 / 30 | Exponential retry delay, capped at maximum |
| MAX_RECONNECT_ATTEMPTS | 5 | Consecutive failure budget, including initial failed attempt |
| COMPLETION_CHECK_SECONDS | 1 | Check for elapsed candle intervals |

Boolean values accept true/false or 1/0. Invalid symbols, intervals, nonfinite or
nonpositive thresholds, and invalid backoff ordering fail configuration explicitly.
A durably processed valid message resets the consecutive failure counter. After the
failure budget is exhausted the feed stays unavailable until backend restart.
Set `MARKETPULSE_FEED_ENABLED=false` to use saved data and replay with no provider access.

## APIs
| GET endpoint | Behavior / query parameters |
| --- | --- |
| /api/health | Application, SQLite connectivity, version; 200 or 503 |
| /api/market/status | Connecting/live/real_time_unverified/delayed/stale/disconnected/unavailable, transport, source/receipt timestamps and separate ages, counters/errors, session qualification |
| /api/market/symbols | Supported symbols/intervals and active_symbol/active_interval defaults |
| /api/market/observations | All raw revisions in ingest ID order; symbol, limit (1–1000, default 100), after_id (>=0); next_after_id cursor |
| /api/market/candles | Latest revision per local candle; symbol, interval, limit (1–1000), revisions=true for revision history; latest N rows returned chronologically |

Symbol and interval default to the active configuration. A supported symbol/interval
that has never been recorded returns an empty array. Invalid parameters return 422;
market database read failures return 503 without private paths. HTTP 200 on market
status does not mean the feed is live; inspect its `state` and `reason`.

Raw prices are in normalized metadata and exposed as `price` by the API; raw OHLCV
columns remain NULL. Provider daily totals/sizes remain original metadata. Local
candles contain source-time OHLC, source lineage, completion, and **NULL volume**.
They are constructed quote candles, not provider-supplied or exchange trade candles.
No empty gap candles or invented prices are generated.

Default provenance is conservatively **delayed/unverified**. A live state additionally
requires confirmed configuration, fresh source/receipt ages, and a weekday regular
clock window. The session window is not a holiday calendar and never verifies an open
exchange; overnight/holiday sessions are not modeled. Provider market_hours codes are
preserved without guessing undocumented numeric meanings. Backend health does not
imply feed health. See [design](design.md) for detailed policies and limitations.

## Verification
From repository root:

```sh
cd backend
../.venv/bin/python -m pytest
```

Frontend regression checks, from repository root:

```sh
cd frontend
npm test
npm run build
```

Automated tests are offline: synthetic fixtures are explicitly documented, and one
captured provider fixture is replayed with recorded provenance. They never depend on
Yahoo availability. For an explicit real-provider probe, from `backend/`:

```sh
../.venv/bin/python scripts/verify_yahoo.py --symbol AAPL --seconds 30 --output /tmp/marketpulse-yahoo.json
```

The probe uses an isolated temporary database, prints its actual outcome, preserves
provider metadata in the optional output, and closes cleanly. A successful subscription
without observations is reported separately from receipt of provider observations.
See [the evidence log](docs/evidence-log.md) for measured test outcomes and runtime limits.

## Remaining work
Provider-candle ingestion, comprehensive exchange calendars, and feed gap
recovery remain unimplemented. Part 4.2 now includes completed-candle SMA indicators/crossover signals and a manual
simulated account and opt-in automatic simulated crossover strategy; isolated historical backtesting is implemented.
Part 4.3 adds AI/chat/image interpretation/audio. None of those later features are
implemented here.


## Browser WebSocket integration
The actual flow is Yahoo → normalization/candle processing → SQLite commit →
FastAPI `/ws/market` → Vite `/ws` proxy → Vue. One shared provider socket records
AAPL/MSFT/NVDA/SPY. Each browser chooses its own validated symbol; switches do not
change other clients or create new Yahoo connections. The configured SYMBOL selects
the default API/UI stock, rather than restricting capture to one symbol.

The reusable browser service reconnects with bounded exponential backoff and an
8-retry unstable-connection budget. It resubscribes after reconnect; the backend
restores the latest available committed quote/candle as a snapshot. Intermediate
missed revisions remain available through REST; this is not complete replay.

Browser socket connectivity and Yahoo feed state are shown independently. Prices
remain last known during outages, ages keep increasing, and stale values are never
presented as current. Source mode (live/delayed/recorded/simulated), UTC source time,
backend receipt time, and local candle completion/revision metadata remain visible.
The chart renders only backend candle rows; there are no generated prices or invented volume.

Message types: connection_status, market_observation, candle_update,
candle_completed, feed_status, error. The complete schema, subscription request,
limits, close behavior and recovery guarantees are in [docs/websockets.md](docs/websockets.md).
Use one backend worker; no cross-process broker is implemented. Production reverse
proxies must support `/ws` upgrades and approved browser origins.

For an explicit provider → database → browser-facing WebSocket check while both dev
servers are running (from backend/):

```sh
../.venv/bin/python scripts/verify_market_socket.py --url ws://127.0.0.1:5173/ws/market --seconds 30 --output /tmp/marketpulse-websocket.json
```

This command uses real network connections, verifies the WebSocket record against
its REST/SQLite representation, and reports whether provider observations actually
arrived. It is separate from mocked automated tests. Actual outcomes are retained
in the evidence log; a successful browser transport alone is not a live-data claim.


## Visual workstation and candle history
`MarketChart.vue` is the reusable TradingView Lightweight Charts component. It renders
candlesticks and a corresponding volume histogram in two panes sharing one UTC time
axis. Price axes, crosshair, pan/zoom and a Fit view button use the chart library.
The workstation includes symbol/interval selection, latest available quote (or an
explicitly labeled saved candle close), provider-reported price change when supplied,
source/receipt timestamps, increasing data age, completion/revision details and
independent browser/Yahoo/health states. TradingView attribution is retained.

Selecting a symbol or interval requests the latest **up to 1000 saved candles** from
`/api/market/candles`. Incoming WebSocket candles merge into the same revision-aware
book while history loads. A stale HTTP response cannot replace a newer revision;
old selection responses are aborted and ignored by generation. After subscription
acknowledgment/reconnection history reloads to fill the subscription gap. Raw quotes
update the price panel; authoritative backend candle events update OHLC. Vue does not
construct candles from prices or write chart revisions back into SQLite.

Existing historical revisions use `series.update(bar, true)`. Inserting a previously
unseen older opening uses sorted `setData`, preserving the visible time range. Normal
active/latest updates use incremental `update`; viewport fitting is initial/manual,
not forced on every tick. Empty time intervals are not filled with invented bars.

The interval selector supports live 1m, 5m and 15m candles simultaneously. Each unique
Yahoo quote is stored once and rebuilds all three affected source-time buckets in the
same transaction. CANDLE_INTERVAL selects the default UI/API interval. Switching charts
uses saved history plus incoming interval revisions; no extra Yahoo connection or
historical polling is opened. Previously unrecorded intervals populate as quotes arrive;
there is no automatic backfill of every old bucket.

Volume bars require finite, nonnegative interval volume with an explicit reliable
metadata marker (`volume_reliable=true` or `volume_semantics=interval_trade_volume`).
Current Yahoo quote candles have NULL volume, so the histogram stays empty with a
visible explanation. Whitespace time points align the volume pane without fake zeros.
Daily totals and last sizes are never summed or converted into invented candle volume.

Recorded/simulated data stays labeled; delayed, stale, disconnected and unavailable
values remain last known. Receipt timestamps and charts remain available during
browser reconnection. Replay, SMA indicators and manual simulated accounting are implemented; opt-in automatic simulated trading is implemented; isolated backtesting is now available below. Details and browser evidence are in
[docs/charting.md](docs/charting.md) and [the evidence log](docs/evidence-log.md).


## Recorded replay
Select **Replay** in the dashboard. It loads the selected symbol/interval's last 15
recorded minutes, plus an as-of baseline. Edit **Start / End · UTC** (end exclusive),
choose receipt-time or commit-arrival ordering, and click **Load selection**. Play,
Pause, Resume, Restart, Stop and 0.25–100× speed operate on the frozen selection.
Progress counts recorded rows, including raw observations and candle revisions.
Replay shows **REPLAY · RECORDED**, original timestamps and recorded source age;
it never changes stored provenance or presents historical values as current.
Returning to Live reloads saved history and restores the live subscription.

Replay requires the backend and existing saved observations, **not Yahoo connectivity**.
No demonstration prices or runtime fixtures are inserted. To run offline with your
existing database, from `backend/`:

```sh
MARKETPULSE_FEED_ENABLED=false ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
../.venv/bin/python scripts/verify_database.py --db data/marketpulse.sqlite3
```

The audit is read-only. Existing records remain append-only; no column migration or
record rewrite was needed. The executable DDL remains backend/app/schema.sql.

- `GET /api/replay/catalog?symbol=AAPL&interval=1m`: available receipt bounds/count.
- `GET /api/replay/records?symbol=AAPL&interval=1m`: paged immutable rows, optional
  aware `start`, `end`, `order=receipt|arrival`, `limit`, `after_sequence`, `snapshot_max_id`.
- `/ws/replay`: per-browser frozen playback session, independent of `/ws/market`.

Selections are limited to 10,000 events; narrow the range when necessary. The chart
retains up to 1,000 openings. No seek or durable session recovery is implemented:
a lost replay connection requires Load selection and starts a new session. Reliable
interval volume is displayed when recorded with the required metadata; current Yahoo
quote candles have none. See [replay protocol](docs/replay.md) for exact behavior.

Replay verification (2026-11-09): **115 backend tests**, **24 frontend tests**, and
production build passed in a source-matched temporary copy. Browser playback of
**76 genuine previously saved AAPL events** completed with the Yahoo feed disabled;
all **2,138 stored rows and their row digest remained unchanged**. No new live-provider
observation was claimed in this stage. Details, initial failures and browser limits
are in [the evidence log](docs/evidence-log.md).


## Part 4.1 final audit — 2026-11-09
The [requirements and submission review](docs/part-4.1-review.md) maps all 18 requested
capabilities to their actual status and evidence. A fresh source-only copy installed
Python requirements and `npm ci` successfully, initialized an empty database and
started both documented servers. **117 backend tests passed (0 failed, 0 skipped)**;
**24 frontend tests passed (0 failed, 0 skipped)**; production build passed.

A newly received Yahoo AAPL observation was traced through decoded metadata,
normalization, SQLite, a non-snapshot WebSocket frame and the browser's matching
price/source/receipt timestamps. The feed remained **delayed**: provider streaming
receipt was verified, exchange real-time entitlement was not. A simulated upstream
outage verified bounded retries, unavailable status, retained charts, advancing age
and independent replay. Reliable-volume rendering was separately browser-tested with
an explicitly simulated fixture in a disposable database; Yahoo interval volume is
still unavailable. See [audit evidence](docs/evidence-log.md) for exact results.

The pipeline verification script now excludes saved subscription snapshots from
new-provider evidence and queries the exact observation ID, including databases with
more than 1,000 rows. Saved snapshots remain available in a separate evidence field.

The fresh npm install reports four moderate transitive development-dependency
advisories (glob/minimatch chain through js-beautify/editorconfig); these remain
unresolved. Python `pip check` reports no broken requirements. The existing test-client
deprecation warning remains. No dependency upgrade or claim of a security audit is made.

No report.md or commit was created. This checkout currently has no configured Git
remote or HEAD commit, and no demonstration video was recorded. Those submission
items must be supplied before the eventual report-only Canvas submission.

## Freshness label update — 2026-11-11
Fresh Yahoo observations now display **Real-time unverified** (`real_time_unverified`
in feed-status payloads) when real-time delivery is not confirmed. This also applies
outside regular hours without asserting active trading. If either source or receipt
age exceeds FRESH_SECONDS (default 15), the status becomes **Delayed**; above
STALE_SECONDS (default 120), **Stale** takes precedence. Disconnected/unavailable and
recorded/replay states retain their meanings. Vue checks age between status messages.
Stored provenance remains unchanged and is explicitly labeled separately in the UI;
there is no database migration or retroactive relabeling. Tests: 118 backend and 25
frontend passed; production build passed. The running dashboard was browser-verified.

## Automatic candle zoom — 2026-11-11
The chart defaults to **Latest 25** candles with **Follow latest** enabled. The Zoom
selector focuses on the latest 10/25/50/100 candles in one step, sharing the time range
with volume. Uncheck Follow latest to pan/zoom freely without subsequent ticks resetting
the viewport. **Fit all** shows all loaded history and disables following. All-history
mode leaves manual navigation available. The same controls work for live and replay,
across symbol/interval changes. Empty/small datasets use available candles only.
The replay panel now has an **Open replay** button in Live mode; playback controls
activate after the saved selection loads instead of appearing as unexplained placeholders.

## Part 4.2 — SMA indicators and crossover signals
Development branch: `codex/part-2`. SMA indicators/signals are implemented alongside the manual simulated account below;
opt-in automatic simulated trading is implemented; isolated historical backtesting is implemented. Existing market streaming,
volume handling, history and replay are preserved.

The dashboard overlays **SMA(20)** (blue), **SMA(50)** (gold), and BUY/SELL arrows. The
legend shows the latest completed-candle values and crossover result with its candle
timestamp. Toggle **SMA indicators** to hide/show lines and markers. Only completed
candles count: SMA20 needs 20 closes, SMA50 needs 50, and a crossover needs both previous
and current pairs (at least 51 completed candles). Incomplete candles have no indicator
values/signals; no provisional calculations are performed. The indicator API itself never executes trades.

BUY requires previous fast<=slow and current fast>slow; SELL requires previous fast>=slow
and current fast<slow. Current equality means HOLD. Staying above/below produces HOLD,
not repeated BUY/SELL. Higher candle revisions recompute the snapshot; stable signal IDs
replace corrected/retracted markers instead of appending duplicates.

| API | Behavior |
| --- | --- |
| GET /api/indicators/config | Periods, equality/completion rules, limits and execution-disabled flag |
| GET /api/indicators/sma | symbol/interval, limit 1–1000, optional as_of_id; points, signals and latest completed status |
| GET /api/indicators/signals | Same selection; confirmed crossings plus latest completed HOLD/BUY/SELL status |
| POST /api/indicators/evaluate | Bounded chart candle snapshot for live or replay; all calculations remain in Python |

Replay sends only its arrived/as-of candles to evaluate. It does not query current/future
SQLite revisions for indicators. Source/provenance/type changes reset the window rather
than combining unlike data. Missing time buckets are not filled. Calculations cover the
retained 1,000-candle snapshot, so its earliest points need their own warm-up.

Verification: **132 backend tests**, **33 frontend tests**, and production build passed.
Manual/Fraction references and actual saved-data API results are documented in
[docs/indicators.md](docs/indicators.md). Browser automation was unavailable during this
stage, so no new visual browser verification is claimed. No schema migration or indicator
ledger was added. Signals are analytical derived views, not executions or recommendations.

## Part 4.2 — Manual SIMULATED account
The dashboard now includes a persistent **SIMULATED** USD account starting at **$10,000**,
available cash, equity, average-cost positions, realized/unrealized P/L, order history and
fill/trade history. This is paper accounting with no brokerage connection or real trades.

Choose the stock using the dashboard selector. Enter whole shares and an explicit
**manual reference price** (up to six decimal places), then submit a paper order.
“Use displayed price” copies that price rounded to six places; it does not guarantee a
current market fill. Zero commissions and zero slippage apply. Long-only, no leverage,
no fractional shares or short selling. Uncheck Fill immediately to create a pending
order; it reserves no funds/shares and fills at its fixed creation reference price only
when you manually select Fill. Pending orders can be canceled. Insufficient cash/shares
creates a retained rejected order; malformed requests return422 without creating an order.

Orders use client_order_id idempotency keys; retrying the same request cannot execute
again, and reusing a key with different details returns409. Cash, position, fill and
order status commit atomically. Restart/replay never resets or re-executes the account.
Replay disables manual submission/fill controls; the account remains independent.
Automatic execution is a separate opt-in strategy described below; isolated backtesting is described below.

Position values use latest saved provider quotes, with their timestamps, age and original
provenance. They can be stale. Missing/invalid marks produce unavailable equity/P&L,
not invented prices. Cash, costs and realized P/L remain available. Monetary accounting
uses integer micro-USD; averages are displayed from exact remaining cost basis. See
[execution/accounting documentation](docs/paper-trading.md) and
[database schema](docs/database.md) for rounding, lifecycle and migration details.

APIs: GET `/api/paper/account`, `/positions`, `/orders`, `/fills`, `/trades`;
POST `/api/paper/orders`, `/orders/{id}/execute`, `/orders/{id}/cancel`.
History endpoints accept limit1–1000 (default100); the dashboard shows the latest100.
Initialization adds the accounting tables/seed inside the existing startup transaction;
original observations and market schema_version1 are preserved. No account reset endpoint
is provided. Back up active SQLite files with the SQLite backup API, including WAL state.

## Part 4.2 — Automatic SIMULATED SMA strategy
Automatic trading defaults **OFF**. In the strategy panel, enable the selected symbol and
interval explicitly. Disable before changing its configured selection. This controls a
single backend strategy, independently of which browser is open; enabled configuration
survives restart. Disable cancels pending decisions without liquidating existing shares.

Confirmed completed-candle SMA20/50 crossings queue decisions. BUY allocates up to20% of
cash at the first eligible subsequent observed price, rounded down to whole shares;
SELL closes only shares managed by that strategy scope. No brokerage, leverage, shorts,
fabricated fills or real execution. Analytical arrows differ from purple SIM fill circles.
Replay cannot drive this strategy; an already enabled engine can still process genuine
provider arrivals while a browser views replay.

GET `/api/strategy/status`, POST `/api/strategy/config` with
`{"enabled":true,"symbol":"AAPL","interval":"1m"}`, and GET
`/api/strategy/fills?symbol=AAPL&interval=1m` expose configuration and traceable actions.
See [strategy rules and limitations](docs/strategy.md).

Latest verification: **173 backend tests**, **39 frontend tests**, and production build
passed using deterministic fixtures. Two startup initializations preserved89,807 market
rows and account row hashes, with integrity/foreign-key checks passing. Automatic trading
was left OFF and no test orders were submitted to the user account. Browser automation
transport was unavailable, so visual verification is not claimed for this stage.

## Part 4.2 — Historical backtesting
Use **SMA crossover backtesting** below the chart. Select the dashboard symbol/interval,
UTC start/end (end exclusive), candle origin, starting balance and periods; click **Run
Backtest**. Defaults$10,000/SMA20/50; fast must be less than slow. Stored data only, no
additional Yahoo downloader. Results include equity/return/P&L, completed trades vs fills,
win rate, maximum drawdown, equity curve and histories. Insufficient history is reported.

The event-driven engine shares the existing SMA/crossing/sizing functions, uses first
completed candle versions and recorded availability, and fills at the next eligible open.
It never fills at the signal candle close. Long-only whole shares,20% cash allocation,
zero fees/slippage. Missing next open means unfilled; no forced end liquidation.
Each run has independent cash/positions and persists only in backtest_runs. Live account,
strategy, replay and market observations are untouched; backtest fills are never live.

APIs: POST `/api/backtests`, GET `/api/backtests`, GET `/api/backtests/{id}`. See
[backtesting rules, schema and bias limitations](docs/backtesting.md).
Latest full verification: **192 backend tests**, **42 frontend tests**, production build
passed in the matching dependency-equipped temporary copy. Two runs using292 saved AAPL
candles matched; all108,941 market records and live account/strategy row hashes were
preserved. Automatic trading stayedOFF. Browser automation was unavailable, so no new
visual verification is claimed. Historical results do not guarantee future performance.

## Part 4.2 verification and continuous integration
Latest local checks: **204 backend tests passed**, **42 frontend tests passed**, and
production build succeeded. Batch and incremental SMA20/50 were checked against exact
Fraction arithmetic and pandas rolling means over360 synthetic points. Absolute tolerance
is1e-9 USD (relative0); largest measured difference2.3283064365386963e-10 USD.
Explicit values, accounting tables, full strategy lineage and hand-checked equity/drawdown
examples are in [verification.md](docs/verification.md) and
[reference evidence](docs/evidence/sma-reference-verification.json).

```sh
cd backend
../.venv/bin/python -m pytest
../.venv/bin/python scripts/verify_references.py
cd ../frontend
npm test
npm run build
```

[GitHub Actions workflow](.github/workflows/ci.yml) runs on pushes and pull requests
(and manual dispatch): Python3.13 backend install/tests/reference checks; Node24 npm ci,
frontend tests/build. Yahoo is disabled and no API keys are required. Its YAML passed
local checks; **it has not been pushed or run on GitHub in this stage**.
Tests used the matching temporary source/runtime copy; no live account orders were made.
Browser transport was unavailable, so visual verification remains outstanding. Existing
Starlette/httpx deprecation warning remains; Part4.3 was not started.

## Final Part4.2 requirements review
The [22-item audit](docs/part-4.2-review.md) records implementation, evidence and explicit
unmet requirements. Final rerun: **204 backend tests**, **42 frontend tests**, production
build passed. A disposable full provider-shaped observation→completed candle→SMA→signal→
order/fill trace verified16shares@125, cash8000/equity10000. A saved-data backup backtest
used327candles,11fills/5completed trades, ending equity9996.525; repeated results matched
without account/market mutations. These are verification outcomes, not expected returns.

Browser inspection is still blocked by unavailable automation; hosted Part4.2 CI has not
run and the workflow/code remain uncommitted. The submitted commit and accessible30–60s
Part4.2 video remain pending. No new report or commit was created; an older report.md was
left untouched. Simulation/source security checks and exact evidence links are in the
audit. Part4.3 remains out of scope.

## Chart-side paper trading
On desktop, the main workstation now places candles/SMA/volume beside a sticky
**SIMULATED account + manual order ticket**. Cash, equity, P/L, selected-symbol holdings,
displayed reference/feed timestamp and estimated order cost/proceeds are visible together.
“Use displayed price” still requires an explicit click; prices are not silently updated.
Positions, orders and fills sit directly below this workspace. Market/candle metadata is
expandable; replay, automatic strategy controls and backtesting follow below. Smaller
screens stack the ticket after the chart. Estimates are presentation only; the backend
remains the authority for validation/accounting. Replay continues to disable order entry.
Latest layout verification:43 frontend tests/build passed; browser automation unavailable.

## Collapsible dashboard panels
Click a panel's title row to Hide/Show it. The chart, status cards, simulated account,
positions/activity, observations, replay, automatic strategy and backtest windows are
collapsible; positions/orders/fills can also collapse individually. Main panels start
open, and the existing market metadata disclosure stays initially closed. Hiding preserves
forms/chart state and background updates; it does not pause replay or disable automatic
trading. Strategy ON/OFF remains in its collapsed header. Open/closed preferences are stored in this browser and restored
across reloads. Latest checks:204backend/45frontend tests and build passed; browser access
remains unavailable.

## Remembered panel layout
Each panel and nested history/details section remembers its open/closed state across
refreshes using browser localStorage. Keys are stable when the symbol, interval or data
mode changes. Preferences apply to this browser and site address; clearing site data
resets them. If storage is blocked/full, toggling still works for the session. Collapsed
status cards now shrink to header bars rather than stretching to neighboring open cards.
Latest checks:204 backend tests,48 frontend tests and production build passed.

Market selection controls (Live/Replay, stock symbol and1m/5m/15m interval) now live inside the chart panel, above the instrument/zoom toolbar.

## Recover Yahoo streaming from the app
Click **Reconnect Yahoo feed** beside the market chart's mode/stock/interval selectors.
The backend must already be running. This restarts the single shared Yahoo session and
completion task, without changing account/strategy settings, subscriptions or saved data.
Repeated requests within3seconds share the same restart. The control is disabled during
replay and while its request is pending. A connecting response is not a live-data claim;
feed freshness/status update when actual observations arrive.

If persistence previously failed, the backend checks the database write lock before
resuming; a remaining storage problem returns a visible error instead of discarding data.
This explicitly enables a startup-disabled feed for the current process; environment
settings still govern the next backend startup. No browser control can restart a stopped
backend process. Latest checks:208backend/49frontend tests and build passed; actual local
API/provider recovery verified separately from mocked tests.

## November16 verification evidence
Latest rerun: **208 backend tests**, **49 frontend tests**, production build and
independent SMA checks passed. **17 actual browser workflow checks passed** in a separate,
clearly labeled synthetic fixture instance: chart/volume/SMAs/markers, manual and automatic
paper trades, accounting, backtest results/equity/history, errors, replay isolation and
refresh persistence. Your main account was not used for test orders.
See [the current verification record](docs/testing-2026-11-16.md) and
[repeatable browser cases](docs/browser-test-cases.md). Raw logs/JUnit/reference values,
screenshots and result JSON are under docs/evidence/2026-11-16/. GitHub-hosted CI has
not run for this local version; commit/push awaits the user's later instruction.
report.md was not changed. No Part4.3 implementation was added.


## Confirmed chart signals — November 18, 2026

BUY/SELL arrows and actual FILL circles have independent visibility controls and signal details. Saved backtests can display their exact recorded candle/signal/fill snapshot in a separate chart.
See [marker behavior and verification](docs/chart-signals.md).
