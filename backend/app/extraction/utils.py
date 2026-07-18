"""Small value-coercion helpers used by the extraction schema."""

from __future__ import annotations

from typing import List


def coerce_string_to_list(value: str | List[str]) -> List[str]:
    """Coerces a bare string into a single-item list.

    DSPy's structured output occasionally returns a single string for a
    field typed as a list (e.g. when the model finds only one item and
    "simplifies" its answer). Pydantic's `BeforeValidator` runs this
    before the normal `list[str]` validation, so both shapes end up
    valid.

    Args:
        value: Either a plain string or an already-list value.

    Returns:
        The value wrapped in a list if it was a bare string; otherwise
        the value unchanged (still validated as `list[str]` afterwards).
    """
    if isinstance(value, str):
        return [value]
    return value
