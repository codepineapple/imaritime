"""Builds the per-group context text for Step D's barrier-finding comparison.

Deliberately scoped to just the causal-narrative fields (contributing
factors, root causes, immediate causes) -- the fields that could
plausibly contain "the condition present in fatal cases but absent from
near-misses" -- rather than every extracted field, keeping the LLM
context focused on what the comparison actually needs. Each report is
also tagged with how it matched the described event (exact operation/
vessel match, semantic similarity, or both), so the model comparing
groups knows which reports are a precise operational match versus
"similar in spirit" -- that distinction matters when judging how
confidently a barrier condition generalizes.
"""
from __future__ import annotations

from app.event_analysis.trajectory import MatchedReport

CONTEXT_FIELDS = ["contributing_factors", "root_causes", "immediate_causes"]

_MATCH_TYPE_LABELS = {
    "exact": "exact operation/vessel match",
    "semantic": "semantically similar, not an exact operation/vessel match",
    "both": "exact operation/vessel match and semantically similar",
}


def build_group_context(matched_reports: list[MatchedReport]) -> str:
    """Builds formatted context text for one severity bucket's reports.

    Args:
        matched_reports: The bucket's matched reports (e.g.
            `TrajectoryBuckets.fatal`), each tagged with how it matched.

    Returns:
        A formatted text block, one section per report, with source
        page numbers and match type inlined -- or a placeholder string
        if the bucket is empty.
    """
    if not matched_reports:
        return "(no matching reports in this group)"

    chunks = []
    for matched in matched_reports:
        report = matched.report
        pages_by_field = {
            fm.field_name: fm.source_page_numbers
            for fm in report.field_metadata
            if fm.source_page_numbers
        }
        match_label = _MATCH_TYPE_LABELS.get(matched.match_type, matched.match_type)
        lines = [f"Report #{report.id} [{match_label}]"]
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
