#!/usr/bin/env bash
# Vault seed script — example with placeholder values.
#
# Usage:
#   cp seed.example.sh seed.sh
#   # edit seed.sh and replace every CHANGE_ME with real values
#   docker compose up -d
#   bash seed.sh
#
# seed.sh is gitignored. Never commit real secrets.

set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-root-token-changeme}"

# Wrapper: run vault CLI inside the vault container
v() {
  docker compose exec \
    -e VAULT_ADDR="$VAULT_ADDR" \
    -e VAULT_TOKEN="$VAULT_TOKEN" \
    vault vault "$@"
}

echo "Seeding Vault at $VAULT_ADDR ..."

# Database — matches POSTGRES_* bootstrap values in .env
v kv put secret/concierge/database \
  user="concierge" \
  password="CHANGE_ME" \
  host="postgres" \
  port="5432" \
  name="concierge"

# MinIO — matches MINIO_ROOT_* bootstrap values in .env
v kv put secret/concierge/minio \
  endpoint="minio:9000" \
  access_key="minioadmin" \
  secret_key="CHANGE_ME"

# Redis
v kv put secret/concierge/redis \
  url="redis://redis:6379"

# LLM — set provider to openai, azure, or groq; leave unused keys blank
v kv put secret/concierge/llm \
  provider="openai" \
  openai_api_key="CHANGE_ME" \
  openai_model="gpt-4o-mini" \
  openai_embedding_model="text-embedding-3-small" \
  azure_openai_api_key="" \
  azure_openai_endpoint="" \
  azure_openai_deployment="" \
  azure_openai_embedding_deployment="" \
  groq_api_key=""

# Widget JWT signing secret — use a long random string
v kv put secret/concierge/widget \
  token_secret="CHANGE_ME"

# Backend JWT signing secret — use a long random string, different from widget
v kv put secret/concierge/backend \
  secret_key="CHANGE_ME"

# Internal service-to-service tokens
v kv put secret/concierge/services \
  model_server="CHANGE_ME" \
  guardrails="CHANGE_ME"

echo "Done. All secrets written to Vault."
