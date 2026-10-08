# ScopeDesk backend

## Prerequisites

- Python 3.11+
- Docker Compose (ScopeDesk MinIO; Postgres may be an existing host DB)

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, GEMINI_MODEL, JWT_SECRET, etc.
```

### ScopeDesk MinIO (local object storage)

Community `minio/minio` images are no longer pullable from Docker Hub / Quay on many networks. This repo uses the **Chainguard MinIO** image (S3-compatible), pinned by digest in `docker-compose.yml`.

From the **repo root**:

1. Copy `.env.example` to `.env` and set strong `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` (used by compose).
2. Match `S3_ACCESS_KEY` / `S3_SECRET_KEY` in `backend/.env` to those same values (the API uses root credentials for local dev only).
3. Start MinIO only (does not touch `sentinel-*` on 9000/5432):

```bash
docker compose up -d minio
```

- S3 API: `http://localhost:9100`
- Console: `http://localhost:9101` — log in with the credentials in the **repo root `.env`** (`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`).

Before any shared or staging environment, replace root credentials with a **restricted access key** scoped to the `scopedesk` and `scopedesk-test` buckets.

Create buckets (names must match `S3_BUCKET` and `S3_TEST_BUCKET` in `backend/.env`):

```bash
cd backend
source .venv/bin/activate  # or venv
python -m scripts.ensure_buckets
```

On startup the API verifies Postgres (`SELECT 1`) and MinIO (`head_bucket`). If either fails, uvicorn exits unless `SKIP_STARTUP_CHECKS=true`.

## Run API

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

- Liveness: `GET http://localhost:8080/health` (process up; no dependency checks)
- Readiness: `GET http://localhost:8080/health/ready` (database + object storage; `503` if not ready)

Step generation uses `MAX_CONCURRENT_GENERATIONS` (default 2) as a **per-process** limit. If you run multiple uvicorn workers, each worker allows that many concurrent Gemini calls independently.

## Seed RBAC and admin (Phase 1)

Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `ADMIN_FULL_NAME` in `.env`, then:

```bash
python -m app.seed
```

Safe to run repeatedly: adds missing permissions, roles, and links; does not remove custom role links or reset an existing admin password.

## Database migrations

```bash
cd backend
source venv/bin/activate
alembic current
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Phase 0: Gemini (dummy data only)

From `backend/` with `.env` set (`GEMINI_API_KEY`, `GEMINI_MODEL`):

```bash
python -m scripts.list_models
python -m scripts.try_gemini
python -m scripts.try_gemini --bad-schema
```

Do not send real client data on the free tier.

## Storage diagnostics

```bash
python -m scripts.diagnose_storage   # uses scopedesk-test only, diagnostics/ prefix
python -m scripts.report_missing_storage_objects
python -m scripts.find_orphans --min-age 0
```

## Quality checks

```bash
cd backend
source venv/bin/activate
ruff check .
pytest
```
