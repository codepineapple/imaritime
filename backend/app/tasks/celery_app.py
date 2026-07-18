"""Celery application.

Run the worker with:

    uv run celery -A app.tasks.celery_app worker --loglevel=info

Broker/backend, time limits, etc. all come from `Settings` -- nothing
hardcoded here.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "imaritime",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.ingestion_tasks", "app.tasks.brief_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Progress polling: the frontend polls IngestionJob rows in the database
    # (see app/api/routers/jobs.py), which is the durable source of
    # truth; Celery's own result backend is a secondary/debug view.
    task_track_started=True,
    result_expires=60 * 60 * 24,
    # Safety: don't ack a task until it's actually finished, so a worker
    # crash mid-task lets another worker pick it back up instead of
    # silently losing it.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Hard/soft time limits guard against a stuck Docling/LLM call
    # blocking a worker slot forever.
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=max(settings.CELERY_TASK_TIME_LIMIT - 30, 30),
    # Redis's transport defaults to a 3600s (1 hour) visibility_timeout:
    # if a worker dies mid-task (crash, dev --reload restart, OOM kill),
    # the message sits "delivered but unacked" and invisible to other
    # workers for up to that long before Celery redelivers it -- even
    # though task_acks_late+task_reject_on_worker_lost are meant to
    # handle exactly this. Until that timeout elapses, the job just sits
    # frozen in the DB with no progress and no error ("ghost" jobs).
    # Bounding this just past our own hard task_time_limit means a lost
    # task gets redelivered soon after it would have hit that limit
    # anyway, not up to an hour later.
    broker_transport_options={
        "visibility_timeout": settings.CELERY_TASK_TIME_LIMIT + 120,
    },
)
