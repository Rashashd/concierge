# Runbook — Concierge

Operational guide for local development and CI. Everything assumes you are at the repository root unless stated otherwise.

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Docker Desktop | 4.x | Must be running before any `docker compose` command |
| Python | 3.12 | Managed by `uv` — do not install it separately |
| `uv` | 0.4+ | `pip install uv` or `winget install astral-sh.uv` |
| Node.js | 18+ | Widget dev server only |

---

## First-time setup

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | What to put |
|---|---|
| `VAULT_TOKEN` | Any string — this is the dev-mode Vault root token |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Local DB credentials (your choice) |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Local MinIO credentials (your choice) |
| `AZURE_OPENAI_API_KEY` and related `AZURE_*` vars | Your Azure OpenAI deployment details |
| `WIDGET_TOKEN_SECRET` | Any 32+ character random string |

Leave `VAULT_ADDR=http://vault:8200` unchanged — it is the address used by the containerised backend. Native services use `localhost:8200` which is set separately in the startup sequence below.

---

## Starting the stack

### 1. Start infrastructure

```bash
docker compose up -d --wait postgres redis minio vault pgadmin
```

### 2. Seed Vault (first time, or after `docker compose down -v`)

```bash
VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=<your-token> bash seed.sh
```

`seed.sh` writes all required secrets into the KV v2 mount at `secret/concierge/`. This covers database credentials, LLM keys, MinIO credentials, the widget token secret, and service-to-service tokens.

### 3. Run database migrations

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/<db> \
  uv run alembic upgrade head
```

### 4. Start application services

Run each in a separate terminal:

```bash
# Backend API
cd backend
VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=<token> \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Intent classifier
cd model-server
VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=<token> \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

# NeMo guardrails sidecar (requires annoy C++ extension — see note below)
cd guardrails
GUARDRAILS_SERVICE_TOKEN=local-guardrails-token NEMO_ENABLED=false \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8002

# Streamlit admin UI
cd streamlit
BACKEND_URL=http://localhost:8000 \
  uv run streamlit run app.py --server.port 8501

# Widget dev server
cd widget
npm install && npm run dev
```

> **Guardrails on Windows:** `nemoguardrails` depends on the `annoy` C++ extension, which requires MSVC Build Tools (`winget install Microsoft.VisualStudio.2022.BuildTools`). If you cannot compile it, run guardrails in Docker instead: `docker compose up -d guardrails`.

### Full Docker alternative

```bash
docker compose up -d --wait
```

Builds and starts all services. Seed Vault and run migrations as above after the stack is healthy.

---

## Service endpoints

| Service | URL | Notes |
|---|---|---|
| Streamlit admin | http://localhost:8501 | Primary UI for tenant managers and admins |
| Backend API docs | http://localhost:8000/docs | FastAPI Swagger UI |
| Backend health | http://localhost:8000/healthz | Returns `{"status":"ok"}` |
| Widget dev server | http://localhost:5173 | Vite HMR dev build |
| Vault UI | http://localhost:8200 | Token = `VAULT_TOKEN` from `.env` |
| pgAdmin | http://localhost:5050 | `admin@concierge.local` / `admin` |
| MinIO console | http://localhost:9001 | Credentials from `.env` |
| Model server health | http://localhost:8001/healthz | TF-IDF classifier |
| Guardrails health | http://localhost:8002/healthz | NeMo sidecar |

---

## Common operations

### Create a tenant

1. Open Streamlit at `http://localhost:8501`
2. Log in as a `tenant_manager` account (register one via `POST /auth/register` if first run — see API docs)
3. Go to **Create Tenant** → fill in name and slug → click **Create**
4. Go to **Tenants** → find the new tenant → copy its UUID

### Add or update content

Log in to Streamlit as a `tenant_admin` → go to **Content** → use the create / edit / delete forms. Every change is re-indexed into pgvector immediately (no separate indexing step).

### Reindex a tenant's content

If embeddings are stale or missing: Streamlit → **Content** → click **Reindex All**. This re-embeds every content item for the tenant and rebuilds the pgvector chunks.

