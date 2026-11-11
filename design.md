# MarketPulse design

## Architecture and communication
Vue renders the workstation and receives committed market messages from `/ws/market`
through Vite's WebSocket proxy, alongside health and symbol-list HTTP requests. FastAPI's lifespan initializes SQLite, starts the Yahoo stream and
completion timer, then cancels/awaits them during shutdown. The market socket hub starts before ingestion
and shuts down after it. Routes remain thin and
read-only. SQLite work runs in a worker thread to avoid blocking the event loop;
shutdown waits for any in-flight transaction before returning. Configure a single
backend worker. TradingView Lightweight Charts now renders saved and streamed candle revisions;
market WebSocket fanout remains active.

## Actual Yahoo connection
The inspected installed version is yfinance **1.8.0**, with documented synchronous and
asynchronous WebSocket APIs. `YahooStream` uses `AsyncWebSocket.subscribe` to establish
the provider connection and subscribe, and `close` to shut down. It directly receives
from the inspected `_ws` object and uses `_decode_message` to decode Yahoo's protobuf
payload. This small private seam is isolated and version guarded. The public `listen`
loop in that version swallows callback/connection errors and contains its own fixed
3-second retry; MarketPulse avoids it so one service owns failures/retries. No global
yfinance configuration is changed. Unsupported versions fail unavailable rather than
silently switching to historical polling. Upgrade only after inspecting/testing the seam.

