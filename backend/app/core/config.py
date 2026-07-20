"""Single source of truth for every configurable value in the backend.

Everything is exposed as an environment variable (loadable from a
`.env` file) via `pydantic-settings`. No module anywhere else should
read `os.environ` directly -- import `get_settings()` instead, so there
is exactly one place that knows where the PostgreSQL database lives, where
Qdrant stores its data, what the Redis URL is, how the DSPy extraction
pipeline is configured, and so on.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application-wide configuration, sourced from environment variables.

    Attributes:
        APP_NAME: Human-readable application name, used in the health
            endpoint and MLflow experiment naming.
        ENVIRONMENT: Deployment environment label (e.g. "development",
            "production"); informational only.
        API_V1_PREFIX: URL prefix under which every router is mounted.
        DEBUG: Enables FastAPI's debug mode.
        CORS_ORIGINS: Comma-separated list of allowed frontend origins.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------
    APP_NAME: str = "iMaritime API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @computed_field
    @property
    def cors_origins_list(self) -> list[str]:
        """Parses `CORS_ORIGINS` into a list of origin strings.

        Returns:
            The comma-separated `CORS_ORIGINS` value split into a
            trimmed, non-empty list of origins.
        """
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ------------------------------------------------------------------
    # Relational database (PostgreSQL via async SQLAlchemy).
    # Runs as a Docker container by default -- see compose.yaml, started
    # automatically by init.py if nothing is already listening on
    # POSTGRES_HOST:POSTGRES_PORT.
    # ------------------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "imaritime"
    POSTGRES_PASSWORD: str = "imaritime"
    POSTGRES_DB: str = "imaritime"

    @computed_field
    @property
    def database_url(self) -> str:
        """Builds the async SQLAlchemy database URL from the `POSTGRES_*` settings.

        Returns:
            A `postgresql+asyncpg://...` connection URL.
        """
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ------------------------------------------------------------------
    # File storage for uploaded source documents (PDF/TXT/MD/JSONL)
    # ------------------------------------------------------------------
    UPLOAD_STORAGE_DIR: str = str(BASE_DIR / "uploads")
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024

    # ------------------------------------------------------------------
    # Vector database (Qdrant) -- runs as a server (Docker container by
    # default; `setup.py` starts one automatically if nothing is already
    # listening on QDRANT_URL). Local/embedded on-disk mode is
    # intentionally not supported -- always connects over HTTP.
    # ------------------------------------------------------------------
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "reports"
    #: Minimum cosine similarity score (0-1) for a Qdrant hit to count as
    #: a genuine semantic match. Without this, Qdrant happily returns
    #: the "top N nearest" vectors regardless of how dissimilar they
    #: actually are -- with a small collection, that means literally
    #: every report can come back as a "semantic match" for any query,
    #: including nonsense ones. Tune this against your embedding model:
    #: 0.5 is a reasonable starting point for bge-small-en-v1.5.
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.5
    QDRANT_DOCKER_IMAGE: str = "qdrant/qdrant"
    QDRANT_CONTAINER_NAME: str = "imaritime-qdrant"

    # ------------------------------------------------------------------
    # Intelligence briefs
    # ------------------------------------------------------------------
    #: Maximum number of reports a single brief-generation job can be
    #: built from. Enforced both by the request schema
    #: (`CreateBriefJobRequest`) and re-checked by the frontend before
    #: it even calls the API, so the two never drift apart -- the
    #: frontend reads this value from `GET /api/v1/config`.
    MAX_REPORTS_PER_BRIEF: int = 5

    # ------------------------------------------------------------------
    # Embeddings (for semantic search over reports)
    # ------------------------------------------------------------------
    EMBEDDING_PROVIDER: str = "fastembed"
    FASTEMBED_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    FASTEMBED_VECTOR_SIZE: int = 384
    #: Max seconds /reports/search will wait on the embed+Qdrant step of
    #: hybrid search before giving up and falling back to keyword-only
    #: results. Semantic search is an enhancement, not a hard dependency
    #: -- a slow/unreachable embedding provider (e.g. blocked model
    #: download) must never stall the whole report list.
    SEMANTIC_SEARCH_TIMEOUT_SECONDS: float = 3.0
    #: How many semantically-similar reports Step B pulls in for event
    #: analysis, on top of whatever matches operation_type/vessel_type
    #: exactly. Reuses SEMANTIC_SIMILARITY_THRESHOLD as its relevance
    #: cutoff rather than a second, separate threshold.
    EVENT_ANALYSIS_SEMANTIC_TOP_N: int = 10
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_VECTOR_SIZE: int = 1536
    OPENAI_API_KEY: str | None = None

    @computed_field
    @property
    def embedding_vector_size(self) -> int:
        """Resolves the active embedding provider's vector dimensionality.

        Returns:
            `OPENAI_EMBEDDING_VECTOR_SIZE` if `EMBEDDING_PROVIDER` is
            "openai", otherwise `FASTEMBED_VECTOR_SIZE`.
        """
        return (
            self.OPENAI_EMBEDDING_VECTOR_SIZE
            if self.EMBEDDING_PROVIDER == "openai"
            else self.FASTEMBED_VECTOR_SIZE
        )

    STORE_FULL_REPORT_TEXT: bool = True

    # ------------------------------------------------------------------
    # Redis / Celery (background ingestion pipeline)
    # ------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    CELERY_TASK_TIME_LIMIT: int = 900
    #: If a job hasn't been updated in this many seconds and isn't in a
    #: terminal state (completed/failed), it's treated as stalled and
    #: auto-marked failed the next time it's listed (see
    #: app/db/job_reconciliation.py). This is a safety net independent
    #: of Celery/Redis's own recovery (broker_transport_options
    #: visibility_timeout, task_acks_late) -- it catches any way a job
    #: could otherwise sit frozen forever (worker never came back,
    #: Celery wasn't running at all, etc.), not just the specific
    #: Redis-visibility-timeout gotcha. Should comfortably exceed
    #: CELERY_TASK_TIME_LIMIT so it never fires on a task that's still
    #: legitimately running.
    JOB_STALE_AFTER_SECONDS: int = 1800

    @computed_field
    @property
    def celery_broker_url(self) -> str:
        """Resolves the Celery broker URL, defaulting to `REDIS_URL`.

        Returns:
            `CELERY_BROKER_URL` if explicitly set, otherwise `REDIS_URL`.
        """
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @computed_field
    @property
    def celery_result_backend(self) -> str:
        """Resolves the Celery result backend URL, defaulting to `REDIS_URL`.

        Returns:
            `CELERY_RESULT_BACKEND` if explicitly set, otherwise `REDIS_URL`.
        """
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    # ------------------------------------------------------------------
    # DSPy extraction pipeline (app.extraction.service.ExtractionService)
    # ------------------------------------------------------------------
    MODEL: str = ""
    API_BASE: str = ""
    API_KEY: str = ""

    #: Passed to `dspy.LM(..., max_retries=...)`.
    DSPY_LM_MAX_RETRIES: int = 12
    #: Passed to `dspy.Predict(...).batch(..., num_threads=...)`.
    DSPY_NUM_THREADS: int = 8
    #: Passed to `dspy.Predict(...).batch(..., timeout=...)`, in seconds.
    DSPY_BATCH_TIMEOUT_SECONDS: int = 300
    #: Structured-output adapter: "json" (dspy.JSONAdapter) or "chat"
    #: (DSPy's default chat-based adapter, no explicit adapter set).
    DSPY_ADAPTER: str = "json"

    # ------------------------------------------------------------------
    # MLflow (DSPy call tracing / experiment tracking)
    # ------------------------------------------------------------------
    MLFLOW_EXPERIMENT_NAME: str = "imaritime"
    MLFLOW_TRACKING_URI: str | None = None
    MLFLOW_LOG_TRACES: bool = True
    MLFLOW_LOG_TRACES_FROM_COMPILE: bool = True
    MLFLOW_LOG_TRACES_FROM_EVAL: bool = True
    MLFLOW_LOG_COMPILES: bool = True
    MLFLOW_LOG_EVALS: bool = True

    # ------------------------------------------------------------------
    # Intelligence brief generation (app.extraction.brief_service)
    # ------------------------------------------------------------------
    #: Maximum number of matching reports included in one brief-generation
    #: LLM call's context, to keep prompt size bounded for
    #: high-recurrence operation/vessel pairings.
    BRIEF_MAX_REPORTS_CONTEXT: int = 60

    # ------------------------------------------------------------------
    # Open-vocabulary fields: DB column name -> DSPy signature input name
    # ------------------------------------------------------------------
    OPEN_VOCAB_FIELD_MAP: dict[str, str] = {
        "operation_type": "operation_types",
        "vessel_type": "vessel_types",
        "casual_signature": "root_cause_signatures",
    }


@lru_cache
def get_settings() -> Settings:
    """Returns the process-wide cached `Settings` instance.

    Returns:
        A `Settings` instance populated from environment variables /
        `.env`, constructed once per process and reused thereafter.
    """
    return Settings()
