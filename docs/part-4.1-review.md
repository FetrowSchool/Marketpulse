# Part 4.1 requirements and submission readiness

Review date: 2026-11-09. This is supporting documentation, **not report.md**.
No Part 4.2 implementation, commit, report or video was created in this audit.

## Requirement comparison
| # | Requirement | Actual implementation / verification |
| --- | --- | --- |
| 1 | Yahoo market-data connection | Implemented yfinance 1.8.0 streaming; new actual provider receipt verified. Real-time exchange entitlement remains unverified, so data stays delayed. No polling fallback. |
| 2 | Candlestick visualization | Implemented native Lightweight Charts with backend-constructed quote OHLC, revisions and completion. Browser verified; not official trade OHLCV. |
| 3 | Corresponding volume | **Partial:** aligned native histogram and reliable-volume contract implemented and browser verified using an explicitly simulated fixture. Actual Yahoo quote stream cannot establish interval volume; real-data pane honestly remains unavailable. |
| 4 | WebSocket communication | Implemented one shared upstream socket, committed-record `/ws/market` fanout and independent `/ws/replay`. New-provider record traced through Vite proxy. |
| 5 | Visible data source | Implemented Yahoo/source and constructed-candle labels; provenance distinguishes simulated, recorded presentation and delayed observations. |
| 6 | Visible data age | Implemented source age separate from backend receipt time; live-mode age advanced during outage. Replay uses recorded playhead age. |
| 7 | Visible feed status | Implemented connecting/live/delayed/stale/disconnected/unavailable semantics. Browser connected does not imply provider live. Actual new stream remained delayed. |
| 8 | SQLite persistence | Implemented atomic append-only raw/candle writes; new raw observation matched directly to SQLite. Integrity audit passed. |
| 9 | Historical retrieval | Implemented validated observation/candle REST APIs, ingest cursor and latest revision history; browser restored saved data after restart. |
| 10 | Replay | Implemented frozen read-only snapshot, symbol/range, receipt or arrival ordering, speed and Play/Pause/Resume/Restart/Stop. Browser completed 228 genuine saved AAPL events with upstream unavailable. |
| 11 | Observation identity | Implemented stable scoped IDs and canonical hashes; Yahoo supplies no event sequence, so payload-hash identity cannot distinguish truly separate identical provider events. |
| 12 | Source/receipt timestamps | Implemented canonical UTC microseconds; traced browser values match original row values exactly. |
| 13 | Revisions | Implemented append-only ordered revisions and chart rejection of lower revisions. Existing and new offline regression tests passed. |
| 14 | Candle completion | Implemented provisional/complete revisions, timer finalization and late completed corrections. Browser observed both provisional and complete candles. |
| 15 | Duplicates | Implemented exact normalized-content deduplication within identity, excluding receipt; same-price distinct content/identity survives. Offline tests passed. |
| 16 | Out-of-order observations | Implemented source-time OHLC rebuild of affected bucket, immutable late revisions and stable receipt/ID replay. Known expected-result tests passed. |
| 17 | Unavailable feed | Implemented retained data, advancing age, bounded reconnects and responsive independent replay. Upstream failure deliberately simulated and labeled; not an actual Yahoo outage. |
| 18 | Evidence/documentation | Implemented documentation, tests, genuine pipeline trace, recorded replay and distinct simulated evidence. Submission artifacts below remain pending. |

## New end-to-end provider evidence
The documented fresh-source startup connected to Yahoo with TLS verification using the
installed certifi trust bundle. Data flow was:

Yahoo WebSocket → yfinance decode → normalize_message → raw/candle transaction →
SQLite commit → MarketSocketHub → FastAPI /ws/market → Vite proxy → Vue revision book
and native Lightweight Charts.

Observation **#453**, AAPL, price **351.43**, source **2026-11-09T19:09:56.000000Z**,
receipt **2026-11-09T19:09:57.619056Z**, was independently captured as a newly broadcast
(non-snapshot) frame and read directly from SQLite. The frame equals the SQLite row;
Vue's displayed price and both timestamps match. Original decoded metadata is retained
in [the trace](evidence/final-end-to-end-trace.json). These IDs belong to the audit's
isolated database. Native subsequent updates continued in the browser; the screenshot
may contain a later tick because the stream kept running.

This is successful actual provider streaming receipt, **not verified exchange real-time
entitlement**. The application labeled it delayed with realtime_entitlement_unverified.
It does not prove a complete exchange tape, interval volume or source correctness.

The verification probe was revised: saved subscription snapshots now go into
snapshot_records and cannot satisfy new-provider receipt. It retrieves the exact ID
using after_id, including IDs beyond the first 1,000 rows. Two mocked regression tests
verify both snapshot-only and new-event outcomes. The existing historical evidence was
not relabeled or treated as new evidence.

## Outage, database and replay results
An external verification-only Yahoo adapter wrapper raised explicit OSError failures
when a local marker appeared; the production service/routes were not changed to add a
failure endpoint. Status samples showed disconnected attempt 1, disconnected attempt 2,
then unavailable attempt 3. Retry base/cap were both 2 seconds for this experiment.
The browser-to-backend socket stayed connected, candles/observation #897 stayed visible,
and age increased **6 → 23 seconds**. All **450 raw rows** retained an identical digest.
Legitimate elapsed-candle completion can append constructor revisions, not fake quotes.

