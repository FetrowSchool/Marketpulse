"""Validated historical backtests; never invokes the live account or strategy."""
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.routes.market import Symbol, Interval
from app.services.backtests import Backtests
from app.services.database import utc_timestamp

router = APIRouter(prefix='/api/backtests', tags=['isolated backtests'])


class Configuration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: Symbol
    interval: Interval
    start: AwareDatetime
    end: AwareDatetime
    candle_type: Literal['constructed_candle', 'provider_candle'] = 'constructed_candle'
    starting_balance: Decimal = Field(default=Decimal('10000'), gt=0, le=1_000_000, decimal_places=6, allow_inf_nan=False)
    fast_period: int = Field(default=20, strict=True, ge=1, le=499)
    slow_period: int = Field(default=50, strict=True, ge=2, le=500)

    @model_validator(mode='after')
    def order(self):
        if self.start >= self.end:
            raise ValueError('Start must precede end')
        if self.fast_period >= self.slow_period:
            raise ValueError('Fast SMA must be less than slow SMA')
        return self

    def configuration(self):
        return {'symbol': self.symbol.value, 'interval': self.interval.value,
                'start': utc_timestamp(self.start), 'end': utc_timestamp(self.end),
                'candle_type': self.candle_type, 'starting_balance': str(self.starting_balance),
                'fast_period': self.fast_period, 'slow_period': self.slow_period}


def call(function, *args):
    try:
        return function(*args)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, 'Backtest storage unavailable') from exc


@router.post('')
def run(request: Request, body: Configuration):
    return call(Backtests(request.app.state.database).run, body.configuration())


@router.get('')
def history(request: Request, limit: int = Query(20, ge=1, le=100)):
    return {'mode': 'BACKTEST · SIMULATED', 'runs': call(Backtests(request.app.state.database).list, limit)}


@router.get('/{identifier}')
def result(request: Request, identifier: int = Path(ge=1)):
    value = call(Backtests(request.app.state.database).get, identifier)
    if value is None:
        raise HTTPException(404, 'Backtest not found')
    return value


@router.get('/{identifier}/chart')
def chart(request: Request, identifier: int = Path(ge=1)):
    value = call(Backtests(request.app.state.database).chart, identifier)
    if value is None:
        raise HTTPException(404, 'Backtest not found')
    return value
