"""Inspecting the current open-vocabulary term lists.

Useful for debugging/admin visibility into exactly what the LLM is
being shown for `operation_type`/`vessel_type`/`casual_signature` on the
next extraction call.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSessionDep
from app.core.config import get_settings
from app.db import vocab_crud

router = APIRouter(prefix="/vocab", tags=["vocabulary"])

settings = get_settings()


@router.get("/{field_name}", response_model=list[str])
async def get_vocabulary(field_name: str, db: DbSessionDep) -> list[str]:
    """Lists the current known values for one open-vocabulary field.

    Args:
        field_name: One of `Settings.OPEN_VOCAB_FIELD_MAP`'s keys
            (operation_type, vessel_type, casual_signature).
        db: Injected DB session.

    Returns:
        The current known-value list for that field.

    Raises:
        HTTPException: 400 if `field_name` isn't open-vocabulary.
    """
    if field_name not in settings.OPEN_VOCAB_FIELD_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"'{field_name}' is not an open-vocabulary field. "
            f"Valid options: {list(settings.OPEN_VOCAB_FIELD_MAP)}",
        )
    return await vocab_crud.get_vocabulary(db, field_name)


@router.get("", response_model=dict[str, list[str]])
async def get_all_vocabularies(db: DbSessionDep) -> dict[str, list[str]]:
    """Lists all open-vocabulary fields' known values at once.

    Args:
        db: Injected DB session.

    Returns:
        A dict keyed by DB column name, mapping to each field's known values.
    """
    return {
        field_name: await vocab_crud.get_vocabulary(db, field_name)
        for field_name in settings.OPEN_VOCAB_FIELD_MAP
    }
