import asyncio
import logging
import random
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from app.config.settings import settings
from app.provider.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class _GlobalLimiter:
    """Process-wide concurrency + sliding-window RPM gate shared by every provider instance."""

    def __init__(self, max_concurrency: int, rpm: int) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.rpm = rpm
        self.sent: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def _wait_rpm(self) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.sent and now - self.sent[0] >= 60.0:
                    self.sent.popleft()
                if len(self.sent) < self.rpm:
                    self.sent.append(now)
                    return
                await asyncio.sleep(60.0 - (now - self.sent[0]))

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self.semaphore:
            await self._wait_rpm()
            yield


# ponytail: per-process limiter only. Multiple workers/containers sharing one API key
# multiply the effective rate; move to Redis-based limiting (app/services/redis_client.py) then.
_limiter = _GlobalLimiter(settings.llm_max_concurrency, settings.llm_rpm_limit)


def _error_detail(exc: APIStatusError) -> str:
    """Extract the server error message from gateway {"error":..} or platform {"detail":{"error":..}} bodies."""
    body = exc.body
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        body = body["detail"].get("error", body["detail"])
    if isinstance(body, dict):
        return str(body.get("message") or body)
    return str(body or exc.message)


def _retry_delay(exc: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None if the error is not retryable."""
    if attempt >= settings.llm_max_retries:
        return None
    if isinstance(exc, RateLimitError):
        retry_after = exc.response.headers.get("retry-after")
        try:
            return float(retry_after) + random.uniform(0, 0.5)
        except (TypeError, ValueError):
            pass
    elif isinstance(exc, APITimeoutError):
        return None  # a 10-minute timeout is not worth repeating
    elif not (
        isinstance(exc, APIConnectionError)
        or (isinstance(exc, APIStatusError) and exc.status_code in (502, 503))
    ):
        return None
    return min(2.0**attempt, 30.0) * random.uniform(0.5, 1.5)


class CustomProvider(BaseLLMProvider):
    """OpenAI-compatible LLM provider (supports bandelbanget.xyz, AMD Token Factory, OpenRouter, etc.)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        client: AsyncOpenAI | None = None,
        api_key_env: str = "CUSTOM_LLM_API_KEY",
    ) -> None:
        self.base_url = (base_url or settings.custom_llm_base_url).rstrip("/")
        self.api_key = api_key or settings.custom_llm_api_key
        self.default_model = default_model or settings.custom_llm_default_model
        self.timeout = timeout or settings.custom_llm_timeout
        self.api_key_env = api_key_env
        # ponytail: _client can be injected for testing or created on demand.
        # Ceiling: Single client per instance; upgrade to connection pool if scaling across workers.
        self._client = client

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "sk-dummy",
                timeout=self.timeout,
                max_retries=0,  # retries are handled by _retry_delay with the global limiter
            )
        return self._client

    def _map_error(self, exc: Exception, model: str) -> Exception:
        """Translate an OpenAI SDK error into a clear, provider-aware exception."""
        where = f"{self.base_url} (model {model})"
        if isinstance(exc, AuthenticationError):
            return PermissionError(f"Authentication failed for {self.base_url}. Check {self.api_key_env} in .env.")
        if isinstance(exc, PermissionDeniedError):
            return PermissionError(
                f"Access denied (403) by {where}: {_error_detail(exc)}. "
                f"The account behind {self.api_key_env} may be pending verification/review (account_not_verified)."
            )
        if isinstance(exc, RateLimitError):
            return RuntimeError(f"Rate limit exceeded on {where} after retries: {_error_detail(exc)}")
        if isinstance(exc, BadRequestError):
            return ValueError(
                f"Bad request (400) to {where}: {_error_detail(exc)}. "
                "Check the model ID (case-sensitive), parameters and remaining credits."
            )
        if isinstance(exc, APIStatusError):
            return RuntimeError(f"LLM provider {where} returned HTTP {exc.status_code}: {_error_detail(exc)}")
        if isinstance(exc, APITimeoutError):
            return TimeoutError(f"Request to {where} timed out after {self.timeout}s.")
        if isinstance(exc, APIConnectionError):
            return ConnectionError(f"Failed to connect to LLM provider at {self.base_url}.")
        return exc

    async def aclose(self) -> None:
        """Close the underlying client session."""
        if self._client is not None:
            await self._client.close()

    async def is_available(self) -> bool:
        """Verify reachability of the provider API; failures are logged, not raised."""
        try:
            await self._get_client().models.list()
            return True
        except AuthenticationError:
            logger.error("LLM provider %s rejected the API key (401). Check %s.", self.base_url, self.api_key_env)
        except PermissionDeniedError as exc:
            logger.error("LLM provider %s denied access (403): %s", self.base_url, _error_detail(exc))
        except APIStatusError as exc:
            logger.warning("LLM provider %s returned HTTP %s: %s", self.base_url, exc.status_code, _error_detail(exc))
        except APIConnectionError as exc:
            logger.warning("LLM provider %s unreachable: %s", self.base_url, exc)
        return False

    async def list_models(self) -> list[str]:
        """Fetch list of available model IDs from provider."""
        try:
            res = await self._get_client().models.list()
            return [m.id for m in res.data]
        except (APIStatusError, APIConnectionError) as exc:
            raise self._map_error(exc, "-") from exc

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send chat messages and return assistant text content."""
        client = self._get_client()
        target_model = model or self.default_model
        attempt = 0
        while True:
            async with _limiter.slot():
                try:
                    res = await client.chat.completions.create(
                        model=target_model,
                        messages=messages,  # type: ignore[arg-type]
                        stream=False,
                        **kwargs,
                    )
                    break
                except (APIStatusError, APIConnectionError) as exc:
                    delay, error = _retry_delay(exc, attempt), exc
                    if delay is None:
                        raise self._map_error(exc, target_model) from exc
            logger.warning("LLM request to %s failed (%s); retry %d in %.1fs", self.base_url, error, attempt + 1, delay)
            attempt += 1
            await asyncio.sleep(delay)

        choice = res.choices[0] if res.choices else None
        content = (choice.message.content or "") if choice else ""
        finish_reason = choice.finish_reason if choice else None
        if finish_reason == "length" or not content:
            logger.warning(
                "LLM %s on %s returned %d chars with finish_reason=%s (thinking tokens count toward max_tokens).",
                target_model, self.base_url, len(content), finish_reason,
            )
        if not content:
            raise RuntimeError(
                f"LLM {target_model} returned empty content (finish_reason={finish_reason}); "
                "raise max_tokens or use a non-thinking model."
            )
        return content

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send prompt as user message and return completion text."""
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            **kwargs,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream assistant response tokens chunk by chunk (retries only before the first chunk)."""
        client = self._get_client()
        target_model = model or self.default_model
        attempt = 0
        while True:
            async with _limiter.slot():
                try:
                    stream = await client.chat.completions.create(
                        model=target_model,
                        messages=messages,  # type: ignore[arg-type]
                        stream=True,
                        **kwargs,
                    )
                except (APIStatusError, APIConnectionError) as exc:
                    delay, error = _retry_delay(exc, attempt), exc
                    if delay is None:
                        raise self._map_error(exc, target_model) from exc
                else:
                    try:
                        async for chunk in stream:
                            if chunk.choices and chunk.choices[0].delta.content:
                                yield chunk.choices[0].delta.content
                    except (APIStatusError, APIConnectionError) as exc:
                        raise self._map_error(exc, target_model) from exc
                    return
            logger.warning("LLM stream to %s failed (%s); retry %d in %.1fs", self.base_url, error, attempt + 1, delay)
            attempt += 1
            await asyncio.sleep(delay)
