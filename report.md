# MarketPulse — Assignment 4, Part 4.2

## Repository information

Project: MarketPulse — Live Market Workstation
* Repository: [FetrowSchool/Marketpulse](https://github.com/FetrowSchool/Marketpulse)
* Submitted Commit: [bc9ff3c46d25d0036ad29fe7cdc57bd9bcf11f27](https://github.com/FetrowSchool/Marketpulse/commit/bc9ff3c46d25d0036ad29fe7cdc57bd9bcf11f27)


## Project overview

For part 2, I exapnded the app by adding technical indicators, simulated trading, and historical backtesting. The app still uses  ue 3, FastAPI, and SQLite while building on the market-data dashboard developed in Part 4.1. The goal of this part was to allow the application to interpret market trends, generate trading signals, and evaluate the results of a trading strategy.

## technical indicators

The app includes two simple moving averages:

* SMA(20), which calculates the average closing price of the previous 20 candles.
* SMA(50), which calculates the average closing price of the previous 50 candles.

Both indicators are displayed on the candlestick chart.

The application detects crossovers between the two moving averages to generate BUY and SELL signals. A BUY signal occurs when SMA(20) crosses above SMA(50), while a SELL signal occurs when SMA(20) crosses below SMA(50).

## Simulated trading 

MarketPulse includes a simulated trading account with a starting balance of $10,000.

The application tracks:

* Available cash
* Open positions
* Orders and fills
* Average purchase price
* Realized profit/loss
* Unrealized profit/loss
* Total account equity
* Trading history

The automated strategy uses confirmed SMA crossover signals to make simulated trading decisions.

When a BUY signal occurs, the strategy uses up to 20% of available cash toward purchasing shares. When a SELL signal occurs, it attempts to sell based on expected profit margins.


## Design Decisions

I separated market data processing from the frontend so the backend could manage external connections, database storage, and WebSocket communication independently. I also chose to preserve previous observation revisions rather than overwriting them. This helps show historical replay and provides a foundation for Part 4.2. 

## Historic backtesting

The application includes a backtesting system that evaluates the SMA crossover strategy using historical market data. The backtesting engine processes historical candles and generates simulated trades based on confirmed crossover signals.

Backtesting results include:

* Starting and ending account equity
* Total return
* Number of trades
* Win rate
* Maximum drawdown
* Trade history
* Equity curve


## limitations

The SMA crossover strategy relies on historical price trends and cannot guarantee profitable trading decisions. Backtesting performance also depend on the availability of historical market data. 

## Project Files and Documentation

- [README.md](README.md)
- [AGENTS.md](AGENTS.md)
- [design.md](design.md)
- [Architecture Documentation](docs/architecture.md)
- [Database Documentation](docs/database.md)
- [SMA and Crossover Rules](docs/indicators.md)
- [Simulated Accounting and Execution Assumptions](docs/paper-trading.md)
- [Automatic SMA Strategy](docs/strategy.md)
- [Backtesting and Limitations](docs/backtesting.md)
- [Latest Verification Record — November 16](docs/testing-2026-11-16.md)
- [Browser Test Cases](docs/browser-test-cases.md)
- [AI Use Disclosure](AI-USE.md)
- [Evidence Log](docs/evidence-log.md)

### Verification evidence

- [Test Summary](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/summary.json)
- [Backend Test Output](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/backend.log)
- [Frontend Test Output](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/frontend.log)
- [Production Build Output](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/build.log)
- [SMA Expected/Actual Reference Values](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/sma-reference.json)
- [Browser Workflow Results and Revised Approaches](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/browser-checks.json)
- [Crossover, Simulated Fill, and Account Screenshot](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/browser-chart-crossover.jpg)
- [Backtest Results, Equity Curve, and Trade History Screenshot](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/browser-backtest-panel.jpg)
- [Backtest Calculation and Trade Data](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/browser-backtest-result.json)
- [Simulated Account, Orders, and Fills Evidence](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/browser-final-account.json)
- [Local CI Configuration Check](https://github.com/FetrowSchool/Marketpulse/blob/codex/part-2/docs/evidence/2026-11-16/ci-local-validation.log)

## Demonstration Recording

Link: https://drive.google.com/file/d/1mtA1E1iMbHI_tH8n0QIRpcC_Jrs9hAi0/view?usp=sharing
