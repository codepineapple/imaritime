"""Stale-job reconciliation.

`IngestionJob`, `BriefJob`, and `EventAnalysisJob` all progress through a pending -> ... ->
completed/failed lifecycle driven by a Celery task. Normally, if a
worker dies mid-task, `task_acks_late` + `task_reject_on_worker_lost`
(see `app.tasks.celery_app`) plus a tightened Redis `visibility_timeout`
let another worker pick the task back up. But that's still dependent on
Celery/Redis internals -- if the worker never comes back, Celery isn't
running at all, or some other edge case slips through, a job can be
left sitting in a non-terminal state forever: a "ghost" that never
completes, fails, or shows an error, with no way for the user to know
anything is wrong short of waiting indefinitely.

This module is a safety net that doesn't depend on any of that: any job
that hasn't been updated in `Settings.JOB_STALE_AFTER_SECONDS` and isn't
already in a terminal state is treated as stalled and flipped to
"failed" with a clear message, the next time it's listed. It's called
from the job-listing endpoints (see `app.api.routers.jobs`,
`app.api.routers.briefs`) rather than run as a background sweep, so it
needs no extra infrastructure (no Celery Beat, no cron) -- polling the
list endpoint (which the frontend already does continuously while
anything is running) is what drives it.
"""

from __future__ import annotations

import datetime
from typing import Union

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import BriefJob, IngestionJob, EventAnalysisJob

settings = get_settings()

_TERMINAL_STATUSES = ("completed", "failed")

_STALLED_MESSAGE = (
    "This job stopped making progress and was automatically marked as failed "
    "(no update in over {minutes} minutes -- the worker that was processing it "
    "may have crashed or restarted). Use Retry to try again."
)


async def reconcile_stale_jobs(
    session: AsyncSession, model: Union[type[IngestionJob], type[BriefJob], type[EventAnalysisJob]]
) -> None:
    """Marks any job stuck without progress for too long as failed.

    Args:
        session: Active async DB session (caller commits/rolls back).
        model: `IngestionJob` or `BriefJob` or `EventAnalysisJob` -- all share the
            `status`/`stage`/`error_message`/`updated_at` columns this
            operates on.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(
        seconds=settings.JOB_STALE_AFTER_SECONDS
    )
    minutes = settings.JOB_STALE_AFTER_SECONDS // 60

    await session.execute(
        update(model)
        .where(model.status.notin_(_TERMINAL_STATUSES))
        .where(model.updated_at < cutoff)
        .values(
            status="failed",
            stage="failed",
            error_message=_STALLED_MESSAGE.format(minutes=minutes),
        )
    )
    await session.commit()
