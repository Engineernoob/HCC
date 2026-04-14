# Hirectl Backend

It’s a real-time hiring intelligence system that identifies high-signal opportunities and tells you exactly how to act before they get saturated.

The backend:
- ingests live hiring signals from multiple sources
- persists companies, roles, signals, profile preferences, and historical rollups
- computes fit, urgency, and model-blended scores
- serves the Next.js console over FastAPI
- runs scheduled ingestion and enrichment jobs

## Architecture

```text
hirectl/
  config.py                  env-driven settings
  cli.py                     hirectl CLI
  scheduler.py               APScheduler worker
  tracked_companies.py       tracked companies + portfolio board registry
  api/
    app.py                   FastAPI API
  ai/
    engine.py                best-effort AI generation with Ollama/OpenAI/Anthropic
  analytics/
    history.py               daily rollups + dataset export
  automation/
    service.py               watchlist + outreach automation
  db/
    models.py                SQLAlchemy models
    repository.py            async repositories
    session.py               DB engine/session setup
  ingestion/
    ashby.py                 Ashby job boards
    career_page.py           direct career-page crawler
    funding.py               funding feeds + SEC Form D
    github_watcher.py        GitHub activity signals
    greenhouse.py            Greenhouse boards
    portfolio_boards.py      multi-company portfolio boards like a16z Jobs
    social.py                broader social/news/community signals
    yc_jobs.py               Work at a Startup
    service.py               persistence + rescoring
  modeling/
    baseline.py              hiring velocity baseline model
```

## Current stack

- Python 3.11
- FastAPI
- SQLAlchemy async
- PostgreSQL + pgvector
- Redis
- APScheduler
- Docker Compose
- Ollama optional but supported in Docker

## Quickstart

### 1. Configure env

```bash
cd /Users/taahirahdenmark/HCC/hirectl-backend
cp .env.example .env
```

Important local defaults:
- Postgres host port is `5433`, not `5432`
- API runs on `http://localhost:8000`
- Ollama runs on `http://localhost:11434`

### 2. Start Docker services

```bash
docker compose up -d postgres redis ollama
```

If you want the full stack in Docker:

```bash
docker compose up -d postgres redis ollama api scheduler
```

### 3. Install the backend locally

```bash
python3 -m venv .hirebackend
source .hirebackend/bin/activate
pip install -e .
```

### 4. Initialize the database

```bash
hirectl db init
```

### 5. Pull the small Ollama model

The default local model is `llama3.2:1b`.

```bash
docker compose exec ollama ollama pull llama3.2:1b
```

If Ollama is unavailable, ingestion and scoring still continue. AI output falls back to deterministic text.

### 6. Start the API

Local process:

```bash
source .hirebackend/bin/activate
hirectl api --reload
```

Docker:

```bash
docker compose up -d api
```

### 7. Start the scheduler

Local process:

```bash
source .hirebackend/bin/activate
hirectl scheduler
```

Docker:

```bash
docker compose up -d scheduler
```

## Ingestion sources

Run everything:

```bash
hirectl ingest
```

Run a specific source:

```bash
hirectl ingest --source greenhouse
hirectl ingest --source ashby
hirectl ingest --source yc_jobs
hirectl ingest --source career_page
hirectl ingest --source funding
hirectl ingest --source github
hirectl ingest --source social
hirectl ingest --source portfolio_boards
```

Current major sources:
- `greenhouse`
- `ashby`
- `yc_jobs`
- `career_page`
- `funding`
- `github`
- `social`
- `portfolio_boards`

Notes:
- `portfolio_boards` currently supports Consider-powered portfolio boards like `jobs.a16z.com`
- `career_page` defaults to the lighter HTTP renderer; set `CAREER_PAGE_RENDERER=auto` or `playwright` only if needed

## CLI reference

