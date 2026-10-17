from app.config.settings import settings
from app.provider.base import BaseLLMProvider
from app.provider.custom import CustomProvider
from app.provider.ollama import OllamaProvider


def get_provider(provider_type: str | None = None) -> BaseLLMProvider:
    """Factory function returning the configured LLM provider instance."""
    provider_name = (provider_type or settings.llm_provider).lower()
    if provider_name == "ollama":
        return OllamaProvider()
    if provider_name in ("custom", "openai"):
        return CustomProvider()
    if provider_name == "amd":
        if not settings.amd_api_key.startswith("rc-"):
            raise ValueError(
                "AMD_API_KEY is missing or invalid: expected an AMD Token Factory key starting with 'rc-'."
            )
        return CustomProvider(
            base_url=settings.amd_base_url,
            api_key=settings.amd_api_key,
            default_model=settings.amd_default_model,
            timeout=settings.amd_timeout,
            api_key_env="AMD_API_KEY",
        )
    raise ValueError(
        f"Unsupported LLM provider: '{provider_name}'. Supported: ['ollama', 'custom', 'amd']"
    )


def get_model(role: str, provider_type: str | None = None) -> str | None:
    """Model ID for a pipeline role ("fast" or "reasoning") on the active provider.

    Returns None for providers without role-specific models (provider default is used).
    """
    provider_name = (provider_type or settings.llm_provider).lower()
    if provider_name == "amd":
        return settings.amd_fast_model if role == "fast" else settings.amd_reasoning_model
    if provider_name in ("custom", "openai"):
        return settings.custom_llm_fast_model if role == "fast" else settings.custom_llm_reasoning_model
    return None


__all__ = ["BaseLLMProvider", "OllamaProvider", "CustomProvider", "get_provider", "get_model"]
