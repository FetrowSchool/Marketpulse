# Implementation evidence log

## Entry template
- Entry ID / date / author:
- Stage and goal:
- User prompt or concise faithful summary (link original where available):
- Coding tool / editor / known model (unknown if unavailable):
- Files created or changed:
- Implementation summary:
- Design decisions and alternatives:
- Validation commands / environment:
- Actual results (counts, exit codes, failures; no inferred passes):
- Failure, diagnosis, corrective action, recheck:
- Limitations / unresolved items:
- Human review / supporting artifacts:

## MP-001 — 2026-11-08 — Part 4.1 foundation
- Prompt: build MarketPulse with Vue/Vite and Python/FastAPI/SQLite; preserve raw,
  constructed, and provider candle observations and revisions; implement health,
  honest empty dashboard, documentation, and tests. No Yahoo integration, indicators,
  trading, AI/audio, or report.md.
- Tool: Codex desktop coding agent; GPT-6 family indicated by environment, exact
  deployed variant unavailable. Shell and web tools; no subagents.
- Generated files: README.md, AGENTS.md, AI-USE.md, design.md, .gitignore;
  backend application/config/routes/services/schema/tests/dependency files;
  frontend application/styles/config/tests/dependency files; docs architecture,
  database, and evidence log. Repository file inventory can be checked with `git status`.
- Decisions: one append-only observations table; separate observation versus candle
  identity; canonical UTC; transactionally allocated revisions; content-based duplicate
  suppression; ingest ID order for deterministic replay; disabled UI controls and
  no invented market data. No deployment requested for this local university project.
- Reference checks: official Vite/Vue setup and FastAPI testing/lifespan/CORS docs.
  https://vite.dev/guide/ ; https://vuejs.org/guide/quick-start ;
  https://fastapi.tiangolo.com/tutorial/testing/ ;
  https://fastapi.tiangolo.com/advanced/testing-events/ ;
  https://fastapi.tiangolo.com/tutorial/cors/ .
- Initial failure: sandbox Python dependency download could not resolve pypi.org;
  rerun requested with network permission. npm installation also subject to network checks.
- Validation results: completed; measured outcomes follow below.
- Limits: no provider feed, real chart library, WebSocket transport, timed replay UI,
  ingestion HTTP endpoint, or future-stage functionality. Synthetic tests are labeled
  simulated and are never displayed in the dashboard.

### Validation and corrective actions
- Environment: Python 3.13.15, Node 24.20.0, npm 11.19.0; SQLite is Python's bundled SQLite.
- Dependency download: initial pip and npm attempts failed with sandbox DNS errors.
  Network-authorized retries installed successfully. Exact Python environment is in
  `backend/requirements-lock.txt`; frontend uses `frontend/package-lock.json`.
- Initial workspace backend command: `cd backend && ../.venv/bin/python -m pytest -q`:
  **23 passed**, exit 0, with one StarletteDeprecationWarning about httpx TestClient.
- Initial workspace frontend command: `cd frontend && npm test && npm run build`:
  **3 tests passed**, production build succeeded, exit 0.
- npm audit initially reported 8 vulnerabilities (6 moderate, 2 critical).
  Updated Vitest from 3.2.x to 5.1.0 and reinstalled Vue Test Utils 2.4.6.
  `npm audit fix` then exited 1 with **4 moderate** advisories remaining in
  glob/minimatch and dependent js-beautify/editorconfig. No critical advisories remained.
  These are development/test dependencies; no forced transitive major overrides were applied.
- Preview attempts in the workspace stalled or failed with filesystem timeouts
  reading Vite runtime files and Python virtual-environment files. Interrupted owned
  attempts; an early browser navigation returned connection refused. This did not
  invalidate the completed initial tests, but required independent runtime verification.
- Copied application source, tests, config, and lockfiles to
  `/private/tmp/marketpulse-verification`, excluding dependencies, generated data,
  and caches, and installed the same dependencies there. No source edits were made
  in the verification copy. Final checks:
  - `cd /private/tmp/marketpulse-verification/frontend && npm test && npm run build`:
    **3 passed** under Vitest 5.1.0; Vite 7.3.7 production build succeeded, exit 0.
  - `cd /private/tmp/marketpulse-verification/backend && ../.venv/bin/python -m pytest -q`:
    **23 passed, 1 warning**, exit 0. The warning is the same Starlette/httpx deprecation.
  - Temporary Vite startup first failed with sandbox bind EPERM; network-authorized
    startup succeeded on 127.0.0.1:5173. Temporary Uvicorn initialized SQLite and
    started successfully on 127.0.0.1:8000.
  - Authorized HTTP request to the frontend returned **200**. Through Vite's proxy,
    `/api/health` returned `{"status":"ok","database":"connected","version":"0.1.0"}`.
  - Codex in-app browser accessibility and screenshot inspection verified the dark
    desktop dashboard, backend available/database connected, no market data state,
    and disabled symbol/replay controls. No mobile browser screenshot was captured;
    responsive behavior is implemented in CSS but only desktop browser QA was performed.
- No market provider connection was used. No deployment or report.md was created.
- Remaining limitations: development dependency advisories, the test-client warning,
  and workspace filesystem timeouts. Future data feed/chart/replay transport work
  remains out of scope for this foundation.
- Source consistency: recursive diff of backend app/tests and frontend src/tests,
  plus comparisons of frontend package.json, package-lock.json, and vite.config.js,
  exited 0 with no differences between workspace and verification copy.
- Teardown: stopped the owned temporary Vite and Uvicorn processes and closed the
  temporary browser tab after verification; startup commands remain in README.

### Created file inventory
```text
.gitignore
AGENTS.md
AI-USE.md
README.md
design.md
backend/.env.example
backend/requirements.txt
backend/requirements-lock.txt
backend/pytest.ini
backend/app/__init__.py
backend/app/config.py
backend/app/main.py
backend/app/schema.sql
backend/app/routes/__init__.py
backend/app/routes/health.py
backend/app/services/__init__.py
backend/app/services/database.py
backend/tests/conftest.py
backend/tests/test_database.py
backend/tests/test_health.py
frontend/index.html
frontend/package.json
frontend/package-lock.json
frontend/vite.config.js
frontend/src/main.js
frontend/src/App.vue
frontend/src/style.css
frontend/tests/App.test.js
docs/architecture.md
docs/database.md
docs/evidence-log.md
```


## MP-002 — 2026-11-08 — Yahoo streaming and backend observation processing
- Prompt summary: inspect the project and follow AGENTS.md; implement yfinance
  streaming for AAPL/MSFT/NVDA/SPY with configurable active symbol, normalization,
  source-time candles, feed freshness, persistence, validated market REST endpoints,
  deterministic tests and a separate real Yahoo attempt. No historical polling
  substitution, frontend charting, broadcasting, trading, indicators, AI/audio, or report.md.
- Tools: same Codex desktop agent (GPT-6 family indicated by environment, exact
  deployed variant unavailable); shell and primary-source web lookups. No subagents,
  additional editor, browser changes, credentials, or model switches.
- Inspected existing AGENTS.md, services, schema, configuration, routes, tests,
  README/design/database/architecture documentation before changes. Updated the
  AGENTS scope restriction to match the user's explicit new provider authorization.
- Initially yfinance was not installed in the verification environment. Installed
  **1.8.0**, inspected its AsyncWebSocket implementation and PricingData fields,
  then pinned that exact package and regenerated the Python environment lock.
  The project virtual-environment dependency installation also completed successfully.