```text
hirectl ingest [--source SOURCE] [--verbose]
hirectl automate
hirectl dataset build --as-of-start YYYY-MM-DD --as-of-end YYYY-MM-DD
hirectl model train --dataset artifacts/hiring_velocity_dataset.csv
hirectl model refresh
hirectl score COMPANY_NAME
hirectl brief COMPANY_NAME [--provider anthropic|openai|ollama]
hirectl brief-refresh [--limit N]
hirectl outreach COMPANY_NAME [--contact ROLE] [--angle TEXT]
hirectl digest [--send]
hirectl api [--host HOST] [--port PORT] [--reload]
hirectl scheduler
hirectl db [init|status|reset]
hirectl status
```

## API

### Health and stats

```text
GET /healthz
GET /api/stats
```

### Companies

```text
GET /api/companies?stage=series_b&remote_us=true&min_score=70
GET /api/companies/{id_or_slug}
POST /api/companies/{id_or_slug}/brief
POST /api/companies/{id_or_slug}/outreach
PUT /api/companies/{id_or_slug}/watchlist
```

### Signals and roles

```text
GET /api/signals?hours=168&min_score=50
GET /api/signals/stream
GET /api/roles?role_type=backend&remote_us=true
POST /api/ingest/run?source=greenhouse
```

### Candidate profile

Used by the frontend personalization layer.

```text
GET /api/profile
PUT /api/profile
```

Example:

```bash
curl http://localhost:8000/api/profile
```

```bash
curl -X PUT http://localhost:8000/api/profile \
  -H 'Content-Type: application/json' \
  --data '{
    "preferredRoles":["backend","infra","distributed"],
    "preferredSkills":["python","postgres","docker","kubernetes"],
    "preferredStages":["seed","series a","series b"],
    "remoteOnly":true,
    "preferredLocations":["remote"],
    "targetCompanyIds":[],
    "avoidCompanyIds":[]
  }'
```

## AI behavior

AI is best-effort.

- If Ollama/OpenAI/Anthropic is available, the backend can generate briefs and outreach drafts.
- If AI is down or times out, ingestion still succeeds.
- AI brief refresh runs outside the ingest critical path.

Useful commands:

```bash
hirectl brief "Baseten"
hirectl brief-refresh --limit 8
hirectl outreach "Turso" --contact "engineering lead"
```

Default Ollama settings:

```env
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:1b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT_SECONDS=8
AI_FAILURE_COOLDOWN_SECONDS=120
```

## Scheduler

The scheduler is APScheduler-based and runs:
- job board ingests
- funding ingests
- social ingests
- career page crawls
- automation
- daily rollups
- model refresh
- brief refresh
- daily digest

It has a heartbeat-based Docker healthcheck and does not expose HTTP.

Useful settings:

```env
SCHEDULER_RUN_ON_STARTUP=false
APSCHEDULER_LOG_LEVEL=WARNING
CRON_JOB_BOARDS=0 */4 * * *
CRON_BRIEF_REFRESH=*/20 * * * *
```

## Historical data + model

Build the training dataset:

```bash
hirectl dataset build \
  --as-of-start 2026-04-07 \
  --as-of-end 2026-04-09 \
  --step-days 1 \
  --output artifacts/hiring_velocity_dataset.csv
```

Train the baseline model:

```bash
hirectl model train --dataset artifacts/hiring_velocity_dataset.csv
```

Refresh model-blended scores:

```bash
hirectl model refresh
```

## Docker notes

The Compose setup is tuned to be lighter-weight than the initial version:
- Postgres is capped and tuned for local development
- Redis disables persistence
- API and scheduler have smaller memory/CPU budgets
- Ollama is included as an optional local AI service

Important exposed ports:
- API: `8000`
- Ollama: `11434`
- Postgres: `5433`
- Redis: `6379`

## Frontend connection

Local frontend env:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For Vercel + local backend tunneling:

Frontend:

```env
NEXT_PUBLIC_API_URL=https://your-ngrok-url.ngrok-free.app
```

Backend:

```env
FRONTEND_ORIGINS=https://your-vercel-app.vercel.app
```

