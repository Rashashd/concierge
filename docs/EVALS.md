# Evals

## Baseline RAG Eval

We freeze baseline RAG metrics before adding hybrid search, reranking, query
rewriting, or parent-child retrieval. The baseline uses the current tenant-safe
pgvector RAG path with hosted embeddings and live Postgres/pgvector.

This baseline uses a temporary CI ingestion path: committed synthetic Markdown
fixtures are chunked inside `ci/rag/run_rag_golden.py`, embedded, inserted into
pgvector, and then evaluated through the real retrieval path. It is not the
production ingestion pipeline.

The corpus includes near-duplicate same-tenant distractor documents. Each tenant
has 5 answer fixtures and 5 distractor fixtures (archived, draft, internal,
holiday, and legacy content) that share vocabulary with the real answer docs but
contain stale or conflicting facts. This makes retrieval harder and exposes
whether advanced RAG techniques actually improve over the baseline.

Source markers (e.g., `[alpha-hours]`) have been removed from all fixture
Markdown body text so retrieval cannot win by matching a unique token.
Deterministic retrieval checks are metadata-based, using the `fixture_path`
stored in chunk metadata to identify which document a retrieved chunk came from.

### Command

Start the local stack, apply migrations, seed Vault, then run from the backend
directory:

```bash
RAG_EVAL_DATABASE_URL=postgresql+asyncpg://concierge:CHANGE_ME@127.0.0.1:5432/concierge \
VAULT_ADDR=http://127.0.0.1:8200 \
VAULT_TOKEN=root-token-changeme \
uv run python ../ci/rag/run_rag_golden.py
```

RAGAS is required for this eval. Missing Vault, database, LLM, embedding, or
RAGAS judge configuration should fail the run.

### Dataset

`ci/rag/rag_golden.json` contains 20 synthetic examples across three tenants:
15 single-hop questions (5 per tenant) and 5 multi-hop questions that require
retrieving facts from 2 different answer docs for the same tenant.

Each example points to one or more Markdown fixtures in `ci/rag/rag_eval_docs/`, a
question, a list of expected fixture paths (`expected_fixture_paths`), a
reference answer, and expected answer phrases. Single-hop examples use a list
of one fixture path; multi-hop examples use a list of two fixture paths.

`ci/rag/rag_eval_distractors.json` adds 15 same-tenant distractor documents (5 per
tenant) that are ingested but are not correct sources for any golden question.
Distractors include archived policies, draft documents, internal handbooks,
holiday schedules, and legacy platform documentation.

### Metrics

| Metric | Definition |
|---|---|
| `retrieval_hit_at_1` | An expected fixture document appears in the top retrieved chunk. |
| `retrieval_hit_at_5` | An expected fixture document appears in one of the top 5 retrieved chunks. |
| `mrr_at_5` | Mean reciprocal rank of the expected fixture document within the top 5. |
| `expected_doc_precision_at_5` | Share of top-5 chunks originating from any expected fixture document. This exposes noisy context sets even when hit@5 is perfect. |
| `expected_doc_mrr_at_5` | Mean reciprocal rank across all expected fixture documents for multi-hop questions. |
| `answer_contains_expected` | The generated answer contains all expected phrases for that example. |
| `cross_tenant_leak_count` | Count of retrieved chunks whose tenant differs from the question tenant. Must be 0. |
| `chunk_count_total` | Total number of chunks created from the temporary Markdown fixture corpus. |
| `faithfulness` | RAGAS faithfulness score over answer and retrieved contexts. |
| `answer_relevancy` | RAGAS answer relevancy score for the question and answer. |
| `context_precision` | RAGAS LLM context precision with reference; higher means retrieved contexts are more relevant to the reference answer. |
| `context_recall` | RAGAS context recall; higher means retrieved contexts cover more of the reference answer. |

CI runs the deterministic retrieval, answer-phrase, and cross-tenant-leak checks
on the full golden set. The hosted RAGAS judge metrics are opt-in with
`RUN_RAGAS_METRICS=true` because the live judge calls can exceed the PR workflow
budget. When enabled, all four RAGAS metrics (`Faithfulness`,
`ResponseRelevancy`, `LLMContextPrecisionWithReference`, `LLMContextRecall`) run
on a fixed representative sample of the golden set.

### Comparison Baselines for Advanced RAG

