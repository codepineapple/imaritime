"""The `VocabularyTerm` ORM model: the open-vocabulary feedback loop's storage."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VocabularyTerm(Base):
    """A known value for one open-vocabulary field.

    Open-vocabulary fields (`operation_type`, `vessel_type`,
    `casual_signature`) are fed to the extraction LLM as "pick one of
    these, or invent a new general label" lists. This table stores that
    growing, per-field set: `field_name` is the DB column name (e.g.
    "operation_type"), `normalized_term` is the lowercased/whitespace-
    collapsed form used for de-duplication, and `term` preserves the
    original casing shown to the LLM and the UI.

    Attributes:
        id: Primary key.
        field_name: The open-vocabulary DB column this term belongs to.
        term: The term, in its original casing.
        normalized_term: Lowercased/whitespace-collapsed form of `term`,
            used for case/whitespace-insensitive de-duplication.
        first_seen_report_id: The report this term was first extracted from.
        usage_count: How many reports have used this term.
        created_at: Timestamp this term was first seen.
    """

    __tablename__ = "vocabulary_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_name: Mapped[str] = mapped_column(String(64), index=True)
    term: Mapped[str] = mapped_column(String(255))
    normalized_term: Mapped[str] = mapped_column(String(255), index=True)
    first_seen_report_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL")
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("field_name", "normalized_term", name="uq_vocab_field_term"),
    )

    def __repr__(self) -> str:
        """Returns a debug-friendly representation.

        Returns:
            A string identifying this term by field name and value.
        """
        return f"<VocabularyTerm {self.field_name}={self.term!r}>"
