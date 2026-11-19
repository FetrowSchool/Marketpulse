"""Validated indicator queries and chart/replay as-of evaluation; no persistence writes."""
import sqlite3
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, AwareDatetime, ConfigDict, Field, FiniteFloat
from app.routes.market import Symbol, Interval
from app.services.database import utc_timestamp
from app.services.indicators import CONFIG, evaluate, saved_snapshot

router=APIRouter(prefix='/api/indicators',tags=['indicators'])


class Candle(BaseModel):
    model_config=ConfigDict(extra='ignore')
    id: int=Field(ge=1,strict=True)
    symbol: Symbol
    data_source: Literal['yahoo_finance']
    observation_type: Literal['constructed_candle','provider_candle']
    data_mode: Literal['live','delayed','recorded','simulated']
    source_observation_id: str=Field(min_length=1,max_length=300)
    candle_interval: Interval
    candle_open_timestamp: AwareDatetime
    source_timestamp: AwareDatetime
    received_timestamp: AwareDatetime
    revision: int=Field(ge=1,strict=True)
    candle_complete: bool=Field(strict=True)
    close: FiniteFloat=Field(gt=0,strict=True)

    def record(self):
        value=self.model_dump(mode='json')
        for key in ('candle_open_timestamp','source_timestamp','received_timestamp'):
            value[key]=utc_timestamp(value[key])
        return value


class Evaluation(BaseModel):
    symbol: Symbol
    interval: Interval
    candles: list[Candle]=Field(max_length=1000)


@router.get('/config')
def configuration():
    return CONFIG


@router.post('/evaluate')
def evaluate_chart(body: Evaluation):
    try:
        return evaluate([row.record() for row in body.candles],body.symbol.value,body.interval.value)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


def snapshot(request,symbol,interval,limit,as_of_id):
    selected=symbol.value if symbol else request.app.state.settings.active_symbol
    selected_interval=interval.value if interval else request.app.state.settings.candle_interval
    try:
        return saved_snapshot(request.app.state.database,selected,selected_interval,limit,as_of_id)
    except (sqlite3.Error,OSError) as exc:
        raise HTTPException(503,'Indicator history unavailable') from exc


@router.get('/sma')
def sma(request: Request,symbol: Symbol|None=None,interval: Interval|None=None,
        limit: int=Query(1000,ge=1,le=1000),as_of_id: int|None=Query(None,ge=0)):
    return snapshot(request,symbol,interval,limit,as_of_id)


@router.get('/signals')
def signals(request: Request,symbol: Symbol|None=None,interval: Interval|None=None,
            limit: int=Query(1000,ge=1,le=1000),as_of_id: int|None=Query(None,ge=0)):
    data=snapshot(request,symbol,interval,limit,as_of_id)
    return {key:data[key] for key in ('symbol','interval','configuration','signals','latest','snapshot_max_id')}
