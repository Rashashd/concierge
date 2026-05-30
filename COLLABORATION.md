# Collaboration

## Team ownership

The team split the work into three vertical slices so that each person owned a
complete part of the product instead of only one technical layer.

| Person | Slice | Main ownership |
|---|---|---|
| Racha | Platform foundation | tenancy, database, RLS, auth, provisioning, Vault, erasure, CI skeleton, admin UI |
| Hadi | Conversation surface | hosted LLM adapter, classifier router, LangGraph agent, RAG, memory, widget |
| Hussein | Models and safety | classifier training/eval, model-server, guardrails, red-team evals, supporting docs |

---

## Racha contribution report

Racha owned the platform foundation slice: everything that underpins multi-tenancy before the first LLM call happens.

### Database and isolation

Racha designed and wrote all Alembic migrations, including the PostgreSQL RLS policies that enforce tenant isolation at the database layer. Every tenant-scoped table (`content_items`, `chunks`, `leads`, `widget_configs`) carries a policy of the form:

```sql
CREATE POLICY tenant_isolation ON <table>
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
```

The `true` flag on `set_config` is mandatory: it makes the session variable transaction-local, preventing pooled connections from leaking one tenant's value into the next request. RLS is a backstop — every repository query also explicitly filters by `tenant_id` in the `WHERE` clause.

### Auth and tenant provisioning

Racha implemented the authentication system (FastAPI Users, JWT, `tenant_manager` / `tenant_admin` / visitor role model) and the tenant provisioning API: `POST /tenants`, `GET /tenants`, `POST /{id}/suspend`, `POST /{id}/unsuspend`, and `DELETE /{id}`. Role enforcement follows a hard rule: `401` for missing/invalid tokens, `403` for valid tokens with insufficient role — no `200` with error payloads.

### Vault integration

Racha built the Vault KV v2 client in `app/infra/vault.py` and wired it into the backend lifespan. All runtime secrets (DB credentials, LLM API keys, MinIO keys, widget token secret, service-to-service tokens) are read once at startup and cached in `Settings` for the process lifetime. No secret appears in environment variables visible to container inspect or CI logs.

### PII redaction

Racha implemented the Presidio-based PII redactor in `app/security/redaction.py`. The redactor runs before any downstream touchpoint — guardrails, classifier, agent, and Redis memory all receive the redacted message. The raw user message never reaches the LLM, classifier, or persistent storage.

### Tenant erasure

Racha built `services/erasure.py`, which implements the GDPR right-to-erasure path. A single `POST /tenants/{id}/erase` call deletes all Redis session keys, MinIO objects under the tenant prefix, pgvector chunks, content items, widget configs, and leads, then writes an audit log entry. Cost records are intentionally preserved for billing.

### Content management and indexing

Racha built the content CRUD API (`app/api/content.py`) and the indexing service (`app/services/indexing.py`), which embeds content items into pgvector via Azure OpenAI embeddings and syncs blobs to MinIO. Create and update operations trigger re-indexing immediately; delete removes both the content item and its chunks.

### Streamlit admin UI

Racha built the full Streamlit admin application (`streamlit/`). The UI is a thin API client with no business logic of its own — every action calls a backend endpoint. It is split into two role-scoped page groups:

- **Tenant manager pages:** tenant list/suspend/unsuspend, create tenant, audit log, health checks, cost monitoring, widget embed snippet
- **Tenant admin pages:** persona and guardrail config, content CRUD with pagination, leads viewer, escalations viewer, embed snippet

Key hardening applied: JWT expiry triggers automatic session clear and redirect; unsaved-changes warning on persona form; slug and password validation on create-tenant form; pagination on all list views.

### CI pipeline

Racha wrote `.github/workflows/ci.yml`, structured into separate jobs so that lint and unit tests give feedback in under 60 seconds without infrastructure. The `stack-smoke` job builds the full Docker stack and verifies `/healthz`. The `eval-rag-golden` job is gated behind an Azure secret availability check so it skips gracefully on forks.

### Integration tests

Racha wrote the live end-to-end integration test suite in `tests/integration/test_live_pipeline.py` (9 tests). These tests run the real ASGI app in-process against real Postgres/pgvector, Redis, Vault, MinIO, and Azure OpenAI, and verify: RAG content isolation between tenants, widget token tenant scoping, Redis session key isolation, PII redaction before storage, guardrails blocked-topic refusal, and prompt-injection refusal. Tests skip gracefully in CI when Vault is unreachable.

### Coordination notes

- Hadi's `/chat` handler uses the `get_admin_tenant_session` dependency and `require_tenant_admin` gate that Racha built.
- The Vault token flow Racha designed is reused by Hadi's guardrails client and Hussein's model-server.
- The RLS session variable set by Racha's `get_session` dependency applies to every query Hadi's RAG and tool repositories make.
- The `ErasureReport` returned by Racha's erasure service clears Redis memory that Hadi's memory service manages.

