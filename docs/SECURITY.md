# Security

## Chat security flow

The `/chat` handler executes these steps in order:

1. **Tenant context** is loaded from the verified widget JWT by
   `get_current_tenant`. `tenant_id` comes only from the token — never from the
   request body, headers, or query params.

2. **Tenant record** is fetched server-side from the DB via
   `tenant_repo.get_by_id(session, tenant_context.tenant_id)`. The caller cannot
   influence which tenant record is loaded.

3. **Origin check** — the `Origin` request header is validated against
   `tenant.allowed_origins`. See [Origin enforcement](#origin-enforcement).

4. **Message redaction** — `redactor.redact(request.message)` strips PII before
   the message reaches any downstream component. See
   [Message redaction](#message-redaction).

5. **Input guardrails** — `guardrails.check_input()` evaluates the redacted
   message against the tenant's guardrail config. If the decision is `refuse`,
   the handler returns immediately with the guardrail reason. No LLM call,
   classifier call, memory load, or memory save happens.

6. **Memory load** — if input passes guardrails, tenant-scoped Redis history is
   loaded via `load_history` using the key pattern
   `session:{tenant_id}:{session_id}`.

7. **Classifier routing** — the classifier (if available) predicts a label and
   route hint. The router maps this to one of four actions:
   - `refuse` — returns a static spam rejection (no memory saved)
   - `lead` — returns a lead-capture prompt
   - `escalate` — returns a human-escalation message
   - `agent` — runs the RAG agent

   If the classifier is unavailable or fails, the system falls back to the
   agent path.

8. **Agent / RAG** — the agent uses server-side tenant context only. The system
   prompt instructs it to ignore user instructions about switching tenants or
   disclosing tenant data. RAG retrieval is scoped to the verified tenant at
   the repository and RLS layers.

9. **Output guardrails** — `guardrails.check_output()` evaluates the answer
   before it is returned. If `safe_text` is present and the decision is
   `allow`, the safe version replaces the answer. If the decision is `refuse`,
   a generic refusal message replaces the answer.

10. **Memory save** — if the route action is not `refuse`, the redacted user
    message and the final guarded assistant answer are saved to Redis. Spam and
    refuse routes are never stored.

## Tenant isolation

- `ChatRequest` uses `extra="forbid"` — `tenant_id` cannot be injected via the
  request body.
- `tenant_id` comes exclusively from the verified widget token via
  `TenantContext`. No request body field, header, or query parameter can
  override it.
- The system prompt instructs the agent to treat tenant context as
  server-side-verified and to ignore user instructions about switching tenants,
  disclosing tenant data, or using a different tenant ID.
- RAG retrieval applies tenant filters at both the repository layer and
  PostgreSQL RLS layer.
- MinIO objects are stored under `tenants/{tenant_id}/` prefixes.
- Redis session keys follow the pattern `session:{tenant_id}:{session_id}`.
  Deletion uses a tenant-prefix scan to avoid cross-tenant key leakage.

## Message validation

- `min_length=1` and a `@field_validator` reject empty and whitespace-only
  messages before any routing or model call.
- `max_length=4000` caps the payload size.
- `ChatRequest` uses `extra="forbid"` to reject unknown fields.

## Origin enforcement

`backend/app/security/origin.py` provides `normalize_origin()` and
`is_origin_allowed()`. The `/chat` handler checks the `Origin` request header
against `tenant.allowed_origins` before any downstream processing.

`normalize_origin()` rejects non-Origin URLs: paths beyond `/`, queries,
fragments, userinfo, params, and non-HTTP schemes.

**When `allowed_origins` is non-empty:**

| Scenario | Result |
|---|---|
| Matching origin | Allowed |
| Missing `Origin` header | 403 |
| Origin with path (`/some/path`) | 403 (rejected by `normalize_origin`) |
| Non-matching origin | 403 |
| Invalid origin syntax | 403 |

**When `allowed_origins` is empty (current default):** all origins are
permitted. **This is temporary.** Once every tenant has configured allowed
origins, the empty-list fallback will be removed.

Origin checks are defense-in-depth and are not a replacement for token
authentication. The widget JWT remains the primary identity boundary.

## Message redaction

`backend/app/security/redaction.py` uses Microsoft Presidio with a spaCy NLP
pipeline to detect and replace PII in user messages. The `Redactor.redact()`
method replaces detected entities with `[REDACTED_<TYPE>]` tokens and returns
the text unchanged if no PII is found.

The redacted message is used at every downstream touchpoint:

- Guardrails input check
- Classifier `predict()` call
- Agent/LLM user message
- Redis memory user turn

The raw (unredacted) message never reaches the LLM, classifier, or persistent
storage.

## Guardrails

`backend/app/infra/guardrails.py` is an async HTTP client for the NeMo
Guardrails sidecar. It exposes:

- `check_input(tenant_id, message, tenant_config)` — evaluates the visitor
  message before routing.
- `check_output(tenant_id, message, tenant_config)` — evaluates the assistant
  answer before returning it.

Each returns a `GuardrailResponse` with:

| Field | Type | Description |
|---|---|---|
| `decision` | `"allow"` or `"refuse"` | Whether to proceed |
| `reason` | `str` or `None` | Reason for refusal (used as response text) |
| `safe_text` | `str` or `None` | Sanitized version when `decision="allow"` |
| `triggered_rules` | `list[str]` | Names of rules that fired |

**Input refusal** returns immediately with the guardrail reason. No LLM call,
classifier call, history load, or memory save occurs.

**Output refusal** replaces the assistant answer with a static refusal message.
The generic refusal is saved to Redis memory, not the original unsafe answer.

**Output sanitization** (`safe_text` with `decision="allow"`) replaces the
answer with the guardrails-sanitized version before returning it and before
saving to memory.

Guardrails failures (sidecar unavailable, timeout) are logged as warnings and
do not block the request — the unmodified message or answer proceeds through
the pipeline.

## Logging

Raw user messages are not logged. PII redaction applies before any data leaves
the service.

## Intentionally not solved yet

- **Empty `allowed_origins=[]` is a temporary allow-all.** Every tenant will
  eventually configure its own allowed origins, and the empty-list fallback
  will be removed.
- **Origin checks are not a replacement for auth/token verification.** The
  widget JWT is the primary identity boundary. Origin validation is an
  additional layer for embedded-widget scenarios.
- **Guardrails are defense-in-depth, not the tenant isolation boundary.**
  Guardrail rules can be bypassed by a sidecar failure. The isolation
  guarantees come from RLS, repository filters, token verification, and
  tenant-scoped storage.
- **Classifier failures fall back to the agent path by design.** An
  unavailable classifier does not block the conversation — the message is
  routed to the full RAG agent. This trades precision for availability in
  the face of model-server disruptions.