- Primary references: yfinance streaming API at
  https://ranaroussi.github.io/yfinance/reference/yfinance.websocket.html ; source at
  https://github.com/ranaroussi/yfinance/blob/main/yfinance/live.py ; schema at
  https://github.com/ranaroussi/yfinance/blob/main/yfinance/pricing.proto .
- Decisions: public yfinance subscribe/close with an isolated version-pinned private
  receive/decode seam, because public listen owns a fixed-delay retry loop and can
  swallow failures. MarketPulse owns capped exponential reconnects and cancellation.
  There is no historical-data polling fallback or application market WebSocket server.
- Normalization: original decoded provider dictionary retained; source time uses
  epoch milliseconds and canonical UTC; receipt captured before database waiting;
  missing OHLCV stays missing. Symbol id is not an event identity. Canonical full
  decoded-payload hashes deduplicate retransmissions without collapsing different
  messages at the same timestamp. Provider event identity is explicitly unavailable.
- Candles: UTC source-time quote buckets, effective latest raw revisions, ingest-ID
  tie-break, preserved raw-ID lineage, incomplete until end, timer completion, late
  historical corrections, and no completion regression after clock rollback.
  No gaps are filled and no day-volume/last-size conversion is invented.
- Persistence: existing append-only schema retained, source-time index added
  idempotently; raw quote plus resulting candle commit/rollback together. No schema
  migration or destructive initialization was needed. Database failures stop the feed
  and are visible separately from connection failures.
- Status: separate source age and valid-observation receipt age, source high-water,
  transport/attempt/error counters, conservative delayed/unverified provenance. Clock
  windows qualify regular-session status, while holidays, early closes and overnight
  calendars remain unverified. No undocumented market_hours mapping was assumed.

### Verification and actual failures
- Environment: Python 3.13.15, Node 24.20.0, npm 11.19.0, yfinance 1.8.0.
- Offline tests first passed **71 tests**. Added further coverage for installed
  protobuf decode, timeout cleanup, captured-provider replay, completion monotonicity,
  all supported symbols, and enabled FastAPI lifespan with an injected synthetic stream.
- An intermediate pytest invocation started before its source-copy command finished;
  it failed collection with four ImportErrors while market_repository.py was partially
  copied. Corrected the validation sequencing, waited for copy completion, and reran.
  No application import failure remained. A subsequent run passed 79 tests before
  the final enabled-lifespan regression was added.
- Final command in `/private/tmp/marketpulse-verification/backend`:
  `../.venv/bin/python -m pytest -q` → **80 passed, 1 warning in 1.13s**, exit 0.
  Warning: Starlette TestClient's existing httpx deprecation; not a failed test.
- Frontend regression in `/private/tmp/marketpulse-verification/frontend`:
  `npm test && npm run build` → **3 passed**, Vitest 5.1.0; Vite 7.3.7 production
  build succeeded, exit 0. No frontend source/config changes were made this stage.
- The original project environment again stalled reading files. Its requested
  `cd backend && ../.venv/bin/python -m pytest -q` attempt produced no test result
  before interruption. Final validation used an isolated source copy with the same
  locked dependencies; no pass is claimed for the stalled workspace attempt.
- Recursive source comparisons were used to verify copied application/tests match
  the workspace; final comparison outcome is appended after this entry.

### Real-provider evidence (separate from tests)
The probe used a temporary SQLite database, a 30-second window, AAPL, and at most
two connection attempts. Real network access was explicitly requested by the user.
1. Sandboxed attempt: DNS failure; zero subscriptions/observations. Evidence:
   `docs/evidence/yahoo-sandbox-failure-2026-11-08.json`.
2. Network-authorized attempt: SSLCertVerificationError (Python local issuer trust
   store); zero subscriptions/observations. Evidence:
   `docs/evidence/yahoo-tls-failure-2026-11-08.json`.
3. Network-authorized retry with SSL_CERT_FILE selecting the installed certifi CA
   bundle: **one successful subscription, one actual Yahoo AAPL observation, zero
   rejected messages**, raw row persisted and local candle revision 1 constructed;
   timer appended complete revision 2. No certificate verification was disabled.
   Source timestamp: `2026-11-09T02:48:48.000000Z`; backend receipt:
   `2026-11-09T02:48:50.131759Z`. This was November 8, 2026 at approximately
   9:48 p.m. America/New_York, outside regular trading hours. Evidence:
   `docs/evidence/yahoo-stream-2026-11-08.json`.
- These JSON files preserve the actual probe output at capture time. The early probe
  field `successful_live_observations_verified=true` means an observation really
  arrived over the provider stream, **not** that exchange real-time entitlement or
  an active trading session was verified. That capture separately records
  `realtime_entitlement_verified=false`, `data_mode=delayed`, and status delayed.
  The probe CLI was subsequently clarified to separate provider observation verification
  from fresh-live-data verification. Status session wording was also clarified to
  regular-session weekend closure rather than assuming all overnight feeds are closed.
- Preserved the decoded quote in `backend/tests/fixtures/yahoo_recorded_quote.json`.
  Its offline replay explicitly uses data_mode recorded. Synthetic test messages are
  documented as simulated, and no offline test calls Yahoo. The real-provider probe
  is a separate script, not a pytest dependency. No invented stock prices are used.

### Created or changed files
- backend/app/services/normalization.py (new)
- backend/app/services/candles.py (new)
- backend/app/services/market_repository.py (new)
- backend/app/services/yahoo_stream.py (new)
- backend/app/services/market_data.py (new)
- backend/app/routes/market.py (new)
- backend/scripts/verify_yahoo.py (new)
- backend/tests/test_market_processing.py (new)
- backend/tests/test_market_service.py (new)
- backend/tests/test_market_api.py (new)
- backend/tests/fixtures/yahoo_recorded_quote.json (new)
- docs/evidence/yahoo-stream-2026-11-08.json (new)
- docs/evidence/yahoo-sandbox-failure-2026-11-08.json (new)
- docs/evidence/yahoo-tls-failure-2026-11-08.json (new)
- backend/app/services/database.py; backend/app/schema.sql; backend/app/config.py;
  backend/app/main.py; backend/tests/conftest.py; backend/.env.example;
  backend/requirements.txt; backend/requirements-lock.txt (updated)
- README.md; AGENTS.md; design.md; docs/architecture.md; docs/database.md;
  docs/evidence-log.md; AI-USE.md (updated)

### Remaining limits and review
- Only AAPL was exercised against the actual provider. Other supported symbols are
  covered offline; no guarantee of provider uptime, licensing/entitlement, or full tape.
- Source identity is a content fingerprint because Yahoo supplies no unique event
  sequence; identical separate events and undocumented corrections are ambiguous.
- Candle OHLC describes received quotes only; volume remains NULL. There is no gap
  recovery, full exchange calendar, split/adjustment policy, or provider-candle ingestion.
- Adapter private seams require reinspection before a yfinance upgrade. The source-mode
  confirmation option must never be enabled merely because a socket connects.
- Frontend feed labels remain static placeholders; only health is wired there. Use
  `/api/market/status` for actual feed status. No chart or broadcast code was added.
- Existing frontend development dependency advisories from MP-001 and the backend
  test-client deprecation remain; no newly invented audit or remediation claim is made.
- No report.md, later-stage features, deployment, or trading actions were created.
- Final source consistency check: recursive comparisons of backend app, tests, and
  scripts (excluding __pycache__), plus requirements and requirements-lock files,
  exited 0 with no differences between workspace and verification copy.
