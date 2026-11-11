"""Lifecycle, freshness, failure visibility, and bounded reconnect ownership."""
import asyncio
import logging
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo

from app.services.database import utc_timestamp
from app.services.market_repository import MarketRepository
from app.services.normalization import normalize_message, SUPPORTED_SYMBOLS, INTERVALS
from app.services.yahoo_stream import StreamingUnavailable, YahooStream

logger = logging.getLogger(__name__)


class PersistenceFailure(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


async def database_work(function, *args):
    # Finish an in-flight SQLite transaction before shutdown returns.
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


@dataclass
class FeedStatus:
    settings: object
    state: str = "unavailable"
    connected: bool = False
    source_at: datetime | None = None
    received_at: datetime | None = None
    connected_at: datetime | None = None
    successful_connections: int = 0
    attempts: int = 0
    consecutive_failures: int = 0
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    last_error: str | None = None
    last_provider_market_hours: object = None
    database_error: bool = False

    def snapshot(self, now):
        source_age = (now - self.source_at).total_seconds() if self.source_at else None
        receipt_age = (now - self.received_at).total_seconds() if self.received_at else None
        local = now.astimezone(ZoneInfo("America/New_York"))
        regular_window = local.weekday() < 5 and time(9, 30) <= local.time() < time(16)
        session = "regular_window_unverified" if regular_window else "outside_regular_hours"
        if local.weekday() >= 5:
            session = "regular_session_weekend_closed"
        state, reason = self.state, self.last_error
        if self.connected and not self.database_error:
            wait_age = (now - self.connected_at).total_seconds() if self.connected_at else 0
            if source_age is None:
                state = "stale" if wait_age >= self.settings.stale_seconds else "connecting"
                reason = "awaiting_first_observation"
            elif source_age > self.settings.stale_seconds or receipt_age > self.settings.stale_seconds:
                state, reason = "stale", "source_or_receipt_stale"
            elif source_age > self.settings.fresh_seconds or receipt_age > self.settings.fresh_seconds:
                state, reason = "delayed", "source_or_receipt_delayed"
            elif not regular_window:
                state, reason = "real_time_unverified", "outside_regular_trading_window"
            elif not self.settings.realtime_confirmed:
                state, reason = "real_time_unverified", "realtime_entitlement_unverified"
            else:
                # This is stream freshness, NOT a claim that an exchange is open.
                state, reason = "live", "fresh_stream_realtime_confirmed_by_configuration"
        return {"state": state, "reason": reason, "last_error": self.last_error, "symbol": self.settings.active_symbol,
                "data_source": "yahoo_finance", "transport": "yfinance.AsyncWebSocket",
                "transport_connected": self.connected,
                "data_mode": "live" if self.settings.realtime_confirmed else "delayed",
                "candle_origin": "locally_constructed", "interval": self.settings.candle_interval,
                "live_intervals": list(INTERVALS),
                "latest_source_timestamp": utc_timestamp(self.source_at) if self.source_at else None,
                "last_received_timestamp": utc_timestamp(self.received_at) if self.received_at else None,
                "source_data_age_seconds": source_age,
                "seconds_since_receipt": max(0, receipt_age) if receipt_age is not None else None,
                "provider_market_hours": self.last_provider_market_hours,
                "market_session": session, "market_session_verified": False,
                "market_session_note": "US regular-session clock window only; holidays and overnight sessions unverified; freshness does not establish active trading",
                "fresh_seconds": self.settings.fresh_seconds, "stale_seconds": self.settings.stale_seconds,
                "successful_connections": self.successful_connections,
                "connection_attempts": self.attempts, "consecutive_failures": self.consecutive_failures,
                "accepted_observations": self.accepted, "duplicates": self.duplicates,
                "rejected_messages": self.rejected,
                "persistence": "failed" if self.database_error else "no_failure_reported"}


class MarketDataService:
    def __init__(self, database, settings, *, stream_factory=YahooStream, clock=utc_now,
                 sleep=asyncio.sleep):
        self.settings, self.clock, self.sleep = settings, clock, sleep
        self.stream_factory = stream_factory
        self.repository = MarketRepository(database, symbol=settings.active_symbol,
            interval=settings.candle_interval, data_mode="live" if settings.realtime_confirmed else "delayed",
            intervals=(settings.candle_interval, *[key for key in INTERVALS if key != settings.candle_interval]))
        self.repositories = {symbol: MarketRepository(database, symbol=symbol,
            interval=settings.candle_interval, data_mode=self.repository.data_mode, intervals=self.repository.intervals)
            for symbol in SUPPORTED_SYMBOLS}
        self.repositories[settings.active_symbol] = self.repository
        self.symbol_times = {}
        self.status = FeedStatus(settings)
        self.tasks = []
        self.stopping = False
        self.stream = None

    def snapshot(self, symbol=None):
        symbol = symbol or self.settings.active_symbol
        if symbol not in SUPPORTED_SYMBOLS:
            raise ValueError("Unsupported symbol")
        if symbol == self.settings.active_symbol:
            return self.status.snapshot(self.clock())
        values = self.symbol_times.get(symbol, {})
        status = replace(self.status, settings=replace(self.settings, active_symbol=symbol),
                         source_at=values.get("source_at"), received_at=values.get("received_at"),
                         last_provider_market_hours=values.get("market_hours"))
        return status.snapshot(self.clock())

    def start(self):
        if not self.settings.feed_enabled:
            self.status.last_error = "feed_disabled"
            return
        self.status.state = "connecting"
        self.tasks = [asyncio.create_task(self.run(), name="yahoo-feed"),
                      asyncio.create_task(self.complete_loop(), name="candle-completion")]

    async def stop(self):
        self.stopping = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.status.connected = False
        if not self.status.database_error:
            self.status.state = "disconnected"

    def database_failed(self):
        logger.error("Market data persistence failed; feed stopped")
        self.status.database_error = True
        self.status.state, self.status.last_error = "unavailable", "database_error"
        self.status.connected = False

    async def handle_message(self, message):
        receipt = self.clock()
        try:
            symbol = message.get("id") if isinstance(message, dict) else None
            if symbol not in self.repositories:
                raise ValueError("Unsupported Yahoo symbol")
            repository = self.repositories[symbol]
            observation = normalize_message(message, receipt, symbol=symbol,
                data_mode=repository.data_mode, max_future_seconds=self.settings.max_future_seconds)
        except (ValueError, TypeError):
            self.status.rejected += 1
            self.status.last_error = "invalid_provider_message"
            return
        # Source high-water and last receipt belong to the individual symbol.
        source_at = datetime.fromisoformat(observation.source_timestamp.replace("Z", "+00:00"))
        if symbol == self.settings.active_symbol:
            self.status.received_at = receipt
            if self.status.source_at is None or source_at >= self.status.source_at:
                self.status.source_at = source_at
                self.status.last_provider_market_hours = message.get("market_hours")
        else:
            previous = self.symbol_times.setdefault(symbol, {})
            previous["received_at"] = receipt
            if source_at >= previous.get("source_at", source_at):
                previous.update(source_at=source_at, market_hours=message.get("market_hours"))
        try:
            _, inserted = await database_work(repository.ingest, observation, receipt)
        except (sqlite3.Error, OSError) as exc:
            self.database_failed()
            raise PersistenceFailure("Market persistence failed") from exc
        self.status.accepted += int(inserted)
        self.status.duplicates += int(not inserted)
        self.status.last_error = None
        self.status.consecutive_failures = 0

    async def run(self):
        while not self.stopping and not self.status.database_error:
            self.status.state = "connecting"
            self.status.attempts += 1
            try:
                self.stream = self.stream_factory()
                # Subscribe once per provider session, never once per browser.
                symbols = [self.settings.active_symbol, *[symbol for symbol in SUPPORTED_SYMBOLS
                           if symbol != self.settings.active_symbol]]
                await asyncio.wait_for(self.stream.connect(symbols), self.settings.connect_timeout_seconds)
                self.status.connected, self.status.connected_at = True, self.clock()
                self.status.successful_connections += 1
                while not self.stopping:
                    try:
                        message = await self.stream.receive()
                    except ValueError:
                        self.status.rejected += 1
                        self.status.last_error = "invalid_provider_message"
                        continue
                    await self.handle_message(message)
            except asyncio.CancelledError:
                raise
            except StreamingUnavailable:
                self.status.state, self.status.last_error = "unavailable", "streaming_incompatible"
                break
            except PersistenceFailure:
                break
            except Exception as exc:
                logger.warning("Yahoo streaming connection failed (%s)", type(exc).__name__)
                self.status.state, self.status.last_error = "disconnected", "connection_failed"
            finally:
                self.status.connected = False
                if self.stream:
                    try:
                        await asyncio.wait_for(self.stream.close(), self.settings.close_timeout_seconds)
                    except Exception:
                        logger.warning("Yahoo stream close failed or timed out")
                    self.stream = None
            if self.status.database_error:
                break
            self.status.consecutive_failures += 1
            if self.status.consecutive_failures >= self.settings.max_reconnect_attempts:
                self.status.state, self.status.last_error = "unavailable", "reconnect_attempts_exhausted"
                break
            delay = min(self.settings.reconnect_base_seconds * 2 ** (self.status.consecutive_failures - 1),
                        self.settings.reconnect_max_seconds)
            await self.sleep(delay)

    async def complete_loop(self):
        try:
            while not self.stopping:
                for repository in self.repositories.values():
                    await database_work(repository.complete_due, self.clock())
                await self.sleep(self.settings.completion_check_seconds)
        except asyncio.CancelledError:
            raise
        except (sqlite3.Error, OSError):
            self.database_failed()
            for task in self.tasks:
                if task is not asyncio.current_task():
                    task.cancel()
