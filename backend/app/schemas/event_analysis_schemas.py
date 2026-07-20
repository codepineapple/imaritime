"""Pydantic DTOs for the event trajectory analysis job API."""
from __future__ import annotations

import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.extraction.event_analysis import EventAnalysisFindings


class CreateEventAnalysisJobRequest(BaseModel):
    """Request body for starting a new event trajectory analysis job."""

    description: str = Field(
        min_length=1,
        max_length=4000,
        description="Plain-language description of the event, e.g. 'Crew member entered "
        "cargo hold on log carrier, felt dizzy, climbed back out. No injury.'",
    )


class MatchedReportRef(BaseModel):
    """One report in a severity bucket, tagged with how it matched the described event."""

    report_id: int
    match_type: Literal["exact", "semantic", "both"] = Field(
        description="'exact' (operation_type/vessel_type match), 'semantic' "
        "(similarity match against the description only), or 'both'."
    )


def _parse_matched_report_ref(raw: object) -> MatchedReportRef:
    """Parses one stored bucket entry, tolerating the pre-semantic-search shape.

    Before semantic matching was added, `near_miss_report_ids`/
    `serious_report_ids`/`fatal_report_ids` stored plain `list[int]` --
    JSONB has no schema enforcement, so any `EventAnalysisJob` row
    created before that change still has that old shape sitting in the
    database. Rather than requiring those rows to be deleted or
    migrated, a bare int is treated as an "exact" match (the only kind
    that existed at the time it was stored).

    Args:
        raw: One entry from a stored bucket list -- either an int (the
            old shape) or a `{"report_id": int, "match_type": str}`
            dict (the current shape).

    Returns:
        The parsed `MatchedReportRef`.
    """
    if isinstance(raw, dict):
        return MatchedReportRef(**raw)
    return MatchedReportRef(report_id=raw, match_type="exact")


class EventAnalysisJobOut(BaseModel):
    """API representation of an `EventAnalysisJob` row, including results once completed."""

    id: int
    description: str
    status: str
    stage: Optional[str] = None
    error_message: Optional[str] = None

    operation_type: Optional[str] = None
    vessel_type: Optional[str] = None
    event_summary: Optional[str] = None
    severity_stage: Optional[str] = None

    near_miss_count: Optional[int] = None
    serious_count: Optional[int] = None
    fatal_count: Optional[int] = None
    near_miss_reports: list[MatchedReportRef] = Field(default_factory=list)
    serious_reports: list[MatchedReportRef] = Field(default_factory=list)
    fatal_reports: list[MatchedReportRef] = Field(default_factory=list)

    findings: Optional[EventAnalysisFindings] = None

    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_model(cls, job) -> "EventAnalysisJobOut":
        """Builds an `EventAnalysisJobOut` from an `EventAnalysisJob` ORM instance.

        Args:
            job: The `EventAnalysisJob` row to convert.

        Returns:
            The API representation, with `analysis_payload` parsed into
            structured `EventAnalysisFindings` when present.
        """
        return cls(
            id=job.id,
            description=job.description,
            status=job.status,
            stage=job.stage,
            error_message=job.error_message,
            operation_type=job.operation_type,
            vessel_type=job.vessel_type,
            event_summary=job.event_summary,
            severity_stage=job.severity_stage,
            near_miss_count=job.near_miss_count,
            serious_count=job.serious_count,
            fatal_count=job.fatal_count,
            near_miss_reports=[_parse_matched_report_ref(r) for r in (job.near_miss_report_ids or [])],
            serious_reports=[_parse_matched_report_ref(r) for r in (job.serious_report_ids or [])],
            fatal_reports=[_parse_matched_report_ref(r) for r in (job.fatal_report_ids or [])],
            findings=EventAnalysisFindings.model_validate(job.analysis_payload)
            if job.analysis_payload
            else None,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
