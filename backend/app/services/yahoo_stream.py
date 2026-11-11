"""Version-isolated yfinance streaming adapter; no historical polling fallback.

1.8.0 listen() swallows failures and owns a fixed-delay reconnect loop. To make
MarketPulse the sole retry owner we retain public subscribe/close but use the
inspected _ws receive and _decode_message seams. Fail closed on version changes.
"""
import asyncio
import json


class StreamingUnavailable(RuntimeError):
    pass


class YahooStream:
    def __init__(self):
        try:
            import yfinance as yf
        except ImportError as exc:
            raise StreamingUnavailable("yfinance is not installed") from exc
        if yf.__version__ != "1.8.0" or not hasattr(yf, "AsyncWebSocket"):
            raise StreamingUnavailable("Unsupported yfinance streaming version; expected 1.8.0")
        self.client = yf.AsyncWebSocket(verbose=False)

    async def connect(self, symbol):
        await self.client.subscribe([symbol] if isinstance(symbol, str) else symbol)
        if not callable(getattr(self.client._ws, "recv", None)) or not callable(
                getattr(self.client, "_decode_message", None)):
            raise StreamingUnavailable("yfinance streaming compatibility check failed")

    async def receive(self):
        envelope = json.loads(await self.client._ws.recv())
        if not isinstance(envelope, dict) or not isinstance(envelope.get("message"), str):
            raise ValueError("Invalid Yahoo WebSocket envelope")
        result = self.client._decode_message(envelope["message"])
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("Invalid Yahoo protobuf payload")
        return result

    async def close(self):
        await self.client.close()
        heartbeat = self.client._heartbeat_task
        if heartbeat:
            await asyncio.gather(heartbeat, return_exceptions=True)
