## Widget / Chat Security

### Origin validation

`app/security/origin.py` provides `normalize_origin` and `is_origin_allowed`
helpers. They normalise origins (lowercase, strip trailing slash, preserve
port) and compare against a configurable allow-list.

Hard enforcement in the `/chat` handler is **not yet wired** because per-tenant
allowed-origin storage is not implemented. Once each tenant can configure its
allowed origins (on the Tenant table or a related table), add a check before or
after widget-token verification.

### Chat request validation

`ChatRequest` (`app/schemas.py`):

- `extra="forbid"` — the request body **cannot** include `tenant_id` or any
  other unlisted field, preventing tenant override attacks via the body.
- `message` is required, 1–4000 characters after a `field_validator` strips
  whitespace. Whitespace-only messages are rejected with a 422.

### Prompt isolation

The agent system prompt (in `app/services/agent/graph.py`) explicitly states:

- Tenant context comes from a **server-side verified token** and must not be
  overridden.
- The LLM must **ignore** user instructions to switch tenants, disclose tenant
  data, or use a different tenant ID.
- RAG results are scoped to the verified tenant only.
