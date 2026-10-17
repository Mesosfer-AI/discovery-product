import json
from typing import Any, AsyncIterator
import httpx

from app.config.settings import settings
from app.provider.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """LLM provider implementation for local or remote Ollama instances."""

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.default_model = default_model or settings.ollama_default_model
        self.timeout = timeout or settings.ollama_timeout
        # ponytail: _client can be injected or lazily initialized.
        # Ceiling: Long-running apps should manage a single shared client or close on shutdown.
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def is_available(self) -> bool:
        """Check if the Ollama instance is reachable."""
        try:
            client = self._get_client()
            res = await client.get("/api/tags", timeout=3.0)
            return res.status_code == 200
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    async def list_models(self) -> list[str]:
        """Fetch list of model names currently available in Ollama."""
        client = self._get_client()
        try:
            res = await client.get("/api/tags")
            res.raise_for_status()
            data = res.json()
            return [model.get("name", "") for model in data.get("models", [])]
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            ) from exc

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send chat messages to Ollama and return assistant content string."""
        client = self._get_client()
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        try:
            res = await client.post("/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
            return data.get("message", {}).get("content", "")
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama API returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a single prompt to Ollama and return the text completion."""
        client = self._get_client()
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
            **kwargs,
        }
        try:
            res = await client.post("/api/generate", json=payload)
            res.raise_for_status()
            data = res.json()
            return data.get("response", "")
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama API returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream assistant response tokens chunk by chunk."""
        client = self._get_client()
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }
        try:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama stream returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

    async def embed(
        self,
        text: str | list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate vector embeddings for input text(s)."""
        client = self._get_client()
        payload = {
            "model": model or self.default_model,
            "input": text,
        }
        try:
            res = await client.post("/api/embed", json=payload)
            res.raise_for_status()
            data = res.json()
            return data.get("embeddings", [])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama embedding returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
