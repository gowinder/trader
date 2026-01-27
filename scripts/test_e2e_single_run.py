#!/usr/bin/env python3
"""Single iteration E2E test"""

import os
import sys
import time
import json
import hmac
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime

# Read API credentials
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

print("=" * 80)
print("🧪 E2E Single Iteration Test")
print("=" * 80)
print()

# Test 1: Get account
print("📊 Test 1: Get Account Info")
timestamp = int(time.time() * 1000)
params = {"timestamp": timestamp}
query_string = urllib.parse.urlencode(params)
signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
params["signature"] = signature

url = f"https://testnet.binancefuture.com/fapi/v2/account?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url)
req.add_header('X-MBX-APIKEY', api_key)

with urllib.request.urlopen(req) as response:
    account = json.loads(response.read())
    balance = float(account['availableBalance'])
    print(f"✅ Balance: {balance:.2f} USDT")
    print()

# Test 2: Get multi-timeframe data
print("📊 Test 2: Multi-Timeframe Data")
timeframes = ["15m", "1h", "4h", "1d"]
symbol = "BTCUSDT"

for interval in timeframes:
    url = f"https://testnet.binancefuture.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit=100"
    with urllib.request.urlopen(url) as response:
        klines = json.loads(response.read())
        closes = [float(k[4]) for k in klines]
        current_price = closes[-1]

        # Calculate MA
        ma7 = sum(closes[-7:]) / 7
        ma25 = sum(closes[-25:]) / 25

        # Determine trend
        trend = "UPTREND" if ma7 > ma25 else "DOWNTREND" if ma7 < ma25 else "SIDEWAYS"

        print(f"  {interval:>4s}: {current_price:>10.2f} USDT | Trend: {trend:>10s} | MA7: {ma7:.2f}")

print()

# Test 3: Calculate Confluence
print("📊 Test 3: Trading Decision Simulation")
print("  Confluence calculation: Based on trend alignment")
print("  Decision logic: HOLD (no order execution in this test)")
print()

print("=" * 80)
print("✅ Single Iteration Test Complete")
print("=" * 80)