- The stalled workspace pytest process was interrupted during pytest module imports,
  before collection (exit 130); it was not counted as a test pass or application failure.
  All real-provider probes exited after cleanup, and no verification server was left running.

## MP-003 — 2026-11-08 — FastAPI-to-Vue WebSocket integration
- Prompt summary: inspect and preserve the existing implementation; broadcast committed
  Yahoo observations/candle revisions at /ws/market, support multiple clients and validated
  symbol selection, distinguish browser and Yahoo connectivity, preserve last-known data
  during failures, add deterministic tests and attempt real-provider full-pipeline verification.
  No candlestick visualization or later-stage features.
- Tools/models: same Codex desktop agent (exact deployed model variant unavailable), shell
  execution, primary-source web lookup, Codex in-app browser. No subagents/model switch,
  additional editors, AI APIs, credentials, or chart-generation tools were used.
- Inspected AGENTS.md, app factory, persistence, provider lifecycle, normalizer/candle
  design, database documentation, Vue dashboard, Vite config, and existing tests before edits.
  The user's explicit scope now authorizes broadcasting; AGENTS.md was updated accordingly.
- References checked: FastAPI WebSockets and testing documentation,
  https://fastapi.tiangolo.com/advanced/websockets/ and
  https://fastapi.tiangolo.com/advanced/testing-websockets/ ; browser WebSocket semantics,
  https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications .

### Implementation and decisions
- One yfinance socket per application process subscribes to the four supported stocks once
  per provider session. Browser subscriptions are independent backend filters, never Yahoo
  connection creation. This eagerly captures the small universe; active_symbol remains the
  default API/UI selection. Source/receipt times and freshness are tracked independently
  for each stock; connection/retry counters remain shared.
- Repository post-commit hooks publish serialized committed rows, including timer completion.
  Raw/candle rollback emits no events, raw duplicates emit no new record broadcasts, and
  snapshots do not write observations. SQLite schema and immutable-record policies remain.
- MarketSocketHub schedules fanout from persistence threads onto the event loop. Separate
  128-frame queues/senders keep slow/disconnected clients from blocking ingestion. Origin
  checking is explicit because HTTP CORS does not protect WebSocket handshakes.
- JSON envelope schema version 1 supports connection_status, market_observation,
  candle_update, candle_completed, feed_status and error, retaining row identity/revision,
  original timestamps, interval/completion, source age, provenance and feed status.
  Full protocol/limits/close semantics are documented in docs/websockets.md.
- Increasing per-client request IDs guard symbol switches; queued old subscriptions are
  discarded and the browser rejects wrong-symbol/old-generation frames. Reconnection
  restores latest persisted snapshots, not an automatic history replay.
- Reusable browser transport uses same-origin ws/wss, 10-second connect/idle checks,
  capped 0.5–15 second exponential waits and eight retries per unstable run. A stable
  open connection resets the budget after 10 seconds; manual reconnect is available.
- Vue displays selected stock, last price, original source and backend receipt timestamps,
  increasing source age, local candle revision/completion metadata, backend health, and
  separate browser/Yahoo transport states. Late prices cannot regress latest source time.
  Prices remain explicitly last known/noncurrent during delayed/stale/disconnected states.
  Recorded/simulated provenance remains labeled. No USD/currency or interval volume is guessed.

### Automated tests and corrective actions
- All automated connections are mocked/in-process. Synthetic quotes in the WebSocket/UI
  tests are test-only; the existing recorded-provider fixture is replayed offline. Tests
  never open Yahoo connections.
- Initial backend run: **88 passed, 5 failed**. Five new WebSocket tests failed during
  Starlette TestClient context teardown with CancelledError. Session cleanup awaited tasks
  under an already-cancelled AnyIO scope. Corrective action: cancellation-shield the
  cleanup, cancel/await reader/writer tasks, then remove/close the client. The 13-test
  WebSocket subset passed after the fix. Additional tests checked a departing client's
  isolation and independent per-symbol source ages; binary frames now get safe errors.
- Final backend command in /private/tmp/marketpulse-verification/backend:
  `../.venv/bin/python -m pytest -q` → **95 passed, 1 warning in 1.23s**, exit 0.
  Warning remains the existing Starlette/httpx TestClient deprecation.
- Frontend command in /private/tmp/marketpulse-verification/frontend:
  `npm test && npm run build` → **8 passed** across two test files; production build
  succeeded, exit 0. Tests cover generation filtering, all supported record/status/error
  handling, capped retries/exhaustion, timeouts/cleanup, feed rendering, stale/last-known
  labeling, distinct timestamps, symbol switching, late prices, and preserved health behavior.
- Verification used the same isolated working copy strategy as MP-002 because the project
  virtual-environment file reads have stalled. Source was copied completely before checks;
  recursive comparisons of backend app/tests and frontend src/tests/config are recorded below.
  No successful workspace-virtualenv test execution is invented for this stage.

### Actual provider and browser verification
- Started a local Uvicorn server with a separate SQLite file at
  /private/tmp/marketpulse-ws-stage-live.sqlite3, the existing certifi trust bundle, TLS
  verification enabled, and real Yahoo streaming. Started the Vue/Vite dev server.
  This runtime used no synthetic or recorded test fixture injection.
- Dashboard readiness check returned HTTP **200**.
- Ran `../.venv/bin/python scripts/verify_market_socket.py --url
  ws://127.0.0.1:5173/ws/market --seconds 30 --output /private/tmp/marketpulse-ws-pipeline.json`
  with authorized network access, separate from pytest.
- Actual result: **provider_to_sqlite_to_websocket_verified**. Received two connection
  control messages, 18 status messages, one AAPL market_observation and one candle_update.
  The quote was a new committed event (not a snapshot); SQLite observation ID 33 matched
  all record fields returned over the WebSocket, checked through the REST database read.
- Actual source timestamp: **2026-11-09T04:23:10.000000Z**; backend receipt:
  **2026-11-09T04:23:11.680793Z**; WebSocket enqueue:
  **2026-11-09T04:23:11.684872Z**. This was November 8 at about 11:23 p.m.
  America/New_York. Full untouched capture is
  docs/evidence/market-websocket-pipeline-2026-11-08.json.
- Source provenance was delayed/unverified, provider transport connected, one successful
  Yahoo connection, and regular/overnight session qualification remained explicit. This
  proves the actual provider-to-browser-facing transport path, not exchange entitlement
  or active regular trading. Candle volume remained NULL.
- Codex in-app browser inspected the Vue dashboard at the same Vite origin. It showed
  browser socket Connected and Yahoo Delayed, then an actual AAPL price (344.85) with
  source **2026-11-09T04:23:30.000000Z**, receipt **2026-11-09T04:23:31.708842Z**,
  source age increasing, candle metadata `1m · incomplete · r2`, and LAST KNOWN · NOT
  CURRENT. These were real observations arriving during inspection, not invented prices.
  The chart remained a placeholder. Screenshot/accessibility inspection confirmed rendering.
- Real new-event WebSocket push and actual Vue receipt were verified; automated multi-client,
  switching, shutdown and network-failure scenarios remained mocked. No successful live
  market entitlement or unperformed browser switching/failure check is claimed.

### Files created/changed
- New: backend/app/services/market_socket.py; backend/app/routes/market_socket.py;
  backend/tests/test_market_socket.py; backend/scripts/verify_market_socket.py;
  frontend/src/services/marketSocket.js; frontend/tests/marketSocket.test.js;
  frontend/tests/socketFixture.js; docs/websockets.md;
  docs/evidence/market-websocket-pipeline-2026-11-08.json.
