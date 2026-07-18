"""The `Report` ORM model: one row per ingested incident report."""

from __future__ import annotations

import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB as _JSONB

#: Configured so Python None binds as true SQL NULL, not the JSON null
#: literal (Postgres JSONB defaults to the latter, which then fails
#: jsonb_array_elements_text() with "cannot extract elements from a
#: scalar" -- these columns are all populated from extraction fields
#: that can legitimately be None).
JSONB = _JSONB(none_as_null=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Report(Base):
    """A single ingested safety-flash / incident report.

    Known extraction fields are promoted to typed, indexed columns for
    fast filtering/sorting/grouping. List-valued and loosely-structured
    fields are stored as PostgreSQL `JSONB` columns. `raw_payload` keeps a
    verbatim copy of the source `MaritimeIncident` dump for full
    fidelity, and `field_metadata` (see `FieldMetadata`) holds the
    per-field confidence/status/evidence, including for any field not
    (yet) promoted to a column here.

    Attributes:
        id: Primary key.
        source_filename: Original uploaded filename, if any.
        source_file_path: Path to the stored source document on disk.
        content_hash: SHA-256 of the canonicalized extraction payload,
            used to detect and skip duplicate ingestions.
        ingested_at: Timestamp this row was created.
        incident_title: Report title.
        incident_type: Incident classification (e.g. "Grounding").
        incident_date: Date the incident occurred.
        location: Geographic location of the incident.
        operation_type: Open-vocabulary maritime operation category.
        vessel_type: Open-vocabulary vessel category.
        casual_signature: Open-vocabulary root-cause-pattern label.
        vessel_information: Free-text/structured vessel details.
        weather_conditions: Weather/sea state at the time of the incident.
        environmental_factors: Environmental contributing elements.
        pollution: Details of any environmental pollution/spills.
        property_damage: Details of vessel/cargo/third-party damage.
        equipment_involved: Machinery/equipment implicated.
        sequence_of_events: Chronological breakdown of events.
        immediate_causes: Direct acts/conditions that caused the incident.
        root_causes: Underlying systemic issues.
        contributing_factors: Secondary contributing factors.
        human_factors: Human behaviors/errors/ergonomics involved.
        technical_failures: Mechanical/electrical/structural failures.
        regulatory_issues: Regulatory violations/shortcomings.
        lessons_learned: Derived safety lessons.
        corrective_actions: Actions taken/proposed.
        safety_recommendations: Official recommendations issued.
        keywords: Free-form tags summarizing the incident.
        injuries: Injury count.
        fatalities: Fatality count.
        overall_confidence: Mean per-field extraction confidence.
        human_review_required: True if any field needs human review.
        fields_requiring_review: Names of fields flagged for review.
        raw_payload: Verbatim extraction JSON, for audit/fidelity.
        full_text: Full parsed source document text, if
            `Settings.STORE_FULL_REPORT_TEXT` is enabled.
        vector_indexed: Whether this report's embedding is stored in Qdrant.
        field_metadata: Per-field extraction metadata rows.
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)

    source_filename: Mapped[Optional[str]] = mapped_column(String(512))
    source_file_path: Mapped[Optional[str]] = mapped_column(String(1024))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )

    incident_title: Mapped[Optional[str]] = mapped_column(Text)
    incident_type: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    incident_date: Mapped[Optional[datetime.date]] = mapped_column(Date, index=True)
    location: Mapped[Optional[str]] = mapped_column(String(512), index=True)

    operation_type: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    vessel_type: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    casual_signature: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    vessel_information: Mapped[Optional[Any]] = mapped_column(JSONB)
    weather_conditions: Mapped[Optional[Any]] = mapped_column(JSONB)
    environmental_factors: Mapped[Optional[Any]] = mapped_column(JSONB)
    pollution: Mapped[Optional[Any]] = mapped_column(JSONB)
    property_damage: Mapped[Optional[Any]] = mapped_column(JSONB)

    equipment_involved: Mapped[Optional[list]] = mapped_column(JSONB)
    sequence_of_events: Mapped[Optional[list]] = mapped_column(JSONB)
    immediate_causes: Mapped[Optional[list]] = mapped_column(JSONB)
    root_causes: Mapped[Optional[list]] = mapped_column(JSONB)
    contributing_factors: Mapped[Optional[list]] = mapped_column(JSONB)
    human_factors: Mapped[Optional[list]] = mapped_column(JSONB)
    technical_failures: Mapped[Optional[list]] = mapped_column(JSONB)
    regulatory_issues: Mapped[Optional[list]] = mapped_column(JSONB)
    lessons_learned: Mapped[Optional[list]] = mapped_column(JSONB)
    corrective_actions: Mapped[Optional[list]] = mapped_column(JSONB)
    safety_recommendations: Mapped[Optional[list]] = mapped_column(JSONB)
    keywords: Mapped[Optional[list]] = mapped_column(JSONB)

    injuries: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    fatalities: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    overall_confidence: Mapped[Optional[float]] = mapped_column(Float, index=True)
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )
    fields_requiring_review: Mapped[Optional[list]] = mapped_column(JSONB)

    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    vector_indexed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    field_metadata: Mapped[List["FieldMetadata"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FieldMetadata.field_name",
    )

    __table_args__ = (
        Index("ix_reports_type_location", "incident_type", "location"),
        Index(
            "ix_reports_review_confidence",
            "human_review_required",
            "overall_confidence",
        ),
        Index("ix_reports_operation_vessel", "operation_type", "vessel_type"),
    )

    def __repr__(self) -> str:
        """Returns a debug-friendly representation.

        Returns:
            A string identifying this report by id and title.
        """
        return f"<Report id={self.id} title={self.incident_title!r}>"
