"""Builds the per-group context text for Step D's barrier-finding comparison.

Deliberately scoped to just the causal-narrative fields (contributing
factors, root causes, immediate causes) -- the fields that could
plausibly contain "the condition present in fatal cases but absent from
near-misses" -- rather than every extracted field, keeping the LLM
context focused on what the comparison actually needs.
"""
from __future__ import annotations

from app.db.models import Report

CONTEXT_FIELDS = ["contributing_factors", "root_causes", "immediate_causes"]


def build_group_context(reports: list[Report]) -> str:
    """Builds formatted context text for one severity bucket's reports.

    Args:
        reports: The bucket's reports (e.g. `TrajectoryBuckets.fatal`).

    Returns:
        A formatted text block, one section per report, with source
        page numbers inlined next to each field where known -- or a
        placeholder string if the bucket is empty.
    """
    if not reports:
        return "(no matching reports in this group)"

    chunks = []
    for report in reports:
        pages_by_field = {
            fm.field_name: fm.source_page_numbers
            for fm in report.field_metadata
            if fm.source_page_numbers
        }
        lines = [f"Report #{report.id}"]
        for field_name in CONTEXT_FIELDS:
            value = getattr(report, field_name, None)
            if not value:
                continue
            pages = pages_by_field.get(field_name)
            page_suffix = f" (p. {', '.join(str(p) for p in pages)})" if pages else ""
            value_text = "; ".join(str(v) for v in value) if isinstance(value, list) else str(value)
            lines.append(f"  {field_name}{page_suffix}: {value_text}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)
