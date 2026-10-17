from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseLLMProvider(ABC):
    """Abstract base class contract for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a list of chat messages and return the assistant response text."""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a raw prompt and return the completion response text."""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream chunks of assistant response text."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider service is reachable."""
        pass
