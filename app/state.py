"""
app/state.py
============
Shared state management: Rate Limiter, Redis Session History, Supabase Fallback History.
These were previously inlined in unified_server.py (lines 97-229).
"""
import json
import logging
import os
import time
from typing import Dict, List, Optional

import redis.asyncio as redis

from app.config import REDIS_URL
from binding import select_client

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Distributed rate limiter using Redis Token Bucket algorithm."""

    def __init__(self, r: redis.Redis, capacity: int, refill_rate: float):
        self.r = r
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second

    async def consume(self, key: str, tokens: int = 1) -> bool:
        try:
            now = time.time()
            bucket_key = f"rate_limit:{key}"
            lua = """
            local key = KEYS[1]
            local capacity = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])
            local requested = tonumber(ARGV[4])
            local bucket = redis.call('hgetall', key)
            local last_tokens = capacity
            local last_refill = now
            if #bucket > 0 then
                for i=1, #bucket, 2 do
                    if bucket[i] == 'tokens' then last_tokens = tonumber(bucket[i+1]) end
                    if bucket[i] == 'last_refill' then last_refill = tonumber(bucket[i+1]) end
                end
            end
            local delta = math.max(0, now - last_refill)
            local current_tokens = math.min(capacity, last_tokens + (delta * refill_rate))
            if current_tokens >= requested then
                redis.call('hset', key, 'tokens', current_tokens - requested, 'last_refill', now)
                redis.call('expire', key, 60)
                return 1
            else
                return 0
            end
            """
            result = await self.r.eval(lua, 1, bucket_key, self.capacity, self.refill_rate, now, tokens)
            return bool(result)
        except Exception:
            return True  # Fail open if Redis unavailable


class RedisSharedState:
    """Redis-backed session and history management."""

    def __init__(self, r: redis.Redis):
        self.r = r

    async def get_history(self, session_id: str, user_id: str, org_id: str = None, limit: int = 10) -> List[Dict]:
        try:
            key = f"history:{user_id}:{session_id}"
            data = await self.r.lrange(key, 0, limit - 1)
            return [json.loads(d) for d in data][::-1]
        except Exception:
            return []

    async def add_history(self, session_id: str, user_id: str, role: str, content: str, org_id: str = None):
        try:
            key = f"history:{user_id}:{session_id}"
            await self.r.lpush(key, json.dumps({"role": role, "content": content}))
            await self.r.ltrim(key, 0, 19)
            await self.r.expire(key, 3600 * 24)
        except Exception:
            pass


class SupabaseSharedState:
    """Supabase-backed history management (fallback when Redis is unavailable)."""

    def __init__(self, client_name: str = "talentops"):
        self.client_name = client_name

    async def get_history(self, session_id: str, user_id: str, org_id: str = None, limit: int = 10) -> List[Dict]:
        try:
            select_client(self.client_name)
            query = supabase.table("chat_history").select("role, content")
            query = query.eq("session_id", session_id).eq("user_id", user_id)
            if org_id:
                query = query.eq("org_id", org_id)
            response = await query.order("created_at", desc=True).limit(limit).execute()
            return response.data[::-1] if response.data else []
        except Exception as e:
            logger.error(f"Supabase History Error: {e}")
            return []

    async def add_history(self, session_id: str, user_id: str, role: str, content: str, org_id: str = None):
        try:
            select_client(self.client_name)
            await supabase.table("chat_history").insert({
                "session_id": session_id, "user_id": user_id,
                "role": role, "content": content, "org_id": org_id
            }).execute()
        except Exception as e:
            logger.error(f"Error saving history to Supabase: {e}")


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
_shared_state_instance = None


async def get_shared_state():
    """Factory: return Redis or Supabase state based on availability."""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            r = redis.from_url(redis_url, decode_responses=True)
            await r.ping()
            logger.info("Using Redis for Shared State")
            return RedisSharedState(r)
        except Exception:
            logger.warning("Redis unavailable. Falling back to Supabase for history.")
    logger.info("Using Supabase for Shared State (Zero-Install Mode)")
    return SupabaseSharedState()


async def get_shared_state_singleton():
    global _shared_state_instance
    if _shared_state_instance is None:
        _shared_state_instance = await get_shared_state()
    return _shared_state_instance
