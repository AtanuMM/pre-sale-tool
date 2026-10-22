# ScopeDesk (pre-sale-tool)

ScopeDesk is an internal **presales and delivery-scoping platform**. Teams capture a client request (email, RFQ, attachments), then walk a **gated, eight-step workflow** where each step produces a reviewable artifact. Earlier approved outputs become structured context for later steps. **Google Gemini** generates draft content from Pydantic-defined JSON schemas; **Python post-processing** assigns stable IDs, enforces business rules, builds traceability, and assembles exports. Humans **approve** each step before the next unlocks.

This repository is a **monorepo**:

| Path | Role |
|------|------|
| `backend/` | FastAPI API, SQLAlchemy models, Alembic migrations, LLM orchestration, document export (DOCX/XLSX/CSV), S3 integration |
| `frontend/` | React 19 + Vite SPA (ScopeDesk UI) |
| `e2e/` | Playwright end-to-end tests (optional CI/local) |
| `scripts/` | Test runners and E2E server helpers |
| `docker-compose.yml` | Local **MinIO** (S3-compatible) and optional **PostgreSQL 16** |

For backend-only commands and storage diagnostics, see also [`backend/README.md`](backend/README.md).

---

## Table of contents

1. [What the product does](#what-the-product-does)
2. [Architecture overview](#architecture-overview)
3. [Third-party services and libraries](#third-party-services-and-libraries)
4. [Prerequisites](#prerequisites)
5. [Full local setup (step by step)](#full-local-setup-step-by-step)
6. [Running the application](#running-the-application)
7. [Environment variables reference](#environment-variables-reference)
8. [The eight-step workflow](#the-eight-step-workflow)
9. [How generation works](#how-generation-works)
10. [Authentication, sessions, and RBAC](#authentication-sessions-and-rbac)
11. [Database and migrations](#database-and-migrations)
12. [Object storage (S3 / MinIO)](#object-storage-s3--minio)
13. [File intake and text extraction](#file-intake-and-text-extraction)
14. [Exports and project package](#exports-and-project-package)
15. [Testing](#testing)
16. [Playwright E2E](#playwright-e2e)
17. [Production and security notes](#production-and-security-notes)
18. [Troubleshooting](#troubleshooting)
19. [Repository conventions](#repository-conventions)

---

## What the product does

### Problem

Presales teams receive unstructured requests (forwards, RFQs, PDFs, spreadsheets). They must turn that into **consistent, traceable deliverables**: scope understanding, gaps, feature breakdown, estimates, commercial SOW, SRS, sprint plan, and functional specs—often under time pressure and with multiple reviewers.

### Solution

ScopeDesk provides:

- **Projects** with immutable-style **intake** (source message + attachments stored in object storage).
- A **linear workflow** of eight steps; each step has statuses such as locked, ready, generating, in review, approved, failed.
- **Versioned outputs** per step (generate → review → request changes → approve).
- **Role-based access control** (Admin, Lead, Analyst, Viewer) with fine-grained permissions.
- **Audit trail** for sensitive actions.
- **Document exports** (Word, Excel, CSV depending on step) and, after FRS approval, a **project package** download.
- **Admin** screens for users, roles, and global settings.

The UI product name is **ScopeDesk**. The git repository folder is often named `pre-sale-tool`.

---

## Architecture overview

```mermaid
flowchart TB
  subgraph client [Browser]
    UI[React SPA - Vite]
  end

  subgraph api [Backend - FastAPI]
    R[Routers: auth, projects, steps, users, roles, settings]
    G[Step generation worker pool]
    PP[Post-processors per step]
    DOC[Document renderers DOCX/XLSX/CSV]
    R --> G
    G --> PP
    PP --> DOC
  end

  subgraph data [Data stores]
    PG[(PostgreSQL)]
    S3[(S3-compatible storage)]
  end

  subgraph external [External]
    GEM[Google Gemini API]
  end

  UI -->|HTTPS JSON + cookies| R
  R --> PG
  R --> S3
  G --> GEM
  G --> PG
  DOC --> S3
```

**Request flow (simplified):**

1. User logs in → JWT access token (short-lived) + **HttpOnly refresh cookie**.
2. User creates a project → intake text/files persisted; files uploaded to S3; text extracted locally (no LLM).
3. User generates a step → API enqueues work, calls Gemini with a step-specific schema, validates JSON, runs post-process, stores `StepVersion.content` in Postgres.
4. User approves → step status updates; next step may become **ready**.
5. User downloads export → backend renders bytes from stored JSON (and may read diagram assets from S3).

On API startup (unless disabled), the process **checks Postgres and S3**, then runs **generation recovery** to fail stuck in-flight generations safely.

---

## Third-party services and libraries

### Required external services

| Service | Purpose in ScopeDesk | Local dev | Production notes |
|---------|----------------------|-----------|------------------|
| **PostgreSQL 16+** | All relational data: users, roles, projects, step versions, audit, settings | `docker compose --profile full-stack up -d postgres` **or** your own instance; default URL in `backend/.env.example` | Managed RDS/Cloud SQL/etc.; connection string in `DATABASE_URL` |
| **S3-compatible object storage** | Uploaded intake files, generated diagram assets, export-related blobs | **MinIO** via `docker compose up -d minio` on ports **9100** (API) and **9101** (console) | AWS S3, MinIO, or any S3 API; configure `S3_*` env vars |
| **Google Gemini** | Structured JSON generation for workflow steps | API key from [Google AI Studio](https://aistudio.google.com/) or GCP | Billing, quotas, model allowlists; set `GEMINI_API_KEY` and `GEMINI_MODEL` |

ScopeDesk does **not** require Redis, Elasticsearch, or a separate job queue service: generation uses an **in-process thread pool** in the API process (`MAX_CONCURRENT_GENERATIONS`).

### Backend Python stack (high level)

| Area | Packages |
|------|----------|
| API | FastAPI, Uvicorn, Starlette, python-multipart |
| Config | pydantic-settings, python-dotenv |
| Database | SQLAlchemy 2.x, psycopg 3, Alembic |
| Auth | PyJWT, argon2-cffi (password hashing) |
| LLM | google-genai |
| S3 | boto3 |
| Documents | python-docx, openpyxl, pypdf |
| Charts (sprint exports) | matplotlib |
| Tests / quality | pytest, ruff |

See [`backend/requirements.txt`](backend/requirements.txt) for pinned versions.

### Frontend stack

| Area | Packages |
|------|----------|
| UI | React 19, React Router 7 |
| Build | Vite 8, TypeScript 6 |
| Styling | Tailwind CSS 4, Radix UI primitives, next-themes (light/dark) |
| Data | TanStack React Query |
| Tests | Vitest, Testing Library |

---

## Prerequisites

Install on your machine:

| Tool | Version / notes |
|------|-----------------|
| **Git** | Any recent version |
| **Python** | **3.11+** (3.12 is used in many dev environments) |
| **Node.js** | **20+** recommended (for `frontend/` and `e2e/`) |
| **Docker + Docker Compose** | For MinIO; optional Postgres service in compose |
| **PostgreSQL client** (optional) | `psql` for debugging |

Accounts / credentials you must obtain:

- **Gemini API key** and a **model ID** your key can call (e.g. a Gemini 2.x flash/pro model—set exactly what works in your account).
- Strong secrets for **JWT** and **admin password** (see env section).

---

## Full local setup (step by step)

These steps assume you clone the repo and work from its root.

### 1. Clone and directory layout

```bash
git clone <your-remote-url> pre-sale-tool
cd pre-sale-tool
```

### 2. Root `.env` for Docker Compose (MinIO only)

Compose reads MinIO root credentials from the **repository root** `.env`:

```bash
cp .env.example .env
```

Edit `.env` and set:

- `MINIO_ROOT_USER` — long random username (not `minioadmin` in shared environments).
- `MINIO_ROOT_PASSWORD` — **at least 32 characters**.

These values are **only** for the MinIO container. The API uses separate `S3_ACCESS_KEY` / `S3_SECRET_KEY` in `backend/.env` (for local dev they are typically set to the same values as root user/password).

### 3. Start infrastructure

**MinIO (required for file uploads and readiness checks):**

```bash
docker compose up -d minio
```

Wait until healthy (`docker compose ps`). Then:

- S3 API: `http://localhost:9100`
- Web console: `http://localhost:9101` (login with root `.env` credentials)

**PostgreSQL (choose one):**

**Option A — Compose Postgres (profile `full-stack`):**

```bash
docker compose --profile full-stack up -d postgres
```

Default credentials match `backend/.env.example`: user/db/password `scopedesk`, port **5432**.

**Option B — Existing Postgres:** create a database and user, then set `DATABASE_URL` accordingly.

### 4. Backend virtualenv and dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` (minimum to run):

| Variable | What to set |
|----------|-------------|
| `DATABASE_URL` | Postgres DSN, e.g. `postgresql+psycopg://scopedesk:scopedesk@localhost:5432/scopedesk` |
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `GEMINI_MODEL` | Model string (must match a model your key can use) |
| `JWT_SECRET` | Long random string (**32+ chars** if `APP_ENV` is not `development`) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_FULL_NAME` | First admin user (seed) |
| `S3_ENDPOINT_URL` | `http://localhost:9100` for local MinIO |
| `S3_BUCKET` | `scopedesk` (or your bucket name) |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Match MinIO root user/password from repo root `.env` |
| `ALLOWED_ORIGINS` | Must include your Vite origin, e.g. `http://localhost:5173,http://127.0.0.1:5173` |

### 5. Create S3 buckets

From `backend/` with venv active:

```bash
python -m scripts.ensure_buckets
```

This creates `S3_BUCKET` and `S3_TEST_BUCKET` (default `scopedesk-test`) if missing.

### 6. Database migrations

Still in `backend/`:

```bash
alembic upgrade head
```

Verify:

```bash
alembic current
```

### 7. Seed RBAC and admin user

```bash
python -m app.seed
```

Idempotent: creates permissions, default roles (Admin, Lead, Analyst, Viewer), links permissions to roles, and creates the admin user from `ADMIN_*` env vars if missing. **Does not reset** an existing admin password.

### 8. Frontend dependencies and env

```bash
cd ../frontend
npm install
cp .env.example .env
```

Default `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

The API port must match where you run Uvicorn (see below).

### 9. Smoke check before UI

With backend running (next section):

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/ready
```

`health/ready` should report `"database": "ok"` and `"object_storage": "ok"`. If not, fix Postgres/MinIO/buckets before debugging the UI.

---

## Running the application

### Backend API (development)

From `backend/` with venv active:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

This matches `frontend/.env.example` (`VITE_API_BASE_URL=http://localhost:8000`).

Alternative port (documented in `backend/README.md`): `--port 8080` — then update `VITE_API_BASE_URL` to match.

Endpoints:

| URL | Meaning |
|-----|---------|
| `GET /health` | Liveness (process up) |
| `GET /health/ready` | Readiness (Postgres + S3); **503** if dependencies fail |
| OpenAPI | `GET /docs` (FastAPI Swagger UI) |

**Startup checks:** On boot, unless `SKIP_STARTUP_CHECKS=true`, the API **exits** if Postgres or S3 is unreachable. Tests set `SKIP_STARTUP_CHECKS=true` automatically.

### Frontend (development)

From `frontend/`:

```bash
npm run dev
```

Default Vite URL: **http://localhost:5173**

Log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env`.

### Typical daily workflow

1. Ensure MinIO (and Postgres) are running.
2. Start API (`uvicorn …`).
3. Start frontend (`npm run dev`).
4. Create a project → complete Step 1 → approve → continue down the chain.

---

## Environment variables reference

Configuration is loaded from `backend/.env` via Pydantic Settings ([`backend/app/config.py`](backend/app/config.py)). Only the most important groups are listed here; the file contains many tuning knobs for estimates, SOW caps, SRS/FRS batch sizes, timeouts, etc.

### Core application

| Variable | Default / example | Description |
|----------|-------------------|-------------|
| `APP_ENV` | `development` | Environment name; affects JWT secret length validation |
| `SKIP_STARTUP_CHECKS` | `false` | If `true`, skip Postgres/S3 checks on startup |
| `TRUST_X_FORWARDED_FOR` | `false` | Trust proxy headers for client IP (audit) |
| `ALLOWED_ORIGINS` | CSV or JSON list | CORS origins for browser; **must** include Vite URL |

### Database

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | SQLAlchemy URL with psycopg driver, e.g. `postgresql+psycopg://user:pass@host:5432/dbname` |

Tests may use `scopedesk_test` derived from this URL (see `backend/tests/db_utils.py`).

### Google Gemini

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | API key |
| `GEMINI_MODEL` | Model ID passed to `google-genai` |
| `MAX_PROMPT_CHARS` | Upper bound on assembled prompt size |
| `GENERATION_TIMEOUT_SECONDS` | Default generation deadline (some steps have longer overrides) |
| `MAX_CONCURRENT_GENERATIONS` | Per **process** concurrent LLM jobs (default 2) |

Step-specific timeouts and batch sizes include `ESTIMATE_*`, `SRS_*`, `SPRINT_PLAN_*`, `FRS_*` — see `config.py`.

### Object storage (S3 API)

| Variable | Description |
|----------|-------------|
| `S3_ENDPOINT_URL` | MinIO: `http://localhost:9100`; AWS: omit or use regional endpoint |
| `S3_BUCKET` | Primary bucket for project files |
| `S3_TEST_BUCKET` | Used by storage diagnostic scripts/tests |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Credentials |
| `S3_REGION` | Default `us-east-1` |
| `S3_PATH_STYLE` | `true` for MinIO path-style addressing |

### Auth

| Variable | Description |
|----------|-------------|
| `JWT_SECRET` | Signs access tokens |
| `ACCESS_TOKEN_MINUTES` | Access token TTL (default 15) |
| `REFRESH_TOKEN_DAYS` | Refresh token TTL (default 7) |
| `REFRESH_COOKIE_NAME` | HttpOnly cookie name (default `scopedesk_refresh`) |

### Admin seed

| Variable | Description |
|----------|-------------|
| `ADMIN_EMAIL` | Initial admin login |
| `ADMIN_PASSWORD` | Initial admin password |
| `ADMIN_FULL_NAME` | Display name |

### Upload / intake limits

Includes `MAX_UPLOAD_FILE_BYTES`, `MAX_FILES_PER_INPUT`, `MAX_EXTRACTED_TEXT_CHARS`, `MAX_INTAKE_REQUEST_BYTES`, ZIP bomb limits, etc.

### Frontend

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | Backend origin for browser API calls (build-time for production) |

---

## The eight-step workflow

Steps are registered in [`backend/app/steps/definitions.py`](backend/app/steps/definitions.py). Each implemented step defines: JSON schema for LLM output, optional **input fields** (forms in UI), **layout** for viewers, **post-process** function, and **export formats**.

| Order | Key | Title | Depends on | LLM + post-process | Typical exports |
|------:|-----|-------|------------|--------------------|-----------------|
| 1 | `scope_analysis` | Scope Analysis | — | Yes | DOCX |
| 2 | `gap_analysis` | Gap Analysis | scope | Yes | DOCX |
| 3 | `feature_list` | Feature List | gap | Yes | DOCX |
| 4 | `estimate` | Estimate | feature_list | Yes (multi-pass) | DOCX, XLSX, CSV |
| 5 | `sow` | Statement of Work | estimate | Yes + reassemble | DOCX |
| 6 | `srs` | Software Requirements Specification | sow | Yes (multi-pass) | DOCX, XLSX, CSV |
| 7 | `sprint_plan` | Sprint Plan | srs | Yes (multi-pass) | DOCX, XLSX, CSV |
| 8 | `frs` | Functional Requirements Specification | sprint_plan | Yes (multi-pass) | DOCX, XLSX, CSV |

**Gating rule:** Step *N* is generally **locked** until step *N−1* is **approved**. Generating creates a new **version**; **approve** marks the version current and unlocks downstream work.

**FRS completion:** Approving FRS can mark the **project completed** and enable **project package** download (ZIP of deliverables), subject to permissions and backend assembly logic.

---

## How generation works

1. **Context assembly** — Approved JSON from upstream steps plus intake projection is compiled into prompts (per step modules under `backend/app/services/*_generation.py` and `backend/app/steps/`).
2. **Structured LLM call** — [`backend/app/llm/gemini.py`](backend/app/llm/gemini.py) requests JSON matching a Pydantic model (converted to Gemini `response_schema`).
3. **Validation** — Pydantic parses the response; schema registry rejects forbidden Gemini schema keywords at import time.
4. **Post-processing** — Step-specific functions (e.g. `postprocess_srs`, `postprocess_frs`) assign IDs, dedupe, compute health metrics, build traceability, and produce the **stored** document shape.
5. **Persistence** — Result saved on `StepVersion`; progress written for UI polling.
6. **Recovery** — If the process dies mid-generation, startup/lazy recovery marks stale in-flight rows failed with safe codes.

**Important operational detail:** Gemini rejects some JSON Schema features (notably certain `maxItems` on arrays in large nested models). FRS and other steps encode workarounds in schema design; after schema changes, **restart the API** before retrying generation.

**Concurrency:** `MAX_CONCURRENT_GENERATIONS` limits parallel jobs **per uvicorn worker**. Multiple workers multiply throughput and Gemini load.

---

## Authentication, sessions, and RBAC

### Login model

- `POST /auth/login` → JSON with **access token** + user profile; **refresh token** in HttpOnly cookie.
- `POST /auth/refresh` → new access token using cookie.
- `POST /auth/logout` → clears refresh cookie server-side.
- Frontend stores access token in memory/local pattern and sends `Authorization: Bearer …` on API calls.

### Permissions (seeded)

Defined in [`backend/app/seed.py`](backend/app/seed.py), including:

`project.create`, `project.view`, `project.archive`, `project.delete`, `input.add`, `step.generate`, `step.request_changes`, `step.edit`, `step.approve`, `step.reopen`, `document.download`, `reference.view`, `reference.manage`, `template.view`, `template.manage`, `prompt.view`, `audit.view`, `audit.export`, `user.manage`, `role.manage`, `settings.manage`.

Default roles:

- **Admin** — all permissions  
- **Lead** — generate, approve, audit view, etc.  
- **Analyst** — create and work steps (approval subject to policy)  
- **Viewer** — read/download  

Manage users and role permission sets in the **Users** and **Roles** admin pages.

---

## Database and migrations

- **ORM:** SQLAlchemy 2.x models under `backend/app/models/` (projects, steps, auth, files, system settings).
- **Migrations:** Alembic in `backend/alembic/versions/`.

Common commands (from `backend/`):

```bash
alembic current
alembic history
alembic upgrade head
alembic revision --autogenerate -m "describe change"   # developer workflow
```

After pulling new migrations, always run `alembic upgrade head` before starting the API.

---

## Object storage (S3 / MinIO)

### What is stored

- **Intake attachments** (PDF, DOCX, XLSX, images, etc.) keyed by project/file metadata in Postgres.
- **Diagram or binary artifacts** produced during some steps (when applicable).
- Diagnostic scripts use **`S3_TEST_BUCKET`** with isolated prefixes.

### MinIO image note

Community `minio/minio` images are not pullable on all networks. This repo pins a **Chainguard MinIO** image in `docker-compose.yml` (S3-compatible).

### Production

- Do **not** use MinIO root credentials for the app. Create an IAM user or MinIO service account limited to the app bucket(s).
- Set `S3_PATH_STYLE` appropriately (often `false` for AWS virtual-hosted style).
- Enable encryption, versioning, and lifecycle policies per your org standards.

### Diagnostics (backend)

```bash
cd backend && source .venv/bin/activate
python -m scripts.diagnose_storage
python -m scripts.report_missing_storage_objects
python -m scripts.find_orphans --min-age 0
```

---

## File intake and text extraction

When users create a project or add input, files are validated and uploaded to S3. Text is extracted **on the server** without Gemini:

| Format | Library |
|--------|---------|
| PDF | pypdf |
| DOCX | python-docx |
| XLSX | openpyxl |
| CSV / plain text | stdlib |
| Email (.eml) | stdlib `email` |

Extracted text is capped by `MAX_EXTRACTED_TEXT_CHARS` (truncation marker appended if exceeded). Extraction status is exposed on project/intake APIs for the UI.

---

## Exports and project package

- Per-step **Download** uses stored JSON → `backend/app/documents/*` renderers.
- Formats depend on `export_formats` on each step definition (DOCX, XLSX, CSV).
- **Project package** (`GET /projects/{id}/package`) aggregates approved deliverables after workflow completion (size cap `PROJECT_PACKAGE_MAX_BYTES`).

---

## Testing

### Backend (pytest)

From `backend/` with venv:

```bash
pytest
ruff check .
```

Requires Postgres for many tests; migration tests use a **`scopedesk_test`** database. If Postgres is unavailable, some tests skip.

Set in test env automatically (see `backend/tests/conftest.py`): `SKIP_STARTUP_CHECKS=true`, `APP_ENV=test`, `ENABLE_TEST_ROUTES=true`.

### Frontend (Vitest)

From `frontend/`:

```bash
npm run typecheck
npm run test
npm run lint
npm run build
```

### All unit/integration tests

From repo root:

```bash
bash scripts/run-all-tests.sh
```

Optional E2E:

```bash
RUN_E2E=1 bash scripts/run-all-tests.sh
```

---

## Playwright E2E

E2E uses **separate ports** to avoid clashing with daily dev:

| Service | Dev default | E2E default |
|---------|-------------|-------------|
| Frontend | 5173 | 5174 |
| API | 8000 | 8001 |

Setup:

```bash
cd e2e
cp .env.example .env   # optional; playwright merges backend/.env for admin password
npm install
npx playwright install chromium
npm test
```

Playwright config starts backend via [`scripts/e2e-start-backend.sh`](scripts/e2e-start-backend.sh) and Vite with `VITE_API_BASE_URL` pointing at the E2E API.

Set `E2E_LIVE_GENERATE=1` in `e2e/.env` only when you intentionally want tests to call **live Gemini** (slow, costs money).

---

## Production and security notes

- Set `APP_ENV` to something other than `development` and use a **strong `JWT_SECRET` (32+ characters)**.
- Restrict `ALLOWED_ORIGINS` to real front-end origins; keep `allow_credentials=True` in mind when adding new domains.
- Run Uvicorn behind a reverse proxy (TLS termination, request size limits).
- Store secrets in a secret manager, not git. Repo `.gitignore` excludes `.env` files.
- Gemini: treat client data according to your **data processing agreement** with Google; use enterprise controls if required.
- Tune `MAX_CONCURRENT_GENERATIONS` and step timeouts for your SLA and API quotas.
- Back up Postgres and S3 buckets; audit log retention is in Postgres.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| API exits immediately on start | Postgres or MinIO down | Start services; run `ensure_buckets`; check `DATABASE_URL` |
| `health/ready` → 503 object_storage | Wrong keys, bucket missing, MinIO down | Align `S3_*` with MinIO; run `python -m scripts.ensure_buckets` |
| CORS errors in browser | Origin not allowed | Add Vite URL to `ALLOWED_ORIGINS`; restart API |
| Login fails after seed | Wrong admin env | Re-check `ADMIN_EMAIL`/`ADMIN_PASSWORD`; seed does not overwrite existing password |
| Generation `INVALID_ARGUMENT` from Gemini | Schema/model mismatch | Pull latest code; restart API; verify `GEMINI_MODEL`; see backend schema notes for FRS/SRS |
| Generation `FrozenInstanceError` / context errors | Stale code | Restart API after pulling fixes |
| Upload fails size limit | `MAX_UPLOAD_FILE_BYTES` | Increase only with care; adjust proxy body limits too |
| Playwright cannot connect | Ports in use | Stop dev servers or change `E2E_*` URLs in `e2e/.env` |
| MinIO image pull fails | Registry/network | Use pinned Chainguard image in compose; see `backend/README.md` |

**Gemini sanity scripts** (from `backend/`):

```bash
python -m scripts.list_models
python -m scripts.try_gemini
```

---

## Repository conventions

- **Python style:** Ruff (`ruff check .` in `backend/`).
- **TypeScript:** `npm run typecheck`, oxlint.
- **Migrations:** Never edit applied migration history in shared branches without team agreement; add new revisions.
- **Secrets:** Never commit `.env`, keys, or client attachments.

---

## Quick reference cheat sheet

```bash
# Infra
cp .env.example .env                    # repo root — MinIO
docker compose up -d minio
docker compose --profile full-stack up -d postgres   # optional

# Backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
# edit .env (DATABASE_URL, GEMINI_*, JWT_SECRET, S3_*, ADMIN_*, ALLOWED_ORIGINS)
python -m scripts.ensure_buckets
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm install && cp .env.example .env
npm run dev    # http://localhost:5173
```

---

*Document generated for the ScopeDesk monorepo (`pre-sale-tool`). For backend maintenance scripts and MinIO details, keep [`backend/README.md`](backend/README.md) open alongside this guide.*
