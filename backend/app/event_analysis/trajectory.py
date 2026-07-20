"""Step B: querying and bucketing matching reports by severity outcome.

Two ways a report can match the described event: an exact
`operation_type`/`vessel_type` match (as before), or a semantic
similarity match against the raw description (new) -- so a synonym
mismatch ("Enclosed space entry" vs. "Confined space entry") doesn't
silently produce zero comparison data even when clearly relevant
reports exist. The two sets are unioned, deduplicated by report id, and
each report is tagged with how it was found.

Severity itself is derived from `Report.injuries`/`Report.fatalities`
(plain counts), not a graded clinical scale -- there are three buckets,
not the four a "near miss / minor / serious / fatal" scale might
suggest, because the data can't actually support a minor/serious
distinction without reprocessing every historical report. See
`app.db.models.event_analysis_job.SEVERITY_STAGES`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.db import crud
from app.db.base import AsyncSessionLocal
from app.db.crud import ReportFilters
from app.db.models import Report
from app.vectorstore.embeddings import get_embedding_provider
from app.vectorstore.qdrant_store import semantic_search

settings = get_settings()

#: How a report ended up in the comparison set: an exact operation_type/
#: vessel_type match, a semantic similarity match against the raw
#: description, or both.
MatchType = str  # "exact" | "semantic" | "both"


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
class MatchedReport:
    """One report in the comparison set, tagged with how it was found.

    Attributes:
        report: The matched report.
        match_type: `"exact"` (operation_type/vessel_type match),
            `"semantic"` (similarity match against the raw description
            only), or `"both"`.
    """

    report: Report
    match_type: MatchType


@dataclass
class TrajectoryBuckets:
    """The matching reports for one described event, by severity.

    Attributes:
        near_miss: Matching reports with no reported injuries or fatalities.
        serious: Matching reports with at least one injury but no fatalities.
        fatal: Matching reports with at least one fatality.
    """

    near_miss: list[MatchedReport] = field(default_factory=list)
    serious: list[MatchedReport] = field(default_factory=list)
    fatal: list[MatchedReport] = field(default_factory=list)

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


async def _find_semantic_matches(description: str) -> list[Report]:
    """Finds reports semantically similar to the raw event description.

    Bounded by `Settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS` and never
    allowed to raise -- semantic matching is an enhancement on top of
    the exact operation/vessel match, not a hard dependency. Both the
    embedding provider's construction and the actual embed call run in
    the threadpool: constructing the provider can itself be slow on
    first use, and a synchronous call blocks the event loop directly,
    which `asyncio.wait_for` can't interrupt -- only an awaited
    threadpool call gives it something to actually cancel.

    Args:
        description: The user's raw, original event description (not
            Step A's cleaned-up restatement -- the rawest, most direct
            signal of intent).

    Returns:
        Up to `Settings.EVENT_ANALYSIS_SEMANTIC_TOP_N` reports meeting
        `Settings.SEMANTIC_SIMILARITY_THRESHOLD`, or `[]` if semantic
        search is unavailable, too slow, or finds nothing.
    """
    try:
        provider = await run_in_threadpool(get_embedding_provider)
        vector = await run_in_threadpool(provider.embed, description)
        hits = await asyncio.wait_for(
            run_in_threadpool(semantic_search, vector, settings.EVENT_ANALYSIS_SEMANTIC_TOP_N),
            timeout=settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001
        return []

    if not hits:
        return []

    report_ids = [report_id for report_id, _score in hits]
    async with AsyncSessionLocal() as session:
        return await crud.get_reports_by_ids(session, report_ids)


async def get_trajectory_buckets(
    session: AsyncSession, operation_type: str, vessel_type: str, description: str
) -> TrajectoryBuckets:
    """Finds every report matching a described event, bucketed by severity.

    Unions two match sources -- an exact `operation_type`/`vessel_type`
    match, and a semantic similarity match against the raw description
    -- deduplicated by report id and tagged with how each was found.

    Args:
        session: Active async DB session.
        operation_type: Exact `operation_type` to match (Step A's classification).
        vessel_type: Exact `vessel_type` to match (Step A's classification).
        description: The user's raw event description, used for the
            semantic match.

    Returns:
        The matching reports, sorted into near_miss/serious/fatal buckets.
    """
    filters = ReportFilters(operation_types=[operation_type], vessel_types=[vessel_type])
    exact_reports = await crud.list_all_matching(session, filters)
    exact_ids = {r.id for r in exact_reports}

    semantic_reports = await _find_semantic_matches(description)
    semantic_ids = {r.id for r in semantic_reports}

    reports_by_id: dict[int, Report] = {r.id: r for r in exact_reports}
    for r in semantic_reports:
        reports_by_id.setdefault(r.id, r)

    buckets = TrajectoryBuckets()
    for report_id, report in reports_by_id.items():
        is_exact = report_id in exact_ids
        is_semantic = report_id in semantic_ids
        match_type = "both" if is_exact and is_semantic else ("semantic" if is_semantic else "exact")
        stage = classify_severity(report)
        getattr(buckets, stage).append(MatchedReport(report=report, match_type=match_type))
    return buckets
