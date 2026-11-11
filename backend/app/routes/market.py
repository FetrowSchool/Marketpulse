"""Validated, read-only market API. No chart or broadcast transport."""
import sqlite3
from enum import Enum
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/market", tags=["market"])


class Symbol(str, Enum):
    AAPL = "AAPL"
    MSFT = "MSFT"
    NVDA = "NVDA"
    SPY = "SPY"


class Interval(str, Enum):
    minute = "1m"
    five_minutes = "5m"
    fifteen_minutes = "15m"


@router.get("/status")
def market_status(request: Request):
    service = request.app.state.market
    return service.status.snapshot(service.clock())


@router.get("/symbols")
def symbols(request: Request):
    return {"symbols": [symbol.value for symbol in Symbol],
            "active_symbol": request.app.state.settings.active_symbol,
            "active_interval": request.app.state.settings.candle_interval,
            "live_intervals": list(request.app.state.market.repository.intervals),
            "intervals": [interval.value for interval in Interval]}


def read_market(function, *args):
    try:
        return function(*args)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(status_code=503, detail="Market database unavailable") from exc


@router.get("/observations")
def observations(request: Request, symbol: Symbol | None = None,
                 limit: int = Query(100, ge=1, le=1000), after_id: int = Query(0, ge=0)):
    selected = symbol.value if symbol else request.app.state.settings.active_symbol
    rows = read_market(request.app.state.market.repository.observations, selected, limit, after_id)
    return {"symbol": selected, "order": "ingest_id", "observations": rows,
            "next_after_id": rows[-1]["id"] if rows else after_id}


@router.get("/candles")
def candles(request: Request, symbol: Symbol | None = None, interval: Interval | None = None,
            limit: int = Query(100, ge=1, le=1000), revisions: bool = False):
    selected = symbol.value if symbol else request.app.state.settings.active_symbol
    selected_interval = interval.value if interval else request.app.state.settings.candle_interval
    rows = read_market(request.app.state.market.repository.candles, selected, selected_interval, limit, revisions)
    return {"symbol": selected, "interval": selected_interval, "candle_origin": "locally_constructed",
            "volume_available": False, "includes_revisions": revisions, "candles": rows}
