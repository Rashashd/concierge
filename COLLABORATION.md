# Collaboration

## Team ownership

The team split the work into three vertical slices so that each person owned a
complete part of the product instead of only one technical layer.

| Person | Slice | Main ownership |
|---|---|---|
| Racha | Platform foundation | tenancy, database, RLS, auth, provisioning, Vault, erasure, CI skeleton |
| Hadi | Conversation surface | hosted LLM adapter, classifier router, LangGraph agent, RAG, memory, widget |
| Hussein | Models and safety | classifier training/eval, model-server, guardrails, red-team evals, admin/supporting docs |

## Hussein contribution report

Hussein owned the models and safety slice of the Concierge project. His work
focused on the trained classifier, the lean model-server, the guardrails
sidecar, the red-team checks, and the documentation needed to defend those
decisions.

### Model and classifier work

Hussein prepared the classifier work for the Concierge router. The classifier
predicts one of four visitor intents: `spam`, `question`, `lead`, or
`escalate`. These labels are used by the router to decide whether to drop spam,
answer through RAG, capture a lead, escalate to a human, or fall back to the
bounded agent.

The classifier work compared three approaches:

- a classical TF-IDF + Logistic Regression model
- a small DL TF-IDF MLP exported to ONNX
- a hosted-API LLM zero-shot baseline through Groq

The final documented results were:

| Model | Macro-F1 | Weighted-F1 | Avg latency ms | P95 latency ms |
|---|---:|---:|---:|---:|
| Classical TF-IDF + Logistic Regression | 0.9432 | 0.9433 | 0.95 | 1.26 |
| Small DL TF-IDF MLP exported to ONNX | 0.9627 | 0.9626 | 2.92 | 6.71 |
| Groq zero-shot LLM baseline | 0.7830 | 0.7810 | 1512.50 | 1512.50 |

Although the DL model had the highest macro-F1, Hussein documented the decision
to ship the classical model because it is very close in quality, faster,
simpler, cheaper, and easier to serve in the lean model-server without adding
PyTorch, TensorFlow, or transformers to the service containers.

### Model-server work

Hussein contributed the lean `model-server` service. The model-server exposes
the classifier behind HTTP instead of importing the model directly into the
backend. This keeps the classifier as a separate service boundary and matches
the project requirement that the trained model is served lean.

The model-server uses:

- `sklearn/joblib` for the shipped classical model
- `onnxruntime` for the DL/ONNX artifact
- artifact metadata and hashes recorded in the model card
- FastAPI endpoints for health checks and prediction

This keeps training-heavy dependencies out of production containers while still
showing that both ML and DL artifacts were produced and evaluated.

### Guardrails and red-team work

Hussein also worked on the guardrails and safety side. The guardrails sidecar
contains deterministic policy checks for prompt injection, jailbreak attempts,
cross-tenant data requests, and redaction behavior.

The red-team eval covers 9 probes:

- prompt injection attempts
- jailbreak-style override attempts
- cross-tenant data extraction attempts
- safe messages that should be allowed
- redaction of an email address and a fake API key

The latest red-team result passes with:

- required refusal rate: `1.00`
- actual refusal rate: `1.00`
- failures: `0`

This supports the project's main safety requirement: a visitor from one tenant
must not be able to extract another tenant's data or system instructions.

### Eval and documentation work

Hussein updated the evaluation and decision documentation for his slice. This
included:

- documenting the ML vs DL vs LLM comparison in `docs/DECISIONS.md`
- documenting classifier results, latency, per-class F1, and shipping rationale
- adding the classifier, agent, RAG, red-team, and redaction summaries to
  `docs/EVALS.md`
- keeping `ci/eval_thresholds.yaml` aligned with the current gates
- explaining why `tool_selection_accuracy_min` remains at `0.30` until the
  golden set is expanded

### Coordination notes

Hussein's slice connected with the rest of the team in these places:

- Hadi's classifier router depends on the model-server prediction contract.
- Racha's service-to-service authentication and Vault setup provide the service
  credential pattern used when the backend calls the model-server and guardrails
  sidecar.
- The red-team and redaction gates support the shared tenant-isolation story.
- The documentation in `DECISIONS.md` and `EVALS.md` gives the team numbers to
  defend during the final demo.

## Team disagreement and resolution

One team discussion was whether to ship the DL model because it achieved the
highest macro-F1, or ship the classical model because it was simpler and faster.
The team resolved this by choosing the classical model for production and
keeping the DL model as a documented ONNX comparison artifact. This decision
keeps the production container lean while still satisfying the requirement to
train and compare ML, DL, and LLM approaches.

## Blockers and risks

| Risk | Resolution |
|---|---|
| DL export could add heavy dependencies to production | Training stays in the notebook; serving uses ONNX Runtime only |
| LLM baseline is slow and provider-priced | Use it only as a comparison baseline, not as the default router |
| Tool-selection threshold is low | Keep `0.30` temporarily, document the reason, and tighten after expanding the golden set |
| Guardrails could be mistaken for the isolation boundary | Document that hard isolation comes from verified tenant context, repository filters, RLS, and tenant-scoped storage |
