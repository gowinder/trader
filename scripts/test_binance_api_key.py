"""Test Binance Testnet API Key validity"""
import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import os

load_dotenv()

async def test_api_key():
    """Test if Binance Testnet API Key is valid"""

    api_key = os.getenv("TESTNET_API_KEY")
    api_secret = os.getenv("TESTNET_API_SECRET")

    print("=" * 60)
    print("🔑 Testing Binance Testnet API Key")
    print("=" * 60)
    print(f"API Key: {api_key[:10]}...{api_key[-10:]}" if api_key else "Not found")
    print(f"API Secret: {'*' * 20}")

    if not api_key or not api_secret:
        print("❌ API Key or Secret not found in .env!")
        return

    # Test with CCXT
    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "urls": {
                "fapi": "https://testnet.binancefuture.com/fapi/v1"
            }
        }
    })

    try:
        print("\n📡 Fetching account info...")
        balance = await exchange.fetch_balance()
        print("✅ API Key is VALID!")
        print(f"\n💰 Account Balance:")

        # Show USDT balance
        if "USDT" in balance["total"]:
            print(f"  USDT: {balance['total']['USDT']:.2f}")

        # Show all non-zero balances
        print(f"\n  All Balances:")
        for currency, amount in balance["total"].items():
            if amount > 0:
                print(f"    {currency}: {amount:.8f}")

    except ccxt.AuthenticationError as e:
        print(f"❌ Authentication Failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("  1. Visit: https://testnet.binancefuture.com/")
        print("  2. Login with GitHub account")
        print("  3. Go to API Management")
        print("  4. Generate NEW API Key & Secret")
        print("  5. Enable permissions: Reading, Trading, Futures")
        print("  6. Update .env file with new credentials")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_api_key())
