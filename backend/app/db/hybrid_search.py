"""Hybrid keyword + semantic search support for the reports search endpoint.

`app.db.crud.ReportFilters` already does the SQL-level work of including
semantically-similar reports in the result set (via `semantic_report_ids`,
OR-ed into the free-text token's condition). This module provides the
complementary piece: given a report already fetched from that query,
determine whether it matched via keyword, semantic similarity, or both,
so the API response can label each result accordingly.
"""

from __future__ import annotations

from app.db.crud import JSON_ANY_FIELDS, LIST_FIELDS, SCALAR_TEXT_FIELDS
from app.db.models import Report


def report_matches_text(report: Report, text: str) -> bool:
    """Checks whether a report's fields contain `text` (case-insensitive).

    Mirrors `app.db.crud._all_fields_condition`'s SQL logic, but evaluated
    in Python against an already-loaded `Report` instance -- used purely
    for labeling a hybrid search result's match type, not for filtering
    (filtering already happened in SQL).

    Args:
        report: An already-fetched report.
        text: The free-text query to check for.

    Returns:
        True if `text` appears (case-insensitively) in any scalar,
        JSON-any, or list-valued searchable field.
    """
    needle = text.strip().lower()
    if not needle:
        return False

    for field_name in SCALAR_TEXT_FIELDS:
        value = getattr(report, field_name, None)
        if value and needle in str(value).lower():
            return True

    for field_name in JSON_ANY_FIELDS:
        value = getattr(report, field_name, None)
        if value and needle in str(value).lower():
            return True

    for field_name in LIST_FIELDS:
        value = getattr(report, field_name, None) or []
        for item in value:
            if needle in str(item).lower():
                return True

    return False