---

## Hadi contribution report

Hadi owned the conversation surface slice: everything from the moment a widget token is verified to the moment a response is returned and stored.

### Chat agent path

Hadi built the `/chat` endpoint and the bounded LangGraph agent loop. Verified tenant context flows from the widget JWT into the agent state; `tenant_id` is never accepted from the request body, headers, query params, or tool arguments. The agent can choose `rag_search`, `capture_lead`, or `escalate`, but all tenant-scoped inputs are injected server-side.

The system prompt lives in `backend/app/prompts/v1/system.md` rather than inline in route code, keeping the isolation contract reviewable and versionable like code.

### RAG retrieval

Hadi wired the RAG retrieval path and built the eval stack to measure it in phases:

1. **Baseline pgvector** — measured before adding anything advanced
2. **LLM reranker** — pgvector fetches 20 candidates; the LLM reranker scores and keeps the top 5 (hit@1 +14%, expected doc precision@5 +21%, answer phrase pass rate +36%)
3. **Hybrid search + reranker** — pgvector dense retrieval combined with Postgres full-text search (0.7/0.3 weights), then reranker (context_precision +7% over reranker-only)

Metadata filtering, parent-child retrieval, and runtime RAGAS judge were explicitly deferred: no metadata conventions were stable enough to filter reliably, and adding them without a metric delta would be premature complexity.

### Conversation tools

Hadi implemented all three agent tools:

- `rag_search` — server-side tenant context injection, pgvector retrieval with repository-layer tenant filter
- `capture_lead` — write to `leads` table with per-session rate limiting (3 writes/hour); `tenant_id` from verified context only
- `escalate` — writes an audit log entry, returns a visitor message and ticket ID

Agent state carries the DB session so tools can issue queries within the same transaction context as the chat handler.

### Redis memory

Hadi implemented `services/memory.py` and integrated it into the `/chat` flow with tenant-scoped keys (`session:{tenant_id}:{session_id}`). Only the redacted user message and the final guardrailed assistant answer are stored — no pre-guardrail output, no raw PII.

### Tenant admin APIs

Hadi built the lead management APIs (`GET /leads`, `PATCH /leads/{id}`) and the content management APIs (`GET/POST/PUT/DELETE /content`) for the `tenant_admin` role. These complement Racha's content indexing service — Hadi's endpoints are the write surface; indexing is triggered via the service layer.

### Cost attribution

Hadi added cost tracking: each agent turn reports token counts from `AIMessage.usage_metadata` across all AI messages in the turn, summed and persisted to `cost_records` via `services/cost.py`. Token counts are stored, not dollar amounts — pricing policy is a separate concern that changes more often than raw token accounting.

### Chat security hardening

Hadi hardened the `/chat` path with origin enforcement (`app/security/origin.py`), whitespace-only message rejection, and prompt isolation text in the system prompt that instructs the agent to treat tenant context as server-verified and to refuse any instruction to switch tenants or disclose tenant data.

### Guardrails integration hardening

Hadi tightened the guardrails integration after the sidecar was running correctly:

- The backend now applies `safe_text` from the guardrails response — sanitized text is used downstream instead of the raw input
- Sanitized text is forwarded to NeMo rather than the original user message
- Service-token authentication was wired through Docker Compose and Vault so the sidecar requires a valid bearer token on every request
- Guardrail endpoint tests were added to the integration suite

### CI and eval structure

Hadi reorganized `ci/` into `ci/rag`, `ci/agent`, and `ci/redteam` subdirectories and updated all references. He built the RAG golden dataset (`ci/rag/rag_golden.json`, 20 examples across three tenants, 5 distractors per tenant) and the deterministic + RAGAS eval pipeline. The corpus uses fictional terminology so no answer can be hallucinated from model training data.

### Coordination notes

- The RLS session, DB session dependency, and `get_admin_tenant_session` that Hadi's routes use were built by Racha.
- Hadi's guardrails client reads the service token from Vault using the infrastructure Racha designed.
- Hussein's model-server prediction contract is consumed by Hadi's classifier router.
- The Presidio redactor Racha built feeds into the `/chat` flow Hadi owns — they agreed on the placement: redaction before guardrails, before classifier, before agent, before memory.

---

## Hussein contribution report

Hussein owned the models and safety slice of the Concierge project. His work
focused on the trained classifier, the lean model-server, the guardrails
sidecar, the red-team checks, and the documentation needed to defend those
decisions.

### Model and classifier work

Hussein prepared the classifier work for the Concierge router. The classifier
predicts one of four visitor intents: `spam`, `question`, `lead`, or
`escalate`. These labels are used by the router to decide whether to drop spam,
answer through RAG, capture a lead, escalate to a human, or fall back to the
bounded agent.

The classifier work compared three approaches:

