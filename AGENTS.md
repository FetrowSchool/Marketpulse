# MarketPulse project instructions

## Scope and conventions
- Vue 3 single-file components, JavaScript, CSS, and Vite in `frontend/`.
- Python 3.11+, FastAPI, SQLite, and Uvicorn in `backend/`.
- Keep HTTP routes thin; put persistence and domain behavior in `app/services/`.
- Use the application factory and injectable settings for isolated tests.
- Part 4.1 includes the foundation, Yahoo streaming, observation processing, and
  constructed candles, backend WebSocket fanout, and frontend feed integration.
  TradingView Lightweight Charts visualization and deterministic read-only replay are included. Do not add trading, indicators,
  AI, audio, or speculative future modules without authorization.
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
