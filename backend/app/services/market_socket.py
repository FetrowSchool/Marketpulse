"""Committed-record fanout; no socket writes occur in ingestion threads."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from app.services.database import utc_timestamp


@dataclass(eq=False)
class MarketClient:
    websocket: object
    symbol: str
    subscription_id: int = 0
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=128))
    closing: asyncio.Event = field(default_factory=asyncio.Event)
    close_code: int = 1000


class MarketSocketHub:
    def __init__(self, market, *, status_seconds=1):
        self.market = market
        self.clients = set()
        self.status_seconds = status_seconds
        self.loop = None
        self.status_task = None
        self.closed = False

    def start(self):
        self.loop = asyncio.get_running_loop()
        self.closed = False
        self.status_task = asyncio.create_task(self.status_loop(), name="market-socket-status")

    async def stop(self):
        self.closed = True
        if self.status_task:
            self.status_task.cancel()
            await asyncio.gather(self.status_task, return_exceptions=True)
        for client in list(self.clients):
            client.close_code = 1012
            client.closing.set()

    def add(self, websocket):
        client = MarketClient(websocket, self.market.settings.active_symbol)
        self.clients.add(client)
        self.send(client, "connection_status", data={"state": "connected", "requires_subscription": True})
        return client

    def remove(self, client):
        self.clients.discard(client)

    def envelope(self, client, kind, *, record=None, data=None):
        status = self.market.snapshot(client.symbol)
        now = self.market.clock()
        source_time = record["source_timestamp"] if record else status["latest_source_timestamp"]
        age = (now - datetime.fromisoformat(source_time.replace("Z", "+00:00"))).total_seconds() if source_time else None
        return {"schema_version": 1, "type": kind, "subscription_id": client.subscription_id,
                "symbol": client.symbol, "source": "yahoo_finance", "sent_timestamp": utc_timestamp(now),
                "event_id": f"observation:{record['id']}" if record else None,
                "source_timestamp": source_time,
                "received_timestamp": record["received_timestamp"] if record else status["last_received_timestamp"],
                "interval": record["candle_interval"] if record else status["interval"],
                "candle_complete": record["candle_complete"] if record else None,
                "revision": record["revision"] if record else None,
                "observation_identity": {key: record[key] for key in
                    ("id", "source_observation_id", "observation_type")} if record else None,
                "data_age_seconds": age, "feed_status": status,
                "data": record if record is not None else (data or {})}

    def send(self, client, kind, *, record=None, data=None):
        if client.closing.is_set() or self.closed:
            return
        try:
            client.queue.put_nowait(self.envelope(client, kind, record=record, data=data))
        except asyncio.QueueFull:
            client.close_code = 1013  # Slow client must reconnect and obtain a SQLite snapshot.
            client.closing.set()

    def publish_records(self, records):
        # Called only after a repository transaction committed, possibly from a worker thread.
        if self.loop and not self.loop.is_closed() and not self.closed:
            self.loop.call_soon_threadsafe(self.deliver_records, records)

    def deliver_records(self, records):
        for record in records:
            kind = "market_observation" if record["observation_type"] == "raw_provider" else (
                "candle_completed" if record["candle_complete"] else "candle_update")
            for client in list(self.clients):
                if client.subscription_id and client.symbol == record["symbol"]:
                    self.send(client, kind, record=record)

    async def status_loop(self):
        while True:
            for client in list(self.clients):
                if client.subscription_id:
                    self.send(client, "feed_status")
            await asyncio.sleep(self.status_seconds)
