"""Sentiment analysis cache with TTL and rate limiting"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import asyncio
from ..utils.logger import logger


@dataclass
class CacheEntry:
    """Cache entry with TTL"""

    data: Any
    timestamp: datetime
    ttl_seconds: int

    def is_expired(self) -> bool:
        """Check if entry is expired"""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > self.ttl_seconds


@dataclass
class RateLimiter:
    """Simple rate limiter"""

    max_requests: int = 100  # Max requests per window
    window_seconds: int = 3600  # 1 hour window
    requests: list = field(default_factory=list)  # Request timestamps

    def can_request(self) -> bool:
        """Check if request is allowed"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # Clean old requests
        self.requests = [ts for ts in self.requests if ts > cutoff]

        # Check limit
        if len(self.requests) >= self.max_requests:
            return False

        # Record request
        self.requests.append(now)
        return True

    def get_wait_time(self) -> float:
        """Get seconds to wait before next request"""
        if not self.requests:
            return 0.0

        oldest = min(self.requests)
        wait_until = oldest + timedelta(seconds=self.window_seconds)
        wait_seconds = (wait_until - datetime.now()).total_seconds()

        return max(0.0, wait_seconds)


class SentimentCache:
    """Sentiment analysis cache with TTL and rate limiting

    Features:
    - TTL-based cache expiration
    - Per-source rate limiting
    - Automatic cleanup of expired entries
    """

    def __init__(
        self,
        default_ttl: int = 900,  # 15 minutes
        max_requests_per_hour: int = 100,
        cleanup_interval: int = 300,  # 5 minutes
    ):
        """Initialize cache

        Args:
            default_ttl: Default TTL in seconds (15 minutes)
            max_requests_per_hour: Max API requests per hour per source
            cleanup_interval: Cleanup interval in seconds
        """
        self.default_ttl = default_ttl
        self.cache: Dict[str, CacheEntry] = {}
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.max_requests_per_hour = max_requests_per_hour
        self.cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_cache_key(self, source: str, symbol: str) -> str:
        """Generate cache key"""
        return f"{source}:{symbol}"

    def _get_rate_limiter(self, source: str) -> RateLimiter:
        """Get or create rate limiter for source"""
        if source not in self.rate_limiters:
            self.rate_limiters[source] = RateLimiter(
                max_requests=self.max_requests_per_hour,
                window_seconds=3600,
            )
        return self.rate_limiters[source]

    def get(self, source: str, symbol: str) -> Optional[Any]:
        """Get cached data if not expired

        Args:
            source: Data source name
            symbol: Trading symbol

        Returns:
            Cached data or None if expired/not found
        """
        key = self._get_cache_key(source, symbol)
        entry = self.cache.get(key)

        if entry is None:
            logger.debug(f"Cache miss: {key}")
            return None

        if entry.is_expired():
            logger.debug(f"Cache expired: {key}")
            del self.cache[key]
            return None

        age = (datetime.now() - entry.timestamp).total_seconds()
        logger.debug(f"Cache hit: {key} (age: {age:.0f}s)")
        return entry.data

    def set(self, source: str, symbol: str, data: Any, ttl: Optional[int] = None):
        """Cache data with TTL

        Args:
            source: Data source name
            symbol: Trading symbol
            data: Data to cache
            ttl: TTL in seconds (uses default if None)
        """
        key = self._get_cache_key(source, symbol)
        ttl_seconds = ttl or self.default_ttl

        self.cache[key] = CacheEntry(
            data=data,
            timestamp=datetime.now(),
            ttl_seconds=ttl_seconds,
        )

        logger.debug(f"Cached: {key} (TTL: {ttl_seconds}s)")

    def can_request(self, source: str) -> bool:
        """Check if request is allowed (rate limiting)

        Args:
            source: Data source name

        Returns:
            True if request is allowed
        """
        limiter = self._get_rate_limiter(source)
        can_request = limiter.can_request()

        if not can_request:
            wait_time = limiter.get_wait_time()
            logger.warning(
                f"Rate limit reached for {source}. Wait {wait_time:.0f}s"
            )

        return can_request

    def get_wait_time(self, source: str) -> float:
        """Get seconds to wait before next request

        Args:
            source: Data source name

        Returns:
            Seconds to wait
        """
        limiter = self._get_rate_limiter(source)
        return limiter.get_wait_time()

    def cleanup_expired(self):
        """Remove expired cache entries"""
        expired_keys = [
            key for key, entry in self.cache.items() if entry.is_expired()
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    async def start_cleanup_task(self):
        """Start background cleanup task"""
        if self._cleanup_task is not None:
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(self.cleanup_interval)
                    self.cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Cleanup task error: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Sentiment cache cleanup task started")

    async def stop_cleanup_task(self):
        """Stop background cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Sentiment cache cleanup task stopped")

    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        logger.debug("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics

        Returns:
            Dictionary with cache stats
        """
        total_entries = len(self.cache)
        expired_entries = sum(1 for entry in self.cache.values() if entry.is_expired())

        rate_limits = {
            source: {
                "requests": len(limiter.requests),
                "max_requests": limiter.max_requests,
                "wait_time": limiter.get_wait_time(),
            }
            for source, limiter in self.rate_limiters.items()
        }

        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": total_entries - expired_entries,
            "rate_limits": rate_limits,
        }