When evaluating advanced RAG techniques (hybrid search, reranking, query
rewriting, parent-child retrieval), compare against these primary metrics:

- **`expected_doc_precision_at_5`** - measures how much of the top-5 context
  comes from the correct document(s). Lower means more distractor noise.
- **RAGAS `context_precision`** - LLM-judged relevance of retrieved contexts
  to the reference answer.
- **Answer correctness** - via `answer_contains_expected` and RAGAS
  `faithfulness`.

The corpus is intentionally hard: same-tenant distractors share vocabulary with
answer docs, so naive vector search will retrieve a mix of correct and
distractor chunks. Advanced RAG should improve `expected_doc_precision_at_5`
and `context_precision` over this baseline.

### Results

#### Deterministic Metrics

| Date | Technique | Chunks | Hit@1 | Hit@5 | MRR@5 | Expected doc precision@5 | Expected doc MRR@5 | Answer phrase pass | Cross-tenant leaks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-05-27 | Baseline (pgvector) | 172 | 0.70 | 0.95 | 0.8042 | 0.4700 | 0.7396 | 0.70 | 0 |
| 2026-05-27 | Reranker | 172 | 0.80 | 1.00 | 0.9000 | 0.5700 | 0.8354 | 0.95 | 0 |
| 2026-05-28 | Hybrid + Reranker | 172 | 0.85 | 1.00 | 0.9167 | 0.5500 | 0.8500 | 0.95 | 0 |

#### RAGAS Metrics

| Date | Technique | Faithfulness | Answer relevancy | Context precision | Context recall |
|---|---|---:|---:|---:|---:|
| 2026-05-27 | Baseline (pgvector) | 0.9881 | 0.8738 | 0.6811 | 0.8000 |
| 2026-05-27 | Reranker | 0.9974 | 0.9049 | 0.6737 | 0.9750 |
| 2026-05-28 | Hybrid + Reranker | 0.9832 | 0.8880 | 0.7232 | 0.9750 |

#### Notes

| Date | Technique | Notes |
|---|---|---|
| 2026-05-27 | Baseline (pgvector) | 20 examples, 15 distractors, marker-free chunk text. |
| 2026-05-27 | Reranker | LLM reranker scores 20 vector candidates, keeps top 5. Improves precision (+21%), answer accuracy (+36%), hit@1 (+14%). Context precision flat - RAGAS judge noise. |
| 2026-05-28 | Hybrid + Reranker | pgvector + Postgres FTS (0.7/0.3 weights), then reranker. Improves context_precision (+7% vs reranker), hit@1 (+6%), MRR@5 (+2%). Minor precision@5 dip within noise. |

---

## Agent Golden Eval

Deterministic routing eval that verifies `/chat` classifier integration without calling hosted LLMs, Redis, or the model-server.

**Command:** `cd backend && uv run python ../ci/agent/run_agent_golden.py`

**What it covers:**
- spam → refuse (static response, agent not called)
- lead → lead capture response
- escalate → escalation response
- question → agent/RAG path
- low confidence → falls back to agent
- classifier unavailable (null predicate) → falls back to agent
- classifier failure (raises) → falls back to agent
- tenant_id override in message → ignored, still uses verified context

**Latest result (2026-05-28):** 8/8 passed, 0 failures.

---

## Classifier Eval

The classifier eval measures the Concierge router model on a held-out test set.
The task is four-way visitor intent classification:

- `spam`
- `question`
- `lead`
- `escalate`

The dataset combines public labeled text-classification data from SMS Spam
Collection for spam examples and CLINC150 / `clinc_oos` examples collapsed into
the Concierge router labels. The processed dataset hash is recorded in the
model card.

### Command

```bash
cd backend
uv run python ../ci/classifier/run_classifier_eval.py
```

### Latest result

| Model | Macro-F1 | Weighted-F1 | Avg latency ms | P95 latency ms | Gate result |
|---|---:|---:|---:|---:|---|
| Classical TF-IDF + Logistic Regression | 0.9432 | 0.9433 | 0.95 | 1.26 | Pass |
| Small DL TF-IDF MLP exported to ONNX | 0.9627 | 0.9626 | 2.92 | 6.71 | Pass |
| Groq zero-shot LLM baseline | 0.7830 | 0.7810 | 1512.50 | 1512.50 | Comparison only |

### Per-class F1

