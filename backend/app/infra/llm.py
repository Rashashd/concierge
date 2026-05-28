from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)

from app.core.config import Settings


def get_llm(settings: Settings) -> ChatOpenAI | AzureChatOpenAI:
    """Return the LLM client for the configured provider."""
    if settings.llm_provider == "azure":
        return AzureChatOpenAI(
            azure_deployment=settings.azure_openai_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key.get_secret_value(),
            api_version=settings.azure_openai_api_version,
            timeout=settings.azure_openai_timeout_seconds,
            max_retries=settings.azure_openai_max_retries,
        )
    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(  # type: ignore[return-value]
            api_key=settings.groq_api_key.get_secret_value(),
            model="llama3-8b-8192",
        )
    # default: openai
    return ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )


def get_embeddings(settings: Settings) -> AzureOpenAIEmbeddings | OpenAIEmbeddings:
    if settings.llm_provider == "azure":
        return AzureOpenAIEmbeddings(
            deployment=settings.azure_openai_embedding_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            openai_api_key=settings.azure_openai_api_key,
            openai_api_version=settings.azure_openai_api_version,
            request_timeout=settings.azure_openai_timeout_seconds,
            max_retries=settings.azure_openai_max_retries,
        )

    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        openai_api_key=settings.openai_api_key,
        request_timeout=settings.azure_openai_timeout_seconds,
        max_retries=settings.azure_openai_max_retries,
    )
