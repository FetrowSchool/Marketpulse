"""Explicit real-provider probe, outside pytest. Run from backend/.

Prints evidence JSON; an isolated temporary SQLite store is discarded afterward.
A successful handshake alone is NOT successful live-data verification.
"""
import argparse
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.services.database import Database
from app.services.market_data import MarketDataService


async def probe(symbol, seconds):
    started = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="marketpulse-yahoo-probe-") as folder:
        settings = Settings(database_path=Path(folder) / "probe.sqlite3", feed_enabled=True,
                            active_symbol=symbol, max_reconnect_attempts=2,
                            connect_timeout_seconds=10)
        database = Database(settings.database_path)
        database.initialize()
        service = MarketDataService(database, settings)
        service.start()
        try:
            await asyncio.sleep(seconds)
            status = service.status.snapshot(service.clock())
            observations = service.repository.observations(symbol, 100)
            candles = service.repository.candles(symbol, settings.candle_interval, 100)
        finally:
            await service.stop()
        return {"started_at": started.isoformat(), "duration_seconds": seconds,
                "provider_attempt": True, "mocked": False,
                "outcome": "provider_observations_received" if observations else
                    "connected_without_observations" if status["successful_connections"] else "failed_provider_attempt",
                "provider_observations_verified": bool(observations),
                "fresh_live_data_verified": bool(observations) and status["state"] == "live",
                "realtime_entitlement_verified": False,
                "status": status, "observations": observations, "candles": candles}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=["AAPL", "MSFT", "NVDA", "SPY"], default="AAPL")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error("--seconds must be between 1 and 300")
    result = asyncio.run(probe(args.symbol, args.seconds))
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(encoded)