Sources inspected: [streaming API](https://ranaroussi.github.io/yfinance/reference/yfinance.websocket.html),
[implementation](https://github.com/ranaroussi/yfinance/blob/main/yfinance/live.py),
[PricingData schema](https://github.com/ranaroussi/yfinance/blob/main/yfinance/pricing.proto).
yfinance is an independent wrapper, not an official Yahoo-supported service contract.
A real stream/subscription with one AAPL observation was verified; the evidence log
separately records DNS/TLS failures, the successful CA-bundle retry, and provenance.

## Normalization and identity
Yahoo's decoded `id` is the symbol, `time` is interpreted as epoch milliseconds,
and `price` is an individual quote. The adapter rejects missing/unexpected symbols,
missing/nonfinite/nonpositive prices, invalid/second-unit timestamps, naive receipt
times, and source times beyond configurable clock skew. Epoch conversion retains
millisecond precision; all internal timestamps use UTC microseconds and Z. Original
decoded fields, including unknown fields, are preserved. Protobuf omitted/default
fields cannot be recovered from a decoded dictionary; wire envelopes are not archived.
Invalid messages increment rejection/error counters but are not stored as valid quotes.

Observation identity remains `(data_source, symbol, observation_type,
source_observation_id)`. The inspected provider schema exposes no unique event ID or
sequence. Therefore `source_observation_id` is a canonical decoded-payload SHA-256,
with `provider_event_id=null` and the strategy recorded in metadata. Receipt time is
excluded. Exact retransmissions on reconnect/restart deduplicate; distinct payloads
at the same source timestamp survive. This cannot distinguish separate identical
provider events or recognize undocumented corrections to a prior event. Do not infer
source revisions from timestamp alone. If a future provider exposes stable IDs,
existing revision storage and effective-revision aggregation can use them.

Candle identity is symbol/source/type/interval/opening time. The local producer's
observation ID includes algorithm version, provenance mode, interval, and UTC bucket
opening. Raw, provider-supplied, and constructed candles remain separate types.
Yahoo stream messages are always normalized as raw price observations: `day_high`,
`day_low`, or `open_price` do not make them interval OHLCV. Provider-candle ingestion
is not added in this stage; the existing schema still supports that separate type.

## Candle construction and revisions
Source timestamps are floored into UTC 1m, 5m, or 15m buckets. Each incoming unique
quote rebuilds only its bucket from persisted effective raw revisions in source-time
order; ingest ID resolves equal timestamps because no source sequence exists. Open
and close are the first and last observed quote; high/low are observed extrema.
Metadata records algorithm version and contributing raw IDs. No missing intervals
are synthesized, and coverage is explicitly observed quotes only. Gaps, dropped
updates, omitted trades, corporate actions, and provider adjustments are not repaired.

Candle completion is false until backend UTC time reaches the bucket end. The timer
appends a completed revision even when no next tick arrives; completion means the
interval elapsed, not that market coverage is complete. A late quote rebuilds its
historical bucket and appends a corrected revision; it never replaces another bucket
or overwrites an earlier row. Once complete, a candle stays complete across clock rollback. Restart rebuilds from persisted data rather than losing
an in-memory candle. Latest raw revisions avoid double counting within a bucket.
The Yahoo fallback identity is content-derived and cannot move between buckets;
future explicit-ID corrections that change event time need an old-bucket retraction
policy before enabling them. Unchanged aggregate snapshots deduplicate.

`day_volume` is a daily/cumulative provider total, not a candle contribution.
`last_size` and similar fields lack reliable unique-trade sequencing in this stream.
They are preserved verbatim in metadata, never summed or differenced into invented
interval volume. Raw volume and constructed candle volume remain NULL. Local quote
OHLC is not equivalent to provider-supplied trade OHLCV and is labeled accordingly.

## Persistence and API
`Database.transaction()` owns BEGIN IMMEDIATE. The repository inserts a raw quote,
queries the affected persisted bucket, constructs OHLC, and appends the candle within
that same transaction. Failure rolls back both. Unique identity/revision and content
constraints plus append-only triggers preserve history. Receipt timestamp is captured
at normalization, before database waiting, and passed to storage; duplicates keep their
first stored receipt while status records later receipt independently. A source-time
lookup index is added idempotently without changing version 1 columns or records.

Observations API returns every raw revision by ingest ID with a cursor. Candles API
returns latest local revisions by default, or row-limited history on request. Results
retain provenance and metadata. Valid-but-unrecorded symbols/intervals return empty
arrays, invalid queries 422, database read errors a safe 503. Feed persistence failures
are sticky/unavailable and stop ingestion; health remains a separate database check.

## Feed state and shutdown
A transport connection alone never implies live data. Status tracks source timestamp
high-water separately from the receipt of the latest valid observation, even if its
persistence fails. Out-of-order updates do not regress source high-water. Source age
and receipt age are calculated independently. Rejected messages do not refresh valid
observation freshness. Small allowed future timestamps may produce a negative source
age, retained to expose clock skew; receipt elapsed time is clamped at zero.

States: connecting before first quote, real_time_unverified for fresh unconfirmed data
(including fresh observations outside the regular clock window), delayed for source/receipt ages above the fresh
threshold, stale above the stale threshold, disconnected during retry wait, and
unavailable for disabled/incompatible feed, exhausted retry budget, or database failure.
Default source provenance is conservatively delayed/unverified because socket access
cannot establish exchange real-time entitlement. Live additionally requires explicit
REALTIME_CONFIRMED configuration, both ages fresh, and a regular weekday clock window.
Source provenance is stable configuration; freshness is a separate changing state.
Neither asserts active trading. Regular hours use America/New_York with DST; weekends
are outside regular trading, and holiday/early-close/overnight calendars are unverified.
The numeric `market_hours` field is preserved, not guessed; the inspected schema does
not document its mapping. Extended-hours observations can be persisted without
misrepresenting regular active trading.

Each failed session closes its client and recreates it before resubscribing. Retry
wait is min(base * 2^(consecutive failures - 1), cap). Valid durable messages reset
consecutive failures. The configured failure budget includes initial failed attempt;
a successful socket without valid messages does not reset it. No quotes on an open
socket cause stale status, not a fabricated market-open claim or historical fallback.
Subscribe/connect and close have timeouts. Cancellation interrupts receive/backoff,
closes transport and its heartbeat, stops completion, and awaits database work. The
10-second SQLite busy timeout bounds lock waits. Process crashes still rely on SQLite
transaction durability, not graceful task cleanup.

## Deterministic replay
ReplayRepository materializes a read-only SQLite snapshot bounded by MAX(id), a selected
symbol/interval, and optional receipt-time UTC [start,end). The default order is
(received_timestamp,id); optional arrival order uses id alone, preserving commit order
when the backend wall clock moves backward. Source timestamps govern candle construction,
not playback timing. Latest revisions must never cross the selected as-of boundary.

ReplaySession uses an injected monotonic clock and cumulative recorded receipt gaps,
scaled by speed. Arrival-mode negative gaps become zero. Pause freezes virtual time;
speed changes settle elapsed time at the previous speed before applying the new one.
Restart and Stop reset the cursor and increment generation; Restart plays, Stop stays
stopped. No Yahoo subscription, processing callback, timer or persistence write is invoked.
Stored raw rows and resulting candle revisions replay exactly as recorded; Vue does not
reconstruct or finalize historical candles using today's clock.

A pre-start baseline selects prior candle revisions and the latest source-time quote,
not final current history. In arrival mode it also excludes IDs at/after the first
selected arrival. The frontend closes its live socket and disposes live history when
entering replay; separate transport/epochs and a fresh revision book prevent live or
previous-generation frames from mixing. Return to Live discards replay state, loads
latest history and resubscribes. Chart context includes mode/generation for reset/fit.
Original data_mode remains unchanged; the replay envelope/UI marks presentation recorded.
Protocol, pacing and bounds are in docs/replay.md. Indicators, trading, AI and audio
remain out of scope; seek and durable replay-session recovery remain unimplemented.

This is a local educational stream capture, not a complete market tape. There is no
provider gap recovery, full session calendar, adjustment/corporate-action policy,
provider-candle ingestion, production deployment, or financial ledger. SQLite REAL
is retained for analytical observations. Schema initialization is repeatable, not a
migration framework. Future schema changes require explicit migrations/backups.


## WebSocket fanout and frontend state
One provider session subscribes once to all four supported symbols. Repositories and
source/receipt high-water are per symbol; upstream connection/retry counters are
shared. Browser subscriptions select a server-side filter, not a provider connection.
The old configured active symbol remains the default API/UI choice.

Repository methods capture serialized rows in the transaction and invoke the hub's
hook only after commit. The hook schedules event-loop queue fanout from worker
threads; producers do not await network sends. Each browser has bounded independent
queue/sender/receiver tasks. Queue overflow or broken transport affects that client,
not SQLite or other clients. Cancellation-shielded ASGI cleanup awaits all tasks.

Schema version 1 envelopes preserve row ID/identity/revision, source and receipt UTC
values, interval/completion, age, provenance/metadata and a separate feed snapshot.
Status pulses continue through quiet feeds and outages. New subscriptions receive
latest persisted snapshots without generating new rows. Per-client request IDs allow
both sender and frontend to discard old subscriptions during a symbol change.

The frontend caches last known data per symbol, rejects older source-time prices and
older candle revisions, and keeps source age advancing while disconnected. It does
not label a connected browser live; currentness requires fresh confirmed upstream
data and an acknowledged subscription. Backend errors and finite reconnect exhaustion
remain visible with a manual retry. Chart drawing is now implemented by the reusable MarketChart component; independent recorded replay is now implemented.

See `docs/websockets.md` for exact schema, retry limits, backpressure, Origin policy,
and best-effort delivery semantics. This is a single-process in-memory fanout, not an
exactly-once or cross-process broadcast/replay system.


## Visual workstation extension
TradingView Lightweight Charts 5.2.1 provides candlesticks and a separate histogram
pane with a shared UTC axis. MarketChart owns lifecycle/resize and attribution;
chartRenderer owns supported initial/latest/historical series operations. The UI
renders only validated backend candle rows, never random data or local candle builds.
Existing historical changes use update(bar,true); unseen earlier insertions use sorted
setData with preserved visible range. Initial measured size fixes first-fit timing.

History REST and live WebSocket updates merge into one generation-scoped revision
book. Stable producer identity, per-identity revision checks, selected symbol/interval
filtering, and ignored superseded responses protect against initialization races.
On subscription/reconnection the latest 1000 saved candle rows are fetched again
without overwriting higher live revisions. Price, source timestamp and last receipt
remain separately available during failure, with explicit last-known classification.

Volume requires explicit reliable interval metadata; current Yahoo quote candles have
NULL volume and show no bars, with an explanation. Provider changes are shown only
when supplied. Other saved intervals can be selected, but only the backend-configured
interval receives live candle construction. Recorded data remains recorded, not live.
See docs/charting.md for exact rules, identity branches, limits and chart API references.


## Final Part 4.1 review and future Part 4.2 boundaries
The complete path was verified with an actual newly received Yahoo observation,
including a matching browser-visible ID/price/timestamps. Saved socket snapshots are
excluded from fresh-provider probe results; this prevents backend availability or
recorded history from masquerading as a live-provider connection. Real-time entitlement
and reliable Yahoo interval volume remain unverified/unavailable respectively.

An upstream-only fault was injected in a disposable verification wrapper, leaving
FastAPI running. Retried connections exhausted the configured budget, browser state
became unavailable, saved candles stayed visible, and replay continued. This is
simulated failure evidence, not a claim that Yahoo itself was down. Original captured
rows survived restart/repeat initialization and deterministic replay unchanged.

Future Part 4.2 work can consume immutable normalized rows and explicit as-of revision
boundaries, derive indicators in a separate service, and use a deterministic clock for
backtests. It must distinguish source chronology, receipt chronology and available-at
information to avoid future revision lookahead. Simulated orders/executions need a
separate ledger and provenance; they must not be inserted as provider observations.
These are design extension points only: no indicator, trade, backtest or ledger code
has been implemented in this review. See docs/part-4.1-review.md for outstanding scope.

## Simultaneous live intervals — 2026-11-11
Each per-symbol MarketRepository now constructs 1m, 5m and 15m in the same immediate
transaction as a single raw insert. A failure in any interval rolls back the entire
batch; publication follows commit once, with one raw event and three candle events.
Duplicate raw delivery skips all interval reconstruction. Late quotes rebuild their
affected source-time bucket independently in each interval. Completion scans all
constructed intervals and never generates empty candles or estimates volume.
CANDLE_INTERVAL now selects only the default, not the sole construction interval.

Subscription snapshots include the latest candle for each interval; live_intervals
advertises capability. Vue merges only the selected interval, while HTTP history and
revision ordering retain their existing race protection. Interval changes never create
additional provider subscriptions. Existing rows remain unchanged, and new intervals
are populated on receipt of new unique observations; no full historical backfill is run.

## Automatic chart focus
Recent-candle zoom is presentation-only: a persistent viewport preference (10/25/50/100,
25 by default) and follow flag configure the reusable chart renderer. Logical index
ranges work across data gaps without constructing fake intermediate bars. Turning off
following preserves the user's viewport on ordinary revisions; context changes focus
the selected dataset. Fit all exits follow mode. Live and replay share the same chart
component. Replay entry is now directly available from the bottom panel as well as
the top mode selector, so disabled Live-mode playback buttons have a clear next action.
