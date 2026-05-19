from ..config import Settings
from .base import LlmProvider
from .mock import MockProvider
from .openai_compatible import OpenAICompatibleProvider


def create_provider(settings: Settings) -> LlmProvider:
    provider_type = settings.llm.provider.lower()
    if provider_type == "mock":
        return MockProvider()
    return OpenAICompatibleProvider(
        api_key=settings.llm.api_key,
        model_name=settings.llm.model_name,
        base_url=settings.llm.base_url,
        provider_name=settings.llm.provider,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
    )
