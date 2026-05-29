from __future__ import annotations

import os
from pathlib import Path

import hvac

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"


REQUIRED_KEYS = [
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
]


def main() -> None:
    env = _load_env(ENV_PATH)
    env.update(_env_overrides(["VAULT_ADDR", "VAULT_TOKEN"]))
    _require_keys(env, REQUIRED_KEYS)
    reranker_provider = env.get("RERANKER_PROVIDER", "llm") or "llm"
    if reranker_provider not in {"llm", "cohere"}:
        raise RuntimeError("RERANKER_PROVIDER must be 'llm' or 'cohere'")
    if reranker_provider == "cohere":
        _require_keys(env, ["COHERE_API_KEY"])

    vault_addr = _host_vault_addr(env["VAULT_ADDR"])
    client = hvac.Client(url=vault_addr, token=env["VAULT_TOKEN"])
    if not client.is_authenticated():
        raise RuntimeError(f"Vault authentication failed for {vault_addr}")

    _write_secret(
        client,
        "concierge/database",
        {
            "user": env["POSTGRES_USER"],
            "password": env["POSTGRES_PASSWORD"],
            "host": "postgres",
            "port": "5432",
            "name": env["POSTGRES_DB"],
        },
    )
    _write_secret(client, "concierge/redis", {"url": "redis://redis:6379"})
    _write_secret(
        client,
        "concierge/minio",
        {
            "endpoint": "minio:9000",
            "access_key": env["MINIO_ROOT_USER"],
            "secret_key": env["MINIO_ROOT_PASSWORD"],
        },
    )
    _write_secret(
        client,
        "concierge/llm",
        {
            "provider": "azure",
            "openai_api_key": "",
            "openai_model": "gpt-4o-mini",
            "openai_embedding_model": "text-embedding-3-small",
            "azure_openai_api_key": env["AZURE_OPENAI_API_KEY"],
            "azure_openai_endpoint": _azure_endpoint(env["AZURE_OPENAI_ENDPOINT"]),
            "azure_openai_deployment": env["AZURE_OPENAI_DEPLOYMENT"],
            "azure_openai_embedding_deployment": env[
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
            ],
            "groq_api_key": "",
            "reranker_provider": reranker_provider,
            "cohere_api_key": env.get("COHERE_API_KEY", ""),
            "cohere_rerank_model": env.get("COHERE_RERANK_MODEL", "rerank-v4.0-fast"),
            "reranker_timeout_seconds": env.get("RERANKER_TIMEOUT_SECONDS", "10"),
            "reranker_max_retries": env.get("RERANKER_MAX_RETRIES", "2"),
            "rag_retrieval_mode": env.get("RAG_RETRIEVAL_MODE", "hybrid"),
            "hybrid_vector_weight": env.get("HYBRID_VECTOR_WEIGHT", "0.7"),
            "hybrid_keyword_weight": env.get("HYBRID_KEYWORD_WEIGHT", "0.3"),
            "hybrid_keyword_candidate_count": env.get(
                "HYBRID_KEYWORD_CANDIDATE_COUNT", "20"
            ),
            "hybrid_vector_candidate_count": env.get(
                "HYBRID_VECTOR_CANDIDATE_COUNT", "20"
            ),
        },
    )
    _write_secret(
        client,
        "concierge/widget",
        {
            "token_secret": env.get(
                "WIDGET_TOKEN_SECRET",
                "local-widget-token-secret-change-me-32",
            )
            or "local-widget-token-secret-change-me-32"
        },
    )
    _write_secret(
        client,
        "concierge/backend",
        {"secret_key": "local-backend-secret-change-me-32"},
    )
    _write_secret(
        client,
        "concierge/services",
        {
            "model_server": env.get(
                "MODEL_SERVER_SERVICE_TOKEN", "local-model-server-token"
            ),
            "guardrails": env.get("GUARDRAILS_SERVICE_TOKEN", "local-guardrails-token"),
        },
    )
    _write_secret(
        client,
        "concierge/langchain",
        {
            "tracing_enabled": "false",
            "api_key": "",
            "project": "concierge",
        },
    )

    print(f"Seeded Vault at {vault_addr} from {ENV_PATH}")


def _load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing env file: {path}")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _clean_env_value(value.strip())
    return values


def _env_overrides(keys: list[str]) -> dict[str, str]:
    return {key: value for key in keys if (value := os.getenv(key))}


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _require_keys(env: dict[str, str], keys: list[str]) -> None:
    missing = [key for key in keys if not env.get(key)]
    if missing:
        raise RuntimeError(
            "Missing required .env values for Vault seed: " + ", ".join(missing)
        )


def _host_vault_addr(vault_addr: str) -> str:
    if vault_addr in {"http://vault:8200", "https://vault:8200"}:
        return vault_addr.replace("vault", "127.0.0.1")
    return vault_addr


def _azure_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    for suffix in ("/openai/v1", "/openai"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _write_secret(
    client: hvac.Client,
    path: str,
    values: dict[str, str],
) -> None:
    client.secrets.kv.v2.create_or_update_secret(
        path=path,
        secret=values,
        mount_point="secret",
    )
    print(f"seeded secret/{path}")


if __name__ == "__main__":
    main()
