"""Pluggable embedding provider, selected via `Settings.EMBEDDING_PROVIDER`.

- "fastembed" (default): a small local ONNX model via the `fastembed`
  package. No API key, no GPU/torch required, runs fully offline.
- "openai": OpenAI's embeddings API, for higher-quality vectors if an
  API key is available.

Both are imported lazily so picking one doesn't require the other's
dependency to be installed.
"""

from __future__ import annotations

import threading
from typing import Optional, Protocol

from app.core.config import get_settings

settings = get_settings()


class EmbeddingProvider(Protocol):
    """Interface every embedding provider implements."""

    def embed(self, text: str) -> list[float]:
        """Embeds a single string.

        Args:
            text: The text to embed.

        Returns:
            A dense embedding vector.
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds multiple strings in one call.

        Args:
            texts: The texts to embed.

        Returns:
            One embedding vector per input text, in the same order.
        """
        ...


class FastEmbedProvider:
    """Local, offline embedding provider backed by the `fastembed` package."""

    def __init__(self, model_name: str) -> None:
        """Loads a FastEmbed model.

        Args:
            model_name: The FastEmbed/Hugging Face model identifier to load.
        """
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed(self, text: str) -> list[float]:
        """Embeds a single string.

        Args:
            text: The text to embed.

        Returns:
            A dense embedding vector.
        """
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds multiple strings in one call.

        Args:
            texts: The texts to embed.

        Returns:
            One embedding vector per input text, in the same order.
        """
        return [vec.tolist() for vec in self._model.embed(texts)]


class OpenAIEmbedProvider:
    """Embedding provider backed by OpenAI's embeddings API."""

    def __init__(self, model_name: str, api_key: Optional[str]) -> None:
        """Initializes the OpenAI client.

        Args:
            model_name: The OpenAI embedding model to use.
            api_key: OpenAI API key.

        Raises:
            RuntimeError: If `api_key` is not provided.
        """
        from openai import OpenAI

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai"
            )
        self._client = OpenAI(api_key=api_key)
        self._model_name = model_name

    def embed(self, text: str) -> list[float]:
        """Embeds a single string.

        Args:
            text: The text to embed.

        Returns:
            A dense embedding vector.
        """
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeds multiple strings in one call.

        Args:
            texts: The texts to embed.

        Returns:
            One embedding vector per input text, in the same order.
        """
        response = self._client.embeddings.create(model=self._model_name, input=texts)
        return [item.embedding for item in response.data]


_provider_instance: Optional[EmbeddingProvider] = None
_provider_error: Optional[Exception] = None
_construction_lock = threading.Lock()


class ProviderInitializingError(Exception):
    """Raised when the embedding provider's (slow) first construction is
    already underway on another thread -- callers should treat this the
    same as any other embedding failure (fall back to keyword-only
    search) rather than piling on a redundant construction attempt."""


def get_embedding_provider() -> EmbeddingProvider:
    """Returns the process-wide embedding provider, per `Settings.EMBEDDING_PROVIDER`.

    The result (success or failure) is memoized manually rather than via
    `functools.lru_cache`, which does not cache exceptions -- without
    this, a provider that fails to construct (e.g. a blocked model
    download) would retry that same expensive failure on every single
    call instead of failing fast after the first attempt.

    Construction also guards against concurrent callers: if one thread
    is already constructing the provider (which, on first use, may mean
    a slow model download), a concurrent call fails fast with
    `ProviderInitializingError` instead of starting a second, redundant
    construction attempt of its own. Combined with a bounded per-request
    timeout at the call site (see `app.api.routers.reports`), this keeps
    every individual request fast even while the *first* construction
    attempt is still working in the background.

    Returns:
        A `FastEmbedProvider` or `OpenAIEmbedProvider`, constructed once
        per process.

    Raises:
        ProviderInitializingError: If another thread is already
            constructing the provider.
        Exception: Whatever the provider's constructor raised on its
            first (and only) construction attempt.
    """
    global _provider_instance, _provider_error

    if _provider_instance is not None:
        return _provider_instance
    if _provider_error is not None:
        raise _provider_error

    if not _construction_lock.acquire(blocking=False):
        raise ProviderInitializingError(
            "Embedding provider is still initializing (first-use model load in progress)."
        )

    try:
        # Re-check now that we hold the lock: another thread may have
        # just finished (successfully or not) while we were waiting on it.
        if _provider_instance is not None:
            return _provider_instance
        if _provider_error is not None:
            raise _provider_error

        if settings.EMBEDDING_PROVIDER == "openai":
            _provider_instance = OpenAIEmbedProvider(
                settings.OPENAI_EMBEDDING_MODEL, settings.OPENAI_API_KEY
            )
        else:
            _provider_instance = FastEmbedProvider(settings.FASTEMBED_MODEL_NAME)
        return _provider_instance
    except Exception as exc:  # noqa: BLE001 - memoize any construction failure
        _provider_error = exc
        raise
    finally:
        _construction_lock.release()


def build_embedding_text(report_data: dict) -> str:
    """Builds the text to embed for one report, from its structured fields.

    Args:
        report_data: A dict of report field values (title, type,
            operation_type, vessel_type, location, casual_signature,
            root_causes, contributing_factors, lessons_learned,
            keywords, full_text).

    Returns:
        A single string concatenating the fields most useful for
        semantic similarity, falling back to a slice of the full parsed
        document text if little structured data is available yet.
    """
    parts = [
        report_data.get("incident_title"),
        report_data.get("incident_type"),
        report_data.get("operation_type"),
        report_data.get("vessel_type"),
        report_data.get("location"),
        report_data.get("casual_signature"),
        " ".join(report_data.get("root_causes") or []),
        " ".join(report_data.get("contributing_factors") or []),
        " ".join(report_data.get("lessons_learned") or []),
        " ".join(report_data.get("keywords") or []),
    ]
    text = " | ".join(p for p in parts if p)
    if len(text) < 40 and report_data.get("full_text"):
        text = report_data["full_text"][:4000]
    return text or (report_data.get("incident_title") or "untitled report")


def embedding_provider_status() -> str:
    """Reports the embedding provider's current lifecycle state.

    Used by the health endpoint and by `app.main`'s startup warm-up
    logging -- introspects the same module-level state
    `get_embedding_provider()` manages, without triggering construction.

    Returns:
        "ready" if constructed successfully, "unavailable" if
        construction previously failed, "initializing" if construction
        is currently underway on another thread, or "not_started" if
        nothing has attempted construction yet.
    """
    if _provider_instance is not None:
        return "ready"
    if _provider_error is not None:
        return "unavailable"
    if _construction_lock.locked():
        return "initializing"
    return "not_started"
