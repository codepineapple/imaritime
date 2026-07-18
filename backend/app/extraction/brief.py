"""Structured output schema for the intelligence brief.

Every section carries its own `citations` -- each pointing at a
specific report id and extracted field name -- since traceability back
to source reports is a hard requirement, not a nice-to-have.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class BriefCitation(BaseModel):
    """A single traceability link from a brief section back to source data."""

    report_id: int = Field(description="The report id this citation refers to.")
    field_name: str = Field(
        description="The extracted field name this citation draws from "
        "(e.g. 'root_causes', 'corrective_actions')."
    )
    page_numbers: List[int] = Field(
        default_factory=list,
        description="Source page numbers within that report, if known.",
    )


class RecurrenceStatement(BaseModel):
    """Section 1: how often this pattern has recurred, in plain numbers."""

    statement: str = Field(
        description="One or two sentences following the pattern: 'X people have "
        "died or been seriously injured in this operation on this vessel class. "
        "[N] incidents recorded over [year range].' Use the exact numbers "
        "provided in the input verbatim -- do not estimate, round, or invent them."
    )
    citations: List[BriefCitation] = Field(default_factory=list)


class PatternThatKills(BaseModel):
    """Section 2: the single most common causal pattern, described vividly."""

    causal_signature: str = Field(
        description="The most frequently recurring causal signature label across matching reports."
    )
    description: str = Field(
        description="One or two vivid, specific plain-language sentences describing "
        "exactly how this pattern kills, grounded in the highlighted most-"
        "representative report's actual details -- not a generic restatement "
        "of the causal signature label."
    )
    citations: List[BriefCitation] = Field(default_factory=list)


class ComplianceIllusionFinding(BaseModel):
    """Section 3: whether formal process existed yet still failed."""

    finding: str = Field(
        description="One or two sentences on whether a permit or procedure existed "
        "in the fatal/serious cases yet still failed to prevent the incident, "
        "drawn from corrective_actions/lessons_learned/regulatory_issues across "
        "the matching reports. If this cannot be determined from the available "
        "reports, state that plainly instead of fabricating a finding."
    )
    citations: List[BriefCitation] = Field(default_factory=list)


class ActionLine(BaseModel):
    """One of up to three direct, imperative corrective-action commands."""

    action: str = Field(
        description="A single direct imperative command (e.g. 'Test the "
        "atmosphere at the bottom of the hold before entry'), not a passive "
        "recommendation (not 'It is recommended that testing be improved')."
    )
    citations: List[BriefCitation] = Field(default_factory=list)


class IntelligenceBrief(BaseModel):
    """The complete structured intelligence brief for one operation/vessel pair."""

    recurrence_statement: RecurrenceStatement
    pattern_that_kills: PatternThatKills
    compliance_illusion_finding: ComplianceIllusionFinding
    action_lines: List[ActionLine] = Field(
        description="At most 3 action lines, prioritized by how often the "
        "underlying corrective action recurs across matching reports."
    )
