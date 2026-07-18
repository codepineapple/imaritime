# iMaritime API

A FastAPI backend for the iMaritime incident-report platform: ingests
maritime safety-flash / incident reports (PDF, TXT, Markdown, or
pre-extracted JSON/JSONL), runs them through an integrated DSPy
extraction pipeline, stores the structured result in PostgreSQL, and
exposes it over a REST API for a React frontend -- including keyword +
semantic hybrid search, causal-pattern grouping, async intelligence
brief generation, and JSONL export/reimport.

## 1. Architecture at a glance

```
imaritime_backend/
├── init.py                     # dev bootstrap: docker compose + migrations + celery + api
├── compose.yaml                 # Redis + Qdrant + PostgreSQL, persistent volumes
├── pyproject.toml               # dependencies, managed with uv
├── alembic.ini, migrations/     # schema migrations (Alembic, async-aware)
├── .env.example
│
└── app/
    ├── main.py                    # FastAPI app factory (routers, CORS, embedding warm-up)
    ├── core/
    │   └── config.py                # Settings: every env var, in one place
    ├── db/
    │   ├── base.py                    # async engine/session (no create_all -- Alembic only)
    │   ├── models/                     # one ORM class per file (JSONB columns)
    │   │   ├── report.py, field_metadata.py, vocabulary_term.py, ingestion_job.py, brief_job.py
    │   │   └── __init__.py               # re-exports all five
    │   ├── crud.py                      # filtering/query logic (PostgreSQL JSONB queries)
    │   ├── search.py                     # attribute-tagged search suggestions
    │   ├── grouping.py                    # causal/operation/vessel grouping + recurrence
    │   └── job_reconciliation.py           # auto-fails jobs a crashed/lost worker abandoned
    ├── schemas/                     # API request/response DTOs
    ├── extraction/                  # the DSPy pipeline, integrated
    │   ├── signature.py                # ExtractMaritimeReport -- verbatim (this is the prompt)
    │   ├── incident.py                   # MaritimeIncident (the canonical extraction schema)
    │   ├── metadata.py                    # Attribute[T]/Metadata traceability wrappers
    │   ├── utils.py                        # coerce_string_to_list
    │   ├── dspy_runtime.py                  # shared DSPy/MLflow global config
    │   ├── service.py                        # ExtractionService: Settings-driven, testable
    │   ├── brief.py, brief_signature.py       # intelligence-brief output schema + signature
    │   └── brief_service.py                    # BriefGenerationService
    ├── briefs/
    │   ├── context_builder.py           # builds LLM context + recurrence stats
    │   └── generator.py                  # orchestrates brief generation from selected reports
    ├── ingestion/
    │   ├── file_validation.py          # magic-byte content validation, not just extension
    │   ├── parsing.py                    # Docling: PDF/DOCX -> page-marked text
    │   ├── loader.py                      # MaritimeIncident -> ORM objects
    │   └── jsonl_loader.py                 # bulk import: pre-extracted JSON/JSONL, reimport, embeds
    ├── vectorstore/
    │   ├── embeddings.py                # pluggable: fastembed (default) / OpenAI
    │   └── qdrant_store.py               # collection mgmt, upsert, search, similarity threshold
    ├── tasks/
    │   ├── celery_app.py                 # Celery app (Redis broker/backend, tightened visibility_timeout)
    │   ├── ingestion_tasks.py              # document ingestion pipeline, with retries
    │   └── brief_tasks.py                   # async brief generation, with retries
    └── api/
        ├── deps.py                     # DI: DB session, settings, Qdrant client
        └── routers/                     # reports, groups, briefs, search, uploads, jobs, vocab, config, health
```

Every module uses **absolute imports**. Every router depends on
`app/api/deps.py` providers rather than constructing sessions/clients
itself. Every function in the codebase has a Google-style docstring.

## 2. The DSPy extraction pipeline (`app/extraction/`)

- **`signature.py`** (`ExtractMaritimeReport`) is preserved **verbatim**
  -- its docstring is the actual LLM prompt.
