"""Starting, listing, and polling async event trajectory analysis jobs.

A user describes an event in plain language -- this mirrors
`app.api.routers.briefs` exactly, so the frontend can reuse the same
"Running/Completed" polling pattern already used for uploads and briefs.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSessionDep
from app.db.job_reconciliation import reconcile_stale_jobs
from app.db.models import EventAnalysisJob
from app.schemas.event_analysis_schemas import CreateEventAnalysisJobRequest, EventAnalysisJobOut
from app.tasks.event_analysis_tasks import analyze_event

router = APIRouter(prefix="/event-analysis", tags=["event analysis"])


@router.post("", response_model=EventAnalysisJobOut, status_code=202)
async def create_event_analysis_job(
    params: CreateEventAnalysisJobRequest, db: DbSessionDep
) -> EventAnalysisJobOut:
    """Starts a new event trajectory analysis job for a described event.

    Args:
        params: The free-text event description.
        db: Injected DB session.

    Returns:
        The newly created job, initially in "pending" status.
    """
    job = EventAnalysisJob(description=params.description, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async_result = analyze_event.delay(job.id)
    job.celery_task_id = async_result.id
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return EventAnalysisJobOut.from_model(job)


@router.get("", response_model=list[EventAnalysisJobOut])
async def list_event_analysis_jobs(
    db: DbSessionDep, limit: int = Query(100, ge=1, le=500)
) -> list[EventAnalysisJobOut]:
    """Lists event analysis jobs, most recently created first.

    Powers the Event Analysis page's Running/Completed tabs. Before
    listing, reconciles any job that's stopped making progress for too
    long (see `app.db.job_reconciliation`), so a lost worker doesn't
    leave a job frozen forever with no visible error.

    Args:
        db: Injected DB session.
        limit: Maximum number of jobs to return.

    Returns:
        Jobs ordered by creation time, newest first.
    """
    await reconcile_stale_jobs(db, EventAnalysisJob)
    stmt = select(EventAnalysisJob).order_by(EventAnalysisJob.created_at.desc()).limit(limit)
    jobs = (await db.execute(stmt)).scalars().all()
    return [EventAnalysisJobOut.from_model(job) for job in jobs]


@router.get("/{job_id}", response_model=EventAnalysisJobOut)
async def get_event_analysis_job(job_id: int, db: DbSessionDep) -> EventAnalysisJobOut:
    """Fetches one event analysis job's current status, and results once completed.

    Args:
        job_id: Primary key of the job to fetch.
        db: Injected DB session.

    Returns:
        The job's current state, including classification/trajectory/
        findings as each stage completes.

    Raises:
        HTTPException: 404 if no job with that id exists.
    """
    job = await db.get(EventAnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Event analysis job {job_id} not found")
    return EventAnalysisJobOut.from_model(job)


@router.post("/{job_id}/retry", response_model=EventAnalysisJobOut)
async def retry_event_analysis_job(job_id: int, db: DbSessionDep) -> EventAnalysisJobOut:
    """Manually re-enqueues an event analysis job stuck in the "failed" state.

    Args:
        job_id: Primary key of the job to retry.
        db: Injected DB session.

    Returns:
        The job's updated state (now "pending", newly enqueued).

    Raises:
        HTTPException: 404 if no job with that id exists; 409 if the
            job isn't currently "failed".
    """
    job = await db.get(EventAnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Event analysis job {job_id} not found")
    if job.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Event analysis job {job_id} is '{job.status}', not 'failed' -- nothing to retry",
        )

    job.status = "pending"
    job.stage = None
    job.error_message = None
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async_result = analyze_event.delay(job.id)
    job.celery_task_id = async_result.id
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return EventAnalysisJobOut.from_model(job)
