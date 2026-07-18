"""Bulk ingestion of pre-extracted JSON/JSON-Lines records.

For migrating historical data, loading a separate batch-extraction run's
output, or re-importing a previous export (see
`app.api.routers.reports.export_reports_endpoint`) -- e.g. after
exporting some reports, deleting them, and wanting them back. No LLM
call is involved here, so the extraction step is skipped entirely; the
embedding step still runs (batched, bounded, best-effort) since a
reimported report should be just as searchable as one that went through
live extraction. For raw source documents (PDF/TXT/MD) that still need
Docling + DSPy extraction, see `app.tasks.ingestion_tasks` instead.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.db import crud, vocab_crud
from app.extraction.incident import MaritimeIncident
from app.ingestion import loader
from app.vectorstore.embeddings import build_embedding_text, get_embedding_provider
from app.vectorstore.qdrant_store import upsert_report_vector

settings = get_settings()


@dataclass
class JsonlIngestResult:
    """Summary of a bulk JSON/JSONL ingestion run.

    Attributes:
        total_records: Total records found in the uploaded file.
        inserted: Records successfully persisted as new reports.
        duplicates: Records skipped because an identical report
            (by content hash) already exists.
        failed: Records that failed to parse or validate.
        errors: Human-readable error messages for failed records.
        embedded: How many of the inserted reports were successfully
            embedded/indexed for semantic search (best-effort -- see
            `_embed_new_reports`; a slow/unavailable embedding provider
            reduces this without failing the import).
    """

    total_records: int = 0
    inserted: int = 0
    duplicates: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    embedded: int = 0


def _iter_json_records(raw_bytes: bytes, filename: str) -> list[dict]:
    """Parses raw upload bytes into a list of record dicts.

    Accepts a single JSON object, a JSON array of objects, or true
    JSON-Lines (one object per line).

    Args:
        raw_bytes: The raw uploaded file content.
        filename: The uploaded filename (used to prefer `.jsonl` parsing
            when the extension says so).

    Returns:
        A list of parsed record dicts (each expected to have an
        `extracted_data` key).

    Raises:
        ValueError: If a `.jsonl` file contains an invalid line.
    """
    text = raw_bytes.decode("utf-8-sig").strip()
    if not text:
        return []

    if not filename.lower().endswith(".jsonl"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            pass  # fall through to line-delimited parsing

    records = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Line {line_no}: invalid JSON ({exc.msg})") from exc
    return records


async def ingest_jsonl(
    session: AsyncSession, raw_bytes: bytes, filename: str
) -> JsonlIngestResult:
    """Ingests a JSON/JSON-array/JSONL file of pre-extracted records.

    Each record must be shaped `{"extracted_data": {<MaritimeIncident
    fields>}, "full_text": "..." (optional)}` -- the same convention
    used by `export_reports_endpoint`'s output, and a superset of the
    older convention (bare `extracted_data`, no `full_text`) so existing
    export/backfill files still import unchanged.

    Args:
        session: Active async DB session (the caller commits).
        raw_bytes: The raw uploaded file content.
        filename: The uploaded filename.

    Returns:
        A summary of how many records were inserted/skipped/failed/embedded.
    """
    result = JsonlIngestResult()

    try:
        raw_records = _iter_json_records(raw_bytes, filename)
    except (ValueError, UnicodeDecodeError) as exc:
        result.total_records = 1
        result.failed = 1
        result.errors.append(str(exc))
        return result

    result.total_records = len(raw_records)
    candidates: list[loader.BuiltReport] = []
    seen_hashes: set[str] = set()

    for idx, raw in enumerate(raw_records, start=1):
        try:
            incident = _validate_record(raw)
            built = loader.build_report_from_incident(
                incident, source_filename=filename, full_text=raw.get("full_text")
            )
        except ValidationError as exc:
            result.failed += 1
            result.errors.append(
                f"Record {idx}: {exc.errors()[0].get('msg', str(exc))}"
            )
            continue
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            result.errors.append(f"Record {idx}: {exc}")
            continue

        if built.report.content_hash in seen_hashes:
            result.duplicates += 1
            continue
        seen_hashes.add(built.report.content_hash)
        candidates.append(built)

    existing = await crud.get_existing_hashes(
        session, [b.report.content_hash for b in candidates]
    )
    to_insert = [b for b in candidates if b.report.content_hash not in existing]
    result.duplicates += len(candidates) - len(to_insert)

    for built in to_insert:
        await crud.create_report(session, built.report)
        await vocab_crud.sync_vocab_from_report(session, built.report)
    result.inserted = len(to_insert)

    if to_insert:
        result.embedded = await _embed_new_reports([b.report for b in to_insert])

    return result


async def _embed_new_reports(reports: list[Any]) -> int:
    """Embeds and indexes a batch of newly-inserted reports, best-effort.

    Recomputing embeddings (rather than requiring them in the import
    file) keeps the import format simple and portable across embedding
    models -- see the export/reimport design discussion this
    implements. Bounded by `Settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS`
    and never allowed to fail the import: a slow/unavailable embedding
    provider just means these reports stay `vector_indexed=False` (same
    as any other report whose embedding step didn't succeed) rather
    than blocking or failing the whole bulk ingest.

    Args:
        reports: Freshly-inserted `Report` ORM instances (already
            flushed, so `.id` is populated).

    Returns:
        How many reports were successfully embedded and indexed.
    """
    try:
        provider = await run_in_threadpool(get_embedding_provider)
        texts = [
            build_embedding_text(
                {
                    "incident_title": r.incident_title,
                    "incident_type": r.incident_type,
                    "operation_type": r.operation_type,
                    "vessel_type": r.vessel_type,
                    "location": r.location,
                    "casual_signature": r.casual_signature,
                    "root_causes": r.root_causes,
                    "contributing_factors": r.contributing_factors,
                    "lessons_learned": r.lessons_learned,
                    "keywords": r.keywords,
                    "full_text": r.full_text,
                }
            )
            for r in reports
        ]
        vectors = await asyncio.wait_for(
            run_in_threadpool(provider.embed_batch, texts),
            timeout=settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS
            * 3,  # a batch, not a single query
        )
    except Exception:  # noqa: BLE001
        return 0

    embedded = 0
    for report, vector in zip(reports, vectors):
        try:
            await run_in_threadpool(
                upsert_report_vector,
                report.id,
                vector,
                {
                    "incident_type": report.incident_type,
                    "operation_type": report.operation_type,
                    "vessel_type": report.vessel_type,
                    "incident_title": report.incident_title,
                },
            )
            report.vector_indexed = True
            embedded += 1
        except Exception:  # noqa: BLE001
            continue  # this one report's index failed; the rest can still succeed

    return embedded


def _validate_record(raw: dict[str, Any]) -> MaritimeIncident:
    """Validates one raw record dict as a `MaritimeIncident`.

    Args:
        raw: A parsed JSON record, expected to have an `extracted_data` key.

    Returns:
        The validated `MaritimeIncident`.

    Raises:
        ValidationError: If `raw["extracted_data"]` doesn't match the
            `MaritimeIncident` schema.
        KeyError: If `raw` has no `extracted_data` key.
    """
    return MaritimeIncident.model_validate(raw["extracted_data"])
