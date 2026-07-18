"""The `BriefJob` ORM model: tracks async intelligence-brief generation."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB as _JSONB

#: Configured so Python None binds as true SQL NULL, not the JSON null
#: literal (Postgres JSONB defaults to the latter, which then fails
#: jsonb_array_elements_text() with "cannot extract elements from a
#: scalar" -- these columns are all populated from extraction fields
#: that can legitimately be None).
JSONB = _JSONB(none_as_null=True)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BriefJob(Base):
    """Tracks one intelligence-brief generation request through its pipeline.

    A user selects up to 5 reports (after whatever filtering they like)
    on the Incidents page and clicks "Generate Brief" -- this creates a
    `BriefJob` row and enqueues a Celery task, exactly mirroring
    `IngestionJob`'s pending -> ... -> completed/failed lifecycle so the
    frontend can reuse the same "Running/Completed" polling pattern for
    both uploads and briefs.

    Attributes:
        id: Primary key.
        celery_task_id: The Celery task id processing this job.
        report_ids: The (up to 5) report ids this brief was requested for.
        status: One of pending/analyzing/generating/completed/failed.
        stage: The pipeline stage currently running or last attempted.
        error_message: Human-readable error detail, if failed (or the
            reason a transient error is being retried).
        brief_payload: The generated `IntelligenceBrief`, dumped to JSON,
            once completed.
        top_causal_signature: The causal signature the brief centers on.
        most_representative_report_id: The report id used for the vivid
            "pattern that kills" detail.
        created_at: Timestamp this job was created.
        updated_at: Timestamp this job's status was last updated.
    """

    __tablename__ = "brief_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    report_ids: Mapped[list[int]] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stage: Mapped[Optional[str]] = mapped_column(String(32))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    brief_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    top_causal_signature: Mapped[Optional[str]] = mapped_column(String(255))
    most_representative_report_id: Mapped[Optional[int]] = mapped_column(Integer)

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
        return f"<BriefJob id={self.id} status={self.status!r}>"
