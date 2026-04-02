"""In-memory and Redis cache implementations."""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseCache(ABC):
    """Abstract cache interface."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with optional TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache entries."""
        pass
    
    @staticmethod
    def make_key(*args: Any) -> str:
        """Create cache key from arguments."""
        key_str = json.dumps(args, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()


class MemoryCache(BaseCache):
    """Simple in-memory cache with TTL support."""
    
    def __init__(self):
        """Initialize memory cache."""
        self._cache: dict[str, tuple[Any, Optional[float]]] = {}
        logger.info("Initialized in-memory cache")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from memory cache."""
        import time
        
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        
        if expiry is not None and time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in memory cache."""
        import time
        
        expiry = None
        if ttl is not None:
            expiry = time.time() + ttl
        
        self._cache[key] = (value, expiry)
    
    async def delete(self, key: str) -> None:
        """Delete key from memory cache."""
        self._cache.pop(key, None)
    
    async def clear(self) -> None:
        """Clear all memory cache entries."""
        self._cache.clear()
    
    def size(self) -> int:
        """Get number of cached items."""
        return len(self._cache)


class RedisCache(BaseCache):
    """Redis-backed cache."""
    
    def __init__(self):
        """Initialize Redis cache."""
        import redis
        
        self._redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
        logger.info(f"Initialized Redis cache at {settings.redis_host}:{settings.redis_port}")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        value = self._redis.get(key)
        if value is None:
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in Redis cache."""
        serialized = json.dumps(value)
        if ttl is not None:
            self._redis.setex(key, ttl, serialized)
        else:
            self._redis.set(key, serialized)
    
    async def delete(self, key: str) -> None:
        """Delete key from Redis cache."""
        self._redis.delete(key)
    
    async def clear(self) -> None:
        """Clear all Redis cache entries."""
        self._redis.flushdb()


def get_cache() -> BaseCache:
    """Get cache instance based on configuration."""
    if not settings.cache_enabled:
        return MemoryCache()  # Return dummy cache
    
    if settings.cache_backend == "redis":
        try:
            return RedisCache()
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}. Falling back to memory cache.")
            return MemoryCache()
    
    return MemoryCache()


# Global cache instance
cache = get_cache()
