"""Pydantic DTOs for the reports/search API surface.

Distinct from `app.extraction.incident.MaritimeIncident` (the extraction
schema): these shape what the API actually returns to the frontend
(flattened, paginated, with computed aggregates), not the raw per-field
traceability structure.
"""

from __future__ import annotations

import datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, Field


def _none_to_empty_list(value: Any) -> Any:
    """Coerces `None` to an empty list; passes any other value through unchanged.

    Extraction is explicitly allowed to leave any field -- including
    list-typed ones -- as `None` when the source document simply
    doesn't support it (see `app.extraction.metadata.Attribute.value`
    and the signature's "set the value to None" rule). That `None` is
    stored as-is in the corresponding nullable `Report`/`FieldMetadata`
    JSON column (see `app.ingestion.loader`), so it's a normal, expected
    value coming out of the database -- not a data error.

    Without this, `list[str] = Field(default_factory=list)` would still
    reject an explicit `None`: `default_factory` only applies when a
    field is *missing* from the input, not when it's present and `None`
    (which is exactly what `model_validate(orm_object,
    from_attributes=True)` passes through for a NULL column). Using this
    as a `BeforeValidator` runs it ahead of Pydantic's own list
    validation, so `None` is normalized to `[]` first instead of being
    rejected outright.

    Args:
        value: The raw value being validated (typically from an ORM
            attribute, but also applies to plain dict/JSON input).

    Returns:
        `[]` if `value` is `None`, otherwise `value` unchanged (still
        subject to the field's normal list-item validation afterward).
    """
    return [] if value is None else value


#: A `list[str]` field that tolerates `None` (coerced to `[]`) wherever
#: the underlying column may legitimately be NULL.
NullableStrList = Annotated[list[str], BeforeValidator(_none_to_empty_list)]


def _none_to_zero(value: Any) -> Any:
    """Coerces `None` to `0`; passes any other value through unchanged.

    Same gap as `_none_to_empty_list`, for count fields instead of list
    fields: `injuries`/`fatalities` are extracted with the same "set to
    None if not supported" rule (see `app.extraction.signature`'s rule
    #4), and `Report.injuries`/`Report.fatalities` are nullable columns
    to match. A real extraction returning "not supported" for a
    casualty count is entirely legitimate -- e.g. a report that simply
    doesn't state a number -- so this normalizes that to `0` (the
    sensible display value for "no reported count") rather than
    rejecting the whole row.

    Args:
        value: The raw value being validated.

    Returns:
        `0` if `value` is `None`, otherwise `value` unchanged (still
        subject to the field's normal int validation afterward).
    """
    return 0 if value is None else value


#: An `int` field that tolerates `None` (coerced to `0`) wherever the
#: underlying column may legitimately be NULL.
NullableInt = Annotated[int, BeforeValidator(_none_to_zero)]

#: Same as `NullableStrList`, for the `list[int]` fields (page numbers).
NullableIntList = Annotated[list[int], BeforeValidator(_none_to_empty_list)]


class FieldMetadataOut(BaseModel):
    """API representation of one `app.db.models.FieldMetadata` row."""

    field_name: str
    value: Any
    status: Optional[str] = None
    human_revision_status: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    #: `FieldMetadata.supporting_quotes` is a nullable JSON column --
    #: NullableStrList so a NULL value (rather than an empty list)
    #: doesn't fail validation.
    supporting_quotes: NullableStrList = Field(default_factory=list)
    #: Same nullability concern as `supporting_quotes`, for `source_page_numbers`.
    source_page_numbers: NullableIntList = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    """Row shape for the paginated report table."""

    id: int
    incident_date: Optional[datetime.date] = None
    incident_title: Optional[str] = None
    incident_type: Optional[str] = None
    location: Optional[str] = None
    operation_type: Optional[str] = None
    vessel_type: Optional[str] = None
    casual_signature: Optional[str] = None
    vessel_information: Optional[Any] = None
    injuries: NullableInt = 0
    fatalities: NullableInt = 0
    overall_confidence: Optional[float] = None
    human_review_required: bool = False
    source_filename: Optional[str] = None
    ingested_at: Optional[datetime.datetime] = None
    #: How this result matched the current search, when a free-text query
    #: is active: "keyword", "semantic", "both", or None (no active
    #: free-text query / this endpoint doesn't do hybrid search).
    match_type: Optional[str] = None
    #: Cosine similarity score from Qdrant, if this report was found (at
    #: least in part) via semantic search.
    semantic_score: Optional[float] = None

    model_config = {"from_attributes": True}


