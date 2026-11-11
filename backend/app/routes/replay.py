"""Replay owns its socket/state and never subscribes to the Yahoo/live hub."""
import asyncio
import json
import sqlite3
import anyio
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, AwareDatetime, ValidationError, ConfigDict

from app.routes.market import Symbol, Interval
from app.services.market_data import database_work
from app.services.replay import ReplayRepository, ReplaySession

router = APIRouter()


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: Symbol
    interval: Interval = Interval.minute
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    order: Literal["receipt", "arrival"] = "receipt"


def repository(app):
    return ReplayRepository(app.state.database)


def load(repo, selection, boundary=None):
    return repo.load(selection.symbol.value, selection.interval.value, selection.start,
                     selection.end, selection.order, boundary)


@router.get("/api/replay/catalog")
def catalog(request: Request, symbol: Symbol, interval: Interval = Interval.minute):
    try:
        return repository(request.app).catalog(symbol.value, interval.value)
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, "Recording database unavailable") from exc


@router.get("/api/replay/records")
def records(request: Request, symbol: Symbol, interval: Interval = Interval.minute,
            start: AwareDatetime | None = None, end: AwareDatetime | None = None,
            order: Literal["receipt", "arrival"] = "receipt", limit: int = Query(100, ge=1, le=1000),
            after_sequence: int = Query(0, ge=0), snapshot_max_id: int | None = Query(None, ge=0)):
    try:
        data = load(repository(request.app), Selection(symbol=symbol, interval=interval, start=start, end=end, order=order), snapshot_max_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, "Recording database unavailable") from exc
    all_records = data.pop("records")
    page = all_records[after_sequence:after_sequence + limit]
    data.pop("baseline")
    return {**data, "records": page, "total": len(all_records), "next_after_sequence": after_sequence + len(page)}


@router.websocket("/ws/replay")
async def replay_socket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in websocket.app.state.settings.cors_origins:
        await websocket.close(code=1008); return
    await websocket.accept()
    session = None
    generation = 0
    receiving = asyncio.create_task(websocket.receive_text())
    loop = asyncio.get_running_loop()
    last_status = 0.0

    async def send(kind, data):
        await asyncio.wait_for(websocket.send_json({"schema_version": 1, "display_mode": "replay",
            "type": kind, "generation": session.generation if session else generation, "data": data}), 5)

    async def send_records(rows):
        for row in rows:
            await send("replay_event", {"record": row})

    async def reset_message():
        await send("replay_loaded", {**session.status(), "baseline": session.recording["baseline"]})

    try:
        await send("replay_status", {"state": "idle", "generation": 0, "position": 0, "total": 0, "speed": 1})
        while True:
            done, _ = await asyncio.wait([receiving], timeout=.02 if session and session.state == "playing" else .2)
            if done:
                try:
                    text = receiving.result()
                    if len(text) > 8192:
                        raise ValueError("Replay request exceeds 8192 characters")
                    request = json.loads(text)
                    if not isinstance(request, dict):
                        raise ValueError("Expected a replay command object")
                    command = request.get("type")
                    if command == "load":
                        selection = Selection.model_validate(request.get("selection"))
                        speed = ReplaySession.validate_speed(request.get("speed", 1))
                        if session:
                            await send_records(session.control("pause", loop.time()))
                        data = await database_work(load, repository(websocket.app), selection)
                        generation = (session.generation if session else generation) + 1
                        session = ReplaySession(data, speed=speed, generation=generation)
                        await reset_message()
                    elif session:
                        rows = session.control(command, loop.time(), request.get("speed"))
                        await send_records(rows)
                        if command in ("restart", "stop"):
                            await reset_message()
                    else:
                        raise ValueError("Load a recording before playback")
                    await send("replay_status", session.status())
                except KeyError:
                    await send("error", {"code": "invalid_replay_request", "message": "Expected a JSON text frame"})
                except (ValueError, TypeError, ValidationError) as exc:
                    message = "Invalid replay selection (supported symbol/interval and timezone-aware range required)" if isinstance(exc, ValidationError) else str(exc)
                    await send("error", {"code": "invalid_replay_request", "message": message})
                except (sqlite3.Error, OSError):
                    await send("error", {"code": "recording_unavailable", "message": "Recording database unavailable"})
                receiving = asyncio.create_task(websocket.receive_text())
            if session:
                rows = session.tick(loop.time())
                await send_records(rows)
                if rows or loop.time() - last_status >= .2:
                    await send("replay_status", session.status()); last_status = loop.time()
    except (WebSocketDisconnect, OSError, TimeoutError, asyncio.CancelledError, RuntimeError):
        pass
    finally:
        with anyio.CancelScope(shield=True):
            receiving.cancel()
            await asyncio.gather(receiving, return_exceptions=True)
            try:
                await asyncio.wait_for(websocket.close(), 2)
            except (RuntimeError, WebSocketDisconnect, OSError, TimeoutError):
                pass