Do not include a trailing slash in `FRONTEND_ORIGINS`.

## Deploy backend to Render

This repo includes a Render Blueprint at `render.yaml`.

It provisions:
- `hirectl-backend-api` as a Docker web service
- `hirectl-backend-scheduler` as a Docker background worker
- `hirectl-postgres` as Render Postgres
- `hirectl-redis` as Render Key Value

### 1. Create the Blueprint

In Render:

1. New Blueprint
2. Connect the backend repository
3. Select `hirectl-backend/render.yaml` if the backend is inside a monorepo
4. Confirm the generated services and database
5. Fill prompted secrets:
   - `SEC_USER_AGENT`
   - `GITHUB_TOKEN`
   - `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` if you want hosted AI summaries

If no hosted AI key is configured, the backend still works. AI calls fall back to deterministic briefs and do not block ingest.

### 2. Confirm the API service

The Docker image starts the API with Render's `PORT`:

```bash
hirectl api --host 0.0.0.0 --port ${PORT:-8000}
```

Health check:

```text
/healthz
```

After deploy, test:

```bash
curl -sS https://YOUR-RENDER-SERVICE.onrender.com/healthz
curl -sS https://YOUR-RENDER-SERVICE.onrender.com/api/stats
```

### 3. Connect Vercel frontend

Update the frontend environment variable in Vercel:

```env
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Then redeploy the frontend.

The Blueprint allows:
- `https://hirectl.vercel.app`
- Vercel preview/deployment URLs matching `https://*.vercel.app`

### 4. Production notes

Render does not run the local Docker Compose Ollama service. The Render config keeps Ollama timeout short so unavailable local AI does not stall ingestion. For production-quality AI briefs, set:

```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

or:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=...
```

## Remote production control

Render free instances do not provide local-terminal SSH into the service. Use the protected admin API instead.

Set this env var on both Render services:

```env
ADMIN_API_KEY=use-a-long-random-secret
```

Then redeploy/restart `hirectl-backend-api`.

Trigger a full ingest from your local terminal:

```bash
curl -X POST "https://hirectl-backend.onrender.com/api/admin/ingest" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

Trigger one source:

```bash
curl -X POST "https://hirectl-backend.onrender.com/api/admin/ingest?source=funding" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

Valid sources:
- `yc_jobs`
- `greenhouse`
- `ashby`
- `github`
- `funding`
- `career_page`
- `portfolio_boards`
- `social`

Run automation:

```bash
curl -X POST "https://hirectl-backend.onrender.com/api/admin/automate" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

Refresh model-blended scores:

```bash
curl -X POST "https://hirectl-backend.onrender.com/api/admin/model-refresh" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

Recommended production refresh loop:

```bash
curl -X POST "https://hirectl-backend.onrender.com/api/admin/ingest" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
curl -X POST "https://hirectl-backend.onrender.com/api/admin/automate" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
curl -X POST "https://hirectl-backend.onrender.com/api/admin/model-refresh" \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

## Environment variables

See [.env.example](/Users/taahirahdenmark/HCC/hirectl-backend/.env.example) for the full set.

High-signal ones:
- `DATABASE_URL`
- `DATABASE_SYNC_URL`
- `REDIS_URL`
- `AI_PROVIDER`
- `AI_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `FRONTEND_ORIGINS`
- `GITHUB_TOKEN`
- `CRUNCHBASE_API_KEY`
- `SEC_USER_AGENT`
- `SEC_FORM_D_ENABLED`
- `CAREER_PAGE_RENDERER`
- `JOB_BOARD_BATCH_SIZE`
- `CAREER_PAGE_BATCH_SIZE`
- `MODEL_ARTIFACT_PATH`

## Current reality

This backend is no longer Phase 1 only.

It now includes:
- live ingestion + persistence
- SSE signal streaming
- automation
- historical rollups
- model training/export
- candidate-profile-backed personalization
- portfolio board support

The README is intended to match the current implementation, not the original scaffold.
