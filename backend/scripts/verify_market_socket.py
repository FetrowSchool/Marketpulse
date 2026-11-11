"""Explicit real server/provider pipeline probe; never run by pytest."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from websockets.asyncio.client import connect


async def verify(url, symbol, seconds):
    evidence = {"mocked": False, "websocket_url": url, "symbol": symbol,
                "outcome": "not_verified", "message_counts": {}, "records": [],
                "snapshot_records": [], "started_at": datetime.now(timezone.utc).isoformat(),
                "realtime_entitlement_verified": False}
    try:
        async with connect(url, open_timeout=10) as socket:
            evidence["backend_socket_connected"] = True
            await socket.send(json.dumps({"type": "subscribe", "symbol": symbol, "request_id": 1}))
            deadline = asyncio.get_running_loop().time() + seconds
            while asyncio.get_running_loop().time() < deadline:
                timeout = deadline - asyncio.get_running_loop().time()
                try:
                    frame = json.loads(await asyncio.wait_for(socket.recv(), timeout))
                except TimeoutError:
                    break
                kind = frame["type"]
                evidence["message_counts"][kind] = evidence["message_counts"].get(kind, 0) + 1
                evidence["last_feed_status"] = frame["feed_status"]
                if kind in ("market_observation", "candle_update", "candle_completed"):
                    # Subscription snapshots are saved history, never new-provider proof.
                    key = "snapshot_records" if frame["data"].get("snapshot") else "records"
                    evidence[key].append(frame)
                if any(row["type"] == "market_observation" for row in evidence["records"]) and any(
                        row["type"].startswith("candle_") for row in evidence["records"]):
                    break
        observations = [row for row in evidence["records"] if row["type"] == "market_observation"]
        if observations:
            split = urlsplit(url)
            http_url = ("https" if split.scheme == "wss" else "http") + "://" + split.netloc
            async with httpx.AsyncClient() as client:
                response = await client.get(http_url + "/api/market/observations", params={"symbol": symbol, "after_id": observations[0]["data"]["id"] - 1, "limit": 1})
                response.raise_for_status()
                rows = {row["id"]: row for row in response.json()["observations"]}
            record = observations[0]["data"]
            evidence["database_record_matches_socket"] = record["id"] in rows and all(
                rows[record["id"]][key] == value for key, value in record.items() if key != "snapshot")
            evidence["outcome"] = "provider_to_sqlite_to_websocket_verified" if evidence["database_record_matches_socket"] else "database_match_failed"
        else:
            evidence["outcome"] = "socket_connected_saved_snapshots_only" if evidence["snapshot_records"] else "socket_connected_no_provider_observations"
    except Exception as exc:
        evidence["outcome"], evidence["error_type"] = "connection_failed", type(exc).__name__
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/market")
    parser.add_argument("--symbol", choices=["AAPL", "MSFT", "NVDA", "SPY"], default="AAPL")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error("--seconds must be 1 to 120")
    evidence = asyncio.run(verify(args.url, args.symbol, args.seconds))
    encoded = json.dumps(evidence, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(encoded)
