#!/usr/bin/env python3
"""Phase 2: Binance Testnet integration test

Simple test script without pytest dependency
Tests:
1. Testnet connection
2. K-line data consistency
3. Complete trading flow simulation
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_trader.config import config
from ai_trader.exchange import create_exchange_client


async def test_testnet_connection():
    """Test 1: Basic testnet connection"""
    print("\n=== Test 1: Testnet Connection ===")

    # Ensure testnet mode
    config.trading_mode = "testnet"
    config.testnet_exchange = "binance"

    client = create_exchange_client()

    try:
        # Test connection by fetching ticker
        print("Fetching BTC/USDT ticker...")
        ticker = await client.get_ticker("BTC/USDT")

        assert ticker is not None, "Ticker should not be None"
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last_price > 0
        assert ticker.bid_price > 0
        assert ticker.ask_price > 0

        print(f"✓ Connection successful")
        print(f"  Symbol: {ticker.symbol}")
        print(f"  Price: ${ticker.last_price:,.2f}")
        print(f"  Bid/Ask: ${ticker.bid_price:,.2f} / ${ticker.ask_price:,.2f}")

        return True

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

    finally:
        await client.close()


async def test_kline_data_consistency():
    """Test 2: K-line data validation"""
    print("\n=== Test 2: K-line Data Consistency ===")

    config.trading_mode = "testnet"
    config.testnet_exchange = "binance"

    client = create_exchange_client()

    try:
        symbol = "BTC/USDT"
        interval = "1h"
        limit = 100

        print(f"Fetching {limit} klines for {symbol} ({interval})...")
        klines = await client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        # Validate data
        assert len(klines) > 0, "Should have kline data"
        print(f"  Received: {len(klines)} klines")

        # Validate structure
        errors = []
        for i, kline in enumerate(klines):
            # Check required fields
            required_fields = ["timestamp", "open", "high", "low", "close", "volume"]
            for field in required_fields:
                if field not in kline:
                    errors.append(f"Missing field '{field}' at index {i}")

            # OHLC consistency
            if kline["high"] < kline["low"]:
                errors.append(f"High < Low at index {i}")
            if kline["high"] < kline["open"]:
                errors.append(f"High < Open at index {i}")
            if kline["high"] < kline["close"]:
                errors.append(f"High < Close at index {i}")
            if kline["low"] > kline["open"]:
                errors.append(f"Low > Open at index {i}")
            if kline["low"] > kline["close"]:
                errors.append(f"Low > Close at index {i}")

            # Time ordering
            if i > 0:
                if kline["timestamp"] <= klines[i-1]["timestamp"]:
                    errors.append(f"Timestamp not ascending at index {i}")

        if errors:
            print("✗ Data validation failed:")
            for error in errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            return False

        print("✓ Data validation passed")
        print(f"  First: {klines[0]['timestamp']}")
        print(f"  Last: {klines[-1]['timestamp']}")
        print(f"  Price range: ${min(k['low'] for k in klines):,.2f} - ${max(k['high'] for k in klines):,.2f}")

        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await client.close()


async def test_complete_trading_flow():
    """Test 3: Complete trading flow simulation"""
    print("\n=== Test 3: Complete Trading Flow ===")

    config.trading_mode = "testnet"
    config.testnet_exchange = "binance"

    client = create_exchange_client()

    try:
        symbol = "BTC/USDT"

        # Step 1: Fetch market data
        print("Step 1: Fetching market data...")
        ticker = await client.get_ticker(symbol)
        print(f"  ✓ Current price: ${ticker.last_price:,.2f}")

        # Step 2: Fetch klines
        print("Step 2: Fetching klines for analysis...")
        klines = await client.get_klines(symbol, "1h", 50)
        print(f"  ✓ Received {len(klines)} klines")

        # Step 3: Fetch account info
        print("Step 3: Fetching account info...")
        account = await client.get_account_info()
        print(f"  ✓ Total balance: ${account.total_balance:,.2f}")
        print(f"  ✓ Available: ${account.available_balance:,.2f}")

        # Step 4: Simulate decision
        print("Step 4: Simulating trading decision...")
        last_close = klines[-1]["close"]
        prev_close = klines[-2]["close"]

        if last_close > prev_close:
            decision = "LONG"
            entry_price = ticker.ask_price
        else:
            decision = "SHORT"
            entry_price = ticker.bid_price

        print(f"  ✓ Decision: {decision} at ${entry_price:,.2f}")

        # Step 5: Calculate order parameters
        print("Step 5: Calculating order parameters...")
        position_size = 0.001  # BTC
        stop_loss_pct = 0.02
        take_profit_pct = 0.03

        if decision == "LONG":
            stop_loss = entry_price * (1 - stop_loss_pct)
            take_profit = entry_price * (1 + take_profit_pct)
        else:
            stop_loss = entry_price * (1 + stop_loss_pct)
            take_profit = entry_price * (1 - take_profit_pct)

        print(f"  ✓ Size: {position_size} BTC")
        print(f"  ✓ Stop loss: ${stop_loss:,.2f}")
        print(f"  ✓ Take profit: ${take_profit:,.2f}")

        print("\n✓ Complete trading flow validated")
        print("  [Data] → [Analysis] → [Decision] → [Order Params]")

        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await client.close()


async def main():
    """Run all tests"""
    print("=" * 60)
    print("PHASE 2: BINANCE TESTNET INTEGRATION TESTS")
    print("=" * 60)

    results = []

    # Test 1: Connection
    results.append(("Testnet Connection", await test_testnet_connection()))

    # Test 2: K-line data
    results.append(("K-line Data Consistency", await test_kline_data_consistency()))

    # Test 3: Trading flow
    results.append(("Complete Trading Flow", await test_complete_trading_flow()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nPassed: {passed}/{total} tests")

    if passed == total:
        print("\n✓ All Phase 2 integration tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed. Please review.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
