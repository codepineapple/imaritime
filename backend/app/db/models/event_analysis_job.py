"""The `EventAnalysisJob` ORM model: tracks async event trajectory analysis."""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB as _JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Configured so Python None binds as true SQL NULL, not the JSON null
#: literal -- see the same fix in app/db/models/report.py for why this
#: matters (jsonb_array_elements_text() rejects a stored JSON `null`).
JSONB = _JSONB(none_as_null=True)

#: The three severity buckets a report -- or a freshly-described event --
#: is classified into. Deliberately three, not the four a clinical
#: severity scale might use (near miss / minor / serious / fatal):
#: `Report.injuries`/`Report.fatalities` are plain counts, not a graded
#: severity, so "minor" vs. "serious" isn't a distinction the data can
#: actually support without reprocessing every historical report.
SEVERITY_STAGES = ("near_miss", "serious", "fatal")


class EventAnalysisJob(Base):
    """Tracks one event-trajectory analysis request through its pipeline.

    A user describes an event in plain language (e.g. "Crew member
    entered cargo hold on log carrier, felt dizzy, climbed back out. No
    injury.") -- this creates an `EventAnalysisJob` row and enqueues a
    Celery task, mirroring `BriefJob`'s pending -> ... ->
    completed/failed lifecycle so the frontend can reuse the same
    "Running/Completed" polling pattern already used for uploads and briefs.

    The pipeline: classify the description (operation type, vessel
    type, severity stage) -> find every historical report matching that
    operation/vessel combination and bucket them by severity outcome
    (near_miss / serious / fatal, by `Report.fatalities`/`injuries`) ->
    compare the fatal group's contributing factors against the near-miss
    group's to find the "barrier" condition present in one but not the
    other -> recommend one concrete action.

    Attributes:
        id: Primary key.
        celery_task_id: The Celery task id processing this job.
        description: The user's original free-text event description.
        status: One of pending/classifying/mapping_trajectory/
            finding_barrier/completed/failed.
        stage: The pipeline stage currently running or last attempted.
        error_message: Human-readable error detail, if failed (or the
            reason a transient error is being retried).
        operation_type: Classified operation type (Step A).
        vessel_type: Classified vessel type (Step A).
        event_summary: The model's restated summary of what happened (Step A).
        severity_stage: The described event's own classified severity --
            which of the three sequence stages is "YOU ARE HERE" (Step A).
        near_miss_count: Matching reports classified as near-miss (Step B).
        serious_count: Matching reports classified as serious (Step B).
        fatal_count: Matching reports classified as fatal (Step B).
        near_miss_report_ids: `{"report_id": int, "match_type": str}` entries
            in the near-miss bucket -- `match_type` is "exact" (operation_type/
            vessel_type match), "semantic" (similarity match against the
            description only), or "both".
        serious_report_ids: Same shape as `near_miss_report_ids`, for the serious bucket.
        fatal_report_ids: Same shape as `near_miss_report_ids`, for the fatal bucket.
        analysis_payload: The barrier finding + recommended action
            (Steps D/E), dumped to JSON, once completed.
        created_at: Timestamp this job was created.
        updated_at: Timestamp this job's status was last updated.
    """

    __tablename__ = "event_analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    description: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stage: Mapped[Optional[str]] = mapped_column(String(32))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    operation_type: Mapped[Optional[str]] = mapped_column(String(255))
    vessel_type: Mapped[Optional[str]] = mapped_column(String(255))
    event_summary: Mapped[Optional[str]] = mapped_column(Text)
    severity_stage: Mapped[Optional[str]] = mapped_column(String(32))

    near_miss_count: Mapped[Optional[int]] = mapped_column(Integer)
    serious_count: Mapped[Optional[int]] = mapped_column(Integer)
    fatal_count: Mapped[Optional[int]] = mapped_column(Integer)
    near_miss_report_ids: Mapped[Optional[list[dict]]] = mapped_column(JSONB)
    serious_report_ids: Mapped[Optional[list[dict]]] = mapped_column(JSONB)
    fatal_report_ids: Mapped[Optional[list[dict]]] = mapped_column(JSONB)

    analysis_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Returns a debug-friendly representation.

        Returns:
            A string identifying this job by id and status.
        """
        return f"<EventAnalysisJob id={self.id} status={self.status!r}>"
