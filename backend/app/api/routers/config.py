"""Exposes frontend-relevant runtime configuration.

Some limits are enforced by the backend (and are env-configurable via
`Settings`) but also need to be known by the frontend *before* it
submits a request -- e.g. so it can grey out "Generate Brief" or warn
the user immediately, rather than only finding out from a 400 response
after they've already picked too many reports. Rather than duplicating
the number in a frontend env var (which can silently drift from what
the backend actually enforces), the frontend fetches it from here once
and treats this as the single source of truth.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
async def get_frontend_config() -> dict:
    """Returns the subset of backend settings the frontend needs to know.

    Returns:
        A dict with `max_reports_per_brief` (see
        `Settings.MAX_REPORTS_PER_BRIEF`).
    """
    settings = get_settings()
    return {"max_reports_per_brief": settings.MAX_REPORTS_PER_BRIEF}
