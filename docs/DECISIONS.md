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
full-text search (FTS). The hybrid retriever uses reciprocal-rank fusion with
configurable weights (default 0.7 vector, 0.3 keyword) and independent
candidate counts per source. This avoids dense-score dominance and improves
context_precision (+7 % over reranker-only) by surfacing keyword matches that
pure vector search misses.

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
