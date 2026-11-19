# SMA indicators and crossover semantics

## Scope and calculation
This document covers the completed-candle indicator subsystem. The indicator service has no execution callbacks. Manual paper orders/positions are
implemented separately (paper-trading.md); opt-in automatic trading and isolated historical backtesting
are documented in strategy.md/backtesting.md. Existing
Part 4.1 functionality remains available on this branch.

For the chronological sequence of completed candle closes:
`SMA(N,t) = (close[t-N+1] + ... + close[t]) / N`.
Fast N=20 and slow N=50 use the same symbol/interval. Decimal arithmetic over stringified
close values avoids spurious floating equality comparisons; returned chart values are
JSON numbers. No averages are calculated until the respective window has N completed
candles. An incomplete candle returns null SMAs, HOLD and confirmed=false. It is not
included in the window or used to advance the previous completed SMA pair. No provisional
indicators are calculated. An invalid completed close breaks the window explicitly.

Rows first resolve the highest revision per observation identity, then the latest
committed identity per candle opening, matching the chart's canonical slot policy.
Source time determines sorted openings; arrival order does not change the resulting
snapshot. Source/producer type/provenance transitions reset the window so separate
series are not mixed. Missing buckets are skipped, not filled with artificial closes.
The 20/50 periods mean observed completed candles, not guaranteed contiguous clock time.

## Crossing and equality
A crossover requires a previous and a current completed pair of SMAs:
- BUY: previous SMA20 <= SMA50, current SMA20 > SMA50.
- SELL: previous SMA20 >= SMA50, current SMA20 < SMA50.
- HOLD otherwise, including current equality.

The first available SMA50 (completed candle 50) has no previous slow SMA and cannot
confirm a crossover. At least 51 completed candles are required. Leaving equality
counts as a crossing; touching equality alone is HOLD. Staying on one side produces
no repeated directional signals. `confirmed` refers to the crossover/HOLD evaluation,
not exchange real-time entitlement. `candle_complete` and `calculation_mode=completed_only`
indicate the indicator inputs. A confirmed result includes its original candle timestamp.

A pure recalculated snapshot contains at most one result per opening. A stable signal ID
hashes algorithm version, symbol, interval, source/type/mode and candle opening. Direction
is excluded, so late revisions can replace BUY with SELL or retract it to HOLD without
adding duplicate marker identities. Revision metadata refers to the contributing current
candle revision, not a separately persisted indicator revision. Earlier market rows are
never rewritten. Indicator snapshots do not execute orders. The separate manual paper-account ledger
uses persistent order idempotency. Automatic execution is a separate durable strategy,
not a side effect of recalculating these analytical snapshots.
These signals are revision-aware analytical views, not trading recommendations.

## APIs and replay isolation
- `GET /api/indicators/config` returns fixed 20/50 configuration and explicit rules.
- `GET /api/indicators/sma` and `/signals` accept existing symbol/interval enums, limit
  1–1000 (default1000) and optional nonnegative as_of_id. One read-only transaction bounds
  all revision selection at the snapshot ID. A revised future row cannot enter an older
  as-of view. Invalid requests return422, read failures a safe503.
- `POST /api/indicators/evaluate` accepts symbol, interval and up to1000 candle records.
  It validates finite positive closes, UTC-aware timestamps, strict completion booleans,
  positive IDs/revisions and rejects mixed symbols/intervals. It performs no DB reads or
  writes, so replay cannot accidentally consult future live history. Input is chart state,
  not an ingestion endpoint or a source of persisted market evidence.

Responses preserve symbol/source/provenance/interval, opening/source/receipt timestamps,
identity, database ID, revision and completion alongside sma20/sma50, HOLD/BUY/SELL,
confirmation, reason and stable signal_id. `latest` means the latest completed candle's
result, not an instruction to repeat an earlier trade. `signals` contains only confirmed
BUY/SELL crossings. Empty/insufficient histories have null values and no marker.

The frontend sends the revision-aware candle book (arrived replay state or merged live
history) to this backend calculator. Requests are coalesced for100ms; superseded responses
are ignored by generation, and obsolete overlays clear while a revision recalculates.
A failed indicator request shows an error without disabling candles, volume or replay.
Results can lag during rapid playback until a current response is received; pausing or
completion settles the final snapshot. No SMA arithmetic is duplicated in JavaScript.

Two LineSeries share the price pane; createSeriesMarkers attaches confirmed arrows to
candlesticks. Marker arrays and line data are replaced as one derived snapshot, so
historical revisions/retractions are reflected. The visibility toggle clears/restores
both lines and markers. Volume pane, attribution and automatic zoom are retained.

## Independent reference and tests
The test fixture closes 1..50 has:
- SMA20 = sum(31..50)/20 = ((31+50)*20/2)/20 = **40.5**.
- SMA50 = sum(1..50)/50 =1275/50 = **25.5**.

Tests independently use Python Fraction over integer closes1..80 to verify every
available20/50 value, rather than duplicating the Decimal implementation. For50 closes
of100, both averages are100. A next close120 gives SMA20=101 and SMA50=100.4 =>BUY;
a next close80 gives99 and99.6 =>SELL. Keeping the subsequent prices on that side yields
HOLD without another directional event. Equality throughout yields no crossings.

Regression tests cover warm-up, equality, opposite crossings, incomplete completion,
revision replacement/retraction, reverse-order input, duplicate inputs, provenance and
symbol/interval isolation, as-of lookup, API validation/failure and replay without writes.
Frontend tests cover request selection isolation/error handling, completion refresh,
visibility, line/marker data and continued candle/volume renderer operations.

Final verification:132 backend tests passed (one existing test-client deprecation warning),
33 frontend tests passed, production build passed. A read-only check of actual saved Yahoo
candles compared the running API with Fraction averages of the last20/50 completed stored
closes: results matched (SMA20=355.6211, SMA50=355.63564 at that snapshot), with unique
signal IDs. See evidence/part2-indicator-verification.json. This is saved-data evidence,
not a fresh-provider or successful browser-rendering claim. Browser automation's native
connection was unavailable after reset, so visual verification remains outstanding.

## Separate automatic execution service
The indicator API remains pure/read-only and its execution-disabled flag describes that
API. A separate opt-in StrategyService now consumes persisted completed candles and the
same calculator, with a durable execution ledger and subsequent-quote timing. Recomputed
chart markers do not instruct trading. See strategy.md and backtesting.md for the separate execution engines.

## Independent batch/incremental verification
The latest independent Fraction/pandas reference comparison and exact expected values
are documented in verification.md; evidence/sma-reference-verification.json records
measured errors. Absolute tolerance1e-9 USD, relative0; this does not modify strict
Decimal signal equality. Production indicator behavior was unchanged in this stage.
