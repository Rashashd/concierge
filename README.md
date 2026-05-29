# Concierge

Concierge is a multi-tenant AI SaaS for businesses that want a branded chat assistant, tenant-scoped retrieval, lead capture, and human escalation. The core requirement is isolation: a visitor on Tenant A must never see Tenant B's data.

## What It Does

- Verifies tenant identity from a signed widget token
- Retrieves only from the current tenant's content
- Captures leads and escalates conversations to humans
- Applies redaction, guardrails, and tenant-scoped memory
- Ships with evals for RAG quality, routing, and isolation

## Why It Stands Out

- Strong tenant isolation with verified token context, repository filters, and PostgreSQL RLS
- Bounded LangGraph agent loop instead of an open-ended chat bot
- Separate services for the model router and guardrails
- Measured RAG changes with baseline and advanced evals

## Tech

FastAPI, PostgreSQL + pgvector, Redis, MinIO, LangGraph, Azure OpenAI, Presidio, and NeMo Guardrails.

## Deep Dives

- [Design](docs/DESIGN.md)
- [Spec](docs/SPEC.md)
- [Decisions](docs/DECISIONS.md)
- [Security](docs/SECURITY.md)
- [Evals](docs/EVALS.md)

## Repo Notes

- `backend/` contains the main API, RAG, auth, and tenant admin surface.
- `guardrails/` contains the sidecar guardrails service.
- `model-server/` contains the lightweight classifier service.
- `widget/` contains the embeddable chat widget.
- `fixtures/manual_tenants/` contains sample tenant docs for local ingestion and isolation tests.
