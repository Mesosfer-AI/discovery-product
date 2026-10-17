import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from openai import AsyncOpenAI

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import Settings, settings
from app.provider import CustomProvider, get_model, get_provider

VALID_AMD_KEY = "rc-" + "0" * 48


def make_provider(responses: list[httpx.Response]) -> tuple[CustomProvider, list[httpx.Request]]:
    """CustomProvider whose HTTP calls return the given responses in order (no network)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[len(seen) - 1]

    client = AsyncOpenAI(
        base_url="https://mock-amd/v1",
        api_key=VALID_AMD_KEY,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    provider = CustomProvider(
        base_url="https://mock-amd/v1",
        api_key=VALID_AMD_KEY,
        default_model="DeepSeek-V4-Flash",
        client=client,
        api_key_env="AMD_API_KEY",
    )
    return provider, seen


def completion(content: str | None, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}]},
    )


def test_get_provider_amd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "amd_api_key", VALID_AMD_KEY)
    provider = get_provider("amd")
    assert isinstance(provider, CustomProvider)
    # Code defaults (a local .env may override them).
    assert Settings.model_fields["amd_base_url"].default == "https://developer.amd.com.cn/radeon/api/v1"
    assert Settings.model_fields["amd_default_model"].default == "DeepSeek-V4-Flash"
    assert Settings.model_fields["amd_timeout"].default == 600.0
    assert provider.base_url == settings.amd_base_url.rstrip("/")
    assert provider.default_model == settings.amd_default_model
    assert provider.timeout == settings.amd_timeout
    assert provider.api_key_env == "AMD_API_KEY"


@pytest.mark.parametrize("key", ["", "sk-dummy", "not-an-amd-key"])
def test_get_provider_amd_rejects_bad_key(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setattr(settings, "amd_api_key", key)
    with pytest.raises(ValueError, match="AMD_API_KEY"):
        get_provider("amd")


def test_model_selection_follows_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "amd_fast_model", "MiMo-V2.6-Flash")
    monkeypatch.setattr(settings, "amd_reasoning_model", "GLM-5.3-Flash")
    assert get_model("fast", "amd") == "MiMo-V2.6-Flash"
    assert get_model("reasoning", "amd") == "GLM-5.3-Flash"
    assert get_model("fast", "custom") == settings.custom_llm_fast_model
    assert get_model("reasoning", "custom") == settings.custom_llm_reasoning_model
    assert get_model("fast", "ollama") is None

    monkeypatch.setattr(settings, "llm_provider", "amd")
    assert get_model("fast") == "MiMo-V2.6-Flash"


def test_429_retry_honors_retry_after() -> None:
    provider, seen = make_provider([
        httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {"message": "rpm exceeded"}}),
        completion('{"ok": true}'),
    ])
    with patch("app.provider.custom.asyncio.sleep", new=AsyncMock()) as sleep:
        reply = asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))
    assert reply == '{"ok": true}'
    assert len(seen) == 2
    sleep.assert_awaited_once()
    assert 7.0 <= sleep.await_args.args[0] < 8.0


def test_400_is_not_retried_and_shows_detail() -> None:
    provider, seen = make_provider([
        httpx.Response(400, json={"detail": {"error": {"message": "Requested model Foo not supported"}}}),
    ])
    with patch("app.provider.custom.asyncio.sleep", new=AsyncMock()) as sleep:
        with pytest.raises(ValueError, match="Requested model Foo not supported"):
            asyncio.run(provider.chat([{"role": "user", "content": "hi"}], model="Foo"))
    assert len(seen) == 1
    sleep.assert_not_awaited()


def test_403_mentions_account_verification() -> None:
    provider, _ = make_provider([
        httpx.Response(403, json={"error": {"message": "account_not_verified"}}),
    ])
    with pytest.raises(PermissionError, match="AMD_API_KEY"):
        asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))


def test_empty_content_raises() -> None:
    provider, _ = make_provider([completion("", finish_reason="length")])
    with pytest.raises(RuntimeError, match="empty content"):
        asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))


def test_stream_retries_429_before_first_chunk() -> None:
    sse = (
        'data: {"choices": [{"index": 0, "delta": {"content": "Hi"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    provider, seen = make_provider([
        httpx.Response(429, headers={"Retry-After": "1"}, json={"error": {"message": "concurrency"}}),
        httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"}),
    ])

    async def collect() -> str:
        return "".join([c async for c in provider.stream_chat([{"role": "user", "content": "hi"}])])

    with patch("app.provider.custom.asyncio.sleep", new=AsyncMock()):
        assert asyncio.run(collect()) == "Hi"
    assert len(seen) == 2
    assert json.loads(seen[1].content)["stream"] is True
