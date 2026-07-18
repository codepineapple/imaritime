"""Grouping reports by an open-vocabulary field and counting recurrence.

Powers "group these matching reports by causal_signature and rank by
how often each pattern recurs" -- the core query behind both the Causal
Patterns view and the Intelligence Brief generator (which needs "the
highest-frequency causal group" as its primary input).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud import ReportFilters
from app.db.models import Report

#: Fields standardized enough across reports to be meaningfully grouped.
GROUPABLE_FIELDS = {"operation_type", "vessel_type", "casual_signature"}


@dataclass
class CausalGroup:
    """One group of reports sharing the same value for a grouped field.

    Attributes:
        group_by_field: Which `Report` column was grouped on.
        value: The shared field value defining this group.
        count: Number of reports in this group (the recurrence score).
        total_injuries: Sum of injuries across the group's reports.
        total_fatalities: Sum of fatalities across the group's reports.
        avg_confidence: Mean overall_confidence across the group's reports.
        earliest_date: Earliest incident_date in the group, if known.
        latest_date: Most recent incident_date in the group, if known.
        sample_report_ids: A handful of report ids belonging to this group.
    """

    group_by_field: str
    value: str
    count: int
    total_injuries: int
    total_fatalities: int
    avg_confidence: Optional[float]
    earliest_date: Optional[str]
    latest_date: Optional[str]
    sample_report_ids: list[int]


async def group_reports(
    session: AsyncSession,
    group_by_field: str,
    filters: Optional[ReportFilters] = None,
    limit: int = 20,
    samples_per_group: int = 5,
) -> list[CausalGroup]:
    """Groups reports matching `filters` by one field, ranked by recurrence.

    Args:
        session: Active async DB session.
        group_by_field: One of `GROUPABLE_FIELDS` ("operation_type",
            "vessel_type", "casual_signature").
        filters: Optional filter criteria to restrict which reports are
            grouped (e.g. a text search, a date range).
        limit: Maximum number of groups to return.
        samples_per_group: Maximum sample report ids to include per group.

    Returns:
        Groups ordered by descending recurrence count.

    Raises:
        ValueError: If `group_by_field` isn't a groupable field.
    """
    if group_by_field not in GROUPABLE_FIELDS:
        raise ValueError(
            f"'{group_by_field}' is not groupable. Options: {sorted(GROUPABLE_FIELDS)}"
        )

    filters = filters or ReportFilters()
    col = getattr(Report, group_by_field)

    stmt = (
        select(
            col.label("value"),
            func.count(Report.id).label("count"),
            func.coalesce(func.sum(Report.injuries), 0).label("total_injuries"),
            func.coalesce(func.sum(Report.fatalities), 0).label("total_fatalities"),
            func.avg(Report.overall_confidence).label("avg_confidence"),
            func.min(Report.incident_date).label("earliest_date"),
            func.max(Report.incident_date).label("latest_date"),
        )
        .where(col.is_not(None))
        .group_by(col)
        .order_by(func.count(Report.id).desc())
        .limit(limit)
    )
    stmt = filters.apply(stmt)

    rows = (await session.execute(stmt)).all()

    groups: list[CausalGroup] = []
    for row in rows:
        sample_stmt = (
            filters.apply(select(Report.id).where(col == row.value))
            .order_by(Report.overall_confidence.desc().nullslast())
            .limit(samples_per_group)
        )
        sample_ids = list((await session.execute(sample_stmt)).scalars().all())

        groups.append(
            CausalGroup(
                group_by_field=group_by_field,
                value=row.value,
                count=row.count,
                total_injuries=int(row.total_injuries or 0),
                total_fatalities=int(row.total_fatalities or 0),
                avg_confidence=round(row.avg_confidence, 4)
                if row.avg_confidence is not None
                else None,
                earliest_date=row.earliest_date.isoformat()
                if row.earliest_date
                else None,
                latest_date=row.latest_date.isoformat() if row.latest_date else None,
                sample_report_ids=sample_ids,
            )
        )
    return groups


async def get_top_group(
    session: AsyncSession,
    group_by_field: str,
    filters: Optional[ReportFilters] = None,
) -> Optional[CausalGroup]:
    """Returns the single highest-recurrence group, or None if there are no matches.

    Args:
        session: Active async DB session.
        group_by_field: One of `GROUPABLE_FIELDS`.
        filters: Optional filter criteria to restrict the candidate reports.

    Returns:
        The top `CausalGroup` by recurrence count, or None.
    """
    groups = await group_reports(
        session, group_by_field, filters, limit=1, samples_per_group=1
    )
    return groups[0] if groups else None
