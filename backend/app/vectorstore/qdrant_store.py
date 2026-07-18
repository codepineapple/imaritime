"""Thin wrapper around `qdrant_client`.

Connects to a Qdrant server over HTTP (`Settings.QDRANT_URL`) -- see
`setup.py`, which starts a local Docker container automatically if
nothing is already listening there. Local/embedded on-disk mode is
intentionally not used, so Qdrant behaves the same way in every
environment (dev container, CI, production) rather than silently
falling back to a file on disk.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_qdrant_client() -> QdrantClient:
    """Returns the process-wide Qdrant client.

    Returns:
        A `QdrantClient` connected to `Settings.QDRANT_URL` (a Qdrant
        server -- typically the Docker container `setup.py` starts).
    """
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


def ensure_collection(client: Optional[QdrantClient] = None) -> None:
    """Creates the reports collection if it doesn't already exist.

    Args:
        client: Qdrant client to use. Defaults to `get_qdrant_client()`.
    """
    client = client or get_qdrant_client()
    collections = {c.name for c in client.get_collections().collections}
    if settings.QDRANT_COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(
                size=settings.embedding_vector_size, distance=Distance.COSINE
            ),
        )


def upsert_report_vector(
    report_id: int,
    vector: list[float],
    payload: dict[str, Any],
    client: Optional[QdrantClient] = None,
) -> None:
    """Inserts or updates one report's vector and payload.

    Args:
        report_id: The report's primary key, used as the Qdrant point id.
        vector: The report's embedding vector.
        payload: Metadata stored alongside the vector (e.g. for filtering).
        client: Qdrant client to use. Defaults to `get_qdrant_client()`.
    """
    client = client or get_qdrant_client()
    ensure_collection(client)
    client.upsert(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points=[PointStruct(id=report_id, vector=vector, payload=payload)],
    )


def delete_report_vector(report_id: int, client: Optional[QdrantClient] = None) -> None:
    """Removes a report's vector from the collection.

    Args:
        report_id: The report's primary key / Qdrant point id.
        client: Qdrant client to use. Defaults to `get_qdrant_client()`.
    """
    client = client or get_qdrant_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME, points_selector=[report_id]
    )


def semantic_search(
    query_vector: list[float],
    limit: int = 10,
    incident_types: Optional[list[str]] = None,
    client: Optional[QdrantClient] = None,
    score_threshold: Optional[float] = None,
) -> list[tuple[int, float]]:
    """Finds the reports most semantically similar to a query vector.

    Args:
        query_vector: The embedded search query.
        limit: Maximum number of results to return.
        incident_types: Optional allow-list to restrict results to.
        client: Qdrant client to use. Defaults to `get_qdrant_client()`.
        score_threshold: Minimum cosine similarity for a hit to be
            included. Defaults to `Settings.SEMANTIC_SIMILARITY_THRESHOLD`.
            Without this, Qdrant returns the top `limit` nearest vectors
            unconditionally -- with a small collection, that means every
            report can qualify as a "match" for any query, however
            irrelevant, since there's nothing to say how similar is
            similar *enough*.

    Returns:
        `(report_id, similarity_score)` tuples meeting the threshold,
        ordered by relevance.
    """
    client = client or get_qdrant_client()
    ensure_collection(client)
    if score_threshold is None:
        score_threshold = settings.SEMANTIC_SIMILARITY_THRESHOLD

    query_filter = None
    if incident_types:
        query_filter = Filter(
            must=[
                FieldCondition(key="incident_type", match=MatchAny(any=incident_types))
            ]
        )

    result = client.query_points(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        query_filter=query_filter,
        score_threshold=score_threshold,
    )
    return [(int(point.id), point.score) for point in result.points]
