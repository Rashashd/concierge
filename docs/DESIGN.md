# Design

## 1. Tenant Isolation Strategy

Isolation is enforced at four independent layers so that no single misconfiguration
creates a cross-tenant breach.

### PostgreSQL Row-Level Security

Every tenant-scoped table (`content_items`, `chunks`, `leads`, `widget_configs`) has
an RLS policy:

```sql
CREATE POLICY tenant_isolation ON <table>
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
```

The session variable is set once per request before any query runs:

```sql
SELECT set_config('app.tenant_id', :tid, true);
```

The `true` flag makes this transaction-local — it auto-clears on commit or rollback.
Pooled connections never carry a previous tenant's value forward.

### Repository Belt-and-Suspenders

Every query in `app/repositories/` explicitly filters by `tenant_id` in the
`WHERE` clause even though RLS is active:

```python
.where(Chunk.tenant_id == tenant_id)
```

Cross-tenant data cannot leak even if a session is accidentally opened without
`set_config` (e.g. in a background job). The application does not rely solely on
the database policy.

### pgvector

Vector similarity searches include the `tenant_id` filter at both the RLS and the
repository layer. The query planner applies the tenant filter before computing
cosine distances, so retrieved chunks always belong to the requesting tenant.

### Token-First Tenant Identity

`tenant_id` is injected into request context exclusively from the verified widget
JWT — never from the request body, query parameters, or headers. `ChatRequest` uses
`extra="forbid"` to reject unknown fields. A caller cannot supply or override the
tenant identity.

### Object Storage (MinIO / S3)

Objects are stored under `tenants/{tenant_id}/` prefixes. The `infra/minio.py`
adapter builds this prefix from the verified tenant context, never from user input.
Right-to-erasure deletes the entire prefix, removing all blobs for a tenant in one
operation.

### Redis Session Memory

Session keys follow the pattern `session:{tenant_id}:{session_id}`. Erasure uses a
prefix scan (`session:{tenant_id}:*`) to delete all sessions for a tenant atomically
without touching other tenants' keys.

---

## 2. Role Model

Three roles at two levels. Permissions are fixed — no configurable matrix.

| Role | Level | Key capabilities |
|---|---|---|
| `tenant_manager` | Platform | Provision tenants, suspend/reactivate, trigger erasure, read cost aggregates |
| `tenant_admin` | Tenant | Manage CMS content, configure persona and guardrails, view leads, configure widgets |
| Visitor | Request | Chat with the agent, submit leads via `capture_lead` |

The Tenant Manager cannot read tenant content. Erasure runs through a
write/delete-only maintenance path — the manager sees neither conversations nor CMS
body text.

See `docs/SPEC.md` for the full permission matrix and API-level enforcement.

---

## 3. Rate Limiting

The `capture_lead` tool enforces a per-session rate limit of **3 lead writes per
`session_id` per hour**, checked at the repository layer before any `INSERT`. This
prevents automated clients from flooding the leads table within a single conversation.

The limit is intentionally session-scoped (not IP-scoped) because the widget token
already ties the session to a verified tenant, making session_id a reliable
de-duplication key without requiring IP tracking.

---

## 4. Caching Decisions

| What | Where | Lifetime |
|---|---|---|
| All settings after Vault load | `@lru_cache` on `get_settings()` | Process lifetime |
| LangChain LLM client | `app.state.llm` (lifespan) | Service restart |
| LangChain embeddings client | `app.state.embeddings` (lifespan) | Service restart |
| Reranker (LLM or Cohere) | `app.state.reranker` (lifespan) | Service restart |
| spaCy NLP pipeline | `app.state.redactor` (lifespan) | Service restart |

Vault is read once at startup. LLM, embedding, and reranker clients are constructed
once and reused for all requests — avoiding per-request TLS handshakes and
authentication round-trips to the provider.

**Classifier results** are not cached. Model server inference (ONNX) runs in under
10 ms. User messages are free-form and rarely repeat verbatim, so a TTL cache would
have a low hit rate and add complexity without measurable benefit.

**Settings** are cached process-wide via `lru_cache`. Vault changes require a service
restart to take effect, which is the expected operational path.

---

## 5. Cost Attribution

Token usage is attributed per tenant at the service layer. Each LangGraph agent turn
reports prompt tokens, completion tokens, and total tokens via the LLM response
metadata. `services/cost.py` aggregates these into per-tenant daily totals, queryable
by the Tenant Manager for billing and capacity planning.

Cost records carry no message content — only `tenant_id`, timestamp, model name, and
token counts. No PII passes through the cost path.

