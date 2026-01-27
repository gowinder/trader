"""Find the correct CryptoPanic API endpoint"""

import asyncio
import os
from dotenv import load_dotenv
import httpx

load_dotenv()

API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")


async def test_endpoints():
    """Test different possible API endpoints"""
    if not API_KEY:
        print("❌ No API key configured")
        return

    print(f"Testing with API Key: {API_KEY[:10]}...")
    print()

    endpoints = [
        # V1 endpoints
        "https://cryptopanic.com/api/v1/posts/",
        "https://cryptopanic.com/api/posts/",
        "https://api.cryptopanic.com/v1/posts/",
        "https://api.cryptopanic.com/posts/",

        # V2 endpoints
        "https://cryptopanic.com/api/v2/posts/",
        "https://api.cryptopanic.com/v2/posts/",

        # Web API endpoints
        "https://cryptopanic.com/web-api/posts/",
        "https://cph-front-lb.cryptopanic.com/web-api/posts/",

        # Free tier endpoints (some APIs have different tiers)
        "https://cryptopanic.com/api/free/v1/posts/",
        "https://cryptopanic.com/api/pro/v1/posts/",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in endpoints:
            print(f"Testing: {url}")

            params = {"auth_token": API_KEY}

            try:
                response = await client.get(url, params=params)
                print(f"  Status: {response.status_code}")

                if response.status_code == 200:
                    try:
                        data = response.json()
                        if "results" in data:
                            print(f"  ✅ SUCCESS! Got {len(data['results'])} posts")
                            print(f"  Response structure: {list(data.keys())}")
                            if data['results']:
                                print(f"  First post: {data['results'][0].get('title', 'N/A')[:50]}...")
                            return url  # Found it!
                        else:
                            print(f"  ⚠️  200 but unexpected format: {list(data.keys())}")
                    except:
                        print(f"  ⚠️  200 but not JSON")
                elif response.status_code == 401:
                    print(f"  ⚠️  401 Unauthorized (endpoint exists, but auth issue)")
                elif response.status_code == 404:
                    print(f"  ❌ 404 Not Found")
                else:
                    print(f"  ❌ {response.status_code}: {response.text[:100]}")

            except Exception as e:
                print(f"  ❌ Error: {e}")

            print()

    print("=" * 60)
    print("No working endpoint found.")
    print()
    print("Possible reasons:")
    print("1. CryptoPanic API key format has changed")
    print("2. API requires additional authentication")
    print("3. API has been deprecated or moved")
    print()
    print("Recommendation:")
    print("- Contact CryptoPanic support")
    print("- Check if there's a new API registration process")
    print("- Consider using alternative: NewsAPI (which is working)")


if __name__ == "__main__":
    asyncio.run(test_endpoints())
