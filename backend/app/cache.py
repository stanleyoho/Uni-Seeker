import hashlib
import json
from typing import Any

import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def make_cache_key(prefix: str, *args: Any) -> str:
    """Create a deterministic cache key."""
    raw = json.dumps(args, sort_keys=True, default=str)
    hash_val = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"uni:{prefix}:{hash_val}"


async def cache_get(key: str) -> Any | None:
    """Get value from Redis cache. Returns None on miss or error."""
    try:
        client = await get_redis()
        data = await client.get(key)
        if data:
            return json.loads(data)
    except Exception:
        logger.warning("cache_get_failed", key=key)
    return None


async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    """Set value in Redis cache with TTL (default 1 hour)."""
    try:
        client = await get_redis()
        await client.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        logger.warning("cache_set_failed", key=key)


async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching pattern."""
    try:
        client = await get_redis()
        keys = []
        async for key in client.scan_iter(match=f"uni:{pattern}:*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)
    except Exception:
        logger.warning("cache_delete_failed", pattern=pattern)


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