- Updated: backend/app/main.py; backend/app/services/market_data.py;
  backend/app/services/market_repository.py; backend/app/services/yahoo_stream.py;
  backend/tests/test_market_service.py; backend/requirements.txt (explicit AnyIO dependency,
  already present in the locked environment); frontend/src/App.vue; frontend/src/style.css;
  frontend/vite.config.js; frontend/tests/App.test.js; README.md; AGENTS.md; design.md;
  docs/architecture.md; docs/database.md; docs/evidence-log.md; AI-USE.md.

### Remaining limits
- In-memory fanout is single-process. Use one Uvicorn worker; no distributed broker,
  authenticated public hosting, or exactly-once WebSocket/replay protocol was added.
- Disconnection may skip intermediate updates; latest snapshots restore state and REST
  preserves history. Consumers must use IDs/source time/revision, not assume wire order.
- Existing yfinance private-seam/version restriction, missing full exchange calendars,
  content-derived provider identity ambiguity, quote-only candles and unavailable volume remain.
- Browser reconnection exhaustion requires manual retry or reload. Provider retry exhaustion
  retains the existing backend-restart policy. No fake quote is generated for either failure.
- No chart visualization, trading, indicators, AI/audio, deployment, or report.md was created.
- Final source comparison exited 0 with no differences for backend app/tests and frontend
  src/tests/Vite configuration between workspace and the tested verification copy.
- Verification servers were stopped after inspection. The separate live verification database
  remains outside the project in /private/tmp; no runtime database or secrets were added to Git.

## MP-004 — 2026-11-08–09 — Visual market workstation
- Prompt summary: inspect/preserve MarketPulse; add reusable TradingView Lightweight
  Charts candlesticks and aligned volume, source-backed live/revision handling, historical
  initialization without races, professional responsive information panels, tests, actual
  browser inspection and documentation. No random/generated market data, simulated trading,
  indicators, AI/audio or functioning replay controls.
- Tools/model: continued with the same Codex desktop agent (exact variant unavailable),
  shell, primary TradingView documentation and Codex in-app browser. No subagents,
  additional editors/model switches, credentials, image generation or hosting deployment.
- Inspected AGENTS.md, Vue dashboard/socket service/tests/styles, candle REST routes and
  persistence before editing. Existing database/identity documentation informed the merge
  strategy. AGENTS scope now includes the user's explicitly authorized visualization.
- Consulted TradingView series/pane/attribution documentation and installed package metadata.
  Installed **lightweight-charts 5.2.1** (and fancy-canvas 2.1.0) and updated the npm lock.
  npm installation reported **4 moderate advisories** in the existing dependency tree;
  no forced package upgrades or invented clean-audit result is claimed.

### Design decisions and implementation
- Reusable MarketChart.vue owns native canvas/series lifecycle, axes, UTC time, two aligned
  panes, loading/empty/error states, attribution and ResizeObserver cleanup. The renderer
  adapts backend candle rows to actual CandlestickSeries and HistogramSeries APIs.
- Vue never builds OHLC from raw prices. Raw observations update the information panel;
  committed backend candle events update chart OHLC/completion/revision. SQLite remains
  authoritative and append-only. No candle or price is synthesized to fill the display.
- One stable identity includes symbol/source/type/mode/producer ID/interval/opening. Only
  higher revisions within that identity replace earlier state. Different producer branches
  at one time slot are not summed; latest committed ID selects the displayed row.
- HTTP history and WebSocket events share one revision book. Selection aborts/invalidates
  previous fetch generations, clearing old context; stale responses cannot overwrite new
  live revisions. Subscription acknowledgments trigger catch-up history loads. The visible
  window is bounded to 1000 openings, and rows are sorted in UTC before plotting.
- Current/latest bars use incremental update; existing historical revisions use the
  library's supported update(bar,true). New older time points/window removals use sorted
  setData with visible time range preservation. Fitting is initial/manual, not every tick.
- A histogram bar requires reliable interval volume metadata and a finite nonnegative
  value. Current Yahoo quote candles have NULL volume; their pane contains whitespace
  points, not fake zero bars, and a visible unavailable explanation. No day-volume or
  last-size conversion is performed.
- Backend symbols metadata now includes active_interval so the UI starts on the configured
  interval. Other supported intervals can show saved history, clearly marked saved-only
  when the backend is constructing a different interval. No resampling/provider polling
  or extra Yahoo connections were added.
- The responsive workstation shows latest quote or an explicitly labeled saved candle
  close, supplied provider change, UTC source/receipt, increasing age, provenance,
  completion/revision, and separate browser/provider/health states. Receipt values are
  cached independently so late updates remain available through disconnection. Change
  numbers are rounded for presentation only; original provider values are preserved.

### Automated checks (mocked/offline)
- Final backend command, in /private/tmp/marketpulse-verification/backend:
  `../.venv/bin/python -m pytest -q` → **95 passed, 1 warning in 1.16s**, exit 0.
  The warning remains the existing Starlette/httpx TestClient deprecation.
- Final frontend command, in /private/tmp/marketpulse-verification/frontend:
  `npm test && npm run build` → **21 tests passed** in five test files (591ms),
  production Vite build succeeded (370ms), exit 0.
- Tests exercise chart construction/panes/initial sizing/resize, real series adapter
  calls through mocks, historical loads, live-before-HTTP races, ignored stale/duplicate
  revisions, completion, supported older-point updates, unseen late insertion,
  symbol/interval isolation, missing/reliable volume contracts, recorded-mode display,
  source/receipt retention during failure, feed states and preserved existing behavior.
- Frontend data fixtures are explicitly synthetic and test-only, including recorded-mode
  rendering cases. Backend's existing captured-provider replay remains an offline test.
  None of the automated tests claims a real Yahoo connection.
- As in preceding stages, tests/build used the matching temporary source copy to avoid
  the known workspace runtime-file stalls. No unexecuted workspace test pass is claimed.
  Source/lock comparisons are recorded below after completion.

### Actual browser/provider checks and visible correction
- Started local Uvicorn with TLS verification enabled and the installed certifi CA bundle;
  reused the separate real-provider SQLite store from MP-003. No test fixture or random
  market data was injected. Started Vite; readiness returned HTTP 200.
- Actual browser initially showed **8 saved AAPL candles** and the original last-known
  source/receipt timestamps while awaiting a new provider observation. Subsequent real
  Yahoo traffic advanced to 10, 15, 17 and 18 saved/received candles during inspection,
  updating OHLC, provisional state/revision, latest price and source/receipt metadata.
- Explicit desktop QA used a temporary **1440×1000** viewport because the default side
  panel is narrow. Initial native-canvas inspection exposed excessive blank space until
  Fit view was clicked. Corrective action: initialize the chart with measured width/
  height, then resize explicitly via ResizeObserver, instead of fitting before async
  autoSize resolved. Reloaded and confirmed corrected automatic first-history fitting;
  added initial-size/resize regression assertions and reran frontend tests/build.
- Also made unavailable-volume label visible above the native canvas and formatted
  provider float change values readably, preserving original stored values. A deliberate
  late-receipt regression assertion verifies receipt retention through a socket failure.
- Browser controls: selected **MSFT**, verified title/price/OHLC/history switched without
  AAPL contamination; exercised Fit view; selected **5m**, observed zero saved candles
  and the explicit saved-only/live-backend-1m explanation; reloaded the configured AAPL
  1m view and verified live updates continued. No fake alternate-interval bars appeared.