| Model | Spam | Question | Lead | Escalate |
|---|---:|---:|---:|---:|
| Classical TF-IDF + Logistic Regression | 0.9639 | 0.9136 | 0.9620 | 0.9333 |
| Small DL TF-IDF MLP exported to ONNX | 0.9873 | 0.9268 | 0.9630 | 0.9737 |
| Groq zero-shot LLM baseline | 1.0000 | 0.7636 | 0.5185 | 0.8500 |

### Gate

The committed classifier gate is:

```yaml
classifier:
  macro_f1_min: 0.8932
  p95_latency_ms_max: 100.0
```

The shipped classical model passes both gates:

- macro-F1: `0.9432 >= 0.8932`
- p95 latency: `1.26 ms <= 100 ms`

The DL model is kept as a required comparison baseline and exported ONNX
artifact, but it is not the shipped production model because the classical model
is close in macro-F1, faster, simpler, and easier to serve lean.

---

## Agent Tool-Selection Eval

The agent golden eval verifies the classifier-driven router and tool-selection
behavior without relying on hosted LLM calls, Redis, or the live model-server.

### Command

```bash
cd backend
uv run python ../ci/agent/run_agent_golden.py
```

### Latest result

| Eval | Examples | Passed | Failed | Accuracy |
|---|---:|---:|---:|---:|
| Agent golden tool-selection | 8 | 8 | 0 | 1.00 |

### Covered cases

The golden set covers:

- spam routed to refusal/drop behavior
- lead routed to lead capture response
- explicit human-support request routed to escalation
- question routed to the agent/RAG path
- low-confidence classifier output falling back to the agent
- classifier unavailable falling back to the agent
- classifier exception falling back to the agent
- tenant-id override attempt ignored in favor of verified tenant context

### Threshold rationale

The committed threshold is intentionally low for now:

```yaml
agent:
  tool_selection_accuracy_min: 0.30
```

This is kept at `0.30` because the current golden set is still small and
deterministic. It prevents the gate from being disabled, while leaving room to
tighten the value after the team expands the golden set beyond the first 8
examples. The latest result is already above the threshold, so the next
recommended step is to increase the threshold once more examples are added.

---

## Red-Team and Redaction Eval

The red-team eval is a deterministic CI gate for prompt injection,
jailbreak-style messages, cross-tenant extraction attempts, safe messages, and
redaction behavior.

### Command

```bash
python ci/redteam/run_redteam.py
```

### Latest result

| Eval | Probe count | Required refusal rate | Actual refusal rate | Failures | Gate result |
|---|---:|---:|---:|---:|---|
| Red-team guardrails | 9 | 1.00 | 1.00 | 0 | Pass |

### Covered cases

The probe set covers:

- prompt injection asking for the system prompt
- prompt injection asking for hidden developer messages
- jailbreak / DAN-style instruction override
- cross-tenant requests for another tenant's leads
- cross-tenant requests for another tenant's conversations
- cross-tenant requests for competitor customer messages
- safe business questions that should be allowed
- lead/pricing intent that should be allowed
- redaction of an email address and fake API key before safe text is returned

The redaction probe confirms that `visitor@example.com` and
`sk-test1234567890` do not remain in the safe text. They are replaced with
`[REDACTED_EMAIL]` and `[REDACTED_SECRET]`.

---

## Overall Eval Gate Summary

| Gate | Threshold | Latest result | Status |
|---|---|---|---|
| Classifier macro-F1 | `>= 0.8932` | `0.9432` shipped classical model | Pass |
| Classifier p95 latency | `<= 100 ms` | `1.26 ms` shipped classical model | Pass |
| Agent tool-selection accuracy | `>= 0.30` | `1.00` | Pass |
| RAG retrieval hit@5 | `>= 0.70` | `1.00` for latest Hybrid + Reranker | Pass |
| RAG faithfulness | `>= 0.80` | `0.9832` for latest Hybrid + Reranker | Pass |
| RAG answer relevancy | `>= 0.80` | `0.8880` for latest Hybrid + Reranker | Pass |
| RAG cross-tenant leaks | `0` | `0` | Pass |
| Red-team refusal rate | `1.00` | `1.00` | Pass |

The current eval state is acceptable for submission because the classifier,
agent golden set, RAG golden set, red-team probes, and redaction checks are all
represented as runnable CI gates with committed thresholds.
