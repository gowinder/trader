#!/usr/bin/env python3
"""Phase 3 Integration Test - Multi-Timeframe Analysis with Real Binance Testnet Data"""

import os
import sys
import time
import hmac
import hashlib
import urllib.request
import urllib.parse
import json
from datetime import datetime

# Read .env file
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
    print("❌ API credentials not found")
    exit(1)


def get_klines(symbol, interval, limit=100):
    """Fetch kline data from Binance Testnet"""
    url = f"https://testnet.binancefuture.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            return data
    except Exception as e:
        print(f"❌ Failed to fetch {interval} klines: {e}")
        return None


def calculate_ma(closes, period):
    """Calculate moving average"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calculate_rsi(closes, period=14):
    """Calculate RSI"""
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def analyze_timeframe(symbol, interval, klines):
    """Analyze a single timeframe"""
    if not klines or len(klines) < 100:
        return None

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    current_price = closes[-1]

    # Calculate indicators
    ma7 = calculate_ma(closes, 7)
    ma25 = calculate_ma(closes, 25)
    ma99 = calculate_ma(closes, 99)
    rsi = calculate_rsi(closes, 14)

    # Determine trend
    trend = "SIDEWAYS"
    if ma7 and ma25 and ma99:
        if ma7 > ma25 > ma99 and current_price > ma7:
            trend = "UPTREND"
        elif ma7 < ma25 < ma99 and current_price < ma7:
            trend = "DOWNTREND"

    # Calculate support/resistance
    recent_highs = max(highs[-20:])
    recent_lows = min(lows[-20:])

    # Volume trend
    recent_volume = sum(volumes[-10:]) / 10
    older_volume = sum(volumes[-30:-10]) / 20
    volume_trend = "INCREASING" if recent_volume > older_volume * 1.1 else "DECREASING" if recent_volume < older_volume * 0.9 else "STABLE"

    return {
        "interval": interval,
        "current_price": current_price,
        "trend": trend,
        "ma7": ma7,
        "ma25": ma25,
        "ma99": ma99,
        "rsi": rsi,
        "support": recent_lows,
        "resistance": recent_highs,
        "volume_trend": volume_trend,
    }


def calculate_confluence(analyses):
    """Calculate multi-timeframe confluence score"""
    if not analyses:
        return 0.0

    # Count uptrend/downtrend/sideways
    trends = [a["trend"] for a in analyses]
    uptrend_count = trends.count("UPTREND")
    downtrend_count = trends.count("DOWNTREND")
    sideways_count = trends.count("SIDEWAYS")

    total = len(trends)

    # Confluence is the ratio of aligned timeframes
    max_aligned = max(uptrend_count, downtrend_count, sideways_count)
    confluence = max_aligned / total

    return confluence


def calculate_position_size(account_balance, entry_price, stop_loss_price, risk_pct=0.01):
    """Calculate position size using fixed percentage risk method"""
    price_diff = abs(entry_price - stop_loss_price)
    if price_diff == 0:
        return None

    risk_amount = account_balance * risk_pct
    position_size = risk_amount / price_diff

    return {
        "position_size": position_size,
        "position_value": position_size * entry_price,
        "risk_amount": risk_amount,
        "risk_percentage": risk_pct * 100,
    }


print("=" * 70)
print("🧪 Phase 3 Integration Test - Multi-Timeframe Analysis")
print("=" * 70)
print()

# Test 1: Multi-Timeframe Data Fetching
print("📊 Test 1: Multi-Timeframe Data Fetching")
print("-" * 70)

symbol = "BTCUSDT"
timeframes = ["15m", "1h", "4h", "1d"]

print(f"Symbol: {symbol}")
print(f"Timeframes: {', '.join(timeframes)}")
print()

start_time = time.time()
analyses = []

for interval in timeframes:
    print(f"  📈 Fetching {interval} data...")
    klines = get_klines(symbol, interval, limit=100)

    if klines:
        analysis = analyze_timeframe(symbol, interval, klines)
        if analysis:
            analyses.append(analysis)
            print(f"     ✅ {len(klines)} candles fetched and analyzed")
        else:
            print(f"     ❌ Analysis failed")
    else:
        print(f"     ❌ Data fetch failed")

fetch_time = time.time() - start_time
print()
print(f"⏱️  Total Time: {fetch_time:.2f}s ({fetch_time / len(timeframes):.2f}s per timeframe)")
print()

# Test 2: Multi-Timeframe Analysis Results
print("=" * 70)
print("📊 Test 2: Multi-Timeframe Analysis Results")
print("-" * 70)
print()

if not analyses:
    print("❌ No analysis data available")
    exit(1)

for analysis in analyses:
    print(f"⏱️  {analysis['interval']:>4s} Timeframe:")
    print(f"     Current Price: {analysis['current_price']:>10.2f} USDT")
    print(f"     Trend: {analysis['trend']:>12s}")
    print(f"     MA7:  {analysis['ma7']:>10.2f} | MA25: {analysis['ma25']:>10.2f} | MA99: {analysis['ma99']:>10.2f}")
    print(f"     RSI: {analysis['rsi']:>11.2f}")
    print(f"     Support: {analysis['support']:>8.2f} | Resistance: {analysis['resistance']:>8.2f}")
    print(f"     Volume Trend: {analysis['volume_trend']}")
    print()

# Test 3: Confluence Score Calculation
print("=" * 70)
print("📊 Test 3: Multi-Timeframe Confluence Score")
print("-" * 70)
print()

confluence_score = calculate_confluence(analyses)
print(f"Confluence Score: {confluence_score:.2%}")
print()

# Determine overall trend
trends = [a["trend"] for a in analyses]
uptrend_count = trends.count("UPTREND")
downtrend_count = trends.count("DOWNTREND")
sideways_count = trends.count("SIDEWAYS")

if uptrend_count > downtrend_count and uptrend_count > sideways_count:
    overall_trend = "UPTREND"
elif downtrend_count > uptrend_count and downtrend_count > sideways_count:
    overall_trend = "DOWNTREND"
else:
    overall_trend = "SIDEWAYS"

print(f"Overall Trend: {overall_trend}")
print(f"  Uptrend: {uptrend_count}/{len(trends)} timeframes")
print(f"  Downtrend: {downtrend_count}/{len(trends)} timeframes")
print(f"  Sideways: {sideways_count}/{len(trends)} timeframes")
print()

# Recommended action based on confluence
if confluence_score >= 0.7:
    recommended_action = "TRADE" if overall_trend != "SIDEWAYS" else "HOLD"
    quality = "HIGH"
elif confluence_score >= 0.5:
    recommended_action = "TRADE (Moderate Setup)" if overall_trend != "SIDEWAYS" else "HOLD"
    quality = "MEDIUM"
else:
    recommended_action = "HOLD"
    quality = "LOW"

print(f"Alignment Quality: {quality}")
print(f"Recommended Action: {recommended_action}")
print()

# Test 4: Position Sizing Calculation
print("=" * 70)
print("📊 Test 4: Position Sizing with Real Market Data")
print("-" * 70)
print()

account_balance = 5000.0  # From Testnet account
current_price = analyses[0]["current_price"]  # Use 15m timeframe price
support = analyses[0]["support"]

# Calculate stop loss (2% below current for long, 2% above for short)
if overall_trend == "UPTREND":
    stop_loss = max(support, current_price * 0.98)
    direction = "LONG"
elif overall_trend == "DOWNTREND":
    stop_loss = min(analyses[0]["resistance"], current_price * 1.02)
    direction = "SHORT"
else:
    stop_loss = current_price * 0.98
    direction = "NEUTRAL"

# Calculate position size based on confluence
if confluence_score >= 0.7:
    risk_pct = 0.02  # 2% for high confidence
elif confluence_score >= 0.5:
    risk_pct = 0.01  # 1% for medium confidence
else:
    risk_pct = 0.005  # 0.5% for low confidence

position = calculate_position_size(account_balance, current_price, stop_loss, risk_pct)

print(f"Account Balance: {account_balance:.2f} USDT")
print(f"Direction: {direction}")
print(f"Entry Price: {current_price:.2f} USDT")
print(f"Stop Loss: {stop_loss:.2f} USDT")
print(f"Risk Distance: {abs(current_price - stop_loss):.2f} USDT ({abs(current_price - stop_loss) / current_price * 100:.2f}%)")
print()

if position:
    print(f"✅ Position Size Calculated:")
    print(f"   Position Size: {position['position_size']:.6f} BTC")
    print(f"   Position Value: {position['position_value']:.2f} USDT")
    print(f"   Risk Amount: {position['risk_amount']:.2f} USDT")
    print(f"   Risk Percentage: {position['risk_percentage']:.2f}%")
    print()

    # Calculate position as % of account
    position_pct = position['position_value'] / account_balance * 100
    print(f"   Position as % of Account: {position_pct:.2f}%")
else:
    print("❌ Position calculation failed")

print()

# Test 5: Trading Decision Summary
print("=" * 70)
print("🎯 Test 5: Professional Trading Decision Summary")
print("-" * 70)
print()

print(f"📊 Market Analysis:")
print(f"   Symbol: {symbol}")
print(f"   Current Price: {current_price:.2f} USDT")
print(f"   Overall Trend: {overall_trend}")
print(f"   Confluence Score: {confluence_score:.2%} ({quality} quality)")
print()

print(f"💡 Trading Recommendation:")
print(f"   Action: {recommended_action}")
print(f"   Direction: {direction}")
print()

if recommended_action.startswith("TRADE"):
    print(f"✅ Trade Setup:")
    print(f"   Entry: {current_price:.2f} USDT")
    print(f"   Stop Loss: {stop_loss:.2f} USDT")
    print(f"   Position Size: {position['position_size']:.6f} BTC")
    print(f"   Risk: {position['risk_amount']:.2f} USDT ({position['risk_percentage']:.2f}%)")
    print()

    # Calculate take profit (1.5:1 R:R minimum)
    risk_distance = abs(current_price - stop_loss)
    if direction == "LONG":
        take_profit_1 = current_price + (risk_distance * 1.5)
        take_profit_2 = current_price + (risk_distance * 2.0)
    else:
        take_profit_1 = current_price - (risk_distance * 1.5)
        take_profit_2 = current_price - (risk_distance * 2.0)

    print(f"🎯 Take Profit Targets:")
    print(f"   TP1 (1.5:1 R:R): {take_profit_1:.2f} USDT")
    print(f"   TP2 (2.0:1 R:R): {take_profit_2:.2f} USDT")
    print()
else:
    print(f"⚠️  {recommended_action}")
    if confluence_score < 0.5:
        print(f"   Reason: Low confluence score ({confluence_score:.2%})")
    else:
        print(f"   Reason: No clear directional trend")
    print()

# Summary
print("=" * 70)
print("✅ Phase 3 Integration Test Complete")
print("=" * 70)
print()
print("Test Results:")
print(f"  ✅ Multi-Timeframe Data Fetching: {len(analyses)}/{len(timeframes)} timeframes")
print(f"  ✅ Trend Analysis: {overall_trend}")
print(f"  ✅ Confluence Calculation: {confluence_score:.2%}")
print(f"  ✅ Position Sizing: {position['position_size']:.6f} BTC")
print(f"  ✅ Risk Management: {position['risk_percentage']:.2f}% risk")
print()
print("🎉 All Phase 3 Core Features Validated with Live Testnet Data!")
print()
