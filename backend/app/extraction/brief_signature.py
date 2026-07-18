"""DSPy signature for the intelligence brief generator.

Unlike `app.extraction.signature.ExtractMaritimeReport` (preserved
verbatim from the originally-supplied extraction code), this signature
is new: it synthesizes a single-screen operational brief from a set of
already-extracted, already-grouped incident reports for one operation
type / vessel class pair.
"""

import dspy

from app.extraction.brief import IntelligenceBrief


class GenerateIntelligenceBrief(dspy.Signature):
    """
    SYSTEM ROLE
    You are a maritime safety intelligence analyst producing a single-screen operational brief for one operation type and vessel class combination, synthesized from a set of prior investigated incident reports covering that same combination.

    OBJECTIVE
    Produce a structured brief with exactly these sections -- a recurrence statement, the dominant pattern that kills, a compliance-illusion finding, and up to three direct action lines -- each grounded strictly in the provided report context, with every claim traceable to a specific report id and extracted field.

    CRITICAL INSTRUCTIONS (RULES OF ENGAGEMENT)
    1. NEVER invent facts, numbers, reports, or details that are not present in the provided context.
    2. Use the exact recurrence numbers you are given (incident count, total injuries, total fatalities, year range) verbatim in the recurrence statement -- do not recompute, round, or estimate them.
    3. Every section's citations must reference real report ids and field names that are actually present in the provided reports context.
    4. Write the "pattern that kills" description with specific, visceral, concrete detail drawn primarily from the highlighted most-representative report -- not a generic restatement of the causal signature label. Prefer describing the actual mechanism of failure over abstract category names.
    5. Action lines must be direct imperative commands aimed at whoever runs this operation next ("Test the atmosphere at the bottom of the hold immediately before entry, not just at the top"), never passive or hedged recommendations ("It is recommended that atmosphere testing procedures be reviewed").
    6. Produce at most 3 action lines, prioritizing whichever corrective actions recur most often across the provided reports.
    7. If the provided context does not contain enough information to support the compliance-illusion finding (e.g. no permit-to-work or procedural information appears anywhere in the reports), state plainly that this could not be determined from the available reports, rather than fabricating a finding.
    8. If two causal signatures are close in frequency, choose the strictly most frequent one as given in top_causal_signature -- do not substitute a different one you judge more interesting.
    """

    operation_type: str = dspy.InputField(
        desc="The maritime operation type this brief covers."
    )
    vessel_type: str = dspy.InputField(desc="The vessel class this brief covers.")
    incident_count: int = dspy.InputField(
        desc="Total number of matching incident reports."
    )
    total_injuries: int = dspy.InputField(
        desc="Total injuries summed across all matching reports."
    )
    total_fatalities: int = dspy.InputField(
        desc="Total fatalities summed across all matching reports."
    )
    year_range: str = dspy.InputField(
        desc="The earliest-to-latest incident year span across matching reports, e.g. '2014-2023'. "
        "May be 'unknown' if no matching reports have a known incident date."
    )
    top_causal_signature: str = dspy.InputField(
        desc="The single most frequently recurring causal signature label across matching reports."
    )
    most_representative_report_id: int = dspy.InputField(
        desc="The report id, within the top causal-signature group, with the highest "
        "extraction confidence. Pull the vivid, specific detail for the 'pattern that "
        "kills' section primarily from this report."
    )
    reports_context: str = dspy.InputField(
        desc="Formatted context: for each matching report, its id followed by its "
        "relevant extracted fields (sequence_of_events, immediate_causes, root_causes, "
        "contributing_factors, corrective_actions, lessons_learned, regulatory_issues) "
        "with source page numbers where available."
    )
    brief: IntelligenceBrief = dspy.OutputField(
        desc="The complete structured intelligence brief adhering exactly to the schema."
    )