class ReportDetail(ReportListItem):
    """Full report detail, including every field's extraction metadata.

    Every `list[str]` field below maps to a `Mapped[Optional[list]]`
    column on `Report` (see `app/db/models/report.py`) -- extraction
    legitimately leaves any of them `None` when the source document
    doesn't support that field, so all of them use `NullableStrList`
    rather than plain `list[str]`. `fields_requiring_review` is
    populated by the loader itself (never NULL in practice), but is
    included here too for defense-in-depth/consistency.
    """

    weather_conditions: Optional[Any] = None
    environmental_factors: Optional[Any] = None
    pollution: Optional[Any] = None
    property_damage: Optional[Any] = None
    equipment_involved: NullableStrList = Field(default_factory=list)
    sequence_of_events: NullableStrList = Field(default_factory=list)
    immediate_causes: NullableStrList = Field(default_factory=list)
    root_causes: NullableStrList = Field(default_factory=list)
    contributing_factors: NullableStrList = Field(default_factory=list)
    human_factors: NullableStrList = Field(default_factory=list)
    technical_failures: NullableStrList = Field(default_factory=list)
    regulatory_issues: NullableStrList = Field(default_factory=list)
    lessons_learned: NullableStrList = Field(default_factory=list)
    corrective_actions: NullableStrList = Field(default_factory=list)
    safety_recommendations: NullableStrList = Field(default_factory=list)
    keywords: NullableStrList = Field(default_factory=list)
    fields_requiring_review: NullableStrList = Field(default_factory=list)
    full_text: Optional[str] = None
    field_metadata: list[FieldMetadataOut] = Field(default_factory=list)


class PaginatedReports(BaseModel):
    """A page of `ReportListItem` results with pagination metadata."""

    items: list[ReportListItem]
    total: int
    page: int
    page_size: int


class StatsOut(BaseModel):
    """Summary statistics for a (possibly filtered) set of reports."""

    total_reports: int
    total_injuries: int
    total_fatalities: int
    human_review_required: int
    avg_confidence: Optional[float] = None


class SearchToken(BaseModel):
    """One field-scoped or global search term.

    Mirrors one entry of `app.db.crud.ReportFilters.field_search_tokens`.
    """

    field: str = "all"
    text: str


class ReportFilterParams(BaseModel):
    """Request body for filtering/searching/paginating reports.

    Mirrors `app.db.crud.ReportFilters`, plus pagination/sort parameters.
    """

    field_search_tokens: list[SearchToken] = Field(default_factory=list)
    date_from: Optional[datetime.date] = None
    date_to: Optional[datetime.date] = None
    min_injuries: Optional[int] = None
    min_fatalities: Optional[int] = None
    confidence_min: Optional[float] = None
    confidence_max: Optional[float] = None
    human_review_required: Optional[bool] = None
    has_data_in: list[str] = Field(default_factory=list)
    operation_types: list[str] = Field(default_factory=list)
    vessel_types: list[str] = Field(default_factory=list)
    casual_signatures: list[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = 25
    sort_by: str = "ingested_at"
    sort_dir: str = "desc"


class SearchSuggestion(BaseModel):
    """One field-tagged autocomplete suggestion."""

    field: str
    text: str


class CausalGroupOut(BaseModel):
    """One group of reports sharing the same operation/vessel/causal-signature value."""

    group_by_field: str
    value: str
    count: int
    total_injuries: int
    total_fatalities: int
    avg_confidence: Optional[float] = None
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    sample_report_ids: list[int] = Field(default_factory=list)


class GroupByRequest(BaseModel):
    """Request body for grouping/recurrence-counting reports.

    Shares its filter fields with `ReportFilterParams`, minus pagination/
    sort (grouping returns ranked groups, not a page of individual reports).
    """

    group_by: str = Field(
        description="One of: operation_type, vessel_type, casual_signature"
    )
    field_search_tokens: list[SearchToken] = Field(default_factory=list)
    date_from: Optional[datetime.date] = None
    date_to: Optional[datetime.date] = None
    min_injuries: Optional[int] = None
    min_fatalities: Optional[int] = None
    confidence_min: Optional[float] = None
    confidence_max: Optional[float] = None
    human_review_required: Optional[bool] = None
    has_data_in: list[str] = Field(default_factory=list)
    operation_types: list[str] = Field(default_factory=list)
    vessel_types: list[str] = Field(default_factory=list)
    casual_signatures: list[str] = Field(default_factory=list)
    limit: int = 20


class ReportIdsRequest(BaseModel):
    """Request body naming a set of reports by id.

    Shared shape for bulk actions (export, bulk delete) triggered from
    a table selection.
    """

    report_ids: list[int] = Field(min_length=1)


class BulkDeleteResult(BaseModel):
    """Summary of a bulk-delete request."""

    deleted: list[int] = Field(default_factory=list)
    not_found: list[int] = Field(default_factory=list)
