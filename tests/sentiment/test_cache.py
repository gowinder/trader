"""Tests for sentiment cache and rate limiting"""

import asyncio
from datetime import datetime, timedelta
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_trader.sentiment.cache import SentimentCache, RateLimiter, CacheEntry


def test_cache_entry_expiration():
    """Test cache entry expiration logic"""
    # Fresh entry
    entry = CacheEntry(
        data="test",
        timestamp=datetime.now(),
        ttl_seconds=60,
    )
    assert not entry.is_expired(), "Fresh entry should not be expired"

    # Expired entry
    old_entry = CacheEntry(
        data="test",
        timestamp=datetime.now() - timedelta(seconds=120),
        ttl_seconds=60,
    )
    assert old_entry.is_expired(), "Old entry should be expired"

    print("✓ Cache entry expiration test passed")


def test_rate_limiter():
    """Test rate limiter"""
    limiter = RateLimiter(max_requests=3, window_seconds=60)

    # Allow first 3 requests
    assert limiter.can_request(), "First request should be allowed"
    assert limiter.can_request(), "Second request should be allowed"
    assert limiter.can_request(), "Third request should be allowed"

    # Block 4th request
    assert not limiter.can_request(), "Fourth request should be blocked"

    # Check wait time
    wait_time = limiter.get_wait_time()
    assert wait_time > 0, "Should have wait time"
    assert wait_time <= 60, "Wait time should be within window"

    print("✓ Rate limiter test passed")


def test_cache_get_set():
    """Test cache get/set operations"""
    cache = SentimentCache(default_ttl=10)

    # Set and get
    cache.set("source1", "BTC", {"sentiment": "bullish"})
    result = cache.get("source1", "BTC")
    assert result is not None, "Should retrieve cached data"
    assert result["sentiment"] == "bullish"

    # Cache miss
    result = cache.get("source1", "ETH")
    assert result is None, "Should return None for cache miss"

    print("✓ Cache get/set test passed")


def test_cache_expiration():
    """Test cache expiration"""
    cache = SentimentCache(default_ttl=1)  # 1 second TTL

    # Set data
    cache.set("source1", "BTC", {"sentiment": "bullish"})

    # Should be cached
    result = cache.get("source1", "BTC")
    assert result is not None, "Should be cached"

    # Wait for expiration
    import time
    time.sleep(1.5)

    # Should be expired
    result = cache.get("source1", "BTC")
    assert result is None, "Should be expired"

    print("✓ Cache expiration test passed")


def test_cache_rate_limiting():
    """Test cache rate limiting"""
    cache = SentimentCache(max_requests_per_hour=3)

    # First 3 requests allowed
    assert cache.can_request("source1"), "First request allowed"
    assert cache.can_request("source1"), "Second request allowed"
    assert cache.can_request("source1"), "Third request allowed"

    # 4th blocked
    assert not cache.can_request("source1"), "Fourth request blocked"

    # Different source should have separate limit
    assert cache.can_request("source2"), "Different source should be allowed"

    print("✓ Cache rate limiting test passed")


def test_cache_cleanup():
    """Test expired entry cleanup"""
    cache = SentimentCache(default_ttl=1)

    # Add entries
    cache.set("source1", "BTC", {"data": 1})
    cache.set("source2", "ETH", {"data": 2})
    cache.set("source3", "BNB", {"data": 3})

    assert len(cache.cache) == 3, "Should have 3 entries"

    # Wait for expiration
    import time
    time.sleep(1.5)

    # Cleanup
    cache.cleanup_expired()

    assert len(cache.cache) == 0, "All expired entries should be cleaned"

    print("✓ Cache cleanup test passed")


def test_cache_stats():
    """Test cache statistics"""
    cache = SentimentCache(default_ttl=60)

    # Add entries
    cache.set("source1", "BTC", {"data": 1})
    cache.set("source2", "ETH", {"data": 2})

    # Request to trigger rate limiting
    cache.can_request("source1")
    cache.can_request("source1")

    # Get stats
    stats = cache.get_stats()

    assert stats["total_entries"] == 2
    assert stats["active_entries"] == 2
    assert "source1" in stats["rate_limits"]
    assert stats["rate_limits"]["source1"]["requests"] == 2

    print("✓ Cache stats test passed")


@pytest.mark.asyncio
async def test_cleanup_task():
    """Test background cleanup task"""
    cache = SentimentCache(default_ttl=1, cleanup_interval=2)

    # Start cleanup task
    await cache.start_cleanup_task()

    # Add expired entry
    cache.set("source1", "BTC", {"data": 1})

    # Wait for cleanup
    await asyncio.sleep(3)

    # Should be cleaned up
    assert len(cache.cache) == 0, "Cleanup task should remove expired entries"

    # Stop task
    await cache.stop_cleanup_task()

    print("✓ Cleanup task test passed")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Sentiment Cache Tests")
    print("=" * 60)
    print()

    test_cache_entry_expiration()
    test_rate_limiter()
    test_cache_get_set()
    test_cache_expiration()
    test_cache_rate_limiting()
    test_cache_cleanup()
    test_cache_stats()

    # Async test
    asyncio.run(test_cleanup_task())

    print()
    print("=" * 60)
    print("✓ All sentiment cache tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