---

## 6. Scaling Story — 10 Tenants to 1,000

The current architecture handles tens of tenants with no code changes. The sections
below identify which components become bottlenecks at 100 and 1,000 tenants and what
the mitigation path looks like.

### What scales naturally

**Backend API (FastAPI + uvicorn)** is stateless — all shared state lives in Postgres,
Redis, and MinIO. Adding backend replicas behind a load balancer requires no code
changes. The lifespan handler creates one connection pool per process; each replica
gets its own pool.

**MinIO / S3** — object storage scales horizontally. Switching from local MinIO to
Amazon S3 is a single environment variable change because `infra/minio.py` uses the
S3-compatible API throughout. The `tenants/{tenant_id}/` prefix structure requires no
migration.

**Redis** — session data is tenant-scoped and short-lived (24-hour TTL). A single
Redis node handles thousands of concurrent active sessions. Horizontal scaling via
Redis Cluster adds capacity without application changes.

**Vault** — secrets are loaded once at startup, not per request. Vault request volume
does not grow with tenant count.

---

### Postgres at 100 tenants

**Connection pool saturation.** The backend pool is set to `pool_size=10,
max_overflow=20` per process. At four backend replicas with 30 connections each,
this approaches Postgres's default `max_connections=100`.

Mitigation: add **PgBouncer** in transaction-pooling mode between the backend and
Postgres. PgBouncer multiplexes hundreds of app-level connections onto a small set
of server connections with no application code changes required.

**pgvector index.** The `HNSW` index on `chunks.embedding` covers all tenants. At
100 tenants × 1,000 chunks each = 100,000 vectors, recall and build time remain
well within acceptable bounds for a shared index.

---

### Postgres at 1,000 tenants

**pgvector index size.** At 1,000 tenants × 5,000 chunks each = 5 million vectors,
the global HNSW index's memory footprint and query latency both increase. Three
options in order of operational complexity:

1. **Partial indexes per tenant** — create one HNSW index per tenant on a
   maintenance schedule. Works when active tenants are fewer than ~200 and chunk
   counts per tenant are modest. DDL can be generated from the tenant registry.

2. **Partitioning by `tenant_id`** — partition the `chunks` table by `tenant_id` and
   attach an HNSW index to each partition. The query planner prunes irrelevant
   partitions automatically; no application code changes needed.

3. **Separate schema per tenant** — strongest isolation; reserved for regulated
   industries where data co-tenancy is prohibited. Operationally expensive to
   manage migrations across hundreds of schemas.

**Read replicas.** The RAG workload (embedding lookup + cosine search) is read-heavy.
A streaming replica absorbs this traffic and frees the primary for writes (chunk
ingestion, lead capture, audit logs). The `async_sessionmaker` in `lifespan.py` can
route read-only sessions to the replica.

**Postgres connections.** PgBouncer remains the right answer. At 1,000 tenants the
multiplexing factor becomes critical — target `pool_mode = transaction` with fewer
than 50 server connections total, regardless of how many backend replicas are running.

---

### LLM rate limits at scale

Azure OpenAI deployments have per-deployment tokens-per-minute (TPM) and
requests-per-minute (RPM) limits. At 1,000 tenants with concurrent visitors, a
single deployment saturates.

Mitigation path in order of effort:

1. **Per-tenant rate limiting at the API layer** — a Redis counter caps LLM calls per
   tenant per minute before they reach the provider. Tenants that exceed their
   allocation receive a queued or degraded response, not an error.

2. **Multiple deployment slots** — rotate across several Azure deployments using a
   round-robin or least-latency policy in `infra/llm.py`. The adapter interface is
   already abstracted; adding a routing layer requires changes only in that file.

3. **Prompt caching** — identical system prompts (the tenant persona injected at
   runtime) are eligible for provider-side caching, reducing billable tokens per
   request proportionally to the prompt-to-completion ratio.

---

### Summary

| Component | 10 tenants | 100 tenants | 1,000 tenants |
|---|---|---|---|
| Backend replicas | 1–2 | 2–4 | 4–8 + autoscale |
| Postgres | Single instance | Single + PgBouncer | Primary + read replica + PgBouncer |
| pgvector index | Global HNSW | Global HNSW | Partial indexes or table partitioning |
| Redis | Single instance | Single instance | Redis Cluster |
| Object storage | Local MinIO | MinIO distributed | Amazon S3 |
| LLM | 1 deployment | 1–2 deployments | Multiple deployments + per-tenant rate limiting |
| Vault | Dev mode | Vault HA (Raft) | Vault HA (Raft) |