- **`incident.py`** (`MaritimeIncident`) and **`metadata.py`**
  (`Attribute[T]`/`Metadata`) are integrated into the app (absolute
  imports, docstrings) with field descriptions preserved exactly, since
  DSPy includes them in the JSON schema shown to the model. List-typed
  evidence fields (`supporting_quotes`, `source_page_numbers`) tolerate
  an explicit `None` (coerced to `[]`) as well as a bare string instead
  of a list, since real-world extractions and hand-authored/legacy
  JSONL data don't always match the schema's nominal strictness.
- **`service.py`**/**`brief_service.py`** configure the DSPy LM,
  `JSONAdapter`, and MLflow autologging from `Settings` via a shared
  runtime module (`dspy_runtime.py`), lazily, on first use.

## 3. The open-vocabulary feedback loop

Three fields -- `operation_type`, `vessel_type`, `casual_signature` --
are open-vocabulary: the LLM is shown the current known set of values
for each and either picks one or invents a new, general label, which
gets folded back in after persisting (`app/db/vocab_crud.py`).
`Settings.OPEN_VOCAB_FIELD_MAP` is the single place mapping DB column
name to signature input field name.

## 4. Ingestion: three paths

**Raw documents** (`POST /api/v1/uploads/documents`, PDF/TXT/MD) go
through the full async Celery pipeline: parse (Docling/plain read) ->
extract (DSPy) -> persist -> embed. Progress (`pending -> parsing ->
extracting -> persisting -> embedding -> completed/failed`) is polled
via `GET /api/v1/jobs`.

**Pre-extracted JSON/JSONL** (`POST /api/v1/uploads/jsonl`) skips
parsing and extraction, running synchronously since there's no LLM
call. Each record's `extracted_data` validates directly against
`MaritimeIncident`. The embedding step still runs here (batched via
`embed_batch`, bounded by `Settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS`,
best-effort) so bulk-imported reports are just as searchable as ones
that went through live extraction.

**Reimporting a previous export** (see section 8) uses this same
endpoint -- an export file *is* a valid bulk-JSONL file.

### File type validation, retries, and ghost-job protection

- Every upload is validated by content (magic-byte sniffing via
  `python-magic`/`filetype`), not just filename extension.
- `TransientIngestionError`/`TransientBriefError` (LLM API errors,
  timeouts) retry with backoff; `PermanentIngestionError`/
  `PermanentBriefError` (bad input) fail immediately.
- **Ghost-job protection** (`app/db/job_reconciliation.py`): if a
  Celery worker crashes or a task hits its hard time limit, nothing
  would normally mark the job `failed` -- it'd just sit frozen forever.
  Any job untouched for `Settings.JOB_STALE_AFTER_SECONDS` (default 30
  min) while non-terminal gets flipped to `failed` with an explanatory
  message the next time the jobs list is polled. Separately, Redis's
  default `visibility_timeout` (an hour) is tightened to
  `CELERY_TASK_TIME_LIMIT + 120s` in `celery_app.py`, since a long
  default there is what lets a crashed task's message sit invisible to
  every other worker in the first place.

## 5. Causal grouping and recurrence counting

`POST /api/v1/groups` groups reports matching a set of filters by
`operation_type`, `vessel_type`, or `casual_signature`, ranked by
recurrence count -- count, summed injuries/fatalities, average
confidence, date range, and sample report ids (highest confidence
first). This is also the foundation the brief generator uses to find
"the pattern that kills."

## 6. Intelligence briefs

A user selects up to `Settings.MAX_REPORTS_PER_BRIEF` reports (any way
they like -- filtered, searched, whatever) and starts an async brief
generation job (`POST /api/v1/briefs`), mirroring `IngestionJob`'s
pending -> ... -> completed/failed lifecycle exactly, polled the same
way (`GET /api/v1/briefs`).

The brief has four sections -- a recurrence statement (numbers computed
deterministically and given to the model as fixed inputs, not
calculated by it), the pattern that kills (the most common
`casual_signature` among the selected reports, described using detail
from the highest-confidence report sharing it), a compliance-illusion
finding, and up to three action lines -- every section carrying
citations (report id + field + page numbers).

`Settings.MAX_REPORTS_PER_BRIEF` (default 5) is exposed to the frontend
via `GET /api/v1/config`, so the UI enforces the same limit the backend
does without duplicating the number in a frontend env var that could
drift out of sync.

## 7. Semantic search (hybrid, merged into `/reports/search`)

There's no standalone semantic-search endpoint -- when a free-text
("all fields") search token is present, `POST /api/v1/reports/search`
also embeds the query and searches Qdrant, unioning semantically
similar reports into the same result set as keyword matches. Each
result is labeled `match_type`: `"keyword"`, `"semantic"`, or `"both"`.

- Bounded by `Settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS` (default 3s)
  and never allowed to fail the request -- a slow/unreachable embedding
  provider degrades to keyword-only results.
- `Settings.SEMANTIC_SIMILARITY_THRESHOLD` (default 0.5) is a real
  correctness requirement, not a tuning nicety: Qdrant's raw
  nearest-neighbor search returns the top-N closest vectors
  *unconditionally*, regardless of how dissimilar they actually are --
  without a minimum score, a small collection means literally every
  report can qualify as a "semantic match" for any query, including
  nonsense ones.
- The embedding provider is warmed up **at server startup**
  (`app/main.py`'s lifespan, fire-and-forgotten so a slow/blocked model
  download never delays the server itself becoming available) rather
  than lazily on first request -- `GET /api/v1/health` reports
  `embedding_status`: `not_started` -> `initializing` ->
  `ready`/`unavailable`. A construction-in-progress guard means
  concurrent requests during that window fail fast instead of each
  spawning a redundant attempt.

## 8. Export, reimport, and deletion

`POST /api/v1/reports/export` (body: `{"report_ids": [...]}`) downloads
a `.jsonl` file, one line per report: `{"format_version": 1,
"extracted_data": <raw MaritimeIncident payload>, "full_text": <parsed
source text, or null>}`. This is deliberately the same shape
`POST /uploads/jsonl` already accepts, so **export -> delete ->
reimport round-trips cleanly** -- verified end-to-end. A few explicit
design choices behind that:

- **Embeddings are recomputed on reimport, not carried in the export
  file.** The vector is fully reproducible from the exported structured
  fields through the same deterministic embedding model, so there's no
  need to ship a float array around, and the format stays portable
  across environments/embedding models.
- **`full_text` is included** for fidelity (the reimported report keeps
  its original parsed source text, not just the extraction), but note
  it's only actually *used* for embedding in the rare case a report's
  structured extraction was nearly empty (see `build_embedding_text`).
- **Reimported reports get new ids.** Nothing tries to preserve or
  rebind the old ones -- if a brief was generated from reports that get
  deleted and reimported, that brief's citations will point at ids that
  no longer resolve, though the brief's own text stays intact as a
  historical record.

Deletion: `DELETE /api/v1/reports/{id}` (single) and
`POST /api/v1/reports/bulk-delete` (body: `{"report_ids": [...]}`) both
best-effort clean up the report's Qdrant vector and stored source file
before removing the DB row (neither failing blocks the deletion);
`FieldMetadata` cascades automatically. Bulk delete reports which ids
didn't exist rather than failing the whole batch.

## 9. Configuration

Every configurable value is a `Settings` field in `app/core/config.py`
(see `.env.example` for the full list) -- PostgreSQL connection,
upload storage dir + max size, Qdrant URL/threshold, embedding
provider + model, Redis/Celery URLs + task time limits, every DSPy/
MLflow tuning parameter, `MAX_REPORTS_PER_BRIEF`,
`JOB_STALE_AFTER_SECONDS`, and `MODEL`/`API_BASE`/`API_KEY`. Nothing is
hardcoded elsewhere; import `get_settings()` rather than reading
`os.environ` directly if you add new code.

## 10. Running it

Everything the backend depends on -- Redis, Qdrant, PostgreSQL -- runs
as Docker containers defined in `compose.yaml`, each with a persistent
named volume so `docker compose down` never loses data.

```bash
cd imaritime_backend
uv sync                 # creates .venv/ and installs everything from pyproject.toml
cp .env.example .env    # then fill in MODEL / API_BASE / API_KEY at least
```

**One-command dev bootstrap** (starts all three Docker services, waits
for each to be reachable, runs Alembic migrations, starts a Celery
worker, then the API in the foreground):

```bash
uv run python init.py
# --skip-docker to manage Redis/Qdrant/PostgreSQL yourself instead
# --skip-migrate / --skip-celery to skip those steps
# --reload for uvicorn autoreload, --port/--host to change the bind address
# --celery-pool solo --celery-concurrency N to control the worker
```

**Windows note:** Celery's default `prefork` pool is unreliable on
Windows, and `--concurrency` silently has no effect under it. `init.py`
detects Windows automatically and defaults to `--celery-pool solo`
instead (which doesn't take a concurrency value at all); override with
`--celery-pool` if you need something else.

Docker services are deliberately left running when `init.py` exits
(only the Celery worker and uvicorn, which it started itself, are
stopped) -- they're persistent infrastructure with persistent volumes,
so leaving them up just makes the next run instant. Run
`docker compose down` yourself to fully stop them.

Or run each piece yourself:

```bash
docker compose up -d
uv run alembic upgrade head
uv run celery -A app.tasks.celery_app worker --loglevel=info --pool=solo   # Windows
uv run celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2  # everywhere else
uv run uvicorn app.main:app --reload
```

API docs (Swagger UI): http://127.0.0.1:8000/docs

## 11. Database migrations (Alembic)

The schema lives entirely in `app/db/models/*.py` (PostgreSQL, JSONB
columns) -- there is **no** `create_all()`/`init_db()` anywhere in the
app; Alembic is the only way the schema gets created or changed.

```bash
uv run alembic revision --autogenerate -m "describe your change"
uv run alembic upgrade head
uv run alembic downgrade -1     # roll back one step
uv run alembic check            # verify no undetected model changes
```

A note for anyone who worked with an earlier SQLite-backed version of
this project: the migration history was reset when PostgreSQL replaced
SQLite (there's no meaningful in-place data migration between the two
engines for a project at this stage) -- there is a single fresh
"initial postgresql schema" migration rather than the old SQLite-era
sequence.

### A real gotcha this surfaced: JSON `null` vs. SQL `NULL`

Every nullable `JSONB` column is defined with `JSONB(none_as_null=True)`
(see the small per-model `_JSONB`/`JSONB` alias at the top of each
`app/db/models/*.py` file). Without this, SQLAlchemy's default behavior
binds a Python `None` as the **JSON `null` literal** stored *inside*
the column, not as a true SQL `NULL` -- and PostgreSQL's
`jsonb_array_elements_text()` (used for searching within list fields)
correctly rejects that with `"cannot extract elements from a scalar"`,
since JSON `null` is a scalar, not an array. SQLite's equivalent
(`json_each()`) was lenient enough to paper over exactly this
distinction, so it never surfaced there.

## 12. What's verified vs. what needs your environment

Verified end-to-end in this build, against a **real local PostgreSQL
instance** (not SQLite) since this environment has no Docker: `uv sync`
resolving the full dependency set, all DB models + a fresh migration
(confirmed real JSONB columns, zero drift), the PostgreSQL rewrite of
every SQLite-specific JSON query (`jsonb_array_elements_text`,
`jsonb_array_length`) including the `none_as_null` fix above, hybrid
keyword+semantic search and the similarity-threshold fix, the full
export -> bulk-delete -> reimport round-trip (new ids, embeddings
recomputed, `full_text` preserved), causal grouping, the async brief
pipeline (report-id selection, top-causal-group + most-representative-
report selection, caching-free regeneration), the ghost-job
reconciliation lifecycle (manually backdated a stuck job, confirmed it
auto-fails with a clear message, confirmed retry re-enqueues and
progresses with a real Celery worker), `init.py`'s full bootstrap
sequence via `--skip-docker` against locally-installed Postgres/Redis
standing in for the Docker services (migrations -> Celery with
`--pool=solo` -- confirmed `concurrency: 1 (solo)` in the worker
banner and a real `Connected to redis://.../celery@... ready.` -> API
serving requests), and the embedding-provider startup warm-up lifecycle
(`not_started` -> `initializing` -> terminal state).

Needs your environment to fully exercise: the actual `docker compose
up -d` orchestration in `init.py` (this sandbox has no Docker daemon,
so only `--skip-docker` was tested; the compose file and the
port-reachability wait loop are straightforward enough that this is
low-risk, but worth a real run), an actual DSPy extraction or
brief-generation call end-to-end (needs a real `MODEL`/`API_KEY`), and
Docling's PDF model download / fastembed's model download (both need
Hugging Face reachable -- this sandbox's network doesn't allow it;
switch to `EMBEDDING_PROVIDER=openai` to avoid the fastembed download
if needed).
