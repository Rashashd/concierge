"""Unit tests for infra/llm.py — verifies provider branch selection."""

from unittest.mock import MagicMock

from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)
from pydantic import SecretStr

from app.infra.llm import get_embeddings, get_llm


def _make_settings(provider: str = "openai") -> MagicMock:
    s = MagicMock()
    s.llm_provider = provider
    # Use real SecretStr so LangChain Pydantic models accept openai_api_key directly
    s.openai_api_key = SecretStr("sk-fake-key")
    s.openai_model = "gpt-4o-mini"
    s.openai_embedding_model = "text-embedding-3-small"
    s.azure_openai_api_key = SecretStr("fake-azure-key")
    s.azure_openai_endpoint = "https://fake.openai.azure.com/"
    s.azure_openai_deployment = "gpt-4o"
    s.azure_openai_embedding_deployment = "text-embedding-3-small"
    s.azure_openai_api_version = "2024-02-01"
    s.azure_openai_timeout_seconds = 30
    s.azure_openai_max_retries = 2
    s.groq_api_key = SecretStr("gsk-fake-key")
    return s


def test_get_llm_returns_chat_openai_for_openai_provider() -> None:
    result = get_llm(_make_settings("openai"))
    assert isinstance(result, ChatOpenAI)


def test_get_llm_returns_azure_chat_openai_for_azure_provider() -> None:
    result = get_llm(_make_settings("azure"))
    assert isinstance(result, AzureChatOpenAI)


def test_get_embeddings_returns_openai_embeddings_for_openai_provider() -> None:
    result = get_embeddings(_make_settings("openai"))
    assert isinstance(result, OpenAIEmbeddings)


def test_get_embeddings_returns_azure_embeddings_for_azure_provider() -> None:
    result = get_embeddings(_make_settings("azure"))
    assert isinstance(result, AzureOpenAIEmbeddings)
