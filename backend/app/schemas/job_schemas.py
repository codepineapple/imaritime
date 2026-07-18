"""Pydantic DTOs for ingestion job status and upload responses."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel


class UploadAcceptedResponse(BaseModel):
    """Response returned immediately after accepting a document upload."""

    job_id: int
    celery_task_id: Optional[str] = None
    status: str
    filename: Optional[str] = None


class IngestionJobOut(BaseModel):
    """API representation of an `app.db.models.IngestionJob` row."""

    id: int
    filename: Optional[str] = None
    content_type: Optional[str] = None
    status: str
    stage: Optional[str] = None
    error_message: Optional[str] = None
    report_id: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class JsonlIngestResult(BaseModel):
    """Summary of a bulk JSON/JSONL ingestion request."""

    total_records: int
    inserted: int
    duplicates: int
    failed: int
    errors: list[str] = []
    embedded: int = 0
