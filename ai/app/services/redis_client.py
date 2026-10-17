import json
from typing import Any
import redis.asyncio as aioredis
from app.config.settings import settings


class CacheManager:
    """Manages Redis connection with in-memory fallback for offline environments."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None
        # ponytail: _fallback_sets & _fallback_cache act as in-memory fallback when Redis is unreachable.
        # Ceiling: Single-process memory only; upgrade by ensuring active Redis server in production.
        self._fallback_sets: dict[str, set[str]] = {}
        self._fallback_cache: dict[str, str] = {}
        self._is_connected: bool | None = None

    async def get_client(self) -> aioredis.Redis | None:
        if self._is_connected is False:
            return None
        if self._redis is None:
            try:
                client = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                )
                await client.ping()
                self._redis = client
                self._is_connected = True
            except Exception:
                self._is_connected = False
                self._redis = None
        return self._redis

    async def is_member_or_add(self, set_key: str, value: str) -> bool:
        """
        Deduplication check:
        Returns True if `value` was newly added (unique).
        Returns False if `value` already existed (duplicate).
        """
        client = await self.get_client()
        if client:
            try:
                # SADD returns 1 if new element was added, 0 if already present
                result = await client.sadd(set_key, value)
                return bool(result == 1)
            except Exception:
                pass

        # In-memory fallback
        if set_key not in self._fallback_sets:
            self._fallback_sets[set_key] = set()
        if value in self._fallback_sets[set_key]:
            return False
        self._fallback_sets[set_key].add(value)
        return True

    async def get_set(self, set_key: str) -> set[str]:
        """All members of a set (Redis, else the in-memory fallback)."""
        client = await self.get_client()
        if client:
            try:
                return set(await client.smembers(set_key))
            except Exception:
                pass
        return set(self._fallback_sets.get(set_key, ()))

    async def get_json(self, key: str) -> Any | None:
        """Retrieve cached JSON payload."""
        client = await self.get_client()
        if client:
            try:
                val = await client.get(key)
                return json.loads(val) if val else None
            except Exception:
                pass
        val = self._fallback_cache.get(key)
        return json.loads(val) if val else None

    async def set_json(self, key: str, data: Any, ttl_seconds: int = 3600) -> None:
        """Store JSON payload in cache with TTL."""
        serialized = json.dumps(data)
        client = await self.get_client()
        if client:
            try:
                await client.set(key, serialized, ex=ttl_seconds)
                return
            except Exception:
                pass
        self._fallback_cache[key] = serialized

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


cache_manager = CacheManager()
