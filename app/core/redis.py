import redis.asyncio as aioredis
from typing import Optional, Any
import json
from app.core.config import settings


class RedisClient:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        self._client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

    async def disconnect(self):
        if self._client:
            await self._client.close()

    async def get(self, key: str) -> Optional[Any]:
        if not self._client:
            return None
        value = await self._client.get(key)
        if value:
            return json.loads(value)
        return None

    async def set(self, key: str, value: Any, ttl: int = settings.REDIS_CACHE_TTL):
        if self._client:
            await self._client.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, key: str):
        if self._client:
            await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        if not self._client:
            return False
        return bool(await self._client.exists(key))

    async def blacklist_token(self, token: str, expire_seconds: int):
        await self.set(f"blacklist:{token}", "1", ttl=expire_seconds)

    async def is_token_blacklisted(self, token: str) -> bool:
        return await self.exists(f"blacklist:{token}")

    async def increment(self, key: str, ttl: int = 60) -> int:
        if not self._client:
            return 0
        pipe = self._client.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, ttl)
        results = await pipe.execute()
        return results[0]


redis_client = RedisClient()
