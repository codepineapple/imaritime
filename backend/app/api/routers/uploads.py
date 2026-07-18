"""Two distinct upload paths.

- `POST /uploads/documents` -- a PDF/TXT/MD source document that still
  needs Docling parsing + DSPy extraction. Saved to disk, an
  `IngestionJob` row is created, and a Celery task is enqueued. Returns
  immediately with a job id to poll.
- `POST /uploads/jsonl` -- a JSON/JSONL file of *already-extracted*
  records (bulk backfill / migrating historical data). No LLM call
  needed, so this is handled synchronously and returns a summary
  directly.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import DbSessionDep
from app.core.config import get_settings
from app.db.models import IngestionJob
from app.ingestion.file_validation import (
    UnsupportedFileTypeError,
    validate_file_content,
)
from app.ingestion.jsonl_loader import ingest_jsonl
from app.schemas.job_schemas import JsonlIngestResult, UploadAcceptedResponse
from app.tasks.ingestion_tasks import process_document

router = APIRouter(prefix="/uploads", tags=["uploads"])

settings = get_settings()


@router.post("/documents", response_model=UploadAcceptedResponse, status_code=202)
async def upload_document(
    db: DbSessionDep, file: UploadFile = File(...)
) -> UploadAcceptedResponse:
    """Accepts a PDF/TXT/MD document and enqueues it for background ingestion.

    The file's actual content is validated against its claimed extension
    (magic-byte sniffing, not just the filename) before it's saved or
    queued -- see `app.ingestion.file_validation`.

    Args:
        db: Injected DB session.
        file: The uploaded file.

    Returns:
        The created job's id and initial status.

    Raises:
        HTTPException: 400 if the file's content doesn't genuinely match
            a supported type, or the file is empty; 413 if it's too large.
    """
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_UPLOAD_BYTES} bytes)",
        )
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "upload"
    try:
        validate_file_content(filename, contents)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    suffix = Path(filename).suffix.lower()
    storage_dir = Path(settings.UPLOAD_STORAGE_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / f"{uuid.uuid4().hex}{suffix}"
    stored_path.write_bytes(contents)

    job = IngestionJob(
        filename=filename,
        content_type=file.content_type,
        source_file_path=str(stored_path),
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async_result = process_document.delay(job.id)
    job.celery_task_id = async_result.id
    db.add(job)
    await db.commit()

    return UploadAcceptedResponse(
        job_id=job.id,
        celery_task_id=async_result.id,
        status=job.status,
        filename=job.filename,
    )


@router.post("/jsonl", response_model=JsonlIngestResult)
async def upload_jsonl(
    db: DbSessionDep, file: UploadFile = File(...)
) -> JsonlIngestResult:
    """Bulk-loads pre-extracted JSON/JSONL records directly.

    No parsing or LLM extraction is involved -- e.g. for migrating
    historical data.

    Args:
        db: Injected DB session.
        file: The uploaded JSON/JSONL file.

    Returns:
        A summary of inserted/duplicate/failed records.

    Raises:
        HTTPException: 413 if the file is too large.
    """
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_UPLOAD_BYTES} bytes)",
        )

    result = await ingest_jsonl(db, contents, file.filename or "upload.jsonl")
    await db.commit()
    return JsonlIngestResult(**result.__dict__)
