"""DSPy signature for Step A: classifying a free-text event description."""
import dspy

from app.extraction.event_analysis import EventClassification


class ClassifyEventDescription(dspy.Signature):
    """
    SYSTEM ROLE
    You are a maritime safety analyst triaging a just-described event so it can be compared against the historical incident record.

    OBJECTIVE
    Read the operator's plain-language description and extract exactly what operation and vessel type it concerns, restate what happened in one sentence, and classify its severity outcome.

    CRITICAL INSTRUCTIONS
    1. Match operation_type and vessel_type to one of the provided known-vocabulary lists whenever the description plausibly fits one -- do not invent a new label if an existing one already covers it.
    2. Only invent a new, general label if genuinely nothing in the known lists fits -- and if you do, keep it as general and short as the existing labels, not specific to this one description.
    3. severity_stage reflects the ACTUAL OUTCOME described, not how dangerous the situation sounds: "felt dizzy, climbed back out, no injury" is near_miss even though it could easily have been fatal. Only classify serious if an actual injury (however minor) is stated, and only fatal if a death is stated.
    4. Do not add details the description doesn't contain. If something is ambiguous, make the most reasonable reading rather than fabricating specifics.
    """

    description: str = dspy.InputField(desc="The user's free-text description of the event.")
    operation_types: list[str] = dspy.InputField(
        desc="Known operation type vocabulary to match against, same list used by the main extraction pipeline."
    )
    vessel_types: list[str] = dspy.InputField(
        desc="Known vessel type vocabulary to match against, same list used by the main extraction pipeline."
    )
    classification: EventClassification = dspy.OutputField(
        desc="The classified operation type, vessel type, event summary, and severity stage."
    )
