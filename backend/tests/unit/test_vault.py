from unittest.mock import MagicMock, patch

import pytest

from app.infra.vault import VaultClient, create_vault_client


def _client_with(data: dict) -> VaultClient:
    client = VaultClient.__new__(VaultClient)
    mock_hvac = MagicMock()
    mock_hvac.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": data}
    }
    client._client = mock_hvac
    return client


# get_database_url


def test_get_database_url_builds_asyncpg_connection_string() -> None:
    client = _client_with(
        {
            "user": "concierge",
            "password": "secret",
            "host": "postgres",
            "port": "5432",
            "name": "concierge",
        }
    )
    assert client.get_database_url() == (
        "postgresql+asyncpg://concierge:secret@postgres:5432/concierge"
    )


def test_get_database_url_reads_correct_vault_path() -> None:
    client = _client_with(
        {"user": "u", "password": "p", "host": "h", "port": "5432", "name": "db"}
    )
    client.get_database_url()
    client._client.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="concierge/database",
        mount_point="secret",
    )


# get_redis_url


def test_get_redis_url_returns_url_from_vault() -> None:
    client = _client_with({"url": "redis://redis:6379"})
    assert client.get_redis_url() == "redis://redis:6379"


# get_minio_config


def test_get_minio_config_returns_raw_dict() -> None:
    data = {"endpoint": "minio:9000", "access_key": "admin", "secret_key": "secret"}
    client = _client_with(data)
    assert client.get_minio_config() == data


# get_llm_config


def test_get_llm_config_returns_raw_dict() -> None:
    data = {"provider": "openai", "openai_api_key": "sk-test"}
    client = _client_with(data)
    assert client.get_llm_config() == data


# get_widget_secret


def test_get_widget_secret_extracts_token_secret_field() -> None:
    client = _client_with({"token_secret": "my-widget-secret"})
    assert client.get_widget_secret() == "my-widget-secret"


# get_backend_secret_key


def test_get_backend_secret_key_extracts_secret_key_field() -> None:
    client = _client_with({"secret_key": "my-backend-key"})
    assert client.get_backend_secret_key() == "my-backend-key"


# get_service_token


def test_get_service_token_extracts_by_service_name() -> None:
    client = _client_with({"model_server": "token-ms", "guardrails": "token-gr"})
    assert client.get_service_token("model_server") == "token-ms"
    assert client.get_service_token("guardrails") == "token-gr"


# get_langchain_config


def test_get_langchain_config_returns_raw_dict() -> None:
    data = {"tracing_enabled": "true", "api_key": "ls-test", "project": "concierge"}
    client = _client_with(data)
    assert client.get_langchain_config() == data


# create_vault_client


def test_create_vault_client_raises_when_not_authenticated() -> None:
    with patch("app.infra.vault.hvac.Client") as MockHvac:
        MockHvac.return_value.is_authenticated.return_value = False
        with pytest.raises(RuntimeError, match="Vault authentication failed"):
            create_vault_client("http://localhost:8200", "bad-token")


def test_create_vault_client_returns_vault_client_when_authenticated() -> None:
    with patch("app.infra.vault.hvac.Client") as MockHvac:
        MockHvac.return_value.is_authenticated.return_value = True
        result = create_vault_client("http://localhost:8200", "root")
        assert isinstance(result, VaultClient)
