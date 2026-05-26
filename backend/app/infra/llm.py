from langchain_openai import AzureChatOpenAI

from app.core.config import Settings


def get_llm(settings: Settings) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key.get_secret_value(),
        api_version=settings.azure_openai_api_version,
        timeout=settings.azure_openai_timeout_seconds,
        max_retries=settings.azure_openai_max_retries,
    )
