#!/usr/bin/env python3
"""Simple Binance Testnet API verification without dependencies"""

import os
import time
import hmac
import hashlib
import urllib.request
import urllib.parse
import json

# Read .env file manually
env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
api_key = None
api_secret = None

if os.path.exists(env_file):
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('TESTNET_API_KEY='):
                api_key = line.split('=', 1)[1].strip('"\'')
            elif line.startswith('TESTNET_API_SECRET='):
                api_secret = line.split('=', 1)[1].strip('"\'')

if not api_key or not api_secret:
    print("❌ TESTNET_API_KEY or TESTNET_API_SECRET not found in .env")
    exit(1)

print("=" * 60)
print("🔑 Testing Binance Testnet API Key")
print("=" * 60)
print(f"API Key: {api_key[:10]}...{api_key[-10:]}")
print()

# Test 1: Get server time (no auth required)
print("📡 Test 1: Server Time (No Auth)")
try:
    url = "https://testnet.binancefuture.com/fapi/v1/time"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())
        server_time = data['serverTime']
        print(f"✅ Server Time: {server_time}")
        print()
except Exception as e:
    print(f"❌ Failed: {e}")
    print()

# Test 2: Get account info (requires auth)
print("📡 Test 2: Account Info (Auth Required)")
try:
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"

    # Sign the request
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    query_string += f"&signature={signature}"
    url = f"https://testnet.binancefuture.com/fapi/v2/account?{query_string}"

    req = urllib.request.Request(url)
    req.add_header('X-MBX-APIKEY', api_key)

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        total_balance = float(data.get('totalWalletBalance', 0))
        available_balance = float(data.get('availableBalance', 0))

        print(f"✅ Account Info Retrieved")
        print(f"   Total Balance: {total_balance} USDT")
        print(f"   Available Balance: {available_balance} USDT")
        print(f"   Can Trade: {data.get('canTrade', False)}")
        print()

except urllib.error.HTTPError as e:
    error_body = e.read().decode('utf-8')
    print(f"❌ HTTP Error {e.code}: {error_body}")
    print()
except Exception as e:
    print(f"❌ Failed: {e}")
    print()

# Test 3: Get market data
print("📡 Test 3: Market Data (No Auth)")
try:
    url = "https://testnet.binancefuture.com/fapi/v1/ticker/24hr?symbol=BTCUSDT"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())
        print(f"✅ BTC/USDT Market Data")
        print(f"   Price: {float(data['lastPrice']):.2f} USDT")
        print(f"   24h Change: {float(data['priceChangePercent']):.2f}%")
        print(f"   24h Volume: {float(data['volume']):.2f} BTC")
        print()
except Exception as e:
    print(f"❌ Failed: {e}")
    print()

print("=" * 60)
print("🏁 API Verification Complete")
print("=" * 60)
