"""Explicit controls for automatic SIMULATED trading; never receives client signals."""
from fastapi import APIRouter,Request
from pydantic import BaseModel,ConfigDict,Field
from app.routes.market import Symbol,Interval
from app.routes.paper import call
from app.services.paper_account import money

router=APIRouter(prefix='/api/strategy',tags=['automatic simulated strategy'])


class Controls(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool=Field(strict=True)
    symbol: Symbol|None=None
    interval: Interval|None=None


@router.get('/status')
def status(request:Request):
    return call(request.app.state.strategy.status)


@router.post('/config')
def configure(request:Request,body:Controls):
    return call(request.app.state.strategy.configure,body.enabled,
                body.symbol.value if body.symbol else None,body.interval.value if body.interval else None)


@router.get('/fills')
def fills(request:Request,symbol:Symbol,interval:Interval):
    rows=call(request.app.state.strategy.fills,symbol.value,interval.value)
    for row in rows:
        row['execution_price']=money(row.pop('execution_price_units'))
    return {'mode':'SIMULATED','symbol':symbol.value,'interval':interval.value,'fills':rows}
