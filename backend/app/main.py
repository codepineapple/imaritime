"""FastAPI application entrypoint.

Run with:

    uv run uvicorn app.main:app --reload --port 8000

(from the project root, so the `.env` file and `app`/`extraction`
packages are found correctly.)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.routers import (
    briefs,
    config,
    groups,
    health,
    jobs,
    reports,
    uploads,
    vocab,
)
from app.core.config import get_settings
from app.vectorstore.embeddings import get_embedding_provider

settings = get_settings()
logger = logging.getLogger("imaritime.startup")


async def _warm_up_embedding_provider() -> None:
    """Triggers the embedding provider's (possibly slow) first construction
    at server startup rather than on whatever request happens to need it
    first.

    Runs in the threadpool and is fired-and-forgotten from `lifespan` --
    deliberately *not* awaited before the server starts accepting
    requests. A model download/load can take anywhere from instant
    (already cached on disk from a previous run) to tens of seconds
    (first run) to indefinite (blocked network) -- blocking server
    startup on it would mean every *other* endpoint (jobs, briefs,
    keyword-only searches, none of which touch embeddings at all) is
    unavailable too while we wait. Instead, this warms the cache in the
    background: if it finishes before a user's first search, that
    search is instant; if not, `app.vectorstore.embeddings
    .get_embedding_provider`'s own bounded-timeout + fail-fast-while-
    initializing logic (see `app.api.routers.reports`) still protects
    that individual request from stalling.
    """
    try:
        await run_in_threadpool(get_embedding_provider)
        logger.info("Embedding provider ready (warmed up at startup).")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Embedding provider failed to initialize at startup (%s). "
            "Semantic search will be unavailable until this succeeds; "
            "keyword search is unaffected.",
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context.

    Schema management is Alembic's job exclusively (`alembic upgrade
    head`, run as part of `python setup.py` / documented in the
    README) -- deliberately not done implicitly here, so the DB schema
    and migration history never drift apart.

    Kicks off the embedding provider warm-up (see
    `_warm_up_embedding_provider`) as a background task rather than
    awaiting it, so the server starts accepting requests immediately
    regardless of how long that takes.

    Args:
        app: The FastAPI application instance.

    Yields:
        None. Control returns to FastAPI to serve requests.
    """
    warm_up_task = asyncio.create_task(_warm_up_embedding_provider())
    try:
        yield
    finally:
        warm_up_task.cancel()


def create_app() -> FastAPI:
    """Builds and configures the FastAPI application.

    Returns:
        A fully configured `FastAPI` instance with CORS and every
        router mounted under `Settings.API_V1_PREFIX`.
    """
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.API_V1_PREFIX
    app.include_router(health.router, prefix=prefix)
    app.include_router(config.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(groups.router, prefix=prefix)
    app.include_router(briefs.router, prefix=prefix)
    app.include_router(uploads.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(vocab.router, prefix=prefix)

    return app


app = create_app()
