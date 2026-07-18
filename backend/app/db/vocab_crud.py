"""The open-vocabulary feedback loop.

`app.extraction.signature.ExtractMaritimeReport` takes three `list[str]`
input fields -- `operation_types`, `vessel_types`,
`root_cause_signatures` -- containing the *currently known* labels for
each category. The LLM either picks one or invents a new, general label
if nothing fits. Any invented label needs to be folded back into the
stored vocabulary so the *next* extraction call sees it too, otherwise
the same "new" category would keep getting reinvented (possibly with
slightly different wording) forever instead of converging.

This module is the single place that:
  1. Reads the current vocabulary for each field, shaped exactly as the
     DSPy signature expects (`get_vocabulary_for_signature`).
  2. Writes newly-seen values back after an extraction completes
     (`sync_term`, `sync_vocab_from_report`).

`app.core.config.Settings.OPEN_VOCAB_FIELD_MAP` is the source of truth
for which DB columns are open-vocabulary and what signature input field
name each maps to -- add a new entry there (and a matching column on
`Report`) to extend this to more fields later without touching this file.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Report, VocabularyTerm

settings = get_settings()


def _normalize(term: str) -> str:
    """Normalizes a term for case/whitespace-insensitive de-duplication.

    Args:
        term: The raw term to normalize.

    Returns:
        The term lowercased with runs of whitespace collapsed to single
        spaces and surrounding whitespace stripped.
    """
    return " ".join(term.strip().lower().split())


async def get_vocabulary(session: AsyncSession, field_name: str) -> list[str]:
    """Lists all known terms for one open-vocabulary DB column.

    Args:
        session: Active async DB session.
        field_name: The `Report` column name (e.g. "operation_type").

    Returns:
        Known terms for this field, most-used first.
    """
    stmt = (
        select(VocabularyTerm.term)
        .where(VocabularyTerm.field_name == field_name)
        .order_by(VocabularyTerm.usage_count.desc(), VocabularyTerm.term.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_vocabulary_for_signature(session: AsyncSession) -> dict[str, list[str]]:
    """Builds the exact kwargs shape `ExtractMaritimeReport` expects.

    Args:
        session: Active async DB session.

    Returns:
        A dict like `{"operation_types": [...], "vessel_types": [...],
        "root_cause_signatures": [...]}`, ready to pass into
        `app.extraction.service.extract_report`.
    """
    result: dict[str, list[str]] = {}
    for db_field, signature_param in settings.OPEN_VOCAB_FIELD_MAP.items():
        result[signature_param] = await get_vocabulary(session, db_field)
    return result


async def sync_term(
    session: AsyncSession,
    field_name: str,
    term: Optional[str],
    report_id: Optional[int] = None,
) -> None:
    """Inserts a new vocabulary term, or bumps an existing one's usage count.

    Args:
        session: Active async DB session.
        field_name: The `Report` column this term belongs to.
        term: The extracted value to record. No-op if empty/None.
        report_id: The report this term was extracted from, recorded as
            `first_seen_report_id` for new terms only.
    """
    if not term or not term.strip():
        return

    normalized = _normalize(term)
    existing = await session.execute(
        select(VocabularyTerm).where(
            VocabularyTerm.field_name == field_name,
            VocabularyTerm.normalized_term == normalized,
        )
    )
    row = existing.scalar_one_or_none()

    if row is None:
        session.add(
            VocabularyTerm(
                field_name=field_name,
                term=term.strip(),
                normalized_term=normalized,
                first_seen_report_id=report_id,
                usage_count=1,
            )
        )
    else:
        await session.execute(
            update(VocabularyTerm)
            .where(VocabularyTerm.id == row.id)
            .values(usage_count=row.usage_count + 1)
        )


async def sync_vocab_from_report(session: AsyncSession, report: Report) -> None:
    """Folds a report's open-vocabulary field values into the growing sets.

    Call once, right after a `Report` row is built/persisted.

    Args:
        session: Active async DB session.
        report: The report whose `operation_type`/`vessel_type`/
            `casual_signature` values should be synced.
    """
    for db_field in settings.OPEN_VOCAB_FIELD_MAP:
        value = getattr(report, db_field, None)
        if isinstance(value, str):
            await sync_term(session, db_field, value, report_id=report.id)
