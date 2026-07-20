"""The document ingestion pipeline, run as a Celery task so file parsing
+ LLM extraction never block an HTTP request.

Progress tracking
------------------
Each stage updates the `IngestionJob` row's `status`/`stage` columns
(pending -> parsing -> extracting -> persisting -> embedding ->
completed | failed). The frontend polls `GET /api/v1/jobs/{id}` to show
progress -- this DB row is the durable source of truth, independent of
Celery's own result backend (which can expire or be cleared).

Retries & safeguards
---------------------
Two distinct exception types drive retry behavior:

- `PermanentIngestionError` -- the input itself is the problem (bad
  file, empty text, extraction output that fails schema validation).
  Retrying won't help; the job is marked "failed" immediately.
- `TransientIngestionError` -- looks like a blip (LLM API error,
  timeout, rate limit). Celery retries these automatically with
  exponential backoff + jitter, up to a bounded number of attempts.

A parsed document's text is cached on the job row after stage 1
succeeds, so a retry triggered by a later stage's transient error
doesn't have to re-run Docling.
"""
from __future__ import annotations

from typing import Any, Optional

from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy import select, update

from app.core.config import get_settings
from app.db import crud, vocab_crud
from app.db.base import AsyncSessionLocal, run_async
from app.db.models import IngestionJob, Report
from app.extraction.service import ExtractionError, extract_report
from app.ingestion.loader import build_report_from_incident
from app.ingestion.parsing import ParsingError, parse_document_to_text
from app.tasks.celery_app import celery_app
from app.vectorstore.embeddings import build_embedding_text, get_embedding_provider
from app.vectorstore.qdrant_store import upsert_report_vector

logger = get_task_logger(__name__)
settings = get_settings()


class TransientIngestionError(Exception):
    """Retryable: network blips, LLM rate limits/timeouts, etc."""


class PermanentIngestionError(Exception):
    """Not retryable: unsupported format, empty document, schema failure."""


