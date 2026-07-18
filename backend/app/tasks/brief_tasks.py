"""Async intelligence-brief generation, run as a Celery task so a slow
DSPy call never blocks an HTTP request.

Mirrors `app.tasks.ingestion_tasks`'s pattern: `BriefJob.status`/`stage`
progress through pending -> analyzing -> generating -> completed/failed,
polled by the frontend via `GET /api/v1/briefs/{id}`; transient LLM
errors are retried with backoff, permanent errors (bad/missing report
selection) fail immediately.
"""

from __future__ import annotations

from typing import Any

from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy import update

from app.briefs.generator import NoMatchingReportsError, generate_brief_from_reports
from app.core.config import get_settings
from app.db.base import AsyncSessionLocal, run_async
from app.db.models import BriefJob
from app.extraction.brief_service import BriefGenerationError
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)
settings = get_settings()


class TransientBriefError(Exception):
    """Retryable: LLM API errors, timeouts, rate limits."""


class PermanentBriefError(Exception):
    """Not retryable: no valid reports selected, or none has causal_signature data."""


async def _update_job(job_id: int, **fields: Any) -> None:
    """Updates a `BriefJob` row's columns and commits.

    Args:
        job_id: Primary key of the job to update.
        **fields: Column name/value pairs to set.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(BriefJob).where(BriefJob.id == job_id).values(**fields)
        )
        await session.commit()


async def _run_brief_pipeline(job_id: int, celery_task_id: str) -> dict:
    """Runs the gather -> analyze -> generate pipeline for one brief job.

    Args:
        job_id: The `BriefJob` to process.
        celery_task_id: The Celery task id processing this job.

    Returns:
        A dict with the `job_id`.

    Raises:
        PermanentBriefError: If the job doesn't exist, none of its
            report ids resolve, or none has causal_signature data.
        TransientBriefError: If the DSPy call fails in a way that looks retryable.
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(BriefJob, job_id)
        if job is None:
            raise PermanentBriefError(f"BriefJob {job_id} not found")
        report_ids = list(job.report_ids)

    await _update_job(
        job_id, status="analyzing", stage="analyzing", celery_task_id=celery_task_id
    )

    async with AsyncSessionLocal() as session:
        try:
            result = await generate_brief_from_reports(
                session,
                report_ids,
                mlflow_experiment_name=f"{settings.MLFLOW_EXPERIMENT_NAME}-briefjob{job_id}",
            )
        except NoMatchingReportsError as exc:
            raise PermanentBriefError(str(exc)) from exc
        except BriefGenerationError as exc:
            raise TransientBriefError(str(exc)) from exc

        await _update_job(
            job_id,
            status="completed",
            stage="completed",
            error_message=None,
            brief_payload=result.brief.model_dump(mode="json"),
            top_causal_signature=result.top_causal_signature,
            most_representative_report_id=result.most_representative_report_id,
        )

    return {"job_id": job_id}


@celery_app.task(
    bind=True,
    name="app.tasks.brief_tasks.generate_brief",
    autoretry_for=(TransientBriefError,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)
def generate_brief(self: Task, job_id: int) -> dict:
    """Celery entrypoint: generates one intelligence brief end-to-end.

    Args:
        self: The bound task instance (for retry count / task id access).
        job_id: The `BriefJob` to process.

    Returns:
        A dict with the `job_id`.

    Raises:
        PermanentBriefError: Re-raised after marking the job failed.
        TransientBriefError: Re-raised to trigger Celery's automatic retry.
    """
    try:
        return run_async(_run_brief_pipeline(job_id, self.request.id))
    except PermanentBriefError as exc:
        run_async(
            _update_job(job_id, status="failed", stage="failed", error_message=str(exc))
        )
        raise
    except TransientBriefError as exc:
        attempt = self.request.retries + 1
        run_async(
            _update_job(
                job_id,
                error_message=f"Attempt {attempt}/{self.max_retries + 1} failed: {exc}",
            )
        )
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort safeguard
        run_async(
            _update_job(
                job_id,
                status="failed",
                stage="failed",
                error_message=f"Unexpected error: {exc}",
            )
        )
        raise
