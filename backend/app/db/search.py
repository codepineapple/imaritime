"""Attribute-tagged search suggestions (autocomplete)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud import JSON_ANY_FIELDS, LIST_FIELDS, SCALAR_TEXT_FIELDS
from app.db.models import Report

_TEXT_TYPE = Report.__table__.c.location.type
_MAX_SNIPPET_LEN = 120


def _truncate(text: str) -> str:
    """Truncates a string to `_MAX_SNIPPET_LEN`, appending an ellipsis if cut.

    Args:
        text: The text to truncate.

    Returns:
        `text` unchanged if short enough, otherwise a truncated copy
        ending in "…".
    """
    text = str(text)
    return text if len(text) <= _MAX_SNIPPET_LEN else text[: _MAX_SNIPPET_LEN - 1] + "…"


async def get_search_suggestions(
    session: AsyncSession,
    query: str,
    limit_per_field: int = 3,
    max_total: int = 10,
) -> list[dict]:
    """Finds field-tagged autocomplete suggestions for a partial query.

    Searches scalar text columns, list-valued JSON columns (via PostgreSQL's
    `jsonb_array_elements_text()`), and loosely-structured JSON columns, returning
    matches tagged with the field they came from so the UI can show an
    attribute badge per suggestion.

    Args:
        session: Active async DB session.
        query: Partial text to match (case-insensitive substring).
        limit_per_field: Maximum suggestions to return per field.
        max_total: Maximum total suggestions to return, across all fields.

    Returns:
        A list of `{"field": ..., "text": ...}` dicts, deduplicated and
        capped at `max_total`.
    """
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    suggestions: list[dict] = []

    for field_name in SCALAR_TEXT_FIELDS:
        col = getattr(Report, field_name)
        stmt = (
            select(col)
            .where(col.is_not(None))
            .where(func.lower(col).like(like))
            .distinct()
            .limit(limit_per_field)
        )
        for value in (await session.execute(stmt)).scalars().all():
            if value:
                suggestions.append({"field": field_name, "text": _truncate(value)})

    for field_name in LIST_FIELDS:
        col = getattr(Report, field_name)
        je = func.jsonb_array_elements_text(col).table_valued("value")
        stmt = (
            select(je.c.value)
            .select_from(Report, je)
            .where(func.lower(je.c.value).like(like))
            .distinct()
            .limit(limit_per_field)
        )
        for value in (await session.execute(stmt)).scalars().all():
            if value:
                suggestions.append({"field": field_name, "text": _truncate(value)})

    for field_name in JSON_ANY_FIELDS:
        col = getattr(Report, field_name)
        casted = func.cast(col, _TEXT_TYPE)
        stmt = (
            select(casted)
            .where(col.is_not(None))
            .where(func.lower(casted).like(like))
            .distinct()
            .limit(limit_per_field)
        )
        for value in (await session.execute(stmt)).scalars().all():
            if value and value.lower() != "null":
                suggestions.append({"field": field_name, "text": _truncate(value)})

    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for s in suggestions:
        key = (s["field"], s["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    return deduped[:max_total]
