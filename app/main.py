from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.db.session import check_database_connection

logger = logging.getLogger(__name__)
API_V1_PREFIX = "/api/v1"


def create_app(*, check_database_on_startup: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("service_starting", extra={"service": settings.service_name})
        if check_database_on_startup:
            await check_database_connection(settings.database_url)
            logger.info("database_connection_ready", extra={"service": settings.service_name})
        yield
        logger.info("service_stopping", extra={"service": settings.service_name})

    app = FastAPI(
        title="npm-sentinel",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.include_router(router, prefix=API_V1_PREFIX)
    return app


app = create_app()
