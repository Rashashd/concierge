"""Vault client. Secrets are stored under secret/concierge/<group>."""

from typing import Any

import hvac
import structlog

logger = structlog.get_logger(__name__)

# Vault secret paths
_PATH_DATABASE = "secret/concierge/database"
_PATH_MINIO = "secret/concierge/minio"
_PATH_REDIS = "secret/concierge/redis"
_PATH_LLM = "secret/concierge/llm"
_PATH_WIDGET = "secret/concierge/widget"
_PATH_BACKEND = "secret/concierge/backend"
_PATH_SERVICES = "secret/concierge/services"


class VaultClient:
    def __init__(self, addr: str, token: str) -> None:
        self._client = hvac.Client(url=addr, token=token)

    def _read(self, path: str) -> dict[str, Any]:
        response = self._client.secrets.kv.v2.read_secret_version(
            path=path.removeprefix("secret/"),
            mount_point="secret",
        )
        return response["data"]["data"]  # type: ignore[no-any-return]

    def get_database_url(self) -> str:
        data = self._read(_PATH_DATABASE)
        user = data["user"]
        password = data["password"]
        host = data["host"]
        port = data["port"]
        db = data["name"]
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    def get_minio_config(self) -> dict[str, str]:
        return self._read(_PATH_MINIO)

    def get_redis_url(self) -> str:
        data = self._read(_PATH_REDIS)
        return data["url"]

    def get_llm_config(self) -> dict[str, str]:
        return self._read(_PATH_LLM)

    def get_widget_secret(self) -> str:
        data = self._read(_PATH_WIDGET)
        return data["token_secret"]

    def get_backend_secret_key(self) -> str:
        data = self._read(_PATH_BACKEND)
        return data["secret_key"]

    def get_service_token(self, service: str) -> str:
        """Shared token for internal service-to-service auth."""
        data = self._read(_PATH_SERVICES)
        return data[service]

    def is_authenticated(self) -> bool:
        return bool(self._client.is_authenticated())


def create_vault_client(addr: str, token: str) -> VaultClient:
    client = VaultClient(addr=addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError(f"Vault authentication failed (addr={addr})")
    logger.info("vault.connected", addr=addr)
    return client
