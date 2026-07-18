"""Grouping matching reports by an open-vocabulary field, ranked by
recurrence -- "how many times has this pattern appeared".
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSessionDep
from app.api.routers.reports import build_report_filters
from app.db.grouping import GROUPABLE_FIELDS, group_reports
from app.schemas.report_schemas import CausalGroupOut, GroupByRequest

router = APIRouter(prefix="/groups", tags=["causal grouping"])


@router.post("", response_model=list[CausalGroupOut])
async def get_report_groups(
    params: GroupByRequest, db: DbSessionDep
) -> list[CausalGroupOut]:
    """Groups reports matching the given filters, ranked by recurrence count.

    Args:
        params: Grouping field plus the same filter criteria as
            `POST /reports/search`.
        db: Injected DB session.

    Returns:
        Groups ordered by descending recurrence count.

    Raises:
        HTTPException: 400 if `params.group_by` isn't a groupable field.
    """
    if params.group_by not in GROUPABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"'{params.group_by}' is not groupable. Options: {sorted(GROUPABLE_FIELDS)}",
        )
    filters = build_report_filters(params)
    groups = await group_reports(db, params.group_by, filters, limit=params.limit)
    return [CausalGroupOut(**vars(g)) for g in groups]