### Run the full test suite

```bash
cd backend
uv run pytest tests/unit/ tests/smoke/ -v --tb=short          # fast, no infra required
uv run pytest tests/integration/test_live_pipeline.py -v      # requires full stack running
```

### Run evals

```bash
# Agent golden set (deterministic, no API calls — runs in CI)
cd backend && uv run python ../ci/agent/run_agent_golden.py

# Red-team guardrail probes (deterministic — runs in CI)
NEMO_ENABLED=false python ci/redteam/run_redteam.py

# RAG golden set (requires Azure OpenAI + live Postgres + Vault)
cd backend
RAG_EVAL_DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/<db> \
  VAULT_ADDR=http://localhost:8200 \
  VAULT_TOKEN=<token> \
  uv run python ../ci/rag/run_rag_golden.py
```

### Rotate a Vault secret

```bash
# Read current value
VAULT_ADDR=http://localhost:8200 vault kv get secret/concierge/llm

# Update a single field (merges with existing data)
VAULT_ADDR=http://localhost:8200 vault kv patch secret/concierge/llm openai_api_key=sk-new-key
```

After rotating any secret, restart the affected service — settings are loaded once at process startup and cached for the process lifetime.

### Erase a tenant (GDPR right-to-erasure)

```http
POST /tenants/{tenant_id}/erase
Authorization: Bearer <tenant_manager_token>
```

`services/erasure.py` deletes in order: all Redis session keys for the tenant, all MinIO objects under `tenants/{tenant_id}/`, all pgvector chunks, all content items, all widget configs, all leads, and writes an audit log entry. Cost records are intentionally preserved for billing.

### Reset the local database

```bash
docker compose down -v            # removes postgres_data and redis_data volumes
docker compose up -d --wait postgres redis minio vault
bash seed.sh                      # re-seed Vault
cd backend && DATABASE_URL=... uv run alembic upgrade head
```

---

## CI pipeline

The CI runs on every push and pull request via `.github/workflows/ci.yml`.

| Job | What it checks | Infrastructure needed |
|---|---|---|
| `lint` | `ruff check`, `ruff format --check`, `mypy app` | None |
| `unit-tests` | `pytest tests/unit/` | None (mocked) |
| `integration-tests` | `pytest tests/integration/ tests/smoke/` | None (live tests skip when Vault unreachable) |
| `stack-smoke` | Full Docker stack builds, backend passes `/healthz` | Full Docker stack (built in job) |
| `eval-agent-golden` | Agent routing correctness, 8 deterministic examples | None |
| `eval-classifier` | Classifier macro-F1 gate (`continue-on-error` — needs model artifacts) | None |
| `eval-redteam` | Guardrail probe refusal rate | None (`NEMO_ENABLED=false`) |
| `eval-rag-golden` | RAG hit@5, faithfulness, cross-tenant leak count | Postgres + Vault + Azure OpenAI (skips if secrets absent) |
| `secret-scan` | Gitleaks secret detection | None |

Integration tests that require the live stack (`test_live_pipeline.py`) are guarded with a Vault reachability check at collection time — they skip gracefully in CI and run when the stack is up locally.

---

## Troubleshooting

**Backend crashes on startup with `ConnectionRefusedError` at `vault.py`**
Vault is not healthy or the token is wrong. Check: `docker compose ps vault` and `docker compose logs vault`. Re-run `seed.sh` with the correct token.

**Alembic fails — `password authentication failed`**
The Postgres volume has stale credentials from a previous run. Reset with `docker compose down -v` and restart.

**RAG answers are generic and ignore tenant content**
Embeddings are not indexed. In Streamlit → **Content**, click **Reindex All**.

**Widget token endpoint returns 500 — `Widget token signing is not configured`**
The `WIDGET_TOKEN_SECRET` in `secret/concierge/widget` is missing or shorter than 32 characters. Patch it with `vault kv patch` and restart the backend.

**`eval-rag-golden` is skipped in CI**
The GitHub repository secrets `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT` are not set. Ask the repository owner to add them under Settings → Secrets.