- Before interruption, browser showed AAPL source **2026-11-09T04:56:37.000000Z**,
  receipt **2026-11-09T04:56:40.679724Z**, price 344.51, 17 candles, and incomplete
  current candle revision 3. Native chart inspection showed no chart error overlay;
  the browser console error query at that point returned an empty list.
- Saved the real REST candle response to **docs/evidence/market-chart-candles.json**.
  It contains **18 AAPL 1m candles**; latest row ID **1563**, opening
  **2026-11-09T04:57:00.000000Z**, source **2026-11-09T04:57:08.000000Z**, receipt
  **2026-11-09T04:57:10.661204Z**, revision **2**, complete **false**, close **344.53**,
  volume **null**. These are actual backend records, not fabricated examples.
- Stopped the backend deliberately. Browser displayed Reconnecting, Yahoo Disconnected,
  unavailable backend health and a visible retry control, while retaining **18 candles**,
  last price **344.53**, the source/receipt above and last-known/noncurrent labeling.
  The final quote arrived between the earlier screenshot and shutdown; data was retained,
  not frozen at an invented earlier price.
- Restarted the same backend/database. Without manual reconnect/reload, the browser
  returned to Connected, health Available and Yahoo Delayed, and advanced to **20 candles**
  with a genuine new quote **344.55**, source **2026-11-09T04:59:18.000000Z**, receipt
  **2026-11-09T04:59:20.802915Z**, raw observation ID **1696**. No data-generation or
  history-overwrite workaround was used. Real-time entitlement/session activity remains
  unverified; the data stayed delayed and LAST KNOWN · NOT CURRENT.
- Reset the temporary viewport to the normal approximately **630px** side-panel width.
  Inspected the responsive stacked chart/information layout and saved its screenshot;
  no phone-specific viewport or separate physical-device test is claimed. Closed the
  temporary browser tab after verification.
- Screenshots: **market-chart-desktop.png**, **market-chart-disconnected.png**,
  **market-chart-recovered.png**, **market-chart-responsive.png**, all under docs/evidence/.
  Native browser updates, controls and interruption/recovery were verified with real
  provider data. Exhaustive historical revision/race/volume-contract edge cases were
  tested with deterministic mocks, not claimed as separate live-provider events.

### Files created/changed
- New: frontend/src/components/MarketChart.vue;
  frontend/src/services/candleBook.js, candleHistory.js, chartRenderer.js;
  frontend/tests/chartFixture.js, candleHistory.test.js, chartRenderer.test.js,
  MarketChart.test.js; frontend/THIRD-PARTY-NOTICES.txt; docs/charting.md;
  the four screenshot PNGs and market-chart-candles.json under docs/evidence/.
- Updated: frontend/src/App.vue; frontend/src/style.css; frontend/package.json;
  frontend/package-lock.json; frontend/tests/App.test.js; backend/app/routes/market.py;
  backend/tests/test_market_api.py; README.md; AGENTS.md; design.md;
  docs/architecture.md; docs/websockets.md; docs/evidence-log.md; AI-USE.md.

### Remaining limits
- Current Yahoo quote candles have no reliable interval volume. The histogram capability
  is implemented, but no real-provider volume bars are claimed or fabricated.
- Only the configured backend interval is constructed live; other interval selections
  retrieve available saved rows only. The display window is 1000 openings, without
  unlimited backfill or functioning replay controls.
- Existing provider identity ambiguity, incomplete feed coverage/calendars, unverified
  entitlement and single-process fanout remain. Charting does not turn partial quote
  coverage into an exchange trade tape or implement adjustments/indicators/trading.
- Existing dependency advisories and test-client deprecation are recorded without
  inventing remediation. No report.md, simulated trading, AI or audio was added.
- Final recursive comparisons exited 0 with no differences for frontend src/tests,
  frontend package/lock files, and backend app/tests between workspace and verification
  copy (Python caches excluded). The final code matches the tested and browser-served copy.
- Verification browser tab was closed and its viewport override reset. Owned Uvicorn/Vite
  servers were stopped after verification; the real-provider runtime SQLite file remains
  outside the repository under /private/tmp. No database or secret was added to Git.


## 2026-11-09 — Persistence verification and deterministic recorded replay

### Request and scope
- User requested integrity review, exact deduplication, append-only revision/late-arrival
  handling, deterministic recorded replay, full Vue controls, tests and browser evidence.
- Read AGENTS.md, docs/database.md and existing persistence, ingestion, candle, live
  transport and chart implementation before changes. Kept existing functionality and
  schema columns. No trading, indicators, AI/audio, data fabrication or report.md.

### Implementation and decisions
- Database observations remain immutable with source/type/symbol/provider identity,
  canonical UTC source/receipt timestamps, payload, provenance, revision and candle
  identity/completion. Existing unique constraints/transactions/triggers enforce writes.
- Added only an idempotent symbol/source/receipt/id index; no table rebuild or destructive
  migration. Added mode=ro/query_only readers and CLI integrity audit. Integrity checks
  are SQLite structure/FKs, revision contiguity, canonical UTC and hash length; no claim
  of reconstituting provider wire payloads or recomputing hashes after REAL coercion.
- Exact normalized content within observation identity deduplicates independently of
  receipt time. Same-price distinct identity/time/source/symbol/payload remains distinct.
  Stable-identity changed content appends a revision; old-content redelivery returns its
  original row. Yahoo's decoded-payload identity limitations remain documented.
- Known deterministic simulated late-arrival example: 100 at 15:00:30, 110 at 15:01:10,
  late 95 at 15:00:20, then 100 at 15:00:40. Earlier minute ends O95/H100/L95/C100,
  complete revision 4; current 110 candle stays unchanged. Both playback runs yield
  identical final state; no original observation/revision is overwritten.
- Replay snapshots MAX(id) and rows in a read-only transaction. Default order receipt
  UTC then ID; optional commit order ID handles wall-clock rollback. Source time builds
  candles. Prior as-of baseline excludes future revisions. No ingestion or write callback
  runs during playback. Per-socket monotonic controller supports controls and speed.
- Vue closes live transport/history on entry, uses separate replay transport/generations
  and revision book, then reloads current history/resubscribes on return. Recorded
  presentation label never overwrites original stored provenance. Missing interval volume
  stays missing. Sessions are bounded to 10,000 rows, chart window 1,000 openings.

### Commands, failures and actual automated results
- Tested a source-matched copy at /private/tmp/marketpulse-verification because workspace
  dependency reads have stalled in earlier work. Commands there:
  `cd backend && ../.venv/bin/python -m pytest` and
  `cd frontend && npm test && npm run build`.
- Initial replay integration frontend run: 7 failed / 16 passed. A local computed
  variable named mode shadowed the new replay mode ref, causing a temporal-dead-zone
  error; renamed it provenance. Subsequent run: 23 tests passed and build passed.
- Expanded backend run: 114 passed / 1 failed. Existing feed-disconnection test could
  consume a pre-transition queued unavailable status. It now waits for the disconnected
  transition instead of assuming the next status was generated after mutation.
- Final backend: **115 passed, 1 warning, 2.62s**, Python 3.13.15 / pytest 9.2.0.
  Existing Starlette/httpx test-client deprecation warning remains; it is not a replay failure.
- Added range/order/symbol/retry frontend regression: first run 23 passed / 1 failed
  because native datetime-local normalizes zero seconds away. Corrected the assertion
  to the equivalent minute-precision aware timestamp; no production workaround needed.
- Final frontend: **24 passed, 7 files, 679ms**; Vite production build passed (see final
  build result). Fixtures are explicitly simulated mocked connections, not live evidence.
