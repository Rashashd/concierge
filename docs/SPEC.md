# SPEC.md — Concierge

Written before service code. These are the contracts the whole team builds against.
If something here needs to change, discuss and update this file first — then update the code.

---

## 1. Tenant ID Convention

- Type: `UUID v4`
- Column name: `tenant_id` — identical everywhere, no aliases
- Source: always from the **verified token** in request context. Never from the request body, headers, or query params. Trusting a caller-supplied `tenant_id` is a one-line cross-tenant breach.
- Tenant Manager users have `tenant_id = NULL` in the users table. They are excluded from tenant-scoped RLS by the application layer — not by an RLS bypass.

---

## 2. Database Schema

### RLS Pattern (applies to every tenant-scoped table)

Set once per request inside the `get_session` dependency, before any query runs:

```sql
SELECT set_config('app.tenant_id', :tenant_id, true);
-- The `true` flag makes this transaction-local. It auto-clears on commit/rollback.
-- Pooled connections never carry a previous tenant's value to the next request.
```

Policy applied to every tenant-scoped table:

```sql
CREATE POLICY tenant_isolation ON <table>
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
```

Every new table that carries `tenant_id` must include its RLS policy in the **same Alembic migration** that creates the table. No exceptions.

---

### `tenants`

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` |
| `name` | `VARCHAR(255)` | NOT NULL |
| `slug` | `VARCHAR(100)` | UNIQUE NOT NULL — URL-safe identifier |
| `is_active` | `BOOLEAN` | NOT NULL DEFAULT `true` |
| `llm_persona` | `TEXT` | NOT NULL DEFAULT `''` — injected into system prompt at runtime |
| `guardrail_config` | `JSONB` | NOT NULL DEFAULT `'{}'` — tenant-editable rails (topics, tone, enabled tools) |
| `allowed_origins` | `TEXT[]` | NOT NULL DEFAULT `'{}'` — drives CORS + CSP frame-ancestors |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |
| `suspended_at` | `TIMESTAMPTZ` | NULL |

No RLS on `tenants` itself — access enforced at the repository layer.

---

### `users`

Managed by `fastapi-users`. Extended with:

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK |
| `email` | `VARCHAR(320)` | UNIQUE NOT NULL |
| `hashed_password` | `TEXT` | NOT NULL |
| `role` | `VARCHAR(50)` | NOT NULL — see Role Model below |
| `tenant_id` | `UUID` | NULL REFERENCES `tenants(id)` — NULL for `tenant_manager` |
| `is_active` | `BOOLEAN` | NOT NULL DEFAULT `true` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |

No RLS on `users` — access enforced at the repository layer.

---

### `content_items`

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` |
| `tenant_id` | `UUID` | NOT NULL REFERENCES `tenants(id)` |
| `title` | `TEXT` | NOT NULL |
| `body` | `TEXT` | NOT NULL |
| `content_type` | `VARCHAR(50)` | NOT NULL — `'page'` \| `'faq'` \| `'product'` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |

RLS: `tenant_id = current_setting('app.tenant_id', true)::uuid`

---

### `chunks` (pgvector)

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` |
| `tenant_id` | `UUID` | NOT NULL REFERENCES `tenants(id)` |
| `content_item_id` | `UUID` | NOT NULL REFERENCES `content_items(id)` |
| `chunk_index` | `INTEGER` | NOT NULL — position within the source item |
| `text` | `TEXT` | NOT NULL |
| `embedding` | `VECTOR(1536)` | NOT NULL — `text-embedding-3-small` dimensions |
| `metadata` | `JSONB` | NOT NULL DEFAULT `'{}'` — for metadata filtering improvement |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |

RLS: `tenant_id = current_setting('app.tenant_id', true)::uuid`

Retrieval queries must also include `.filter(Chunk.tenant_id == tenant_id)` at the repository layer — belt and suspenders.

---

### `leads`

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` |
| `tenant_id` | `UUID` | NOT NULL REFERENCES `tenants(id)` |
| `session_id` | `VARCHAR(255)` | NOT NULL — for rate-limiting writes per visitor |
| `visitor_name` | `VARCHAR(255)` | NULL |
| `contact` | `VARCHAR(320)` | NOT NULL — email or phone |
| `intent` | `TEXT` | NOT NULL |
| `status` | `VARCHAR(50)` | NOT NULL DEFAULT `'new'` — `'new'` \| `'reviewed'` \| `'contacted'` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |

RLS: `tenant_id = current_setting('app.tenant_id', true)::uuid`

---

