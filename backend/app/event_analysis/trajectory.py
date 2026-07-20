"""Step B: querying and bucketing matching reports by severity outcome.

Severity is derived from `Report.injuries`/`Report.fatalities` (plain
counts), not a graded clinical scale -- there are three buckets, not
the four a "near miss / minor / serious / fatal" scale might suggest,
because the data can't actually support a minor/serious distinction
without reprocessing every historical report through a new extraction
field. See `app.db.models.event_analysis_job.SEVERITY_STAGES`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.crud import ReportFilters
from app.db.models import Report


def classify_severity(report: Report) -> str:
    """Buckets a single report by severity outcome.

    Args:
        report: The report to classify.

    Returns:
        `"fatal"` if `fatalities > 0`; else `"serious"` if `injuries > 0`;
        else `"near_miss"`.
    """
    if (report.fatalities or 0) > 0:
        return "fatal"
    if (report.injuries or 0) > 0:
        return "serious"
    return "near_miss"


@dataclass
class TrajectoryBuckets:
    """The matching reports for one operation/vessel combination, by severity.

    Attributes:
        near_miss: Matching reports with no reported injuries or fatalities.
        serious: Matching reports with at least one injury but no fatalities.
        fatal: Matching reports with at least one fatality.
    """

    near_miss: list[Report] = field(default_factory=list)
    serious: list[Report] = field(default_factory=list)
    fatal: list[Report] = field(default_factory=list)

    @property
    def near_miss_count(self) -> int:
        """Returns the number of near-miss reports."""
        return len(self.near_miss)

    @property
    def serious_count(self) -> int:
        """Returns the number of serious reports."""
        return len(self.serious)

    @property
    def fatal_count(self) -> int:
        """Returns the number of fatal reports."""
        return len(self.fatal)


async def get_trajectory_buckets(
    session: AsyncSession, operation_type: str, vessel_type: str
) -> TrajectoryBuckets:
    """Finds every report matching an operation/vessel pair, bucketed by severity.

    Args:
        session: Active async DB session.
        operation_type: Exact `operation_type` to match.
        vessel_type: Exact `vessel_type` to match.

    Returns:
        The matching reports, sorted into near_miss/serious/fatal buckets.
    """
    filters = ReportFilters(operation_types=[operation_type], vessel_types=[vessel_type])
    reports = await crud.list_all_matching(session, filters)

    buckets = TrajectoryBuckets()
    for report in reports:
        stage = classify_severity(report)
        getattr(buckets, stage).append(report)
    return buckets