- Coverage includes exact/same-price duplicates, metadata/revisions, late buckets,
  source/receipt/commit ordering and ties, frozen snapshots, as-of baseline, pause/resume,
  restart/stop/speed, read-only enforcement, repeated initialization/restart, unavailable
  Yahoo, live inserts excluded from loaded replay, original timestamps/provenance,
  frontend volume contract, generation/symbol isolation and lost replay transport reload.

### Genuine saved-provider verification and browser observations
- Used SQLite backup API to copy the existing prior-stage actual-provider database to
  /private/tmp/marketpulse-replay-verification.sqlite3. It contained **2,138 saved rows**.
  No synthetic market rows were inserted for this demonstration. Runtime databases stay
  outside Git. FEED_ENABLED=false ensured no Yahoo session was needed or attempted.
- Pre/post audit: SQLite integrity ok, 0 FK violations, 0 revision-gap groups, 0 invalid
  audited metadata rows. Ordered-row SHA-256 before/after was identical:
  `d3ed33d6519ce1b8887d214b7258c22154f39143b8791251bb802e9b896df35c`.
  JSON serialization is documented in evidence/replay-integrity.json. Compared backup
  rows directly to original saved DB too: exact equality. Replay wrote no duplicate rows.
- In-app browser opened real Vue/FastAPI via Vite. Initial Live showed connected browser,
  unavailable Yahoo/feed_disabled, saved last-known values. Entered Replay with AAPL 1m:
  default 04:48:02–05:03:02 UTC, **76 events**, snapshot #2138, prior baseline visible.
- Play emitted raw/candle rows, paused at 2/76. A later independent inspection still
  showed paused 2/76 with unchanged original timestamps/candle. Selected 100×, resumed;
  chart advanced through revisions and candle completion to **76/76 completed**, final
  record #2056 (constructed candle revision 2, close 344.33). The genuine saved data has
  delayed provenance; replay presentation was clearly recorded throughout.
- Restart began again from first rows/baseline; Stop reset to 0/76 and stopped. Symbol
  switch to MSFT loaded its independent **57-event** recording; returned to Live and
  observed browser Connected / Yahoo Unavailable with latest saved MSFT history.
  Re-entering Replay remained functional without Yahoo. No mixed-symbol candle was seen.
- Native date-time input `fill` timed out in browser automation; the visible field was
  inspected afterward. Manual browser time-range editing is **not claimed verified**.
  UTC range/order request serialization and server bounds are covered by deterministic
  automated tests. An ordering/load action was attempted, but arrival-order browser
  behavior is not claimed independently verified from the available UI evidence.
- Inspected rendered layout at normal ~630px and desktop 1440×1000. Chart, sidebar,
  controls, progress and labels were readable. Console warning/error inspection returned
  an empty list. Saved replay-paused.png, replay-completed.png and replay-live-restored.png
  under docs/evidence/. Reset viewport and closed temporary tab afterward.
- Current genuine Yahoo candles have **no reliable interval volume**, and browser showed
  the unavailable explanation. Reliable-volume rendering is verified with explicitly
  synthetic frontend fixtures only; no real-provider volume bars are claimed.
- A direct read-only repeat of the same genuine 76 records yielded byte-equivalent row
  lists on restart. No new live-provider verification was performed in this stage.

### Files and remaining limits
- New backend services/replay.py, routes/replay.py, scripts/verify_database.py and
  tests/test_replay.py; new frontend services/replaySocket.js, tests/replaySocket.test.js
  and tests/ReplayApp.test.js. Paths are under backend/app or frontend/src as appropriate.
- Updated backend app/main.py, services/database.py, schema.sql, tests/test_market_socket.py;
  frontend src/App.vue, src/style.css, components/MarketChart.vue; AGENTS.md, README.md,
  design.md, docs/database.md, architecture.md, charting.md, websockets.md, evidence-log.md,
  AI-USE.md; added docs/replay.md and four replay evidence artifacts.
- No seek or durable replay cursor; backend/browser transport loss requires explicit load
  and restart. Backend must remain available, Yahoo need not. Large selections require
  narrowing, with up to 1,000 chart openings/baseline identities. No complete trade tape,
  entitlement guarantee, calendar/gap repair or provider-candle ingestion was added.
- Final production build: Vite 7.3.7, **411ms**, 22 modules transformed; generated
  CSS 11.70kB and JS 266.37kB (before gzip). No new dependency installation was needed.
- Final recursive source comparisons exited 0 with no differences for backend app/tests
  (Python caches excluded) and frontend src/tests between workspace and verification copy.
  Owned Uvicorn/Vite verification processes were stopped; backend shutdown completed cleanly.


## 2026-11-09 — Final Part 4.1 requirements audit

### Request, inspection and scope
- User's attached final-audit instructions requested comparison against 18 Part 4.1
  requirements, fresh setup, provider-to-browser tracing, unavailable-feed tests,
  database/replay/browser checks, both suites, documentation and submission readiness.
- Inspected project instructions, source/service/router/schema/UI/chart/transport code,
  tests, scripts, dependencies, existing evidence and documentation. No Part 4.2 work.
- The full requirement/status comparison is docs/part-4.1-review.md. Volume is explicitly
  partial for real Yahoo interval data. Repository URL, submitted hash and video are
  missing; report.md remains intentionally absent. No commit was made.

### Revised approach and code
- Found a verification flaw: scripts/verify_market_socket.py counted subscription
  snapshots as provider observations, so saved history could produce a misleading
  successful-provider outcome. It also searched only the first 1,000 raw records.
- Revised the probe to separate snapshot_records, require new non-snapshot raw events,
  query the exact ID with after_id/limit=1 and expose unverified entitlement explicitly.
  Added tests/test_verification_probe.py with mocked snapshot-only and actual-event
  branches, including ID 2001. This corrects verification, not ingestion behavior.
- Historical evidence remains historical; prior captured non-snapshot rows are not
  invalidated solely because the old script could misclassify snapshots in other runs.

### Fresh setup and actual automated results
- Created /private/tmp/marketpulse-final-review from source only, excluding .git,
  .venv, node_modules, dist, caches, .env and runtime data. Workspace file reads stalled
  during copying; the copy completed before tests/startup. This is a fresh source-copy
  test, not a literal Git checkout: there is no HEAD commit in this project yet.
- Created a fresh venv with `python3 -m venv .venv`, installed
  `.venv/bin/python -m pip install -r backend/requirements.txt`, and ran `npm ci` from
  frontend/. Both installs succeeded. Python 3.13.15, Node 24.20.0, npm 11.19.0.
- `cd backend && ../.venv/bin/python -m pytest -ra`: **117 collected, 117 passed,
  0 failed, 0 skipped, 8.00s**. One existing Starlette/httpx deprecation warning.
- `cd frontend && npm test`: **24 tests, 24 passed, 0 failed, 0 skipped**, 7 files,
  770ms. `npm run build`: **passed**, Vite 7.3.7, 22 modules, 385ms.
- `pip check`: no broken requirements (with a sandbox cache-permission warning).
- Fresh npm ci succeeded but reported deprecated whatwg-encoding/glob and **4 moderate**
  transitive dev-dependency advisories. `npm audit --json` confirmed the
  js-beautify/editorconfig/glob/minimatch chain, exit 1. These advisories remain; no
  force update, zero-vulnerability claim or unrelated dependency churn was introduced.
- Defaults initialized an empty SQLite database and both documented dev servers started.
  The installed certifi CA bundle was selected for this machine; TLS was never disabled.
  HTTP health and Vite API/WebSocket proxies worked with no .env or credentials.

