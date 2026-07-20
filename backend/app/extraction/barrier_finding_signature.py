"""DSPy signature for Steps D+E: finding the barrier condition between
fatal and near-miss cases, and recommending one action.
"""
import dspy

from app.extraction.event_analysis import EventAnalysisFindings


class FindBarrierCondition(dspy.Signature):
    """
    SYSTEM ROLE
    You are a maritime safety analyst looking for what actually separates a near miss from a fatality in the same kind of operation.

    OBJECTIVE
    Compare the contributing factors, root causes, and immediate causes across two groups of historical reports for the same operation/vessel combination -- the near-miss group and the fatal group -- and identify the one specific condition or missing control that was present across the fatal cases but absent from the near-miss cases. Then recommend one concrete action for today, grounded in that finding.

    CRITICAL INSTRUCTIONS
    1. The barrier condition must be a real, specific condition or missing control drawn from the provided reports' actual text -- not a generic category invented to sound plausible ("poor safety culture" is not acceptable; "no secondary retention on the suspended load" is).
    2. Every citation must reference a real report id and field name that is actually present in the provided context.
    3. If the near-miss and fatal groups' contributing factors don't show a clear, consistent difference -- e.g. both groups mention similar factors, or the fatal group is too small/thin to support a real pattern -- say so plainly in the finding rather than forcing a distinction that isn't actually supported by the evidence.
    4. The recommended action must be a direct, specific command aimed at whoever is about to do this operation next ("Test the atmosphere at the bottom of the hold immediately before entry, not just at the top"), never a passive or generic recommendation ("Improve atmosphere testing procedures"). At most two sentences.
    5. If there are zero fatal cases to compare against, state in the finding that no fatal cases exist for this operation/vessel combination in the record, and base the recommended action on whatever near-miss/serious patterns are available instead.
    """

    described_event: str = dspy.InputField(
        desc="The user's original event description plus its classification, for context."
    )
    near_miss_context: str = dspy.InputField(
        desc="Formatted contributing factors/root causes/immediate causes from the near-miss group's reports, each tagged with its report id and source page numbers."
    )
    fatal_context: str = dspy.InputField(
        desc="Formatted contributing factors/root causes/immediate causes from the fatal group's reports, each tagged with its report id and source page numbers."
    )
    near_miss_count: int = dspy.InputField(desc="Total number of matching near-miss reports.")
    serious_count: int = dspy.InputField(desc="Total number of matching serious (nonfatal injury) reports.")
    fatal_count: int = dspy.InputField(desc="Total number of matching fatal reports.")
    findings: EventAnalysisFindings = dspy.OutputField(
        desc="The barrier finding and the one recommended action, each with citations."
    )
