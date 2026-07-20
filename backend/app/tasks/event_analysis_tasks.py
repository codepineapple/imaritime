"""Async event trajectory analysis, run as a Celery task so the two
DSPy calls (classification, barrier-finding) never block an HTTP request.

Mirrors `app.tasks.brief_tasks`'s pattern: `EventAnalysisJob.status`/
`stage` progress through pending -> classifying -> mapping_trajectory ->
finding_barrier -> completed/failed, polled by the frontend via
`GET /api/v1/event-analysis/{id}`; transient LLM errors are retried
with backoff, permanent errors (no matching historical reports at all)
fail immediately.
"""
from __future__ import annotations

from typing import Any

from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy import update

from app.core.config import get_settings
from app.db.base import AsyncSessionLocal, run_async
from app.db.models import EventAnalysisJob
from app.event_analysis.analyzer import classify_event, find_barrier, map_trajectory
from app.extraction.event_analysis_service import EventAnalysisError
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)
settings = get_settings()


class TransientEventAnalysisError(Exception):
    """Retryable: LLM API errors, timeouts, rate limits."""


class PermanentEventAnalysisError(Exception):
    """Not retryable: job doesn't exist, or no historical reports at all
    match the classified operation/vessel combination."""


async def _update_job(job_id: int, **fields: Any) -> None:
    """Updates an `EventAnalysisJob` row's columns and commits.

    Args:
        job_id: Primary key of the job to update.
        **fields: Column name/value pairs to set.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(update(EventAnalysisJob).where(EventAnalysisJob.id == job_id).values(**fields))
        await session.commit()


async def _run_event_analysis_pipeline(job_id: int, celery_task_id: str) -> dict:
    """Runs the classify -> map trajectory -> find barrier pipeline for one job.

    Args:
        job_id: The `EventAnalysisJob` to process.
        celery_task_id: The Celery task id processing this job.

    Returns:
        A dict with the `job_id`.

    Raises:
        PermanentEventAnalysisError: If the job doesn't exist, or no
            historical reports at all match the classified operation/vessel
            combination.
        TransientEventAnalysisError: If a DSPy call fails in a way that
            looks retryable.
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(EventAnalysisJob, job_id)
        if job is None:
            raise PermanentEventAnalysisError(f"EventAnalysisJob {job_id} not found")
        description = job.description

    # --- Step A: classify ---
    await _update_job(job_id, status="classifying", stage="classifying", celery_task_id=celery_task_id)
    async with AsyncSessionLocal() as session:
        try:
            classification = await classify_event(
                session, description, mlflow_experiment_name=f"{settings.MLFLOW_EXPERIMENT_NAME}-event{job_id}"
            )
        except EventAnalysisError as exc:
            raise TransientEventAnalysisError(str(exc)) from exc

    await _update_job(
        job_id,
        operation_type=classification.operation_type,
        vessel_type=classification.vessel_type,
        event_summary=classification.event_summary,
        severity_stage=classification.severity_stage,
    )

    # --- Step B: map trajectory ---
    await _update_job(job_id, status="mapping_trajectory", stage="mapping_trajectory")
    async with AsyncSessionLocal() as session:
        buckets = await map_trajectory(
            session, classification.operation_type, classification.vessel_type, description
        )

    if buckets.near_miss_count + buckets.serious_count + buckets.fatal_count == 0:
        raise PermanentEventAnalysisError(
            f"No historical reports found for operation_type={classification.operation_type!r}, "
            f"vessel_type={classification.vessel_type!r} -- nothing to compare this event against."
        )

    await _update_job(
        job_id,
        near_miss_count=buckets.near_miss_count,
        serious_count=buckets.serious_count,
        fatal_count=buckets.fatal_count,
        near_miss_report_ids=[{"report_id": m.report.id, "match_type": m.match_type} for m in buckets.near_miss],
        serious_report_ids=[{"report_id": m.report.id, "match_type": m.match_type} for m in buckets.serious],
        fatal_report_ids=[{"report_id": m.report.id, "match_type": m.match_type} for m in buckets.fatal],
    )

    # --- Steps D+E: find the barrier condition and recommend one action ---
    await _update_job(job_id, status="finding_barrier", stage="finding_barrier")
    try:
        findings = find_barrier(
            description,
            classification,
            buckets,
            mlflow_experiment_name=f"{settings.MLFLOW_EXPERIMENT_NAME}-event{job_id}",
        )
    except EventAnalysisError as exc:
        raise TransientEventAnalysisError(str(exc)) from exc

    await _update_job(
        job_id,
        status="completed",
        stage="completed",
        error_message=None,
        analysis_payload=findings.model_dump(mode="json"),
    )

    return {"job_id": job_id}


@celery_app.task(
    bind=True,
    name="app.tasks.event_analysis_tasks.analyze_event",
    autoretry_for=(TransientEventAnalysisError,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)
def analyze_event(self: Task, job_id: int) -> dict:
    """Celery entrypoint: runs one event trajectory analysis end-to-end.

    Args:
        self: The bound task instance (for retry count / task id access).
        job_id: The `EventAnalysisJob` to process.

    Returns:
        A dict with the `job_id`.

    Raises:
        PermanentEventAnalysisError: Re-raised after marking the job failed.
        TransientEventAnalysisError: Re-raised to trigger Celery's automatic retry.
    """
    try:
        return run_async(_run_event_analysis_pipeline(job_id, self.request.id))
    except PermanentEventAnalysisError as exc:
        run_async(_update_job(job_id, status="failed", stage="failed", error_message=str(exc)))
        raise
    except TransientEventAnalysisError as exc:
        attempt = self.request.retries + 1
        run_async(
            _update_job(job_id, error_message=f"Attempt {attempt}/{self.max_retries + 1} failed: {exc}")
        )
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort safeguard
        run_async(
            _update_job(job_id, status="failed", stage="failed", error_message=f"Unexpected error: {exc}")
        )
        raise