async def _update_job(job_id: int, **fields: Any) -> None:
    """Updates an `IngestionJob` row's columns and commits.

    Args:
        job_id: Primary key of the job to update.
        **fields: Column name/value pairs to set.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(update(IngestionJob).where(IngestionJob.id == job_id).values(**fields))
        await session.commit()


async def _get_job(job_id: int) -> Optional[IngestionJob]:
    """Fetches an `IngestionJob` by id.

    Args:
        job_id: Primary key of the job to fetch.

    Returns:
        The matching `IngestionJob`, or None if not found.
    """
    async with AsyncSessionLocal() as session:
        return await session.get(IngestionJob, job_id)


async def _run_pipeline(job_id: int, celery_task_id: str) -> dict:
    """Runs the full parse -> extract -> persist -> embed pipeline for one job.

    Args:
        job_id: The `IngestionJob` to process.
        celery_task_id: The Celery task id processing this job, recorded
            on the job row for cross-referencing.

    Returns:
        A dict with the resulting `report_id` and `job_id`.

    Raises:
        PermanentIngestionError: If the job doesn't exist, the document
            can't be parsed, its text is empty, or the extraction output
            fails schema validation.
        TransientIngestionError: If the extraction call itself fails in
            a way that looks retryable.
    """
    job = await _get_job(job_id)
    if job is None:
        raise PermanentIngestionError(f"IngestionJob {job_id} not found")

    await _update_job(job_id, status="parsing", stage="parsing", celery_task_id=celery_task_id)

    # --- Stage 1: parse (skip if a prior attempt already cached this) ---
    parsed_text = job.parsed_text
    if not parsed_text:
        try:
            parsed_text = parse_document_to_text(job.source_file_path)
        except ParsingError as exc:
            raise PermanentIngestionError(f"Parsing failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise TransientIngestionError(f"Parsing raised an unexpected error: {exc}") from exc

        if not parsed_text or not parsed_text.strip():
            raise PermanentIngestionError("Parsed document text is empty.")

        await _update_job(job_id, parsed_text=parsed_text)

    # --- Stage 2: fetch current vocabulary + run extraction ---
    await _update_job(job_id, status="extracting", stage="extracting")
    async with AsyncSessionLocal() as session:
        vocabulary = await vocab_crud.get_vocabulary_for_signature(session)

    try:
        incident = extract_report(
            parsed_text,
            vocabulary,
            mlflow_experiment_name=f"{settings.MLFLOW_EXPERIMENT_NAME}-job{job_id}",
        )
    except ExtractionError as exc:
        # LLM calls are the textbook "try again" case.
        raise TransientIngestionError(str(exc)) from exc

    # --- Stage 3: persist + sync open-vocabulary terms ---
    await _update_job(job_id, status="persisting", stage="persisting")
    async with AsyncSessionLocal() as session:
        built = build_report_from_incident(
            incident,
            source_filename=job.filename,
            source_file_path=job.source_file_path,
            full_text=parsed_text,
        )
        existing = await crud.get_existing_hashes(session, [built.report.content_hash])
        if existing:
            # Same document already ingested (e.g. re-uploaded, or a
            # retried task that got further than it looked). Not an
            # error -- point the job at the existing report.
            result = await session.execute(
                select(Report.id).where(Report.content_hash == built.report.content_hash)
            )
            report_id = result.scalar_one()
        else:
            await crud.create_report(session, built.report)
            await vocab_crud.sync_vocab_from_report(session, built.report)
            await session.flush()
            report_id = built.report.id
        await session.commit()

    # --- Stage 4: embed + index in Qdrant (best-effort) ---
    await _update_job(job_id, status="embedding", stage="embedding")
    try:
        await _embed_report(report_id)
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: the structured report is already safely persisted;
        # semantic search just won't include it until a future retry /
        # manual re-embed job picks it up.
        logger.warning("Embedding step failed for report %s: %s", report_id, exc)

    await _update_job(job_id, status="completed", stage="completed", report_id=report_id, error_message=None)
    return {"report_id": report_id, "job_id": job_id}


async def _embed_report(report_id: int) -> None:
    """Computes and upserts one report's embedding into Qdrant.

    No-ops if the report doesn't exist or is already indexed.

    Args:
        report_id: The report to embed.
    """
    async with AsyncSessionLocal() as session:
        report = await crud.get_report_by_id(session, report_id)
        if report is None or report.vector_indexed:
            return

        provider = get_embedding_provider()
        text = build_embedding_text(
            {
                "incident_title": report.incident_title,
                "incident_type": report.incident_type,
                "operation_type": report.operation_type,
                "vessel_type": report.vessel_type,
                "location": report.location,
                "casual_signature": report.casual_signature,
                "root_causes": report.root_causes,
                "contributing_factors": report.contributing_factors,
                "lessons_learned": report.lessons_learned,
                "keywords": report.keywords,
                "full_text": report.full_text,
            }
        )
        vector = provider.embed(text)
        upsert_report_vector(
            report_id,
            vector,
            payload={
                "incident_type": report.incident_type,
                "operation_type": report.operation_type,
                "vessel_type": report.vessel_type,
                "incident_title": report.incident_title,
            },
        )
        report.vector_indexed = True
        session.add(report)
        await session.commit()


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion_tasks.process_document",
    autoretry_for=(TransientIngestionError,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)
def process_document(self: Task, job_id: int) -> dict:
    """Celery entrypoint: processes one uploaded document end-to-end.

    Bridges to the async pipeline via `app.db.base.run_async`, since
    Celery tasks are synchronous by default.

    Args:
        self: The bound task instance (for retry count / task id access).
        job_id: The `IngestionJob` to process.

    Returns:
        A dict with the resulting `report_id` and `job_id`.

    Raises:
        PermanentIngestionError: Re-raised after marking the job failed.
        TransientIngestionError: Re-raised to trigger Celery's automatic retry.
    """
    try:
        return run_async(_run_pipeline(job_id, self.request.id))
    except PermanentIngestionError as exc:
        run_async(_update_job(job_id, status="failed", stage="failed", error_message=str(exc)))
        raise
    except TransientIngestionError as exc:
        # Record *why* it's retrying so a polling client can show
        # something more useful than "still processing".
        attempt = self.request.retries + 1
        is_final_attempt = self.request.retries >= self.max_retries
        if is_final_attempt:
            # autoretry_for wraps this whole function -- once retries are
            # exhausted, re-raising here just becomes an unhandled Celery
            # task failure with no code path left to run afterward. Mark
            # it failed now, on this last attempt, rather than leaving the
            # job stuck showing its last in-progress stage until the
            # (much slower) stale-job sweep eventually catches it.
            run_async(
                _update_job(
                    job_id,
                    status="failed",
                    stage="failed",
                    error_message=f"Failed after {attempt} attempt(s): {exc}",
                )
            )
        else:
            run_async(
                _update_job(job_id, error_message=f"Attempt {attempt}/{self.max_retries + 1} failed: {exc}")
            )
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort safeguard
        run_async(
            _update_job(job_id, status="failed", stage="failed", error_message=f"Unexpected error: {exc}")
        )
        raise


@celery_app.task(name="app.tasks.ingestion_tasks.reembed_report")
def reembed_report(report_id: int) -> dict:
    """Standalone task to (re)compute and upsert a single report's vector.

    Useful after switching embedding providers/models, or retrying a
    report whose embedding step failed without re-running extraction.

    Args:
        report_id: The report to re-embed.

    Returns:
        A dict with the `report_id` that was re-embedded.
    """
    run_async(_force_reembed(report_id))
    return {"report_id": report_id}


async def _force_reembed(report_id: int) -> None:
    """Clears a report's indexed flag and re-runs its embedding step.

    Args:
        report_id: The report to re-embed.
    """
    async with AsyncSessionLocal() as session:
        report = await crud.get_report_by_id(session, report_id)
        if report:
            report.vector_indexed = False
            session.add(report)
            await session.commit()
    await _embed_report(report_id)
