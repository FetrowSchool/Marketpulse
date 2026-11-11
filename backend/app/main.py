from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import Settings
from app.routes.health import router
from app.routes.market import router as market_router
from app.services.market_data import MarketDataService
from app.services.database import Database
from app.services.market_socket import MarketSocketHub
from app.routes.market_socket import router as socket_router
from app.routes.replay import router as replay_router


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    database = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        app.state.market_hub.start()
        app.state.market.start()
        try:
            yield
        finally:
            await app.state.market.stop()
            await app.state.market_hub.stop()

    app = FastAPI(title="MarketPulse", version=settings.version, lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.market = MarketDataService(database, settings)
    app.state.market_hub = MarketSocketHub(app.state.market)
    for repository in app.state.market.repositories.values():
        repository.on_commit = app.state.market_hub.publish_records
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET"], allow_headers=["Accept", "Content-Type"])
    app.include_router(router)
    app.include_router(market_router)
    app.include_router(socket_router)
    app.include_router(replay_router)
    return app


app = create_app()
