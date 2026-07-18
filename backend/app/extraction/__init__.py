"""DSPy-based maritime incident extraction.

Only `signature.py` (`ExtractMaritimeReport`) is preserved verbatim from
the originally supplied code, since its docstring is the actual LLM
prompt. Everything else in this package (`incident.py`, `metadata.py`,
`utils.py`, `service.py`) has been reorganized and integrated into the
application (absolute imports, Settings-driven configuration, Google
style docstrings) rather than kept as an untouched, separately-vendored
package.
"""

from app.extraction.incident import MaritimeIncident  # noqa: F401
from app.extraction.metadata import (  # noqa: F401
    Attribute,
    CoercedList,
    EvidenceMetadata,
    ExtractionMetadata,
    Metadata,
    StatusMetadata,
)
from app.extraction.service import (  # noqa: F401
    ExtractionError,
    ExtractionService,
    extract_report,
    get_extraction_service,
)
from app.extraction.signature import ExtractMaritimeReport  # noqa: F401
