"""Manual paper-only API. No brokerage or automatic signal execution."""
import sqlite3
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from app.routes.market import Symbol
from app.services.paper_account import PaperAccount, OrderConflict, OrderNotFound

router = APIRouter(prefix='/api/paper', tags=['simulated account'])


class ManualOrder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_order_id: str = Field(min_length=1,max_length=100)
    symbol: Symbol
    side: Literal['BUY','SELL']
    quantity: int = Field(strict=True,ge=1,le=1_000_000)
    execution_price: Decimal = Field(gt=0,le=1_000_000,decimal_places=6,allow_inf_nan=False)
    execute_immediately: bool = Field(default=True,strict=True)
    strategy_signal_id: str | None = Field(default=None,min_length=1,max_length=128)


def service(request):
    return PaperAccount(request.app.state.database)


def call(function,*args,**kwargs):
    try:
        return function(*args,**kwargs)
    except OrderNotFound as exc:
        raise HTTPException(404,str(exc)) from exc
    except OrderConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except (sqlite3.Error,OSError) as exc:
        raise HTTPException(503,'Simulated account storage unavailable; retry with the same client_order_id') from exc


@router.get('/account')
def account(request: Request):
    return call(service(request).summary)


@router.get('/positions')
def positions(request: Request):
    data = call(service(request).summary)
    return {key:data[key] for key in ('mode','positions','valuation_complete','valued_at','valuation_note')}


@router.get('/orders')
def orders(request: Request,limit: int=Query(100,ge=1,le=1000)):
    return {'mode':'SIMULATED','orders':call(service(request).orders,limit)}


@router.post('/orders')
def submit(request: Request,body: ManualOrder):
    return call(service(request).submit,**body.model_dump())


@router.post('/orders/{identifier}/execute')
def execute(request: Request,identifier: int=Path(ge=1)):
    return call(service(request).execute,identifier)


@router.post('/orders/{identifier}/cancel')
def cancel(request: Request,identifier: int=Path(ge=1)):
    return call(service(request).cancel,identifier)


@router.get('/fills')
@router.get('/trades')
def fills(request: Request,limit: int=Query(100,ge=1,le=1000)):
    return {'mode':'SIMULATED','fills':call(service(request).fills,limit)}
