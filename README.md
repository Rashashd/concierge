# Concierge

Concierge is a multi-tenant AI SaaS where any business signs up, manages content in a CMS, and embeds a branded chat assistant on its public site. The core requirement is isolation: a visitor on Tenant A must never see Tenant B's data.

## What it does

- Verifies tenant identity from a signed widget JWT — `tenant_id` never comes from the request body
- Retrieves only from the current tenant's content via pgvector with RLS as a second enforcement layer
- Captures leads and escalates conversations to humans through structured agent tools
- Redacts PII before the message reaches the LLM, classifier, guardrails, or memory
- Ships with evals for RAG quality, routing accuracy, red-team refusal rate, and cross-tenant isolation

## Stack

FastAPI · PostgreSQL + pgvector · Redis · MinIO · HashiCorp Vault · LangGraph · Azure OpenAI · Presidio · NeMo Guardrails · Streamlit · TF-IDF + Logistic Regression classifier · ONNX Runtime

## Services

| Directory | What it is |
|---|---|
| `backend/` | Main API: auth, tenants, RAG, chat, content, leads, widget |
| `model-server/` | Lightweight classifier service (sklearn + ONNX Runtime) |
| `guardrails/` | NeMo Guardrails sidecar for input/output safety checks |
| `streamlit/` | Streamlit admin UI for tenant managers and tenant admins |
| `widget/` | Embeddable chat widget (React + Vite) |
| `ci/` | Eval scripts: RAG golden set, agent golden set, red-team probes, classifier eval |

## Documentation

| Document | What it covers |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | Tenant isolation strategy, role model, caching, cost attribution, scaling story, admin UI design, Vault design |
| [docs/SPEC.md](docs/SPEC.md) | Database schema + RLS policies, role permission matrix, tool contracts, Streamlit admin UI spec, eval thresholds |
| [docs/SECURITY.md](docs/SECURITY.md) | Chat security flow, tenant isolation layers, PII redaction, guardrails placement, origin enforcement |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Every architectural decision with rationale: RAG phases, classifier model choice, Vault, Streamlit, CI structure |
| [docs/EVALS.md](docs/EVALS.md) | Eval results and gate summary: RAG baseline → reranker → hybrid, classifier F1, agent golden set, red-team probes |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Prerequisites, startup, service endpoints, common ops, CI pipeline overview, troubleshooting |
| [COLLABORATION.md](COLLABORATION.md) | Per-person contribution reports, team decisions, blockers |
