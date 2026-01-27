"""Diagnose Binance Testnet connection issues"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
import ccxt.async_support as ccxt

load_dotenv()


async def test_binance_testnet():
    """Test Binance Testnet with different configurations"""

    api_key = os.getenv("TESTNET_API_KEY", "")
    api_secret = os.getenv("TESTNET_API_SECRET", "")

    print("=" * 60)
    print("BINANCE TESTNET DIAGNOSIS")
    print("=" * 60)
    print()

    # Check environment variables
    print("1. Environment Variables:")
    print(f"   TRADING_MODE: {os.getenv('TRADING_MODE')}")
    print(f"   TESTNET_EXCHANGE: {os.getenv('TESTNET_EXCHANGE')}")
    print(f"   API_KEY length: {len(api_key)}")
    print(f"   API_SECRET length: {len(api_secret)}")
    print(f"   API_KEY prefix: {api_key[:10]}...")
    print(f"   API_KEY suffix: ...{api_key[-10:]}")
    print()

    if len(api_key) != 64:
        print(f"⚠️  WARNING: API_KEY should be 64 characters, got {len(api_key)}")
        print()

    # Test 1: Standard testnet URL (current implementation)
    print("2. Test Standard Testnet URL:")
    print("   URL: https://testnet.binancefuture.com/fapi/v1")

    config1 = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "urls": {
                "fapi": "https://testnet.binancefuture.com/fapi/v1"
            }
        },
    }

    exchange1 = ccxt.binance(config1)

    try:
        # Try to fetch ticker (doesn't require auth)
        ticker = await exchange1.fetch_ticker("BTC/USDT")
        print(f"   ✓ Success! BTC/USDT: {ticker['last']}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    finally:
        await exchange1.close()

    print()

    # Test 2: Alternative testnet URL configuration
    print("3. Test Alternative URL Configuration:")
    print("   Setting testnet=True in options")

    config2 = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    }

    exchange2 = ccxt.binance(config2)
    exchange2.set_sandbox_mode(True)  # CCXT way to enable testnet

    try:
        # Print the actual URL being used
        if hasattr(exchange2, 'urls'):
            print(f"   Actual URL: {exchange2.urls}")

        ticker = await exchange2.fetch_ticker("BTC/USDT")
        print(f"   ✓ Success! BTC/USDT: {ticker['last']}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    finally:
        await exchange2.close()

    print()

    # Test 3: Check if API key has correct permissions
    print("4. Test API Key Permissions:")

    config3 = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    }

    exchange3 = ccxt.binance(config3)
    exchange3.set_sandbox_mode(True)

    try:
        # Try to fetch account balance (requires auth)
        balance = await exchange3.fetch_balance({"type": "future"})
        print(f"   ✓ API Key valid! USDT Balance: {balance.get('USDT', {}).get('total', 0)}")
    except ccxt.AuthenticationError as e:
        print(f"   ✗ Authentication failed: {e}")
        print()
        print("   Possible causes:")
        print("   1. API Key is from wrong environment (production vs testnet)")
        print("   2. API Key has been deleted or expired")
        print("   3. API Key permissions are insufficient")
        print("   4. API Key/Secret has spaces or invisible characters")
        print()
        print("   Solution:")
        print("   - Visit: https://testnet.binancefuture.com/")
        print("   - Login with GitHub")
        print("   - Go to API Management")
        print("   - Delete old API Key")
        print("   - Create new API Key with 'Enable Reading' and 'Enable Futures'")
        print("   - Copy the 64-character key carefully (no spaces)")
    except Exception as e:
        print(f"   ✗ Other error: {e}")
    finally:
        await exchange3.close()

    print()
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_binance_testnet())
