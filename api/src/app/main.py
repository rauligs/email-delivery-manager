from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.settings = get_settings()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
