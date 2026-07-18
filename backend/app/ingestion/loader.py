"""Maps a `MaritimeIncident` into ORM `Report` + `FieldMetadata` objects.

Intentionally DB-session-free -- it just builds Python objects. Callers
(the Celery ingestion task, or the bulk-JSONL endpoint) are responsible
for opening a session, checking for duplicate content hashes,
persisting, and syncing the open-vocabulary tables afterward (see
`app.db.vocab_crud`).
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

from app.core.config import get_settings
from app.db.models import FieldMetadata, Report
from app.extraction.incident import MaritimeIncident

settings = get_settings()

DATE_FIELD_SOURCE_NAME = "date"

LIST_FIELDS = {
    "equipment_involved",
    "sequence_of_events",
    "immediate_causes",
    "root_causes",
    "contributing_factors",
    "human_factors",
    "technical_failures",
    "regulatory_issues",
    "lessons_learned",
    "corrective_actions",
    "safety_recommendations",
    "keywords",
}

SCALAR_TEXT_FIELDS = {
    "incident_title",
    "incident_type",
    "location",
    "operation_type",
    "vessel_type",
    "casual_signature",
}

JSON_ANY_FIELDS = {
    "vessel_information",
    "weather_conditions",
    "environmental_factors",
    "pollution",
    "property_damage",
}

INT_FIELDS = {"injuries", "fatalities"}

FIELD_NAME_OVERRIDES = {"date": "incident_date"}

_KNOWN_COLUMN_FIELDS = (
    SCALAR_TEXT_FIELDS
    | LIST_FIELDS
    | JSON_ANY_FIELDS
    | INT_FIELDS
    | {DATE_FIELD_SOURCE_NAME}
)


@dataclass
class BuiltReport:
    """A mapped-but-not-yet-persisted report, ready for a caller to save.

    Attributes:
        report: The `Report` ORM instance (with `field_metadata` populated).
        open_vocab_values: The open-vocabulary field values extracted
            from this report, keyed by DB column name -- handed to
            `app.db.vocab_crud.sync_term` by the caller after persisting.
    """

    report: Report
    open_vocab_values: dict[str, Optional[str]] = dc_field(default_factory=dict)


def _content_hash(extracted_data: dict[str, Any]) -> str:
    """Computes a stable hash of an extraction payload, for dedup.

    Args:
        extracted_data: The `MaritimeIncident.model_dump(mode="json")` output.

    Returns:
        A hex-encoded SHA-256 digest of the canonicalized payload.
    """
    canonical = json.dumps(extracted_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_date(raw: Any) -> Optional[datetime.date]:
    """Best-effort parses a date value in any of several common formats.

    Args:
        raw: The raw extracted date value (string, date, or None).

    Returns:
        A `date` object, or None if `raw` is empty/unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime.date):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%d %B %Y",
        ):
            try:
                return datetime.datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        try:
            from dateutil import parser as dateutil_parser

            return dateutil_parser.parse(raw, fuzzy=True).date()
        except Exception:
            return None
    return None


def _coerce_int(raw: Any) -> Optional[int]:
    """Best-effort coerces a value to int.

    Args:
        raw: The raw extracted value.

    Returns:
        An int, or None if `raw` is empty/not coercible.
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def build_report_from_incident(
    incident: MaritimeIncident,
    source_filename: Optional[str] = None,
    source_file_path: Optional[str] = None,
    full_text: Optional[str] = None,
) -> BuiltReport:
    """Maps a validated `MaritimeIncident` into a `Report` ORM instance.

    Args:
        incident: The extracted (and DSPy/Pydantic-validated) incident.
        source_filename: Original uploaded filename, if any.
        source_file_path: Path to the stored source document, if any.
        full_text: The full parsed document text, stored on the report
            if `Settings.STORE_FULL_REPORT_TEXT` is enabled.

    Returns:
        A `BuiltReport` wrapping the mapped `Report` (with
        `field_metadata` populated) and the open-vocabulary values seen.
    """
    raw_extracted_data = incident.model_dump(mode="json")
    content_hash = _content_hash(raw_extracted_data)

    report_kwargs: dict[str, Any] = {}
    field_metadata_rows: list[FieldMetadata] = []
    confidences: list[float] = []
    review_required_fields: list[str] = []
    open_vocab_values: dict[str, Optional[str]] = {}

    for field_name, attr in incident:
        value = attr.value
        meta = attr.metadata

        status = meta.status_metadata.status
        human_revision_status = meta.status_metadata.human_revision_status
        confidence = meta.extraction_metadata.confidence
        reasoning = meta.extraction_metadata.reasoning
        quotes = meta.evidence_metadata.supporting_quotes
        pages = meta.evidence_metadata.source_page_numbers

        field_metadata_rows.append(
            FieldMetadata(
                field_name=field_name,
                value=value,
                status=status,
                human_revision_status=human_revision_status,
                confidence=confidence,
                reasoning=reasoning,
                supporting_quotes=quotes,
                source_page_numbers=pages,
            )
        )

        if confidence is not None:
            confidences.append(confidence)
        if (
            human_revision_status
            and human_revision_status.strip().lower() == "required"
        ):
            review_required_fields.append(field_name)

        column_name = FIELD_NAME_OVERRIDES.get(field_name, field_name)
        if field_name not in _KNOWN_COLUMN_FIELDS:
            continue

        if field_name == DATE_FIELD_SOURCE_NAME:
            report_kwargs[column_name] = _parse_date(value)
        elif field_name in INT_FIELDS:
            report_kwargs[column_name] = _coerce_int(value)
        else:
            report_kwargs[column_name] = value

        if field_name in settings.OPEN_VOCAB_FIELD_MAP:
            open_vocab_values[field_name] = value if isinstance(value, str) else None

    overall_confidence = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )

    report = Report(
        source_filename=source_filename,
        source_file_path=source_file_path,
        content_hash=content_hash,
        overall_confidence=overall_confidence,
        human_review_required=bool(review_required_fields),
        fields_requiring_review=review_required_fields,
        raw_payload=raw_extracted_data,
        full_text=full_text if settings.STORE_FULL_REPORT_TEXT else None,
        field_metadata=field_metadata_rows,
        **report_kwargs,
    )
    return BuiltReport(report=report, open_vocab_values=open_vocab_values)
