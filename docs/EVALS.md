# Evals

## Baseline RAG Eval

We freeze baseline RAG metrics before adding hybrid search, reranking, query
rewriting, or parent-child retrieval. The baseline uses the current tenant-safe
pgvector RAG path with hosted embeddings and live Postgres/pgvector.

### Command

Start the local stack, apply migrations, seed Vault, then run from the backend
directory:

```bash
RAG_EVAL_DATABASE_URL=postgresql+asyncpg://concierge:CHANGE_ME@127.0.0.1:5432/concierge \
VAULT_ADDR=http://127.0.0.1:8200 \
VAULT_TOKEN=root-token-changeme \
uv run python ../ci/run_rag_golden.py
```

RAGAS is required for this eval. Missing Vault, database, LLM, embedding, or
RAGAS judge configuration should fail the run.

### Dataset

`ci/rag_golden.json` contains 15 synthetic examples across three tenants. Each
example has tenant fixture content, one question, an expected source marker, a
reference answer, and expected answer phrases.

### Metrics

| Metric | Definition |
|---|---|
| `retrieval_hit_at_5` | Expected source marker appears in one of the top 5 retrieved chunks. |
| `answer_contains_expected` | The generated answer contains all expected phrases for that example. |
| `cross_tenant_leak_count` | Count of retrieved chunks whose tenant differs from the question tenant. |
| `faithfulness` | RAGAS faithfulness score over answer and retrieved contexts. |
| `answer_relevancy` | RAGAS answer relevancy score for the question and answer. |

### Baseline Results

Status: pending live run after local Vault and Postgres are seeded with real LLM
credentials.

| Date | Retrieval hit@5 | Answer phrase pass | Cross-tenant leaks | RAGAS faithfulness | RAGAS answer relevancy | Notes |
|---|---:|---:|---:|---:|---:|---|
| Pending | - | - | - | - | - | Run `ci/run_rag_golden.py` after seeding Vault. |
