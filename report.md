# MarketPulse — Assignment 4, Part 4.1

Prepared November 11, 2026. Verification results below are from the November 9,
2026 audit; tests were not rerun for this documentation-only report.

## Repository information

Project: MarketPulse — Live Market Workstation
* Repository: [FetrowSchool/Marketpulse](https://github.com/FetrowSchool/Marketpulse)
* Submitted Commit: [bc9ff3c46d25d0036ad29fe7cdc57bd9bcf11f27](https://github.com/FetrowSchool/Marketpulse/commit/bc9ff3c46d25d0036ad29fe7cdc57bd9bcf11f27)


## Project overview

I developed MarketPulse, a web-based stock market dashboard using Vue 3, FastAPI, and SQLite. The app uses Yahoo Finance to retrieve market information and uses WebSockets to communicate updates between the backend and frontend.

My goal for this part was to establish the foundation for trading site by providing market data visualization, database persistence, and historical replay.

## Market Data and Dashboard

The application includes:

* Yahoo Finance market data using yfinance.
* Candlestick charts using TradingView Lightweight Charts.
* Volume visualization.
* Stock symbol selection.
* WebSocket communication between FastAPI and Vue.
* Market data source, timestamps, and status indicators.


The backend processes incoming observations before sending updates to the frontend. The dashboard distinguishes live market observations from delayed, stale, and recorded data.


## Database and Replay

SQLite is used to store market observations and candlestick information.The database preserves  source & recipt timestamps, revisions, and candle completion status. The application handles duplicate observations, revised candles, and out of order updates while preserving historical information. Recorded observations can be retrieved and replayed without requiring an active Yahoo Finance connection. This allows the dashboard to be shown when the market is closed.

## Design Decisions

I separated market data processing from the frontend so the backend could manage external connections, database storage, and WebSocket communication independently. I also chose to preserve previous observation revisions rather than overwriting them. This helps show historical replay and provides a foundation for Part 4.2. 

## Automated testing and startup

| Check | Passed | Failed | Skipped | Result |
| Backend pytest | 117 | 0 | 0 | 8.00 seconds; one existing test-client deprecation warning |
| Frontend Vitest | 24 | 0 | 0 | Seven test files, 770ms |
| Frontend production build | — | 0 | — | Passed, Vite 7.3.7, 385ms |

## limitations

Yahoo Finance data availability depends on market hours, provider connectivity, and potential data delays. The app displays data age and feed status to make these limitations visible.

## Project Files and Documentation

- [README.md](README.md)
- [AGENTS.md](AGENTS.md)
- [design.md](design.md)
- [Architecture Documentation](docs/architecture.md)
- [Database Documentation](docs/database.md)
- [AI Use Disclosure](AI-USE.md)
- [Evidence Log](docs/evidence-log.md)

## Demonstration Recording

Link: https://drive.google.com/file/d/1mtA1E1iMbHI_tH8n0QIRpcC_Jrs9hAi0/view?usp=sharing
