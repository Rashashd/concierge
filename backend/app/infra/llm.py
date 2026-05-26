from langchain_openai import AzureChatOpenAI, ChatOpenAI

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
        from langchain_groq import ChatGroq  # type: ignore[import-untyped]

        return ChatGroq(  # type: ignore[return-value]
            api_key=settings.groq_api_key.get_secret_value(),
            model="llama3-8b-8192",
        )
    # default: openai
    return ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )
