from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request):
    connected = request.app.state.database.is_connected()
    return JSONResponse(status_code=200 if connected else 503, content={
        "status": "ok" if connected else "degraded",
        "database": "connected" if connected else "unavailable",
        "version": request.app.state.settings.version,
    })
