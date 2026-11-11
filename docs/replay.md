# Deterministic recorded replay

Replay is read-only presentation of saved observations, separate from Yahoo and the
live `/ws/market` connection. No runtime sample-data generator/importer is included.
An empty database shows an empty selection. Actual saved Yahoo observations retain
their original delayed/live provenance; simulated test fixtures remain simulated.
The envelope and interface explicitly label presentation **REPLAY · RECORDED**.

## Selection and ordering
Supported symbols: AAPL, MSFT, NVDA, SPY; intervals: 1m, 5m, 15m. Records include raw
observations and selected-interval candle revisions from yahoo_finance. Time bounds
are optional timezone-aware UTC receipt times `[start,end)`; source time is preserved,
not used as the receipt filter. Default order is `(received_timestamp,id)` ascending.
Equal receipts use the stable unique database ID. `arrival` orders by ID to reproduce
commit arrivals when receipt clocks roll backward. Neither order sorts by source time.

Each load executes one read transaction, captures MAX(id), and materializes at most
10,000 immutable rows. Oversized selections fail explicitly; narrow the time range.
Later live writes do not enter the session. A pre-start baseline contains prior
latest candle revisions (up to 1,000 identities) plus a prior source-time quote;
it excludes future revisions. Arrival mode additionally bounds baseline IDs below the
first selected arrival. No rows means no baseline. Baseline is initialization context,
not counted as playback events. The frontend defaults to the latest 15 recorded minutes.
The chart displays up to 1,000 openings and never pads gaps with prices or zero volume.

## HTTP
- `GET /api/replay/catalog?symbol=AAPL&interval=1m` returns event_count,
  first_receipt, last_receipt, selected-source snapshot_max_id, max_events and range_clock.
- `GET /api/replay/records?symbol=AAPL&interval=1m&order=receipt&limit=100`
  accepts optional aware start/end, after_sequence (zero-based consumed count) and
  snapshot_max_id. It returns records, total, next_after_sequence and selection metadata.
  Retain the returned snapshot_max_id and identical selection when fetching later pages.
  The records endpoint does not include the baseline; the socket's loaded message does.
- Invalid symbol/interval/range/cursor/limit is 422. Database read failure is 503 with
  a safe message. This endpoint never creates recordings.

## WebSocket `/ws/replay`
The same explicit local browser Origin policy applies as to live sockets. Each client
owns a separate session; no Yahoo subscription or live-hub queue is created.

Client commands:
```json
{"type":"load","selection":{"symbol":"AAPL","interval":"1m","start":"2026-11-09T04:48:02Z","end":"2026-11-09T05:03:02Z","order":"receipt"},"speed":10}
{"type":"play"}
{"type":"pause"}
{"type":"resume"}
{"type":"speed","speed":100}
{"type":"restart"}
{"type":"stop"}
```
Speed is a finite JSON number from 0.25 through 100, excluding booleans. Commands
are text JSON objects, capped at 8,192 characters. Load must precede controls.

Server envelope:
```text
{
  schema_version: 1,
  display_mode: "replay",
  type: replay_loaded | replay_event | replay_status | error,
  generation: integer,
  data: type-specific payload
}
```
- `replay_loaded`: session status plus `baseline` serialized original database rows.
  Also emitted after Restart/Stop so future displayed state can be cleared.
- `replay_event`: `{record: original_serialized_database_row}`. Identity, ID, revision,
  type, symbol, source, interval/completion, source_timestamp, received_timestamp,
  data_mode, price/OHLCV and metadata retain their stored meaning and missing values.
  There is no invented source timestamp for a status/control envelope.
- `replay_status`: state, generation, speed, position, total, progress, duration_seconds,
  elapsed_seconds, playhead_receipt_timestamp, playhead_source_timestamp, last_record_id,
  symbol, interval, start/end, order and snapshot_max_id. Before loading, idle status
  contains only state/generation/position/total/speed. Playhead fields are null before
  the first playback event. Progress counts rows, not candles or elapsed time.
- `error`: code and message (`invalid_replay_request` or `recording_unavailable`).
  No private database path or SQL details are exposed.

## State and timing
Load starts ready; Play starts/resumes. Pause freezes the cursor and virtual clock.
Resume excludes paused wall time. Speed changes first settle elapsed playback at the
old speed. Restart returns to the same frozen selection and baseline, increments
generation and starts playing. Stop resets to baseline/cursor zero and remains stopped.
Play after completion is mapped to Restart by the UI. Empty playback completes with
zero records; it does not fabricate an event. Changing the range pauses playback and
requires reload before Play. First selected event is immediate; pacing is cumulative
nonnegative consecutive receipt gaps divided by speed, using an injected monotonic
clock. Arrival-mode negative gaps are clamped to zero. Up to 100 due rows drain per
loop; stable ordering is retained even when several rows are due together.

The frontend rejects older generations and closes/disposes its live socket/history
while replaying. Restart clears the book and resets chart context. Returning to Live
clears replay data, restores latest REST history and resubscribes to the market socket.
Yahoo unavailability cannot stop recorded playback. Backend/transport loss does end
the in-memory session: the interface preserves displayed rows, reports the error and
requires explicit Load selection to start a new session. Sessions are not durable;
there is no seek, automatic cursor recovery, or cross-process session migration.

Candles are original committed constructor/provider revisions, not recomputed with
today's clock. Incomplete candles remain incomplete until a recorded completion arrives.
Higher revisions update their correct historical bar; lower revisions cannot replace
them. Reliable interval volume uses the existing explicit metadata contract. Yahoo
quote totals/unsequenced sizes remain metadata and never become invented volume bars.
Source age during replay uses recorded playhead receipt minus visible source time;
this is recorded latency, not freshness now. Original provenance remains visible.
