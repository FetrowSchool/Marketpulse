# Market WebSocket protocol — schema version 1

## Transport and subscriptions
Connect to `/ws/market` on the same origin as the UI. Vite proxies `/ws` to FastAPI
locally; production hosting must proxy both `/api` and WebSocket upgrades for `/ws`.
The browser never connects to Yahoo. WebSocket Origin is checked explicitly against
the configured CORS origins; absent Origin is allowed for local CLI/non-browser clients.
This is a local workstation, not an authenticated public broadcasting service.

The server sends `connection_status` with `data.state=connected` and subscription ID
0, then the browser selects one supported symbol using a JSON text request:

```json
{"type":"subscribe","symbol":"AAPL","request_id":1}
```

Supported symbols: AAPL, MSFT, NVDA, SPY. `request_id` must be an increasing positive
integer <=2147483647 within that connection. The acknowledgment has
`type=connection_status`, `data.state=subscribed`, and `subscription_id=request_id`.
There is one selected symbol per client, while different clients may select different
symbols. Switching again uses the next request ID; it does not alter another client.
Invalid JSON, binary frames, unsupported symbols/types, and invalid request IDs produce
an `error` message without silently changing the current subscription. Text requests
over 4096 characters are rejected. No trading or provider commands are accepted.

After acknowledgment, the server sends current feed status and, when available, the
latest persisted quote and local candle with `data.snapshot=true`. Snapshot fields
are original committed observations, not freshly generated market data. Their source
age and recorded/simulated/delayed/live provenance remain intact. No fabricated empty
market snapshots are emitted when data does not exist.

## Common server envelope
All messages use these keys. Unavailable fields are JSON null, not invented values.

| Key | Meaning |
| --- | --- |
| schema_version | Integer 1 |
| type | connection_status, market_observation, candle_update, candle_completed, feed_status, error |
| subscription_id | Client's acknowledged request generation; 0 before subscription |
| symbol | Selected stock symbol |
| source | yahoo_finance |
| sent_timestamp | Actual backend send/enqueue time in canonical UTC |
| event_id | observation:<SQLite ID> for a stored record, otherwise null |
| source_timestamp | Stored source time for record messages; latest source high-water for status |
| received_timestamp | Original stored backend receipt for records; latest valid receipt for status |
| interval | Candle interval for candle records; null for raw quotes; configured interval for status |
| candle_complete | Stored completion boolean for candles; null otherwise |
| revision | Stored revision for a record; null otherwise |
| observation_identity | Object containing id, source_observation_id, observation_type; null for control messages |
| data_age_seconds | Source age at enqueue time; null when no source time exists |
| feed_status | Symbol-specific feed freshness/transport snapshot |
| data | Stored serialized observation/candle, connection acknowledgment, or error details |

Record `data` contains the REST row representation, including source/mode, both original
timestamps, OHLCV when applicable, revision/completion, hash, price, and metadata.
Raw prices live in `data.price`; original Yahoo fields are under
`data.metadata.original`. A candle is always `observation_type=constructed_candle`
in this producer, with metadata `candle_origin=locally_constructed`. Volume remains
null. Provider-supplied candles are not conflated with these quote aggregates.

`market_observation` is a committed normalized raw quote. `candle_update` is an
incomplete constructed candle revision. `candle_completed` carries any complete
revision, including a late correction or completed snapshot; it does not imply a new
trade or complete market coverage. The immutable SQLite ID/revision identifies it.

`feed_status` messages arrive approximately once per second even when prices do not
change. `feed_status` includes state/reason/last_error, upstream transport connectivity,
source high-water, latest valid backend receipt, independently calculated source and
receipt ages, freshness thresholds, provenance and session qualification. Transport
attempt/accepted/duplicate/rejection counters describe the shared connection, while
source/receipt timestamps and freshness belong to the selected symbol.

Errors have `data.code` and a safe human-readable `data.message`. Current codes are
`invalid_subscription` and `database_unavailable`. Yahoo outages are conveyed through
feed status (disconnected/unavailable/retry state) without closing healthy browser
sockets. Browser-to-backend connection state is tracked separately by the client.

