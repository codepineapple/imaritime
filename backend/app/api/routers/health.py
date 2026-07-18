"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.vectorstore.embeddings import embedding_provider_status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Reports basic service health/identity, including embedding readiness.

    `embedding_status` reflects whether semantic search is ready to use:
    "ready" (warmed up successfully), "initializing" (still loading,
    e.g. downloading the model), "unavailable" (failed -- keyword search
    still works fine), or "not_started".

    Returns:
        A dict with status, app name, environment, and embedding_status.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "embedding_status": embedding_provider_status(),
    }
