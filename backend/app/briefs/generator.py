"""Builds an intelligence brief from a specific, user-selected set of reports.

Unlike the earlier operation_type/vessel_type-filtered design, briefs are
now generated from an explicit list of user-selected reports (up to
`Settings.MAX_REPORTS_PER_BRIEF`) on the Incidents page (after applying
whatever filters they like) -- see `app/tasks/brief_tasks.py` for the
async job that calls this.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.briefs.context_builder import build_reports_context, compute_year_range
from app.core.config import get_settings
from app.db import crud
from app.db.models import Report
from app.extraction.brief import IntelligenceBrief
from app.extraction.brief_service import get_brief_generation_service

#: Maximum reports a single brief can be built from. Sourced from
#: `Settings` (env-configurable) rather than hardcoded, so ops can tune
#: it without a code change -- see `Settings.MAX_REPORTS_PER_BRIEF`.
MAX_REPORTS_PER_BRIEF = get_settings().MAX_REPORTS_PER_BRIEF


class NoMatchingReportsError(Exception):
    """Raised when none of the requested report ids could be found."""


@dataclass
class BriefGenerationResult:
    """The outcome of generating a brief from a set of reports.

    Attributes:
        brief: The generated `IntelligenceBrief`.
        top_causal_signature: The most common `casual_signature` among
            the selected reports (or the first non-empty one, if all differ).
        most_representative_report_id: The highest-confidence report id
            within the top causal-signature group.
    """

    brief: IntelligenceBrief
    top_causal_signature: str
    most_representative_report_id: int


def _pick_top_causal_signature_and_representative(
    reports: list[Report],
) -> tuple[str, int]:
    """Finds the most common causal signature and its most-confident report.

    Args:
        reports: The selected reports (1-5).

    Returns:
        A tuple of (top causal signature label, id of the highest-
        `overall_confidence` report sharing that signature).

    Raises:
        NoMatchingReportsError: If none of the reports has a
            `casual_signature` value.
    """
    signatures = [r.casual_signature for r in reports if r.casual_signature]
    if not signatures:
        raise NoMatchingReportsError(
            "None of the selected reports has a casual_signature value."
        )

    top_signature, _count = Counter(signatures).most_common(1)[0]
    candidates = [r for r in reports if r.casual_signature == top_signature]
    most_representative = max(candidates, key=lambda r: r.overall_confidence or 0.0)
    return top_signature, most_representative.id


def _most_common_or_mixed(values: list[str | None], label: str) -> str:
    """Picks the most common non-null value, or a "Mixed ..." label if none recur.

    Args:
        values: The values to summarize (e.g. every selected report's
            `operation_type`).
        label: Human-readable name for what these values represent,
            used to build the "Mixed ..." fallback label.

    Returns:
        The most common value, or f"Mixed {label}" if there's no
        non-null value or no value repeats.
    """
    present = [v for v in values if v]
    if not present:
        return f"Unknown {label}"
    most_common, count = Counter(present).most_common(1)[0]
    return most_common if count > 1 or len(set(present)) == 1 else f"Mixed {label}"


async def generate_brief_from_reports(
    session: AsyncSession,
    report_ids: list[int],
    mlflow_experiment_name: str | None = None,
) -> BriefGenerationResult:
    """Generates an intelligence brief from a specific set of reports.

    Args:
        session: Active async DB session.
        report_ids: Up to `MAX_REPORTS_PER_BRIEF` report ids to brief.
        mlflow_experiment_name: Optional MLflow experiment name override.

    Returns:
        The generated brief plus which causal signature and report it
        was centered on.

    Raises:
        NoMatchingReportsError: If none of the given ids exist, or none
            has a `casual_signature` value.
        app.extraction.brief_service.BriefGenerationError: If the
            underlying DSPy call fails.
    """
    reports = await crud.get_reports_by_ids(session, report_ids)
    if not reports:
        raise NoMatchingReportsError(
            f"None of the requested report ids exist: {report_ids}"
        )

    top_causal_signature, most_representative_report_id = (
        _pick_top_causal_signature_and_representative(reports)
    )

    operation_type = _most_common_or_mixed(
        [r.operation_type for r in reports], "operation types"
    )
    vessel_type = _most_common_or_mixed(
        [r.vessel_type for r in reports], "vessel types"
    )

    total_injuries = sum(r.injuries or 0 for r in reports)
    total_fatalities = sum(r.fatalities or 0 for r in reports)
    year_range = compute_year_range(reports)
    reports_context = build_reports_context(
        reports, highlight_report_id=most_representative_report_id
    )

    service = get_brief_generation_service()
    brief = service.generate(
        operation_type=operation_type,
        vessel_type=vessel_type,
        incident_count=len(reports),
        total_injuries=total_injuries,
        total_fatalities=total_fatalities,
        year_range=year_range,
        top_causal_signature=top_causal_signature,
        most_representative_report_id=most_representative_report_id,
        reports_context=reports_context,
        mlflow_experiment_name=mlflow_experiment_name,
    )

    return BriefGenerationResult(
        brief=brief,
        top_causal_signature=top_causal_signature,
        most_representative_report_id=most_representative_report_id,
    )
