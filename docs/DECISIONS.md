# Decisions

## Baseline RAG Before Advanced Retrieval

Decision: measure baseline pgvector RAG before adding hybrid search, reranking,
query rewriting, or parent-child chunking.

Reason: advanced RAG should be justified by metric deltas, not by intuition. The
baseline eval uses the current tenant-scoped pgvector path, 15 synthetic golden
examples, deterministic retrieval/answer checks, and required RAGAS
faithfulness/answer relevancy. Future advanced RAG changes must rerun the same
golden eval and compare against the baseline table in `docs/EVALS.md`.
