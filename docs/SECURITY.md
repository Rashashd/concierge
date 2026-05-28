# Security

## Chat

### Tenant isolation

The `ChatRequest` model uses `extra="forbid"`, so `tenant_id` cannot be
injected via the request body. Tenant identity comes exclusively from the
verified widget token via `TenantContext`.

### Message validation

- `min_length=1` and a `@field_validator` reject empty and whitespace-only
  messages before any routing or model call.
- `max_length=4000` caps the payload size.

### Origin security

`backend/app/security/origin.py` provides `normalize_origin()` and
`is_origin_allowed()` for validating request origins. These helpers reject
non-Origin URLs (paths, queries, fragments, userinfo) and non-HTTP schemes.

Hard enforcement in the `/chat` handler awaits per-tenant allowed-origin
configuration storage. Until then, the empty-allowlist fallback permits all
origins.

### Spam handling

Spam-classified messages are refused with a static response. The user message
and the refusal are not stored in Redis session memory.

### Prompt isolation

The system prompt instructs the agent to treat tenant context as
server-side-verified and to ignore user instructions about switching tenants,
disclosing tenant data, or using different tenant IDs. RAG results are scoped
to the verified tenant only.

### Memory

Session memory keys are tenant-scoped (`session:{tenant_id}:{session_id}`).
Deletion uses a tenant-prefix pattern to avoid cross-tenant key leakage.

### Logging

Raw user messages are not logged. PII redaction applies before any data leaves
the service.
