"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, chat, documents, health, queries
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.container import Services, build_services

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    services_factory: Callable[[Settings], Services] = build_services,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = services_factory(settings)
        await services.startup()
        app.state.services = services
        logger.info(
            "Attest RAG ready (provider=%s, guardrail_mode=%s, judge=%s)",
            settings.llm_provider,
            settings.guardrail_mode,
            settings.judge_enabled,
        )
        try:
            yield
        finally:
            await services.shutdown()

    app = FastAPI(
        title="Attest RAG API",
        version="1.0.0",
        description="Enterprise document QA with hybrid retrieval and LLM-as-a-Judge evaluation.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, documents, chat, queries, analytics):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
