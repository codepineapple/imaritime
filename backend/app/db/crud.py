"""Async data-access layer for reports.

Every function is a plain `async def` taking an `AsyncSession` --
callable directly from FastAPI route handlers (via dependency
injection) or from Celery tasks (via `app.db.base.run_async`).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from sqlalchemy import Select, and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FieldMetadata, IngestionJob, Report, VocabularyTerm

LIST_FIELDS = [
    "equipment_involved",
    "sequence_of_events",
    "immediate_causes",
    "root_causes",
    "contributing_factors",
    "human_factors",
    "technical_failures",
    "regulatory_issues",
    "lessons_learned",
    "corrective_actions",
    "safety_recommendations",
    "keywords",
]

SCALAR_TEXT_FIELDS = [
    "incident_title",
    "incident_type",
    "location",
    "operation_type",
    "vessel_type",
    "casual_signature",
]

JSON_ANY_FIELDS = [
    "vessel_information",
    "weather_conditions",
    "environmental_factors",
    "pollution",
    "property_damage",
]

SORTABLE_COLUMNS = {
    "id": Report.id,
    "incident_title": Report.incident_title,
    "incident_type": Report.incident_type,
    "incident_date": Report.incident_date,
    "location": Report.location,
    "operation_type": Report.operation_type,
    "vessel_type": Report.vessel_type,
    "casual_signature": Report.casual_signature,
    "injuries": Report.injuries,
    "fatalities": Report.fatalities,
    "overall_confidence": Report.overall_confidence,
    "human_review_required": Report.human_review_required,
    "ingested_at": Report.ingested_at,
}

_TEXT_TYPE = Report.__table__.c.location.type


def _field_condition(field_name: str, like: str):
    """Builds a SQL condition matching a field regardless of its storage shape.

    Args:
        field_name: Name of the `Report` field to match against.
        like: An already-lowercased SQL `LIKE` pattern (with `%` wildcards).

    Returns:
        A SQLAlchemy condition, or None if `field_name` isn't recognized.
    """
    if field_name in SCALAR_TEXT_FIELDS:
        return func.lower(getattr(Report, field_name)).like(like)

    if field_name in JSON_ANY_FIELDS:
        col = getattr(Report, field_name)
        return func.lower(func.cast(col, _TEXT_TYPE)).like(like)

    if field_name in LIST_FIELDS:
        col = getattr(Report, field_name)
        # PostgreSQL equivalent of SQLite's json_each(): jsonb_array_elements_text()
        # unnests a JSONB array of strings into one row per element, letting
        # us EXISTS-check for any element matching the pattern.
        je = func.jsonb_array_elements_text(col).table_valued("value")
        return exists(select(je.c.value).where(func.lower(je.c.value).like(like)))

    return None


def _all_fields_condition(like: str):
    """Builds an OR-condition matching `like` against every searchable field.

    Args:
        like: An already-lowercased SQL `LIKE` pattern (with `%` wildcards).

    Returns:
        A SQLAlchemy OR condition, or None if no fields are searchable.
    """
    conditions = [
        c
        for f in (*SCALAR_TEXT_FIELDS, *JSON_ANY_FIELDS, *LIST_FIELDS)
        if (c := _field_condition(f, like)) is not None
    ]
    return or_(*conditions) if conditions else None


@dataclass
class ReportFilters:
    """All filter/search criteria the API can apply to the report list.

    Attributes:
        field_search_tokens: `{"field": <name> | "all", "text": <query>}`
            dicts, AND-ed together; `field == "all"` matches if any
            searchable field contains the text.
        date_from: Minimum incident date (inclusive).
        date_to: Maximum incident date (inclusive).
        min_injuries: Minimum injury count.
        min_fatalities: Minimum fatality count.
        confidence_min: Minimum overall confidence.
        confidence_max: Maximum overall confidence.
        human_review_required: Filter by review-required flag, or None for any.
        has_data_in: List-column names that must be non-empty.
        operation_types: Restrict to these `operation_type` values.
        vessel_types: Restrict to these `vessel_type` values.
        casual_signatures: Restrict to these `casual_signature` values.
    """

    field_search_tokens: Sequence[dict] = field(default_factory=list)
    date_from: Optional[datetime.date] = None
    date_to: Optional[datetime.date] = None
    min_injuries: Optional[int] = None
    min_fatalities: Optional[int] = None
    confidence_min: Optional[float] = None
    confidence_max: Optional[float] = None
    human_review_required: Optional[bool] = None
    has_data_in: Sequence[str] = field(default_factory=list)
    operation_types: Sequence[str] = field(default_factory=list)
    vessel_types: Sequence[str] = field(default_factory=list)
    casual_signatures: Sequence[str] = field(default_factory=list)
    #: Report ids found semantically similar to the free-text ("all") query,
    #: if any -- OR-ed into that token's condition so semantically-similar
    #: reports are included even without a literal keyword match. Populated
    #: by the reports router (see app/api/routers/reports.py), not by
    #: ReportFilters itself, which has no knowledge of Qdrant/embeddings.
    semantic_report_ids: Sequence[int] = field(default_factory=list)

    def apply(self, stmt: Select) -> Select:
        """Applies every configured filter to a SELECT statement.

        Args:
            stmt: The base `select(Report)` (or count/aggregate select)
                statement to filter.

        Returns:
            The statement with a `WHERE` clause reflecting all
            configured filters AND-ed together.
        """
        conditions = []

        for token in self.field_search_tokens:
            token = token or {}
            field_name = token.get("field") or "all"
            text = (token.get("text") or "").strip().lower()
            if not text:
                continue
            like = f"%{text}%"
            if field_name == "all":
                cond = _all_fields_condition(like)
                if self.semantic_report_ids:
                    semantic_cond = Report.id.in_(self.semantic_report_ids)
                    cond = (
                        or_(cond, semantic_cond) if cond is not None else semantic_cond
                    )
            else:
                cond = _field_condition(field_name, like)
            if cond is not None:
                conditions.append(cond)

        if self.date_from:
            conditions.append(Report.incident_date >= self.date_from)
        if self.date_to:
            conditions.append(Report.incident_date <= self.date_to)
        if self.min_injuries is not None:
            conditions.append(Report.injuries >= self.min_injuries)
        if self.min_fatalities is not None:
            conditions.append(Report.fatalities >= self.min_fatalities)
        if self.confidence_min is not None:
            conditions.append(Report.overall_confidence >= self.confidence_min)
        if self.confidence_max is not None:
            conditions.append(Report.overall_confidence <= self.confidence_max)
        if self.human_review_required is not None:
            conditions.append(
                Report.human_review_required == self.human_review_required
            )
        if self.operation_types:
            conditions.append(Report.operation_type.in_(self.operation_types))
        if self.vessel_types:
            conditions.append(Report.vessel_type.in_(self.vessel_types))
        if self.casual_signatures:
            conditions.append(Report.casual_signature.in_(self.casual_signatures))

        for col_name in self.has_data_in:
            if col_name in LIST_FIELDS:
                conditions.append(
                    func.jsonb_array_length(getattr(Report, col_name)) > 0
                )

        if conditions:
            stmt = stmt.where(and_(*conditions))
        return stmt


async def create_report(session: AsyncSession, report: Report) -> Report:
    """Adds a `Report` to the session and flushes to obtain its id.

    Args:
        session: Active async DB session.
        report: The `Report` instance to persist (not yet committed).

    Returns:
        The same `Report` instance, with its `id` populated.
    """
    session.add(report)
    await session.flush()
    return report


async def get_existing_hashes(session: AsyncSession, hashes: Sequence[str]) -> set[str]:
    """Finds which of the given content hashes already exist in the DB.

    Args:
        session: Active async DB session.
        hashes: Candidate `content_hash` values to check.

    Returns:
        The subset of `hashes` that already exist on some `Report` row.
    """
    if not hashes:
        return set()
    result = await session.execute(
        select(Report.content_hash).where(Report.content_hash.in_(hashes))
    )
    return {row[0] for row in result.all()}


async def list_reports(
    session: AsyncSession,
    filters: ReportFilters,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "ingested_at",
    sort_dir: str = "desc",
) -> tuple[list[Report], int]:
    """Lists reports matching `filters`, paginated and sorted.

    Args:
        session: Active async DB session.
        filters: Filter criteria to apply.
        page: 1-indexed page number.
        page_size: Number of rows per page.
        sort_by: Column name to sort by (see `SORTABLE_COLUMNS`).
        sort_dir: "asc" or "desc".

    Returns:
        A tuple of (the page of `Report` rows, total matching count).
    """
    base_stmt = filters.apply(select(Report))
    count_stmt = filters.apply(select(func.count(Report.id)))
    total = (await session.execute(count_stmt)).scalar_one()

    sort_col = SORTABLE_COLUMNS.get(sort_by, Report.ingested_at)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

    stmt = (
        base_stmt.order_by(order).offset(max(page - 1, 0) * page_size).limit(page_size)
    )
    result = await session.execute(stmt)
    return list(result.scalars().unique().all()), total


async def list_all_matching(
    session: AsyncSession, filters: ReportFilters
) -> list[Report]:
    """Fetches every report matching `filters`, with no pagination.

    Intended for aggregate operations (grouping, brief generation) over
    a filtered set, not for user-facing paginated listings -- see
    `list_reports` for that.

    Args:
        session: Active async DB session.
        filters: Filter criteria to apply.

    Returns:
        Every matching `Report`, unordered.
    """
    stmt = filters.apply(select(Report))
    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def get_report_by_id(session: AsyncSession, report_id: int) -> Optional[Report]:
    """Fetches a single report by id.

    Args:
        session: Active async DB session.
        report_id: Primary key of the report to fetch.

    Returns:
        The matching `Report`, or None if not found.
    """
    result = await session.execute(select(Report).where(Report.id == report_id))
    return result.scalar_one_or_none()


async def delete_report(session: AsyncSession, report_id: int) -> bool:
    """Deletes a single report by id.

    `FieldMetadata` rows are removed automatically -- both the ORM
    relationship (`cascade="all, delete-orphan"`) and the DB foreign key
    (`ondelete="CASCADE"`) cover it. This only handles the SQL row;
    callers are responsible for any out-of-DB cleanup (the report's
    Qdrant vector, its stored source file) before calling this -- see
    `app.api.routers.reports.delete_report_endpoint`, which does both.

    Args:
        session: Active async DB session (caller commits).
        report_id: Primary key of the report to delete.

    Returns:
        True if a report with that id existed and was deleted, False if
        there was nothing to delete.
    """
    report = await get_report_by_id(session, report_id)
    if report is None:
        return False
    await session.delete(report)
    await session.flush()
    return True


async def get_reports_by_ids(
    session: AsyncSession, report_ids: Sequence[int]
) -> list[Report]:
    """Fetches multiple reports by id, preserving the requested order.

    Args:
        session: Active async DB session.
        report_ids: Primary keys to fetch.

    Returns:
        The matching `Report` rows, in the same order as `report_ids`
        (ids with no matching row are silently skipped).
    """
    if not report_ids:
        return []
    result = await session.execute(select(Report).where(Report.id.in_(report_ids)))
    reports = {r.id: r for r in result.scalars().unique().all()}
    return [reports[rid] for rid in report_ids if rid in reports]


async def get_stats(
    session: AsyncSession, filters: Optional[ReportFilters] = None
) -> dict[str, Any]:
    """Computes summary statistics for reports matching `filters`.

    Args:
        session: Active async DB session.
        filters: Filter criteria to apply. Defaults to no filtering.

    Returns:
        A dict with total_reports, total_injuries, total_fatalities,
        human_review_required, and avg_confidence.
    """
    filters = filters or ReportFilters()

    total = (
        await session.execute(filters.apply(select(func.count(Report.id))))
    ).scalar_one()
    total_injuries = (
        await session.execute(
            filters.apply(select(func.coalesce(func.sum(Report.injuries), 0)))
        )
    ).scalar_one()
    total_fatalities = (
        await session.execute(
            filters.apply(select(func.coalesce(func.sum(Report.fatalities), 0)))
        )
    ).scalar_one()
    review_required = (
        await session.execute(
            filters.apply(
                select(func.count(Report.id)).where(
                    Report.human_review_required.is_(True)
                )
            )
        )
    ).scalar_one()
    avg_confidence = (
        await session.execute(
            filters.apply(select(func.avg(Report.overall_confidence)))
        )
    ).scalar_one()

    return {
        "total_reports": total,
        "total_injuries": int(total_injuries or 0),
        "total_fatalities": int(total_fatalities or 0),
        "human_review_required": review_required,
        "avg_confidence": round(avg_confidence, 2)
        if avg_confidence is not None
        else None,
    }


async def get_distinct_values(session: AsyncSession, column_name: str) -> list[str]:
    """Lists distinct non-null values for one scalar `Report` column.

    Args:
        session: Active async DB session.
        column_name: Name of the scalar column to list distinct values for.

    Returns:
        Sorted, non-empty distinct values -- typically used to populate
        filter-option dropdowns in the UI.
    """
    col = getattr(Report, column_name)
    result = await session.execute(
        select(col).where(col.is_not(None)).distinct().order_by(col)
    )
    return [v for v in result.scalars().all() if v]


async def delete_all_reports(session: AsyncSession) -> None:
    """Deletes all reports, field metadata, vocabulary terms, and jobs.

    Utility for demos/tests -- wipes all ingested data.

    Args:
        session: Active async DB session.
    """
    await session.execute(delete(FieldMetadata))
    await session.execute(delete(Report))
    await session.execute(delete(VocabularyTerm))
    await session.execute(delete(IngestionJob))
