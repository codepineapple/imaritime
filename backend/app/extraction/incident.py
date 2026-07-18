"""Canonical structured-output schema for a maritime incident extraction.

This is the single source of truth for "what does one extracted report
look like" -- used as `extraction.signature.ExtractMaritimeReport`'s
output type (so DSPy returns a real `MaritimeIncident` instance, not
just raw JSON), and used throughout the rest of the backend (ingestion,
API responses) instead of a separate, generic mirror schema.

Field descriptions are preserved verbatim from the original signature
design: DSPy includes them in the JSON schema shown to the model, so
they are effectively part of the prompt and are not simplified/altered
here even though this file's structure was reorganized.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.extraction.metadata import Attribute, CoercedList


class MaritimeIncident(BaseModel):
    """Structured output schema for the full maritime accident report."""

    incident_title: Attribute[str] = Field(
        description="The title of the maritime incident."
    )
    incident_type: Attribute[str] = Field(
        description="Classification of the incident (e.g., Grounding, Collision, Fire)."
    )
    date: Attribute[str] = Field(description="Date the incident occurred.")
    operation_type: Attribute[str] = Field(
        description=(
            "Type of maritime operation (e.g., Cargo Transport, Fishing, "
            "Passenger Transport, Enclosed Space Entry, Lifting "
            "Operation, Mooring, DP Operation, etc). It must be selected "
            "from the predefined list. However, if no matching label is "
            "available, generate it. It must be as general as possible "
            "and not specific to the incident. It should be a short "
            "label that can be used to group incidents with similar "
            "operation types. because the generated label will be added "
            "to the predefined list for future use. "
            "NOTE: It should be a 3 word maximum with Title Case and should not contain any special characters or numbers."
        )
    )
    vessel_type: Attribute[str] = Field(
        description=(
            "Type of vessel involved (e.g., Bulk Carrier, Container "
            "Ship, Tanker, Fishing Vessel, Log Carrier, Offshore Vessel, "
            "Bulk Carrier, Tanker, etc). It must be selected from the "
            "predefined list. However, if no matching label is "
            "available, generate it. It must be as general as possible "
            "and not specific to the incident. It should be a short "
            "label that can be used to group incidents with similar "
            "vessel types. because the generated label will be added to "
            "the predefined list for future use. "
            "NOTE: It should be a 3 word maximum with Title Case and should not contain any special characters or numbers."
        )
    )
    vessel_information: Attribute[str] = Field(
        description="Details regarding the vessel(s) involved."
    )
    location: Attribute[str] = Field(description="Geographic location of the incident.")
    weather_conditions: Attribute[str] = Field(
        description="Weather and sea state at the time of the incident."
    )
    equipment_involved: Attribute[CoercedList] = Field(
        description="Specific machinery or equipment involved."
    )
    sequence_of_events: Attribute[CoercedList] = Field(
        description="Chronological breakdown of events leading to the incident."
    )
    immediate_causes: Attribute[CoercedList] = Field(
        description="The direct acts or conditions that caused the incident."
    )
    root_causes: Attribute[CoercedList] = Field(
        description="The underlying systemic issues that led to the incident."
    )
    casual_signature: Attribute[str] = Field(
        description=(
            "short standardised label for the root cause pattern "
            "(Fall, Trip, Collision, Fire, Explosion, Grounding, Capsize,"
            "Oxygen Depletion, Line Snapping, etc). It must be selected "
            "from the predefined list. However, if no matching label is "
            "available, generate it. It must be as general as possible "
            "and not specific to the incident. It should be a short "
            "label that can be used to group incidents with similar "
            "root causes. because the generated label will be added to "
            "the predefined list for future use. "
            "NOTE: It should be a 3 word maximum with Title Case and should not contain any special characters or numbers."
        )
    )
    contributing_factors: Attribute[CoercedList] = Field(
        description="Factors that contributed but were not the primary root cause."
    )
    human_factors: Attribute[CoercedList] = Field(
        description="Human behaviors, errors, or ergonomics impacting the incident."
    )
    technical_failures: Attribute[CoercedList] = Field(
        description="Mechanical, electrical, or structural failures."
    )
    environmental_factors: Attribute[CoercedList] = Field(
        description="Environmental elements contributing to the incident."
    )
    regulatory_issues: Attribute[CoercedList] = Field(
        description="Violations or shortcomings regarding maritime regulations."
    )
    injuries: Attribute[int] = Field(description="Number of injuries. 0 if none.")
    fatalities: Attribute[int] = Field(description="Number of fatalities. 0 if none.")
    pollution: Attribute[str] = Field(
        description="Details of any environmental pollution or spills."
    )
    property_damage: Attribute[str] = Field(
        description="Details of damage to the vessel, cargo, or third-party property."
    )
    lessons_learned: Attribute[CoercedList] = Field(
        description="Derived safety lessons to prevent recurrence."
    )
    corrective_actions: Attribute[CoercedList] = Field(
        description="Actions taken or proposed to address the root causes."
    )
    safety_recommendations: Attribute[CoercedList] = Field(
        description="Official safety recommendations issued by the investigators."
    )
    keywords: Attribute[CoercedList] = Field(
        description="Tags and keywords summarizing the incident."
    )