### `widget_configs`

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` |
| `tenant_id` | `UUID` | NOT NULL REFERENCES `tenants(id)` |
| `widget_id` | `UUID` | UNIQUE NOT NULL DEFAULT `gen_random_uuid()` — public-facing ID in the loader script |
| `greeting` | `TEXT` | NOT NULL DEFAULT `'Hi, how can I help you?'` |
| `theme_color` | `VARCHAR(7)` | NOT NULL DEFAULT `'#0066CC'` |
| `enabled_tools` | `TEXT[]` | NOT NULL DEFAULT `'{rag_search,capture_lead,escalate}'` |
| `is_active` | `BOOLEAN` | NOT NULL DEFAULT `true` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |

RLS: `tenant_id = current_setting('app.tenant_id', true)::uuid`

---

### `audit_logs`

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` |
| `actor_id` | `UUID` | NOT NULL — user who triggered the action |
| `actor_role` | `VARCHAR(50)` | NOT NULL |
| `tenant_id` | `UUID` | NULL — NULL for platform-level actions |
| `action` | `VARCHAR(100)` | NOT NULL — e.g. `'tenant.created'`, `'tenant.erased'`, `'lead.captured'`, `'conversation.escalated'` |
| `payload` | `JSONB` | NOT NULL DEFAULT `'{}'` — redacted before insert, no PII |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` |

No RLS — readable only by `tenant_manager`, enforced at the repository layer.

---

## 3. Role Model

Three roles, two levels. No configurable permission matrix — these are fixed.

| Action | `tenant_manager` | `tenant_admin` | `member` / visitor |
|---|---|---|---|
| Provision a new tenant | ✅ | ❌ | ❌ |
| Suspend / reactivate a tenant | ✅ | ❌ | ❌ |
| Trigger tenant erasure | ✅ | ❌ | ❌ |
| Read aggregate cost / usage | ✅ | ❌ | ❌ |
| Read any tenant's content, leads, or conversations | ❌ | ❌ | ❌ |
| Manage own tenant's CMS content | ❌ | ✅ | ❌ |
| Configure agent persona and guardrail rails | ❌ | ✅ | ❌ |
| View own tenant's leads | ❌ | ✅ | ❌ |
| Create and configure widgets | ❌ | ✅ | ❌ |
| Get embed snippet | ❌ | ✅ | ❌ |
| Chat with the agent | ❌ | ❌ | ✅ |
| Submit a lead via `capture_lead` | ❌ | ❌ | ✅ |

**Key constraints:**
- The Tenant Manager cannot read tenant content. It provisions, suspends, and erases — it never reads conversations, leads, or CMS body. Erasure runs through a write/delete-only maintenance path.
- `401` — missing or invalid token. `403` — valid token, insufficient role. Never `200` with `{"error": ...}`.

---

## 4. Tool Contracts

All three tools are called by the LangGraph agent. They return structured output on success or a `ToolError` on failure — they never raise an exception into the agent loop.

### Shared error type

```python
class ToolError(BaseModel):
    tool: str      # name of the tool that failed
    code: str      # machine-readable reason — see per-tool list below
    message: str   # human-readable explanation for the agent to act on
```

---

### `rag_search`

Retrieve relevant chunks from the tenant's CMS content and return a synthesized answer.

```python
class RAGSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    # tenant_id injected from request context — never supplied by the caller

class ChunkReference(BaseModel):
    chunk_id: UUID
    content_item_id: UUID
    text: str
    score: float        # cosine similarity score

class RAGSearchOutput(BaseModel):
    answer: str
    source_chunks: list[ChunkReference]
```

Error codes: `retrieval_failed` | `embedding_failed` | `no_chunks_found`

Side effects: none — read only.

---

### `capture_lead`

Write a visitor's contact details and intent to the tenant's leads table.

```python
class CaptureLeadInput(BaseModel):
    visitor_name: str | None = Field(default=None, max_length=255)
    contact: str = Field(..., max_length=320)    # email or phone number
    intent: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(..., max_length=255) # used for rate-limiting

class CaptureLeadOutput(BaseModel):
    lead_id: UUID
    status: Literal["captured", "duplicate"]
```

Error codes: `rate_limited` | `validation_error` | `write_failed`

Side effects: writes one row to `leads`. `tenant_id` comes from the verified token — the agent cannot supply or override it. Rate limit: max 3 writes per `session_id` per hour, enforced at the repository layer before insert.

---

### `escalate`

Flag the conversation for human follow-up.

```python
class EscalateInput(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
    conversation_id: str = Field(..., max_length=255)

class EscalateOutput(BaseModel):
    ticket_id: UUID
    status: Literal["escalated"]
    visitor_message: str    # what the agent should relay to the visitor
```

Error codes: `already_escalated` | `write_failed`

Side effects: writes one row to `audit_logs` with `action = 'conversation.escalated'`.

---

## 5. Eval Thresholds

Committed in `ci/eval_thresholds.yaml`. Values below are placeholders — tighten as real numbers land during the week. Lowering a threshold requires a one-line justification in `docs/DECISIONS.md`.

| CI gate | Metric | Placeholder threshold | Notes |
|---|---|---|---|
| Classifier | macro-F1 on held-out test | ≥ 0.75 | Tighten after first training run |
| Agent tool-selection | correct tool out of 15 examples | ≥ 13 / 15 | Two misses allowed |
| RAG retrieval | hit@5 on 15 triples | ≥ 0.70 | |
| RAG generation | faithfulness (RAGAS) | ≥ 0.80 | |
| Red-team | injection + cross-tenant probes refused | 100% | Non-negotiable — any failure blocks merge |
| Redaction | fake API key never appears unredacted | 100% | Non-negotiable |
