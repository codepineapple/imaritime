"""Pydantic DTOs for the intelligence brief job API."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.briefs.generator import MAX_REPORTS_PER_BRIEF
from app.extraction.brief import IntelligenceBrief


class CreateBriefJobRequest(BaseModel):
    """Request body for starting a new brief generation job."""

    report_ids: list[int] = Field(
        min_length=1,
        max_length=MAX_REPORTS_PER_BRIEF,
        description=f"1 to {MAX_REPORTS_PER_BRIEF} report ids to generate a brief from.",
    )


class BriefJobOut(BaseModel):
    """API representation of a `BriefJob` row, including the result once completed."""

    id: int
    report_ids: list[int]
    status: str
    stage: Optional[str] = None
    error_message: Optional[str] = None
    top_causal_signature: Optional[str] = None
    most_representative_report_id: Optional[int] = None
    brief: Optional[IntelligenceBrief] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_model(cls, job) -> "BriefJobOut":
        """Builds a `BriefJobOut` from a `BriefJob` ORM instance.

        Args:
            job: The `BriefJob` row to convert.

        Returns:
            The API representation, with `brief_payload` parsed into a
            structured `IntelligenceBrief` when present.
        """
        return cls(
            id=job.id,
            report_ids=list(job.report_ids),
            status=job.status,
            stage=job.stage,
            error_message=job.error_message,
            top_causal_signature=job.top_causal_signature,
            most_representative_report_id=job.most_representative_report_id,
            brief=IntelligenceBrief.model_validate(job.brief_payload)
            if job.brief_payload
            else None,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
