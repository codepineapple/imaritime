"""Polling and manually retrying ingestion job progress."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSessionDep
from app.db.job_reconciliation import reconcile_stale_jobs
from app.db.models import IngestionJob
from app.schemas.job_schemas import IngestionJobOut
from app.tasks.ingestion_tasks import process_document

router = APIRouter(prefix="/jobs", tags=["ingestion jobs"])


@router.get("", response_model=list[IngestionJobOut])
async def list_jobs(
    db: DbSessionDep, limit: int = Query(100, ge=1, le=500)
) -> list[IngestionJobOut]:
    """Lists ingestion jobs, most recently created first.

    Powers the upload modal's Running/Completed tabs -- the frontend
    splits this single list client-side by `status`. Before listing,
    reconciles any job that's stopped making progress for too long
    (see `app.db.job_reconciliation`) -- so a job whose worker crashed
    or was lost shows up as a clearly-failed, retry-able row instead of
    sitting frozen forever.

    Args:
        db: Injected DB session.
        limit: Maximum number of jobs to return.

    Returns:
        Jobs ordered by creation time, newest first.
    """
    await reconcile_stale_jobs(db, IngestionJob)
    stmt = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
    jobs = (await db.execute(stmt)).scalars().all()
    return [IngestionJobOut.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=IngestionJobOut)
async def get_job(job_id: int, db: DbSessionDep) -> IngestionJobOut:
    """Fetches one ingestion job's current status/stage.

    Args:
        job_id: Primary key of the job to fetch.
        db: Injected DB session.

    Returns:
        The job's current state.

    Raises:
        HTTPException: 404 if no job with that id exists.
    """
    job = await db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return IngestionJobOut.model_validate(job)


@router.post("/{job_id}/retry", response_model=IngestionJobOut)
async def retry_job(job_id: int, db: DbSessionDep) -> IngestionJobOut:
    """Manually re-enqueues a job that's stuck in the "failed" state.

    Useful after fixing an API key or a transient outage that exhausted
    Celery's automatic retries.

    Args:
        job_id: Primary key of the job to retry.
        db: Injected DB session.

    Returns:
        The job's updated state (now "pending", newly enqueued).

    Raises:
        HTTPException: 404 if no job with that id exists; 409 if the
            job isn't currently "failed".
    """
    job = await db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is '{job.status}', not 'failed' -- nothing to retry",
        )

    job.status = "pending"
    job.stage = None
    job.error_message = None
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async_result = process_document.delay(job.id)
    job.celery_task_id = async_result.id
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return IngestionJobOut.model_validate(job)
