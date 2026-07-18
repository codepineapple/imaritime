"""The `IngestionJob` ORM model: tracks a document through the async pipeline."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionJob(Base):
    """Tracks one uploaded source document through the ingestion pipeline.

    Progresses through: pending -> parsing -> extracting -> persisting
    -> embedding -> completed (or failed at any stage). The frontend
    polls this row (not Celery's own result backend, which can expire)
    to show ingestion progress.

    Attributes:
        id: Primary key.
        celery_task_id: The Celery task id processing this job.
        filename: Original uploaded filename.
        content_type: Uploaded file's declared content type.
        source_file_path: Path to the stored source document on disk.
        status: One of pending/parsing/extracting/persisting/embedding/
            completed/failed.
        stage: The pipeline stage currently running or last attempted.
        error_message: Human-readable error detail, if failed (or the
            reason a transient error is being retried).
        parsed_text: Cached Docling/plain-text output, populated after a
            successful parse so a retry doesn't have to re-parse.
        report_id: The resulting `Report`, once persisted.
        created_at: Timestamp this job was created.
        updated_at: Timestamp this job's status was last updated.
    """

    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    filename: Mapped[Optional[str]] = mapped_column(String(512))
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    source_file_path: Mapped[Optional[str]] = mapped_column(String(1024))

    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stage: Mapped[Optional[str]] = mapped_column(String(32))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    parsed_text: Mapped[Optional[str]] = mapped_column(Text)

    report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Returns a debug-friendly representation.

        Returns:
            A string identifying this job by id and status.
        """
        return f"<IngestionJob id={self.id} status={self.status!r}>"
