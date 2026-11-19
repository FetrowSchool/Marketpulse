# MarketPulse project instructions

## Scope and conventions
- Vue 3 single-file components, JavaScript, CSS, and Vite in `frontend/`.
- Python 3.11+, FastAPI, SQLite, and Uvicorn in `backend/`.
- Keep HTTP routes thin; put persistence and domain behavior in `app/services/`.
- Use the application factory and injectable settings for isolated tests.
- Part 4.1 includes the foundation, Yahoo streaming, observation processing, and
  constructed candles, backend WebSocket fanout, and frontend feed integration.
  TradingView Lightweight Charts visualization and deterministic read-only replay are included.
- Part 4.2 authorizes completed-candle SMA20/SMA50/crossovers and persistent manual
  simulated account/orders/accounting. Automatic simulated SMA crossover trading is now authorized. Historical backtesting is also authorized, isolated from the main paper account.
  Do not add AI, audio, or speculative future modules without authorization.
- Store timestamps as fixed-width UTC ISO 8601 with microseconds and `Z`.
- Use the persistence service for writes; do not update or delete observations.
- Preserve provider payloads, missing values, provenance, and all unique revisions.
- Observation identity and candle identity differ; read `docs/database.md` first.

## Tests
- Run `cd backend && ../.venv/bin/python -m pytest` for backend changes.
- Run `cd frontend && npm test && npm run build` for frontend changes.
- Test meaningful behavior: metadata, constraints, duplicate detection, ordering,
  revision preservation, initialization, failure states, and health integration.
- Use temporary databases and explicitly simulated fixtures. Never use a real feed
  as a unit-test dependency. Report commands and actual results, including failures.

## Documentation and evidence
- Keep README, design, schema documentation, and architecture consistent with code.
- Record material prompts, files, decisions, failures, and validation in
  `docs/evidence-log.md`. Do not claim checks that were not executed.
- Update `AI-USE.md` when tools or known models change. Mark unknown information.
- Do not create `report.md` until requested.

## Security and data honesty
- Never commit secrets, API keys, `.env`, databases, virtual environments, or dependencies.
- Keep sensitive values out of browser bundles and logs. Validate all provider input.
- Use parameterized SQL values and explicit local CORS origins; do not broaden CORS
  or add credential support without a concrete requirement.
- Clearly distinguish live, delayed, recorded, and simulated data in storage and UI.
  Do not infer live status from backend availability. Do not invent market prices.
- Replay presentation is recorded data, while original observation provenance stays intact.
- Never label delayed data live. Unknown data mode must be resolved before ingestion.

## Current architecture and verification
- `app/services/market_data.py` owns one Yahoo session for four symbols; repositories
  commit raw observations and candle revisions before live WebSocket publication.
- `app/services/replay.py` reads immutable snapshots; `/ws/replay` sessions and the Vue
  replay transport/book are separate from `/ws/market` and live history.
- Charts render backend candle revisions. Only explicitly reliable interval volume
  becomes bars; never convert Yahoo daily totals or unsequenced sizes into candle volume.
- A saved subscription snapshot is historical evidence, not a newly received provider
  event. Provider probes must exclude snapshot frames from fresh-receipt claims.
- For final verification, run both full suites and the frontend build. Test fresh
  dependencies in an isolated source copy when workspace runtime reads stall; identify
  that environment and compare tested source with the workspace before claiming results.
- Keep intentional failure injection and simulated browser fixtures in separate disposable
  environments. Record actual provider, saved-provider and simulated evidence separately.
- Do not commit or create report.md during audits unless explicitly instructed. Final
  submission needs a real repository URL/commit and accessible demonstration video;
  never invent these artifacts or imply they exist.
- Live construction supports 1m, 5m and 15m together. Persist raw observations once
  with all affected candle revisions in one transaction; interval selection must not
  create another provider subscription. CANDLE_INTERVAL selects only the default.

## Manual paper-account rules
- Paper orders/fills are SIMULATED and separate from provider observations. No broker. Backtests use separate isolated state. Automatic simulated actions require the opt-in strategy
  service, a persisted confirmed signal and a later eligible observed price.
- Use integer micro-USD and remaining total cost basis; never calculate sale cost from
  a rounded display average. Release all residual basis on full close.
- Serialize validation, fill, cash, position and order status in one persistence transaction.
  Preserve unique client keys/fill-per-order constraints and retry the same identity after
  an uncertain response. Account initialization must never top up/reset existing cash.
- Test executions only in isolated test databases; do not place demonstration orders in
  the user's persistent account. Saved mark prices may be stale or missing; label them.

## Authorized Part 4.2 automatic simulated strategy
- Keep automatic trading default OFF; no broker is authorized. Backtests must never
  mutate live account/strategy state or broadcast simulated fills as live.
- Only persisted completed-candle confirmed signals may queue strategy orders; browser
  indicators and recorded replay must never trigger them.
- Preserve stable signal identities and same-transaction orders/fills/account/ownership.
- Require a subsequent eligible observed quote and retain its ID; never fill at the
  confirming candle close or fabricate an unavailable price.
- Preserve manual share ownership,20% whole-share sizing, and traceable decisions.


## Verification and continuous integration
- Run the full backend/frontend suites and production build before reporting completion.
- Also run `cd backend && ../.venv/bin/python scripts/verify_references.py` after indicator
  changes. Compare batch/incremental results with independent Fraction/pandas references.
- Reference tolerance is absolute1e-9 USD, relative0, for supported prices <=$1,000,000;
  do not apply this tolerance to Decimal crossover equality or money accounting.
- Maintain .github/workflows/ci.yml push/PR checks using locked dependencies and
  MARKETPULSE_FEED_ENABLED=false. Never require Yahoo/API secrets in deterministic CI.
- Keep hand-calculated accounting/equity/drawdown examples in docs/verification.md and
  preserve distinct fill vs completed-trade counts. Run trades only in disposable DBs.
- jsdom and mocked chart tests are not browser verification. Record blocked UI access,
  local YAML checks and actual GitHub-hosted runs separately; never invent a green CI run.
- This stage authorizes verification/CI only; do not begin Part4.3 or push/commit unless asked.

## Final Part4.2 audit evidence
- docs/part-4.2-review.md is the current requirements matrix. Preserve the distinction
  between implemented/tested features and unverified browser/hosted-CI/submission items.
- Do not count old Part4.1 screenshots or a pre-existing report/video as proof of new
  Part4.2 behavior. Leave report.md unchanged until specifically asked to prepare it.
- When auditing recorded data, use a SQLite-aware backup and execute orders/backtests
  in disposable copies. Verify the full observation/candle/signal/order/fill/account trace.
- A current HEAD is not a submitted Part4.2 commit when implementation is uncommitted.
  Do not commit/push or start Part4.3 without explicit instruction.

## Current browser verification evidence
- The November16 fixture browser pass is documented in docs/testing-2026-11-16.md and
  docs/browser-test-cases.md. Keep it separate from live-provider and hosted-CI evidence.
- Browser test trading must use the isolated fixture harness/temporary account and
  visible synthetic-data banner, never the user's persistent main account.
- Preserve actual failed/revised driver approaches and untested controls; do not convert
  them to false passes. Report preparation and GitHub commit/push still require instruction.
