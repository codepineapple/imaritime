"""The `FieldMetadata` ORM model: per-field extraction provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB as _JSONB

#: Configured so Python None binds as true SQL NULL, not the JSON null
#: literal (Postgres JSONB defaults to the latter, which then fails
#: jsonb_array_elements_text() with "cannot extract elements from a
#: scalar" -- these columns are all populated from extraction fields
#: that can legitimately be None).
JSONB = _JSONB(none_as_null=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.report import Report


class FieldMetadata(Base):
    """Per-field extraction metadata for a single report.

    One row per key present in the source extraction payload -- powers
    the "full detail" view (confidence, status, reasoning, evidence per
    field), and is populated even for fields not promoted to a `Report`
    column, so newly-added extraction fields show up automatically.

    Attributes:
        id: Primary key.
        report_id: Foreign key to the owning `Report`.
        field_name: Name of the extracted field (e.g. "root_causes").
        value: The extracted value for this field (any JSON-serializable type).
        status: Extraction status ("Official Report Information",
            "AI Generated", or "Not Supported").
        human_revision_status: "Required" or "Not Required".
        confidence: Extraction confidence, 0.0-1.0.
        reasoning: Model's step-by-step justification for this value.
        supporting_quotes: Verbatim quotes supporting the value.
        source_page_numbers: Page numbers the quotes were found on.
        report: The owning `Report`.
    """

    __tablename__ = "field_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )

    field_name: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[Optional[Any]] = mapped_column(JSONB)

    status: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    human_revision_status: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, index=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    supporting_quotes: Mapped[Optional[list]] = mapped_column(JSONB)
    source_page_numbers: Mapped[Optional[list]] = mapped_column(JSONB)

    report: Mapped["Report"] = relationship(back_populates="field_metadata")

    __table_args__ = (
        UniqueConstraint("report_id", "field_name", name="uq_fieldmeta_report_field"),
    )

    def __repr__(self) -> str:
        """Returns a debug-friendly representation.

        Returns:
            A string identifying this row by report id and field name.
        """
        return f"<FieldMetadata report_id={self.report_id} field={self.field_name!r}>"
