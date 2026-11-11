# SQLite database

## Schema and relationships
Canonical executable schema: [`backend/app/schema.sql`](../backend/app/schema.sql).
There are two tables, with no foreign-key relationship: `schema_version` records the
schema version (currently 1), and `observations` holds immutable observations.
`PRAGMA foreign_keys=ON` is applied for future relationships; WAL permits readers
while writes are serialized. Each connection has a 10-second lock timeout.

| observations column | SQLite type / meaning |
| --- | --- |
| id | INTEGER PRIMARY KEY AUTOINCREMENT; stable ingest sequence |
| symbol | TEXT NOT NULL; service normalizes to uppercase |
| data_source | TEXT NOT NULL; stable source/producer namespace |
| source_observation_id | TEXT NOT NULL; stable source identity within symbol/type/source |
| observation_type | raw_provider, constructed_candle, or provider_candle |
| data_mode | live, delayed, recorded, or simulated; required provenance |
| candle_interval | Nullable TEXT; required nonempty for candle observations |
| candle_open_timestamp | Nullable UTC TEXT; required for candle observations |
| open, high, low, close | Nullable REAL; missing data stays NULL |
| volume | Nullable nonnegative REAL |
| source_timestamp | Required UTC TEXT; source event time |
| received_timestamp | Required UTC TEXT; backend normalization/receipt time, before database waiting |
| revision | Positive INTEGER; arrival revision within observation identity |
| candle_complete | NULL for raw; 0 provisional or 1 complete for candles |
| payload_json | Required valid JSON; original payload and/or relevant metadata |
| content_hash | Required SHA-256 of canonical normalized content |

UTC text format is `YYYY-MM-DDTHH:MM:SS.ffffffZ`; the service rejects naive timestamps
and converts aware timestamps to this format. The ingestion boundary supplies receipt time; ordinary service inserts default to backend now. The Yahoo adapter retains its original epoch-millisecond time in payload metadata.
The current service requires an explicit source timestamp. It does not infer OHLCV:
a raw price-only message can have all five OHLCV columns NULL with price in its payload.
Candle OHLCV columns can also be partial. Complete means the provider/constructor
marked the interval closed, not that every numeric field is present or immutable forever.

## Identity and revision strategy
**Observation identity:** `(data_source, symbol, observation_type, source_observation_id)`.
Repeated normalized content returns the original row ID. Changed content creates
`MAX(revision)+1` in an immediate transaction. Payload key order does not affect hashes;
receipt timestamp, row ID, and revision are excluded. Reappearance of earlier content
is considered a duplicate, not a new revision. A source adapter must supply a distinct
identity if the provider intends the same values as a genuinely new event. Numeric or
payload representation changes may count as changes, so adapters should normalize consistently.

**Candle identity:** `(symbol, data_source, observation_type, candle_interval,
candle_open_timestamp)`. This is deliberately not unique: multiple source observations
and revisions may reference the same candle. A provider candle and a constructed candle
remain distinct. Choosing the canonical candle from multiple identities requires a
future source-specific policy; revision numbers cannot be compared across identities.
Constructed metadata should include algorithm version and contributing database IDs.
There is no lineage join table or candle materialization table yet.

## Constraints, indexes, and transactions
- Nonempty symbol, source, and source observation identity.
- Enumerated observation types/data modes, positive revisions, nonnegative volume.
- Candle type requires nonempty interval, opening time, and completion flag; raw
  type requires all three to be NULL.
- JSON validity is checked by SQLite. The Python service rejects nonfinite numbers.
- Unique `(data_source, symbol, observation_type, source_observation_id, revision)`.
- Unique `(data_source, symbol, observation_type, source_observation_id, content_hash)`.
- `idx_observations_candle`: symbol/source/type/interval/opening/revision lookup.
- `idx_observations_history`: symbol/source timestamp/id historical retrieval.
- `idx_observations_replay`: receipt timestamp/id chronological lookup.
- `idx_observations_receipt_selection`: symbol/source/receipt timestamp/id for bounded replay selections.
- Arrival replay uses the INTEGER PRIMARY KEY directly.
- Triggers reject every UPDATE and DELETE on observations.
- `BEGIN IMMEDIATE` covers duplicate lookup, revision allocation, and INSERT.
  Market ingestion extends that same transaction to the raw quote and candle revision. Failed
  writes roll back. Connections are closed after each operation.

