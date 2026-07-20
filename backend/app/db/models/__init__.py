"""ORM models, one class per file, all re-exported from here.

Import `from app.db.models import Report, FieldMetadata, VocabularyTerm,
IngestionJob, BriefJob, EventAnalysisJob` rather than reaching into individual submodules
-- this is also what registers every model class with `Base`'s shared
declarative registry (needed for Alembic autogenerate and for cross-file
`relationship()` string references to resolve correctly).
"""

from app.db.models.brief_job import BriefJob  # noqa: F401
from app.db.models.field_metadata import FieldMetadata  # noqa: F401
from app.db.models.ingestion_job import IngestionJob  # noqa: F401
from app.db.models.report import Report  # noqa: F401
from app.db.models.vocabulary_term import VocabularyTerm  # noqa: F401
from app.db.models.event_analysis_job import EventAnalysisJob  # noqa: F401

__all__ = ["Report", "FieldMetadata", "VocabularyTerm", "IngestionJob", "BriefJob", "EventAnalysisJob"]
