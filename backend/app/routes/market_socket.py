import asyncio
import json
import sqlite3
import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.market_data import database_work
from app.services.normalization import SUPPORTED_SYMBOLS

router = APIRouter()


@router.websocket("/ws/market")
async def market_socket(websocket: WebSocket):
    # HTTP CORS middleware does not enforce WebSocket Origin.
    origin = websocket.headers.get("origin")
    if origin and origin not in websocket.app.state.settings.cors_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    hub = websocket.app.state.market_hub
    if hub.closed:
        await websocket.close(code=1012)
        return
    client = hub.add(websocket)

    async def receive():
        while True:
            try:
                raw = await websocket.receive_text()
            except KeyError:
                hub.send(client, "error", data={"code": "invalid_subscription", "message": "Expected a JSON text frame"})
                continue
            try:
                if len(raw) > 4096:
                    raise ValueError("Message exceeds 4096 characters")
                request = json.loads(raw)
                if not isinstance(request, dict) or request.get("type") != "subscribe":
                    raise ValueError("Expected a subscribe request")
                symbol, identifier = request.get("symbol"), request.get("request_id")
                if symbol not in SUPPORTED_SYMBOLS:
                    raise ValueError("Unsupported symbol; choose AAPL, MSFT, NVDA, or SPY")
                if type(identifier) is not int or not client.subscription_id < identifier <= 2147483647:
                    raise ValueError("request_id must be an increasing positive integer")
            except (ValueError, TypeError) as exc:
                hub.send(client, "error", data={"code": "invalid_subscription", "message": str(exc)})
                continue
            client.symbol, client.subscription_id = symbol, identifier
            # Drop queued old subscription messages; in-flight frames also carry the old ID.
            while not client.queue.empty():
                client.queue.get_nowait()
            hub.send(client, "connection_status", data={"state": "subscribed", "request_id": identifier})
            hub.send(client, "feed_status")
            try:
                repository = hub.market.repositories[symbol]
                quote = await database_work(repository.latest_quote, symbol)
                if client.subscription_id == identifier and quote:
                    hub.send(client, "market_observation", record={**quote, "snapshot": True})
                for interval in repository.intervals:
                    candles = await database_work(repository.candles, symbol, interval, 1)
                    if client.subscription_id == identifier and candles:
                        candle = {**candles[0], "snapshot": True}
                        hub.send(client, "candle_completed" if candle["candle_complete"] else "candle_update", record=candle)
            except (sqlite3.Error, OSError):
                hub.send(client, "error", data={"code": "database_unavailable", "message": "Market snapshot unavailable"})

    async def send():
        while True:
            message = await client.queue.get()
            if message["subscription_id"] == client.subscription_id:
                await asyncio.wait_for(websocket.send_json(message), timeout=5)

    tasks = [asyncio.create_task(receive()), asyncio.create_task(send()),
             asyncio.create_task(client.closing.wait())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        # ASGI servers/TestClient may cancel the session during normal shutdown.
        pass
    finally:
        # Shield cleanup from AnyIO level cancellation so pending writers/readers
        # are actually awaited rather than leaked at context shutdown.
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            hub.remove(client)
            try:
                await asyncio.wait_for(websocket.close(code=client.close_code), timeout=2)
            except (RuntimeError, WebSocketDisconnect, OSError, TimeoutError):
                pass