### New actual Yahoo-to-browser trace
- New real-provider attempt succeeded while regular clock-window status remained
  unverified. Feed provenance/status stayed delayed: realtime_entitlement_unverified.
  Actual receipt is verified; exchange real-time entitlement is not.
- Updated probe produced provider_to_sqlite_to_websocket_verified from a new raw event
  (ID 69) while keeping the initial stored snapshots in a separate evidence field.
  Capture: evidence/final-provider-pipeline.json.
- Independently monitored newly broadcast non-snapshot frames while reading the actual
  Vue DOM. Browser observation **#453 AAPL price351.43**, source
  **2026-11-09T19:09:56.000000Z**, receipt **2026-11-09T19:09:57.619056Z** matched SQLite
  and the captured WebSocket record exactly. Original payload and normalized metadata
  are retained in evidence/final-end-to-end-trace.json. Browser values are also in
  final-browser-observation.json; later ticks can appear in the screenshot because
  the actual feed continued running. No snapshot/replay was used as fresh-provider proof.
- Native chart showed new prices, evolving OHLC/revisions and provisional/complete
  candles. AAPL/NVDA symbol selection worked. Actual stream volume stayed unavailable;
  neither daily totals nor unsequenced sizes were converted to interval volume.

### Explicit simulated outage and recorded replay
- Restarted the same captured DB under a temporary external verification wrapper around
  YahooStream. A local marker caused receive/connect to raise OSError, while FastAPI and
  its market socket stayed running. Retry base/cap=2s, budget=3. This is simulated
  upstream failure, **not an actual Yahoo service outage**; no product fault endpoint added.
- Status samples: disconnected attempt1 → disconnected attempt2 → unavailable attempt3.
  See final-simulated-outage-status.json. Browser stayed Connected, backend Available,
  saved candles and raw #897 stayed visible, age increased **6s →23s** with unchanged
  observation/candle display (final-outage-browser.json and final-browser-outage.png).
- All **450 raw rows** and raw digest remained identical during failure. No fake raw
  events appeared (final-outage-integrity.json). Candle completion may legitimately
  append an elapsed-interval constructor revision, even without a new provider quote.
- Replay loaded **228 genuine saved AAPL events**, completed 228/228 at 100×, and
  Restart/Pause/Resume worked during upstream unavailability. Paused snapshot #907
  is shown in final-browser-replay.png. Stored delayed provenance stayed unchanged;
  presentation clearly read REPLAY · RECORDED.
- Intentionally restarted backend with FEED_ENABLED=false. Replay reported transport
  loss and preserved displayed data; explicit Load selection reset/reloaded the session.
  Play/Pause/Resume worked offline. Returning to Live restored saved candles and a
  connected browser/unavailable Yahoo; 5m selection showed saved-only/empty state.
- Vite logged expected ECONNREFUSED/ECONNRESET during deliberate backend restarts;
  backend/browser recovery was observed. These were intentional interruption effects,
  not omitted failures. Final browser console warn/error lookup returned [] separately.

### Database survival and deterministic replay
- Genuine captured DB contained **907 rows** after shutdown. Two repeated initializations
  preserved count and row SHA-256 exactly:
  `6ecf41c863d00057f9c21ca962eee0da6f27eff57976d4711deb689aed1e1855`.
- Integrity audit: ok, 0 foreign-key violations, 0 revision-gap groups, 0 invalid audited
  metadata rows. Two complete 228-row AAPL replay runs returned identical sequences
  and did not write records. See final-database-verification.json. Final audit CLI
  after browser verification again passed with 907 rows. No schema migration required.
- Synthetic regression suites verify identities, original metadata/UTC timestamps,
  exact duplicates/same-price distinctions, append-only multiple revisions, late
  source-time bucket changes, historical retrieval, snapshot bounds and replay controls.
  These deterministic offline tests are not presented as newly received provider data.

### Separate simulated volume capability check and browser limits
- Created a **different disposable database** with eight explicit simulated SPY candles,
  fixture metadata and known interval volume [100,250,125,400,300,150,500,200]. It never
  mixed with the genuine provider capture. The normalized schema's Yahoo-shaped source
  namespace was used for API compatibility; data_mode=simulated and fixture metadata
  explicitly establish that these are not provider observations.
- Native browser histogram displayed 8 bars with SIMULATED labels and the supplied
  values. Fit view worked. Replay showed 1 bar at 1×, then 8 bars and 8/8 complete at
  100×, retaining simulated original provenance under REPLAY · RECORDED presentation.
  Captures: final-simulated-volume-fixture.json, final-browser-simulated-volume.png,
  final-browser-volume-replay.png. This verifies renderer capability only; actual
  Yahoo interval-volume visualization remains unmet/unavailable.
- Inspected 1440×1000 desktop layout and the normal side-panel state, native charts,
  status/age/source/receipt labels, selection, empty history, feed outage, replay controls,
  transport-error/reload and mode switching. Native date-time editing was not retried
  after the preceding stage's automation timeout; range/order serialization remains
  covered by tests. No exhaustive device/accessibility claim.
- Reset viewport, closed temporary tab, and stopped all owned backend/Vite processes.
  Runtime databases/environments remain outside the repository. No credentials used.

### Files, documentation and readiness
- Code: updated backend/scripts/verify_market_socket.py; added
  backend/tests/test_verification_probe.py. No product architecture rewrite needed.
- Updated README.md, AGENTS.md, design.md, docs/architecture.md, docs/database.md,
  docs/evidence-log.md and AI-USE.md. Added docs/part-4.1-review.md and the final-* JSON/PNG
  artifacts referenced above. Future Part 4.2 extension points are design-only.
- Recursive comparisons of tested backend app/tests/scripts, frontend src/tests,
  package-lock.json and requirements.txt against workspace exited 0 with no differences
  (Python caches excluded). Tested code matches the delivered workspace.
- `git remote -v` returned no remote; `git rev-parse --verify HEAD` failed because no
  commit exists. No demonstration video was recorded/uploaded. Eventual report-only
  Canvas submission still needs those real links/hash. report.md intentionally absent.


## 2026-11-11 — Requested report creation
- User explicitly requested report.md, authorizing its creation after earlier deferral.
- Created the report from the November 9 review and retained evidence. Test counts,
  provider tracing, simulated outage/volume distinctions and limitations are attributed
  to that audit; no new test or browser execution is claimed for report authoring.
- Rechecked Git metadata: no configured remote and no HEAD commit. The report marks
  repository URL, submitted hash and demonstration-video link pending. No commit,
  video, publication or Part 4.2 work was performed.
- Supporting documentation links remain relative until a real repository URL/commit
  can provide accessible submission links. The report is clearly marked a draft.

## 2026-11-11 — Fresh streaming label refinement
- User requested Real-time unverified for fresh Yahoo streaming, preserving delayed/stale
  for older data. Inspected AGENTS, freshness logic, dashboard and existing tests first.
- Backend FeedStatus now emits real_time_unverified for fresh unconfirmed observations,
  including outside regular hours. Reason/session context is retained; confirmed fresh
  regular-window live state is unchanged. No schema/data-mode migration or row rewriting.
- Vue recognizes the new state, ages it locally into delayed/stale using source and
  receipt thresholds, and displays Real-time unverified in feed/price classification.
  Stored provenance is explicitly labeled separately in chart footer/candle details.
  Replay/simulated labels and disconnected/unavailable behavior remain distinct.
