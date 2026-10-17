import asyncio
import json
import os
import sys
from pathlib import Path
import httpx
from openai import AsyncOpenAI

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.provider import BaseLLMProvider, CustomProvider, OllamaProvider, get_provider


def make_ollama_mock_transport() -> httpx.MockTransport:
    """Creates a mock HTTP transport emulating Ollama endpoints."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "llama3.2:latest"}, {"name": "nomic-embed-text:latest"}]},
            )

        if path == "/api/chat":
            body = json.loads(request.content.decode())
            if body.get("stream"):
                chunks = [
                    json.dumps({"message": {"content": "Hello"}, "done": False}) + "\n",
                    json.dumps({"message": {"content": " world!"}, "done": True}) + "\n",
                ]
                return httpx.Response(200, content="".join(chunks).encode())
            return httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": "Hello from mock Ollama!"}, "done": True},
            )

        if path == "/api/generate":
            return httpx.Response(
                200,
                json={"response": "Completion response", "done": True},
            )

        if path == "/api/embed":
            return httpx.Response(
                200,
                json={"embeddings": [[0.1, 0.2, 0.3]]},
            )

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def make_custom_mock_transport() -> httpx.MockTransport:
    """Creates a mock HTTP transport emulating OpenAI /v1 endpoints."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/models" in path:
            return httpx.Response(
                200,
                json={"data": [{"id": "deepseek-v4-flash"}, {"id": "kimi-k2.5"}]},
            )

        if "/chat/completions" in path:
            body = json.loads(request.content.decode())
            if body.get("stream"):
                sse_data = (
                    'data: {"choices": [{"delta": {"content": "Streamed "}}]}\n\n'
                    'data: {"choices": [{"delta": {"content": "Custom!"}}]}\n\n'
                    "data: [DONE]\n\n"
                )
                return httpx.Response(200, content=sse_data.encode())
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "Hello from Custom Provider!"}}]},
            )

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


async def check_ollama() -> None:
    transport = make_ollama_mock_transport()
    mock_client = httpx.AsyncClient(base_url="http://mock-ollama:11434", transport=transport)
    provider = OllamaProvider(
        base_url="http://mock-ollama:11434",
        default_model="llama3.2",
        client=mock_client,
    )

    assert await provider.is_available() is True
    assert "llama3.2:latest" in await provider.list_models()
    assert await provider.chat([{"role": "user", "content": "hi"}]) == "Hello from mock Ollama!"
    assert await provider.generate("hi") == "Completion response"

    streamed: list[str] = []
    async for chunk in provider.stream_chat([{"role": "user", "content": "hi"}]):
        streamed.append(chunk)
    assert "".join(streamed) == "Hello world!"
    assert await provider.embed("test") == [[0.1, 0.2, 0.3]]
    await provider.aclose()


async def check_custom_provider() -> None:
    transport = make_custom_mock_transport()
    mock_http = httpx.AsyncClient(transport=transport)
    openai_client = AsyncOpenAI(
        base_url="https://mock-custom.xyz/v1",
        api_key="sk-test",
        http_client=mock_http,
    )
    provider = CustomProvider(
        base_url="https://mock-custom.xyz/v1",
        api_key="sk-test",
        default_model="deepseek-v4-flash",
        client=openai_client,
    )

    assert await provider.is_available() is True
    models = await provider.list_models()
    assert "deepseek-v4-flash" in models

    reply = await provider.chat([{"role": "user", "content": "halo"}])
    assert reply == "Hello from Custom Provider!"

    gen_reply = await provider.generate("halo")
    assert gen_reply == "Hello from Custom Provider!"

    streamed: list[str] = []
    async for chunk in provider.stream_chat([{"role": "user", "content": "halo"}]):
        streamed.append(chunk)
    assert "".join(streamed) == "Streamed Custom!"
    await provider.aclose()


async def run_all_checks() -> None:
    # 1. Factory check
    ollama_p = get_provider("ollama")
    assert isinstance(ollama_p, OllamaProvider)
    custom_p = get_provider("custom")
    assert isinstance(custom_p, CustomProvider)

    # 2. Run provider checks
    await check_ollama()
    await check_custom_provider()
    print("ALL PROVIDER CHECKS (OLLAMA + CUSTOM) PASSED.")


def test_providers() -> None:
    asyncio.run(run_all_checks())


if __name__ == "__main__":
    asyncio.run(run_all_checks())
