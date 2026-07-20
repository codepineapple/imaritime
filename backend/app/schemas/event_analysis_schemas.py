"""Pydantic DTOs for the event trajectory analysis job API."""
from __future__ import annotations

import datetime
from typing import Optional

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
    near_miss_report_ids: list[int] = Field(default_factory=list)
    serious_report_ids: list[int] = Field(default_factory=list)
    fatal_report_ids: list[int] = Field(default_factory=list)

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
            near_miss_report_ids=list(job.near_miss_report_ids or []),
            serious_report_ids=list(job.serious_report_ids or []),
            fatal_report_ids=list(job.fatal_report_ids or []),
            findings=EventAnalysisFindings.model_validate(job.analysis_payload)
            if job.analysis_payload
            else None,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
