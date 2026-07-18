"""Async SQLAlchemy engine/session setup.

Schema management is Alembic's job exclusively (`alembic upgrade head`)
-- there is deliberately no `create_all()`/`init_db()` helper here, so
the database schema and the migration history can never silently drift
apart.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

T = TypeVar("T")

settings = get_settings()
Path(settings.UPLOAD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models (see `app.db.models`)."""


# NullPool rather than a real connection pool: this backend is called
# from two different execution contexts -- FastAPI's single long-lived
# event loop, and Celery tasks bridged via `run_async` below, where
# *each call* spins up and tears down its own fresh event loop. asyncpg
# connections are bound to the event loop that created them, so a real
# pool's cached connections would go stale/unusable the moment a
# Celery task's loop closes. NullPool (a fresh connection per checkout)
# is the simplest way to keep both contexts safe with one engine
# definition, at the cost of some connection-setup overhead under
# FastAPI -- an acceptable trade for this app's scale.
async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def run_async(coro: Awaitable[T]) -> T:
    """Bridges an async coroutine into a synchronous call site.

    Celery tasks are synchronous by default, while this backend's data
    layer is entirely async; this is the single bridge between the two.
    Each call gets its own event loop, which pairs with `NullPool` above
    to keep asyncpg happy regardless of which thread/process invokes it.

    Args:
        coro: The coroutine to run to completion.

    Returns:
        The coroutine's result.
    """
    return asyncio.run(coro)
