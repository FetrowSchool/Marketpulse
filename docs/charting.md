# Visual workstation and historical/live chart state

## Components
- `MarketChart.vue` owns a single Lightweight Charts chart with candlestick pane 0
  and histogram pane 1, shared UTC time scale, price axes, attribution, loading/error
  overlays, missing-volume explanation and cleanup.
- `chartRenderer.js` adapts canonical candle rows to the supported 5.2.1 chart API.
  It measures initial dimensions before fitting and uses ResizeObserver-driven
  explicit resize, avoiding a first-fit race against asynchronous canvas autosizing.
- `candleBook.js` validates complete OHLC and keeps the highest revision per stable
  producer identity. Its visible window is the latest 1000 candle openings.
- `candleHistory.js` owns HTTP load generations, abort/timeouts and the shared
  historical/live book; no old response replaces current live state.
- `App.vue` integrates selectors, book, WebSocket, feed freshness, saved/live metadata,
  provider price change and last-known price/receipt caches. No chart writes reach SQLite.

## Identity, revision ordering and races
A producer identity combines symbol, source, observation type, data mode, source
observation ID, interval and UTC opening. Revision counters are compared only within
that identity. Duplicate or lower revisions are ignored. If different producer/mode
identities share a time slot, the most recently committed SQLite ID wins that displayed
slot; values are never numerically combined. Original rows/branches remain in SQLite.
The chart footer shows the provenance modes of its displayed rows.

Symbol/interval selection clears chart context immediately, starts the REST request,
and maintains/changes the validated backend symbol subscription. Live events merge
into the same book before/during/after the fetch. Each request captures a generation;
responses from a superseded selection are ignored even if fetch ignores abort.
Subscription acknowledgment/reconnection triggers a catch-up REST load. That load
merges, rather than replaces, records so a stale snapshot cannot overwrite a higher
revision already received over the socket. Requests have a 10-second timeout and
preserve received candles on failure. Disposal invalidates requests and closes resources.

Raw observations update latest quote display. OHLC only changes when the backend's
committed candle_update/candle_completed arrives. This avoids double aggregation,
fabricated volume, and frontend/backend candle divergence. Completion is the stored
backend flag, not a browser clock guess. A late correction updates its own opening,
without replacing newer candles or rewriting any database revision.

Latest quote ordering uses source time and ingest ID. A newer saved candle may provide
an explicitly labeled fallback close; source-ordered raw lineage resolves equal-source
timestamp ties when available. Backend receipt time is cached independently of price
selection, so a late message's receipt remains visible during disconnection.

## Supported chart operations
Initial history/context replacement uses sorted `setData`. Latest/active candles use
incremental `update`. An existing older candle uses `update(bar, true)`, the supported
historical-update API. A previously unseen older candle cannot use that flag: it
requires a sorted data replacement. Removal/window trimming also uses replacement.
Visible UTC time range is restored for such replacements. History completion fits
once per context, and manual Fit view is available; new ticks do not force refitting.
Historical volume whitespace/value transitions safely refresh the volume series.
The chart removes resources and disconnects its ResizeObserver on unmount.

References: [Lightweight Charts series API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi),
[pane API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IPaneApi).

## Volume and missing data
A histogram point is plotted only for finite, nonnegative interval volume with an
explicit reliable-volume metadata contract: volume_reliable=true or
volume_semantics=interval_trade_volume. Zero is accepted only when actually supplied
under that contract. Missing/unverified volume becomes `{time}` whitespace, never zero.
Yahoo day_volume/last_size remain provider metadata and are not chart interval volume.
Current constructed Yahoo candles therefore show an empty aligned pane plus a visible
unavailable explanation. OHLC-incomplete or invalid records are not fabricated into
plot points. Saved-history failure and an empty selection have distinct visible states.

## Intervals and source honesty
The backend constructs 1m, 5m and 15m candles simultaneously from the same quotes.
The selector retrieves saved history and accepts only matching-interval live revisions.
Live capabilities are advertised by live_intervals in symbols/status responses; older
servers without that field retain the configured-interval saved-only fallback. The application does not silently resample,
download provider history, fill gaps or build fake bars to make the chart look full.

Live/delayed/recorded/simulated provenance is retained. Stale/disconnected/unavailable
states keep chart values with last-known labeling and ages advancing. Browser socket
connectivity is separate from Yahoo feed freshness and health. Provider change uses
only supplied change/change_percent fields, rounded for presentation; raw fields stay
unchanged. Currency is shown only when supplied. Recorded playback is now available
through the separate replay controller, transport and revision book (see replay.md).

## Attribution and limits
The built-in TradingView attribution link is enabled, and the creator/NOTICE text is
also visible below the chart and in frontend/THIRD-PARTY-NOTICES.txt. Package version
5.2.1 and dependencies are locked by npm.

This is a latest-1000-opening workstation window, not an unlimited scroll/backfill or
unlimited replay window. The separate replay engine feeds recorded rows to this chart.
It uses stored backend observations, not a complete exchange market
tape; no full session calendar, guaranteed real-time entitlement, split adjustment,
reliable Yahoo quote volume, indicator or trading behavior is added. Browser QA and
unit-test claims are separated in docs/evidence-log.md.

## Automatic recent-candle viewport
App.vue now defaults to 25 visible candles with following enabled and offers 10/25/50/100
presets, a Follow latest toggle and Fit all. MarketChart passes viewport preferences to
chartRenderer, which uses the installed Lightweight Charts setVisibleLogicalRange API.
The logical window ends two positions beyond the newest actual candle. With fewer than
N records it fits available rows; no data or bars are generated for padding. Price and
volume share this time scale. New revisions/candles keep the chosen recent window when
following; turning following off preserves manual navigation. Selection/context changes
focus the new dataset appropriately, including replay restart. Fit all/all-history stops
following. Viewport changes do not change SQLite, provenance or candle aggregation.
