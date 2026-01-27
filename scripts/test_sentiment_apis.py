"""Test sentiment analysis APIs"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
import httpx

load_dotenv()


async def test_cryptopanic():
    """Test CryptoPanic API with different parameters"""
    api_key = os.getenv("CRYPTOPANIC_API_KEY", "")

    if not api_key:
        print("❌ CryptoPanic API Key not configured")
        return

    print("=" * 60)
    print("Testing CryptoPanic API")
    print("=" * 60)
    print(f"API Key: {api_key[:10]}... (length: {len(api_key)})")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Basic endpoint (no filters)
        print("Test 1: Basic endpoint (no filters)")
        url1 = "https://cryptopanic.com/api/v1/posts/"
        params1 = {"auth_token": api_key}

        try:
            response = await client.get(url1, params=params1)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Success! Got {len(data.get('results', []))} posts")
                if data.get("results"):
                    print(f"   First post: {data['results'][0].get('title', 'N/A')[:50]}...")
            else:
                print(f"   ✗ Failed: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        print()

        # Test 2: With currency filter
        print("Test 2: With currency filter (BTC)")
        params2 = {
            "auth_token": api_key,
            "currencies": "BTC",
        }

        try:
            response = await client.get(url1, params=params2)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Success! Got {len(data.get('results', []))} posts")
            else:
                print(f"   ✗ Failed: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        print()

        # Test 3: With kind filter
        print("Test 3: With currency + kind filter")
        params3 = {
            "auth_token": api_key,
            "currencies": "BTC",
            "kind": "news",
        }

        try:
            response = await client.get(url1, params=params3)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Success! Got {len(data.get('results', []))} posts")
            else:
                print(f"   ✗ Failed: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        print()

        # Test 4: API info endpoint
        print("Test 4: Check API info")
        info_url = "https://cryptopanic.com/api/v1/"
        params4 = {"auth_token": api_key}

        try:
            response = await client.get(info_url, params=params4)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print(f"   ✓ API is accessible")
                print(f"   Response: {response.text[:200]}")
            else:
                print(f"   ✗ Failed: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

    print()


async def test_newsapi():
    """Test NewsAPI"""
    api_key = os.getenv("NEWSAPI_KEY", "")

    if not api_key:
        print("❌ NewsAPI Key not configured")
        return

    print("=" * 60)
    print("Testing NewsAPI")
    print("=" * 60)
    print(f"API Key: {api_key[:10]}... (length: {len(api_key)})")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Simple query
        print("Test 1: Simple Bitcoin query")
        url = "https://newsapi.org/v2/everything"

        # Calculate from date (NewsAPI requires date in YYYY-MM-DD format)
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        params = {
            "apiKey": api_key,
            "q": "Bitcoin",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "from": from_date,
        }

        try:
            response = await client.get(url, params=params)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                total = data.get("totalResults", 0)
                articles = data.get("articles", [])
                print(f"   ✓ Success! Total results: {total}")
                print(f"   ✓ Fetched: {len(articles)} articles")
                if articles:
                    print(f"   First article: {articles[0].get('title', 'N/A')[:50]}...")
            else:
                print(f"   ✗ Failed: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        print()

        # Test 2: Alternative query
        print("Test 2: Alternative query (BTC OR cryptocurrency)")
        params2 = {
            "apiKey": api_key,
            "q": "BTC OR cryptocurrency",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 5,
            "from": from_date,
        }

        try:
            response = await client.get(url, params=params2)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Success! Got {len(data.get('articles', []))} articles")
            else:
                print(f"   ✗ Failed: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

    print()


async def main():
    """Run all tests"""
    await test_cryptopanic()
    await test_newsapi()

    print("=" * 60)
    print("Testing Complete")
    print("=" * 60)
    print()
    print("如果看到 404 错误：")
    print("  - CryptoPanic: 可能 API 端点已变更，检查文档")
    print("  - NewsAPI: 检查 API Key 是否有效")
    print()
    print("如果返回 0 条结果：")
    print("  - 检查时间范围（最近24小时可能没有新闻）")
    print("  - 尝试扩大时间范围（7天）")


if __name__ == "__main__":
    asyncio.run(main())