Replay completed **228/228 genuine saved AAPL events**, then Restart/Pause/Resume worked
while Yahoo was unavailable. After an intentional backend restart the replay connection
reported its loss and required Load selection; reload restored a ready session. Returning
to Live restored saved candles/connected browser with Yahoo unavailable. Selecting an
unrecorded 5m interval showed a distinct empty/saved-only state rather than fake bars.

The captured database contained **907 rows**. Clean shutdown and two repeated schema
initializations preserved all ordered rows and SHA-256:
`6ecf41c863d00057f9c21ca962eee0da6f27eff57976d4711deb689aed1e1855`.
SQLite integrity was ok, with zero FK violations, revision gaps or audited metadata
failures. Two full 228-event replay runs returned identical row sequences and did not
change the database. No schema migration was required during this review.

A separate disposable database contained **8 explicitly simulated SPY candles** with
known volume [100,250,125,400,300,150,500,200]. Native histogram bars were visible;
recorded playback progressed from 1 to 8 bars and completed 8/8. The UI labeled the
fixture SIMULATED or REPLAY · RECORDED with simulated original provenance. These rows
were never mixed into the genuine capture DB and are not Yahoo-volume evidence.

## Fresh setup and automated checks
There is no HEAD commit in this checkout, so a literal Git clean-checkout test was not
possible. Instead, a fresh source-only copy was created at
/private/tmp/marketpulse-final-review, excluding .git, dependencies, virtual environments,
.env, build outputs and runtime databases. Unlike prior validation copies, this audit
created a new venv and installed dependencies from the documented files.

Executed successfully:
```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm test
npm run build
```
From backend/: `../.venv/bin/python -m pytest -ra`.
Python `pip check`: no broken requirements. Python 3.13.15, Node 24.20.0, npm 11.19.0.
No .env was needed; defaults initialized an empty SQLite DB on startup. Installed
certifi was selected as the trusted CA bundle for this machine; TLS remained enabled.
Documented Uvicorn and npm dev commands started successfully; HTTP health/database and
Vite's HTTP/WebSocket proxies worked. Only local loopback ports were used.

| Check | Collected | Passed | Failed | Skipped | Actual result |
| --- | ---: | ---: | ---: | ---: | --- |
| Backend pytest | 117 | 117 | 0 | 0 | 8.00s; one existing Starlette/httpx deprecation warning |
| Frontend Vitest | 24 | 24 | 0 | 0 | 7 files, 770ms |
| Frontend production build | — | — | 0 | — | Vite 7.3.7, 385ms, 22 modules |

Fresh npm ci reported **4 moderate** transitive development advisories through
js-beautify/editorconfig/glob/minimatch. `npm audit --json` confirmed them (exit 1).
They remain unresolved; no force upgrade or audit-clean claim is made. Automated tests
use mocked/simulated transport; they do not depend on Yahoo being available.

Browser inspection covered desktop 1440×1000 and the normal side-panel layout,
candles/revisions, source/time/age/status, AAPL/NVDA/SPY selection, saved-only interval,
unavailable source, replay controls and mode switching. Final console warn/error lookup
returned no entries. Native date-time field automation failed in the preceding replay
stage, and was not reverified manually here; UTC range serialization/validation is
covered by automated tests. Exhaustive physical-device/accessibility testing is not claimed.

## Submission gate
Canvas eventually receives **only report.md**. Do not submit the whole project as the
Canvas report, and do not create report.md until requested. The eventual report must link
to supporting documentation/evidence and include functionality, decisions, verification
and limitations, plus these currently missing items:

| Submission item | Current state |
| --- | --- |
| GitHub repository URL | Missing: `git remote -v` returned no configured remote |
| Submitted commit hash | Missing: no HEAD commit (`git rev-parse --verify HEAD` failed); no commit authorized |
| Accessible 30–60 second demonstration video | Missing: no video was recorded or uploaded |
| report.md | Intentionally not created, as instructed |

Core Part 4.1 functionality is implemented with the explicit volume/data-quality limits
above. Full end-to-end **actual interval-volume visualization** is unmet with this Yahoo
quote source; its renderer is verified only by simulated fixtures. Seek/durable replay
sessions, exchange calendars, gap recovery, provider-candle ingestion and production
hosting remain outside this implementation. Replay is bounded to 10,000 selected events
and 1,000 displayed openings. No Part 4.2 feature was implemented.

Supporting evidence: [provider probe](evidence/final-provider-pipeline.json),
[exact displayed-row trace](evidence/final-end-to-end-trace.json),
[outage samples](evidence/final-simulated-outage-status.json),
[outage integrity](evidence/final-outage-integrity.json),
[database/replay audit](evidence/final-database-verification.json),
[simulated volume fixture](evidence/final-simulated-volume-fixture.json),
[full evidence log](evidence-log.md).