- a classical TF-IDF + Logistic Regression model
- a small DL TF-IDF MLP exported to ONNX
- a hosted-API LLM zero-shot baseline through Groq

The final documented results were:

| Model | Macro-F1 | Weighted-F1 | Avg latency ms | P95 latency ms |
|---|---:|---:|---:|---:|
| Classical TF-IDF + Logistic Regression | 0.9432 | 0.9433 | 0.95 | 1.26 |
| Small DL TF-IDF MLP exported to ONNX | 0.9627 | 0.9626 | 2.92 | 6.71 |
| Groq zero-shot LLM baseline | 0.7830 | 0.7810 | 1512.50 | 1512.50 |

Although the DL model had the highest macro-F1, Hussein documented the decision
to ship the classical model because it is very close in quality, faster,
simpler, cheaper, and easier to serve in the lean model-server without adding
PyTorch, TensorFlow, or transformers to the service containers.

### Model-server work

Hussein contributed the lean `model-server` service. The model-server exposes
the classifier behind HTTP instead of importing the model directly into the
backend. This keeps the classifier as a separate service boundary and matches
the project requirement that the trained model is served lean.

The model-server uses:

- `sklearn/joblib` for the shipped classical model
- `onnxruntime` for the DL/ONNX artifact
- artifact metadata and hashes recorded in the model card
- FastAPI endpoints for health checks and prediction

This keeps training-heavy dependencies out of production containers while still
showing that both ML and DL artifacts were produced and evaluated.

### Guardrails and red-team work

Hussein also worked on the guardrails and safety side. The guardrails sidecar
contains deterministic policy checks for prompt injection, jailbreak attempts,
cross-tenant data requests, and redaction behavior.

The red-team eval covers 9 probes:

- prompt injection attempts
- jailbreak-style override attempts
- cross-tenant data extraction attempts
- safe messages that should be allowed
- redaction of an email address and a fake API key

The latest red-team result passes with:

- required refusal rate: `1.00`
- actual refusal rate: `1.00`
- failures: `0`

This supports the project's main safety requirement: a visitor from one tenant
must not be able to extract another tenant's data or system instructions.

### Eval and documentation work

Hussein updated the evaluation and decision documentation for his slice. This
included:

- documenting the ML vs DL vs LLM comparison in `docs/DECISIONS.md`
- documenting classifier results, latency, per-class F1, and shipping rationale
- adding the classifier, agent, RAG, red-team, and redaction summaries to `docs/EVALS.md`
- keeping `ci/eval_thresholds.yaml` aligned with the current gates
- explaining why `tool_selection_accuracy_min` remains at `0.30` until the golden set is expanded

### Coordination notes

Hussein's slice connected with the rest of the team in these places:

- Hadi's classifier router depends on the model-server prediction contract.
- Racha's service-to-service authentication and Vault setup provide the service
  credential pattern used when the backend calls the model-server and guardrails
  sidecar.
- The red-team and redaction gates support the shared tenant-isolation story.
- The documentation in `DECISIONS.md` and `EVALS.md` gives the team numbers to
  defend during the final demo.

---

## Team disagreements and resolutions

**Classical vs DL classifier for production.** Hussein's DL model achieved higher macro-F1 (0.9627 vs 0.9432), but the team chose the classical model for the shipped production service. The DL model is kept as a documented ONNX comparison artifact. Rationale: the quality delta is small; the classical model is 3× faster, simpler to serve, and keeps the model-server under the container size limit without PyTorch.

**RAG complexity timing.** Hadi advocated for measuring a pgvector baseline before adding hybrid search or reranking. The team agreed: each technique was added only after documenting the delta it provided over the previous baseline. This prevented premature optimization and gave the team defensible numbers for the demo.

**Guardrails as isolation boundary.** Early discussions treated the guardrails sidecar as a tenant-isolation mechanism. The team aligned on treating it as defense-in-depth only — hard isolation guarantees come from verified token context, repository tenant filters, RLS, and tenant-scoped storage. This distinction is explicit in `docs/SECURITY.md` and `docs/DESIGN.md`.

---

## Blockers and risks

| Risk / Blocker | Status | Resolution |
|---|---|---|
| DL export adds heavy deps to production | Resolved | Training stays in notebooks; production uses ONNX Runtime only |
| LLM baseline is slow and provider-priced | Resolved | Used as comparison baseline only, not default router |
| Tool-selection accuracy threshold is low | Open | Kept at `0.30` temporarily; documented reason; tighten after expanding golden set |
| Guardrails container was running a stub | Resolved | Dockerfile lacked `build-essential` for `annoy` C++ extension; fixed and rebuilt |
| `eval-rag-golden` blocked on Azure secrets | Open | Azure OpenAI secrets not yet added as GitHub repository secrets; job skips gracefully |
| Guardrails mistaken for isolation boundary | Resolved | Documented in `SECURITY.md` and `DESIGN.md` that hard isolation comes from RLS + repo filters + verified context |