## Initialization
FastAPI lifespan creates the database directory, enables WAL, and executes the DDL
inside an explicit transaction. `CREATE ... IF NOT EXISTS` and `INSERT OR IGNORE` for
version 1 preserve existing data. Schema failures roll back and prevent startup.
Tests initialize temporary databases twice and check record preservation.
This initializer does not upgrade incompatible older schemas or validate a manually
modified schema. Future versions need migrations. Back up databases with SQLite-aware
backup tools, including WAL considerations; do not copy only the main file during writes.

## Retrieval and replay
`Database.retrieve(symbol=None, order="receipt", limit=1000, after_id=0)` returns
all revisions in ascending ID, optionally filtering symbol. Limit is 1–10000.
`order="source"` sorts by source timestamp then ID, including late events; it cannot
be combined with a nonzero ingest cursor. Replay ID order represents arrival, not market
event chronology. This legacy retrieval method orders by ID despite its receipt option
name. The new ReplayRepository explicitly implements receipt-time chronology separately.
Read-only replay HTTP/WebSocket transport uses frozen maximum IDs and timed playback;
see the replay section below and docs/replay.md.


## Yahoo quote processing extension
The schema version and columns remain unchanged. A new idempotent index,
`idx_observations_source_time(data_source, symbol, observation_type, data_mode,
source_timestamp, id)`, supports provider/source-time bucket queries. Raw prices
live at `payload_json.price` (exposed as `price` by REST serialization); raw OHLCV
and candle identity fields remain NULL. Original decoded fields live under
`payload_json.original`; volume totals/sizes are retained under `provider_volume`.

Yahoo `id` is the ticker, not an observation ID. No event sequence is provided by
the inspected yfinance PricingData schema. The raw source ID is therefore SHA-256
of the canonical decoded payload, recorded with `identity_strategy` and a NULL
provider event ID. Exact content retransmissions deduplicate across reconnect and
restart; distinct payloads at the same source timestamp survive as distinct identities.
This cannot detect true-but-identical separate events or identify unadvertised
corrections. Missing fields remain missing, not fabricated or inferred from daily OHLC.

Constructed candle IDs are `quote-candle-v1:<mode>:<interval>:<UTC opening>` within
source/symbol/type scope. Effective latest raw revisions are ordered by source time
then ingest ID. Aggregate payload lists contributing raw IDs, construction version,
quote-only coverage, and the reason volume is unavailable. Daily cumulative volume
and unsequenced sizes are not converted to interval volume; candle volume is NULL.
Provider-supplied candles remain a separate supported schema type, but this stream
adapter does not ingest them.

`MarketRepository.ingest` wraps quote insertion plus bucket rebuild/candle append in
one immediate transaction. Duplicates skip the rebuild. Timer completion is also
transactional and appends a new revision; late historical observations append another
complete revision while preserving all prior rows. No empty intervals are generated.
Completion means elapsed time, not guaranteed complete market coverage. Persisted
quotes permit restart recovery without reconstructing state from volatile memory.
The content-derived Yahoo identity cannot change source timestamp; enabling future
explicit-ID time corrections requires an old-bucket retraction policy first.

API observations return all raw revisions in ascending ingest ID with `after_id`.
API candles return the latest revision per local producer identity by default;
`revisions=true` includes earlier rows. The limit selects the latest N candle rows,
which are returned chronologically. Each row retains source, mode, identity,
timestamps, revision, completion and metadata. Original reception of a duplicate
stays in the database; later duplicate arrival time is tracked in feed status only.
Recorded fixture replay uses mode recorded; synthetic tests are not live evidence.


## Post-commit WebSocket delivery
Schema and stored rows are unchanged in the WebSocket stage. A repository captures
serialized raw/candle rows in its transaction, commits, then invokes a fanout hook.
Rollback emits no record messages; duplicate raw observations skip record publication.
Candle completion commits publish through the same hook. Browser connection/subscription
changes never write invented market rows. Snapshot requests read the latest existing
quote/candle and set a wire-only snapshot flag, preserving original timestamps/IDs.
Queue loss or browser reconnection does not erase SQLite history; the frontend restores
latest snapshots, while REST remains available for earlier revisions. There is no
socket replay cursor or exactly-once guarantee. All four supported stocks are now
captured through one provider subscription set, with independently constructed buckets.


