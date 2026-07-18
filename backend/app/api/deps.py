"""Dependency-injection providers used by every router.

Routers depend on these functions (`Depends(...)`) rather than
importing/constructing engines, sessions, or clients directly -- keeps
routers thin, testable, and swappable (e.g. override `get_db_session` in
tests to point at an in-memory database).
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from app.core.config import Settings, get_settings
from app.db.base import AsyncSessionLocal
from app.vectorstore.qdrant_store import get_qdrant_client


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields one DB session per request.

    Yields:
        An `AsyncSession`, closed automatically once the request finishes.
    """
    async with AsyncSessionLocal() as session:
        yield session


def get_qdrant() -> QdrantClient:
    """Provides the process-wide Qdrant client.

    Returns:
        The shared `QdrantClient` instance.
    """
    return get_qdrant_client()


#: Typed aliases for concise handler signatures.
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
QdrantDep = Annotated[QdrantClient, Depends(get_qdrant)]
