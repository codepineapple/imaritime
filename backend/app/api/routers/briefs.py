"""Starting, listing, and polling async intelligence-brief generation jobs.

A user selects up to 5 reports (after whatever filtering they like) on
the Incidents page and starts a brief generation job -- this mirrors
`app.api.routers.jobs` (ingestion jobs) exactly, so the frontend can
reuse the same "Running/Completed" polling pattern for both.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSessionDep
from app.briefs.generator import MAX_REPORTS_PER_BRIEF
from app.db.job_reconciliation import reconcile_stale_jobs
from app.db.models import BriefJob
from app.schemas.brief_schemas import BriefJobOut, CreateBriefJobRequest
from app.tasks.brief_tasks import generate_brief

router = APIRouter(prefix="/briefs", tags=["intelligence briefs"])


@router.post("", response_model=BriefJobOut, status_code=202)
async def create_brief_job(
    params: CreateBriefJobRequest, db: DbSessionDep
) -> BriefJobOut:
    """Starts a new intelligence-brief generation job for the given reports.

    Args:
        params: The (up to `MAX_REPORTS_PER_BRIEF`) report ids to brief.
        db: Injected DB session.

    Returns:
        The newly created job, initially in "pending" status.

    Raises:
        HTTPException: 400 if more than `MAX_REPORTS_PER_BRIEF` report
            ids are given (also enforced by the request schema).
    """
    if len(params.report_ids) > MAX_REPORTS_PER_BRIEF:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_REPORTS_PER_BRIEF} reports per brief.",
        )

    job = BriefJob(report_ids=params.report_ids, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async_result = generate_brief.delay(job.id)
    job.celery_task_id = async_result.id
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return BriefJobOut.from_model(job)


@router.get("", response_model=list[BriefJobOut])
async def list_brief_jobs(
    db: DbSessionDep, limit: int = Query(100, ge=1, le=500)
) -> list[BriefJobOut]:
    """Lists brief generation jobs, most recently created first.

    Powers the Briefs page's Running/Completed tabs. Before listing,
    reconciles any job that's stopped making progress for too long (see
    `app.db.job_reconciliation`), so a lost worker doesn't leave a job
    frozen forever with no visible error.

    Args:
        db: Injected DB session.
        limit: Maximum number of jobs to return.

    Returns:
        Jobs ordered by creation time, newest first.
    """
    await reconcile_stale_jobs(db, BriefJob)
    stmt = select(BriefJob).order_by(BriefJob.created_at.desc()).limit(limit)
    jobs = (await db.execute(stmt)).scalars().all()
    return [BriefJobOut.from_model(job) for job in jobs]


@router.get("/{job_id}", response_model=BriefJobOut)
async def get_brief_job(job_id: int, db: DbSessionDep) -> BriefJobOut:
    """Fetches one brief job's current status, and its result once completed.

    Args:
        job_id: Primary key of the job to fetch.
        db: Injected DB session.

    Returns:
        The job's current state, including the generated brief once
        `status == "completed"`.

    Raises:
        HTTPException: 404 if no job with that id exists.
    """
    job = await db.get(BriefJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Brief job {job_id} not found")
    return BriefJobOut.from_model(job)


@router.post("/{job_id}/retry", response_model=BriefJobOut)
async def retry_brief_job(job_id: int, db: DbSessionDep) -> BriefJobOut:
    """Manually re-enqueues a brief job that's stuck in the "failed" state.

    Args:
        job_id: Primary key of the job to retry.
        db: Injected DB session.

    Returns:
        The job's updated state (now "pending", newly enqueued).

    Raises:
        HTTPException: 404 if no job with that id exists; 409 if the
            job isn't currently "failed".
    """
    job = await db.get(BriefJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Brief job {job_id} not found")
    if job.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Brief job {job_id} is '{job.status}', not 'failed' -- nothing to retry",
        )

    job.status = "pending"
    job.stage = None
    job.error_message = None
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async_result = generate_brief.delay(job.id)
    job.celery_task_id = async_result.id
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return BriefJobOut.from_model(job)