## Verified deduplication, revisions and late arrivals
Within `(data_source,symbol,observation_type,source_observation_id)`, a duplicate is
identical canonical normalized content, identified by SHA-256. The hashed content
includes source timestamp, OHLCV, candle identity/completion, data mode and full payload;
receipt time, row ID and revision are excluded. JSON object key order is canonical.
Same price alone is never a duplicate rule. Different symbol/source/type/identity,
source time or relevant payload survives. With Yahoo's payload-derived identity, a
changed decoded payload creates a different observation identity rather than claiming
an undocumented provider correction. Without a provider sequence, truly separate but
identical messages cannot be distinguished; this limitation is explicit.

Example: event E price 100/time T inserted twice with different receipt times returns
the original ID once. E2 price 100/time T+1 is a separate observation. Stable explicit
identity E with changed payload becomes revision 2. Redelivery of E's original content
returns revision 1's original ID; it does not allocate revision 3 or replace revision 2.
The unique hash/revision constraints and BEGIN IMMEDIATE make this deterministic across
reconnect and database restart.

Known simulated candle example (tests/test_replay.py): source prices 100 at 15:00:30,
110 at 15:01:10, then late 95 at 15:00:20 and 100 at 15:00:40. The earlier minute becomes
O95/H100/L95/C100, complete revision 4 after its completion and two late revisions.
The 15:01 candle stays 110. Earlier raw observations and candle revisions remain intact.
Source time plus ingest ID determines OHLC; received_timestamp plus ID determines
chronological replay. ID alone preserves commit arrival across clock rollback.
The chart rejects older revisions within an identity, including reordered deliveries.

## Replay reads and integrity audit
ReplayRepository opens SQLite URI mode=ro and PRAGMA query_only=ON. A read transaction
captures MAX(id) and rows together; later live inserts cannot enter that session.
Selection filters symbol, Yahoo source, raw observations plus the requested interval's
constructed/provider candles, receipt UTC [start,end), and ID <= snapshot maximum.
Default sorting is received_timestamp,id; optional arrival sorting is id. Stored UTC
text has fixed microseconds so lexical ordering is chronological. No observation is
inserted, updated or deleted by replay. Original metadata, modes, identities, revision,
completion, source time and receipt time are serialized unchanged.

Window baseline rows are the latest identity revisions strictly before start, bounded
by the snapshot, with up to 1,000 candle identities plus a previous source-time quote.
Arrival mode also excludes IDs at/after the first selected event. Empty selections have
no baseline. The 10,000-event selection bound rejects oversized requests explicitly.
HTTP paging must retain the same range/order/snapshot_max_id across pages.

`python scripts/verify_database.py --db PATH` checks SQLite integrity, foreign keys,
contiguous revision sequences, canonical UTC source/receipt values and hash lengths.
It reports failures and exits nonzero without modifying data. This is not a forensic
recalculation of original hash content (SQLite REAL conversion can erase numeric JSON
representation differences). Schema constraints/triggers and deterministic insertion
and restart tests provide the complementary checks. New receipt-selection indexing is
idempotent; version 1 columns/rows remain unchanged, so no destructive migration was used.
A SQLite-aware backup of 2,138 genuine saved rows passed the audit and retained an
identical ordered-row SHA-256 after browser replay; see evidence/replay-integrity.json.


## Final Part 4.1 persistence check
The final fresh-start/provider audit created 907 rows (450 raw observations plus candle
revisions). Shutdown followed by two idempotent initializations retained identical
ordered-row SHA-256, all timestamps/identities/payloads/revisions, and a passing integrity
audit. Replaying all 228 selected AAPL events twice produced identical rows and no writes.
During a simulated upstream outage, raw count/digest stayed unchanged; legitimate candle
completion remains a recorded constructor revision, not a fabricated provider quote.
No schema change or migration was required in this final review. Actual captured and
simulated-volume verification databases were kept separate and outside the repository.
See evidence/final-database-verification.json and final-outage-integrity.json.

The 2026-11-11 Real-time unverified UI/status update changes no schema, hashes or stored
rows. It is a feed freshness state, not a new data_mode value. Original conservative
provenance remains delayed unless the existing realtime-confirmed configuration was
explicitly established. UI labels distinguish that stored provenance from freshness.

## Simultaneous interval writes — 2026-11-11
One raw quote now commits atomically with its affected 1m, 5m and 15m candle revisions.
The existing interval-bearing constructor identity keeps these histories distinct.
Duplicate raw input writes nothing; late data and timer completion append independently
per interval. Tests verify that a failure in the final (15m) candle rolls back all
preceding raw/1m/5m inserts and emits no events. Schema version, indexes and original
records are unchanged. Old buckets without saved 5m/15m candles are not bulk-backfilled;
a new quote rebuilds its affected buckets from available persisted source observations.
