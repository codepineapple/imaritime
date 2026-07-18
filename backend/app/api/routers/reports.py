"""Browsing/filtering already-ingested reports.

Filtering is expressed as a JSON body (`ReportFilterParams`) rather than
flat query params, since it includes nested search tokens and several
list-valued fields -- awkward to express cleanly as GET query strings.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import DbSessionDep
from app.core.config import get_settings
from app.db import crud
from app.db import search as search_db
from app.db.crud import ReportFilters
from app.db.hybrid_search import report_matches_text
from app.schemas.report_schemas import (
    BulkDeleteResult,
    PaginatedReports,
    ReportDetail,
    ReportFilterParams,
    ReportIdsRequest,
    ReportListItem,
    SearchSuggestion,
    StatsOut,
)
from app.vectorstore.embeddings import get_embedding_provider
from app.vectorstore.qdrant_store import delete_report_vector, semantic_search

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


def build_report_filters(params: ReportFilterParams) -> ReportFilters:
    """Converts an API request body into a `ReportFilters` query object.

    Shared across routers (reports, groups, briefs) that all accept the
    same filter shape.

    Args:
        params: The validated request body (or any object exposing the
            same filter fields, e.g. `GroupByRequest`).

    Returns:
        A `ReportFilters` instance ready to pass to `app.db.crud`.
    """
    return ReportFilters(
        field_search_tokens=[t.model_dump() for t in params.field_search_tokens],
        date_from=params.date_from,
        date_to=params.date_to,
        min_injuries=params.min_injuries,
        min_fatalities=params.min_fatalities,
        confidence_min=params.confidence_min,
        confidence_max=params.confidence_max,
        human_review_required=params.human_review_required,
        has_data_in=params.has_data_in,
        operation_types=params.operation_types,
        vessel_types=params.vessel_types,
        casual_signatures=params.casual_signatures,
    )


def _free_text_query(params: ReportFilterParams) -> str:
    """Extracts and combines every "all fields" search token's text.

    Args:
        params: The request body to read search tokens from.

    Returns:
        The space-joined text of every token with `field == "all"`, or
        an empty string if there are none.
    """
    return " ".join(
        t.text.strip()
        for t in params.field_search_tokens
        if t.field == "all" and t.text.strip()
    )


async def _semantic_hits(free_text: str) -> dict[int, float]:
    """Embeds a query and finds semantically similar reports in Qdrant.

    Args:
        free_text: The free-text query to embed and search with.

    Returns:
        A dict of `{report_id: similarity_score}` for the top matches.

    Raises:
        Exception: Whatever the embedding provider or Qdrant client raises
            (e.g. a failed/blocked model download, or an unreachable
            Qdrant server) -- left to the caller to catch, since this
            step is an enhancement, not a hard dependency.
    """
    # get_embedding_provider() itself can block (its first call may
    # construct/download the model) -- it must run in the threadpool too,
    # not just .embed(), or the caller's asyncio.wait_for timeout can
    # never actually interrupt it: a synchronous call blocks the event
    # loop directly, and wait_for can only cancel at an await point.
    provider = await run_in_threadpool(get_embedding_provider)
    vector = await run_in_threadpool(provider.embed, free_text)
    hits = await run_in_threadpool(semantic_search, vector, 100)
    return dict(hits)


async def _resolve_semantic_scores(free_text: str) -> dict[int, float]:
    """Resolves semantic hits for a free-text query, bounded and fail-safe.

    Shared by every endpoint that needs to build a `ReportFilters` from
    the same free-text query (`/reports/search` and `/reports/stats`) --
    having each build its own filters from `params` but only one of them
    actually run this step was exactly the bug where the stats endpoint
    silently fell back to keyword-only counts while the table showed the
    full hybrid result set.

    Bounded by `Settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS` and never
    allowed to raise -- a slow or unreachable embedding provider
    degrades to keyword-only results (empty dict) instead of failing or
    stalling the caller.

    Args:
        free_text: The free-text query to embed and search with. If
            empty, returns `{}` immediately without touching the
            embedding provider/Qdrant at all.

    Returns:
        A dict of `{report_id: similarity_score}` for the matches found,
        or `{}` if there's no query, semantic search is unavailable, or
        it didn't respond in time.
    """
    if not free_text:
        return {}
    try:
        return await asyncio.wait_for(
            _semantic_hits(free_text), timeout=settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS
        )
    except Exception:  # noqa: BLE001
        # Semantic search is an enhancement, not a hard dependency -- if
        # the embedding provider/Qdrant is unavailable or too slow, fall
        # back to keyword-only results rather than failing (or
        # stalling) the request.
        return {}


@router.post("/search", response_model=PaginatedReports)
async def search_reports(
    params: ReportFilterParams, db: DbSessionDep
) -> PaginatedReports:
    """Lists reports matching the given filters, paginated and sorted.

    When a free-text ("all fields") search token is present, this also
    runs a semantic similarity search over the same text (via the
    configured embedding provider + Qdrant) and includes semantically
    similar reports in the result set alongside keyword matches, even if
    they don't share a literal keyword. Each result is labeled with how
    it matched: "keyword", "semantic", or "both".

    The semantic step is bounded by `Settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS`
    and never allowed to fail the request -- a slow or unreachable
    embedding provider degrades to keyword-only results instead of
    stalling the whole report list.

    Args:
        params: Filter/pagination/sort criteria.
        db: Injected DB session.

    Returns:
        A page of matching reports plus the total matching count, each
        annotated with its match type when a free-text query is active.
    """
    free_text = _free_text_query(params)
    semantic_scores = await _resolve_semantic_scores(free_text)

    filters = build_report_filters(params)
    filters.semantic_report_ids = list(semantic_scores.keys())

    reports, total = await crud.list_reports(
        db,
        filters,
        page=params.page,
        page_size=params.page_size,
        sort_by=params.sort_by,
        sort_dir=params.sort_dir,
    )

    items = []
    for report in reports:
        match_type = None
        if free_text:
            is_keyword_match = report_matches_text(report, free_text)
            is_semantic_match = report.id in semantic_scores
            if is_keyword_match and is_semantic_match:
                match_type = "both"
            elif is_semantic_match:
                match_type = "semantic"
            elif is_keyword_match:
                match_type = "keyword"
        item = ReportListItem.model_validate(report).model_copy(
            update={
                "match_type": match_type,
                "semantic_score": semantic_scores.get(report.id),
            }
        )
        items.append(item)

    return PaginatedReports(
        items=items, total=total, page=params.page, page_size=params.page_size
    )


@router.post("/stats", response_model=StatsOut)
async def report_stats(params: ReportFilterParams, db: DbSessionDep) -> StatsOut:
    """Computes summary statistics for reports matching the given filters.

    Uses the same hybrid keyword+semantic resolution as `/reports/search`
    (see `_resolve_semantic_scores`) so the stat cards always describe
    the exact same result set the table is showing -- previously this
    endpoint never ran the semantic step at all, so a free-text search
    would show the full hybrid count/results in the table but only the
    keyword-only subset's stats at the top.

    Args:
        params: Filter criteria (pagination/sort fields are ignored).
        db: Injected DB session.

    Returns:
        Aggregate statistics (counts, average confidence) over the same
        result set `/reports/search` would return for these params.
    """
    free_text = _free_text_query(params)
    semantic_scores = await _resolve_semantic_scores(free_text)

    filters = build_report_filters(params)
    filters.semantic_report_ids = list(semantic_scores.keys())

    stats = await crud.get_stats(db, filters)
    return StatsOut(**stats)


@router.get("/suggestions", response_model=list[SearchSuggestion])
async def search_suggestions(
    db: DbSessionDep,
    q: str = Query(
        ..., min_length=1, description="Partial text to find field-tagged matches for"
    ),
) -> list[SearchSuggestion]:
    """Finds field-tagged autocomplete suggestions for a partial query.

    Args:
        db: Injected DB session.
        q: Partial search text.

    Returns:
        Suggestions tagged with the field they matched.
    """
    suggestions = await search_db.get_search_suggestions(db, q)
    return [SearchSuggestion(**s) for s in suggestions]


@router.get("/distinct/{column_name}", response_model=list[str])
async def distinct_values(column_name: str, db: DbSessionDep) -> list[str]:
    """Lists distinct values for one scalar column.

    Powers filter-option dropdowns (incident_type, location,
    operation_type, vessel_type, casual_signature) in the frontend.

    Args:
        column_name: Name of the scalar column to list distinct values for.
        db: Injected DB session.

    Returns:
        Sorted distinct non-null values for that column.

    Raises:
        HTTPException: 400 if `column_name` isn't an allowed column.
    """
    allowed = {
        "incident_type",
        "location",
        "operation_type",
        "vessel_type",
        "casual_signature",
    }
    if column_name not in allowed:
        raise HTTPException(
            status_code=400, detail=f"Cannot list distinct values for '{column_name}'"
        )
    return await crud.get_distinct_values(db, column_name)


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(report_id: int, db: DbSessionDep) -> ReportDetail:
    """Fetches full detail for one report, including per-field metadata.

    Args:
        report_id: Primary key of the report to fetch.
        db: Injected DB session.

    Returns:
        The full report detail.

    Raises:
        HTTPException: 404 if no report with that id exists.
    """
    report = await crud.get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return ReportDetail.model_validate(report)


@router.delete("/{report_id}", status_code=204)
async def delete_report_endpoint(report_id: int, db: DbSessionDep) -> None:
    """Permanently deletes a report, including its vector and source file.

    Best-effort cleans up everything else associated with the report
    before removing the DB row: its Qdrant vector (if it was ever
    embedded) and its stored source document on disk, if any. Neither
    of those failing (e.g. Qdrant unreachable, file already missing)
    blocks the deletion -- the DB row, which is the source of truth, is
    still removed either way. `FieldMetadata` rows cascade automatically.

    Args:
        report_id: Primary key of the report to delete.
        db: Injected DB session.

    Raises:
        HTTPException: 404 if no report with that id exists.
    """
    report = await crud.get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    if report.vector_indexed:
        try:
            delete_report_vector(report_id)
        except Exception:  # noqa: BLE001 - cleanup is best-effort, never blocks deletion
            pass

    if report.source_file_path:
        try:
            Path(report.source_file_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    await crud.delete_report(db, report_id)
    await db.commit()


@router.post("/bulk-delete", response_model=BulkDeleteResult)
async def bulk_delete_reports(
    params: ReportIdsRequest, db: DbSessionDep
) -> BulkDeleteResult:
    """Deletes multiple reports at once (e.g. from a table selection).

    Each report is cleaned up the same way `delete_report_endpoint`
    does (Qdrant vector + source file, best-effort, then the DB row).
    Ids that don't exist are reported back rather than raising -- a
    bulk action over a selection shouldn't fail entirely because one
    row was already deleted by something else in the meantime.

    Args:
        params: The report ids to delete.
        db: Injected DB session.

    Returns:
        Which ids were actually deleted, and which didn't exist.
    """
    deleted: list[int] = []
    not_found: list[int] = []

    for report_id in params.report_ids:
        report = await crud.get_report_by_id(db, report_id)
        if report is None:
            not_found.append(report_id)
            continue

        if report.vector_indexed:
            try:
                delete_report_vector(report_id)
            except Exception:  # noqa: BLE001
                pass
        if report.source_file_path:
            try:
                Path(report.source_file_path).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

        await crud.delete_report(db, report_id)
        deleted.append(report_id)

    await db.commit()
    return BulkDeleteResult(deleted=deleted, not_found=not_found)


@router.post("/export")
async def export_reports_endpoint(
    params: ReportIdsRequest, db: DbSessionDep
) -> Response:
    """Exports a set of reports as a JSONL file, for backup or reimport.

    Each line is `{"format_version": 1, "extracted_data": <the report's
    raw MaritimeIncident-shaped payload>, "full_text": <parsed source
    text, or null>}` -- the same shape `POST /uploads/jsonl` accepts, so
    exporting some reports, deleting them, and reimporting the exact
    same file round-trips cleanly. Reimported reports get new ids
    (nothing here tries to preserve or rebind the old ones), and their
    embeddings are recomputed at import time rather than carried in the
    file -- see `app.ingestion.jsonl_loader._embed_new_reports`.

    Args:
        params: The report ids to export. Ids that don't exist are
            silently skipped (the export just contains fewer records),
            since a stale selection shouldn't turn a partial export into
            a hard failure.
        db: Injected DB session.

    Returns:
        A `.jsonl` file download (`Content-Disposition: attachment`).
    """
    reports = await crud.get_reports_by_ids(db, params.report_ids)

    lines = [
        json.dumps(
            {
                "format_version": 1,
                "extracted_data": report.raw_payload,
                "full_text": report.full_text,
            }
        )
        for report in reports
    ]
    body = "\n".join(lines) + ("\n" if lines else "")

    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="reports_export.jsonl"'},
    )
