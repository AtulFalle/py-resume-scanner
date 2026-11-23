# Resume Screener

An AI-assisted resume screening app. Upload PDF resumes, let background workers extract structured candidate profiles and build vector embeddings, then search the pool with a job description. Search returns a ranked shortlist where each candidate gets a 0–100 match score, a skill-by-skill assessment, strengths, gaps and supporting evidence.

Everything runs locally. The LLM and embedding model are served by your own OpenAI-compatible inference server (for example `llama.cpp`'s `llama-server`), so no resume data leaves your machine.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Processing pipeline](#processing-pipeline)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Running with Docker Compose](#running-with-docker-compose)
- [Local development (without Docker for the app)](#local-development-without-docker-for-the-app)
- [Setting up the model servers](#setting-up-the-model-servers)
- [API reference](#api-reference)
- [Development commands](#development-commands)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

---

## Features

- **PDF resume ingestion**: upload one or many PDFs (up to 10 MB each) from the UI or the API.
- **Structured extraction**: an LLM turns raw resume text into a typed profile: contact details, work history, education, skills with evidence (and where each skill was demonstrated), seniority, domains and one of 24 role categories.
- **Precise search**: a query like "Angular developer, 5+ years" is parsed into required skills, minimum years and role categories. Resumes that don't have every required skill (any common spelling) or enough experience are filtered out in Postgres before vector search runs, so unrelated professions never show up.
- **Semantic search + LLM evaluation**: the remaining resumes are ranked by vector similarity, and the top N are scored 0–100 by the LLM. Anything below the minimum score (default 60) is hidden.
- **Structured candidate profiles**: name, role, category, seniority, total years of experience (taken from the resume or calculated from job dates) and profile links, all filterable.
- **Public profile research**: links in the resume (including clickable PDF links) are checked automatically. GitHub uses the official API. Personal websites are fetched politely (robots.txt, private network addresses blocked). LinkedIn is never scraped; recruiters can paste profile text instead.
- **Duplicate detection** and one-click reprocessing of failed resumes.
- **Asynchronous, fault-tolerant processing**: RabbitMQ queues with dead-lettering, idempotent job claiming and per-resume status tracking.
- **Streamlit UI**: pages for ingestion, the resume library and candidate search.

---

## Architecture

```
                ┌──────────────┐
                │ Streamlit UI │  :8501
                └──────┬───────┘
                       │ HTTP
                ┌──────▼───────┐        ┌────────────┐
                │ FastAPI API  │───────▶│  RustFS    │  S3-compatible object storage (PDFs)
                │   :8000      │        │ :9000/9001 │
                └──┬───┬────┬──┘        └────────────┘
                   │   │    │
         metadata  │   │    │ publish job
         ┌─────────▼┐  │  ┌─▼──────────┐
         │ Postgres │  │  │  RabbitMQ  │ :5672 / :15672
         │  :5432   │  │  └─┬────────┬─┘
         └──────────┘  │    │        │
                       │  resume.  resume.
                       │  processing embedding
                       │    │        │
                       │ ┌──▼─────┐ ┌▼──────────┐      ┌────────┐
                       │ │Extractor│ │ Embedding │─────▶│ Qdrant │ :6333
                       │ │ worker  │ │  worker   │      └────────┘
                       │ └──┬──────┘ └─────┬─────┘
                       │    │              │
                ┌──────▼────▼──┐    ┌──────▼─────────┐
                │ LLM server   │    │ Embedding server│   (run on the host,
                │ :8080 /v1    │    │ :8081 /v1       │    OpenAI-compatible)
                └──────────────┘    └─────────────────┘
```

| Service | Purpose | Port(s) |
|---|---|---|
| `api` | FastAPI backend: upload, search, health | 8000 |
| `ui` | Streamlit frontend | 8501 |
| `extractor` | Worker: PDF → text → structured profile | none |
| `embedding` | Worker: text → chunks → vectors in Qdrant | none |
| `research` | Worker: checks GitHub / personal websites linked from resumes | none |
| `postgres` | Resume metadata, extracted text and profiles | 5432 |
| `rabbitmq` | Job queues (management UI on 15672) | 5672, 15672 |
| `rustfs` | S3-compatible storage for the original PDFs (console on 9001) | 9000, 9001 |
| `qdrant` | Vector database for resume chunks | 6333, 6334 |

The LLM and embedding servers are **not** part of `docker-compose.yaml`. You run them on the host, and the containers reach them through `host.docker.internal`.

---

## Processing pipeline

### Ingestion

1. `POST /resumes/upload` validates the file (PDF only, non-empty, ≤ 10 MB), stores it in RustFS as `<uuid7>.pdf` and inserts a `resumes` row.
2. The API publishes `{resume_id, object_name}` to the `resume.processing` queue.
3. The **extractor worker** claims the job (`queued → extracting`), downloads the PDF, extracts the text and clickable link targets with `pypdf`, and calls the LLM with a JSON schema to produce a `ResumeExtraction`. It then builds the searchable `candidate_profiles` row in code (years of experience, normalized skills, links), saves everything, publishes to `resume.embedding`, and schedules a profile research run on `resume.research`.
4. The **embedding worker** claims the job (`embedding_queued → embedding`), splits the text into ~2,500-character chunks with 250 characters of overlap, embeds them and upserts them into the Qdrant `resumes` collection. Any old chunks for that resume are replaced first.

Jobs are claimed with a conditional `UPDATE … WHERE status = …`, so a duplicate message cannot process the same resume twice. Failed messages are rejected into the `resume.dlq` dead-letter queue.

### Resume status lifecycle

```
uploaded ──▶ queued ──▶ extracting ──▶ embedding_queued ──▶ embedding ──▶ embedded ✅
   │                        │                                   │
   ▼                        ▼                                   ▼
queue_failed            failed                          embedding_failed
```

`error_message` on the row holds the failure reason (truncated to 1,000 characters).

### Search

1. **Parse the query** (one small LLM call, cached in memory) into role, categories, required skills, preferred skills, min/max years, location and a short text for semantic search. Explicit filters from the UI replace the parsed values. A regex fallback catches "5+ years" if the model misses it.
2. **Hard filters in Postgres** (no LLM):
   - every required skill must appear in the resume text or the extracted skills, matched as a whole word with common aliases (`Angular` matches "AngularJS" and "Angular 8", not "rectangular");
   - total experience ≥ minimum years (with a 0.5-year tolerance). Resumes with unknown experience are kept by default;
   - role category, but only when no required skills were given, or when the recruiter picked categories explicitly.
3. **Vector search** in Qdrant, restricted to the resumes that passed. Chunks are grouped per candidate.
4. **LLM evaluation** of the top N (default 10). The prompt first decides whether the candidate is in the same profession, assesses each required skill, and only then gives a score. The same caps are enforced in code: wrong profession → at most 15; a required skill missing → at most 45; experience not stated when a minimum was asked → at most 75. Results are cached per query and candidate in `candidate_evaluations`, so repeating a search is instant.
5. **Threshold**: candidates below `min_score` (default `SEARCH_MIN_MATCH_SCORE=60`) are hidden, and the response says how many were hidden.

> Evaluations run one at a time by default (`SEARCH_EVALUATION_CONCURRENCY=1`) because the reference `llama-server` runs with `--parallel 1`. Raise it if your server handles parallel requests.

---

## Tech stack

- **Python 3.15** managed with **[uv](https://docs.astral.sh/uv/)**
- **FastAPI** + **Uvicorn**, **Pydantic v2** / `pydantic-settings`
- **SQLAlchemy 2 (async)** + **asyncpg** on **PostgreSQL 17**
- **aio-pika** on **RabbitMQ 4**
- **Qdrant** (`qdrant-client`) for vectors
- **RustFS** through the `minio` S3 client
- **pypdf** for text extraction
- **Streamlit** for the UI
- **httpx** for calling the OpenAI-compatible model servers
- **ruff**, **mypy** and **pytest** for development

---

## Project structure

```
.
├── docker-compose.yaml        # Full stack: infra + api + ui + workers
├── Dockerfile                 # Single image used by api, ui and both workers
├── Makefile                   # Dev shortcuts (install, dev, lint, test…)
├── pyproject.toml / uv.lock
└── src/
    ├── resume_ai/             # Backend package
    │   ├── main.py            # FastAPI app + startup (bucket, tables, MQ, LLM client)
    │   ├── core/              # Settings (env vars) and DB engine/session
    │   ├── api/routes/        # health, resume upload, search, ai (direct extraction)
    │   ├── services/          # Upload, semantic search, re-ranking
    │   ├── repository/        # DB queries
    │   ├── models/            # SQLAlchemy `Resume` model
    │   ├── schemas/           # Pydantic schemas (extraction, evaluation, search)
    │   ├── ai/
    │   │   ├── runtime.py     # httpx client for /chat/completions and /embeddings
    │   │   ├── registry.py    # Which model each task uses
    │   │   ├── chunking.py    # Text chunker
    │   │   ├── retrival.py    # Qdrant chunk retrieval
    │   │   ├── aggregate.py   # Chunk → candidate aggregation
    │   │   └── tasks/         # Extraction, embedding, query embedding, re-ranking prompts
    │   ├── message_queue/     # RabbitMQ publisher / consumer (with DLQ)
    │   ├── storage/           # S3 (RustFS) and Qdrant wrappers
    │   └── workers/           # extractor.py, embedding.py
    └── ui/                    # Streamlit app
        ├── app.py             # Entry point / dashboard
        ├── pages/             # resume_upload, resume_list, candidate_search
        ├── component/         # Candidate card
        ├── services/          # API client
        └── styles/
```

---

## Prerequisites

- **Docker** with Docker Compose v2
- **uv**, for local development: `pip install uv` or see the [install docs](https://docs.astral.sh/uv/getting-started/installation/)
- **Python 3.15** (uv can install it with `uv python install 3.15`)
- An **OpenAI-compatible LLM server** that supports `response_format: {"type": "json_schema"}`
- An **OpenAI-compatible embedding server** returning **768-dimensional** vectors (or change `AI_EMBEDDING_DIMENSIONS`)

---

## Configuration

Settings are loaded from environment variables and a `.env` file in the project root (see `src/resume_ai/core/config.py`). Variable names are case-insensitive.

Copy the example and edit it:

```bash
cp .env.example .env
```

### Application variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | none | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@localhost:5432/resume_ai` |
| `RABBITMQ_URL` | ✅ | none | AMQP URL, e.g. `amqp://user:pass@localhost:5672/` |
| `AI_EMBEDDING_BASE_URL` | ✅ | none | Embedding server base URL, e.g. `http://localhost:8081/v1` |
| `AI_EMBEDDING_MODEL` | ✅ | none | Model name sent to the embedding server |
| `AI_EMBEDDING_DIMENSIONS` | | `768` | Vector size. Must match the model and the Qdrant collection |
| `AI_LLM_BASE_URL` | | `http://localhost:8080/v1` | LLM server base URL |
| `AI_RESUME_EXTRACTION_MODEL` | | `resume-extractor` | Model name for resume extraction (and the default for the two below) |
| `AI_QUERY_PARSING_MODEL` | | same as extraction | Optional smaller model for parsing search queries |
| `AI_CANDIDATE_EVALUATION_MODEL` | | same as extraction | Optional smaller model for scoring candidates |
| `SEARCH_MIN_MATCH_SCORE` | | `60` | Candidates below this score are hidden |
| `SEARCH_SHORTLIST_SIZE` | | `10` | Default number of candidates evaluated per search |
| `SEARCH_RETRIEVAL_LIMIT` | | `200` | Resume chunks pulled from Qdrant before grouping |
| `SEARCH_EVALUATION_CONCURRENCY` | | `1` | Parallel LLM evaluations |
| `GITHUB_TOKEN` | | empty | Optional token; raises the GitHub API limit from 60 to 5,000 requests/hour |
| `RESEARCH_HTTP_TIMEOUT` | | `15` | Timeout (s) for GitHub and website requests |
| `AI_LLM_TIMEOUT` | | `1200` | LLM request timeout (seconds) |
| `AI_EMBEDDING_TIMEOUT` | | `1200` | Embedding request timeout (seconds) |
| `S3_ENDPOINT_URL` | | `localhost:9000` | **Must be `host:port` with no scheme** (MinIO client requirement) |
| `S3_SECURE` | | `false` | Use HTTPS for object storage |
| `S3_ACCESS_KEY` | | `resume_ai` | Also used as the RustFS access key in Compose |
| `S3_SECRET_KEY` | | `change-this-secret` | Also used as the RustFS secret key in Compose |
| `S3_BUCKET` | | `resumes` | Created automatically on API startup |
| `QDRANT_URL` | | `http://localhost:6333` | Qdrant URL |
| `DEBUG` | | `true` | FastAPI debug mode |
| `API_BASE_URL` | | `http://localhost:8000` | Used by the **UI** to reach the API |

### Infrastructure variables (used by `docker-compose.yaml`)

| Variable | Used by |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `postgres` container |
| `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | `rabbitmq` container |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `rustfs` container |

### Example `.env` (local development)

```dotenv
# --- Infra credentials (docker-compose) ---
POSTGRES_DB=resume_ai
POSTGRES_USER=resume_ai
POSTGRES_PASSWORD=change-me
RABBITMQ_USER=resume_ai
RABBITMQ_PASSWORD=change-me
S3_ACCESS_KEY=resume_ai
S3_SECRET_KEY=change-this-secret

# --- App connections (host-side; see note for full Docker) ---
DATABASE_URL=postgresql+asyncpg://resume_ai:change-me@localhost:5432/resume_ai
RABBITMQ_URL=amqp://resume_ai:change-me@localhost:5672/
S3_ENDPOINT_URL=localhost:9000
S3_BUCKET=resumes
QDRANT_URL=http://localhost:6333

# --- Model servers ---
AI_LLM_BASE_URL=http://localhost:8080/v1
AI_RESUME_EXTRACTION_MODEL=resume-extractor
AI_EMBEDDING_BASE_URL=http://localhost:8081/v1
AI_EMBEDDING_MODEL=nomic-embed-text
AI_EMBEDDING_DIMENSIONS=768
```

> The same `.env` works for both local development and the full Docker stack: Compose builds the container connection URLs (`postgres`, `rabbitmq`, `qdrant`, `rustfs`, model servers) from the same credentials.

---

## Running with Docker Compose

This runs everything except the model servers.

1. Start the LLM and embedding servers on the host ([see below](#setting-up-the-model-servers)) on ports **8080** and **8081**.
2. Create `.env` from `.env.example`. Compose rewrites the hostnames for the containers.
3. Build and start:

   ```bash
   docker compose up -d --build
   docker compose logs -f api extractor embedding research
   ```
4. **Upgrading from an earlier version?** New tables are created on API startup. Then build profiles for resumes that were already processed (no LLM calls):

   ```bash
   docker compose exec api uv run --no-sync python -m resume_ai.scripts.backfill_profiles
   ```

   To also pick up the improved extraction prompt, use **Retry** or `POST /resumes/{id}/reprocess` on individual resumes.
5. Open:
   - UI: http://localhost:8501
   - API docs (Swagger): http://localhost:8000/docs
   - RabbitMQ management: http://localhost:15672
   - RustFS console: http://localhost:9001
   - Qdrant dashboard: http://localhost:6333/dashboard

Stop the stack with `docker compose down`. Add `-v` to also delete the Postgres, Qdrant and RustFS volumes.

---

## Local development (without Docker for the app)

The recommended dev loop: run only the **infrastructure** in Docker, and run the API, workers and UI on the host with hot reload.

### 1. Install dependencies

```bash
uv python install 3.15   # if needed
make install             # = uv sync (includes dev tools)
```

### 2. Start infrastructure

```bash
docker compose up -d postgres rabbitmq rustfs qdrant
```

### 3. Configure `.env`

Use the [local development example](#example-env-local-development) with `localhost` hostnames and `S3_ENDPOINT_URL=localhost:9000`.

### 4. Start the model servers

See [Setting up the model servers](#setting-up-the-model-servers).

### 5. Run the app (one terminal each)

```bash
# API with auto-reload on :8000
make dev

# Extraction worker
uv run python -m resume_ai.workers.extractor

# Embedding worker
uv run python -m resume_ai.workers.embedding

# Profile research worker (GitHub / websites)
uv run python -m resume_ai.workers.research

# Streamlit UI on :8501
uv run streamlit run src/ui/app.py
```

On startup the API creates the S3 bucket, the database tables, the Qdrant collection and the RabbitMQ queues. New columns on existing tables are added by small idempotent `ALTER TABLE … IF NOT EXISTS` statements in `core/database.py`. There are no migrations yet.

If you already had processed resumes, run `uv run python -m resume_ai.scripts.backfill_profiles` once (add `--all` to rebuild every profile).

### 6. Try it

```bash
# Upload a resume
curl -F "file=@/path/to/resume.pdf" http://localhost:8000/resumes/upload

# Check processing status
curl "http://localhost:8000/resumes?limit=20"

# Search once a resume reaches status "embedded"
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Angular developer with 5+ years of experience"}'
```

---

## Setting up the model servers

The app talks to two OpenAI-compatible endpoints:

| Role | Endpoint used | Default URL | Requirements |
|---|---|---|---|
| Generation (extraction + re-ranking) | `POST /chat/completions` | `http://localhost:8080/v1` | JSON-schema structured output; served under the name in `AI_RESUME_EXTRACTION_MODEL` |
| Embeddings | `POST /embeddings` | `http://localhost:8081/v1` | Returns `AI_EMBEDDING_DIMENSIONS`-sized vectors |

Example with `llama.cpp` (adjust model files and context size to your hardware):

```bash
# Chat / extraction model, exposed as "resume-extractor"
llama-server -m ./models/<instruct-model>.gguf \
  --alias resume-extractor --port 8080 --host 0.0.0.0 \
  --jinja -c 16384 --parallel 1

# Embedding model (768-dim, e.g. nomic-embed-text v1.5)
llama-server -m ./models/nomic-embed-text-v1.5.Q8_0.gguf \
  --alias nomic-embed-text --port 8081 --host 0.0.0.0 \
  --embeddings
```

Notes:

- Bind to `0.0.0.0` (not just `127.0.0.1`) if the Docker containers need to reach the servers through `host.docker.internal`.
- Requests send `chat_template_kwargs: {"enable_thinking": false}` to turn off "thinking" output on models that support it. Servers that don't support it ignore the field.
- The `search_query:` / `search_document:` prefixes are the task prefixes nomic-embed-text expects. If you switch embedding models, check what prefixes the new model wants and update `AI_EMBEDDING_DIMENSIONS`. Then reset the Qdrant `resumes` collection and re-embed, because existing vectors won't be compatible.
- Extraction outputs can be long (`max_tokens` is 8192), so give the LLM enough context for prompt + resume + output.

---

## API reference

Interactive docs: **http://localhost:8000/docs**

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Hello / liveness |
| `GET` | `/health` | Service health (`{"status": "ok"}`) |
| `GET` | `/ai/health` | AI router health |
| `POST` | `/ai/resumes/extract` | Run structured extraction directly on raw text: `{"document_text": "..."}` → `ResumeExtraction` |
| `POST` | `/resumes/upload` | Multipart upload (`file`). Returns `{id, name, url, status}`. `400` validation error, `409` duplicate file, `503` couldn't be queued |
| `GET` | `/resumes` | Paginated list: `offset`, `limit`, `status`, `category`, `q` (name/filename/role) |
| `GET` | `/resumes/stats` | Counts by status and category |
| `GET` | `/resumes/{id}` | Resume, extracted profile and latest research report |
| `GET` | `/resumes/{id}/file` | Original PDF |
| `POST` | `/resumes/{id}/reprocess` | Run extraction + embedding again |
| `POST` | `/resumes/reprocess-failed` | Requeue every failed resume |
| `POST` | `/resumes/{id}/research` | Re-run public profile research |
| `POST` | `/resumes/{id}/research/manual` | Attach recruiter-provided profile text: `{"source_type": "linkedin", "url": str?, "text": str}` |
| `GET` | `/search/categories` | Role categories |
| `POST` | `/search` | Candidate search (below) |

### `POST /search` request

```json
{
  "query": "Angular developer with 5+ years of experience",
  "limit": 10,
  "min_score": 60,
  "required_skills": null,
  "categories": null,
  "min_years": null,
  "include_unknown_experience": true
}
```

Only `query` is required. `limit` is the number of candidates the LLM evaluates (1–25). `required_skills`, `categories` and `min_years` replace what was parsed from the query when set.

### `POST /search` response (abridged)

```json
{
  "total": 1,
  "requirements": {"role": "Angular Developer", "required_skills": ["Angular"], "min_years": 5, "…": "…"},
  "stats": {"passed_filters": 37, "retrieved": 37, "evaluated": 10, "below_threshold": 6, "min_score": 60},
  "message": "6 weaker candidate(s) scoring below 60 were hidden.",
  "candidates": [
    {
      "resume_id": "0199…",
      "filename": "jane_doe.pdf",
      "full_name": "Jane Doe",
      "primary_role": "Frontend Developer",
      "total_experience_years": 6.5,
      "links": [{"url": "https://github.com/janedoe", "source_type": "github"}],
      "semantic_score": 0.71,
      "match_score": 84,
      "profession_match": true,
      "summary": "…",
      "skills": [
        {"requirement": "FastAPI", "status": "…", "candidate_evidence": "…"}
      ],
      "relevant_experience": "…",
      "strengths": ["…"],
      "gaps": ["…"],
      "evidence": ["…"],
      "matched_chunks": [{"chunk_index": 0, "text": "…", "score": 0.71}]
    }
  ]
}
```

---

## Development commands

| Command | What it does |
|---|---|
| `make install` | `uv sync` (app + dev dependencies) |
| `make dev` | Run the API with `--reload` |
| `make lint` | `ruff check .` |
| `make format` | Auto-fix lint issues and format with ruff |
| `make format-check` | Check formatting only |
| `make typecheck` | `mypy src` |
| `make test` | `pytest` (expects a `tests/` directory) |
| `make check` | lint + format-check + typecheck + test |

Code style: ruff, line length 100, double quotes, rules `E, F, I, UP, B, SIM`. mypy runs with `disallow_untyped_defs`.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ValueError: path in endpoint is not allowed` or similar on startup | `S3_ENDPOINT_URL` includes `http://`. Use `localhost:9000` |
| `Field required: database_url` (or `rabbitmq_url`, `ai_embedding_*`) | Missing required variables in `.env` |
| Containers can't reach Postgres/RabbitMQ at `localhost` | Inside Docker, use the service names `postgres` / `rabbitmq` in `.env` |
| Search returns nothing for a skill you know exists | The skill may be spelled differently in resumes. Add the spelling to `ALIAS_GROUPS` in `ai/skills.py`, or clear the required-skills filter |
| Older resumes never appear in filtered searches | Run the `backfill_profiles` script so they get a profile (years, category) |
| GitHub research shows "rate limit" | Set `GITHUB_TOKEN` |
| Resume stuck at `queued` | The extractor worker isn't running or can't reach RabbitMQ. Check its logs |
| Status `failed` with "No extractable text found in PDF" | Scanned/image PDF. OCR isn't supported yet |
| `Expected 768 dimensions, received N` | Embedding model doesn't match `AI_EMBEDDING_DIMENSIONS` |
| `LLM returned empty content` / timeouts | Model server overloaded or context too small. Raise `-c`, check `AI_LLM_TIMEOUT` |
| Messages piling up in `resume.dlq` | Processing errors. Check the worker logs and the row's `error_message` |

---

## Known limitations

- PDF only, text-based (no OCR for scanned resumes).
- No authentication on the API or UI. Don't expose either to a network you don't trust.
- No Alembic migrations yet; new columns are added with idempotent `ALTER TABLE` statements on startup.
- LLM evaluation is capped at 25 candidates per search; experience filtering uses total years, not years in the specific skill.
- LinkedIn is not fetched automatically (its terms prohibit scraping). Paste profile text on the candidate page.
- The Kaggle resume dataset is largely anonymized, so it has few links. Use your own resumes to test profile research.
- Failed resumes are not retried automatically; use Retry in the UI or `POST /resumes/reprocess-failed`.
