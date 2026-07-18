"""Traceability wrapper types shared by every field on `MaritimeIncident`.

Every extracted field is wrapped in an `Attribute[T]`, pairing the value
itself with metadata that records where it came from, how confident the
model was, and whether a human needs to double-check it. This is what
lets the API (and the frontend) show provenance/confidence per-field
rather than just a flat structured record.
"""

from __future__ import annotations

from typing import Annotated, Any, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, BeforeValidator, Field

from app.extraction.utils import coerce_string_to_list

T = TypeVar("T")

#: A list field that tolerates the model occasionally returning a bare
#: string instead of a single-item list.
CoercedList = Annotated[List[str], BeforeValidator(coerce_string_to_list)]


def _none_to_empty_list(value: Any) -> Any:
    """Coerces `None` to an empty list; passes any other value through unchanged.

    `EvidenceMetadata.supporting_quotes`/`source_page_numbers` are
    documented as "empty if 'Not Supported'" -- i.e. the model is
    instructed to emit `[]`, not `null`, for an unsupported field. In
    practice, though, hand-authored or legacy JSONL records (bulk
    backfills, migrated historical data -- see
    `app.ingestion.jsonl_loader`) may still have `null` there. Without
    this, that would reject the whole record at ingestion time with a
    "Input should be a valid list" error instead of just treating it as
    "no evidence," which is the same category of gap as the API-response
    side of this (see `app.schemas.report_schemas.NullableStrList`).

    Args:
        value: The raw value being validated.

    Returns:
        `[]` if `value` is `None`, otherwise `value` unchanged (still
        subject to the field's normal list-item validation afterward).
    """
    return [] if value is None else value


#: `List[str]` that also tolerates an explicit `None` (coerced to `[]`),
#: on top of `CoercedList`'s bare-string tolerance.
NullableList = Annotated[List[str], BeforeValidator(_none_to_empty_list)]

#: Same `None`-tolerance as `NullableList`, for the `List[int]` field
#: (`source_page_numbers`).
NullableIntList = Annotated[List[int], BeforeValidator(_none_to_empty_list)]


class StatusMetadata(BaseModel):
    """Tracks the origin and human review state of the extracted information."""

    status: Literal["Official Report Information", "AI Generated", "Not Supported"] = (
        Field(
            description=(
                "The origin of the data. 'Official Report Information' for "
                "explicitly stated facts, 'AI Generated' for derived "
                "intelligence, and 'Not Supported' if the report lacks evidence."
            )
        )
    )
    human_revision_status: Literal["Required", "Not Required"] = Field(
        description=(
            "Flags whether human verification is needed. Set to "
            "'Required' for AI-generated insights, low-confidence "
            "extractions, or unsupported fields."
        )
    )


class ExtractionMetadata(BaseModel):
    """Details the AI's internal process and confidence score."""

    reasoning: str = Field(
        description=(
            "Step-by-step logical explanation of how the value was "
            "extracted or derived. Crucial for 'AI Generated' or "
            "'Not Supported' fields."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score from 0.0 to 1.0. Must be strictly 0.0 if "
            "the status is 'Not Supported'."
        ),
    )


class EvidenceMetadata(BaseModel):
    """Anchors the extracted information to specific parts of the source document."""

    supporting_quotes: NullableList = Field(
        default_factory=list,
        description=(
            "Exact, verbatim quotes extracted directly from the report "
            "text that justify the value. Empty if 'Not Supported'."
        ),
    )
    source_page_numbers: NullableIntList = Field(
        default_factory=list,
        description=(
            "List of integer page numbers where the supporting quotes "
            "are located. Empty if 'Not Supported'."
        ),
    )


class Metadata(BaseModel):
    """Encapsulates all metadata related to the extraction of a single data point."""

    status_metadata: StatusMetadata
    extraction_metadata: ExtractionMetadata
    evidence_metadata: EvidenceMetadata


class Attribute(BaseModel, Generic[T]):
    """A universal wrapper for all extracted fields enforcing traceability."""

    value: Optional[T] = Field(
        description=(
            "The extracted data point or AI-derived intelligence. Must "
            "be NULL/None if status is 'Not Supported'."
        )
    )
    metadata: Metadata
