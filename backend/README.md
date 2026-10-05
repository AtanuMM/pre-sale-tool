# ScopeDesk backend

## Prerequisites

- Python 3.11+
- Docker Compose (Postgres and MinIO)

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, GEMINI_MODEL, JWT_SECRET, etc.
```

From the repo root, start Postgres and MinIO:

```bash
docker compose up -d
```

Create the S3 bucket once (name must match `S3_BUCKET` in `.env`, default `scopedesk`):

- MinIO console: http://localhost:9001 (login `minioadmin` / `minioadmin`), create bucket `scopedesk`, or
- `aws --endpoint-url http://localhost:9000 s3 mb s3://scopedesk` with credentials from `.env`

On startup the API verifies Postgres (`SELECT 1`) and MinIO (`head_bucket`). If either fails, uvicorn exits unless `SKIP_STARTUP_CHECKS=true`.

## Run API

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Liveness: `GET http://localhost:8000/health` (process up; no dependency checks)
- Readiness: `GET http://localhost:8000/health/ready` (database + object storage; `503` if not ready)

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

## Quality checks

```bash
cd backend
source venv/bin/activate
ruff check .
pytest
```
