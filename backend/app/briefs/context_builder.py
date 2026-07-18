"""Builds the LLM context and summary statistics for brief generation."""

from __future__ import annotations

from typing import Optional

from app.db.models import Report

#: Fields whose content is most relevant to synthesizing a brief -- the
#: causal/corrective narrative, not every extracted field.
CONTEXT_FIELDS = [
    "sequence_of_events",
    "immediate_causes",
    "root_causes",
    "contributing_factors",
    "corrective_actions",
    "lessons_learned",
    "regulatory_issues",
]


def compute_year_range(reports: list[Report]) -> str:
    """Computes the earliest-to-latest incident year span across reports.

    Args:
        reports: The matching reports.

    Returns:
        A string like "2014-2023", "2020" (a single year), or "unknown"
        if no matching report has a known incident date.
    """
    years = sorted({r.incident_date.year for r in reports if r.incident_date})
    if not years:
        return "unknown"
    if years[0] == years[-1]:
        return str(years[0])
    return f"{years[0]}-{years[-1]}"


def build_reports_context(
    reports: list[Report], highlight_report_id: Optional[int] = None
) -> str:
    """Builds the formatted per-report context text for the brief signature.

    Args:
        reports: The matching reports to include (each must have its
            `field_metadata` relationship loaded, for page-number lookup).
        highlight_report_id: If given, that report is marked as the
            "most representative" one in the context text, signaling
            the model to draw its vivid detail primarily from it.

    Returns:
        A formatted text block, one section per report, with source
        page numbers inlined next to each field where known.
    """
    chunks = []
    for report in reports:
        pages_by_field = {
            fm.field_name: fm.source_page_numbers
            for fm in report.field_metadata
            if fm.source_page_numbers
        }
        header = f"Report #{report.id}"
        if report.id == highlight_report_id:
            header += " [MOST REPRESENTATIVE REPORT]"
        lines = [header]

        for field_name in CONTEXT_FIELDS:
            value = getattr(report, field_name, None)
            if not value:
                continue
            pages = pages_by_field.get(field_name)
            page_suffix = f" (p. {', '.join(str(p) for p in pages)})" if pages else ""
            value_text = (
                "; ".join(str(v) for v in value)
                if isinstance(value, list)
                else str(value)
            )
            lines.append(f"  {field_name}{page_suffix}: {value_text}")

        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)
