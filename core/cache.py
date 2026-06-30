import time
from typing import Any, Optional
from loguru import logger

log = logger.bind(module="cache")


class TTLCache:
    """Simple TTL cache for frequently accessed data.
    
    Caches values with a time-to-live (TTL) after which they expire.
    Useful for settings and configuration that don't change often.
    """
    
    def __init__(self, ttl_seconds: int = 60):
        """Initialize cache with TTL.
        
        Args:
            ttl_seconds: Time-to-live in seconds for cached values
        """
        self.cache: dict[str, tuple[Any, float]] = {}
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                self.hits += 1
                return value
            # Expired, remove it
            del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any):
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        self.cache[key] = (value, time.time())
    
    def invalidate(self, key: str):
        """Invalidate (remove) a cached value.
        
        Args:
            key: Cache key to invalidate
        """
        if key in self.cache:
            del self.cache[key]
    
    def invalidate_all(self):
        """Invalidate all cached values."""
        self.cache.clear()
    
    def get_stats(self) -> dict:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "size": len(self.cache),
        }


# Cache instances for different data types
# Settings change infrequently, so 30 second TTL is reasonable
settings_cache = TTLCache(ttl_seconds=30)

# Moods change even less frequently, 60 second TTL
moods_cache = TTLCache(ttl_seconds=60)


def cache_setting(key: str, value: Any):
    """Cache a setting value."""
    settings_cache.set(f"setting:{key}", value)


def get_cached_setting(key: str) -> Optional[Any]:
    """Get a cached setting value."""
    return settings_cache.get(f"setting:{key}")


def invalidate_setting(key: str):
    """Invalidate a cached setting."""
    settings_cache.invalidate(f"setting:{key}")


def invalidate_all_settings():
    """Invalidate all cached settings."""
    settings_cache.invalidate_all()


def cache_moods(moods: Any):
    """Cache moods value."""
    moods_cache.set("moods", moods)


def get_cached_moods() -> Optional[Any]:
    """Get cached moods value."""
    return moods_cache.get("moods")


def invalidate_moods():
    """Invalidate cached moods."""
    moods_cache.invalidate("moods")