## Delivery and lifecycle
The repository copies serialized record rows inside its transaction, commits raw and
candle together, then invokes its post-commit hook. Worker threads schedule fanout
onto the application's event loop; they never await browser writes. Duplicate raw
observations do not emit new record events. Completion timer commits also publish.
A failed transaction emits no observations/candles.

Each browser has a 128-frame queue and independent sender with a 5-second write
limit. A full queue closes that client with code 1013 so it can reconnect and request
SQLite snapshots. Normal disconnection removes the client, cancels/awaits its tasks,
and does not affect provider ingestion or other clients. Cleanup is shielded from
ASGI/AnyIO cancellation. Backend shutdown closes sessions with restart code 1012;
Uvicorn may initiate that shutdown close before application lifespan cleanup.

MarketPulse keeps one Yahoo socket per backend process and subscribes to all four
supported symbols once when each upstream session starts. Browser subscriptions are
server-side filters and never open or duplicate Yahoo subscriptions. This eagerly
records the small finite universe, even if only one symbol is viewed. The yfinance
heartbeat may reannounce the existing set; duplicates still deduplicate in SQLite.
Use one backend worker: there is no cross-process broker or distributed fanout.

Delivery is best-effort, not an exactly-once replay protocol. After reconnect the
latest SQLite snapshot restores price/candle state; missing intermediate revisions
remain queryable via REST but are not automatically replayed over the socket. Commit
callbacks from different worker threads can interleave; consumers must use source
time, IDs and revision rather than assuming global wire order. The frontend rejects
old subscription generations and wrong symbols, retains cached last prices per symbol,
ignores older source-time quotes, and ignores older candle revisions/intervals.

## Browser recovery and data honesty
The reusable frontend service uses ws/wss on the application's origin. Connection
and status-idle timeouts are 10 seconds. Retries wait 0.5, 1, 2, 4, 8, then at most
15 seconds, with eight retries per consecutive unstable run. An open connection must
remain stable for 10 seconds to reset the failure budget. Valid matching protocol
messages refresh the idle watchdog; invalid JSON does not. Manual reconnect resets
the budget. Unmount clears timers and closes the socket.

Browser connection does not establish current Yahoo data. UI feed state comes from
the backend and source/receipt ages continue advancing locally. Disconnected, stale,
delayed, recorded and simulated values remain explicitly last known/noncurrent;
prices are never invented or erased solely because the feed fails. Original source
and receipt times are displayed separately. Live/fresh requires confirmed source
mode, fresh age, an acknowledged subscription and healthy browser transport; this
still does not prove an open exchange. TradingView chart visualization now consumes committed candle events; raw observations
continue to update the latest-price panel. Selected interval filtering and a concurrent
REST history merge prevent mixed chart contexts. Recorded replay uses the separate
/ws/replay endpoint and replaySocket.js; see replay.md for its distinct protocol.

## Fresh unverified status — 2026-11-11
Feed snapshots now additionally support `state="real_time_unverified"`. It means the
provider is connected and both source and receipt age are within the configured fresh
threshold, while real-time entitlement or regular-session context is unverified.
The UI label is **Real-time unverified**. Existing `reason` values retain entitlement
or outside-session context. Above the fresh threshold use delayed; above the stale
threshold use stale. A connection without valid observations remains connecting/stale.
This additive status does not change observation data_mode, wire schema version or
recorded rows. The conservative stored mode delayed is separate from current freshness.

## Live interval capability — 2026-11-11
Feed snapshots include live_intervals=["1m","5m","15m"], as does /api/market/symbols.
The existing interval/active_interval still specifies the default. Every subscription
receives committed updates and saved snapshots for all three intervals of its symbol;
clients filter by the record's interval. A new raw observation is broadcast once,
followed by each interval's candle revision. Switching interval needs no new provider
subscription. Existing message types, row timestamps and revision semantics are unchanged.
