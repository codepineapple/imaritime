"""Structured output schemas for the event trajectory analysis feature.

Two DSPy calls, two schemas: `EventClassification` (Step A -- what is
this event, and how severe) and `EventAnalysisFindings` (Steps D/E --
the barrier condition and the one recommended action). Step B/C
(trajectory mapping, sequence display) are deterministic DB work and
frontend rendering respectively -- no LLM, no schema needed.
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

SeverityStage = Literal["near_miss", "serious", "fatal"]


class EventClassification(BaseModel):
    """Step A output: what this described event is, and how severe."""

    operation_type: str = Field(
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
    vessel_type: str = Field(
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
    event_summary: str = Field(
        description="A one-sentence, plain-language restatement of what happened."
    )
    severity_stage: SeverityStage = Field(
        description=(
            "The described event's own severity outcome: 'fatal' if it describes "
            "a death, 'serious' if it describes any injury (however minor), or "
            "'near_miss' if it describes no injury at all -- e.g. 'felt dizzy, "
            "climbed back out, no injury' is near_miss, not serious."
        )
    )


class BarrierCitation(BaseModel):
    """A single traceability link from a finding back to a source report."""

    report_id: int = Field(description="The report id this citation refers to.")
    field_name: str = Field(
        description="The extracted field name this citation draws from "
        "(e.g. 'contributing_factors', 'root_causes')."
    )
    page_numbers: List[int] = Field(
        default_factory=list, description="Source page numbers within that report, if known."
    )


class BarrierFinding(BaseModel):
    """Step D output: the condition present in fatal cases but absent in near-misses."""

    condition: str = Field(
        description=(
            "The single specific condition or missing control that was present in "
            "every (or nearly every) fatal case's contributing factors, but absent "
            "from the near-miss cases' -- described concretely (a real control or "
            "circumstance), not as a generic category. If the fatal and near-miss "
            "groups' contributing factors don't show a clear consistent "
            "difference, say so plainly rather than forcing a distinction that "
            "isn't really there."
        )
    )
    citations: List[BarrierCitation] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """Step E output: the one concrete action to take today."""

    action: str = Field(
        description=(
            "One specific, direct action the user should take today, grounded in "
            "the barrier finding -- at most two sentences, phrased as a command "
            "('Verify X before Y'), not a passive recommendation."
        )
    )
    citations: List[BarrierCitation] = Field(default_factory=list)


class EventAnalysisFindings(BaseModel):
    """Combined Steps D+E output: the barrier condition and the one action."""

    barrier_finding: BarrierFinding
    recommended_action: RecommendedAction
