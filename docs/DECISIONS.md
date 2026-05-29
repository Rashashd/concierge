# Decisions

## Baseline RAG Before Advanced Retrieval

Decision: measure baseline pgvector RAG before adding hybrid search, reranking,
query rewriting, or parent-child chunking.

Reason: advanced RAG should be justified by metric deltas, not by intuition. The
baseline eval uses the current tenant-scoped pgvector path, 15 synthetic golden
examples, deterministic retrieval/answer checks, and required RAGAS
faithfulness/answer relevancy. Future advanced RAG changes must rerun the same
golden eval and compare against the baseline table in `docs/EVALS.md`.

## Advanced RAG Choices

After establishing the pgvector baseline, two advanced techniques were
implemented and evaluated. The shared evaluation methodology and results are
recorded in `docs/EVALS.md`.

### LLM Reranker

The first enhancement was an LLM reranker: pgvector dense retrieval fetches 20
vector candidates, and the LLM reranker scores them to keep the top 5. The
reranker improved hit@1 (+14 %), expected doc precision@5 (+21 %), and answer
phrase pass rate (+36 %).

### Hybrid Search

The second enhancement combined pgvector dense retrieval with Postgres
full-text search (FTS). The hybrid retriever merges vector and keyword
candidates, normalizes both scores, and combines them with configurable weights
(default 0.7 vector, 0.3 keyword) and independent candidate counts per source.
This improves context_precision (+7 % over reranker-only) by surfacing keyword
matches that pure vector search misses.

### Metadata Filtering — Intentionally Skipped

Metadata filtering was deferred because tenant-specific metadata fields are not
yet standardized or stable across tenants. Once metadata conventions solidify,
filters should only use reliable system metadata such as:

- `published` / `draft` / `archived`
- `public` / `internal`
- `content_type`
- `updated_at`

### Evaluation Comparison

Cross-technique comparison uses these primary metrics (all in
`docs/EVALS.md`):

- `expected_doc_precision_at_5` — share of top-5 chunks from correct documents
- `expected_doc_mrr_at_5` — mean reciprocal rank for multi-hop documents
- `hit@1` — correct document appears in the top-1 chunk
- `context_precision` — RAGAS LLM-judged relevance to reference answer
- `answer correctness` — via `answer_contains_expected` and RAGAS `faithfulness`
- `cross_tenant_leak_count` — must be 0

Tenant isolation is enforced at every layer: verified tenant context, repository
tenant filters, RLS, and the RAG retrievers' tenant-scoped queries.

## Conversation Surface Design

Decision: keep the visitor conversation path as a bounded LangGraph agent loop
behind `/chat`, with tool-visible inputs limited to business arguments and all
tenant scoping injected server-side.

Reason: the graded failure mode in this project is cross-tenant leakage. The
agent can choose tools such as `rag_search`, `capture_lead`, and `escalate`,
but it never receives or supplies `tenant_id` as an argument. Verified tenant
context enters once through the widget token dependency, then the backend
injects tenant context and DB session into the agent state. This keeps the LLM
out of the trust boundary while preserving flexible tool selection.

Decision: load the system prompt from versioned prompt files under
`backend/app/prompts/v1/` instead of leaving the chat behavior hardcoded in the
route or graph function.

Reason: prompt behavior is part of the application contract and needs to be
reviewable, testable, and versioned like code. Moving the prompt into
`prompts/v1/system.md` made the agent behavior explicit and easier to evolve
without burying critical isolation text inside Python control flow.

## Redis Memory Design

Decision: store chat memory in Redis with tenant-scoped keys using the pattern
`session:{tenant_id}:{session_id}`.

Reason: Redis memory improves chat continuity, but it is also a possible
cross-tenant leak point if keys are not tenant-scoped. The chosen key format
lets the backend load and save history per visitor session while making tenant
erasure straightforward through a tenant-prefix scan. The design intentionally
keeps `tenant_id` in the key itself rather than relying on implicit separation.

Decision: save redacted user input and final guarded assistant output to memory,
not raw input or pre-guardrail output.

Reason: memory is persistent application state. Once guardrails and redaction
were added to `/chat`, storing anything earlier in the pipeline would preserve
content that the final runtime path had already decided to sanitize or refuse.

## Guardrails Placement

Decision: apply guardrails in the backend conversation flow as:
origin check -> redaction -> input guardrails -> memory/classifier/agent ->
output guardrails -> memory save.

Reason: this order gives each layer a clear job. Origin enforcement happens
before any expensive work. Redaction happens before anything leaves the service.
Input guardrails can refuse unsafe requests before classifier or LLM execution.
Output guardrails get the last word before the response is returned or written
to memory.

Decision: treat guardrails as defense-in-depth, not as the tenant isolation
boundary.

Reason: deterministic guardrails and NeMo checks reduce prompt-injection,
jailbreak, and cross-tenant probing risk, but the hard isolation guarantees
must still come from verified tenant context, repository tenant filters, RLS,
and tenant-scoped storage. If the guardrails sidecar is unavailable, the system
continues with warnings rather than pretending the guardrail layer is a hard
auth boundary.

Decision: enforce service-to-service guardrails auth with a shared service token
and sanitize input before forwarding it to NeMo.

Reason: an unauthenticated sidecar is too weak for a production-shaped
deployment, and raw user input should not be forwarded to a secondary LLM if a
deterministic sanitization step has already removed secrets or PII. The backend
now applies guardrail `safe_text` downstream, and the sidecar runs NeMo checks
against sanitized text rather than raw input.

## Token Cost Attribution

Decision: record per-turn token usage from LangChain `AIMessage.usage_metadata`
instead of estimating tokens manually or calculating dollar cost in the request
path.

Reason: usage metadata is the provider-reported number and is already attached
to each AI response in the LangGraph turn. Summing `input_tokens`,
`output_tokens`, and `total_tokens` across all AI messages in the turn gives a
stable per-tenant usage record even when the turn contains multiple LLM calls.
We intentionally store token counts, not money, because pricing policy is a
separate business concern and changes more often than raw token accounting.