- Added backend regression for 15/16/120/121-second boundaries, independently old
  receipt, weekend context and unchanged provenance. Added frontend regression for
  fresh→delayed→stale, retained prices and disconnection without new observations.
- First frontend run: 24 passed / 1 failed. The new test advanced fake time beyond the
  socket's 10-second idle watchdog, so it correctly disconnected before delayed status.
  Corrected the fixture to send status heartbeats without refreshing source/receipt
  timestamps; this tests aging on a connected but quiet feed without disabling safeguards.
- Verification in source-matched /private/tmp/marketpulse-final-review:
  `cd backend && ../.venv/bin/python -m pytest`: **118 passed**, 2.48s, one existing
  Starlette/httpx deprecation warning. `cd frontend && npm test && npm run build`:
  **25 passed**, 7 files, 593ms; build passed (Vite 7.3.7).
- Applied source updates to running preview and restarted its backend with Yahoo enabled
  and TLS verification. Existing tab showed provider Connected, Real-time unverified,
  source age 3/8/13 seconds and outside regular trading context. Actual provider data,
  not a simulated UI fixture. Screenshot: evidence/real-time-unverified-label.png.
- Updated README/design/protocol/architecture/database documentation, report amendment
  and AI-USE. Earlier dated evidence remains historical. No commit or Part 4.2 work.

## 2026-11-11 — Live 5-minute and 15-minute support
- User requested live support for 5m/15m. Read project instructions/database identity
  documentation and inspected repository, service, completion, socket and Vue selection.
- MarketDataService now configures each symbol repository with 1m/5m/15m. Standalone
  repositories keep single-interval defaults for explicit isolated use. The production
  repository stores a raw observation once, rebuilds all affected source-time buckets
  and commits all revisions atomically. Failure in any interval rolls back everything.
- Duplicate raw delivery skips all interval writes; late quotes revise each affected
  historical bucket independently. Completion checks all intervals, and reconnect
  snapshots include each interval. Status/symbols expose live_intervals. Vue uses this
  capability to enable matching interval updates without saved-only warnings; old-server
  fallback remains. No extra Yahoo socket, schema change or full-history import.
- Added deterministic regressions: source-time 5m/15m aggregation with late observations,
  independent completion and restart deduplication; rollback on final 15m write; live
  WebSocket delivery/snapshots for all intervals with one raw record; Vue 5m/15m switching
  that ignores mismatched candle events. Existing regression baseline also passed.
- Final commands in source-matched /private/tmp/marketpulse-final-review:
  `cd backend && ../.venv/bin/python -m pytest`: **121 passed**, 2.59s, one existing
  Starlette/httpx warning. `cd frontend && npm test && npm run build`: **26 passed**,
  7 files, 725ms; production build passed, Vite 7.3.7, 426ms. No failing final tests.
- Restarted the running backend with TLS verification and Yahoo enabled. Initial AAPL
  selection was empty while awaiting its first new quote (other symbols had arrived).
  No sample prices were inserted to fill the gap. Actual AAPL source timestamp
  2026-11-11T21:35:53.000000Z then created 5m row #41675/opening21:35 and 15m row
  #41676/opening21:30. Their original rows/metadata are in evidence/live-all-intervals.json.
  The 15m bucket also includes available previously persisted quotes in its source window.
- Browser inspected actual AAPL 5m and 15m native charts, provisional flags, price values,
  honest age/feed status and absence of saved-only warnings. Screenshots:
  evidence/live-5m-candles.png and live-15m-candles.png. Left the user's tab on 5m.
  Upstream connection was active; after-hours AAPL was quiet and later aged to delayed
  (56.2s). This is interval streaming support, not a promise of constant quote updates.
- Did not wait a real 15-minute boundary in-browser: timer completion, late corrections
  and restart behavior were verified with deterministic simulated tests. Actual provider
  volume remains unavailable. Existing records stay unchanged, and old untouched buckets
  without saved 5m/15m rows are not bulk-backfilled.
- Updated backend services/market_repository.py, market_data.py, routes/market_socket.py,
  routes/market.py, .env.example; frontend src/App.vue; processing/socket/frontend tests;
  README, design, architecture/database/charting/socket docs, AGENTS, AI-USE and report
  amendment. No Part 4.2 work or commit. Existing server remains running for the user.

## 2026-11-11 — Automatic candle zoom and replay entry
- User first questioned inactive replay controls, then requested automatic zoom instead
  of repeated manual scrolling. Inspected chart renderer/component, dashboard/tests and
  instructions; confirmed installed Lightweight Charts setVisibleLogicalRange support.
- Added default Latest25 focus, 10/25/50/100 presets, Follow latest and Fit all. Recent
  focus uses actual row indices plus viewport padding, never invented candles. Following
  continues across updates/context changes; turning it off leaves manual navigation
  untouched on ordinary revisions. All-history/Fit all disables following. Shared price
  and volume panes use the same time range. Live/replay both use the reusable component.
- Added direct Open replay in the bottom Live-mode panel and explanatory copy instead
  of requiring discovery of the distant top mode selector. No replay backend rewrite.
- Regression tests cover recent-window bounds, incoming rows/revisions, disabled-follow
  viewport preservation, context/small-data reset, component forwarding, dashboard
  presets/fit-all and direct replay entry. Backend unchanged; no backend suite rerun for
  this frontend-only change (last backend result remains the prior 121-test run).
- A refinement initially used an inline `if` statement in a Vue change handler; compiler
  rejected it. That run had 2 failed suites / 18 executed tests passed. Replaced it with
  a named changeZoom handler; no failing code remains. Final source-matched temporary
  run: `cd frontend && npm test && npm run build`: **29 tests passed**, 7 files, 516ms;
  build passed, Vite7.3.7, 386ms, 22 modules. No dependency changes.
- Browser inspected actual native chart Latest10 zoom, follow checkbox and Fit all.
  New Open replay loaded a saved AAPL selection, Play at100x reached **76/76 completed**,
  snapshot#42757, final candle record#42743. This is genuine recorded-provider playback,
  not a new-live-provider claim. Screenshot: evidence/replay-working-with-zoom.png.
- Restored user's dashboard to Live/AAPL5m, Latest25, Follow latest enabled; three
  actual saved/received candles were visible without manual scrolling. Screenshot:
  evidence/automatic-candle-zoom.png. No page reload or chart error was needed after
  the corrected final build; the brief development compiler error was resolved.
- Updated frontend src/App.vue, style.css, components/MarketChart.vue,
  services/chartRenderer.js; tests/App.test.js, MarketChart.test.js, chartRenderer.test.js;
  README, design, docs/charting, report amendment, AI-USE and this log. Preserved stored
  data, provenance, replay isolation and backend functionality. No commit/Part4.2 work.

## 2026-11-11 — Requested GitHub repository and two-commit sequence
- User explicitly authorized a new repository named Marketpulse, an initial commit,
  then a report update containing the repository URL/initial commit hash, followed by
  a second commit without rewriting that recorded hash afterward.
- Created private repository https://github.com/FetrowSchool/Marketpulse using the
  authenticated GitHub CLI. The connector verified account identity; CLI was needed
  because the available connector has no repository-creation action.
- Reviewed 103 candidate files (~2.8MB): no ignored runtime/secret files or recognized
  credential patterns detected; all files were readable after a transient file-read
  cancellation on the first scan. SQLite databases, dependencies and virtual environments
  remain ignored. No new code changes or test reruns were needed for publication.
- The intended second commit changes report.md only, recording the first commit as the
  submitted implementation reference. The report is intentionally not updated again
  to point at the second commit. GitHub history supplies the final publication evidence.
